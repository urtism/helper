# CACHE-05 — Integrazione ClinVar Local

Data: **30 ottobre 2026**. Lista, prioritizzazione e dettaglio utilizzano lo
snapshot SQLite ClinVar locale. Nessuna modifica a formula/pesi/soglie della
priority, criteri ACMG, PVS1, contratto ga2, schema ClinVar o retention
CURRENT/BACKUP. CACHE-06 non avviato.

## 1. Audit dei consumer prima delle modifiche

Letti CACHE-01, CACHE-02/02.1, CACHE-03 e CACHE-04/04.1, le istruzioni del
repository e i moduli indicati nel task. Il working tree conteneva già modifiche
di cleanup e dei task precedenti: sono state conservate.

| Consumer | Comportamento precedente | Integrazione CACHE-05 |
|---|---|---|
| `query.list_variants` | Batch `clinvar.cached_evidence` dal DB delle interrogazioni API | Batch del reader locale e adapter, prima dello scoring |
| `query._compact_variant` | `score_variant` seguito da `apply_clinvar_evidence` | Stesso motore; cambia soltanto l'evidenza in ingresso e si aggiungono i metadati snapshot/matching |
| `query.variant_detail` | Annotazioni ClinVar originali VCF | Evidenza locale più `vcf_clinvar_evidence` distinto |
| `api.variants.sample_variant_detail` | `clinvar.lookup_variant`, con refresh remoto esplicito disponibile | Un reader locale condiviso da dettaglio e calcolo della priority; parametro refresh compatibile, senza rete |
| `source_registry.catalog` | Descriveva cache E-utilities/TTL come fonte operativa | Mostra ClinVar Local, snapshot e data effettiva di installazione/importazione |
| `variant-browser.js` | Colonna Clinical dal VCF, disclosure ClinVar alimentata dal provider remoto | Colonne distinte e disclosure esistente adattata alla fonte locale e alle SCV |

Il motore è puro: non legge database né esegue HTTP. La cache persistente delle
interrogazioni API non era una release globale. Il provider legacy rimane
disponibile per uso esplicito e non è stato modificato da CACHE-05.

La lista già calcolava tutti i candidati quando l'ordinamento o i filtri
dipendevano dalla priority. Conservava soltanto gli ID ordinati in una LRU di
processo, massimo quattro voci; i punteggi non erano persistiti nel run store.
La chiave includeva fingerprint dell'indice, delle fonti e del DB API, ruleset,
filtri, campione e un bucket temporale di un minuto. Le pagine successive
rileggevano e valutavano soltanto gli ID della pagina nella cache dell'ordine.
Questo comportamento è stato riutilizzato.

Assembly: l'indexer deriva il build dai metadati/configurazione della run e lo
conserva su run e varianti. Il lookup usa `variants.reference_build` per ciascun
allele, senza dedurlo da gene/rsID. La configurazione reference della run viene
passata al reader dalle API. L'indexer separa gli ALT, esegue trimming e usa il
FASTA configurato per REF/left alignment; gli indici storici senza FASTA non
garantiscono indel normalizzate. Il reader gestisce questo limite senza creare
un nuovo normalizzatore.

## 2. File interessati

Sotto `helper_next/src/`:

- `helper_variants/clinvar_adapter.py`: adapter locale e durata del reader.
- `helper_variants/query.py`: batch, metadati priority, invalidazione e dettaglio.
- `helper_variants/source_registry.py`: descrizione della fonte realmente usata.
- `helper_variants/__init__.py`: documentazione della dipendenza ga2 esistente.
- `helper_next/api/variants.py`: reader condiviso, paginazione SCV e refresh.
- `helper_variants/web/static/variant-browser.js`: fonte locale/VCF, SCV e cache UI.

Test: `test_clinvar_integration.py`, `test_clinvar_browser.py`,
`test_variant_query.py`, `test_variants_api.py`, `test_variant_viewer.py`,
`test_source_registry.py`, `conftest.py` e una riga di isolamento in
`test_clinvar_local.py`. Aggiunti questo report e
`scripts/benchmark_clinvar_integration.py`.

`engine.py`, `biological_identity.py`, `clinvar_local.py`, il provider legacy,
i moduli ACMG/PVS1 e i dati clinici non sono stati modificati da questo task.

## 3. Adapter e mapping

`LocalEvidence` è un context manager specifico: apre `ClinVarLocal`, legge il
manifest e chiude connessione/lease al termine, anche su eccezione. Rispetta
`HELPER_CLINVAR_LOCAL_DB` e il default XDG già implementato dal reader.
Non introduce cache persistenti, tabelle, orchestratori o fallback.

`batch` deduplica le tuple di input e richiama `lookup_batch`; quest'ultimo
deduplica anche gli alias dopo qualificazione genomica. Per i Variation ID
univoci legge varianti e classificazioni con SELECT batch da 500 ID. Il lookup
genomico mantiene i blocchi da 150 chiavi del reader. Non viene interrogata la
tabella submissions nella lista: 1.100 input uguali richiedono tre SELECT;
201 alleli distinti richiedono quattro SELECT nelle fixture.

| Campo HELPER | Fonte locale / semantica |
|---|---|
| `variation_id`, `identifiers`, `source_url` | Variation ID e URL ufficiale, soltanto con FOUND univoco |
| `allele_id` | Allele ID nullable della variante |
| `classifications`, `review_statuses`, `last_evaluated` | Aggregato `scope=variant, kind=germline`; stelle nullable conservate |
| `has_conflict`, `conflicts` | Indicazione di conflitto dell'aggregato germline |
| `conditions`, `condition_ids`, `rcv_accessions` | Riferimenti condizione/RCV; nessuna classificazione RCV inventata |
| `unaligned_condition_source` | Stringhe originali non associabili univocamente agli RCV, conservate senza join arbitrario |
| `oncogenicity`, `somatic_clinical_impact` e review separati | Aggregati dei rispettivi tipi; non alimentano il contributo germline |
| `submitter_count` | `NumberSubmitters` upstream, compreso zero |
| `submission_count` | Conteggio locale SCV distinte, soltanto nel dettaglio |
| `submission_interpretation_count` | Numero delle righe interpretative, distinto dalle SCV distinte |
| `submissions` | Pagina SCV con submitter, classificazione, review/stelle, condizione, data e URL |
| `contributing_scvs` | Identificativi dichiarati per l'aggregato germline in VS |
| `contributes_to_germline_aggregate` sulle SCV | Corrispondenza con la lista VS; null quando la lista non è disponibile |
| `snapshot_id`, `provenance` | Identificativo composito e manifest conservato dal reader |
| `matching_status`, `match_reason`, `match_method`, `allele_identity`, `matches` | Esito e qualificazione del lookup esistente, candidati ambigui inclusi |

Non si inventano VCV/versioni, date scientifiche di aggiornamento o aggregati
disease-specific. Le SCV non votano per costruire un aggregato. L'adapter lascia
vuoto `classification_breakdown`: le interpretazioni individuali sono esposte
separatamente, con gli identificativi contribuenti quando presenti. Il punteggio
usa sempre l'aggregato disponibile, indipendentemente dalla pagina SCV caricata.
Questo evita di cambiare la priority aprendo o paginando il dettaglio.

## 4. Stati e gestione degli errori

`status` conserva available/not_found/unavailable; `matching_status` distingue
FOUND, NOT_FOUND, UNRESOLVED, AMBIGUOUS ed ERROR. `availability` è AVAILABLE per
FOUND, altrimenti conserva lo stato specifico. `freshness=NOT_APPLICABLE` indica
uno snapshot installato, senza TTL API o falsa certificazione di freschezza live.

`clinical_status` distingue CLASSIFIED, NO_GERMLINE_CLASSIFICATION, NOT_FOUND e
NOT_EVALUABLE. NOT_FOUND non viene interpretato come benigno; UNRESOLVED non
prova assenza. AMBIGUOUS non seleziona un candidato e non fornisce classificazioni.

Database mancante, corrotto o incompatibile produce ERROR, messaggio tecnico
nel log e `last_error` nel payload. Varianti e annotazioni VCF restano accessibili;
il contributo ClinVar è privo di classificazione/evaluated=false secondo il
motore esistente. Non vengono letti dati della vecchia cache per compensare.
Un errore della pagina SCV è esposto in `submissions_error`, senza cancellare
l'aggregato già letto né cambiare il punteggio.

SNV GRCh37/38, contig qualificati e ga2 riusano il reader. Le indel senza FASTA
possono fare match solo sulla rappresentazione NCBI VCF esatta; una forma diversa
resta UNRESOLVED. Con FASTA si riusano verifica REF e left alignment esistenti.
Nessun liftover implicito, matching per gene/rsID o equivalenza fra assembly.
Una query con ALT multiple non viene assegnata ad un allele arbitrario; l'indice
fornisce i singoli ALT separati.

## 5. Lista, priority e release

L'insieme pertinente viene letto dall'indice, arricchito in batch e valutato
prima di filtro/ordinamento per priority e paginazione. Le altre modalità SQL
di ordinamento e i filtri sulle annotazioni originali sono conservati. Il filtro
Clinical e l'ordinamento Clinical restano riferiti al VCF, non al dataset locale;
la nuova colonna ClinVar Local mostra l'evidenza effettivamente usata dalla priority.

La LRU degli ID ordinati usa ora `snapshot_id` al posto di fingerprint/TTL del
DB API. Conserva le altre dipendenze e include il contesto reference della run
e il file di configurazione reference. Uno snapshot diverso non riusa l'ordine
precedente; il successivo accesso ricalcola i candidati e riordina la lista.
Con snapshot invariato le pagine riusano l'ordine già calcolato. In ERROR
l'ordine non viene memorizzato né recuperato dalla LRU.

Ogni priority della lista e del dettaglio espone `clinvar_snapshot_id` e
`clinvar_matching_status`. `apply_clinvar_evidence` sostituisce il componente
ClinVar, senza sommarlo una seconda volta; non cambiano regole, soglie o pesi.
I test confrontano l'adapter con `_summary_evidence` del provider legacy per
classificazioni/review equivalenti: punteggi e componenti identici, compresi
benigno, VUS, conflitti, valori sconosciuti e germline mancante.

Differenze rispetto a payload remoti con breakdown dipendono dalla disponibilità
dei dati: gli export non autorizzano a ricostruire gli aggregati tramite tutte
le SCV. Si conserva l'aggregato ufficiale disponibile, senza cambiare la formula
per compensare differenze di contenuto/release.

Il reader è fissato all'inizio della richiesta. Anche se CURRENT cambia durante
il batch, l'operazione termina sullo snapshot iniziale. Il dettaglio API condivide
lo stesso reader con il calcolo della priority. Nessuna connessione entra nella
LRU o rimane aperta per la sessione utente. I test verificano chiusura SQL,
rilascio dei lock, aggiornamenti mentre un reader usa il precedente CURRENT e
successiva possibilità di pubblicare una terza release rispettando CURRENT/BACKUP.

## 6. Dettaglio e frontend

Si riusa la disclosure ClinVar esistente, ora intitolata
**ClinVar Local — installed snapshot**: fonte, snapshot, matching, errori,
aggregato, review/stelle, valutazione, submitter, condizioni e collegamenti
Variation/RCV. Le stelle sconosciute sono mostrate come non riportate.
Le annotazioni originali rimangono in una disclosure interna esplicita
**Original VCF ClinVar annotation**, oltre alle annotazioni originali dell'indice.

Le submission sono caricate solo nel percorso di dettaglio, tramite paginazione
del reader. L'endpoint esistente accetta `submissions_limit` (1–10.000,
default 100) e `submissions_offset`; restituisce `submissions_next_offset`.
Il controllo More submissions accoda la pagina, verifica variante e snapshot,
e ricarica il dettaglio se la release cambia. Nessun nuovo endpoint o XML.
Gli URL SCV sono ricerche ufficiali NCBI; gli RCV non ricevono aggregati inventati.

`refresh_clinvar=true` resta accettato per compatibilità ma restituisce
`clinvar_refresh.status=NOT_APPLICABLE` e indica l'aggiornamento del dataset
locale. Non può invocare E-utilities, neppure se la vecchia cache è disponibile.
Non viene aggiunto un pulsante di aggiornamento del database.

Le richieste lista/dettaglio usano no-store. Il frontend confronta snapshot e
stato della fonte prima di accodare pagine; al cambio scarta righe/ordine e
dettaglio precedenti e riparte dalla prima pagina. La riapertura di un campione
o tab richiede nuovamente la lista. Una schermata già aperta non viene aggiornata
in background: l'invalidazione è alla successiva consultazione, come richiesto.

**Frontend reale non verificato con browser.** Il tentativo di avviare Chrome
headless fuori sandbox non è stato autorizzato. Sono passati i test statici del
viewer, la sintassi JavaScript e un test Node che esegue il vero `loadPage`,
simula A→B durante la paginazione e verifica scarto dell'ordine A e ripartenza
senza cursor. Rimane un test Chrome opt-in con fixture API offline.

La vista regionale JBrowse/IGV preesistente rimane una consultazione esplicita
separata con traccia remota NCBI, non una fonte per lista, dettaglio o scoring.
Non è stata aperta durante le verifiche e non è convertita in questo task.

## 7. Verifiche automatiche

Regressione finale: **554 passed, 2 skipped, 185 subtests passed**, 30,52 s.
Una verifica aggiuntiva dell'allele condiviso fra campioni/run porta il totale
dei test distinti superati a **555**. Report XML:
`/tmp/helper-cache05/final-regression.xml` e `shared-allele.xml`.

La suite include indicizzazione/store, query/API/viewer, provider legacy,
ClinVar locale e retention, nuovo adapter, source registry, gnomAD,
prioritizzazione, ga2, contesto ACMG, meccanismi e PVS1/calcolatore molecolare.
Le nuove fixture operative vietano rete e accesso alla vecchia cache batch.
Le fixture verificano anche integrità della cache API, equivalenza dello score,
assenza di doppio conteggio, ALT distinti e punteggi indipendenti dalla pagina SCV.

Saltati: Chrome ClinVar opt-in e il controllo Chrome opt-in PVS1 già presente.
Nessuna regressione ACMG/PVS1. Warning preesistente `python_multipart`.
Il tentativo API iniziale in sandbox è stato interrotto perché bloccato nel
trasporto locale AnyIO; la suite API è poi passata fuori sandbox.

Aggiornati i test che richiedevano esplicitamente E-utilities o l'invalidazione
alla scrittura della cache API: ora verificano fixture SQLite reali e cambio di
snapshot. Il test architetturale del viewer vietava già l'import ga2 introdotto
in CACHE-04; ora controlla tramite AST che **l'unica** dipendenza verso helper_next
sia quell'import preesistente in `clinvar_local.py`, senza autorizzarne altri.
Non sono state attenuate le verifiche dei motori scientifici.

Sintassi Python dei moduli interessati, sintassi ES module del viewer e
`git diff --check` superati. Non eseguita la suite integrale estranea al perimetro,
alcun servizio biologico live o job Nextflow.

## 8. Benchmark non distruttivo su run reale

Run indicizzata `20261015_Run_723_CancerHS2`: **10 campioni**, assembly hg19,
qualificato dal reader come GRCh37. Lo script copia l'indice da 174.006.272 byte
in una directory temporanea, rifiuta un WAL attivo e verifica dimensione, mtime
e SHA-256 della sorgente prima/dopo. Le query operative lavorano soltanto sulla
copia. ClinVar viene aperto read-only sullo snapshot installato:

`composite-sha256:da8e890d1ad7950bb61fa74218dcb86a82629d6c3ddaba76d0e8af08446038a7`.

| Misura | Risultato |
|---|---:|
| Varianti distinte della run | 2.609 |
| FOUND | 1.379 |
| NOT_FOUND | 1.222 |
| UNRESOLVED | 8 |
| AMBIGUOUS / ERROR | 0 / 0 |
| Classificazione germline disponibile | 1.374 |
| Acquisizione batch per gli alleli distinti della run | 7,918 s |
| Richieste lista con calcolo globale dei 10 campioni, prima di limit=1 | 7,471 s |
| Acquisizione locale interna alle liste dei campioni | 4,370 s |
| Funzioni di scoring, incluso contributo ClinVar | 1,338 s |
| Chiamate HTTP nel percorso misurato | **0** |
| Fingerprint dell'indice clinico sorgente invariato | **sì** |

Tempi di una singola esecuzione sul sistema locale, con cache filesystem che
si scalda durante la prova: non sono una stima di latenza NCBI o un benchmark
scientifico universale. Il tempo lista include SQL/contesti/ordinamento oltre
allo scoring; il conteggio degli stati riguarda varianti distinte, non call.

Artefatto: `/tmp/helper-cache05/real-benchmark.json`. Riproduzione:

```bash
PYTHONPATH=helper_next/src python scripts/benchmark_clinvar_integration.py \
  --database /percorso/run/results/VARIANT_VIEWER/variants.sqlite \
  --output /tmp/helper-cache05-benchmark.json
```

Il trasporto ClinVar e i socket sono vietati durante la misura. Il vecchio
scenario di cinque aperture con refresh forzato costava 15 HTTP nella fixture
documentata da CACHE-03; il nuovo test esegue cinque richieste con lo stesso
parametro e verifica zero HTTP. Per la run reale non si attribuisce un numero
ipotetico di richieste evitate: il sistema precedente poteva avere cache hit,
quindi il dato misurato e garantito è zero richieste effettive.

## 9. Limiti e aggiornamento successivo

- Nessuna classificazione aggregata RCV, VCV/versione, record_updated o data
  scientifica di aggiornamento inventata. Restano i limiti dei due export e del
  matching documentati da CACHE-04.
- Le SCV individuali possono avere contenuti/release diversi dall'aggregato e
  non vengono automaticamente considerate tutte contribuenti. Nessun voto locale.
- La colonna ClinVar Local è informativa; ordinamento/filtro della priority usano
  il dataset locale, mentre Clinical (VCF) conserva i filtri/sort dell'indice.
- La UI non rileva nuove installazioni senza una successiva richiesta utente;
  non ci sono polling, scheduler o aggiornamenti del database.
- Il futuro aggiornamento deve continuare a pubblicare snapshot validati tramite
  il meccanismo CURRENT/BACKUP esistente. Un nuovo `snapshot_id` invalida già
  l'ordine alla prima lettura. Non serve una migrazione della cache priority.
- I reader operativi devono restare circoscritti alle richieste. I test provano
  che il loro rilascio permette la retention; nessuna modifica alla policy dei
  due database e nessuna conservazione storica aggiuntiva oltre BACKUP.

Nessun download, reimportazione del dataset installato, aggiornamento automatico,
schema nuovo o modifica a dati clinici. Le importazioni dei test riguardano
esclusivamente piccoli dataset sintetici nelle directory temporanee pytest.
