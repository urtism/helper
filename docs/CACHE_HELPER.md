# Cache utilizzate da HELPER

**Stato del codice: 29 ottobre 2026**

Questa relazione descrive le cache implementate nel codice HELPER attivo e i
percorsi predefiniti per Linux. Un percorso predefinito non implica che il file
esista già: dipende dalle funzionalità effettivamente utilizzate, dall'ambiente
di esecuzione e dalle variabili di configurazione. Le cache delle pipeline e
quelle della GUI legacy sono indicate separatamente dalle cache della nuova
applicazione `helper_next`.

## Cache di dati pubblici e annotativi

| Cache | Percorso predefinito | Dati e modalità di gestione |
|---|---|---|
| Gene-fenotipo e indici pubblici | `~/.local/share/helper_variants/gene_phenotype.sqlite3` | SQLite con indici GenCC, Human Phenotype Ontology (HPO), Gene2Phenotype (G2P), ClinGen Dosage, Orphadata/codici di malattia e constraint gnomAD. Il pacchetto di fonti viene aggiornato tramite refresh esplicito o quando l'interfaccia rileva la cache assente/scaduta. L'età massima ordinaria è 7 giorni; i constraint gnomAD per gene hanno una soglia di 30 giorni. L'aggiornamento ricostruisce un database temporaneo e lo sostituisce a quello precedente solo dopo la scrittura completata. Variabile: `HELPER_GENE_PHENOTYPE_DB`. |
| ClinVar per allele esatto | `~/.local/share/helper_variants/clinvar_evidence.sqlite3` | SQLite, chiave basata su assembly e allele. I risultati positivi sono riutilizzati per 7 giorni, quelli senza risultato per 1 giorno. Il lookup viene eseguito su richiesta nella consultazione dei dettagli della variante; un refresh esplicito può saltare il record già presente. Variabile: `HELPER_CLINVAR_CACHE`. |
| Frequenze gnomAD per allele | `~/.local/share/helper_variants/gnomad_frequency.sqlite3` | SQLite con record per allele, assembly e release. Il codice associa GRCh37 a gnomAD 2.1.1 e GRCh38 a gnomAD 4.1. **Il client non applica un TTL**: un risultato in cache viene riutilizzato senza scadenza temporale; la release fa parte dell'identità del dato. Il recupero remoto avviene solo quando richiesto e in assenza di un risultato locale; il percorso ACMG può invece usare i soli dati già presenti. Variabile: `HELPER_GNOMAD_FREQUENCY_CACHE`; `HELPER_GNOMAD_OFFLINE=1` impedisce il recupero remoto del client. |
| Proiezione tra assembly (liftover) | `~/.local/share/helper_variants/assembly_projection.sqlite3` | SQLite per proiezioni di alleli esatti tra GRCh37 e GRCh38, via NCBI Variation Services. **Non è previsto TTL**; un risultato memorizzato resta disponibile fino a una modifica o rimozione esplicita del database. Variabili: `HELPER_LIFTOVER_CACHE` e `HELPER_LIFTOVER_OFFLINE=1`. |
| Catalogo PanelApp | `~/.local/share/helper_next/panelapp/catalog.json` | JSON del catalogo, con cache in memoria per 24 ore. La scadenza è riportata nello stato della cache; la sincronizzazione esplicita (`sync_panels`) recupera il catalogo aggiornato e lo scrive in modo atomico. Se il JSON esiste già, una normale lettura può continuare a usarlo anche quando è datato: il TTL non comporta da solo una sincronizzazione né la cancellazione del file. Variabile: `HELPER_PANELAPP_CACHE`. |
| Dettagli dei pannelli PanelApp | `~/.local/share/helper_next/panelapp/panels/` | File JSON separati per pannello e versione (oltre al dettaglio `latest`). Un dettaglio valido già presente viene riutilizzato senza controllo di età: non ha un TTL applicato dal client. Variabile: stessa `HELPER_PANELAPP_CACHE` del catalogo. |
| Trascritti e cataloghi Ensembl | `~/.cache/helper/transcripts/` | File JSON identificati da trascritto/gene, assembly e release Ensembl; contengono risposta originale, URL, data di acquisizione e digest per verificare integrità e identità. Non hanno TTL: la release esatta nella chiave impedisce di sostituire silenziosamente una release con un'altra. Il recupero è controllato da `HELPER_TRANSCRIPT_FETCH`; la cache è configurabile con `HELPER_TRANSCRIPT_CACHE` e la release con `HELPER_ENSEMBL_RELEASE`. Le nuove voci vengono scritte tramite file temporaneo e sostituzione atomica. |

Quando `XDG_DATA_HOME` è impostata, sostituisce `~/.local/share` per i percorsi
che seguono lo standard XDG. La cache Ensembl usa invece `~/.cache/helper` come
default e non deriva da `XDG_DATA_HOME`.

### Cache delle evidenze gene-malattia/meccanismo

La cache pubblica dei meccanismi è distinta dagli indici di origine descritti
sopra:

- **Percorso:** `~/.local/share/helper_next/mechanisms.sqlite3`.
- **Configurazione:** `HELPER_MECHANISM_DB`; il TTL per fonte può essere
  personalizzato con `HELPER_MECHANISM_TTL_JSON`.
- **Contenuto:** record originali delle fonti, stato per gene e fonte, risultati
  normalizzati gene-malattia, snapshot versionati, collegamenti alle prove,
  revisioni e progressi delle importazioni bulk. È uno SQLite transazionale;
  gli snapshot e i record di fonte sono conservati come storico e non sono una
  semplice cache volatile.
- **Scadenze predefinite:** 7 giorni per fonte, 30 giorni per gnomAD; esiti
  senza record 1 ora; errori 60 secondi. Il cambio di revisione dell'indice
  locale o delle versioni di normalizzazione/mappatura può rendere un risultato
  obsoleto prima del TTL.
- **Politiche di lettura:** `CACHE_ONLY` legge senza aggiornare; `REFRESH_IF_STALE`
  aggiorna dati assenti/scaduti; `FORCE_REFRESH` richiede un nuovo
  aggiornamento; `SNAPSHOT` riproduce uno snapshot identificato.
- **Rete:** l'aggiornamento delle fonti con indice completo rilegge l'indice
  locale già presente. Il recupero gnomAD mirato per gene è abilitato solo con
  `HELPER_MECHANISM_FETCH=1`; il normale uso non effettua probe o sincronizzazioni
  indiscriminate.

Il TTL della cache dei meccanismi non equivale a una data di aggiornamento
scientifico della fonte: HELPER conserva e segnala versioni, timestamp e stato
di freschezza senza considerarli una certificazione scientifica.

## Cache delle pipeline e dei tool

Queste cache non sono contenute nel database condiviso di `helper_next` e
possono essere collocate in percorsi configurati dall'utente:

- **Nextflow:** ogni esecuzione usa una directory `work/` nel run directory e
  la cache Nextflow `.nextflow/cache` nella directory di lancio. `-resume` e il
  riavvio da uno step dipendono dalla disponibilità della work directory e
  della cache Nextflow relative alla run. Non è una cache globale di dati
  clinici.
- **VEP:** il percorso è configurato nel catalogo dei tool o nella
  configurazione della pipeline e passato a VEP come `--dir_cache`. Alcune
  configurazioni versionate nel repository riportano `/home/jarvis/.vep`, ma
  questo è un valore di configurazione, non un default universale di HELPER.
  Anche la GUI legacy monta la directory configurata nel container VEP.
- **File di lavoro:** output intermedi, log e indici creati nella run risiedono
  nelle cartelle di esecuzione; non sono gestiti come cache condivise con TTL.

## Dati persistenti che non sono cache

Per evitare di confondere dati utente con cache rigenerabili:

| Archivio | Percorso predefinito | Contenuto |
|---|---|---|
| Storico analisi | `~/.local/share/helper_next/analysis_history.sqlite3` | Metadati durevoli delle run; non viene ricostruito dalle cartelle di lavoro. Variabile: `HELPER_ANALYSIS_HISTORY_DB`. |
| Contesti e revisioni ACMG | `~/.local/share/helper_next/acmg.sqlite3` | Workspace, interpretazioni e revisioni locali append-only. Variabile: `HELPER_ACMG_DB`. |
| VCF esterni | `~/.local/share/helper_next/external_vcf/` | Sorgenti VCF caricate localmente e relativi artefatti/indici. Non è una cache di dati pubblici; contiene input dell'utente. Variabile: `HELPER_EXTERNAL_VCF_DIR`. |

Anche gli archivi persistenti rispettano `XDG_DATA_HOME` se non è impostata una
variabile specifica.

## Scadenza, aggiornamento e pulizia

1. Lo stato di una cache e la sua freschezza vengono esposti dai rispettivi
   moduli/API quando disponibili. Uno stato `stale` indica che il dato non è più
   considerato aggiornato dal client; non significa che sia stato cancellato.
2. I TTL sono applicati in modo diverso: ClinVar e gene-fenotipo rifiutano i
   record scaduti e possono recuperarli di nuovo; gnomAD frequenze, liftover,
   dettagli PanelApp e trascritti non hanno una scadenza automatica implementata.
3. Non c'è un comando unico che svuoti tutte le cache, né una policy generale di
   limite dimensionale o garbage collection. I record storici/snapshot e i
   dettagli versionati possono quindi accumularsi.
4. Per liberare spazio, individuare prima il percorso effettivo tramite la
   configurazione/variabili d'ambiente; arrestare HELPER prima di intervenire
   sui database SQLite e fare una copia se si desidera conservare lo storico.
   Eliminare un database rimuove anche i dati che HELPER non può ricostruire
   offline. Non eliminare gli archivi ACMG, l'analisi storica o i VCF pensando
   che siano cache.

## Riferimenti nel codice

- Cache varianti: `helper_next/src/helper_variants/`
- Cache meccanismi e archivi ACMG: `helper_next/src/helper_next/core/`
- Uso della cache VEP in Nextflow: `workflows/nextflow/modules/annotation.nf`
- Configurazioni VEP incluse: `configs/tools_cfg/`

## Audit locale: inventario e decisioni

**Rilevazione: 29 ottobre 2026.** Sono stati letti i filesystem e interrogati i
database SQLite senza modificarli. Nell'ambiente della verifica `XDG_DATA_HOME` e
le variabili `HELPER_*` per sovrascrivere i percorsi erano tutte non impostate;
i percorsi osservati coincidono quindi con i default Linux. Il conteggio
SQLite è il numero di righe per tabella, non necessariamente il numero di
varianti o di prove scientifiche distinte.

### File effettivamente presenti

| Percorso | Dimensione | Record / contenuto rilevato | Lettori e scrittori principali |
|---|---:|---|---|
| `~/.local/share/helper_variants/gene_phenotype.sqlite3` | 88.043.520 B (84 MiB) | `assertions` 30.362; `hpo_features` 268.791; `g2p_records` 3.856; `clingen_dosage` 1.539; `gnomad_constraints` 8; `disease_codes` 15.318; `orpha_aliases` 25.405. Schema 4, aggiornato `2026-10-29T09:41:03Z`. | Scritto da `helper_variants.gene_phenotype`; letto da API `/knowledge/gene-phenotypes`, `acmg_context`, `acmg_sources`, catalogo fonti e import bulk. |
| `~/.local/share/helper_variants/clinvar_evidence.sqlite3` | 90.112 B (88 KiB) | 78 alleli: 42 risultati positivi e 36 `not_found`. Alla data di audit, 19 positivi e 5 negativi rientravano nei rispettivi TTL; i record scaduti erano ancora fisicamente nel DB ma non validi per il riuso. | Scritto da `helper_variants.clinvar`; letto dalla consultazione/dettaglio varianti e dalle funzioni di prioritizzazione; può essere aggiornato da lookup su richiesta. |
| `~/.local/share/helper_variants/gnomad_frequency.sqlite3` | 94.208 B (92 KiB) | 54 frequenze/risposte allele-specifiche, con release e timestamp. Nessun TTL implementato. | Scritto da `helper_variants.gnomad_frequency`; letto dal browser varianti e dal builder ACMG. Il builder può limitarsi alla lettura; il client può interrogare l'API se richiesto. |
| `~/.local/share/helper_variants/assembly_projection.sqlite3` | 77.824 B (76 KiB) | 62 proiezioni tra assembly. Nessun TTL implementato. | Scritto/letto da `helper_variants.liftover` per richieste di proiezione. |
| `~/.local/share/helper_variants/historical/catalog.sqlite3` | 12.288 B (12 KiB), più `-shm` da 32 KiB e `-wal` vuoto | Tabella `imports`: 0 righe. La ricerca nel codice attivo non ha trovato lettori o scrittori di questo percorso. | Candidato residuo/orfano, non classificato come cache attiva. |
| `~/.local/share/helper_next/mechanisms.sqlite3` | 1.021.059.072 B (circa 974 MiB) | 15.597 snapshot e 15.597 associazioni; 36.983 record fonte; 87.295 collegamenti snapshot-prova; 30.545 stati fonte; 185.699 record di mapping; 50.111 elementi bulk; 3 run bulk. Dei 30.545 stati, 10.661 `AVAILABLE` e 6.109 `NOT_SUPPORTED` non erano scaduti; 6.104 `CACHE_MISS` e 7.671 `NO_RECORDS` avevano superato il TTL negativo. | `MechanismEvidenceCache` e `MechanismStore`; API meccanismi, evidence coordinator ACMG e comando bulk. Conserva snapshot, provenienza e indici, non solo risultati temporanei. |
| `~/.local/share/helper_next/acmg.sqlite3` | 43.368.448 B (41 MiB) | 35 voci: 10 workspace, 14 interpretazioni, 4 valutazioni, 6 artefatti criteri, 1 confronto. | Letto/scritto da `acmg_store` e API ACMG. Archivio utente append-only. |
| `~/.local/share/helper_next/analysis_history.sqlite3` | 1.466.368 B (1,4 MiB) | 3 run archiviate: 2 completate e 1 fallita. | Letto/scritto da `analysis_history` e API run/import VCF. Archivio durevole. |
| `~/.local/share/helper_next/panelapp/catalog.json` | 339.361 B (circa 332 KiB) | 433 pannelli; ultimo sync `2026-10-06T08:27:01Z`, quindi oltre la soglia di 24 ore. Rimane leggibile da disco anche se obsoleto. | `helper_variants.panelapp`: lettura locale, sync API esplicito o richiesto quando manca il catalogo. |
| `~/.local/share/helper_next/panelapp/panels/` | 1.321 B in 2 file | Due dettagli `latest` (pannelli 101 e 1210); il codice non applica TTL ai dettagli già presenti. | `panelapp.panel_detail`; lettura da file e aggiornamento quando il dettaglio viene richiesto. |
| `~/.local/share/helper_next/backups/TASK27A3_prepopulation_20261027T100617Z.sqlite3` | 267.579.392 B (255 MiB) | Snapshot 20; associazioni 20; record fonte 37; mapping 109.802; elementi bulk 18.957; un run bulk. | Backup storico, non letto dalle normali API. |
| `~/.local/share/helper_next/backups/TASK27A3_source_pinned_20261027T111238Z.sqlite3` | 88.031.232 B (84 MiB) | Cache fonti precedente: 30.345 assertion, 268.791 HPO, 3.856 G2P, 1.537 ClinGen Dosage, 10 constraint gnomAD. | Backup storico, non letto dai moduli attivi. |
| `~/.vep/` | circa 177 GiB, 43.206 file | Circa 88 GiB `homo_sapiens_merged`, 62 GiB `Plugins`, 29 GiB `tmp`; bundle VEP osservato in `112_GRCh37`. I file non costituiscono un conteggio di varianti. | VEP legge `--dir_cache` e `--dir_plugins`; i cataloghi tool inclusi configurano `/home/jarvis/.vep`. `tmp` va trattata come area di lavoro potenzialmente usata da processi. |

Non risultavano presenti nei percorsi default `~/.cache/helper/transcripts/`,
`~/.local/share/helper_next/external_vcf/` o
`~/.local/share/helper_next/imported_variant_runs/`. L'assenza del primo indica
solo che non è stata trovata quella cache Ensembl: le annotazioni già presenti
nel VCF restano consultabili. Gli ultimi due sono depositi di input, non cache
pubbliche; l'assenza non dice nulla su VCF conservati altrove o nelle run.

Sono inoltre presenti directory di esecuzione Nextflow. Due run registrate
nello storico hanno le seguenti dimensioni:

- Nel `work/` del repository: 361 MiB e 68 file.
- In directory sotto `/media/jarvis/ANALISI/`: `work/` misura 22 GiB
  (3.003 file) e 21 GiB (2.545 file); le rispettive `.nextflow/cache` misurano
  circa 1,3 MiB (7 file) e 724 KiB (15 file).

Sono artefatti per ripresa/esecuzione, non cache globali rigenerabili da API.
Vanno conservati finché si vuole usare `-resume` o ripartire da uno step.

### Dati duplicati e relazione tra archivi

- I due database di gene-fenotipo hanno ampia sovrapposizione, ma non sono
  copie identiche. Il confronto riga per riga trova nel backup source-pinned
  30.334 assertion identiche su 30.345, 268.791 HPO su 268.791, 3.850 G2P su
  3.856 e 1.535 ClinGen Dosage su 1.537. Il backup ha 10 record di constraint
  diversi dagli 8 correnti. È quindi uno snapshot di fonte distinto, non una
  copia sostituibile senza perdita.
- Il backup meccanismi prepopulation contiene un sottoinsieme esatto dei dati
  ancora presenti nel database corrente: tutti i suoi 20 snapshot, 20
  associazioni, 18.957 elementi bulk, 109.802 record mapping e 37 record fonte
  corrispondono a righe identiche nel database corrente. I suoi 45 stati fonte
  non corrispondono però a righe identiche correnti: rappresentano uno stato
  temporale diverso.
- Il database meccanismi conserva inoltre rappresentazioni normalizzate,
  snapshot immutabili e riferimenti ai record delle fonti. Questi dati si
  sovrappongono semanticamente agli indici di origine, ma aggiungono
  provenienza, mapping, versioni e storia delle elaborazioni; non sono
  deduplicabili come semplici copie di file.
- Il VCF sorgente, l'indice SQLite della run, le annotazioni del VCF e le
  evidenze ACMG archiviate possono ripetere informazioni sullo stesso allele,
  ma hanno ruoli diversi. L'indice è rigenerabile dal VCF e dagli strumenti
  appropriati; workspace, decisioni e snapshot ACMG non si ricostruiscono dal
  solo VCF.

### Recuperabilità e conservazione

| Categoria | Esempi locali | Cosa si può ricostruire | Decisione di conservazione |
|---|---|---|---|
| Fonti pubbliche correnti | ClinVar, gnomAD, PanelApp, liftover, dati Ensembl | In generale recuperabili da API, se rete e servizio sono disponibili; il dato futuro può differire dalla release o risposta storica. ClinVar e record gnomAD sono identificati per allele/release; Ensembl richiede release/assembly qualificati. | Cache eliminabili solo se non serve l'uso offline e si accetta di rifare il recupero; conservare i metadati/snapshot se serve riproducibilità. |
| Indici di fonti pubbliche | `gene_phenotype.sqlite3` | Ricostruibili scaricando nuovamente le fonti pubbliche e ripassando il builder; non è garantito ricreare gli stessi byte o lo stesso snapshot di fonte. | Conservare almeno una copia della versione usata nelle interpretazioni. Il backup source-pinned non è identico al DB corrente. |
| Elaborazioni pubbliche versionate | `mechanisms.sqlite3` | Alcune matrici possono essere ricalcolate dagli indici; mapping, versioni, errori/stati passati, riferimenti e decisioni di curazione storiche non sono ricostruiti esattamente da una nuova sincronizzazione. | **Conservare** database corrente e almeno un backup verificato. Non cancellare snapshot o tabelle bulk per ridurre lo spazio senza una migrazione progettata. |
| Input e indici di campione | VCF, database per run, directory `work/` | L'indice varianti è rigenerabile se sopravvivono VCF, annotazioni e configurazioni; i risultati temporanei di pipeline possono richiedere una nuova esecuzione. | **Conservare i VCF sorgente e gli output richiesti**. `work/` e `.nextflow/cache` si possono rimuovere soltanto per run concluse quando non serve più riprendere la pipeline. |
| Valutazioni e storia utente | `acmg.sqlite3`, `analysis_history.sqlite3` | Non rigenerabili dal solo VCF: contengono selezioni, interpretazioni, revisioni e metadati delle run. | **Conservare** o migrare esplicitamente con verifica dei record. |
| Tool e risorse annotative | `~/.vep/` | I bundle VEP sono ridownloadabili, ma voluminosi; i plugin possono includere versioni/configurazioni o modifiche locali. | Conservare le release e i plugin effettivamente configurati. Rimuovere versioni inutilizzate solo dopo aver verificato tutte le pipeline. Non cancellare `tmp` mentre VEP è in esecuzione. |

**Eliminabili solo dopo migrazione e verifica:** il backup meccanismi
prepopulation è ridondante per gli snapshot e i record elencati sopra perché
sono stati confrontati con righe identiche nell'archivio corrente. Può essere
rimosso solo dopo aver verificato un ulteriore backup indipendente e aver
accettato la perdita dello stato fonte storico non identico. Il file
`historical/catalog.sqlite3` è un candidato separato: ha zero import e nessun
uso trovato nel codice attivo; prima di rimuoverlo va escluso che una vecchia
versione o un processo esterno lo usi. Il backup source-pinned non è
intercambiabile con il database aggiornato e va conservato finché non è stata
formalmente accettata la perdita della sua versione storica.

Non è stata eliminata né modificata alcuna cache o archivio. La presente
verifica non autorizza la rimozione automatica: i percorsi possono essere usati
da processi esterni o da configurazioni non versionate.

### Comportamento quando manca una cache

| Operazione | Comportamento del codice | Verifica e limite |
|---|---|---|
| Import/lettura VCF e consultazione campione | Le varianti, chiamate e annotazioni vengono lette dall'indice della specifica run; ClinVar e gnomAD sono enrichment opzionali. Cache pubbliche assenti non cancellano né sostituiscono il contenuto del campione. | Test di query campione, upload VCF e assenza della cache del contesto superati. Senza VCF/indice run, invece, il campione non è consultabile. |
| Contesto ACMG automatico | Senza database gene-malattia, la risposta espone `MISSING_DISEASE_CONTEXT` e non inventa un'associazione. È possibile fornire un contesto manuale con identificativi stabili espliciti. | Test specifico cache assente superato. Se il contesto è richiesto dal caso d'uso e non è fornito, non si può proseguire con quel contesto automatico. |
| Evidenza popolazione ACMG | Se manca la cache gnomAD o l'allele esatto, l'evidenza viene dichiarata mancante; il contratto può restare incompleto anziché inventare frequenze o contatori. | Test workbench e PVS1 incompleto superati. Il calcolo non equivale a una valutazione completa quando mancano evidenze richieste. |
| Trascritto/PVS1 | Senza cache Ensembl, il provider restituisce il dato mancante; l'evidence builder può validare un risultato PVS1 `INCOMPLETE` senza effetti trascrizionali. | Test `test_missing_transcript_still_validates_incomplete_pvs1` superato. Non è una verifica biologica completa del trascritto. |
| Meccanismi gene-malattia | Le policy `CACHE_ONLY`/refresh e gli stati `CACHE_MISS`, `UNREACHABLE` o `ERROR` separano assenza e guasto. Gli snapshot già validi vengono mantenuti se una fonte fallisce; i dati mancanti sono riportati, non trasformati in una conclusione negativa. | Test di snapshot offline e fonte non disponibile superati. |
| Annotazione VEP in pipeline | Se il workflow richiede VEP con `--cache --offline`, una cache VEP mancante può interrompere proprio lo step di annotazione. La consultazione del VCF già annotato resta distinta. | Al momento della verifica `/home/jarvis/.vep` è presente e i cataloghi inclusi puntano a quel percorso. Non è stato eseguito un workflow end-to-end con VEP rimosso. |
| Resume/riavvio Nextflow | Senza `work/` e `.nextflow/cache` della run, il resume o il riavvio da uno step non è disponibile; una nuova run da input/configurazione validi è un flusso distinto. | Le due run archiviate osservate hanno entrambe i propri artefatti di resume. |

**Esito:** l'assenza delle cache di arricchimento non interrompe in generale
l'importazione/consultazione del VCF o del campione. ACMG può proseguire in
modalità incompleta se si forniscono gli input obbligatori, ma l'assenza di
contesto automatico impedisce quella selezione e un contesto manuale può essere
necessario. Restano requisiti indipendenti le dipendenze esplicite: ACMG Engine,
reference FASTA quando richiesta per normalizzazione/evidenza strutturata,
VCF/indice della run e, per l'annotazione offline, la cache VEP configurata.

### Verifiche eseguite e limite

- Suite mirata su contesto ACMG, workbench, PVS1, meccanismi, query campioni e
  VCF: **134 passed, 1 skipped, 1 failed**. Il test fallito è
  `test_opt_in_coordinator_extension_validated_by_real_engine_pvs1_unchanged`
  in `test_acmg_mechanisms.py:402`, per un'asserzione sulla presenza di
  `mechanism_evidence`; non è stato modificato codice per correggerlo.
- Rilancio mirato dei casi cache mancante, trascritto mancante, workbench,
  lettura campione, campione inesistente e upload VCF: **40 passed**.
- Un warning di deprecazione `python_multipart` è stato emesso dalla
  dipendenza Starlette. Non è stato eseguito un workflow completo con VEP o
  Nextflow deliberatamente privi delle rispettive cache.
