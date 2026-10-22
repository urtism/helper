# TASK 22 — ACMG Interpretation Workbench

## Classify variant — esecuzione research (2026-10-22)

Il pulsante restava disabilitato con profili disponibili perché le capabilities
del motore riportavano `research_execution_enabled: false`. Il workspace
corrente aveva già normalizzazione e riferimento verificati. Su richiesta
dell'utente, `configs/acmg_engine.json` abilita esplicitamente l'esecuzione
research. Il launcher supporta il booleano `enable_research_interpretation`;
la variabile di ambiente omonima ACMG mantiene priorità, anche per disabilitarlo.
Nessun cambiamento a profili o salvaguardie del riferimento.

Il workbench espone ora il motivo di disabilitazione accanto al pulsante e
nel tooltip: research disattivata, riferimento mancante o profilo non selezionato.
Verifica live API motore: sei profili e `research_execution_enabled: true`.
Test mirati servizio/workbench/contesto: **62 passed**; test Chrome esplicito:
**1 passed**, inclusi abilitazione dopo selezione, avviso research e blocco
per riferimento mancante. Nessuna classificazione reale eseguita automaticamente.
Riaprire il workbench rilegge le capabilities aggiornate.

## Configurazione profili nell'avvio automatico (2026-10-22)

Su scelta dell'utente, `configs/acmg_engine.json` elenca i sei profili
sperimentali TASK20 documentati nel workbench. Il launcher HELPER ne prepara
copie temporanee identiche ai sorgenti per `ACMG_PROFILES_DIR`; l'ambiente
esplicito ha priorità. Nessun cambiamento al contenuto dei profili o al flag
di esecuzione research. La configurazione vale per i processi figli avviati
da HELPER, senza importare il pacchetto scientifico nel server HELPER.

Verifica locale: i sei file caricati nel registro reale del motore risultano
validi, tutti EXPERIMENTAL. Test mirati `test_acmg_service.py`,
`test_acmg_workbench.py`, `test_acmg_context.py`: **58 passed**. Copie/digest,
precedenza dell'ambiente, configurazioni invalide e pulizia dei file temporanei
verificati. Vecchio processo standalone arrestato e richiesto reload HELPER.
Verifica HTTP finale dei profili non eseguita: autorizzazione rifiutata.

## Checkpoint A — VERIFIED (2026-10-21)

Viewer riutilizzato: `helper_variants/indexer.py`, `store.py`, `query.py`,
`web/static/variant-browser.js` e API `helper_next/api/variants.py`.
Sorgenti esterne con manifest e indice SQLite privati, nessun inserimento nella
cronologia analisi. Upload raw in streaming, limite 256 MiB compressi/1 GiB
espansi e 4 MiB per riga; verifica struttura, nomi campioni e coordinate.
Assembly GRCh37/38 confermata esplicitamente; CSQ/ANN e paginazione condivisi.
Conservazione INFO originale, ALT e indice allele, QUAL/FILTER/FORMAT.

Verifica: `PYTHONPATH=helper_next/src python -m pytest -q
helper_next/tests/test_external_vcf.py helper_next/tests/test_variant_indexer.py
helper_next/tests/test_variant_query.py helper_next/tests/test_variant_viewer.py`:
**63 passed**. Comprende equivalenza run/upload, gzip, multialleliche,
multicampione, CSQ fuori ordine e limiti di decompressione.

Modifiche preesistenti nel viewer/API/test mantenute. Nessun commit/push.

## Stato finale — PARTIALLY_COMPLETED

2026-10-21. Ultimo checkpoint tecnico verificato: **D**. Il checkpoint **C è
PARTIAL** per i dati scientifici universali non esposti dal contratto; gli audit
effettivamente restituiti sono visibili e sono stati verificati. Nessuna modifica
ad ACMG Engine, commit o push. Le limitazioni scientifiche TASK20/21 rimangono.

### B — VERIFIED

Client REST separato, URL configurabile (default 127.0.0.1:8000), timeout,
errori strutturati, controllo API v1/schema 1.0 e discovery dei profili per coppia
gene-malattia. Backend ispezionato localmente, HEAD `7d6bea1`, versione 0.1.0.
Strategie reali CUSTOM_ALGORITHMIC e CLINGEN_GUIDED; profili/versioni/strategie
incompatibili non eseguibili. Nessun VCEP dedotto da MYH7.

Mapping allele/annotazione/trascritto espliciti, fonti e checksum. REVEL,
componenti SpliceAI e annotazioni gnomAD AC/AN/AF quando presenti. Assenza di
release/qualità/popolazione dichiarata esplicitamente, nessun conteggio derivato
da AF. Provenienza del contesto strutturato HELPER e delle scelte manuali
separata dal record VCF importato.
Genotipi e INFO completi rimangono localmente ispezionabili; nessun VCF intero
trasmesso al servizio. Verifica FASTA/normalizzazione tramite componenti HELPER
esistenti, richiesta dal contratto per l'evidenza strutturata.

### C — PARTIAL (funzionalità esposte verificate)

Tabella dei 28 criteri, ricerca per stato/review, PP5/BP6 ritirati, status
originale preservato e stati di presentazione distinti. Attivazione candidata
MET/NOT_MET con irrisolti NOT_RECORDED; contributi effettivi provenienti dal
motore. Esclusioni di dipendenza mostrate solo con metadati espliciti.
Forze candidate/effettive, regole, riferimenti, spiegazioni e audit specialistici
esposti integralmente. Numeri PM2 mantenuti come stringhe a piena precisione.
Confronto affiancato tramite API compare, stesso snapshot, dimensioni e fallimenti
riportati dal motore, nessuna categoria di modifica inventata.

La fixture reale AC=1/AN=118595 ha restituito MANUAL_REVIEW_REQUIRED,
METHOD_DISCORDANCE, limiti binomiale/Poisson distinti e nessun contributo PM2.
Il browser con risposte simulate verifica anche la visualizzazione di entrambi
i numeri senza perdita di precisione.

Non sono disponibili uniformemente formula, calcolo, catena parent/override/
effective-rule e primo errore scientifico per ogni evaluatore. I campi mancanti
sono NOT_RECORDED. OpenAPI dei modelli centrali opaco e riferimenti profilo da
canonicalizzazione verificata: [richiesta precisa schema 1.1](TASK22_ACMG_CONTRACT.md).

### D — VERIFIED per workflow e persistenza tecnici

Revisioni CONFIRM/CONTEST/REQUEST_REVIEW, categorie di discrepanza, commenti,
reviewer e timestamp salvati append-only con ID/fingerprint della specifica
interpretazione. Correzioni di evidenza con fonte/versione/checksum e commento,
esiti originali immutabili, rerun, confronto prima/dopo e contesti riapribili.
Export risultato JSON, EvidencePacket, CSV con audit completo, report Markdown,
troubleshooting, review, confronto profili e differenza di rerun.
Nessuna revisione umana cambia l'attivazione calcolata o approva un profilo.

## Collegamento della cache gnomAD al motore

Il dettaglio variante espone il record completo `gnomad_frequency` già presente
nella cache HELPER per lo stesso allele e assembly. Il workbench lo trasferisce
nel packet come evidenza POPULATION, con AC/AN/AF disponibili, popolazioni,
conteggi omozigoti/emizigoti, filtri, copertura, release, dataset e checksum della
fonte. Anche lo stato `not_observed_covered` viene trasmesso; non produce conteggi
o numerosità non restituiti dal servizio. Nessuna soglia PM2 o qualifica ancestrale
viene introdotta dal trasporto. Snapshot precedenti immutati.

Verifiche del collegamento:

* Test mirati workbench/contesto/cache/query: **62 passed**.
* Suite generale: **346 passed**, test opzionali non abilitati, 43.74 s.
* REST sul motore reale in porta 8000, `-k packet_profiles`: **2 passed,
  1 deselected**, 1.98 s. Verificati AC=0 esplicito e assenza con conteggi
  sconosciuti, checksum/release della fonte e confronto sullo stesso snapshot.
* `git diff --check`: passato.

Un tentativo separato del vecchio test di discordanza PM2/MYH7 con
`/tmp/helper-task22-boundary-request.json` è stato rifiutato dal servizio in
porta 8000: la richiesta temporanea seleziona profili/versioni del precedente
ambiente sintetico, non quelli attivi. Il test non ha raggiunto il valutatore;
non è una verifica del presente collegamento. I limiti scientifici dei profili
dimostrativi restano invariati.

## Verifiche precedenti al collegamento della cache gnomAD

| Verifica | Esito |
| --- | --- |
| `PYTHONPATH=helper_next/src python -m pytest -q helper_next/tests` | **336 passed, 3 skipped**, 43.66 s |
| `HELPER_TEST_ACMG_BROWSER=1 PYTHONPATH=helper_next/src python -m pytest -q helper_next/tests/test_acmg_browser.py --tb=short` | **1 passed**, 1.46 s |
| `HELPER_TEST_ACMG_SERVICE=1 ACMG_ENGINE_URL=http://127.0.0.1:8013 HELPER_TEST_ACMG_BOUNDARY_REQUEST=/tmp/helper-task22-boundary-request.json PYTHONPATH=helper_next/src python -m pytest -q helper_next/tests/test_acmg_service_integration.py` | **2 passed**, 2.41 s |
| Smoke test Chrome + API HELPER + motore reale, VCF/FASTA sintetici | Upload, selezione, interpretazione 28 criteri, review e roundtrip di persistenza verificati |
| `node --input-type=module --check` sui due moduli JS modificati | Passato |
| `git diff --check` | Passato |

I tre skip della suite ordinaria sono intenzionali: due test del servizio reale
e un test Chrome, eseguiti separatamente. Warning preesistente di deprecazione
python_multipart. Il threadpool AnyIO del test IGV si blocca nel sandbox:
regressione completa eseguita fuori dal sandbox. Nessun workflow Nextflow reale
avviato. Il test samplesheet preesistente può impiegare tempo nella scansione
dei propri search roots; non è stato modificato.

Il test browser usa API simulate e verifica precisione, ispettore, CONTEST,
parent del rerun, confronto e link export; il motore non è richiesto. Il collaudo
REST impiega i profili research TASK20 e fixture sintetiche ufficiali del motore.
Non costituisce riproduzione scientifica o validazione clinica degli scenari
MYH7 PM1/PVS1/PS1/PS4, né dei profili nel loro insieme.

## File del TASK 22

* Nuovi core: `helper_next/core/external_vcf.py`, `acmg_client.py`,
  `acmg_reference.py`, `acmg_store.py`, `acmg_workbench.py`, `acmg_context.py`, `acmg_population.py`
  (sotto `helper_next/src/`).
* API: nuovo `helper_next/api/acmg.py`; modificati `api/app.py`, `api/variants.py`.
* Viewer riutilizzato: modificati `helper_variants/indexer.py`, `query.py`, `gene_phenotype.py`, `gnomad_frequency.py`,
  `web/static/variant-browser.js`; nuovi `acmg-workbench.js` e `.css`.
* Test: nuovi `test_external_vcf.py`, `test_acmg_workbench.py`,
  `test_acmg_service_integration.py`, `test_acmg_browser.py`, `test_acmg_context.py`; isolamento aggiornato
  in `helper_next/tests/conftest.py`.
* Documenti: questo stato, `TASK22_WORKBENCH.md`, `TASK22_ACMG_CONTRACT.md`;
  collegamenti aggiunti in `helper_next/README.md`.

Le modifiche preesistenti a IGV, clinical-browser, CSS e test del viewer/API
non sono state annullate né attribuite a questo task.

## Ripresa e limiti residui

Aggiornamento richiesto: identificativi automatici da HELPER. Il dettaglio
variante ora include `interpretation_context`, costruito lato backend dalle
annotazioni e dalla cache locale gene-malattia. La cache espone gli ID gene
curati e li mantiene associati alle singole assertion. Il workbench usa ID in
sola lettura e invia il record selezionato/fingerprint, non ID digitati. Una
sola associazione viene precompilata, più malattie richiedono scelta per nome.
Ereditarietà univoca importata; ambiguità e dati mancanti non vengono risolti
per inferenza. Fonti/versioni e contesto risolto sono persistiti ed esportati.

Test aggiunti: mapping senza HGNC nel VCF, API senza ID manuali per run e upload,
malattie multiple, fallback HGNC discordante, cache assente, fingerprint cambiato
ed ereditarietà ambigua. Il browser verifica che gli ID siano di sola lettura,
compilati automaticamente e assenti come input manuale nella richiesta. I due
test REST reali riportati sopra sono del collaudo TASK22 precedente a questo
aggiornamento; non sono stati ripetuti per questa modifica di integrazione locale.

[Installazione e comandi di avvio](TASK22_WORKBENCH.md). Due ambienti Python,
servizio ACMG research esplicitamente abilitato, profili locali esatti e FASTA
coerente con l'assembly dichiarata. L'assenza del riferimento non viene aggirata.

Indici creati prima del task possono non contenere il nuovo INFO/header originale;
restano utilizzabili, ma serve rigenerarli per aggiungere questi dati, altrimenti
lo stadio raw è NOT_RECORDED. Tipi simbolici/breakend sono navigabili ma non
reinterpretati come SNV. Namespace/versioni transcript sconosciuti rimangono
esplicitamente non stabiliti. Nessuna acquisizione automatica di evidenza clinica,
di segregazione o di assay a partire da etichette VCF.

Il completamento dell'audit universale richiede l'estensione engine documentata;
non aggiungere soglie o formule locali per eliminare artificialmente i mancanti.
Fermarsi dopo TASK 22.
