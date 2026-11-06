# HELPER — Structural cleanup e rimozione del valutatore esterno

Data: **29 ottobre 2026**. Pulizia conservativa del solo repository HELPER.
Le regole scientifiche, i dati e gli schemi delle cache non sono stati modificati.

## 1. Stato iniziale e protezione

- Branch iniziale: `clean-up`.
- Commit iniziale: `d222113ce6513f90ce78bb918ccf96718f8b89c8`.
- `git status --short --untracked-files=all`: nessuna modifica e nessun file
  non tracciato non ignorato. Il lavoro ACMG/PVS1 recente era già nel commit.
- Branch di ripristino: `archive/helper-before-structural-cleanup-20261029`,
  sul commit iniziale. Non è stato cambiato il branch di lavoro.
- Snapshot aggiuntivo: `/tmp/helper-before-structural-cleanup-20261029.tar.gz`;
  manifest SHA-256: `/tmp/helper-before-structural-cleanup-20261029.sha256.json`.
  Include i 411 file tracciati/non ignorati presenti, con supporto ai file non
  tracciati. I file runtime ignorati non sono inclusi nello snapshot.
- Non sono stati modificati o cancellati database, cache, campioni, VCF o dati
  diagnostici esistenti. Le fixture pubbliche e sintetiche sono conservate.
  I test usano directory temporanee e database isolati.
- Nessun `reset --hard`, `clean`, migrazione, commit o intervento sul repository
  esterno. La prima creazione del branch era impedita dalla sandbox; è stata
  completata con l'autorizzazione alla scrittura dei riferimenti Git.

Per recuperare un file precedente senza cambiare il checkout:
`git show archive/helper-before-structural-cleanup-20261029:percorso/del/file`.
Lo snapshot in `/tmp` è una protezione aggiuntiva temporanea; il branch è il
riferimento durevole nel repository locale.

## 2. Legacy audit

La ricerca ha coperto sorgenti tracciati e file nascosti non runtime,
configurazioni, script, test e documenti. Sono stati cercati nomi del progetto,
classi client, contratti, variabili d'ambiente, URL, avvio processi, import e
riferimenti frontend. Non sono stati analizzati database o contenuti runtime.

| Elementi iniziali | Categoria | Esito |
|---|---|---|
| `core/acmg_client.py:ACMGClient`, `core/acmg_task22.py:Task22Client` | LEGACY | Rimossi HTTP, retry, discovery OpenAPI e validazione remota |
| `core/acmg_service.py`, lifecycle in `api/app.py` | LEGACY | Rimossi discovery dell'eseguibile e avvio/arresto del servizio |
| `configs/acmg_engine.json` | LEGACY | Rimossi profili risolti nel repository adiacente |
| `api/acmg.py`, `api/acmg_task22.py` | LEGACY | Rimosse route Workbench, classificazione, confronto, preflight e replay |
| `core/acmg_evidence.py`, `acmg_classification.py`, `acmg_task22.py` | LEGACY | Rimossi Coordinator, Evidence Assembler, Evidence Contract e conversioni packet/contract |
| `core/acmg_workbench.py`, `acmg_population.py`, `acmg_store.py` | LEGACY | Rimossi preparazione dei packet e archivio applicativo del vecchio Workbench; database storici non toccati |
| Workbench/Task22 JS, renderer PVS1 e schema editor legacy | LEGACY | Rimossi; eliminato il pulsante che apriva il servizio esterno |
| `acmg_client.digest()` | SHARED | Spostata identica in `core/acmg_digest.py`; nessun adapter |
| `core/acmg_pvs1.py` | SHARED | Conservata identica `nonsense()`, usata da `pvs1/molecular.py`; rimossi serializer e transformer del vecchio contratto |
| `core/acmg_reference.py` | SHARED | Conservato: usato anche dall'importazione VCF esterna |
| `pvs1/`, `api/acmg_calculator.py`, `core/acmg_molecular_impact.py`, `acmg-calculator.js` | LOCAL | Conservati integralmente |
| `acmg_context`, `acmg_transcripts`, `acmg_sources`, moduli mechanism/ontology e relativi CLI | LOCAL/SHARED | Conservati, import del checksum aggiornati |
| `helper_variants`, `helper_prioritization`, fonti biologiche e pannelli ACMG SF | SHARED | Conservati; non sono il vecchio valutatore |

Il vecchio URL predefinito era `http://127.0.0.1:8000`. Sono rimossi i consumer
di `ACMG_ENGINE_URL`, `ACMG_ENGINE_TIMEOUT`, `ACMG_ENGINE_TOKEN`,
`HELPER_ACMG_AUTOSTART`, `HELPER_ACMG_COMMAND`, `HELPER_ACMG_ENGINE_DIR`,
`HELPER_ACMG_CONFIG`, `ACMG_PROFILES_DIR`, `ACMG_HOST`, `ACMG_PORT`,
`ACMG_ENABLE_RESEARCH_INTERPRETATION` e `ACMG_CRITERIA_PROTOCOL_VERSION`.
Nessuna configurazione Docker, `.env` o script di avvio operativo rimasto
richiede il servizio. `HELPER_ACMG_REFERENCE_CONFIG` è invece conservata:
configura riferimenti FASTA usati anche nell'importazione VCF.

Le route `/api/acmg/discovery`, `/api/acmg/task22/discovery`,
`/api/acmg/workspaces/...` e `/api/acmg/results/...` non sono più registrate.
Le API `/api/acmg/mechanisms/...` rimangono locali e disponibili.
Nessun fallback remoto o risultato sostitutivo è stato introdotto.

## 3. Interventi e file

Percorsi abbreviati: `core/` e `api/` sotto
`helper_next/src/helper_next/`; statici sotto
`helper_next/src/helper_variants/web/static/`.

File eliminati:

- Core: `acmg_client.py`, `acmg_service.py`, `acmg_classification.py`,
  `acmg_evidence.py`, `acmg_task22.py`, `acmg_workbench.py`,
  `acmg_population.py`, `acmg_store.py`.
- API: `acmg.py`, `acmg_task22.py`.
- Frontend: `acmg-workbench.js`, `acmg-workbench.css`, `acmg-task22.js`,
  `acmg-schema-field.js`, `acmg-pvs1.js`.
- Configurazione: `configs/acmg_engine.json`.
- Test sotto `helper_next/tests/`: `test_acmg_service.py`,
  `test_acmg_service_integration.py`, `test_acmg_classification.py`,
  `test_acmg_evidence.py`, `test_acmg_task22.py`, `test_acmg_workbench.py`,
  `test_acmg_browser.py`, `test_acmg_task22_browser.py`,
  `test_acmg_task28_browser.py`.
- Documenti sotto `docs/`: `TASK22_WORKBENCH.md`, `TASK22_STATUS.md`,
  `TASK22_ACMG_CONTRACT.md`, `TASK23_ACMG_INTEGRATION.md`,
  `TASK23_DATA_EVIDENCE_AUDIT.md`, `TASK23_DATA_EVIDENCE_AUDIT.json`,
  `TASK23_PVS1_ADAPTER_DESIGN.md`, `TASK24_EVIDENCE_ARCHITECTURE.md`.

File modificati o aggiunti:

- `api/app.py`, `variant-browser.js`: rimozione lifecycle/router e accesso UI legacy.
- Nuovo `core/acmg_digest.py`: la sola funzione checksum condivisa già esistente.
  Import aggiornati in context, transcript, mechanism assessment/normalizer/store,
  resolver/bulk, ontology, script di audit/validazione e test molecolari.
- `core/acmg_pvs1.py`: solo helper nonsense locale; `acmg_sources.py` e
  `acmg_mechanism_models.py`: descrizioni aggiornate.
  In `acmg_mechanism_assessment.py` rimossi anche serializer e scope helper
  usati esclusivamente dal contratto remoto; `assess()` e i dati locali restano
  invariati.
- `helper_next/pyproject.toml`: rimossa `jsonschema`, usata esclusivamente dal
  validatore del contratto remoto. Nessuna nuova dipendenza.
- Test context adattati al dettaglio variante locale; nei test mechanism e
  assessment rimossi solo i casi del contratto remoto. Conservati i controlli
  STANDARD/VCEP già presenti per l'assessment dei meccanismi.
- `test_acmg_pvs1.py`: conservati provider e geometria nonsense; la fixture HBB
  pubblica ora verifica direttamente `nonsense()` senza valutatore esterno.
- `tests/test_pvs1_calculator.py`: verifica lifecycle senza processi/connessioni
  al valutatore, presenza delle route locali e assenza delle route rimosse.
- README, mappa di architettura e documento del Calculator aggiornati.
  `TASK25_PVS1_EVIDENCE.md` descrive ora i componenti tecnici riutilizzati.
  Documenti Task27A/Task28, inventari STEP3A/STEP3C e `CACHE_HELPER.md`
  conservati con avviso storico; i JSON di audit
  storici non sono stati riscritti per cancellare la provenienza originale.

Confronto con lo snapshot: `pvs1/*.py`, `api/acmg_calculator.py`,
`core/acmg_molecular_impact.py` e `acmg-calculator.js` sono identici byte per byte.
AST di `nonsense()` e `digest()` identici alle funzioni precedenti. Formule,
versioni, soglie, strength e decision tree sono invariati.

## 4. Struttura finale e audit conservativo

| Directory | Responsabilità |
|---|---|
| `Helper.py`, `HelperGUI/`, `bin/` | GUI PyQt attiva e pipeline tradizionali, non modificate |
| `helper_next/src/helper_next/api/` | API locale, PVS1 e consultazione dei meccanismi |
| `helper_next/src/helper_next/core/` | Servizi applicativi, riferimenti, fonti e meccanismi locali |
| `helper_next/src/helper_variants/` | Import/indice/query VCF, annotazioni e fonti biologiche |
| `helper_next/src/helper_prioritization/` | Priorità sperimentale di revisione, distinta dalla classificazione ACMG |
| `pvs1/` | Modelli, regole STANDARD esistenti e analisi molecolare |
| `configs/`, `files/`, `scripts/`, `workflows/nextflow/` | Configurazioni, riferimenti e strumenti esistenti |
| `tests/`, `helper_next/tests/`, `docs/` | Fixture/test locali e documentazione |
| `legacy/root_gui/` | Materiale storico preesistente, non modificato |

La ricerca per hash non ha trovato file sorgente tracciati identici nell'area
attiva, esclusa `legacy/root_gui/`. Nessuna riorganizzazione estetica o rimozione
basata sul solo nome del file. Gli entry point CLI e i moduli di supporto con
responsabilità analoghe sono distinti, non duplicati da eliminare automaticamente.

L'analisi statica degli import, inclusi quelli differiti nelle funzioni, trova
cicli tra `acmg_mechanism_normalizer`, `acmg_mechanism_store` e `acmg_ontology`.
Sono preesistenti e non sono stati rifattorizzati. Non è stata eseguita una
bonifica indiscriminata di tutti gli import o delle funzioni simili del progetto.

## 5. Motore locale e preservazione PVS1

Percorso operativo unico di valutazione:

```text
variant-browser.js -> acmg-calculator.js
  -> POST /api/acmg-calculator/pvs1
  -> api/acmg_calculator.py:evaluate_pvs1
  -> pvs1/calculator.py:calculate_pvs1
```

La route legge l'allele dal database indicizzato e vincola campione, variante,
annotation ID e trascritto. `acmg_context` fornisce contesti locali con fonte.
Il calcolatore esegue Python nello stesso processo, senza importare o chiamare
il progetto esterno. Le API biologiche pubbliche rimangono intenzionalmente
utilizzabili; non sono servizi di valutazione ACMG.

Sono preservati catalogo genico, struttura esoni/CDS, mapping su entrambi gli
strand, stop-gain/frameshift, stop prematuro, estensione nella 3′ UTR,
percentuale fisica di CDS eliminata, reference non tradotta/alterata,
accorciamento proteico, record non calcolabili, versioni e provenance.
`acmg_molecular_impact.analyze_transcripts()` e `pvs1/impact.py` confrontano i
trascritti; la decisione PVS1 resta riferita all'annotazione selezionata, senza
scegliere il trascritto con strength maggiore.

Il risultato conserva criterio, stato, strength calcolata/applicata, motivazione,
warning, dati mancanti e `decision_trace` con valore, soglia e fonti. Il modello
ammette ACTIVE/INACTIVE/EXPLORATORY e gli stati locali NOT_EVALUABLE e
REQUIRES_REVIEW; non sono state aggiunte regole per produrre stati ulteriori.

**Limiti già presenti:** il motore locale implementa solo PVS1 con policy
STANDARD, ruleset `PVS1_GENERAL 1.1.0`. Policy diverse restano esplicitamente
non valutabili. Non esiste un equivalente locale di classificazione ACMG
complessiva, matrice di tutti i criteri, profili custom/VCEP di valutazione,
confronto protocolli/profili, override degli alberi, replay/trace remoto,
review/rerun/export dei risultati del vecchio Workbench. Queste funzioni erano
legate al servizio rimosso e non sono state ricreate o simulate.
La normalizzazione e l'assessment locale di record VCEP già implementati sono
conservati; non equivalgono a una policy VCEP del nuovo Calculator.
Gli archivi dei risultati precedenti restano sul disco, ma la relativa UI/API
non fa più parte del percorso operativo.

## 6. Mappatura delle cinque cache future

I nomi seguenti sono categorie di pianificazione: nessuna nuova cache,
tabella, directory o migrazione è stata implementata.

| Categoria | Recupero attuale | Memorizzazione attuale | Consumatori e riuso |
|---|---|---|---|
| `patients` | `core/variant_import.py`, `external_vcf.py`, `analysis_history.py`; `helper_variants/indexer.py` legge VCF/TSV e metadati del run | Per run: `results/VARIANT_VIEWER/variants.sqlite`; history in `$XDG_DATA_HOME/helper_next/analysis_history.sqlite3`; import in `helper_next/imported_variant_runs` ed `external_vcf` sotto la stessa data home | API variants, query, browser, prioritizzazione e route PVS1; riusare identità degli alleli, parser e binding dei campioni |
| `variants_static` | CSQ/ANN/TSV e release VEP importati dall'indexer; normalizzazione con FASTA quando configurata | Tabelle variants/annotation_releases/annotations nell'indice del run; metadata/header e predittori già associati alla release | `helper_variants/query.py`, prioritizzazione, PVS1; riusare struttura release/provenance senza spostare i dati ora |
| `variants_dynamic` | `helper_variants/clinvar.py`, `gnomad_frequency.py`; API ClinVar/gnomAD o letture esplicite delle cache | `$XDG_DATA_HOME/helper_variants/clinvar_evidence.sqlite3` e `gnomad_frequency.sqlite3`; annotazioni ClinVar importate restano anche negli indici | API dettaglio, prioritizzazione, `SourceManager`; mantenere separati rilascio upstream, data di acquisizione, TTL e snapshot |
| `gene2p` | `helper_variants/gene_phenotype.py`: GenCC, G2P, HPO, ClinGen dosage, Orphadata, constraint gnomAD; `SourceManager` legge gli indici; registry ontologico e record VCEP già implementati | `$XDG_DATA_HOME/helper_variants/gene_phenotype.sqlite3`; `$XDG_DATA_HOME/helper_next/mechanisms.sqlite3` per record, snapshot, mapping e bulk run | `acmg_context`, mechanism normalizer/store/resolver/bulk/assessment/ontology, API mechanisms e contesto PVS1; riusare identità e scope disease/inheritance |
| `gene_struct` | `acmg_transcripts.TranscriptReferenceProvider`, API pubbliche Ensembl qualificate per assembly/release/accession; catalogo genico e sequenze | JSON con chiave/hash in `~/.cache/helper/transcripts`; `HELPER_TRANSCRIPT_CACHE` consente override; limiti temporanei di errore in memoria in `acmg_molecular_impact.py` | SourceManager, PVS1 molecular/impact/calculator e frontend dei trascritti; riusare qualificazione, coordinate e checksum |

`XDG_DATA_HOME` predefinita: `~/.local/share`. Override esistenti:
`HELPER_ANALYSIS_HISTORY_DB`, `HELPER_IMPORTED_RUNS_DIR`,
`HELPER_EXTERNAL_VCF_DIR`, `HELPER_CLINVAR_CACHE`,
`HELPER_GNOMAD_FREQUENCY_CACHE`, `HELPER_GENE_PHENOTYPE_DB`,
`HELPER_MECHANISM_DB`, `HELPER_TRANSCRIPT_CACHE`, `HELPER_ENSEMBL_RELEASE`.

Duplicazioni/responsabilità da consolidare in seguito:

- Gli indici per run uniscono dati del campione e annotazioni statiche;
  l'eventuale deduplicazione tra run richiede un progetto di migrazione separato.
- ClinVar può comparire sia nell'annotazione VCF sia nella cache dinamica;
  i due record non sono automaticamente intercambiabili per età/provenance.
- L'indice gene-disease contiene le asserzioni originali; la cache dei meccanismi
  conserva record e snapshot derivati. Sono ruoli distinti, pur con dati ripetuti.
- Ogni modulo ha connessioni SQLite/JSON e policy proprie. Non sono state fuse
  policy TTL, transazioni o chiavi per ottenere solo uniformità estetica.
- Il provider dei trascritti ha già una cache di riferimenti; il piccolo cache
  di errori e i lock dell'analisi molecolare non costituiscono una sesta cache
  persistente. I riferimenti FASTA locali restano risorse condivise.

Nessuna delle cinque categorie ha una dipendenza operativa residua dal vecchio
valutatore. L'archivio Workbench precedente è invece un archivio di risultati
storici: non va cancellato né assimilato automaticamente alle cache pubbliche.

## 7. Test e verifiche

Baseline prima delle modifiche:

- Suite mirata ACMG/PVS1, context, VCF indexer/import/query/store:
  **307 passed, 1 skipped, 8 deselected; 185 subtests passed**.
- Test del vecchio repository remoto esclusi intenzionalmente: non è stato
  importato né avviato il valutatore esterno per costruire la baseline.
- Prima esecuzione ampia nella sandbox interrotta nel test HTTP/AnyIO.
  Lo stesso test passa fuori sandbox (**1 passed**), quindi il blocco è ambientale.
- Esecuzione ampia fuori sandbox interrotta al limite di 180 secondi nella zona
  del test samplesheet che include la home nelle radici di ricerca; nessun
  fallimento riportato fino al punto raggiunto.

Dopo le modifiche:

- Stessa area mirata rimasta operativa: **226 passed, 1 skipped;
  185 subtests passed**. La diminuzione comprende i test del sistema eliminato;
  non è una perdita dichiarata di copertura delle nuove fixture molecolari.
- La prima esecuzione dei test adattati ha rilevato due asserzioni errate nel
  test context: attendevano un campo aggiunto dal vecchio packet builder.
  Corrette le asserzioni per verificare fonti e versione del contesto locale;
  nessuna modifica applicativa/scientifica necessaria.
- Suite integrale finale: **646 passed, 1 failed, 1 skipped;
  185 subtests passed**, in 325,50 secondi. Anche il test samplesheet lento
  si è infine concluso con successo. Il fallimento è
  `test_catalog_covers_helper_scripts_and_builds_script_invocations`:
  `audit_mechanism_inventory.py` e `validate_ontology_registry.py` sono presenti
  in `scripts/` ma non in `SCRIPT_OPERATIONS`. Riprodotto sullo snapshot originale
  in `/tmp/helper-cleanup-baseline-tree`: stesso fallimento prima della pulizia.
  Non è stato corretto perché estraneo al task.
- Esecuzione ampia aggiuntiva escludendo quel solo test samplesheet lento:
  **645 passed, 1 failed, 1 skipped, 1 deselected; 185 subtests passed**,
  in 47,37 secondi; stesso fallimento preesistente del catalogo.
- Nessuna regressione introdotta rilevata nei controlli completati.
- `compileall` su PVS1/backend/varianti: passato.
- `node --check` su tutti gli **11 moduli JavaScript** rimasti: passato;
  tutti gli import locali risolti, incluse le query di versione degli URL.
- Build del package in directory temporanea e import dell'app fuori repository:
  verificati dal test esistente; PVS1 è incluso nella distribuzione.
- Lifecycle FastAPI verificato senza processo o connessione a un valutatore;
  route locale presente, route legacy assenti. Nessuna ricerca del repository
  adiacente necessaria per creare l'applicazione.
- Frontend: sorgenti e import verificati. Il test Chrome esistente è saltato
  perché la sandbox impedisce la creazione dei socket. L'esecuzione esterna
  è stata rifiutata: **nessuna verifica frontend interattiva attestata**.
  Non esiste un build npm separato: il frontend è composto da moduli JS statici.
- Dopo la rimozione degli import diventati inutilizzati: **43 passed,
  1 deselected** nei test provider/nonsense/mechanism offline.
- Dopo la rimozione dei metodi di serializzazione del vecchio contratto:
  **85 passed, 1 skipped** nei test assessment/Calculator. Confronto AST:
  `assess()` e `approved_vcep_assertion()` invariati rispetto allo snapshot.
- `git diff --check` e ricerca dei riferimenti operativi legacy: verificati.
  I riferimenti rimasti nei documenti storici/manifest di audit non sono import,
  configurazioni o istruzioni di avvio attive.

Log, XML JUnit e manifest di verifica sono in `/tmp/helper-cleanup-*`.
Il warning `python_multipart` è già presente nella baseline.
Non sono stati eseguiti job Nextflow reali, accessi a dati diagnostici o test
con servizi biologici live per questa pulizia.

## 8. Problemi aperti

1. **P1 — Copertura scientifica locale parziale:** solo PVS1 STANDARD; le
   funzionalità del servizio elencate sopra non hanno equivalente locale.
   Nessuna implementazione automatica è compresa nella pulizia.
2. **P1 — Verifica frontend interattiva pendente:** il codice UI PVS1 è
   preservato, ma catalogo, espansione righe, selezione e visualizzazione dei
   risultati richiedono ancora la prova Chrome in un ambiente consentito.
3. **P2 — Fallimento preesistente del catalogo script:** il catalogo dei
   wrapper non comprende i due script di audit. Riproducibile sullo snapshot
   precedente; non corretto in questo task.
4. **P2 — Test samplesheet lento preesistente:**
   `test_resolve_file_paths_finds_unique_match_in_roots` include l'intera home;
   passa nella suite integrale ma ne aumenta molto la durata.
5. **P2 — Cicli di import e sovrapposizioni delle cache:** richiedono una
   valutazione dedicata prima di accorpare responsabilità persistenti.
6. **P2 — Risultati storici del Workbench:** dati conservati, vecchia UI/API
   ritirata. Non è stato implementato un nuovo lettore o formato di export.

## 9. Prossimo step proposto

Preparare un inventario di chiavi, versioni, schema e policy di lettura/scrittura
per le cinque categorie, partendo da indice run, `SourceManager` e provider dei
trascritti. Separare prima le responsabilità `patients`/`variants_static` sulla
carta e definire fixture di identità, release e provenance. Riutilizzare i
repository di dati attuali e valutare ogni migrazione come task separato con
backup e confronto dei dati. Nessuna nuova cache è stata avviata in questo task.
