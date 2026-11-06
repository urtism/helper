# CACHE-07 — ClinGen VCEP Local Dataset

Data: **2 novembre 2026**. Implementazione limitata a dataset, reader e inventario
amministrativo. Nessuna integrazione in prioritizzazione, Variant Browser,
SourceManager ACMG, Gene2P o motore ACMG/PVS1.

## Audit preliminare

Letti CACHE-01, CACHE-02, CACHE-04, CACHE-05, CACHE-06A e CACHE-06B prima delle
modifiche, insieme ai moduli richiesti e ai componenti Data Sources. Le modifiche
preesistenti nel working tree sono conservate. Nessun database esistente è stato
modificato durante l'audit.

| Componente | Risultato e riuso |
| --- | --- |
| `clinvar_local.py` | Snapshot immutabili, coppia atomica CURRENT/BACKUP, lock e protezione dei reader. Riutilizzati `_publication_lock`, `_roles`, `_select_roles`, `_retirement_guards(validate=False)`, `_reader_owner`, `_snapshots`, fsync, pulizia dei ruoli e helper hash/JSON/data. La validazione biologica degli snapshot rimane specifica di ciascuna fonte. Nessuna modifica al modulo ClinVar. |
| `clinvar_adapter.py` | Adapter dei consumer ClinVar, lasciato invariato. Nessuna conversione delle assertion ERepo in aggregati ClinVar. |
| `biological_identity.py` | Contratto ga2 verificato; non serve un altro normalizzatore. Questo task conserva HGVS accession/versione esatti e offre solo una traduzione sintattica delle SNV genomiche primarie in HGVS. Non crea identità ga2 o equivalenze per indel. |
| `liftover.py` | Riutilizzati vocabolario assembly/cromosomi e accession primarie. Nessuna chiamata di liftover. |
| `source_registry.py` | Voce amministrativa `clingen_vcep_variants` già esistente, ora alimentata dal nuovo reader. Il catalogo storico del browser resta invariato. |
| API/frontend Data Sources | Inventario, dettagli e rendering dei metadati già disponibili. Una sola verifica API aggiunta; nessuna nuova route o azione di aggiornamento. |
| `gene_phenotype.py` / Gene2P | GenCC può contenere submitter ClinGen; `clingen_dosage` conserva HI/TS. Sono prodotti diversi dalle classificazioni VCEP. Nessun importatore ERepo preesistente; nessuna cache Gene–Disease, Dosage o CSpec duplicata. |
| Matching ClinVar/ClinGen | ClinVar locale abbina alleli e conserva SCV/submitter/review. Non costituisce un indice ERepo UUID–malattia–panel. Il nuovo reader cerca identificativi ed espressioni esatti; una ricerca per gene è un inventario, non una prova d'identità della variante. |

## Fonte e verifica effettiva

Fonte primaria: [ClinGen Evidence Repository](https://erepo.clinicalgenome.org/evrepo/),
con export collegato nei [download ufficiali ClinGen](https://search.clinicalgenome.org/kb/downloads).

| Endpoint verificato | Esito |
| --- | --- |
| [TSV completo](https://erepo.clinicalgenome.org/evrepo/api/summary/classifications/download) | HTTP 200, 20 colonne, 13.682 righe dati. |
| [Parametro CSV](https://erepo.clinicalgenome.org/evrepo/api/summary/classifications/download?type=csv) | HTTP 200, ma il contenuto osservato è ancora TSV. Stessi UUID e valori del TSV, ordine differente. L'importatore usa il TSV verificato, senza assumere il formato dal suffisso. |
| [Documentazione API](https://erepo.clinicalgenome.org/docs/cg-erepo/) | Disponibile come app JavaScript; letti anche i contenuti pubblici di `index.md?import` ed `endpts.md?import`. Alcuni esempi nella documentazione sono storici. |
| [Summary bulk](https://erepo.clinicalgenome.org/evrepo/api/summary/classifications?pgSize=20000&pg=1) | HTTP 200, 13.675 record, tutti associabili per UUID al TSV. Espone `docVersion`, `versionsList`, `geneNcbiId`, `affiliationId`, `PCERDocID`, assenti nel TSV. Nessun contenuto sperimentale dettagliato acquisito. |

Header TSV realmente osservato, mantenuto in `COLUMNS` e nei manifest:

```text
Variation
ClinVar Variation Id
Allele Registry Id
HGVS Expressions
HGNC Gene Symbol
Disease
Mondo Id
Mode of Inheritance
Assertion
Applied Evidence Codes (Met)
Applied Evidence Codes (Not Met)
Summary of interpretation
PubMed Articles
Expert Panel
Guideline
Approval Date
Published Date
Retracted
Evidence Repo Link
Uuid
```

Il TSV rimane autorevole per le assertion. Il summary bulk integra soltanto i
metadati assenti, evitando migliaia di richieste puntuali. `download-build`
effettua una richiesta TSV e pagine summary da 20.000 record: il dataset attuale
richiede una sola pagina summary. Se il server limita/tronca le pagine o cambia
il dataset durante l'acquisizione, l'importazione verifica la copertura di tutti
gli UUID non ritirati e fallisce anziché pubblicare un arricchimento parziale.

Il join richiede UUID esatto e concordanza di CAid, Variation ID, gene, MONDO,
malattia, ereditarietà, panel, titolo, classificazione, date, stato di ritiro,
HGVS, criteri Met/Not Met e testo interpretativo. Il TSV appiattisce gli spazi
del testo: il confronto del testo ignora solo whitespace; l'originale TSV viene
conservato senza riscriverlo. Due titoli sorgente contengono virgole interne
(per esempio `ETHE1, EX4DEL`): l'array HGVS del summary viene confrontato nella
forma concatenata originale. Soltanto espressioni HGVS con accession/versione
sono indicizzate; i titoli liberi restano nell'originale.

Sette assertion con `Retracted=true` sono presenti soltanto nel TSV e vengono
conservate con versione sconosciuta. Altre 207 righe hanno stato di ritiro
vuoto: rimane `null`, senza convertirlo in `false`. `versionsList` documenta
le versioni note; non rappresenta l'acquisizione del contenuto storico di tali
versioni. SCV assente da entrambe le fonti selezionate: sempre `null`.
Non si deducono versioni dalle date, dal link CSpec o dal testo narrativo.

I [termini ufficiali ClinGen](https://www.clinicalgenome.org/docs/terms-of-use/)
distribuiscono i contenuti curati con CC0 1.0 e richiedono, quando appropriato,
attribuzione a ClinGen e data di accesso. Il manifest conserva licenza, URL dei
termini, attribuzione e date di download. Non viene utilizzato il logo ClinGen.

## Persistenza e reader

Modulo: `helper_next/src/helper_variants/clingen_vcep_local.py`.
Database predefinito:
`$XDG_DATA_HOME/helper_variants/clingen_vcep_local.sqlite3`, con fallback a
`~/.local/share/helper_variants/clingen_vcep_local.sqlite3`.
Override: `HELPER_CLINGEN_VCEP_LOCAL_DB`.

| Tabella | Contenuto |
| --- | --- |
| `assertions` | PK UUID originale; versione documentale nullable, CAid, Variation ID, gene/ID NCBI, malattia/MONDO/MOI, classificazione e panel/affiliation, date, ritiro a tre stati, link originale, sintesi, PMID, versioni note, SHA-256 del contenuto, intera riga TSV originale e metadati summary selezionati. |
| `hgvs` | Alias HGVS esatti e accession/versione, collegati all'assertion. Nessuna conversione automatica di indel o titoli in alleli. |
| `criteria` | Codice originale, incluso suffisso di strength, ordinalità e stato `Met`/`Not Met`. Nessuna reinterpretazione o applicazione ACMG automatica. |
| `metadata` | Manifest `release`: schema 1, fonte, snapshot, fonti con SHA-256/dimensioni/acquisizione, colonne, conteggi, validazione, licenza e limiti. |

Gli indici servono UUID, CAid, Variation ID, gene, malattia, panel/affiliation,
HGVS e criteri. Le ricerche combinano i filtri con AND e non fondono assertion
della stessa variante in contesti differenti. Paginazione esplicita, limite
1–10.000, ordinamento stabile per UUID. La lettura di una pagina carica HGVS e
criteri con query batch da 500 UUID: nessuna query per ciascuna assertion.

```python
from helper_variants.clingen_vcep_local import ClinGenVCEPLocal

with ClinGenVCEPLocal() as reader:
    manifest = reader.release()
    assertions = reader.query(variation_id=12982)
    exact = reader.query(hgvs="NM_004333.4:c.740T>C")
    context = reader.query(caid="CA281951", disease_id="MONDO:0021060")
    genomic = reader.lookup_genomic("GRCh38", "7", 140801532, "A", "G")
```

Ogni record restituisce snapshot, versione/disponibilità, originale e link
canonico ufficiale ERepo; il link originale dell'export è conservato separatamente.
La query HGVS supporta espressioni indicizzate esatte anche per indel; la query
genomica supporta solo SNV nucleari primarie con assembly esplicito. Nessun
liftover, matching per gene/rsID, equivalenza HGVS approssimativa o verifica REF
inventata. `reference_status=UNVERIFIED` è esplicito. Input genomici non supportati
restituiscono `UNSUPPORTED`; assenza dell'espressione esatta nello snapshot valido
restituisce `NOT_FOUND`. Errori di apertura/schema sono eccezioni, mai assenza.
Più assertion corrispondenti vengono tutte restituite, senza scegliere un panel.

Le query includono i record ritirati per impostazione predefinita, conservandone
lo stato. `include_retracted=False` esclude solo i `true`, mantenendo gli
sconosciuti con `null`: il filtro non certifica che essi siano attivi.

## Costruzione e gestione snapshot

```bash
PYTHONPATH=helper_next/src python -m helper_variants.clingen_vcep_local \
  download-build /tmp/erepo-sources

PYTHONPATH=helper_next/src python -m helper_variants.clingen_vcep_local \
  --database /percorso/clingen_vcep_local.sqlite3 \
  build /tmp/erepo-sources/erepo.tsv --summary /tmp/erepo-sources/erepo-summary.json

PYTHONPATH=helper_next/src python -m helper_variants.clingen_vcep_local info
PYTHONPATH=helper_next/src python -m helper_variants.clingen_vcep_local \
  query --variation-id 12982
PYTHONPATH=helper_next/src python -m helper_variants.clingen_vcep_local rollback
PYTHONPATH=helper_next/src python -m helper_variants.clingen_vcep_local cleanup
```

`build` senza `--summary`, oppure `download-build --tsv-only`, conserva tutte le
assertion TSV con versioni/ID aggiuntivi sconosciuti. Nessun fetch implicito nel
reader, inventario o costruzione da file locali.

La costruzione usa staging sul filesystem degli snapshot, controllo header e
righe, UUID univoci, tipi/date/boolean, coerenza delle fonti, foreign key e
`integrity_check`, quindi verifica tramite il reader. File nuovi immutabili e
selezione atomica CURRENT/BACKUP riusano il protocollo ClinVar, in una directory
VCEP separata. Un precedente BACKUP con reader attivi impedisce il ritiro senza
cambiare i ruoli. Il reader fissa uno snapshot per tutta la sua durata.

Lo snapshot identifica schema e SHA-256 dei file effettivamente acquisiti,
non una release scientifica globale. Anche l'ordine delle righe fa parte dei
byte acquisiti. Le fonti non pubblicano un checksum verificato in questo
workflow: i manifest distinguono i digest locali da una certificazione upstream.

`rollback` scambia solo i ruoli; `cleanup` recupera snapshot/staging abbandonati
senza forzare reader, builder o file estranei. Dopo un'interruzione successiva al
commit i ruoli rimangono coerenti; gli eventuali file non selezionati si ritirano
con `cleanup` o alla successiva pubblicazione. Nessuno scheduler/checker/update
supervisionato VCEP aggiunto. Data Sources espone `update_supported=false`.

## Importazione reale e verifiche

Download e costruzione reali eseguiti in `/tmp/cache07-downloaded/`; ricevuta
`/tmp/cache07-downloaded-result.json`, verifica completa e misura locale in
`/tmp/cache07-real-verification.json`. Nessun XML o documento di evidenze
sperimentali dettagliate scaricato.

| Misura | Risultato |
| --- | ---: |
| Assertion / UUID distinti | 13.682 |
| Assertion con versione documentale verificata | 13.675 |
| Panel / geni / MONDO distinti | 46 / 174 / 126 |
| Assertion con ID NCBI gene | 13.475 |
| HGVS indicizzati | 431.441 |
| Codici Met + Not Met | 130.175 |
| Ritirate / stato di ritiro sconosciuto | 7 / 207 |
| CAid assente / Variation ID assente | 44 / 779 |
| SQLite completo | 201.416.704 byte, circa 192 MiB |
| Lookup HGVS, mediana di 100 ripetizioni a cache calda | 0,146 ms |
| `integrity_check` / errori foreign key | `ok` / 0 |

Misure locali, senza una garanzia universale di latenza. Il controllo completo
ha letto tutte le assertion con il reader e verificato unicità e conteggi.
Il piano SQL usa `hgvs_expression`. Le fixture congelate in
`helper_next/tests/fixtures/clingen_vcep_local/` contengono sette assertion
ufficiali, sei summary disponibili e provenance/checksum; comprendono contesti
distinti della stessa variante, ritiro, dati mancanti e titolo con virgola.

Test specifici: conservazione originale, versioni e criteri, matching esatto,
assembly distinti e input non supportati, batch SQL, file read-only, inventario
e API Data Sources, checksum/righe/header invalidi, fonti discordanti o
incomplete, errori prima/dopo commit, protezione reader, retention e rollback.
Le regressioni Data Sources/ClinVar includono Chrome con API simulate. Le
limitazioni socket della sandbox hanno richiesto il rilancio della suite API
fuori sandbox; nessuna rete biologica nei test automatici.

Esito finale della suite mirata: **180 passati**, inclusi **47 test VCEP**.
Warning preesistente di deprecazione `python_multipart`. Sintassi Python e
`git diff --check` superati.

```bash
python -m pytest -q -o faulthandler_timeout=20 \
  helper_next/tests/test_clingen_vcep_local.py \
  helper_next/tests/test_data_sources.py \
  helper_next/tests/test_data_sources_browser.py \
  helper_next/tests/test_clinvar_update.py \
  helper_next/tests/test_clinvar_integration.py \
  helper_next/tests/test_source_registry.py \
  helper_next/tests/test_clinvar_local.py --tb=short
```

Installazione reale completata e verificata nel percorso predefinito
`/home/jarvis/.local/share/helper_variants/clingen_vcep_local.sqlite3`.
Il registry amministrativo la riconosce come installata. Snapshot:
`erepo-sha256:611c8dcc5900ee69f385fbe7961e5c943d4ccdc6f6872dbc95c40ea84675951f`.
Ricevuta completa: `/tmp/cache07-installation.json`.
Costruzione/validazione e verifica finale: 9,53 s; massimo RSS del processo
345.036 KiB. Si tratta di una prima installazione: CURRENT presente, BACKUP
assente; il prossimo build riuscito conserverà CURRENT come BACKUP.
Non sono stati sostituiti database esistenti o modificati ClinVar/Gene2P.

Nel controllo più ampio `test_variant_package_limits_helper_runtime_imports_to_existing_ga2_reader`
fallisce per cinque import `helper_next.core` già presenti in `source_registry.py`
da CACHE-06A: il test richiede ancora la sola dipendenza ga2 di CACHE-05.
Il nuovo modulo non aggiunge dipendenze dirette a `helper_next`; il test e i
consumer del viewer sono lasciati invariati. Un controllo ClinVar sui processi
non ispezionabili ha avuto un errore transitorio nella prima esecuzione estesa;
il modulo ClinVar completo è passato nei rilanci mirati e finali.

Nessuna suite integrale estranea al perimetro o esecuzione Nextflow effettuata.
