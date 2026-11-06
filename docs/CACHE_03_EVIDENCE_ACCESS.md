# CACHE-03 — Accesso alle evidenze e ottimizzazione ClinVar

Data: **30 ottobre 2026**. Implementazione sui provider esistenti, senza nuove
dipendenze, database applicativi, tabelle, migrazioni o modifiche alle chiavi.

## 1. Ricognizione prima delle modifiche

Riferimenti: `CACHE_01_ARCHITECTURE.md`, `CACHE_02_IDENTITIES.md` e
`HELPER_STRUCTURAL_CLEANUP.md`. La ricognizione dei consumer è stata completata
prima di cambiare le funzioni applicative.

| Operazione | Percorso effettivo | Cache e rete iniziali |
|---|---|---|
| Indicizzazione VCF | `helper_variants/indexer.py` → `store.py` | Importazione delle annotazioni originali, separazione degli ALT; nessun prefetch ClinVar/gnomAD. ClinVar INFO non assegnata indiscriminatamente alle varianti multialleliche. |
| Lista e ordinamento | `api/variants.py:sample_variants` → `query.list_variants` | Letture SQLite batch tramite `clinvar.cached_evidence` e `gnomad_frequency.cached_contexts`; nessuna richiesta HTTP per variante. |
| Prioritizzazione | `query._compact_variant` → `engine.score_variant` / `apply_clinvar_evidence` | gnomAD già letto dalla cache; ClinVar dinamico sostituisce il componente ClinVar tramite il calcolo esistente. Le annotazioni VCF conservano provenienza distinta. |
| Dettaglio | `sample_variant_detail` → `query.variant_detail` → `clinvar.lookup_variant` | ClinVar forzato con `refresh=True` a ogni apertura. `query.variant_detail` legge gnomAD localmente; le annotazioni ClinVar VCF originali restano nell'indice. |
| Frequenze su richiesta | `sample_variant_gnomad_frequency` → `gnomad_frequency.lookup_variant` | Cache prima della richiesta GraphQL puntuale. Nessun nuovo endpoint batch remoto. |
| Source Manager | `core/acmg_sources.py:SourceManager.population` | Cache/attached prima del fetch esplicito; stati CACHED/AVAILABLE e freshness NOT_RECORDED ambigui per cache miss/offline. Gli adapter dei meccanismi gene-malattia hanno uno scope differente. |

Problemi confermati: refresh ClinVar sistematico; arricchimento efetch implicito
per vecchi payload senza breakdown; scarto delle evidenze scadute prima di poterle
riutilizzare in caso di errore; possibile interpretazione di risposte esearch
malformate come assenza; controllo gnomAD incompleto della release e validazione
batch meno rigorosa del lettore singolo. Le chiavi duplicate gnomAD potevano
occupare più batch SQLite.

## 2. File modificati nel task

Percorsi sotto `helper_next/`:

- `src/helper_variants/clinvar.py`: policy cache-first, completezza, offline,
  conservazione dell'ultima evidenza, metadati e validazione.
- `src/helper_variants/gnomad_frequency.py`: validazione condivisa delle letture
  singole/batch per allele, assembly, dataset e release; deduplicazione e stati.
- `src/helper_variants/query.py`: evidenza ClinVar e relativi metadati nella lista.
- `src/helper_next/api/variants.py`: refresh esplicito e binding ga2 facoltativo.
- `src/helper_next/core/acmg_sources.py`: adattamento circoscritto di `population`.
- `tests/test_clinvar.py`, `tests/test_gnomad_frequency.py`,
  `tests/test_variants_api.py`: regressioni su cache, rete, errori e integrazione.
- `tests/test_acmg_context.py`: fixture del dettaglio esplicitamente offline.
- Questo documento.

Le modifiche preesistenti del cleanup e CACHE-02 sono state conservate. Il motore
di prioritizzazione, PVS1, le altre regole ACMG e `biological_identity.py` non
sono stati modificati da CACHE-03.

## 3. Policy ClinVar finale

`lookup_variant` legge la cache esistente prima di ogni recupero remoto. Un dato
fresco con `classifications` e `review_statuses` presenti come liste è adeguato
alla visualizzazione aggregata; liste vuote possono rappresentare campi
legittimamente non riportati. Un payload contenente soltanto l'identificativo
richiede il recupero dell'aggregato, quando consentito. NOT_FOUND fresco è una
risposta valida riutilizzabile.

Restano invariati i TTL: **7 giorni per AVAILABLE, 1 giorno per NOT_FOUND**.
La data SQLite di acquisizione è usata anche per vecchi payload privi del campo
JSON `retrieved_at`. Una data assente/non interpretabile produce UNKNOWN, senza
inventare una data della fonte. Le letture puntuali sono ora `mode=ro`, senza DDL.

Il breakdown delle classificazioni è un arricchimento opzionale: la UI può
visualizzare l'aggregato senza di esso. La sola assenza del breakdown non provoca
rete durante l'apertura normale. `require_breakdown=True` permette al chiamante
di richiederlo esplicitamente: con aggregato fresco e ID numerico si esegue solo
efetch. Un risultato `[]` ottenuto correttamente vale come arricchimento completo;
un fallimento non viene trasformato in un successo vuoto. L'arricchimento non
rinnova la data di acquisizione dell'aggregato. Il recupero iniziale continua a
tentare il breakdown come già faceva il provider; un errore opzionale è esposto
in `breakdown_error`, senza invalidare l'aggregato acquisito.

Il dettaglio usa `refresh_clinvar=False` per default. Il parametro query
`?refresh_clinvar=true` mantiene il refresh esplicito; il provider conserva
`refresh=True`. `fetch=False` oppure `HELPER_CLINVAR_OFFLINE=1` impediscono ogni
richiesta, anche se refresh/breakdown sono richiesti. gnomAD conserva il proprio
`HELPER_GNOMAD_OFFLINE`.

Se il recupero fallisce, una precedente evidenza valida viene restituita con la
propria freschezza e `last_error`, conservando payload e data nel medesimo record
SQLite. Senza evidenza precedente si restituisce ERROR e non si salva una falsa
risposta negativa. Una risposta NOT_FOUND ottenuta correttamente può invece
sostituire la precedente revisione: non è un errore di rete. Non è uno storico
delle revisioni.

## 4. Stati, provenance e coerenza

I provider aggiungono `availability` e `freshness` ai payload esistenti. `status`
mantiene il vocabolario precedente per compatibilità con i consumer.

| Disponibilità logica | Interpretazione |
|---|---|
| AVAILABLE | Evidenza utilizzabile, anche se STALE; include le risposte gnomAD biologiche con contesto di copertura. |
| NOT_QUERIED | Cache miss senza interrogazione consentita; non prova assenza nella fonte. |
| NOT_FOUND | ClinVar interrogato correttamente senza allele corrispondente. |
| ERROR | Errore remoto, payload non valido o cache illeggibile, senza un'evidenza precedente utilizzabile. |
| UNSUPPORTED | Query non supportata, distinta dall'errore di trasporto. |

ClinVar espone FRESH/STALE/UNKNOWN separatamente. Le letture batch mantengono
anche l'evidenza scaduta con STALE, così lista, offline e fallback del dettaglio
possono riferirsi allo stesso ultimo record. `include_stale=False` rimane
disponibile per consumer che vogliono soltanto record freschi. Errori di parsing
ClinVar in cache e di lettura SQLite sono esposti come ERROR, non NOT_FOUND.

gnomAD conserva `observed`, `not_observed_covered`, `not_observed_low_coverage` e
`not_observed_coverage_unknown`, copertura, AC/AN, filtri e popolazioni. FRESH
indica compatibilità con la release configurata, priva di TTL temporale; non
certifica una verifica della release live. Assenza di conteggi o dati non
disponibili non diventa AF=0 né prova di assenza. Una risposta negativa biologica
con copertura resta distinta da una query mai eseguita.

Sono conservati `source`, identificativi ClinVar inclusa l'accession versionata,
`source_url`, `retrieved_at`, `record_updated`, `last_evaluated`, provenance
presente e release/dataset gnomAD. Non sono inventate release ClinVar globali né
date di aggiornamento mancanti. `last_error` descrive l'ultimo tentativo fallito;
una nuova acquisizione riuscita sostituisce il vecchio errore.

La lista ora restituisce `clinvar_evidence`, consentendo di confrontare direttamente
fonte, identificativi, acquisizione e freschezza con il dettaglio. Entrambe le
viste usano il componente di priorità esistente. Nessuna formula, soglia, peso,
regola ACMG o aggiornamento massivo è stato introdotto. La normale successiva
lettura della lista usa la cache aggiornata e l'invalidazione già presente.

## 5. CACHE-02 e Source Manager

Il dettaglio aggiunge `allele_identity` calcolato con `allele_refs`, usando il
record della run quando disponibile. Il binding ga2 è soltanto informativo e non
condiziona il lookup: SNV senza FASTA restano interrogabili; indel e altre query
già supportate non richiedono un ga2 risolto. Assembly e singola ALT restano nella
chiave SQLite precedente; ID degli indici e generazione degli hash sono invariati.

`SourceManager.population` restituisce stati logici e freschezza dal provider,
non considera una cache miss AVAILABLE e verifica che i payload attached
corrispondano ad allele, assembly, dataset e release. Il recupero resta esplicito.
Non è stato aggiunto un adapter ClinVar al Manager: le API e la lista hanno già
accesso diretto al provider, e un passaggio aggiuntivo non offre benefici concreti.
Il ClinVar gene-malattia del Source Manager rimane un adapter con scope diverso;
non viene trasformato in un lookup per allele.

## 6. Misure riproducibili

Fixture HTTP locali; nessuna misura di latenza o quota di un servizio live.

| Scenario | Prima, comportamento riprodotto | Dopo |
|---|---:|---:|
| Cinque aperture del dettaglio di uno stesso allele con cache completa | 15 HTTP: esearch + esummary + efetch a ogni refresh forzato | **0 HTTP** |
| Primo lookup positivo senza cache | 3 HTTP | 3 HTTP, poi riuso |
| Payload fresco senza breakdown ma con aggregato completo | 1 efetch implicito | **0 HTTP** nel lookup normale; 1 efetch solo se esplicitamente richiesto |
| Batch SQLite di 1.100 richieste duplicate gnomAD, un allele unico | 3 SELECT per blocchi da 500 | **1 SELECT**, 1.100 risultati associati all'ordine originale |
| Batch ClinVar di 1.100 richieste, due chiavi ripetute | Deduplicazione già presente | 1 SELECT, conservata e verificata |

Il confronto del dettaglio usa la stessa route e fixture: `refresh_clinvar=True`
riproduce il precedente `refresh=True` sistematico; il default finale riusa la
cache. Il test verifica inoltre uguaglianza dell'evidenza e della priorità tra
lista e dettaglio, ALT G/T distinti e corretta associazione a due campioni.

## 7. Verifiche e risultati

La suite estesa comprende provider, query/API, indexer/store, prioritizzazione,
CACHE-02, contesto ACMG, meccanismi, PVS1 e fixture molecolari:
**440 passed, 1 skipped; 185 subtests passed**, in 17,56 secondi. XML conclusivo
in `/tmp/helper-cache03/final-regression.xml`. Il test saltato è il controllo
Chrome opzionale `test_new_calculator_panel_opens_and_explains_requirements`.

La verifica aggiuntiva dei provider e dell'integrazione HTTP dopo l'ultimo
controllo di compatibilità delle rappresentazioni ClinVar usa
`/tmp/helper-cache03/final-access.xml`: **125 passed**, in 2,96 secondi.
Le fixture coprono TTL positivi/negativi,
refresh esplicito, cache incompleta, breakdown opzionale/vuoto, errori di rete e
validazione, conservazione dell'evidenza precedente, NOT_FOUND, multialleliche,
offline, release/assembly gnomAD, copertura e deduplicazione SQL. I vecchi payload
senza i nuovi metadati vengono letti con lo schema SQLite esistente. Le query
ClinVar precedentemente ammesse non sono limitate dalla disponibilità di ga2:
testate anche rappresentazioni con indel, ALT simbolica e REF N. `compileall`
sui cinque moduli applicativi modificati e `git diff --check` sono passati.

Comando della suite estesa, dalla radice del repository:

```bash
PYTHONPATH=helper_next/src python -m pytest -q \
  helper_next/tests/test_clinvar.py helper_next/tests/test_gnomad_frequency.py \
  helper_next/tests/test_variant_query.py helper_next/tests/test_variants_api.py \
  helper_next/tests/test_variant_indexer.py helper_next/tests/test_variant_store.py \
  helper_next/tests/test_prioritization.py helper_next/tests/test_biological_identity.py \
  helper_next/tests/test_acmg_context.py helper_next/tests/test_acmg_pvs1.py \
  helper_next/tests/test_acmg_mechanism_assessment.py helper_next/tests/test_acmg_mechanisms.py \
  tests/test_pvs1_calculator.py tests/test_pvs1_impact.py \
  tests/test_pvs1_models.py tests/test_pvs1_molecular.py
```

La prima esecuzione API in sandbox si è bloccata nel percorso AnyIO, già descritto
nel report di cleanup, ed è stata interrotta. I test API sono stati rieseguiti con
successo fuori sandbox. Un primo tentativo con offline imposto a tutta la suite
ha impedito anche gli HTTP simulati dei test provider; la verifica corretta usa
offline soltanto nelle fixture pertinenti. Warning preesistente `python_multipart`.

## 8. Limiti e preparazione a CACHE-04

- Nessuno storico delle revisioni: il singolo record SQLite resta aggiornabile;
  l'ultima evidenza è conservata in caso di errore, non dopo un aggiornamento
  riuscito con contenuto differente.
- `last_error` sopravvive nel record quando è disponibile un'evidenza valida;
  errori senza evidenza non sono memorizzati come record negativi. Non sono stati
  introdotti retry persistenti, lease, single flight o scheduler.
- Release gnomAD controllata contro configurazione, payload e colonna SQLite;
  il provider upstream non certifica qui una release live indipendente dal
  dataset ID. Versionamento/fingerprint più forti restano al task successivo.
- Restano i limiti del matcher e degli endpoint remoti esistenti; nessun liftover
  implicito o equivalenza fra assembly. Nessuna migrazione delle chiavi a ga2.
- Le annotazioni VCF originali rimangono nell'indice con il proprio contesto e
  non vengono presentate come una revisione ClinVar dinamica riuscita.
- Nessun test contro servizi biologici live, job Nextflow o verifica browser
  interattiva. La suite completa dell'intero repository non è necessaria a questo
  perimetro; sono stati eseguiti i test pertinenti e le regressioni ACMG/PVS1.
- CACHE-04 potrà usare disponibilità, freschezza, date, identificativi e ga2
  informativo per progettare revisioni e snapshot. Non è stato iniziato alcun
  lavoro di CACHE-04 o prefetch/batch orchestration.
