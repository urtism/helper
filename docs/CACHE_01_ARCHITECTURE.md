# CACHE-01 — Architettura delle cache e contratti dati HELPER

Data: **29 ottobre 2026**. Stato: **audit e progetto; nessuna implementazione**.

## 1. Decisioni, perimetro e metodo

SQLite resta la persistenza operativa iniziale. Le cinque categorie sono confini
logici: non richiedono cinque database, né una riscrittura dei provider.
PostgreSQL è una possibile destinazione futura, senza driver, adapter, ORM o doppia
persistenza in questa fase.

Si conservano gli indici delle run, i database delle fonti e dei meccanismi e il
provider Ensembl. I JSON Ensembl restano artefatti di riferimento versionati,
analogamente ai FASTA e ai bundle VEP: non si crea un nuovo database soltanto per
convertire una cache file già funzionante. Le estensioni transazionali proposte
usano database SQLite esistenti.

Sono stati letti prima [HELPER_STRUCTURAL_CLEANUP.md](HELPER_STRUCTURAL_CLEANUP.md)
e [CACHE_HELPER.md](CACHE_HELPER.md), il cui percorso effettivo è `docs/CACHE_HELPER.md`.
L'inventario seguente è verificato sulle dichiarazioni di schema e sulle funzioni
del **working tree attuale**, comprese le modifiche di cleanup già presenti.
Le parti storiche di CACHE_HELPER relative al vecchio Workbench non descrivono
consumer attivi. Non sono stati importati moduli applicativi, aperti database
operativi, letti VCF di campioni o interrogati servizi remoti. Percorsi e versioni
qui riportati descrivono il codice, non attestano presenza, dimensione o schema
effettivo dei file installati. Il futuro preflight dovrà verificare anche questi.

Legenda delle proposte:

- **ESSENTIAL**: necessaria per identità corrette, conservazione o riuso affidabile.
- **RECOMMENDED**: miglioramento utile, senza bloccare l'uso delle strutture attuali.
- **DEFERRED**: da valutare solo in un task successivo con beneficio dimostrato.

Le sezioni di inventario descrivono fatti esistenti. Nelle sezioni progettuali la
priorità dichiarata si applica a tutte le specifiche del relativo punto. I nomi
di entità proposte non attestano l'esistenza di nuove tabelle.

## 2. Inventario effettivo

Abbreviazioni dei percorsi sorgente:

- `V/`: `helper_next/src/helper_variants/`.
- `C/`: `helper_next/src/helper_next/core/`.
- `A/`: `helper_next/src/helper_next/api/`.

Per i percorsi dati, `DATA` significa `$XDG_DATA_HOME`, oppure `~/.local/share`.
Gli override devono essere rispettati; non si assume che tutte le installazioni
usino i default.

### 2.1 Indice varianti per run e storico delle analisi

Implementazione: [store.py](../helper_next/src/helper_variants/store.py),
[indexer.py](../helper_next/src/helper_variants/indexer.py),
[query.py](../helper_next/src/helper_variants/query.py),
[analysis_history.py](../helper_next/src/helper_next/core/analysis_history.py),
`C/variant_import.py`, `C/external_vcf.py`.

Indice: `<run_dir>/results/VARIANT_VIEWER/variants.sqlite`;
`store.SCHEMA_VERSION = 2`, `store_kind` ammette `run` e `cohort`.
Il supporto allo schema cohort non implica un archivio globale già popolato.

| Tabella esistente | PK e unicità aggiuntiva | Contenuto e riferimenti |
|---|---|---|
| `store_metadata` | `singleton`, vincolato a 1 | Tipo store, versione schema, creazione |
| `runs` | `id INTEGER`; UNIQUE `run_key` | Percorso sorgente, reference build, importazione, metadata JSON |
| `subjects` | `id INTEGER`; UNIQUE `subject_key` | Metadati JSON; struttura esistente, nessuna nuova identità paziente proposta |
| `samples` | `id INTEGER`; UNIQUE `sample_key` | FK facoltativa subject, display name, specimen type, metadata JSON |
| `analyses` | `id INTEGER`; UNIQUE `analysis_key` | FK run/sample, role, pipeline e QC JSON |
| `variants` | `id INTEGER`; UNIQUE `(reference_build, chromosome, position, reference, alternate)` | Allele, tipo, metadata JSON con INFO e rappresentazione VCF originale |
| `calls` | `id INTEGER`; UNIQUE `(analysis_id, variant_id, caller)` | FK analysis/variant; GT, phased, zygosity, DP/AD/AF/GQ/QUAL/FILTER, FORMAT originale e numero ALT nel JSON |
| `annotation_releases` | `id INTEGER`; UNIQUE `release_key` | Annotator/version, build, creazione, resources JSON |
| `annotations` | `id INTEGER`; UNIQUE `(variant_id, release_id, allele, transcript, consequence, hgvsc, hgvsp)` | FK variant/release, gene, impact, clinical significance, AF, canonical, campi CSQ/ANN originali in JSON |
| `index_sources` | `id INTEGER`; UNIQUE `(run_id, relative_path)` | FK run, stage, size/mtime/SHA-256, stato, checkpoint, error, timestamp; aggiunta dalla migrazione 2 |

Indici espliciti: `idx_analyses_run(run_id,sample_id)`,
`idx_calls_variant(variant_id,analysis_id)`,
`idx_variants_locus(reference_build,chromosome,position)`,
`idx_annotations_gene(release_id,gene,variant_id)`,
`idx_annotations_variant(variant_id,release_id)`,
`idx_index_sources_status(run_id,status)`. Si aggiungono quelli impliciti di PK/UNIQUE.

Scrittura: `index_run`, `index_vcf`, `index_tsv`, `register_*`,
`get_or_create_variant`, `record_call`, `record_annotation`. Inserimenti
idempotenti con `INSERT OR IGNORE`; call o annotazioni incompatibili con una
chiave già presente producono errore. Checkpoint e hash permettono ripresa e
riconoscimento delle sorgenti modificate. Non c'è TTL biologico dell'indice.
`connect(..., store_kind)` inizializza/migra; abilita FK, timeout 30 s e WAL.
La connessione senza `store_kind` valida lo schema esistente.

Identità attuali: `run_key` deriva da `record.run_id` o dal nome directory;
`_physical_run` riusa la run per `source_path` quando più tentativi nello storico
condividono la directory. `sample_key` e `analysis_key` sono `run_key:nome`.
I numeri `id` sono locali al database. La release originale è
`run_key:original:<primi 16 caratteri SHA-256 file>`; il digest completo è nei
resources, insieme a definizioni INFO/header. Non è una release globale VEP.

L'indexer separa ciascun ALT, conserva GT e numero dell'allele, assegna CSQ/ANN
multialleliche tramite `ALLELE_NUM` o corrispondenza non ambigua. Non assegna
automaticamente ClinVar INFO multiallelica a tutti gli ALT. Esegue trimming e,
quando dispone di FASTA, left alignment e controllo REF. `reference_build()` può
restituire una stringa di configurazione o `unknown`; `store` non uniforma
assembly e nomi cromosomici. La normalizzazione completa non è quindi garantita
per ogni indice preesistente.

Lettori: query/browser/API variants, prioritizzazione, contesto locale,
`A/acmg_calculator.py`. Gli indici accostano dati campione e annotazioni, ma le
tabelle sono già separate. `variants.metadata_json` può conservare soltanto la
prima origine incontrata per un allele, dato l'inserimento con IGNORE: non è un
registro completo di tutte le occorrenze originali.

Archivio durevole separato: `DATA/helper_next/analysis_history.sqlite3`, override
`HELPER_ANALYSIS_HISTORY_DB`; tabella `runs(id TEXT PRIMARY KEY, created TEXT,
document TEXT)`, nessun indice esplicito ulteriore. `create()` usa UUID4 hex;
`get/list_runs/update/delete` accedono al documento JSON, update/delete usano
`BEGIN IMMEDIATE`. L'ID dello storico identifica un tentativo, non necessariamente
la run fisica dell'indice. Gli input importati restano nei depositi
`DATA/helper_next/imported_variant_runs` e `DATA/helper_next/external_vcf`, con
override `HELPER_IMPORTED_RUNS_DIR` e `HELPER_EXTERNAL_VCF_DIR`. Non sono cache
biologiche eliminabili.

### 2.2 ClinVar e frequenze gnomAD

Implementazione: [clinvar.py](../helper_next/src/helper_variants/clinvar.py),
[gnomad_frequency.py](../helper_next/src/helper_variants/gnomad_frequency.py).

| Archivio | Schema reale, chiave e indici | Lettura/scrittura, aggiornamento e limiti |
|---|---|---|
| `DATA/helper_variants/clinvar_evidence.sqlite3`; `HELPER_CLINVAR_CACHE` | `evidence(allele_key TEXT PRIMARY KEY, payload TEXT NOT NULL, retrieved_at TEXT NOT NULL)`; nessun indice esplicito ulteriore. Chiave `assembly\|chrom\|pos\|REF\|ALT` dopo adattamento locale | `lookup_variant`, `_cached`, `_store`; UPSERT sovrascrive la voce. Positivi 7 giorni, negativi 1 giorno. `cached_evidence` legge batch di 500 chiavi con TTL e senza rete. `refresh=True` bypassa il dato. Il payload include identificativi/versioni quando disponibili, date del record, URL e acquisizione; non contiene una release globale certificata |
| `DATA/helper_variants/gnomad_frequency.sqlite3`; `HELPER_GNOMAD_FREQUENCY_CACHE` | `frequencies(cache_key TEXT PRIMARY KEY, release TEXT NOT NULL, payload TEXT NOT NULL, retrieved_at TEXT NOT NULL)`; nessun indice esplicito ulteriore. Chiave `dataset_id\|assembly\|chrom\|pos\|REF\|ALT` | `lookup_variant`, `cached_variant`, `cached_context(s)`, `_store`; `INSERT OR REPLACE`, nessun TTL. Lettura batch locale a blocchi di 500; lookup remoto puntuale, query regionali separate. Release configurate nel codice: GRCh37 → dataset `gnomad_r2_1`, release `2.1.1`; GRCh38 → `gnomad_r4`, release `4.1`. Questi valori non sono verifica della release live |

ClinVar interroga E-utilities, abbina l'allele esatto e può arricchire il dettaglio
delle classificazioni. Anche un hit privo di `classification_breakdown` può fare
rete. Il retry HTTP è limitato a due tentativi. `_cached` passa da `_connect`,
che può eseguire DDL: non è un accesso fisicamente read-only come il batch.

La route `A/variants.py:sample_variant_detail` chiama attualmente ClinVar con
**`refresh=True` a ogni apertura**, e rimpiazza l'evidenza di dettaglio con quella
recuperata; in errore espone `unavailable`. La lista usa invece le cache batch.
Il TTL del provider non descrive quindi il comportamento di tutte le route.

gnomAD conserva AC/AN/AF, filtri, popolazioni e copertura; distingue `observed`,
`not_observed_covered`, `not_observed_low_coverage` e
`not_observed_coverage_unknown`. Gli errori remoti restituiscono `unavailable`
senza sostituire con una frequenza zero. Il client ammette solo alleli A/C/G/T
su cromosomi nucleari principali; mitocondrio e altre rappresentazioni sono
`unsupported`. `HELPER_GNOMAD_OFFLINE` impedisce il fetch puntuale. Il retry HTTP
arriva a tre tentativi. Non c'è single flight persistente in questi due moduli.

**Problema di versione:** la chiave gnomAD include l'ID del dataset, non il valore
esatto `release`. `cached_variant` ricontrolla una chiave ricalcolata dall'allele,
non una corrispondenza esplicita della release. Un aggiornamento del contenuto
dietro lo stesso dataset ID richiede invalidazione e versionamento separati.

Consumatori: API dettaglio/frequenze, `query.list_variants`,
`helper_prioritization.engine`; `SourceManager.population` legge anche gnomAD.
Nessuna delle due tabelle mantiene oggi una cronologia delle revisioni.

### 2.3 Indice gene-fenotipo e fonti gene-malattia

Implementazione: [gene_phenotype.py](../helper_next/src/helper_variants/gene_phenotype.py).
Archivio `DATA/helper_variants/gene_phenotype.sqlite3`, override
`HELPER_GENE_PHENOTYPE_DB`; schema **4** in `metadata`, non `PRAGMA user_version`.

| Tabella | PK | Struttura biologica principale e indici espliciti |
|---|---|---|
| `metadata` | `key` | Valori testuali: schema, URL fonti, acquisizione globale, ETag/Last-Modified GenCC |
| `assertions` | `sgc_id` | `version_number`, gene CURIE/symbol, disease CURIE/titolo corrente e originale, classificazione, MOI, submitter, date, PMID/URL; indici `gene_curie`, `gene_symbol NOCASE` |
| `hpo_features` | `(disease_curie,hpo_id,qualifier,reference)` | Termini, evidenza, onset/frequency/sex/modifier/aspect/biocuration; indice disease |
| `g2p_records` | `g2p_id` | Gene, disease CURIE/MIM/nome, allelic requirement, confidence originale, mechanism/category/support, consequence, pubblicazioni/review/URL; indici gene symbol/curie |
| `clingen_dosage` | `gene_symbol NOCASE` | Gene NCBI, coordinate, HI/TS score/descrizione/PMID/disease ID, valutazione, URL; nessun altro indice esplicito |
| `gnomad_constraints` | `gene_symbol NOCASE` | Gene Ensembl, transcript, available, pLI/LOEUF/LoF/missense, acquisizione e URL; nessun altro indice esplicito |
| `orpha_aliases` | `(identifier,orpha_id)` | Mapping relation; indice identifier NOCASE |
| `disease_codes` | `(orpha_id,system,code)` | Nome, mapping/ICD relation, validation status e URL/URI; indice orpha_id |

`refresh_cache` scarica GenCC, HPO annotazioni/termini, G2P, ClinGen Dosage e
Orphadata; `build_cache` costruisce un SQLite temporaneo nello stesso filesystem
e pubblica con `os.replace`. I metadati di release di ogni fonte non sono
conservati separatamente; solo GenCC ha ETag/Last-Modified nel builder attuale.
I campi importati sono una selezione, non gli interi download originali.
Il rebuild crea anche una tabella constraint vuota: non copia i constraint
puntuali del precedente DB. `refresh_gnomad_constraint` scrive invece in-place.

`query_gene`, `priority_contexts`, `mechanism_association_inventory` e
`mechanism_source_records` leggono questi indici. Le query ordinarie possono
restituire dati `ready` ma `stale`; la route gene-phenotypes avvia il refresh
in background. La soglia è 7 giorni per l'indice e 30 per i constraint.
I lock di refresh globale/per gene sono **in memoria nel processo**.

`mechanism_source_records` conserva le colonne indicizzate e distingue dataset
non importato da query senza record. Per ClinVar restituisce `NOT_SUPPORTED`:
l'adapter attuale è per allele, non per associazione gene-malattia. Per gnomAD
separa `CACHE_MISS` da constraint interrogato ma assente. I packet dichiarano
`dataset_version=None`; l'etichetta constraint `v4.1.2` nel catalogo non è un
token di release conservato dalla fonte. Il refresh delle fonti bulk qui rilegge
l'indice locale, non esegue una nuova sincronizzazione upstream.

Consumatori: browser geni, prioritizzazione, `acmg_context`, Source Manager,
normalizzazione e bulk dei meccanismi. Sono già presenti fallback per simbolo
nelle query di presentazione: non costituiscono prova di equivalenza fra ID
genici. I reader dei meccanismi e il contesto locale applicano verifiche più
specifiche di identità/scope.

### 2.4 Cache dei meccanismi, snapshot e registro ontologico

Implementazione: [acmg_mechanism_store.py](../helper_next/src/helper_next/core/acmg_mechanism_store.py),
[acmg_mechanisms.py](../helper_next/src/helper_next/core/acmg_mechanisms.py),
`C/acmg_mechanism_models.py`, `C/acmg_mechanism_normalizer.py`,
`C/acmg_mechanism_assessment.py`, `C/acmg_mechanisms_bulk.py`, `C/acmg_ontology.py`.
Archivio `DATA/helper_next/mechanisms.sqlite3`, override `HELPER_MECHANISM_DB`;
schema **3**, controllato con `PRAGMA user_version`.

| Tabella | PK e relazioni | Contenuto / indici espliciti |
|---|---|---|
| `source_records` | `id TEXT` | Source name/record ID/version/dataset version, URL/date, content hash, raw payload JSON, normalizer/fetch status; indice `(source_name,source_record_id,source_record_version)` |
| `mechanism_snapshots` | `snapshot_id` | Association key, matrix hash, versioni normalization/reconciliation/mapping, creazione, payload JSON; indice `(gene_disease_key,created_at)` |
| `snapshot_records` | `(snapshot_id,evidence_id)`; FK snapshot/source record | Collegamenti alle evidenze originali |
| `gene_disease_mechanisms` | `gene_disease_key`; FK snapshot | Gene HGNC/ID, disease ID, allelic requirement, stato/versioni/date; indici `(gene_id,disease_id,allelic_requirement)` e HGNC |
| `mechanism_reviews` | `review_id`; FK snapshot | Reviewer, stato, meccanismo, rationale, data/versione |
| `mechanism_source_state` | `(gene_id,source_name)` | Status, checked/expires epoch REAL, local revision, packet JSON, errore; indice expires_at |
| `mechanism_refresh_leases` | `resource` | Token e scadenza epoch REAL |
| `mechanism_changes` | `id` | Association key, snapshot precedente/corrente, data, differenze JSON; riferimenti snapshot senza FK dichiarate |
| `mechanism_bulk_runs` | `run_id` | Inventory hash, stato, date, options/report JSON, elapsed |
| `mechanism_bulk_items` | `(run_id,association_key)`; FK run/snapshot | Ordinal, association/input hash, stato/tentativi, snapshot iniziale/corrente, summary/error; indici `(run_id,status,ordinal)`, `(association_key,updated_at)` |
| `mechanism_bulk_publications` | `(run_id,snapshot_id)`; FK entrambe | Pubblicazioni del bulk |
| `ontology_registry_releases` | `registry_id` | Manifest JSON |
| `ontology_registry_current` | `singleton=1`; FK registry | Puntatore corrente |
| `ontology_mapping_records` | `mapping_id` | Registry ID, identificativi source/target, verifica, payload JSON; indice `(registry_id,source_identifier,target_identifier)`; registry_id non ha FK dichiarata |

Le PK testuali sono trasferibili: `msr-` deriva da fonte, ID/versione del record,
dataset version e hash del contenuto; `mss-` da association key e matrix hash.
`association_key` attuale include gene, disease, allelic requirement **e
MAPPING_VERSION**. Il registry può canonicalizzare la malattia prima del lookup.
Non è quindi una chiave di associazione indipendente da tutte le policy.

`MechanismStore.publish` pubblica record, snapshot, link e puntatore corrente
in una transazione `BEGIN IMMEDIATE`, con FK abilitate. Trigger bloccano
UPDATE/DELETE di source records, snapshot, snapshot links e delle release/record
ontologici. `current/snapshot/source_record` verificano hash; `peek/peek_states`
permettono letture senza inizializzare il DB. Le connessioni ordinarie possono
inizializzare o migrare; il database è impostato a permessi 0600.

`MechanismEvidenceCache.resolve_gene_disease_mechanism` offre `CACHE_ONLY`,
`REFRESH_IF_STALE`, `FORCE_REFRESH`, `SNAPSHOT`. Default: positivi 7 giorni,
gnomAD 30 giorni, `NO_RECORDS` 1 ora, errori 60 s; packet stale/CACHE_MISS
ricevono durata breve. Override `HELPER_MECHANISM_TTL_JSON`. Invalidazione anche
su revisione file/WAL dell'indice e versioni degli algoritmi/registry. La lease
persistente per gene evita refresh concorrenti anche fra associazioni diverse;
si rilegge lo stato dopo averla ottenuta. Il bulk ha checkpoint, lease rinnovabile
e controlli di revisione dell'inventario.

In errore viene conservato l'ultimo snapshot completo, con lo stato tecnico
aggiornato separatamente. `CACHE_ONLY` può comunque costruire una matrice da
indici locali e salvarla se manca: significa assenza di acquisizione remota,
non necessariamente assenza di scritture. Il fetch constraint remoto richiede
`HELPER_MECHANISM_FETCH=1`. I raw payload sono le righe che l'importatore ha
conservato: non possono recuperare colonne upstream già scartate.

Queste strutture producono matrici di evidenze e assessment biologici. Non sono
un classificatore ACMG complessivo. Il supporto a record VCEP qualificati
nell'assessment non implica un downloader ClinGen VCEP attivo: gli adapter
correnti non forniscono tali record.

### 2.5 Cataloghi genici e strutture dei trascritti Ensembl

Implementazione: [acmg_transcripts.py](../helper_next/src/helper_next/core/acmg_transcripts.py),
`C/acmg_sources.py`, `C/acmg_molecular_impact.py`, `pvs1/molecular.py`,
`pvs1/impact.py`. Archivio `~/.cache/helper/transcripts`, override
`HELPER_TRANSCRIPT_CACHE`; non deriva da XDG_DATA_HOME.

Nessuna tabella SQL o indice secondario. Un file JSON per digest della chiave:

- Trascritto: `{schema: VERSION, assembly, transcript: ENST...version, release}`.
- Catalogo: `{schema: VERSION, assembly, gene, release}`.

`VERSION` è `helper-transcript-reference-1.0`; la release esplicita proviene da
`HELPER_ENSEMBL_RELEASE` o dal costruttore. I file contengono `key`, `raw`, `urls`,
`acquired_at`, `digest`. Il provider verifica identità, hash e release prima/dopo
il download; pubblica con file temporaneo univoco e replace atomico. Nessun TTL.
`get` richiede accession Ensembl versionata e non sostituisce con RefSeq/latest.
Host configurabile con `HELPER_ENSEMBL_REST_URL`; una release dichiarata ma non
servita dall'host genera errore, senza sostituzione silenziosa.

Il catalogo `gene_transcripts` conserva lookup espanso, trascritti anche non
codificanti, coordinate, strand, esoni e flag canonical/MANE/APPRIS. Il lookup
genico originale conserva anche le coordinate del gene; queste non sono tutte
esposte nella proiezione `data`. `get/qualify` espone esoni ordinati in senso
trascrizionale, coordinate genomiche/mRNA, CDS/coding segments, giunzioni,
cDNA/CDS/proteina, gene IDs e digest/provenance. Coordinate 1-based inclusive;
la CDS comprende lo stop. Sono controllate coerenza exon/CDS/traduzione e
assembly; il percorso molecolare attuale è per cromosomi nucleari principali.

UTR, exon rank e phase/frame non sono colonne persistenti dedicate:
le UTR derivano da cDNA e limiti CDS, il rank dall'ordine degli esoni, il frame
dalla struttura codificante qualificata. Non va dichiarata una phase upstream
se non acquisita. Il catalogo non codificante è distinto dal riferimento
codificante completo richiesto da `qualify`.

`SourceManager.transcript/gene_transcripts` controlla fetch anche tramite
`HELPER_TRANSCRIPT_FETCH`. `acmg_molecular_impact._reference_source` aggiunge
single flight nel processo e cache errori di 30 s, massimo 128 fallimenti;
i lock LRU hanno massimo 512 chiavi. Non è una cache persistente aggiuntiva né
un lock fra processi. Il download diretto del provider non ha questi lock.

### 2.6 Cache e archivi collaterali

| Componente reale | Archivio / struttura / aggiornamento | Ruolo e decisione |
|---|---|---|
| `V/liftover.py` | `DATA/helper_variants/assembly_projection.sqlite3`, `HELPER_LIFTOVER_CACHE`; `projections(cache_key TEXT PK,payload TEXT,retrieved_at TEXT)`. Chiave assembly sorgente/chrom/pos/REF/ALT; destinazione opposta implicita; REPLACE, nessun TTL, nessun altro indice esplicito; `project_variant`, `_cached/_store`; `HELPER_LIFTOVER_OFFLINE` | Relazione di proiezione, non identità cross-assembly; consumer API/browser. Mantenere separata (**RECOMMENDED**), con futura provenance/versione del servizio (**RECOMMENDED**) |
| `V/panelapp.py` | `DATA/helper_next/panelapp/catalog.json`, `HELPER_PANELAPP_CACHE`; dettagli `panels/<id>-v<version>.json` o `-latest.json`. Catalogo in memoria 24 h, disk sync esplicito/assenza; dettagli validi senza TTL, fallback locale compatibile; scrittura replace di `.tmp` | Selezione pannelli, non indice gene2p meccanicistico. Nessuna fusione necessaria (**RECOMMENDED**); versionare latest risolto negli usi riproducibili (**RECOMMENDED**) |
| `V/secondary_findings.py` | Liste versionate incluse nel modulo, `catalog/detail`; nessun DB o refresh remoto | Risorsa software per pannelli SF; conservarne versione (**ESSENTIAL** quando usata) |
| `V/query.py` | `_PRIORITY_ORDER_CACHE`: OrderedDict, massimo 4 ordinamenti, lock nel processo; chiave DB/sample/filtri/ruleset, fingerprint cache biologiche e minuto corrente | Cache derivata di ordinamento; nessuna evidenza originale. Invalidare sulla revisione delle fonti, includendo WAL se necessario (**RECOMMENDED**) |
| `C/acmg_reference.py` | FASTA/.fai esistenti; `_checksum` LRU 8 voci su path/size/mtime/ctime; `verify`, `HELPER_ACMG_REFERENCE_CONFIG` | Identità reference e controllo normalizzazione; non un nuovo archivio biologico. Riutilizzare (**ESSENTIAL**) |
| VEP, Nextflow | Bundle VEP configurato via `--dir_cache`; workdir e `.nextflow/cache` di esecuzione | Risorse annotative e ripresa pipeline; fuori dal consolidamento delle cinque categorie (**ESSENTIAL**) |
| `acmg.sqlite3`, backup, cataloghi storici descritti in CACHE_HELPER | Archivio Workbench precedente e backup; i relativi moduli di accesso sono stati rimossi dal working tree | Non classificare come cache attiva, non eliminare, migrare o riattivare (**ESSENTIAL**). Nessuna verifica fisica nuova effettuata |

## 3. Mappa delle cinque categorie e dipendenze

| Categoria | Base da riutilizzare | Dati esclusivi della categoria | Dipendenze |
|---|---|---|---|
| `patients` | Storico, depositi input, runs/samples/analyses/calls/index_sources del run store | Run, campioni, QC/GT/FORMAT, provenienza del record VCF, relazione campione-allele | Riferimenti logici a varianti/annotazioni; non copia le risposte biologiche condivise |
| `variants_static` | variants/annotation_releases/annotations e header originali nel run store | Identità allele, conseguenze, trascritti, predittori qualificati per versione | Reference normalizzata; release annotative; eventuali riferimenti gene/trascritto |
| `variants_dynamic` | ClinVar evidence, gnomAD frequencies | Evidenze variante/fonte/revisione, copertura e stato acquisizione | Identità allele e manifest fonte; liftover solo come relazione accessoria |
| `gene2p` | gene_phenotype + mechanisms + ontology registry | Associazioni gene-malattia-ereditarietà, originali/normalizzazioni/assessment | Mapping versionati, constraint gene-level; nessuna dipendenza necessaria da campione |
| `gene_struct` | TranscriptReferenceProvider e JSON Ensembl | Gene/trascritti/esoni/CDS/UTR/frame/sequenze qualificati | Assembly/release/reference; nessuna dipendenza dalla variante per il download |

Il passaggio da evidenze a priorità è in `helper_prioritization.engine`:
`score_variant/apply_clinvar_evidence` ricevono i contesti letti in batch da
`query.list_variants`. Il riepilogo genico usato senza malattia selezionata può
essere ambiguo: non sostituisce una relazione disease-specific per PVS1.

Il percorso locale è `A/acmg_calculator.evaluate_pvs1` →
`pvs1.calculator.calculate_pvs1`, con `acmg_context.build/select` per il contesto,
`acmg_molecular_impact.analyze_transcripts` e `pvs1.molecular/impact` per il
calcolo molecolare. `prepare_pvs1_input` ha anche una lettura diretta del
provider con fetch disabilitato. Non tutti i consumer attraversano Source Manager
e non tutti consumano la matrice mechanism. Il motore locale attuale implementa
PVS1 STANDARD, non l'intera classificazione ACMG.

## 4. Identità condivise — ESSENTIAL

### 4.1 Regole generali

Mantenere gli ID interi come FK locali e chiavi delle API attuali; aggiungere
identità logiche senza reinterpretare gli ID esistenti. Le identità logiche
sono stringhe UTF-8, senza significato dipendente dal motore SQL. Le tuple sono
serializzate in JSON canonico con schema esplicito e SHA-256 completo, riusando
`C/acmg_digest.digest`; nessuna concatenazione ambigua di nomi liberi.
Le stringhe/payload usati per hash non ammettono NaN/Infinity. La versione
della canonicalizzazione fa parte del contratto; gli hash storici esistenti
non vengono rigenerati con nuove regole.

| Entità | Identità logica proposta | Compatibilità e limiti |
|---|---|---|
| Tentativo di analisi | UUID `analysis_history.runs.id` esistente | Non usarlo come identità universale di ogni run fisica |
| Run fisica | `run_ref`: UUID persistente nel metadata della run, associato ai tentativi history esistenti | Per gli indici legacy assegnazione una tantum futura con mapping. Nome directory, path e hash del VCF sono provenance, non identità primaria |
| Campione nella run | `sample_ref = H(schema,run_ref,sample_key_originale)` | Nessuna equivalenza fra nomi uguali in run diverse; nessun nuovo identificativo anagrafico. Per correlazioni longitudinali usare solo relazioni già autorizzate/esistenti |
| Analisi/call | `analysis_ref = H(schema,run_ref,analysis_key_originale)`; call identificata da analysis_ref/allele_ref/caller | Le stage oggi possono condividere analysis_key: non inventare analisi distinte retroattivamente; mantenere il contesto pipeline originale |
| Allele genomico concreto | `allele_ref = ga1:<SHA-256 di assembly,sequenza di riferimento,position,REF,ALT normalizzati>` | Una sola ALT; identità indipendente da run/campione/rsID/HGVS/ClinVar ID |
| Variante | Per SNV/indel biallelico concreto `variant_ref = allele_ref` | Un sito multiallelico è un contenitore di alleli, non una chiave condivisa alternativa |
| Gene | CURIE stabile, HGNC preferito quando verificato; Ensembl/NCBI come ID distinti mappati | Simbolo e alias sono etichette. Mapping con fonte/release/hash, niente equivalenza da sola somiglianza del nome |
| Trascritto | namespace + accession + versione; `transcript_context_ref = H(schema,assembly,Ensembl release,namespace,accession,version)` | Stessa accession senza versione insufficiente; RefSeq ed Ensembl distinti. Il catalogo genico è identificato da gene/assembly/release |
| Associazione gene-malattia | `association_ref = H(schema,gene CURIE,disease anchor CURIE,allelic requirement normalizzato)` | Anchor della fonte conservato; UNKNOWN e requisiti distinti non si fondono. Mapping successivi sono relazioni versionate, non riscritture dell'anchor |
| Record di evidenza | `record_id = H(schema,source,source_record_id,source_record_version,source_version,source_snapshot_ref,content_hash)` | Immutabile; per dato senza ID upstream si usa il soggetto della query qualificato. Nessun timestamp inventato come release |
| Versione annotativa condivisa | `annotation_version_ref = H(schema,assembly,reference identity,manifest annotatore/risorse/plugin,parametri,versione parser/normalizer)` | Separata dalla release originale della run e dal digest del file campione |

L'associazione logica nuova affianca, senza sostituire, `gene_disease_key`
esistente: si conserva un mapping al key con MAPPING_VERSION e ai singoli
snapshot. Una nuova policy/mappatura può produrre un'altra vista normalizzata,
ma non cambia l'identità dell'asserzione originale. Alias MONDO/OMIM/ORPHA
passano dal registry già implementato; equivalenze ambigue restano esplicite.

### 4.2 Normalizzazione delle varianti

Prima del riuso globale:

1. Risolvere esplicitamente GRCh37/GRCh38; `unknown` resta consultabile nella run
   ma non entra nelle cache globali come allele verificato.
2. Risolvere il contig tramite accession/versione della sequenza di riferimento;
   per i cromosomi principali mantenere anche etichetta canonica 1–22/X/Y/MT.
   Registrare manifest/checksum del FASTA e mapping contig. Un alias `chr1` può
   diventare `1` solo nel contesto verificato; non fondere contig alt/decoy o
   reference mitocondriali differenti sotto la stessa etichetta.
3. Validare REF sul FASTA, uppercase, trimming e left alignment con
   `indexer.normalize_allele` e gli accessi reference esistenti. Posizione
   **1-based**, REF/ALT VCF non vuoti. Salvare normalizer version e risultato
   della validazione; non pretendere una normalizzazione completa senza reference.
4. Separare ALT e conservare record originale, indice ALT, GT originale, phase,
   metriche allele-specifiche e regola di associazione CSQ/ANN.
5. Alleli con la stessa tupla qualificata in run diverse condividono allele_ref.
   `rsID`, VCV, HGVS e indici ALT restano alias/provenance, non chiavi.

Un allele non verificato riceve solo un riferimento locale all'occorrenza:
non si marca falsamente come assenza nella fonte se manca la normalizzazione.
Alleli simbolici, breakend, `*`, CNV/SV e gVCF non risolti restano nel run store;
il riuso universale della tupla SNV/indel non ne garantisce l'identità.
Un contratto strutturale specifico è **DEFERRED**. Non ridurre MNV ad altre
varianti senza una policy esplicita. Liftover non fonde GRCh37 e GRCh38: produce
una relazione con validazione REF, fonte e possibili fallimenti/ambiguità.

### 4.3 Originali e annotazioni condivise

**ESSENTIAL:** conservare due livelli distinti:

- `original_annotation_ref = H(schema,run_ref,SHA-256 completo sorgente,
  identificatore dell'occorrenza nel file,indice ALT,identificatore riga CSQ/ANN)`.
  Il riferimento esatto al file sopravvive alla ricostruzione degli ID SQL.
- `shared_annotation_ref = H(schema,allele_ref,annotation_version_ref,
  transcript_context_ref o Feature qualificata,contenuto biologico normalizzato)`.
  Esclude campione, GT, INFO/FORMAT/QC personali e path della run.

Il manifest annotativo deve distinguere software VEP, release cache/Ensembl,
assembly, reference, plugin/predittori e versioni dei loro dataset, parametri
rilevanti e parser. `annotation_releases.created_at` è importazione locale;
`source_sha256` identifica il file originale. Nessuno dei due prova la versione
dei dataset. Il fallback esistente dalla major VEP alla release Ensembl in
`annotation_release()` va conservato e segnalato come fallback, senza promuoverlo
a versione scientifica verificata per deduplicazione globale.

Se il manifest è incompleto, mantenere annotazioni originali con scope della
run; uguaglianza apparente dei campi non dimostra equivalenza fra release.
Non ricalcolare VEP per riutilizzare record già qualificati. La deduplicazione
fisica fra run è **DEFERRED**; all'interno dell'indice le annotazioni sono già
condivise fra campioni tramite variant/release.

## 5. Contratto comune delle evidenze — ESSENTIAL

Contratto minimo logico, aggiungibile ai risultati dei provider esistenti senza
una nuova gerarchia di interfacce. Non tutti i campi devono essere colonne in
tutte le cache.

| Campo | Semantica e applicabilità |
|---|---|
| `record_id` | Identità immutabile di una revisione; assente/null se non è stato acquisito alcun record |
| `source` | Fonte e prodotto, per esempio ClinVar aggregate, gnomAD genomes o gene constraint; non il nome della funzione consumer |
| `source_version` | Release originale effettivamente osservata, nullable; separare `source_record_version`, release dataset e versione di schema/algoritmo HELPER |
| `source_snapshot_ref` | Hash/manifest del download o della risposta quando manca una release numerata; non presentarlo come release upstream |
| `retrieved_at` | Data UTC di acquisizione di quei byte dalla fonte; rileggere l'indice non la aggiorna |
| `updated_at` | Aggiornamento tecnico della voce/puntatore locale; separato da `source_updated_at`, data dichiarata dalla fonte, nullable |
| `assembly` | Richiesto per allele/struttura/coordinate; omesso per associazioni gene-malattia senza coordinate. Il contesto GRCh38 del file dosage resta nella provenance della fonte |
| `status` | Esito di disponibilità, con freshness e stato dell'ultimo tentativo separati |
| `provenance` | URL/query, upstream record ID/version, hash payload/reference, manifest, parser/normalizer/mapping/rules versions, derivazione e limitazioni |
| `checked_at`, `expires_at` / `next_retry_at` | Metadati operativi applicabili al controllo di freschezza o errore, non versione biologica |

Timestamps UTC ISO-8601 con timezone; input incompleti mantengono null e
limitazioni. Non inventare date o release per riempire campi obbligatori.
`content_hash` riguarda il payload immutabile, escludendo marker come cache hit,
timestamp di lettura e status tecnico mutabile. Conservare a parte l'hash dei
byte upstream quando disponibili e l'hash della rappresentazione normalizzata.

### Stati e assenza di evidenza

| Stato logico | Significato | Corrispondenza con gli stati attuali |
|---|---|---|
| `AVAILABLE` | Risposta biologica disponibile, contenuto e scope validati | ClinVar available; gnomAD observed e risposte di assenza con contesto; packet AVAILABLE |
| `NOT_QUERIED` | Nessun tentativo completato per quella query/fonte/versione | CACHE_MISS, voce assente; oggi alcuni wrapper restituiscono AVAILABLE con data=None |
| `NOT_FOUND` | Query supportata eseguita con successo e nessun record nello scope | ClinVar not_found, NO_RECORDS; non include errori, schema assente o dataset non caricato |
| `ERROR` | Acquisizione, parsing, validazione o storage falliti | ERROR, UNREACHABLE, NORMALIZATION_ERROR; conservare error code e retryability |
| `UNSUPPORTED` | Richiesta fuori capacità dell'adapter | NOT_SUPPORTED, unsupported; non trattarla come NOT_FOUND |

`STALE` deve essere riconoscibile come freshness (`FRESH`, `STALE`, `UNKNOWN`)
ortogonale al contenuto: un record può essere AVAILABLE e STALE, o NOT_FOUND e
STALE. Per compatibilità si può esporre anche status STALE con `data_status`
originario. L'ultimo tentativo ERROR non cancella l'ultimo dato AVAILABLE:
`last_attempt_status/error/checked_at` stanno sullo stato di recupero.

La mancata osservazione gnomAD conserva sempre copertura, AN, filtri e release;
non è un generico NOT_FOUND e non produce automaticamente AF=0 o un criterio
ACMG. I suoi stati specialistici restano nel payload. UNKNOWN mechanism non
equivale a meccanismo assente; NOT_FOUND non equivale a evidenza negativa.

### Snapshot e riproducibilità

**ESSENTIAL:** un consumo che richiede riproducibilità fissa un manifest
immutabile di record, anche per esiti NOT_FOUND rilevanti. Il manifest contiene
allele/annotation version, revisione di ogni fonte, snapshot gene2p, struttura
trascrizionale/reference digest, mapping e versioni degli algoritmi effettivamente
usati. Non contiene nomi di campione, GT o altri dati clinici.

Per gene2p si riusano `mechanism_snapshots/snapshot_records`. Per un insieme
biologico trasversale si propone, **in futuro nello stesso mechanisms.sqlite3**,
`biological_snapshots(snapshot_id PK, schema_version, created_at, manifest_json,
content_hash)` e `biological_snapshot_items(snapshot_id FK, role, record_ref,
content_hash, PRIMARY KEY(snapshot_id,role,record_ref))`. Non riutilizzare
`mechanism_snapshots.payload` per un formato diverso da GeneDiseaseMechanismResult.
I link a record in altri file sono riferimenti logici, verificati dal consumer,
non FK SQL cross-database. Gli artefatti Ensembl citati vanno conservati e
verificati; un manifest da solo non sostituisce i payload.

Un risultato locale futuro riporta snapshot ID, input selezionato e ruleset,
senza trasferire dati paziente nell'archivio biologico. La persistenza completa
delle valutazioni locali è **DEFERRED**, con task separato: il Calculator non
ha oggi il vecchio archivio operativo di classificazioni/replay. Gli archivi
Workbench storici restano conservati senza dipendenze riattivate.
Una lettura pinned non usa mai il record corrente o la rete al posto della
revisione mancante. Snapshot e payload referenziati non sono eliminabili per TTL.

## 6. Schemi logici proposti per categoria

Le strutture seguenti sono contratti futuri; nessun DDL viene eseguito da CACHE-01.
Campi JSON sono limitati a payload/manifest o dettagli poco interrogati;
soggetti, versioni, stati e date di lookup hanno colonne normali dove necessario.

### A. patients — ESSENTIAL

Conservare run store e history. Estendere in futuro i metadata con run_ref,
sample_ref, analysis_ref e mapping agli ID locali, mantenendo i vincoli attuali.
La relazione sample → analysis → call → allele continua a contenere genotype,
profondità, qualità e FORMAT originale. Le annotazioni restano in tabelle
distinte e vengono referenziate, senza copiare interi payload biologici nelle call.

Per preservare tutte le origini dello stesso allele, proporre nel **run store**
`variant_occurrences(occurrence_ref TEXT PK, source_id FK index_sources,
record_ordinal INTEGER, alt_index INTEGER, variant_id FK variants,
original_vcf_json TEXT, UNIQUE(source_id,record_ordinal,alt_index))`.
Associare in modo esplicito le call alle occorrenze di origine (link
`call_id/occurrence_ref` univoco), senza cambiare la semantica della call esistente.
Ordinale definito sul file con SHA-256 fissato; per TSV usare un tipo sorgente
esplicito. Indici source/ordinal e variant_id. In questo modo INFO/QUAL originali
non vengono persi per effetto della prima INSERT in variants.

Nessun nuovo dato anagrafico; i soli metadati esistenti restano nei depositi
campione, mai nei manifest delle fonti. Nessun TTL di eliminazione per input,
storia o misure campione. Non riscrivere ora VCF/JSON/CFG/samplesheet.

### B. variants_static — ESSENTIAL per contratto; condivisione fisica DEFERRED

Entità logiche: `GenomicAllele(allele_ref, tupla normalizzata, reference provenance)`,
`AnnotationVersion(annotation_version_ref, manifest)`,
`StaticAnnotation(shared_annotation_ref, allele_ref, annotation_version_ref,
feature/transcript context, consequence, fields_json, content_hash)` e
`OriginalAnnotationBinding(original_annotation_ref, release_id locale,
annotation_id locale, occurrence_ref, shared_annotation_ref facoltativo)`.

Le prime implementazioni usano le tabelle `variants`, `annotation_releases` e
`annotations` già presenti, aggiungendo identità/manifest e mantenendo il binding
al record importato. Predittori e annotazioni trascrittiche sono stabili soltanto
nel loro contesto di versione. ClinVar/AF importati da VEP rimangono nello
snapshot originale; non diventano automaticamente il dato dinamico corrente.

Se una misura successiva dimostra duplicazioni rilevanti fra run, valutare il
`store_kind=cohort` già supportato per la sola rappresentazione biologica
condivisa, con UNIQUE sui riferimenti logici e indici allele/version/transcript.
Questa opzione richiede un task dedicato; **non si introduce ora un DB globale
variants_static, né si svuotano gli indici delle run**.

### C. variants_dynamic — ESSENTIAL

Conservare i due DB attuali, aggiungendo **in ciascuno soltanto per la propria
fonte** una cronologia e uno stato di lookup. Nomi logici proposti:

| Entità proposta | Campi e vincoli |
|---|---|
| `evidence_revisions` | `record_id TEXT PK`, `allele_ref TEXT NOT NULL`, source/product/dataset, source_version nullable, source_record_id/version nullable, source_snapshot_ref, retrieved_at/source_updated_at, data_status, original_payload JSON, normalized_payload JSON, content_hash, parser_version, provenance JSON |
| `retrieval_state` | `query_key TEXT PK`, allele_ref/source/product/dataset/requested_version_scope, current_record_id FK revisions nullable, last_attempt_status, checked_at, expires_at/next_retry_at, error_code/details; query_key = hash della query qualificata |
| `refresh_leases` | `resource TEXT PK`, token, expires_at; stessa tecnica di lease già presente nei meccanismi, applicata localmente |

UNIQUE di revisione sul digest canonico di soggetto/fonte/versioni/hash,
non su una tupla con NULL la cui unicità cambi fra motori. Indici
`(allele_ref,source,source_version,retrieved_at)`,
`(source,source_record_id,source_record_version)` e
`retrieval_state(next_retry_at)`/`expires_at`. L'esatta query_scope include
assembly, dataset, tipo genomes/exomes/constraint e release richiesta; mai solo
il nome generico gnomAD. Una release sconosciuta è un contesto dichiarato
UNKNOWN con fingerprint, non una stringa che finge una release scientifica.

`evidence` e `frequencies` restano inizialmente proiezioni correnti compatibili
con i reader; cronologia e puntatore vengono pubblicati nella stessa transazione
locale. La duplicazione temporanea del piccolo payload corrente serve alla
compatibilità, non crea un secondo archivio autorevole. Eliminare tale proiezione
o sostituirla con vista è **DEFERRED**. Nessuna fusione di ClinVar e gnomAD è
necessaria: hanno policy e adapter distinti.

La lettura puntuale e batch deve poter scegliere contesto corrente, release
esatta o record/snapshot pinned. Il batch conserva ordine e un esito per ogni
input, deduplica le query senza perdere il mapping ai richiedenti. Si riusano i
batch SQL da 500 già implementati; l'acquisizione remota può inizialmente essere
una coda limitata di lookup puntuali. Non si presume un endpoint remoto bulk.

**DEFERRED:** prefetch ClinVar durante indicizzazione. Quando autorizzato, usare
gli alleli normalizzati unici della run e gli stessi lookup/stati/lease; non
aprire campioni, non bloccare la validità dell'indice per un errore di rete,
non creare record ClinVar per campione. Nessuna implementazione in CACHE-01.

### D. gene2p — ESSENTIAL

Conservare due ruoli fisici: `gene_phenotype` come indice delle fonti correnti,
`mechanisms` come archivio di evidenze, normalizzazione e storia. Non sono copie
intercambiabili. Le entità logiche si appoggiano alle strutture esistenti:

1. **Originale**: righe GenCC/G2P/dosage/constraint, manifest per fonte e
   `source_records` immutabili. Registrare upstream ID/version/data, ciò che
   l'importatore ha conservato e ciò che manca. Per i nuovi download mantenere
   un fingerprint/manifest per fonte; il dato scartato in passato resta ignoto.
2. **Normalizzazione**: `MechanismIdentity/MechanismEvidence`, mapping
   ontology, allelic requirement originale e normalizzato, scope esatto/mapped/
   gene-level/ambiguo, categorie direct/contextual/contradictory e relative
   versioni. Non fondere relazioni con sola coincidenza del simbolo o del nome
   malattia.
3. **Inferenza HELPER**: `GeneDiseaseMechanismResult` e
   `acmg_mechanism_assessment.assess`, collegate allo snapshot degli input.
   Conservare il risultato dell'assessment con versioni, supporting/conflicting
   evidence refs e rationale/basis. Un eventuale payload persistito va nello
   stesso mechanisms DB, separato dal raw e dalla matrice; identità hash di
   snapshot input + versione assessment/regole + contenuto, senza nuove regole.
4. **Confidence e motivazione**: distinguere la confidence G2P originale da
   `mechanism_confidence` HELPER e da stato/mancanze tecniche. Rappresentare
   LoF/GoF/DN/UNKNOWN tramite mapping ai valori esistenti
   LOSS_OF_FUNCTION/GAIN_OF_FUNCTION/DOMINANT_NEGATIVE/UNKNOWN; preservare
   MIXED/OTHER e conflitti esistenti senza ridurli forzatamente a un singolo valore.

Constraint gnomAD è contesto gene-level: non identifica da solo malattia o
meccanismo. GenCC porta validità gene-malattia; ClinGen Dosage HI/TS resta una
categoria distinta. Il contratto non promuove queste fonti a nuove asserzioni
dirette. Si conservano integralmente le regole attuali di normalizer/assessment
e del Calculator, comprese differenze di scope e requisiti di confidence.

**ESSENTIAL:** manifest fonte separati nel metadata/packet e invalidazione per
fingerprint, non per sola data globale dell'indice. Conservare i constraint
puntuali durante un rebuild solo se ancora compatibili col loro contesto;
altrimenti marcarli obsoleti e mantenere gli originali referenziati in archivio.
Coordinare rebuild e scritture puntuali per evitare che il replace perda
aggiornamenti concorrenti. Storico delle righe effettivamente consumate in
source_records; archiviazione integrale di ogni download è **RECOMMENDED**,
con retention e dimensioni valutate separatamente.

### E. gene_struct — ESSENTIAL per qualificazione; estensioni RECOMMENDED

Riutilizzare gli artefatti del provider, senza ridownload per variante.
Schema logico delle proiezioni, riferite allo stesso raw e digest:

| Entità | Chiave e contenuto |
|---|---|
| `GeneStructure` | gene context = gene/assembly/release; contig, start/end genomici, strand, gene version se presente, catalog complete e membri trascritto |
| `TranscriptStructure` | transcript_context_ref; gene context, accession/versione, coordinate, biotype, MANE/canonical/APPRIS, reference digest |
| `TranscriptExon` | transcript context + rank; exon ID/versione se disponibile, coordinate genomiche e mRNA, strand; l'exon ID da solo non identifica l'uso nel trascritto |
| `CodingSegment` | transcript context + ordine; exon ref, coordinate genomiche/mRNA/CDS, frame/phase con convenzione esplicita e indicazione source o derived |
| `UTRSegment` | transcript context + tipo 5prime/3prime + ordine; segmenti ricavati dai limiti CDS nel contesto mRNA, con versione della derivazione |
| `ReferenceSequence` | transcript context + tipo cDNA/CDS/protein + sequence digest; sequenza e provenienza già presenti nel bundle |

Non sono tabelle nuove obbligatorie: ordine, segmenti e UTR possono essere
proiezioni in memoria del JSON verificato. Esporre coordinate geniche, exon rank
e frame espliciti è **RECOMMENDED**; il dato derivato deve dichiarare algoritmo,
coordinate e riferimento, senza spacciarlo per field Ensembl originale.
Non attribuire CDS/phase a un noncoding o a una struttura incompleta.

Per i segmenti codificanti, definire il frame derivato come numero di basi CDS
precedenti modulo 3; se serve una phase GFF, dichiarare separatamente convenzione
e trasformazione. I due numeri non sono sinonimi. Queste proiezioni non cambiano
il calcolo PVS1 già implementato.

**RECOMMENDED:** estendere single flight ai chiamanti diretti e fra processi
solo dove misurato necessario, mantenendo pubblicazione atomica e ricontrollo
checksum; conservare nel manifest la revisione esatta. Conversione dei JSON in
un archivio SQL è **DEFERRED**: richiede un vantaggio concreto di query/concorrenza
e un solo passaggio di autorità, senza doppia persistenza. Si potrà usare il DB
biologico esistente; il provider e i contratti non richiedono oggi un nuovo DB.

## 7. Accesso, aggiornamento e concorrenza

### 7.1 Source Manager esistente e integrazione minima

Implementazione: [acmg_sources.py](../helper_next/src/helper_next/core/acmg_sources.py),
[source_registry.py](../helper_next/src/helper_variants/source_registry.py).
`SourceManager` delega già `transcript`, `gene_transcripts`, `population`,
`gene_disease`, `mechanism_records`, `mechanism_association_inventory`,
`ontology_registry`; `catalog` legge stato locale senza HTTP probe.
`source_registry` è un catalogo descrittivo, non un job scheduler né uno store
delle risposte. Alcune etichette di release sono descrittive/hardcoded.

**ESSENTIAL:** rendere coerenti esiti e policy nei punti già esistenti:

```text
Richiesta con identità e contesto/versione
  -> verifica input e policy (offline / corrente / pinned)
  -> lettura puntuale o batch della cache competente
  -> restituzione hit oppure decisione di refresh
  -> acquisizione mediante provider esistente, fuori transazione SQL
  -> validazione, pubblicazione atomica e aggiornamento stato
  -> evidenze + provenance + freshness al consumer
```

Patients e static restano nelle query dello store, con binding al campione.
Source Manager non deve inghiottire repository clinici o riscrivere le query
SQL. Per ClinVar bastano deleghe specifiche a `cached_evidence/lookup_variant`
quando un consumer condiviso le richiede; per gnomAD riusare
`population/cached_contexts`. Il batch locale esistente non va sostituito con
N chiamate puntuali. Il resolver mechanism continua a coordinare la propria
cache sopra Source Manager; evitare un ciclo inverso SourceManager → resolver
→ SourceManager. Nessun `CacheProvider` universale o service locator aggiuntivo.

**ESSENTIAL:** correggere in un futuro task l'ambiguità AVAILABLE con data=None
di `population/transcript` e distinguere offline/miss/error da assenza biologica.
La normale apertura del dettaglio deve poter riusare ClinVar fresco; il refresh
forzato diventa una scelta esplicita. `CACHE_ONLY` è una policy di acquisizione
senza rete; l'assenza totale di scritture va richiesta separatamente usando i
reader realmente read-only. `SNAPSHOT` deve essere senza refresh e senza
sostituzione della revisione richiesta.

**ESSENTIAL:** Source Manager restituisce evidenze e condizioni tecniche.
Normalizzazione/assessment biologici restano nei moduli esistenti versionati;
criteri, strength e decision tree restano in `pvs1/` e nei futuri moduli ACMG.
Nessun cambiamento alle funzioni PVS1, nessuna dipendenza dal vecchio valutatore.

### 7.2 Policy differenziate per fonte — ESSENTIAL

Le durate proposte sotto sono scelte operative iniziali, non attestazioni sulla
validità scientifica delle evidenze. I default attuali restano il punto di
partenza ove non c'è una release verificabile.

| Fonte / dato | Hit e obsolescenza proposti | Refresh controllato |
|---|---|---|
| ClinVar aggregate per allele | Mantenere 7 giorni positivo, 1 giorno NOT_FOUND come default; confrontare anche versioni record/fingerprint. Nessuna release globale inventata da retrieved_at | Esplicito o su scadenza quando fetch ammesso; nuova revisione, preservando le precedenti. Dettagli aggiuntivi sono acquisizioni tracciate, non rete nascosta in lettura offline |
| gnomAD frequenze | Release esatta + prodotto e parser qualificati; niente TTL uniforme del dato fissato a release | Cambio release o correzione upstream identificata → nuovo contesto/fingerprint. Negativi biologici validi nella stessa release con copertura conservata; errori a retry breve. Etichetta hardcoded da verificare rispetto alla risposta |
| GenCC / G2P | Revisione record e manifest export; 7 giorni come controllo operativo iniziale degli export non versionati | Sincronizzazione nel workflow gene_phenotype, poi ricalcolo solo associazioni interessate. Rileggere lo stesso indice non ringiovanisce la fonte |
| ClinGen Dosage | Fingerprint export e data di valutazione per record; 7 giorni per controllo snapshot non versionato | Refresh dell'export separato dalla reinterpretazione; HI/TS e fonte coordinate restano espliciti |
| gnomAD constraint | Release propria distinta da frequenze; fino a qualificazione completa mantenere controllo a 30 giorni | Targeted fetch già previsto, se abilitato. Mai convertire la label v4.1.2 in release verificata senza prova |
| HPO / Orphadata / MONDO | Release o fingerprint del mapping; non lo stesso TTL biologico degli alleli | HPO/Orphadata via workflow indice; MONDO tramite registry pinned con fingerprint. Un cambio mapping invalida la vista derivata, non gli originali |
| gene2p derivata | Freschezza dipende da versioni normalizer/assessment/registry e revisioni delle fonti | Riutilizzare resolver, TTL per fonte e lease. NO_RECORDS 1 ora, errore 60 s come default già presenti; non trasformare ricalcolo locale in sync remoto |
| gene_struct | Nessun TTL per un artefatto assembly/accession.version/release verificato | Recuperare solo se assente o esplicitamente invalido; nuova release in nuova chiave. Errori temporanei 30 s nel wrapper attuale; release non disponibile non diventa latest |
| Annotazioni VEP originali / input run | Nessun TTL distruttivo | Nuova annotazione crea nuova versione; l'originale resta attribuibile al file sorgente |

### 7.3 Cache miss, errori, batch e offline — ESSENTIAL

Su hit controllare identità, contesto di versione, integrità e freshness prima
del riuso. Su miss senza fetch restituire NOT_QUERIED, non NOT_FOUND. Su stale
offline restituire l'ultimo record con indicazione STALE e limitazioni; il
consumer decide se può valutarlo. Su snapshot pinned il dato resta quello
storico anche se la fonte corrente è cambiata.

Il refresh acquisisce fuori dalla transazione, valida e pubblica in blocco
revisioni/puntatori compatibili. Se fallisce, mantiene l'ultimo dato e registra
il tentativo/error code/retry time. Non avanzare retrieved_at per tentativi
falliti o semplici riletture. Un errore di scrittura non va presentato come
persistenza riuscita: il risultato può essere utilizzabile nel processo, con
limite esplicito alla riproducibilità finché non è salvato.

Per batch: raggruppare per fonte/prodotto/release, deduplicare allele_ref,
leggere prima in SQL, recuperare solo mancanti/scaduti ammessi, salvare piccoli
blocchi con esiti per elemento e checkpoint. Un errore su un elemento non deve
trasformare tutto il batch in NOT_FOUND. Il bulk mechanism già presente resta
il riferimento per checkpoint e conservazione di snapshot completi.

Per rate limiting: mantenere una coda limitata per host/fonte, inizialmente
un'acquisizione concorrente per fonte nel worker, con timeout/budget batch.
I retry HTTP esistenti sono limitati ma troncano Retry-After: il futuro contratto
deve rispettare la scadenza richiesta dal server, anche rinviando il job invece
di dormire a lungo. Backoff limitato con jitter per errori retryable; nessun
retry automatico indefinito per input invalido, schema incompatibile o 4xx
permanente. Coordinare il budget anche fra processi se il deployment li usa;
non inventare quote upstream numeriche non verificate.

### 7.4 Concorrenza e integrità — ESSENTIAL

- SQLite mantiene un writer per file: transazioni brevi, timeout espliciti,
  FK abilitate su ogni connessione mutante. WAL dove già previsto e sui DB
  locali mutabili dopo verifica del filesystem; WAL non sostituisce la lease.
- Single flight per `(fonte,query qualificata)` con ricontrollo dopo il lock.
  Riutilizzare il modello `mechanism_refresh_leases` nei DB dinamici; token del
  proprietario, scadenza e rinnovo se il job dura più della lease. Non chiamare
  la rete mantenendo una transazione SQL aperta. Unicità del record impedisce
  comunque doppie revisioni identiche.
- Rileggere/verificare token e contesto prima della pubblicazione; un worker
  scaduto non deve sovrascrivere un puntatore più recente. Liberare solo la
  lease del proprio token. Recuperare lease scadute dopo crash.
- Il rebuild gene_phenotype e il fetch constraint richiedono lo stesso lock di
  pubblicazione fra processi, indipendente dall'inode sostituito; mantenere
  validi i vecchi reader e non perdere scritture nella finestra di replace.
- Nessuna transazione atomica garantita fra file SQLite separati e JSON.
  Pubblicare prima i record immutabili, poi il manifest verificato. Un manifest
  con dipendenze mancanti è incompleto e non deve apparire riproducibile.
- Refresh non cancella snapshot. Retention/garbage collection sono **DEFERRED**;
  richiedono verifica di tutti i riferimenti, backup e una policy esplicita.

## 8. Organizzazione fisica proposta

| Categoria / archivio | Scelta | Motivazione e priorità |
|---|---|---|
| patients + static originale | Conservare SQLite per run e history separata; future estensioni di identità/origine | Campione e annotazioni già distinti in tabelle; accesso rapido e ricostruzione da VCF, nessun trasferimento inutile. **ESSENTIAL** |
| static condivisa fra run | Nessun nuovo DB adesso; possibile uso store cohort solo dopo misura | Identità/manifest completi prima della deduplicazione; migrazione utile solo con vantaggio dimostrato. **DEFERRED** |
| ClinVar | Conservare DB; aggiungere revisioni/stato/lease | Fonte con refresh temporale e history oggi assente. **ESSENTIAL** |
| gnomAD frequenze | Conservare DB; aggiungere contesto release esatta e revisioni/stato/lease | Evitare collisioni di release e preservare evidenze/coverage. **ESSENTIAL** |
| gene2p fonti | Conservare gene_phenotype; manifest per fonte e pubblicazione coordinata | Efficiente indice bulk ricostruibile; non deve assumere il ruolo di archivio storico. **ESSENTIAL** |
| gene2p storia e normalizzazione | Riutilizzare mechanisms e registry; eventuali manifest biologici nello stesso file | Già transazionale, versionato e immutabile; evitare nuovi archivi. **ESSENTIAL** |
| gene_struct | Conservare artefatti JSON Ensembl separati e provider; qualificazione/snapshot comuni | Accesso per chiave e sequenze già verificati, nessun beneficio immediato da riscrittura SQL. **ESSENTIAL** per riuso; conversione SQL **DEFERRED** |
| liftover, PanelApp | Conservare archivi tecnici attuali | Responsabilità e policy proprie; una fusione richiederebbe riscrivere accessi senza vantaggio dimostrato. **RECOMMENDED** |

Non esiste una corrispondenza categoria=file: due categorie condividono il run
store e gene2p usa due archivi con ruoli distinti. Gli archivi pubblici non
contengono campioni o identità cliniche. Non serve una nuova directory/cache
per ciascuna categoria.

## 9. Compatibilità futura PostgreSQL

### 9.1 Contratti trasferibili — ESSENTIAL nella progettazione

| SQLite / situazione attuale | Contratto logico / futura conversione |
|---|---|
| PK INTEGER implicita rowid | Conservare numero per compatibilità locale, trasferibile a BIGINT; tutte le relazioni condivise usano anche ID logici TEXT/UUID. Nessuna dipendenza dall'ordine di assegnazione |
| TEXT per ID, CURIE e hash | TEXT o UUID solo per UUID validi; preservare bytes e prefissi dei digest |
| Posizioni/rank/count INTEGER | BIGINT per coordinate/conteggi potenzialmente grandi; rank INTEGER, CHECK positività coerenti |
| Boolean INTEGER 0/1 | BOOLEAN con conversione esplicita, distinguendo null da false |
| REAL per frequenze/metriche | DOUBLE PRECISION con finite-check; niente NaN/Infinity nei JSON o nei digest |
| Timestamp TEXT / scadenze epoch REAL | TIMESTAMPTZ per istanti; conversione UTC esplicita, durata numerica separata. Conservare originali necessari ai digest storici |
| metadata/payload/document JSON in TEXT | TEXT canonico immutabile per contenuti hashati; JSONB opzionale come proiezione interrogabile. Hash mai calcolato dal rendering JSONB |
| COLLATE NOCASE | Colonna normalizzata per ricerche, regole esplicite indipendenti dalla collation locale; conservare etichette originali |
| NULL / stringhe vuote | Mappatura campo per campo, senza convertire indiscriminatamente i valori nei payload storici. UNIQUE e query_scope definiti anche con release sconosciuta |

FK restano entro il database/store. I collegamenti fra archivi usano record_ref,
hash e manifest con verifica applicativa. Un consolidamento futuro in PostgreSQL
potrà aggiungere FK interne al nuovo confine solo dopo verifica di orfani,
cardinalità e semantica; nessun vincolo cross-file fittizio in SQLite.

Indici prioritari: quelli reali censiti sopra, più gli indici proposti su
allele/fonte/versione, scadenza retry, transcript context ed association_ref.
FK non indicizzate richiedono valutazione dei piani sulle query effettive,
non l'aggiunta indiscriminata di indici a ogni campo JSON.

### 9.2 Dipendenze SQLite realmente presenti

| Codice / costrutto | Lavoro necessario solo al momento della migrazione — DEFERRED |
|---|---|
| `store.py`, gene_phenotype, gnomAD, liftover: `INSERT OR IGNORE/REPLACE` | Rendere esplicita la politica di conflitto. REPLACE può avere effetti delete/insert e non è sinonimo universale di UPDATE |
| `store.connect`, `MechanismStore.connect`: PRAGMA foreign_keys/busy_timeout/journal_mode/user_version, sqlite3.Row, executescript, placeholder `?` | Tradurre gestione connessione/schema/parametri nel task di migrazione; niente adapter oggi |
| `MechanismStore.refresh_lock/publish`, history e ontology: `BEGIN IMMEDIATE` | Transazioni e lock di riga/advisory o lease atomiche nel nuovo motore; preservare ricontrollo token e immutabilità |
| Trigger `RAISE(ABORT,...)` su storico mechanism/ontology | Vincolo di immutabilità equivalente con privilegi/trigger PostgreSQL, verificato con test |
| `query.py`: json_extract/json_each, inclusi filtri liste/campi predittori; `acmg_ontology.py`: json_extract mapping_source | Query JSON/parametri riscritte puntualmente, oppure colonne estratte per i lookup frequenti |
| `query.py`: GROUP_CONCAT DISTINCT e aggregazioni con colonne non aggregate; `indexer._physical_run`: GROUP BY r.id con altre colonne | Aggregazioni esplicite, ordine deterministico e cardinalità dichiarata; non affidarsi alle permissività SQLite |
| gene_phenotype inventory/source records e mechanism bulk: ORDER BY rowid | Ordinamento tramite chiavi logiche/ordinal/timestamp e tie-breaker stabile |
| `mechanism_revision`, query priority fingerprint e rebuild con os.replace | Revisioni contenuto/manifest al posto di inode/mtime/WAL; swap di dataset transazionale invece di sostituzione del file |

Le query già parametrizzate e le funzioni di accesso esistenti costituiscono il
confine sufficiente. Tenere i nuovi contratti e le trasformazioni biologiche
fuori dalle peculiarità SQL, senza introdurre un framework multi-database.

### 9.3 Procedura futura — DEFERRED

Definire un task autonomo con backup verificato, blocco delle scritture e
inventario di file/schema/override. Esportare tabelle, ID, JSON canonici e
artefatti referenziati; caricare in staging con mapping degli ID locali se
necessario. Verificare conteggi per tabella/fonte/release, hash dei record e
snapshot, unicità, FK/orfani, semantica NULL/date e risultati delle query su
fixture rappresentative, incluse multialleliche e record obsoleti.
Confrontare esiti delle funzioni esistenti e del Calculator su input identici,
senza cambiare regole. Effettuare un solo cutover dopo verifica; conservare il
backup SQLite e il piano di rollback. Nessuna doppia scrittura operativa.

## 10. Problemi strutturali e interventi ordinati

| Problema verificato | Intervento futuro e componenti da riusare | Priorità |
|---|---|---|
| ID SQL e run_key nominali non identificano globalmente run/campioni | run_ref e mapping nelle strutture esistenti; distinguere history attempt/run fisica | **ESSENTIAL** |
| Build/contig e indel non sempre qualificati | Contratto normalizzazione con indexer e acmg_reference; scope locale se non verificato | **ESSENTIAL** |
| Prima origine VCF mantenuta in variants metadata; altre occorrenze possono andare perse nell'indice | Relazioni original occurrence/call nel run store; VCF sorgente sempre autorevole | **ESSENTIAL** |
| Release originale legata a run+digest file, manifest VEP incompleto | Separare original release, annotation_version_ref e shared annotation; preservare header e fallback dichiarati | **ESSENTIAL** |
| Stessi dati biologici annotati fra campioni/run | Riutilizzare subito tabelle e lookup già condivisi; deduplicazione fisica cross-run soltanto con manifest completo | **DEFERRED** per consolidamento fisico |
| ClinVar forzato sul dettaglio, lista con cache; merge/provenance differente | Lettura coerente e refresh esplicito usando provider/batch esistenti; originali VCF separati dalla revisione live | **ESSENTIAL** |
| Dynamic cache sovrascrivono la risposta precedente | Revisioni immutabili, head/stato separato e snapshot manifest | **ESSENTIAL** |
| ID dataset gnomAD non garantisce release esatta | Controllo reale release/fingerprint e query scope esplicito | **ESSENTIAL** |
| Metadata gene2p globali; etichette di versione non provate | Manifest per fonte, raw vs normalized vs inferred, limite storico dei campi scartati | **ESSENTIAL** |
| Rebuild gene_phenotype perde constraint puntuali e può concorrere con scritture | Pubblicazione coordinata e conservazione delle revisioni compatibili | **ESSENTIAL** |
| TTL e stati eterogenei, data=None dichiarata AVAILABLE | Contratto dati/freshness/last attempt senza falsa evidenza negativa | **ESSENTIAL** |
| Lock in memoria e retry locali non coordinano tutti i processi | Lease con token e budget per fonte; riusare pattern mechanism | **ESSENTIAL** per worker concorrenti |
| Source records e stato mechanism possono ripetere righe dell'indice | Conservare ruoli corrente/storico; eventuale compattazione solo dopo misura, senza cancellare originali referenziati | **DEFERRED** |
| Ensembl catalogo e bundle trascritto ripetono alcuni esoni | Mantenere catalogo completo e riferimento qualificato; riuso per chiave. Dedup dei piccoli payload solo se utile | **RECOMMENDED** per single flight, **DEFERRED** per riscrittura storage |
| Fingerprint da file/stat non sempre descrive modifiche WAL o contenuto | Token di revisione persistente/manifest per invalidazioni; preservare i cache derivati già presenti | **RECOMMENDED** |
| Schema migration differenti: metadata, PRAGMA e tabelle senza versione | Manifest di schema per store estesi e migrazioni locali esplicite; nessun coordinatore universale | **RECOMMENDED** |
| Snapshot crescenti e backup storici | Misurazione e retention referenziale con approvazione del task dedicato; nessuna pulizia automatica | **DEFERRED** |

## 11. Sequenza proposta dei task successivi

Questa sequenza è progettuale e non autorizza l'avvio dei task.

| Ordine / task proposto | Risultato concreto e dipendenze | Priorità / criterio di completamento |
|---|---|---|
| CACHE-02 — Identità e fixture dei contratti | Definire serializzazione/chiavi, tuple normalizzate e mapping legacy; fixture alias assembly/contig, indel in ripetizioni con/senza FASTA, multialleliche, run omonime, transcript.version e mapping ambiguo | **ESSENTIAL**; identità uguali solo quando dimostrate, nessuna variazione delle decisioni scientifiche |
| CACHE-03 — Stati, provenance e policy di lettura | Allineare risultati dei provider e Source Manager senza nuove interfacce; manifest per fonte/release; ripristinare riuso ClinVar nel dettaglio con refresh esplicito | **ESSENTIAL**; offline/cache-only non fa rete, miss distinto da errore/negativo, batch e dettaglio restituiscono provenance compatibile |
| CACHE-04 — Revisioni dinamiche e snapshot biologici | Estendere ClinVar/gnomAD nei rispettivi DB, migrando solo in task autorizzato con backup; manifest trasversali nel DB mechanism esistente | **ESSENTIAL**; refresh conserva la revisione precedente; pinned riproduce gli stessi payload e segnala dipendenze mancanti |
| CACHE-05 — Concorrenza e integrità delle fonti | Lease dinamiche, rate budget, publication lock per rebuild/constraint, fault handling e checkpoint | **ESSENTIAL** quando si abilitano worker/batch concorrenti; due richieste equivalenti non duplicano acquisizione, crash non corrompe head/storico |
| CACHE-06 — Originali run e static contracts | Aggiungere mapping logici/occurrences e manifest annotativi negli indici; nessun riassetto dei VCF o regole di parsing scientifico | **ESSENTIAL**; ricostruzione dell'origine e del binding campione/allele/annotazione senza perdita |
| CACHE-07 — Gene2p e gene_struct, esposizione coerente | Per-source release manifests e collegamenti assessment/snapshot; proiezioni coordinate/rank/UTR/frame dal provider qualificato; mantenere normalizer, assessment e PVS1 | **ESSENTIAL** per provenance e scope; **RECOMMENDED** per nuovi campi derivati. Verifiche sugli stessi input devono preservare gli esiti scientifici |
| CACHE-08 — Prestazioni e consolidamento misurato | Misurare hit/miss, richieste evitate, dimensioni e tempi; valutare cohort static e dedup dei payload | **RECOMMENDED** per misure; **DEFERRED** per trasferimenti di dati senza vantaggio dimostrato |
| CACHE-09 — Prefetch ClinVar in indicizzazione | Coda di alleli unici sui contratti già consolidati, errori separati dal completamento indice | **DEFERRED**; nessun fetch anticipato implementato da questo audit |
| Eventuale migrazione PostgreSQL | Preflight, staging, confronto/cutover/rollback descritti sopra, senza doppia persistenza | **DEFERRED**, nessun adapter o driver ora |

I task implementativi dovranno riusare i test già presenti in
`helper_next/tests/test_variant_store.py`, `test_variant_indexer.py`,
`test_clinvar.py`, `test_gnomad_frequency.py`, `test_gene_phenotype.py`,
`test_source_registry.py`, `test_prioritization.py`, `test_acmg_context.py`,
`test_acmg_mechanisms*.py`, `test_acmg_mechanism_assessment.py`,
`test_acmg_pvs1.py` e `tests/test_pvs1_*.py`, aggiungendo verifiche sui nuovi
comportamenti effettivi. Nessun nuovo test speculare alla sola descrizione è
richiesto in CACHE-01.

## 12. Verifiche e limiti di CACHE-01

Verifica statica dei contratti contro DDL, PK/UNIQUE, indici e funzioni realmente
presenti nei file citati; distinzione esplicita fra stato attuale ed entità
proposte. Il documento non presume tabelle o servizi recuperati da documenti
storici dopo la loro rimozione. Nessun conteggio di dati operativi ripetuto.

Unico output: `docs/CACHE_01_ARCHITECTURE.md`. Nessuna modifica a codice,
database, schemi, cache, dati o criteri PVS1/ACMG. Test applicativi e servizi
biologici live non eseguiti: il cambiamento è esclusivamente documentale.
La progettazione non garantisce di recuperare versioni o colonne upstream mai
conservate; quelle lacune devono rimanere dichiarate. Nessun task successivo
avviato.
