# Task 28C — Integrazione HELPER / ACMG Engine

> Nota 2026-10-29: documento storico. La cache pubblica dei meccanismi e il relativo assessment locale sono conservati; Workbench, Coordinator/Assembler, contratti e valutazioni del servizio esterno descritti qui sono stati rimossi. Stato operativo: [HELPER_STRUCTURAL_CLEANUP.md](HELPER_STRUCTURAL_CLEANUP.md).

Data: 2026-10-28. Stato: **PARTIALLY_IMPLEMENTED**; compatibilità operativa con
l'Engine **BLOCKED** fino alla disponibilità delle operazioni e degli schemi
compatibili. Nessun test eseguito in questa sessione.

## Percorso Classify variant

`api/acmg.py::execution_inputs` usa ora `Task22Client` e il nuovo ponte
`core/acmg_classification.py`. Il percorso riusa i classificatori esistenti
dell'Engine, senza classificatore HELPER:

1. Selezione di variante, annotazione, trascritto e contesto già salvati nel workspace.
2. Selezione di profili e protocollo Engine; per CLINGEN_GUIDED il default di
   trasporto è CLINGEN_GENERAL, per ACMG_2015 è ACMG_2015. Strategie custom o
   confronti eterogenei richiedono un protocollo esplicito.
3. `EvidenceCoordinator` acquisisce i requisiti Engine, riusa Source Manager e
   cache; la richiesta del meccanismo usa CACHE_ONLY.
4. `EvidenceAssembler` produce e sottopone all'Engine il contratto per la
   validazione autorevole. L'assessment viene conservato anche per conseguenze
   diverse da nonsense attraverso un'EXTENSION con annotazione selezionata,
   identità della variante, evidenze e provenance.
5. Il ponte conserva il contratto completo e trasferisce i suoi valori normalizzati
   nello snapshot del packet richiesto dal classificatore esistente.
   Il formato packet rimane quello dichiarato dall'Engine: non viene inventato
   un endpoint di classificazione EvidenceContract né uno schema packet 1.1.
6. `/v1/evidence-packets/interpret` o `/v1/interpretations/compare` viene chiamato
   soltanto se il relativo schema OpenAPI accetta il payload completo.
7. HELPER mostra la classificazione restituita dall'Engine. Con PVS1 che trasporta
   confidence assessment, una risposta priva di `criterion_results[].pvs1_evaluation`
   e dei metadati richiesti viene archiviata come `classification_integration_failure`
   e segnalata come blocco, senza presentarla come classificazione Task 28 integrata.

Il pulsante **Open Classify variant** rende raggiungibile il percorso dal workspace
Task 22; la matrice Task 22 continua a essere una valutazione dei criteri, senza
categoria finale. Il selettore Criteria protocol permette una scelta esplicita.
Le categorie finali, l'attivazione, le strength, la riconciliazione delle dipendenze
e i calcoli ACMG/Tavtigian restano interamente nell'Engine.

## EvidenceContract 1.1 e compatibilità

Non sono stati duplicati modelli Pydantic dell'Engine. Si mantengono dizionari di
trasporto e validazione contro schemi/operazioni dichiarati dall'Engine.

Il contratto diventa `evidence-contract-1.1` quando contiene il confidence
assessment PVS1 o l'EXTENSION `helper-mechanism-assessment`. Sono conservati
variante normalizzata, trascritto/conseguenza, gene–malattia–ereditarietà,
confidence, association status, scope, assertions, supporting/conflicting evidence,
mapping uncertainty, snapshot e provenance. I fatti tecnici nonsense/PTC già
disponibili rimangono nel transformer PVS1 esistente. HELPER non determina NMD,
strength o attivazione del criterio.

I payload legacy privi dei nuovi assessment mantengono 1.0. È disponibile anche
la selezione esplicita della versione nel serializer; chiedere 1.0 con nuovi
assessment produce `CONFIDENCE_REQUIRES_CONTRACT_1_1`, senza eliminare dati.
`Task22Client` legge lo schema autorevole e controlla enum/const della versione
prima del POST di validazione: incompatibilità → `ENGINE_CONTRACT_VERSION_UNSUPPORTED`.
La discovery espone le versioni dichiarate e accetta Engine 1.0 e/o 1.1.

**Limite esterno:** il report precedente descrive l'Engine effettivo come 1.0 e
le modifiche 1.1 come temporanee. In questa sessione non è stato interrogato,
avviato o modificato l'Engine, né sono stati letti i sorgenti esterni. Non si
attesta che il suo classificatore consumi il nuovo assessment. L'accettazione
dello schema non dimostra da sola l'applicazione delle nuove regole scientifiche.

Le attività separate per il progetto Engine sono:

- Pubblicare EvidenceContract 1.1 e validazione/schema compatibili.
- Fare consumare gli assessment dal percorso reale dei classificatori esistenti,
  esponendo anche nel risultato finale l'audit PVS1 coerente con quello Task 22:
  status, active, mechanism/confidence/scope, calculated/applied strength,
  classification eligibility, warnings, requires_review, reason, source evidence,
  decision trace. Aggiornare gli schemi OpenAPI del packet se necessari.
- Applicare nel motore le regole di eleggibilità e la precedenza delle regole
  VCEP. HELPER non sostituisce tali decisioni.

## Risultati e revisione

`acmg-pvs1.js` è condiviso da Task 22 e dal riepilogo di classificazione. Mostra
ACTIVE/INACTIVE/EXPLORATORY esattamente come registrati, meccanismo/confidence/scope,
strength calcolata/applicata, motivo, warning e richiesta di revisione.
EXPLORATORY è presentato come teorico, senza contributo alla classificazione.
INFERRED/DISPUTED hanno un warning visibile anche nel riepilogo, senza dipendere
dalla sola presenza di un warning testuale Engine. Sono consultabili evidenze,
provenance automatica, valori, soglie e decision trace. Le righe dei criteri usano
lo stato PVS1 esplicito, evitando di presentare EXPLORATORY come MET/ACTIVE.
Il report scaricabile include questi metadati e l'audit del Coordinator.

Le correzioni richiedono ancora provenienza MANUAL, versione, checksum e motivo;
il ponte conserva `automatic_contract`, contratto finale e correzioni separati.
Le reviews restano append-only. Nessun risultato automatico viene sovrascritto.

Resta il limite del transformer tecnico esistente: il percorso specializzato
produce fatti verificati per nonsense, non una nuova implementazione tecnica
frameshift/splice/CNV. Per questi casi l'assessment di meccanismo è conservato,
ma non viene inventata un'osservazione tecnica sufficiente per PVS1.

## File modificati in questa sessione

Sotto `helper_next/src/helper_next/`:

- `api/acmg.py`, `api/acmg_task22.py`.
- `core/acmg_classification.py` (nuovo), `core/acmg_evidence.py`,
  `core/acmg_mechanism_assessment.py`, `core/acmg_task22.py`, `core/acmg_workbench.py`.

Sotto `helper_next/src/helper_variants/web/static/`:

- `acmg-pvs1.js` (nuovo), `acmg-task22.js`, `acmg-workbench.js`.

Test predisposti o adattati, **non eseguiti**:

- `helper_next/tests/test_acmg_classification.py` (nuovo).
- `helper_next/tests/test_acmg_mechanism_assessment.py`.
- `helper_next/tests/test_acmg_task22.py`, `helper_next/tests/test_acmg_workbench.py`.

Documentazione: questo file, [TASK28A_MECHANISM_CONFIDENCE.md](TASK28A_MECHANISM_CONFIDENCE.md)
e [TASK28_STATUS.md](TASK28_STATUS.md). Le modifiche preesistenti degli altri task
sono state conservate.

## Verifiche e problemi aperti

Eseguiti soltanto parsing AST dei file Python interessati e controllo sintattico
dei tre moduli JavaScript modificati. Nessun import applicativo, pytest, HTTP,
Chrome/browser, E2E, benchmark, server, sincronizzazione, popolamento o commit.
Nessun comando fuori sandbox o richiesta di autorizzazione.

Dopo autorizzazione: verifiche mirate dei nuovi casi VCEP e dei blocchi 1.0/1.1;
contratto reale 1.1 e ponte packet; classificazione con l'Engine effettivamente
aggiornato e i suoi classificatori; EXPLORATORY escluso dalla categoria finale;
warning INFERRED/DISPUTED, correzioni/reviews separate e provenance nel riepilogo.
Non è pianificata una ripetizione automatica delle suite già passate o bloccate.
Gli altri limiti sulle inferenze e sulla fonte VCEP sono descritti nel report 28A.
