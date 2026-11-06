# CACHE-05.1 — Profiling e ottimizzazione ClinVar

Data: **30 ottobre 2026**. Riduzione misurata del caricamento globale delle
liste: **51,0% sulla mediana di tre confronti appaiati**. Evidenze e risultati
scientifici identici; nessuna modifica a formule, criteri ACMG/PVS1, contratto
ga2, schema ClinVar, dataset installato o retention. CACHE-06 non avviato.

## 1. Percorso analizzato

Letti CACHE-04/04.1, CACHE-05, istruzioni del repository e moduli richiesti.

1. `variant-browser.openSample` apre il workspace e invoca `loadPage`.
2. La lista passa da `api.variants.sample_variants` a `query.list_variants`.
3. `LocalEvidence` apre un reader ClinVar fissato allo snapshot corrente.
4. La query verifica la LRU dell'ordine, qualificata da indice, snapshot,
   parametri, campione, reference, ruleset e altre fonti.
5. Al primo calcolo per priority legge tutti i candidati pertinenti, non solo
   quelli della prima pagina. Recupera contesti gene/frequenza/occorrenza/famiglia.
6. L'adapter deduplica gli alleli, esegue lookup genomico batch, legge varianti e
   aggregati per Variation ID e converte le evidenze. I conteggi SCV raggruppati
   già presenti per la visualizzazione restano distinti dalle submission dettagliate.
7. `_compact_variant` costruisce le righe e richiama `score_variant` e
   `apply_clinvar_evidence`. Poi filtri, ordine globale e selezione della pagina.
8. Il reader viene chiuso prima della risposta. La risposta è serializzata e
   `loadPage` accoda le righe e renderizza il workspace.

Le pagine successive riusano l'ordine LRU e valutano le righe della pagina.
Richieste indipendenti per campioni diversi aprono reader indipendenti e possono
incontrare gli stessi alleli. Il dettaglio è un percorso separato: condivide un
reader nella richiesta, carica la pagina SCV e calcola la priority con lo stesso
snapshot. Non viene richiesto per tutte le righe prima di mostrare la lista.

Prima di CACHE-05.1, ogni allele qualificato con FASTA apriva la reference e
rileggeva il `.fai`; `acmg_reference.verify` ripeteva l'apertura per verificare
l'allele normalizzato. I contig venivano riqualificati ripetutamente e i path
venivano risolti/stat per ogni allele. Il digest del FASTA era già in una LRU
di processo: il primo checksum completo non era ripetuto per ogni variante.

## 2. Metodo e baseline prima delle modifiche

Run: `20261015_Run_723_CancerHS2`, **2.609 varianti distinte**, **10 campioni**,
**7.996 righe complessive** nelle liste dei campioni. Stesso snapshot di CACHE-05:

`composite-sha256:da8e890d1ad7950bb61fa74218dcb86a82629d6c3ddaba76d0e8af08446038a7`.

Prima di modificare il codice applicativo sono stati salvati i sorgenti rilevanti
e relativi SHA-256 in `/tmp/helper-cache051/before-source/` e
`before-source.json`, poi eseguiti cProfile e tre benchmark senza profiler.

Il benchmark conserva esattamente lo scenario CACHE-05: acquisizione degli
alleli distinti della run, poi una richiesta lista per ogni campione con
`limit=1`. Quest'ultima calcola comunque l'ordine globale del campione.
La run clinica non viene aperta in scrittura: si verifica assenza WAL, si copia
l'indice in una directory temporanea e si controllano size/mtime/SHA-256 della
sorgente. ClinVar è aperto read-only. Non si copiano o modificano i database
ClinVar installati. Socket e trasporto ClinVar sono vietati durante le misure.

Le tre ripetizioni iniziali, in processi nuovi, riproducono la baseline:

| Metrica | CACHE-05 pubblicato | Mediana iniziale CACHE-05.1 |
|---|---:|---:|
| Acquisizione 2.609 alleli | 7,918 s | 7,517 s |
| Liste globali dei 10 campioni | 7,471 s | 7,332 s |
| ClinVar nelle liste | 4,370 s | 4,334 s |
| Scoring | 1,338 s | 1,312 s |
| HTTP ClinVar | 0 | 0 |

Non è stata svuotata la cache del sistema operativo. Si distinguono **primo
accesso del processo**, con checksum reference non ancora in LRU, e **reference
già verificata nel processo**. Non si dichiara una misura hardware a disco freddo.

## 3. Profiling delle fasi

Tempi cumulativi strumentati; molte fasi sono annidate e **non vanno sommate**.
Le percentuali di miglioramento nella sezione successiva usano esclusivamente
misure senza profiler. I tempi SQL includono execute e consumo delle righe.

| Fase | Prima: esecuzioni / tempo | Dopo: esecuzioni / tempo |
|---|---:|---:|
| Apertura reader ClinVar, inclusa validazione | 11 / 0,00957 s | 11 / 0,00817 s |
| Lettura manifest del reader | 22 / 0,00290 s | 22 / 0,00241 s |
| Selezione metadati reference | 21.168 / 0,12098 s | 11 / 0,00013 s |
| Apertura reference e controlli file | 21.168 / 7,89056 s | 11 / 0,00476 s |
| Costruzione IndexedFasta/parsing `.fai` (sottofase) | 21.168 / 6,85056 s | 11 / 0,00388 s |
| Checksum integrale FASTA, cache miss | 1 / 6,1704 s | 1 / 6,1700 s |
| Qualificazione assembly | 10.605 / 0,05132 s | 10.605 / 0,03267 s |
| Qualificazione contig | 10.584 / 0,20217 s | 229 / 0,00474 s |
| Normalizzazione e verifica della forma normalizzata | 21.168 / 0,08234 s | 21.168 / 0,05969 s |
| Costruzione risultato/hash ga2 | 10.605 / 0,27269 s | 10.605 / 0,16852 s |
| Matching SQLite | 78 SELECT / 0,09207 s | 78 SELECT / 0,08891 s |
| Lettura variante/aggregati/RCV | 46 SELECT / 0,15979 s | 46 SELECT / 0,14926 s |
| Conversione adapter | 10.605 / 0,27465 s | 10.605 / 0,26046 s |
| Costruzione righe, escluso scoring | 7.996 / circa 0,621 s | 7.996 / circa 0,621 s |
| Scoring score/apply | 7.996 + 7.996 / 2,97482 s | 7.996 + 7.996 / 2,98737 s |
| Filtro + ordinamento priority | 10 + 10 / 0,01103 s | 10 + 10 / 0,01040 s |
| Codifica cursor/paginazione | 10 / 0,00039 s | 10 / 0,00040 s |

La costruzione esclusa dal punteggio è ottenuta sottraendo il tempo score/apply
misurato dal wrapper al tempo inclusivo di `_compact_variant`. Il primo checksum
non è nascosto nei tempi SQL: da solo spiega gran parte del primo accesso.

La serializzazione di una pagina reale da 200 righe, misurata separatamente
senza cProfile tramite `jsonable_encoder` e JSON, richiede 0,165 s prima e
0,159 s dopo; payload identico da **1.832.949 byte**. Non è il costo dominante
del caricamento globale. Le copie delle righe per la presentazione e la provenance
non sono state compattate, così il confronto conserva l'intero payload.

Il lookup/adapter usava già SELECT batch e deduplicazione degli ID; non sono
emersi SELECT per variante o caricamenti di tutte le submission da eliminare.
I conteggi raggruppati per la presentazione sono una parte piccola del costo e
restano invariati rispetto alla versione corrente del working tree.

## 4. Ottimizzazioni introdotte

Modifiche applicative limitate a tre file:

- `helper_next/core/biological_identity.py`: aggiunta `allele_refs_batch`, che
  chiama la stessa generazione ga2 e mantiene un dizionario locale al batch per
  assembly. Riusa selezione reference, reader FASTA/FAI, metadati/digest e contig
  qualificati. Chiude tutti i reader nel `finally`, anche su interruzione.
- `helper_next/core/acmg_reference.py`: il verificatore esistente può ricevere
  internamente la reference già aperta e i suoi metadati. Continua a verificare
  checksum configurato, REF normalizzato e normalizzazione. Non chiude risorse
  di cui è proprietario il batch; l'uso autonomo continua ad aprire/chiudere il
  proprio reader come prima.
- `helper_variants/clinvar_local.py`: `lookup_batch` qualifica gli input validi
  mediante il percorso batch; conserva gestione degli input invalidi, risultati
  uno-a-uno, SQL, deduplicazione delle chiavi e matching esistenti.

Nessun nuovo algoritmo di normalizzazione o digest. I controlli REF originali
e normalizzati rimangono entrambi, così come i 21.168 passaggi di normalizzazione
del caso misurato. Non si è introdotto un percorso SNV che eviti la reference:
il guadagno misurato viene dal riuso delle risorse, conservando la semantica.

Nessuna nuova cache tra richieste. La memoria condivisa dura soltanto il batch;
il checksum conserva la LRU preesistente basata su path/size/mtime/ctime. Una
nuova operazione seleziona nuovamente risorse e metadati. Le risorse reference
devono continuare a essere amministrate come immutabili, come già previsto da
CACHE-02: non è aggiunta una garanzia per riscritture che mantengano tutti i
metadati usati dalla cache preesistente.

Non è stata alterata la LRU dell'ordine, né la sua invalidazione. Non si sposta
lo scoring dopo la paginazione e non si condividono evidenze fra richieste di
campioni diversi tramite una nuova cache. Il risparmio si applica a ogni batch,
anche quando i campioni successivi incontrano gli stessi alleli.

Altri file del task: `scripts/profile_clinvar_integration.py`, quattro test
aggiuntivi in `test_biological_identity.py` e questo report. Il benchmark
CACHE-05 originale non è stato modificato.

## 5. Confronto controllato e modifiche parallele

Durante il lavoro sono state rilevate modifiche parallele ad adapter, query,
frontend e relativi test, riguardanti classificazioni/conteggi visualizzati e
filtri. Sono state preservate e **non sono attribuite a CACHE-05.1**.
Il primo confronto integrale tra momenti diversi mostrava differenze proprio
in questi campi di presentazione: non è stato usato come prova di equivalenza.

Per isolare l'effetto delle tre modifiche di prestazioni, lo script supporta
`--baseline-source`: importa i sorgenti salvati prima dell'ottimizzazione e
ripristina, solo nel processo benchmark, le funzioni precedenti `allele_refs`,
`verify` e `lookup_batch`. Mantiene lo stesso adapter e la stessa query correnti,
non scrive i sorgenti e condivide correttamente la LRU checksum originale.

Eseguiti tre confronti appaiati prima/dopo in processi distinti. Gli SHA-256
dell'adapter e della query coincidono **all'interno di ogni coppia**; la terza
coppia conserva un successivo aggiornamento parallelo dell'adapter in entrambi
i lati. Nessuna comparazione attribuisce all'ottimizzazione un cambio di fonte,
regole di presentazione o query. Gli artefatti registrano i fingerprint.

## 6. Benchmark prima/dopo senza profiler

Mediane dei tre confronti appaiati sul medesimo indice e snapshot:

| Metrica | Prima controllato | Dopo | Riduzione |
|---|---:|---:|---:|
| Acquisizione 2.609 alleli, checksum non ancora in LRU | 7,508 s | 6,349 s | **15,44%** |
| Caricamento globale delle liste, 10 campioni | 7,430 s | 3,641 s | **51,00%** |
| ClinVar nelle liste | 4,390 s | 0,654 s | **85,10%** |
| Scoring | 1,307 s | 1,300 s | 0,60%, sostanzialmente invariato |
| Peak RSS del processo benchmark | 81.712 KiB | 80.660 KiB | 1,29% |
| Chiamate HTTP ClinVar | 0 | 0 | — |

Liste: prima 7,144–7,463 s; dopo 3,582–3,680 s. Il risultato del 51% riguarda
la **mediana**, non una garanzia di latenza o di riduzione minima per ogni prova.
Rispetto ai 7,471 s pubblicati in CACHE-05, 3,641 s corrispondono a circa 51,3%.

Ulteriore misura appaiata, pagina reale da 200 righe del primo campione:

| Scenario | Prima | Dopo | Riduzione |
|---|---:|---:|---:|
| Prima pagina, primo checksum del processo | 6,840 s | 6,526 s | **4,59%** |
| Prima pagina, reference già verificata, ordine LRU cancellato | 0,699 s | 0,334 s | **52,28%** |
| Pagina successiva, ordine LRU riusato | 0,206 s | 0,115 s | **44,34%** |
| Batch 2.609 alleli con reference già verificata | 1,369 s | 0,195 s | **85,74%** |
| Serializzazione della prima pagina | 0,165 s | 0,159 s | 3,94% |

La prima pagina non è stata resa più veloce restituendo un ordinamento parziale:
anche il caso caldo cancella l'ordine LRU prima della misura e rivaluta tutte
le varianti del campione. Lo stesso payload della prima pagina è verificato
identico fra caso freddo e caldo.

Le misure delle liste nello scenario CACHE-05 seguono il batch dell'intera run:
il checksum è quindi già nella LRU. Questo spiega perché il guadagno globale
supera quello del primo accesso del processo. La copia temporanea e la verifica
SHA dell'indice clinico non sono incluse negli intervalli applicativi.

## 7. Identità dei risultati e memoria

Confronto integrale, stessa versione corrente di adapter/query:

- Identici tutti i payload delle **2.609 evidenze**, compresi identità ga2,
  provenance, stato, classificazioni, review, conflitti e conteggi disponibili.
- Identici punteggi, componenti e ordine delle **7.996 righe** dei dieci campioni.
- Identiche prima pagina, pagina successiva e dimensione della risposta.
- FOUND **1.379**, NOT_FOUND **1.222**, UNRESOLVED **8**, AMBIGUOUS **0**, ERROR **0**;
  classificazione germline disponibile **1.374** in tutte le misure.
- Snapshot invariato, zero HTTP e fingerprint clinico invariato in ogni prova.

SHA-256 canonici uguali prima/dopo:

| Output | Digest |
|---|---|
| Tutte le evidenze | `f4b32131c40928cca40112bbd6a1aa80c6175f2418bb4877c75c573434bc79a8` |
| Tutte le righe, in ordine per campione | `6cc95fdf3da27898198bd3e3a98ad645ca4adb58a48e7dfec861ac940efabbc2` |
| Prima pagina | `51b0b5a8c27c7ae8470142a710dd73dd569785e364cba51b2fe745f6ca81cd13` |
| Pagina successiva | `81926de329966c1e0566eaafb8c748d6bc25ab7d4d04b28c8afdacde6db08a7d` |

La memoria applicativa aggiunta è limitata ai reader/metadati dei build presenti
nel batch e a contig già qualificati; non si carica il dataset ClinVar in RAM.
Il peak RSS del benchmark resta intorno a 79–80 MiB. Il comando diagnostico
`outputs` trattiene invece tutte le righe e ne costruisce JSON canonico per il
confronto: il suo peak di circa 340 MiB è memoria della **verifica esaustiva**,
non una nuova cache del caricamento ordinario.

## 8. Frontend e serializzazione

Nessuna ottimizzazione frontend introdotta da questo task. Ispezionati apertura
campione, lista, ordinamento, ripristino route, caricamento dettaglio e gestione
snapshot. La prima pagina dipende dalla lista, non dai recuperi accessori del
dettaglio; il costo misurato dominante era nel backend reference.

La verifica Node del vero `loadPage` controlla richieste e invalidazione: una
richiesta per caricamento normale; al cambio snapshot durante la paginazione,
risposta nuova e ripartenza dalla prima pagina senza mescolare le righe.
Non è una misura del rendering DOM, della rete o delle richieste effettive di
una sessione browser. **Il frontend reale non è stato profilato nel browser**:
resta non autorizzata la precedente esecuzione Chrome fuori sandbox. I due
test browser opt-in sono dichiarati saltati, non presentati come verifiche UI.

Non si rimuove provenance per ridurre il payload, non si aggiungono framework,
stato parallelo o nuovi livelli di caching. La serializzazione da circa 0,16 s
e il payload da 1,83 MB restano limiti misurati, senza assumere che dominarne
la riduzione migliorerebbe il caso principale più del riuso della reference.

## 9. Test e verifiche

Regressione: **566 passed, 2 skipped, 185 subtests passed**, 32,65 s.
XML: `/tmp/helper-cache051/regression.xml`.

Inclusi provider legacy/locale, adapter, query, API, viewer/Node, registry,
indexer/store, gnomAD, priority, ga2, contesto ACMG, meccanismi e PVS1/calcolatore
molecolare. Sono coperti SNV/indel, assembly, multialleliche, matching ambiguo,
cambio snapshot, invalidazione, chiusura reader e CURRENT/BACKUP.

Quattro test aggiunti verificano:

- Risultati batch uguali a quelli puntuali, inclusi indel ripetute, alias,
  multialleliche, REF errato e input non supportati; una sola apertura reference
  e mantenimento di entrambe le verifiche di normalizzazione.
- Chiusura della reference su interruzione del batch.
- Nuova acquisizione dei metadati a ogni operazione quando cambia la reference.
- Assembly distinti e preservazione degli errori di checksum configurato.

I test non confrontano soglie temporali fragili: verificano risultati e durata
delle risorse. Il test di modifica reference forza una revisione mtime esplicita
perché la sandbox può assegnare lo stesso timestamp a scritture consecutive;
verifica il contratto della LRU checksum già presente.

I test API sono eseguiti fuori sandbox, dato il blocco AnyIO locale già verificato
nei task precedenti. Saltati solo i controlli Chrome opt-in ClinVar e PVS1;
warning preesistente `python_multipart`. Superati sintassi Python e
`git diff --check`. Nessun job Nextflow, servizio biologico live o suite estranea
al perimetro. Nessuna modifica ai test scientifici per attenuare regressioni.

Il confronto AST conferma `SCHEMA` e `SCHEMA_VERSION` ClinVar invariati, così
come tutte le funzioni top-level di pubblicazione/retention; cambia il metodo
di qualificazione batch del reader. `engine.py`, l'indexer e i criteri scientifici
non sono stati modificati da CACHE-05.1.

## 10. Artefatti, riproduzione e limiti rimasti

Artefatti in `/tmp/helper-cache051/`:

- `before-profile.json/.pstats`, `after-profile.json/.pstats`: fasi e cProfile.
- `before-1..3.json`, `after-1..3.json`: misure cronologiche iniziali.
- `control-before-1..3.json`, `control-after-1..3.json`: confronti appaiati che
  tengono conto delle modifiche parallele; usati per le percentuali principali.
- `final-before-outputs.json`, `final-after-outputs.json`: confronto esaustivo,
  pagine fredde/calde, serializzazione e digest.
- `before-source/`, `before-source.json`: implementazioni iniziali e fingerprint.

Esempio sullo stesso ambiente:

```bash
PYTHONPATH=helper_next/src python scripts/profile_clinvar_integration.py \
  --database /percorso/run/results/VARIANT_VIEWER/variants.sqlite \
  --mode measure --output /tmp/clinvar-after.json

PYTHONPATH=helper_next/src python scripts/profile_clinvar_integration.py \
  --database /percorso/run/results/VARIANT_VIEWER/variants.sqlite \
  --baseline-source /tmp/helper-cache051/before-source \
  --mode measure --output /tmp/clinvar-before.json
```

`--mode profile` aggiunge i contatori/cProfile; `--mode outputs` verifica tutti
i risultati e misura pagina 200/serializzazione. Il baseline-source deve essere
un albero di sorgenti fidato conservato prima della modifica, non un dataset.

Il costo residuo principale del primo accesso resta il checksum completo del
FASTA: circa sei secondi. Non è eliminato né spacciato per un risultato a cache
calda. Un eventuale intervento successivo potrebbe spostare una verifica reference
condivisa prima della consultazione, con durata delle risorse e revisione del
file esplicite; non è implementato qui. Non si propone una cache persistente di
checksum senza un contratto affidabile per le reference immutabili.

Restano lo scoring e i contesti del campione, che non si possono semplicemente
omettere prima della paginazione per ottenere un ordine corretto. Non è stata
introdotta una cache delle evidenze fra campioni o una nuova cache di punteggi.
Il criterio misurabile del task è soddisfatto sul caso globale e a reference
calda; il miglioramento del primo accesso assoluto è più limitato e dichiarato.
