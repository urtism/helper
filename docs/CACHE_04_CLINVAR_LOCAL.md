# CACHE-04 — ClinVar locale

Data: **30 ottobre 2026**. Implementazione indipendente dal provider attuale.
Nessuna modifica a prioritizzazione, API, frontend, Source Manager, ACMG o PVS1;
nessuna lettura/scrittura/migrazione di `clinvar_evidence.sqlite3`.

## 1. Audit e fonti effettivamente verificate

Letti CACHE-01, CACHE-02/02.1 e CACHE-03; ispezionati `helper_variants/clinvar.py`,
`query.py`, `helper_prioritization/engine.py`, `helper_next/api/variants.py`,
`core/biological_identity.py` e la sezione ClinVar di `variant-browser.js`.
Le modifiche preesistenti del working tree restano estranee a questo task.
Il perimetro di questo task prevale sulle proposte storiche di CACHE-01 che
prevedevano una diversa estensione delle cache dinamiche.

Fonti primarie:

- [NCBI variant_summary.txt.gz](https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz).
- [NCBI submission_summary.txt.gz](https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/submission_summary.txt.gz).
- [README del formato](https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/README),
  consultato insieme alle intestazioni dei file scaricati, non usato come schema immutabile.
- [Identificativi](https://www.ncbi.nlm.nih.gov/clinvar/docs/identifiers/),
  [review status](https://www.ncbi.nlm.nih.gov/clinvar/docs/review_status/),
  [collegamenti](https://www.ncbi.nlm.nih.gov/clinvar/docs/linking),
  [campi di ricerca](https://www.ncbi.nlm.nih.gov/clinvar/docs/help/).

I due archivi sono stati scaricati integralmente una volta ciascuno. Sono
disponibili checksum MD5 ufficiali: il loro formato effettivo contiene il
percorso assoluto NCBI, non necessariamente il solo nome del file. Si calcolano
anche SHA-256 e dimensione locale; la lettura gzip fino a EOF verifica CRC e trailer.
La documentazione descrive export settimanali e archivi mensili; nessun numero
di release comune viene dedotto dalle date HTTP.

| File acquisito | Dimensione compressa | MD5 ufficiale | HTTP Last-Modified |
|---|---:|---|---|
| variant_summary.txt.gz | 456.577.488 byte | c79b46f3c02ef544608e0d9a83cac46e | Mon, 26 Oct 2026 13:50:58 GMT |
| submission_summary.txt.gz | 404.887.032 byte | b7f5d29bdc0fdace0cdfb7c8f2e23ca1 | Sun, 25 Oct 2026 03:44:46 GMT |

`Last-Modified` è metadato HTTP, **non una data di pubblicazione certificata**.
La release locale è uno **snapshot composito** identificato dal digest dei due
SHA-256, con manifest separati, colonne originali, URL, checksum, acquisizione e
importazione. `common_release_verified=false`. File successivi possono differire:
`check-updates` confronta esplicitamente i singoli checksum remoti, senza scheduler.

Sono state verificate 43 colonne in variant_summary e 16 in submission_summary.
Tra le colonne più recenti, assenti dalla descrizione principale del README,
figurano `SCVsForAggregateGermlineClassification`,
`SCVsForAggregateSomaticClinicalImpact`,
`SCVsForAggregateOncogenicityClassification` e
`ContributesToAggregateClassification`: vengono tutte conservate.
VCF aggiuntivi non necessari: `PositionVCF`, `ReferenceAlleleVCF` e
`AlternateAlleleVCF` forniscono già la rappresentazione VCF left-shifted.
Nessun XML o dataset di terze parti acquisito.

## 2. Matrice HELPER → ClinVar

`VS` indica variant_summary; `SS` submission_summary. Le stringhe biologiche e le
date restano nel formato originale. I sentinel documentali `-`, `na` e stringa
vuota diventano NULL nei campi estratti; le coordinate originali e i dettagli
accessori conservano i valori sorgente. Nessuna informazione del provider attuale
è stata eliminata: il nuovo reader non è ancora un suo sostituto.

| Campo HELPER / uso attuale | Fonte | Campo originale | Trasformazione / disponibilità |
|---|---|---|---|
| identifiers, Variation ID, link variante | VS e SS | VariationID | Intero positivo; nessun uso di rsID/gene per fondere record |
| Allele ID | VS | AlleleID | Identificativo distinto dal Variation ID; NULL per record solo SS |
| accession_version / VCV | Nessuna dei due | Assente | VCV e versione NULL; non derivati artificialmente dal Variation ID |
| Gene e identificativi | VS | GeneSymbol, GeneID, HGNC_ID | Stringhe originali; nessun mapping genico implicito |
| Nome e tipo variante | VS | Name, Type | Colonne del record variante |
| Assembly e allele genomico | VS | Assembly, ChromosomeAccession, Chromosome, PositionVCF, ReferenceAlleleVCF, AlternateAlleleVCF | Assembly separati; accession qualificata; normalizzazione esistente |
| Coordinate di dettaglio originali | VS | Start, Stop, ReferenceAllele, AlternateAllele, Cytogenetic | Conservate nella posizione; non usate al posto dei campi VCF left-shifted |
| classifications / clinical_significance | VS | ClinicalSignificance | Aggregato variante, scope=variant, kind=germline; nessuna assegnazione automatica agli RCV |
| review_statuses.label | VS | ReviewStatus | Testo originale |
| review_statuses.stars / clinvar_stars | VS | ReviewStatus | Vocabolario ufficiale → 0–4; status sconosciuto → NULL |
| conditions | VS | PhenotypeList | Associazione posizionale ai RCV solo quando il numero di gruppi coincide |
| condition_ids | VS | PhenotypeIDS | Conservazione di gruppi pipe, virgole e punti e virgola; nessuna separazione ambigua |
| rcv_accessions / Condition records | VS | RCVaccession | Accession distinte e URL; versione solo se esplicita |
| Classificazione aggregata disease-specific RCV | Non disponibile | Assente | NULL esplicito, NOT_IN_SELECTED_DATASETS; non ricalcolata localmente |
| Classificazione disease-specific SCV | SS | ClinicalSignificance, ReportedPhenotypeInfo, SubmittedPhenotypeInfo | Interpretazione del singolo submitter; scope=submission_condition, senza inventare un join SCV→RCV |
| conflicts / has_conflict | VS | ClinicalSignificance | Flag testuale dell'aggregato germline/oncogenicity; non usato per il clinical impact somatico |
| classification_breakdown | SS + VS | ClinicalSignificance, ContributesToAggregateClassification, SCVsForAggregateGermlineClassification | Dati necessari disponibili per un futuro adapter; nessun nuovo breakdown che confonda tutte le SCV con quelle dell'aggregato |
| origins | VS | Origin, OriginSimple | Origin in colonna, OriginSimple nei dettagli |
| last_evaluated | VS | LastEvaluated | Data originale dell'aggregato germline |
| oncogenicity | VS | Oncogenicity | Aggregato separato, kind=oncogenicity |
| oncogenicity_review_statuses | VS | ReviewStatusOncogenicity | Testo e stelle separati |
| Data oncogenicità | VS | OncogenicityLastEvaluated | Data originale |
| somatic_clinical_impact | VS | SomaticClinicalImpact | Aggregato separato, kind=somatic_clinical_impact |
| somatic_review_statuses | VS | ReviewStatusClinicalImpact | Due stelle anche per multiple submitters senza consenso, secondo la definizione specifica somatica |
| Data clinical impact | VS | SomaticClinicalImpactLastEvaluated | Data originale |
| submitter_count | VS | NumberSubmitters | Numero upstream, compreso zero; conteggi locali per nome separatamente interrogabili |
| submission_count | SS | SCV | COUNT DISTINCT locale delle SCV presenti nello snapshot, distinto dal numero di righe interpretative e dall'eventuale numero del provider remoto |
| SCV e versione | SS | SCV | Stringa completa + accession e versione estratte |
| Submitter | SS | Submitter | Nome originale; nessun organization ID disponibile |
| Review / data singola interpretazione | SS | ReviewStatus, DateLastEvaluated | Campi separati dall'aggregato variante |
| Submission somatica / oncogenicità | SS | SomaticClinicalImpact, Oncogenicity | Classificazioni per SCV, non fuse con il germline |
| Informazioni aggiuntive SCV | SS | Description, CollectionMethod, OriginCounts, SubmittedGeneSymbol, ExplanationOfInterpretation | JSON accessorio originale |
| Contributo all'aggregato | VS e SS | SCVsForAggregate*, ContributesToAggregateClassification | Conservato senza ricostruire regole di aggregazione NCBI |
| record_updated | Non disponibile | Assente | Non ricavabile da LastEvaluated o Last-Modified |
| most_recent_submission | Non disponibile | Assente | Nessuna data di submission inventata |
| source_url | Identificativi | VariationID, RCVaccession, SCV | URL ufficiali, nessun recupero automatico dell'evidenza |
| retrieved_at / freshness / provenance | Manifest locale | Date acquisizione/importazione, checksum per file | Snapshot installato; nessun TTL fittizio o release scientifica dedotta |
| Annotazioni ClinVar originali VCF | Indice HELPER esistente | CLNSIG, CLNREVSTAT, CLNDN, CLNDISDB, CLNSIGCONF, CLNORIGIN, ONC, SCI ecc. | Restano nell'indice e non vengono migrate o sovrascritte |

I campi `OtherIDs`, rsID, dbVar, ClinSigSimple, Guidelines, TestedInGTR,
SubmitterCategories e colonne future sconosciute sono conservati nei dettagli,
non utilizzati come identità. Un disallineamento fra gruppi RCV/condizioni
conserva anche le tre stringhe originali in `unaligned_condition_source`.

## 3. Schema e indici

Persistenza: soltanto SQLite, schema locale **1**, `PRAGMA user_version=1`.
Cinque tabelle, senza ORM, servizi o dipendenze aggiuntive:

- `variants`: PK Variation ID; Allele ID, VCV/versione nullable, nome/tipo,
  gene/ID/HGNC, origini, numero submitter upstream e dettagli accessori JSON.
  Include anche i Variation ID presenti soltanto in SS, senza inventarne l'Allele ID.
- `genomic_positions`: FK variante, assembly/accession/posizione/REF/ALT, stato e
  motivo del matching, coordinate originali JSON. Una riga per ogni riga VS,
  comprese quelle non interrogabili. Nessun indice che duplichi il JSON.
- `classifications`: FK variante, scope, tipo, classificazione/review/stelle/data,
  condizione/ID/RCV, conflitto e SCV contribuenti. Gli RCV sono riferimenti con
  classificazione NULL, distinti dagli aggregati variante.
- `submissions`: PK source_row (ordinale della riga dati); SCV completa,
  accession/versione, FK variante, submitter,
  classificazioni dei tre tipi, review/stelle/data, condizioni e contributo;
  dettagli accessori JSON.
- `metadata`: manifest JSON della release, contatori, schema e validazione.

Indici: `positions_allele(assembly,chromosome,position,reference,alternate)`
parziale sulle righe interrogabili; `positions_variant(variation_id)`;
`classifications_variant(variation_id,scope,kind)`;
`submissions_variant(variation_id,scv)`, oltre alle PK/unicità necessarie.
`ANALYZE` dopo l'importazione. Ogni connessione del builder abilita FK.

Gli inserimenti usano `executemany` in blocchi da 5.000 righe. La memoria non
cresce con il numero totale di record; cache SQLite 32 MiB, temporanei su disco.
Trigger temporanei rifiutano duplicati con dati variante/aggregato discordanti:
un cambio upstream non viene risolto scartando silenziosamente un valore.
**SCV e versione non sono una chiave univoca delle righe SS**: il file reale
contiene, per esempio, due righe SCV000024996.132 / Variation ID 4559 con
classificazioni e date differenti. Ogni riga viene conservata; i conteggi
distinguono righe interpretative e SCV distinte. Non si assume che un duplicato
sia eliminabile né si sceglie arbitrariamente una delle interpretazioni.
I trigger non persistono nel database finale.

## 4. Accesso locale e matching

Implementazione: `helper_next/src/helper_variants/clinvar_local.py`.

`ClinVarLocal` apre lo snapshot in sola lettura, `immutable=1`, verificando schema
e manifest. `variant`, `positions`, `aggregate`, `conditions`,
`condition_classifications`, `submissions`, `submission_counts`, `release`,
`lookup` e `lookup_batch` sono esclusivamente locali. Gli errori di apertura o
schema sollevano `ClinVarLocalError`: non diventano falsi NOT_FOUND.
Submission e classificazioni per condizione sono paginate (default 100, massimo
10.000 per chiamata); il solo aggregato non legge la tabella submissions.

Il lookup riusa `biological_identity.allele_refs`, contratto **ga2** di CACHE-02,
la qualificazione dei contig, gli alias assembly e `indexer.normalize_allele`.
Nessun nuovo normalizzatore e nessun liftover implicito. SNV senza FASTA sono
qualificabili e mantengono REF UNVERIFIED. Con FASTA/.fai si usano i controlli REF,
il trimming e il left alignment già esistenti. Contig/assembly discordanti,
REF mismatch, simboliche e ALT multiple non vengono associati per approssimazione.

I campi VCF NCBI sono già dichiarati left-shifted. Un indel senza FASTA può
ottenere un hit solo se coincide esattamente con questa rappresentazione;
`match_method=exact_ncbi_vcf`, ga2 UNRESOLVED conservato. Una rappresentazione
diversa senza reference resta UNRESOLVED, non una prova di assenza ClinVar.
Con FASTA il query allele normalizzato usa le stesse coordinate canoniche.
Il database non memorizza milioni di hash ga2 ridondanti rispetto all'indice
genomico; il risultato del lookup conserva il binding e la provenance ga2.

Esiti: FOUND, NOT_FOUND per query qualificata, UNRESOLVED con motivo, AMBIGUOUS
se più Variation ID condividono l'allele. Non si fondono ID per rsID o gene.
Un batch accetta una tupla `(assembly, chromosome, position, REF, ALT)` per
richiesta, deduplica le chiavi SQL, conserva ordine e duplicati, restituisce un
esito anche per input invalido e usa blocchi da 150 chiavi (750 parametri).

URL: `/clinvar/variation/{VariationID}/`,
`/clinvar/variation/{VCV}/`, `/clinvar/{RCV}/` e ricerca ufficiale
`?term={SCV}[clv_acc]`. La ricerca SCV apre il record variante che la contiene:
ClinVar non promette una pagina autonoma SCV. Gli identificativi/versioni sono
esposti al chiamante senza scaricare evidenze dettagliate.

## 5. Costruzione e pubblicazione

Default: `$XDG_DATA_HOME/helper_variants/clinvar_local.sqlite3`, oppure
`~/.local/share/helper_variants/clinvar_local.sqlite3`.
Override: `HELPER_CLINVAR_LOCAL_DB` o argomento `database` / CLI `--database`.

```bash
PYTHONPATH=helper_next/src python -m helper_variants.clinvar_local \
  download-build --download-dir /percorso/archivi-clinvar

PYTHONPATH=helper_next/src python -m helper_variants.clinvar_local \
  --database /percorso/clinvar_local.sqlite3 build \
  --variant-summary /percorso/variant_summary.txt.gz \
  --submission-summary /percorso/submission_summary.txt.gz

PYTHONPATH=helper_next/src python -m helper_variants.clinvar_local info
PYTHONPATH=helper_next/src python -m helper_variants.clinvar_local check-updates
```

`download-build` acquisisce il checksum ufficiale e poi ciascun archivio una sola
volta, verificando lunghezza HTTP e MD5. I download incompleti sono temporanei e
non sovrascrivono un archivio precedente. L'importazione da file locali registra
SHA-256/MD5; verifica anche il sidecar `.md5` quando presente. Un subset di test
senza checksum upstream viene dichiarato non verificato rispetto all'originale,
non spacciato per export ufficiale completo.

La costruzione avviene in una directory temporanea dentro
`clinvar_local.sqlite3.snapshots/`, sullo stesso filesystem della destinazione.
Si controllano header, larghezza di ogni riga, identificativi, conteggi,
`integrity_check`, `foreign_key_check`, schema e manifest. Solo dopo questi
controlli il file validato diventa uno snapshot immutabile (permessi 0444).

**Non viene sostituito nessun file SQLite aperto.** Il nome pubblico è un
symlink; il reader risolve e fissa il percorso immutabile prima della connessione.
La pubblicazione usa un lock POSIX sulla directory fra writer, fsync del file e
delle directory, e sostituzione atomica del solo symlink. Un normale file
preesistente alla destinazione è rifiutato, senza tentare migrazioni o replace.
I reader già aperti continuano sul loro snapshot; i nuovi vedono quello nuovo.
Il modello usa le primitive POSIX dell'ambiente XDG/Linux attuale.

**Policy aggiornata da CACHE-04.1: al massimo due database persistenti**, CURRENT
e BACKUP. CURRENT è l'ultimo dataset validato attivo; BACKUP è quello
precedentemente attivo. Durante la costruzione è ammesso uno staging temporaneo;
un lock sulla directory degli snapshot impedisce builder concorrenti.

Il symlink pubblico seleziona una piccola directory `.roles-<uuid>/`, contenente
i due symlink CURRENT/BACKUP. La sostituzione atomica dell'unico puntatore
pubblico seleziona l'intera coppia: non esiste una finestra con ruoli discordanti.
Queste directory contengono solo collegamenti, non database o manifest duplicati.
I manifest, le release e i checksum restano nei file SQLite immutabili.

Prima di pubblicare si acquisisce un lock esclusivo sui file da ritirare. Ogni
reader `ClinVarLocal` acquisisce invece un lock condiviso sullo snapshot prima
della connessione e lo mantiene fino a `close()`. Risoluzione del puntatore e
acquisizione del lock sono coordinate con la pubblicazione. Se il vecchio BACKUP
è ancora in uso, l'aggiornamento restituisce un errore `active readers`, elimina
lo staging e lascia CURRENT/BACKUP invariati: si riprova dopo la chiusura dei
reader. Non si aggira il limite conservando un terzo database persistente e non
si cancella un file aperto confidando nel comportamento POSIX di `unlink`.

Un controllo aggiuntivo di `/proc` protegge connessioni SQLite dello stesso utente
già aperte prima dell'introduzione dei lock, comprese connessioni inattive. Processi
non ispezionabili bloccano prudentemente il ritiro; fanno eccezione soltanto i
demoni di credenziali del desktop `(sd-pam)`, `gnome-keyring-d`, `ssh-agent`, che
non eseguono query HELPER. Nuovi reader devono usare `ClinVarLocal`: nessun
protocollo di lock applicativo può coordinare nuovi accessi arbitrari che lo
ignorano. La procedura di manutenzione dell'installazione reale è stata eseguita
fuori dall'isolamento dei processi della sandbox.

Gli errori di download, costruzione e validazione avvengono prima del commit e
non modificano nessuno dei due ruoli. Dopo il commit si eliminano automaticamente
gli snapshot non referenziati, le vecchie directory dei ruoli e gli staging
abbandonati. Un'interruzione dopo il commit conserva comunque una coppia coerente;
il `finally` recupera la pulizia quando possibile, mentre dopo SIGKILL si usa
`cleanup` o la successiva pubblicazione. Un file residuo di un'operazione interrotta
non viene selezionato automaticamente come CURRENT o BACKUP.

La pulizia non tocca un builder attivo, file temporanei aperti, directory con
contenuto estraneo o download parziali attivi. I nuovi parziali hanno prefisso
`.clinvar-download-` e un lock mantenuto durante il download. I temporanei
protetti vengono elencati in `deferred`; i file non attribuibili a HELPER non sono
rimossi indiscriminatamente. La vecchia implementazione senza ruoli viene migrata
senza cambiare il file CURRENT. Se esistono più snapshot legacy senza una storia
verificabile, si richiede `--legacy-backup`: non si inventa la provenienza del
BACKUP deducendola dal solo timestamp.

```bash
PYTHONPATH=helper_next/src python -m helper_variants.clinvar_local rollback
PYTHONPATH=helper_next/src python -m helper_variants.clinvar_local cleanup
PYTHONPATH=helper_next/src python -m helper_variants.clinvar_local \
  cleanup --download-dir /percorso/archivi-clinvar
```

`rollback` scambia atomicamente CURRENT e BACKUP senza download, importazioni,
riscritture SQLite o modifiche dei manifest; ripeterlo riattiva il dataset che
era CURRENT. In assenza di BACKUP restituisce un errore esplicito. Il builder
continua a restituire `previous_snapshot`. Non sono implementati scheduler,
job persistenti, aggiornamenti periodici o integrazioni CACHE-05.

## 6. Importazione reale e misure

Importazione integrale riuscita dei due archivi ufficiali, con MD5 verificati,
CRC gzip e validazione SQLite completa. Snapshot:
`composite-sha256:da8e890d1ad7950bb61fa74218dcb86a82629d6c3ddaba76d0e8af08446038a7`.

| Misura / record | Risultato reale |
|---|---:|
| Righe variant_summary importate / posizioni conservate | 9.312.744 |
| Varianti distinte, inclusi ID disponibili solo nelle submission | 4.692.214 |
| Righe submission_summary importate | 6.854.560 |
| SCV versionate distinte | 6.854.554 |
| Aggregati germline | 4.446.728 |
| Aggregati oncogenicità | 3.119 |
| Aggregati somatic clinical impact | 2.031 |
| Riferimenti variante-condizione RCV, senza aggregato inventato | 6.340.513 |
| Totale righe classifications | 10.792.391 |
| Varianti con almeno una posizione interrogabile | 4.598.523 (98,003%) |
| Varianti senza posizione interrogabile, tutte conservate | 93.691 |
| Dimensione SQLite installato, inclusi metadati d'installazione | 13.600.215.040 byte (12,666 GiB) |
| Importazione completa, inclusi hash, indici e controlli finali | 879,43 s (14 min 39 s) |
| Importazione/indici/conteggi prima del controllo finale d'integrità | 814,30 s |
| Massimo RSS del processo di importazione | 137.464 KiB (134,24 MiB) |

| Assembly sorgente | Posizioni interrogabili | Non interrogabili conservate |
|---|---:|---:|
| GRCh37 | 4.600.425 | 75.298 |
| GRCh38 | 4.600.033 | 22.679 |
| NCBI36 | 0 | 4.771 |
| na | 0 | 9.538 |

I numeri per assembly contano posizioni, non varianti distinte. I 93.691 ID
senza posizione interrogabile non vengono scartati. Sono presenti sei righe
interpretative in più rispetto alle SCV versionate distinte: tutte conservate.

SHA-256 degli archivi originali:

- VS: `657b47d0a00ba3ad4b3ddf03e160835c8a4a3c7a2e130c92c904b70021a35703`.
- SS: `ac3bbc9eec20f4392f93a5054d88801b1e4c90d57c3daff138cf11287c0279ec`.

Il confronto sul database completo ha verificato **258 righe** delle fixture
contro variante, classificazioni, review, coordinate e SCV realmente installate,
oltre alle due interpretazioni SCV000024996.132. `EXPLAIN QUERY PLAN` conferma
`SEARCH genomic_positions USING INDEX positions_allele` con tutti e cinque i
campi dell'allele. Non sono state effettuate API NCBI durante questi controlli.

Benchmark finale sulla copia XDG installata, cache filesystem calda:

| Operazione | Mediana | Ripetizioni |
|---|---:|---:|
| Lookup puntuale, inclusa qualificazione | 0,050 ms | 100 |
| Solo classificazioni aggregate di un Variation ID | 0,0072 ms | 100 |
| Batch di 100 alleli distinti | 3,34 ms | 5 |
| Batch di 1.000 alleli distinti | 36,80 ms | 5 |
| Batch di 10.000 alleli distinti | 396,99 ms | 5 |

Tutti gli alleli dei batch misurati hanno restituito FOUND. Sono misure locali,
non una stima di latenza del sito NCBI né un confronto fra hardware diversi.
L'operazione non include il caricamento delle submission. Il campione comprende
5.000 alleli per assembly, con ordine mescolato e seed fisso.

Artefatti della prova: `/tmp/helper-cache04/real-import.json`,
`real-verification.json`, `benchmark.json`, `benchmark-installed.json` e
`submission-preflight.json` nella
stessa directory. Gli archivi originali sono conservati in `/tmp/helper-cache04/`.

Installazione completata nel percorso XDG predefinito:
`/home/jarvis/.local/share/helper_variants/clinvar_local.sqlite3`, symlink a uno
snapshot immutabile nella directory adiacente `clinvar_local.sqlite3.snapshots/`.
La copia persistente ha superato nuovamente `integrity_check` e
`foreign_key_check` prima dell'attivazione atomica; il reader predefinito apre
questa copia senza override. I metadati registrano anche `installed_at` e la
provenance delle date dei download. Il riepilogo è
`/tmp/helper-cache04/installation.json`. Nessuna sostituzione del provider attuale.
Questa installazione ha trasferito lo snapshot dalla directory di prova al default
XDG e ripetuto i controlli: il trasferimento aggiuntivo è separato dal tempo del
builder riportato sopra. Normalmente `build` e `download-build` pubblicano
direttamente alla destinazione scelta. Anche il confronto delle 258 righe è
stato ripetuto con successo sulla copia XDG, usando il reader senza override.

Il benchmark riproducibile è `scripts/benchmark_clinvar_local.py`:

```bash
PYTHONPATH=helper_next/src python scripts/benchmark_clinvar_local.py \
  --database /percorso/clinvar_local.sqlite3 --repeats 5 \
  --output /tmp/clinvar-benchmark.json
```

Seleziona fino a 5.000 alleli distinti per assembly dall'indice, li mescola con
seed fisso e misura qualificazione + SQL + costruzione del risultato, con cache
filesystem calda. Nessuna moltiplicazione artificiale di una singola query per
simulare un batch di 10.000 alleli distinti. Lo script dichiara batch saltati
quando mancano abbastanza alleli. L'importazione reale misura anche il massimo
RSS tramite `resource.getrusage` su Linux; non è il consumo dell'intera macchina.

## 7. Verifiche

Fixture sintetiche e subset NCBI congelati in
`helper_next/tests/fixtures/clinvar_local/`, con provenance e checksum degli
originali. Variation ID 2, 3, 7105 (CFTR), 13961 (BRAF), 17662; le righe sono
copiate senza riscrivere classificazioni o condizioni. L'importazione delle
fixture confronta aggregato, review, Allele ID, coordinate e SCV con le righe
originali. Non sono fixture inventate presentate come dati ClinVar reali.
Una fixture separata conserva le due righe originali SCV000024996.132 della
variante 4559, verificando che entrambe le interpretazioni rimangano accessibili.

Copertura dei test: schema/FK/conteggi, entrambi gli assembly e alias, SNV,
indel esatto e left alignment in ripetizione con FASTA, REF errato,
multialleliche, risultati assenti e ambigui, stati non supportati, ordine e
deduplicazione batch, classificazioni dei tre tipi, condizioni e SCV discordanti,
stelle sconosciute, URL, colonne nuove, condizioni non allineabili, checksum e
lunghezza errati, gzip troncato, header/righe invalide, importazione ripetibile,
errori di pubblicazione, vecchi reader e conservazione degli snapshot precedenti.

Verifiche automatiche di CACHE-04: **188 passed** nella suite ClinVar locale/provider,
ga2 e prioritizzazione; **204 passed, 1 skipped, 185 subtests passed** nelle
regressioni query/store/indexer, gnomAD, contesto PVS1 e calcolatore molecolare.
Totale: **392 passed, 1 skipped**, oltre ai 185 subtest. Dei test principali,
**41** riguardano il nuovo modulo. Il test saltato è
`test_new_calculator_panel_opens_and_explains_requirements`, Chrome opt-in.
Warning preesistente `python_multipart`; nessuna suite browser interattiva,
nessun job Nextflow e nessuna suite integrale estranea al perimetro eseguiti.

```bash
PYTHONPATH=helper_next/src python -m pytest -q \
  helper_next/tests/test_clinvar_local.py helper_next/tests/test_clinvar.py \
  helper_next/tests/test_biological_identity.py helper_next/tests/test_prioritization.py

PYTHONPATH=helper_next/src python -m pytest -q \
  helper_next/tests/test_variant_query.py helper_next/tests/test_variant_store.py \
  helper_next/tests/test_variant_indexer.py helper_next/tests/test_gnomad_frequency.py \
  helper_next/tests/test_acmg_pvs1.py tests/test_pvs1_calculator.py \
  tests/test_pvs1_impact.py tests/test_pvs1_models.py tests/test_pvs1_molecular.py
```

XML delle esecuzioni: `/tmp/helper-cache04/targeted-tests.xml`,
`/tmp/helper-cache04/regression-tests.xml`. `compileall` sui nuovi moduli e
`git diff --check` superati. I test locali vietano la rete, salvo trasporti
esplicitamente simulati per verificare download e confronto degli snapshot.

## 8. Limiti e preparazione CACHE-05

- Nessuna classificazione aggregata per RCV, VCV/versione, versione degli RCV
  non versionati, record_updated o data dell'ultima submission nei due export.
  Le SCV forniscono interpretazioni per condizione, non una ricostruzione
  autorizzata dell'aggregato NCBI. Il sito resta necessario per questi dettagli,
  storia/versioni e collegamenti SCV→RCV non presenti nei file.
- `PhenotypeIDS`/`PhenotypeList` possono riportare il numero delle condizioni
  quando sono più di cinque. Non si inventano i termini omessi. I separatori
  interni e le condizioni multiple vengono conservati senza spezzare associazioni.
- VS descrive Allele ID e non è un mapping esaustivo di tutti i Variation ID di
  genotipi/aplotipi. Gli ID presenti solo in SS restano nel database, senza
  ereditare coordinate dagli alleli che li compongono.
- Simboliche, grandi eventi, posizioni mancanti, assembly diversi e contig non
  qualificabili rimangono identificabili ma non interrogabili per allele. Il
  motivo e la copertura sono nel database. Il solo nome mitocondriale MT non
  produce equivalenza con un'accession/versione; serve un contig esplicito.
- Gli alleli sorgente NCBI sono fidati come VCF left-shifted; il dataset non
  certifica una verifica REF locale con FASTA. Una query indel non coincidente
  richiede la reference per verificarne l'equivalenza.
- Lo snapshot composito non prova allineamento temporale fra i due export.
  SCV contribuenti elencate in VS e SCV presenti in SS possono differire.
- La retention CURRENT/BACKUP elimina le release più vecchie: una release oltre
  BACKUP non rimane disponibile per audit. Un BACKUP con reader attivi impedisce
  un ulteriore aggiornamento fino alla loro chiusura, preservando il limite di due
  database persistenti. La gestione usa le primitive POSIX/Linux descritte sopra.

In CACHE-05 servirà un adapter esplicito verso il payload di `clinvar.py`, con
provenance dello snapshot e limiti di copertura. Dovrà distinguere l'aggregato
variante dalle interpretazioni per condizione, usare gli SCV contribuenti per un
eventuale breakdown e definire il comportamento per NOT_FOUND/UNRESOLVED/
AMBIGUOUS e dati non disponibili. Lista, dettaglio e prioritizzazione potranno
poi utilizzare il reader batch locale. API/frontend/Source Manager e il provider
attuale non sono stati modificati in anticipo.

## 9. CACHE-04.1 — Verifiche e applicazione della retention

Modificati soltanto `clinvar_local.py`, `test_clinvar_local.py` e questo report.
Il confronto AST con il modulo precedente conferma **schema SQL e tutti i metodi
di interrogazione invariati**; il reader cambia solo apertura/chiusura per
mantenere il lock. Nessuna modifica a dati ClinVar, prioritizzazione, API,
frontend o cache `clinvar_evidence.sqlite3`.

I test della retention coprono aggiornamenti consecutivi con due soli file,
rollback ripetibile senza ricostruzione e senza cambiamenti ai byte SQLite,
reader attivi sul BACKUP (sia `ClinVarLocal` sia SQLite diretto), errori di
validazione con entrambi i ruoli già presenti, interruzioni prima e dopo il
commit atomico, SIGKILL di un builder in un processo distinto, rifiuto della
pulizia mentre il builder è attivo, pulizia al termine, staging aperti e
abbandonati, parziali di download attivi, preservazione di file estranei,
migrazione legacy, comandi CLI e processi non ispezionabili.

Risultato finale CACHE-04.1: **205 passed**, di cui **58** nel modulo ClinVar
locale, nella suite locale/provider/ga2/prioritizzazione. Nessun test saltato in
questa esecuzione; warning `python_multipart` preesistente. XML:
`/tmp/helper-cache041/regression-tests.xml`. Sintassi Python e
`git diff --check` verificati. Nessun nuovo download o reimportazione integrale:
questo task modifica esclusivamente la gestione dei file e dei reader.

Sull'installazione reale è stato verificato e mantenuto **un solo database
persistente**, CURRENT, da **13.600.215.040 byte**. BACKUP è assente perché non
esisteva un dataset precedentemente attivo nel percorso XDG; il prossimo
aggiornamento completato lo creerà. Il puntatore è stato migrato alla selezione
atomica dei ruoli conservando lo stesso inode, dimensione, mtime, intero manifest
di release e checksum. Anche il lookup BRAF V600E / Variation ID 13961 è passato.

La copia di prova rimasta da CACHE-04 in
`/tmp/helper-cache04/installed/clinvar_local.sqlite3.snapshots/` è stata
confrontata con CURRENT (stesso snapshot, conteggi e SHA-256 delle fonti),
verificata come inutilizzata e rimossa con il relativo puntatore. Recuperati
**13.600.210.944 byte (12,666 GiB)**. Archivi sorgente, fixture e report delle
misure restano conservati. Riepilogo dell'applicazione reale:
`/tmp/helper-cache041/installed-retention.json`; nessun file rinviato alla pulizia.
