# TASK 22 — contratto ACMG verificato e richieste di estensione

Contratto ispezionato in `/home/jarvis/git/acmg-engine`: `api/routes.py`,
`api/schemas.py`, `domain/{evidence_packet,interpretation,criteria,profiles,
classification,comparison,variant,population_ci}.py`, `docs/openapi.json`.
Nessuna modifica a quel repository. API verificata: **v1**, schema **1.0**,
pacchetto **evidence-packet-v1**, risultato **evidence-packet-result-v1**.

## API attualmente utilizzate

| Metodo / percorso reale | Uso HELPER |
| --- | --- |
| GET /health | Identità servizio e disponibilità |
| GET /v1/capabilities | Versioni, strategie eseguibili, abilitazione research |
| GET /openapi.json | Presenza endpoint, schemi e enum disponibili |
| GET /v1/criteria | Inventario completo e metadati di copertura scientifica |
| GET /v1/profiles/applicable | Coppia esatta namespace/ID gene e malattia |
| POST /v1/evidence-packets/interpret | Pacchetto congelato e configurazione esplicita |
| POST /v1/interpretations/compare | Stesso snapshot e configurazioni esplicite |

Il test sintetico PM2 interroga anche l'endpoint reale POST /v1/interpretations.
Non esiste un endpoint GET per recuperare interpretazioni per ID: HELPER salva
localmente e integralmente le risposte ricevute.

Strategie reali: `CUSTOM_ALGORITHMIC`, `CLINGEN_GUIDED`. ACMG 2015 è un metodo
di classificazione/profilo, non una terza strategia inventata dal client.
La classificazione è vincolata al profilo; HELPER mostra il metodo e non lo
sostituisce. Profili DRAFT/DEPRECATED e combinazioni tra strategie incompatibili
sono rifiutati. Specializzazioni e versioni richiedono selezione esplicita.

## Dati effettivamente esposti

`CriterionResult` espone status, activation (configurazione), reason_code,
strength/original_strength/modified_strength, rules, supporting_evidence_ids,
excluded_evidence, explanation, warnings, required_manual_actions, provenance.
Audit opzionali: population, clingen, computational, pvs1, functional, family,
molecular, missense, ps4, phenotype, benign, splice_equivalence.

`population_upper_ci` contiene osservazione, AF, limite binomiale e Poisson,
soglia e booleani primary/sensitivity/method_discordance. Questi valori restano
stringhe e booleani originali; HELPER non calcola né arrotonda confronti.
Metodo primario/sensibilità e operatore provengono dalla regola del risultato.

Il candidato MET deriva dallo status dell'evaluatore. Per gli stati irrisolti
l'attivazione candidata resta NOT_RECORDED, non falsa. I candidati dei singoli
metodi PM2 rimangono visibili nell'audit anche con MANUAL_REVIEW_REQUIRED.
Il contributo effettivo proviene da classification.included_criteria e
effective_strengths. EXCLUDED_BY_DEPENDENCY è mostrato soltanto se una
DependencyAssessment esplicita EXCLUDE coincide con una criterion exclusion;
le altre esclusioni mantengono il motivo originale senza riclassificarlo.
PP5/BP6 sono etichettati DEPRECATED; lo status originale resta visibile.

VCEP mapping espone definizione originale/modificata, modification_types,
applicabilità, evidenza richiesta, dipendenze, esclusioni e riferimenti. La UI
mostra solo queste categorie, senza costruire modifiche a partire dalle soglie.
Il confronto visualizza branches, comparisons e not_comparable del motore.

## Limiti verificati — inspector PARTIAL

1. Nell'OpenAPI attuale RuleProfile, CriterionResult e InterpretationResult
   risultano oggetti aperti senza campi descritti, sebbene i modelli interni
   e i payload runtime siano strutturati. La compatibilità strutturale completa
   non è verificabile dal solo schema pubblicato.
2. ProfileCollection non espone ProfileReference autorevoli. Il client usa la
   canonicalizzazione di trasporto verificata di RuleProfile.reference(): JSON
   ordinato, SHA256, esclusione di overridable_criteria se vuoto. Nessuna regola
   scientifica viene risolta in HELPER, ma questa dipendenza dal serializzatore
   va sostituita con riferimenti forniti dal servizio.
3. Non esiste una traccia universale per tutti i criteri con formula, input,
   output, operatore e condizioni qualitative. Esistono audit specialistici,
   mostrati integralmente; i campi assenti restano NOT_RECORDED. Una struttura
   scientifica più dettagliata non può essere ricostruita nel frontend.
4. Non esiste una catena uniforme parent-rule → override → effective-rule né
   un primo stadio scientifico fallito comune a tutti gli evaluatori. La UI
   distingue il primo dato non registrato dai motivi scientifici del motore.

La normalizzazione **non richiede un nuovo endpoint**: la verifica FASTA e la
normalizzazione degli alleli esistenti in HELPER soddisfano il contratto. In
assenza di riferimento, il servizio rifiuta evidenza strutturata con
PACKET_NORMALIZATION_REQUIRED; HELPER conserva il pacchetto e segnala il requisito.

## Proposta versionata per ACMG Engine — non implementata

Proposta `workbench-audit-v1`, schema di trasporto **1.1**, stessi endpoint v1.
Richiede aggiornamento esplicito del controllo di compatibilità di HELPER dopo
l'implementazione e i test nel repository scientifico.

* Pubblicare schemi OpenAPI completi dei tre modelli oggi opachi, mantenendo
  campi, enum e nullability dei modelli reali.
* Aggiungere a ProfileCollection `profile_references: ProfileReference[]`,
  affiancato a profiles; ciascun riferimento deve essere esattamente quello
  restituito da RuleProfile.reference(), non calcolato dal chiamante.
* Aggiungere a CriterionResult `workbench_audit` opzionale con
  `schema_version: "workbench-audit-v1"` e `availability` per ogni sezione:
  `RECORDED | NOT_RECORDED | NOT_APPLICABLE`.
* `candidate` ed `effective`: status, active nullable, strength nullable,
  esclusioni tipizzate con reason_code, dependency_id e rule reference. I
  candidati numerici primario/sensibilità devono restare separati dall'esito
  del safeguard; nessuna attivazione automatica in METHOD_DISCORDANCE.
* `calculations[]`: calculation_id, metric, input_evidence_ids, input_paths,
  input_values, calculated_value, formula_id/version, formula_text nullable,
  method, operator, threshold, condition_result nullable, rule_reference,
  source_id/version. Decimali come stringhe, senza arrotondamento scientifico.
* `conditions[]`: condition_id, observed_value, expected_value/rule_reference,
  outcome `PASS | FAIL | UNKNOWN`, evidence_ids, explanation, branch_id.
* `rule_lineage[]`: organization, guideline_id/version, profile_reference,
  source_document/section, parent_rule_reference nullable, applied_override
  nullable, effective_rule_reference, scientific_review_status. La risoluzione
  resta esclusivamente nel registro ACMG Engine.
* `first_failure`: stage nullable, reason_code, evidence_ids, input_paths,
  explanation. Gli stadi autorevoli iniziano da EVIDENCE_PACKET; RAW_VCF e
  NORMALIZED_ANNOTATION rimangono responsabilità locale di HELPER, collegati
  tramite source checksum/field paths, senza invio del VCF intero.

Verifiche richieste al servizio: JSON schema dei payload runtime; riferimenti
profilo identici; campi mancanti espliciti; replay deterministico; confronto
stesso snapshot; esclusioni e forze candidate/effettive; fixture sintetica
AC=1/AN=118595 con entrambi i limiti originali e nessun contributo PM2.
