# Task 28A/28C — stato integrazione HELPER

> Nota 2026-10-29: documento storico. La cache pubblica dei meccanismi e il relativo assessment locale sono conservati; Workbench, Coordinator/Assembler, contratti e valutazioni del servizio esterno descritti qui sono stati rimossi. Stato operativo: [HELPER_STRUCTURAL_CLEANUP.md](HELPER_STRUCTURAL_CLEANUP.md).

Data: 2026-10-28. Esito complessivo: **PARTIALLY_IMPLEMENTED**.
Le modifiche sono implementate nel codice HELPER e riesaminate staticamente;
non si dichiara il task VALIDATED o COMPLETED. Nessun test è stato eseguito
in questa sessione. Le verifiche storiche riportate più sotto non validano questo stato.

## Stato attuale

| Area | Esito | Stato del codice e limite |
| --- | --- | --- |
| Coordinator / confidence / scope | IMPLEMENTED | Associazione distinta da meccanismo; assertions ed evidenze favorevoli/contrastanti conservate; nessun calcolo ACMG. |
| Priorità VCEP | PARTIALLY_IMPLEMENTED | Precedenza per assertions normalizzate esplicite e approvate, anche GoF/DN/OTHER; fonte verificabile non disponibile negli adapter attuali. |
| Acquisizione biologica VCEP reale | BLOCKED | I profili di classificazione non sostituiscono uno statement molecolare. Nessuna assertion inventata. |
| EvidenceContract 1.1 | IMPLEMENTED | Serializzazione, assessment anche senza transformer nonsense, negoziazione preventiva della versione; legacy senza assessment resta 1.0. Compatibilità reale non verificata. |
| Classify variant / compare | PARTIALLY_IMPLEMENTED | Collegati al Coordinator e ai classificatori Engine esistenti tramite il packet normalizzato; contratto completo e correzioni conservati nell'audit. |
| Compatibilità operativa Engine | BLOCKED | Ultimo stato noto: Engine effettivo 1.0; nessuna nuova ispezione o esecuzione. Schema non compatibile o audit PVS1 assente impediscono la presentazione come risultato Task 28 integrato. |
| Workbench / riepilogo / report | IMPLEMENTED | Stati PVS1, meccanismo/confidence, calculated/applied strength, warning, review, ragione, provenance e trace; EXPLORATORY distinto ed esplicitamente senza contributo. |
| Verifica funzionale | BLOCKED | Non autorizzata in questa sessione. Solo analisi statica e modifiche nel repository HELPER. |

IMPLEMENTED indica la presenza del codice, non una validazione del comportamento.
L'Engine non è stato modificato; nessun classificatore, punteggio Tavtigian, strength
o decision tree VCEP è stato introdotto in HELPER.

## Deliverable e file

- [TASK28A_MECHANISM_CONFIDENCE.md](TASK28A_MECHANISM_CONFIDENCE.md): precedenza VCEP,
  requisiti di provenance e limiti delle inferenze ClinVar/gnomAD.
- [TASK28C_HELPER_INTEGRATION.md](TASK28C_HELPER_INTEGRATION.md): flusso Classify variant,
  contratto 1.1/legacy 1.0, visualizzazione, elenco completo dei file e attività
  separate per ACMG Engine.
- Questo report: stato attuale, cache e storico delle verifiche precedenti.

File principali: nuovo `core/acmg_classification.py`, aggiornamenti al Coordinator,
assessment e client Task 22, API `acmg.py`, nuovo renderer condiviso `acmg-pvs1.js`,
renderer Task 22 e classificazione, righe del Workbench e test sintetici predisposti.
I percorsi completi sono nel deliverable 28C. Le modifiche preesistenti sono conservate.

## Cache: lettura statica dei manifest

`TASK27A3_FULL_POPULATION_REPORT.json` riporta 15.577 associazioni valide e SUCCESS;
il preflight registrava già 20 matrici e 20 snapshot. Nel report storico risultano
15.597 matrici correnti e altrettanti snapshot dopo il popolamento. Questi dati
non dimostrano che la differenza di 20 sia costituita da record storici, né
identificano quali associazioni siano nuove, riutilizzate o storiche.
Ripartizione: **NON DETERMINATA**. Nessuna query al database, scansione massiva,
ricostruzione dei conteggi o sincronizzazione è stata eseguita; ciò non blocca
le modifiche applicative.

## Verifiche della sessione e passi successivi

Solo parsing AST Python e controllo di sintassi JavaScript dei moduli modificati;
nessun import dell'applicazione. Test nuovi/adattati lasciati da eseguire in seguito
su autorizzazione: scope e precedenza VCEP, blocco preventivo della versione,
conservazione del contratto e delle correzioni, schema del classificatore e risposta
PVS1 incompleta. I test di integrazione con Engine 1.1 e la visualizzazione reale
restano da concordare; nessuna suite già superata o bloccata è stata rieseguita.

Nessun pytest, test HTTP, Chrome/browser, E2E, benchmark, server, sync o popolamento.
Nessun comando fuori sandbox, richiesta di autorizzazione o commit. Nessun intervento
nel repository ACMG Engine o nell'area Engine temporanea.

## Appendice — report storico del 2026-10-27

Quanto segue fotografa lo stato precedente all'intervento del 2026-10-28.
Le diciture NON IMPLEMENTATO di questa appendice descrivono quel precedente stato;
per l'esito attuale fanno fede la tabella e i deliverable sopra.

### Arresto e verifica statica precedenti

Data: 2026-10-27. Stato: **INCOMPLETO — non utilizzabile come integrazione verificata**.
Alla richiesta di arresto sono cessati test, tentativi HTTP e verifiche fuori sandbox.
Successivamente sono state effettuate soltanto letture statiche e la stesura di questo report.
Nessun commit. Le modifiche preesistenti degli altri task sono state conservate.

## Collocazione effettiva dei file

**HELPER**, sotto `helper_next/`:

- `src/helper_next/core/acmg_mechanism_assessment.py` — nuovo assessment biologico.
- `src/helper_next/core/acmg_evidence.py` — coordinamento e trasporto dell'assessment.
- `src/helper_next/core/acmg_pvs1.py` — serializzazione e verifica dello scope.
- `src/helper_next/core/acmg_task22.py` — contratto 1.1, discovery e riferimenti ai profili.
- `src/helper_next/api/acmg_task22.py` — selezione del profilo e metadati nell'export CSV.
- `src/helper_variants/web/static/acmg-task22.js` — visualizzazione degli esiti Engine.
- `tests/conftest.py` — isolamento della cache nei test.
- `tests/test_acmg_evidence.py`, `tests/test_acmg_task22.py` — runtime Engine di test configurabile.
- `tests/test_acmg_pvs1.py` — aspettativa UNKNOWN aggiornata a INACTIVE.
- `tests/test_acmg_mechanism_assessment.py`, `tests/test_acmg_task28_browser.py` — nuovi test.
- `docs/TASK28_STATUS.md` — questo report.

**ACMG Engine effettivo**, `/home/jarvis/git/acmg-engine`: **nessuna modifica Task 28 applicata**;
working tree risultato pulito nella verifica statica finale. Il contratto effettivo resta 1.0.

Le modifiche seguenti esistono soltanto nell'area temporanea `/tmp/helper-task28-engine`:

- `src/acmg_engine/domain/{pvs1,evidence_contract,criteria_protocol}.py`.
- `src/acmg_engine/pvs1/{mechanism_confidence,disease_mechanism,evaluator}.py`.
- `src/acmg_engine/decision/workspace.py`, `src/acmg_engine/services/criteria_protocols.py`.
- `tests/test_task28_pvs1_confidence.py`, `tests/test_task22_contract.py`.
- `scripts/export_evidence_contract.py`.
- `docs/openapi.json`, `docs/schemas/evidence-contract-1.1.json` e aggiornamenti agli schemi
  `criteria-matrix-1.0.json`, `criterion-execution-1.0.json`, `decision-tree-1.0.json`.
- `docs/examples/task28/profiles/helper-pvs1-experimental-classify.json` e
  `helper-pvs1-experimental-review-only.json`.

Questi artefatti temporanei non sono una modifica installata o una release dell'Engine.

## Funzioni implementate e limiti architetturali

HELPER produce assertions separate, confidence DEFINITIVE/INFERRED/DISPUTED/UNKNOWN,
scope, stato dell'associazione distinto dal conflitto sul meccanismo, riferimenti alle
fonti, limiti e provenance. Non assegna strength, punti ACMG o classificazioni.
Sono preservati gli scope di malattia/ereditarietà; l'Assembler rifiuta un assessment
per uno scope differente. GenCC validity e constraint isolato non vengono convertiti in LoF.

L'inferenza implementata usa HI ClinGen 3 con identità qualificata; resta gene-level
senza qualificazione della malattia e dell'ereditarietà. Nei dati disponibili molte
identità Dosage/constraint non sono riconciliate con HGNC. La distribuzione ClinVar LoF
necessaria per ulteriori inferenze non è disponibile. Le fixture non sono risultati reali.

Nell'Engine **temporaneo**, la policy esplicita `HELPER_EXPERIMENTAL_1.0` riusa gli alberi
tecnici e distingue strength calcolata/applicata. INFERRED/DISPUTED conservano warning,
evidenze e revisione richiesta. EXPLORATORY ha `active=false`, `applied_strength=null`,
`classification_eligible=false`; il risultato legacy non resta MET e le dipendenze del
percorso Task 22 non ricevono un PVS1 effettivamente attivo. Le esclusioni tecniche
non vengono aggirate assegnando EXPLORATORY.

**VCEP:** nell'Engine temporaneo rimangono prioritari gli override selezionati e le
esclusioni già esistenti. In HELPER manca invece la gestione della precedenza di
assertions di meccanismo VCEP pertinenti: requisito **NON IMPLEMENTATO**, bloccante
per dichiarare completa la precedenza VCEP lungo l'intero flusso.

**Classificazione:** il nuovo assessment è collegato al percorso Task 22 dei criteri,
che non produce una categoria finale. `api/acmg.py::execution_inputs` continua a
preparare il packet del percorso “Classify variant” senza chiamare il nuovo Coordinator.
Il collegamento applicativo assessment → classificazione ACMG/Tavtigian è quindi
**NON IMPLEMENTATO / NON VERIFICATO end-to-end**. I risultati delle fixture sul
classificatore Engine temporaneo non dimostrano un contributo nell'applicazione reale.
Anche il riepilogo della classificazione legacy non è stato aggiornato ai nuovi metadati.

## Contratto e cache

L'Engine temporaneo accetta 1.0 e 1.1; il nuovo assessment richiede 1.1. Le serializzazioni
legacy dei meccanismi e della policy standard preservano l'assenza dei nuovi campi.
Sono passate verifiche su input legacy e sul nuovo contratto con il modello Pydantic reale
temporaneo. Questo non rende l'Engine effettivo 1.0 compatibile con input 1.1.

**Blocco operativo:** HELPER può ora emettere 1.1 mentre l'Engine effettivo accetta solo
1.0. Non è stato implementato un controllo preventivo completo che impedisca tale
incompatibilità prima dell'invio. L'integrazione corrente non va dichiarata pronta.

Dalle letture della cache già effettuate prima dell'arresto risultano 15.597 righe
in `gene_disease_mechanisms` e 15.597 in `mechanism_snapshots`. L'ultimo bulk
`f760716ded064eb4a163a3ab73f45554` risulta COMPLETED con 15.577 SUCCESS.
Il report 27A.3 indica anch'esso 15.597 matrici **correnti**.
Non sono dunque 15.597 nuove matrici Task 28. La differenza di 20 non dimostra
che si tratti di snapshot storici. La ripartizione nuove/riutilizzate/storiche è
**NON VERIFICATA**: non sono state eseguite ulteriori query dopo la richiesta di arresto.

## Verifiche già concluse prima dell'arresto

- HELPER: **65 passati, 5 saltati** nella selezione Evidence/PVS1/Task22/assessment,
  usando il runtime separato e i sorgenti dell'Engine temporaneo.
- Engine temporaneo: **216 passati, 2 deselected** nella selezione PVS1/contratto/protocolli
  con esclusione dei test API; **19 nuovi test Task 28 passati** in esecuzione separata.
  I conteggi si sovrappongono e non vanno sommati come test distinti.
- Workbench: **1 test Chrome passato**, con risposte Engine sintetiche esplicitamente
  identificate: ACTIVE/INACTIVE/EXPLORATORY, warning, evidence/trace e risultato immutato.
  Non era un test HTTP end-to-end con l'Engine effettivo.
- Ruff e mypy sugli otto moduli Engine interessati avevano superato i controlli prima
  degli ultimi raccordi; non sono stati ripetuti sullo stato finale.

Non completati: il test HTTP PVS1 Engine si è bloccato nella sandbox nel percorso
ASGI/AnyIO ed è stato interrotto; la causa definitiva è **NON VERIFICATA**. Non è stato
rieseguito fuori sandbox. I cinque test HELPER saltati richiedevano opt-in per servizi reali.
Nessuna suite completa né verifica dei servizi reali è stata conclusa per Task 28.
Gli ultimi ritocchi non hanno ricevuto una ripetizione integrale dei controlli, in
rispetto dell'arresto richiesto. Nessuna validazione clinica è attestata.

## Attività residue

1. Portare e revisionare le modifiche temporanee nell'Engine effettivo, solo con una
   successiva autorizzazione; gestire preventivamente la compatibilità 1.0/1.1.
2. Integrare in HELPER la precedenza delle assertions di meccanismo VCEP pertinenti.
3. Collegare il nuovo assessment al percorso di classificazione esistente, mantenendo
   le decisioni nell'Engine; aggiornare il riepilogo legacy e la revisione separata.
4. Verificare nuove/riutilizzate/storiche nella cache senza confondere matrici correnti
   e snapshot; mantenere espliciti i limiti delle identità e delle inferenze disponibili.
5. Completare soltanto le verifiche mirate concordate, inclusi esclusioni VCEP,
   compatibilità e classificazione end-to-end; **nessun nuovo test senza autorizzazione**.
6. Produrre i tre deliverable finali TASK28A/TASK28B/TASK28C con esiti effettivi.
