# Audit delle fonti HELPER e dell’Evidence Contract ACMG Engine

Data: **26 ottobre 2026**. [Manifest machine-readable](TASK23_DATA_EVIDENCE_AUDIT.json).
L’audit descrive il codice e le cache locali osservate, non certifica validità
clinica, completezza scientifica o disponibilità attuale dei servizi remoti.

## Perimetro e riproducibilità

- HELPER HEAD: `6a2d0d458448237e8d2b6be5f78a97e3cbaec794`, con modifiche locali
  Task 23 non ancora committate. Il manifest conserva i digest dei sorgenti letti.
- ACMG Engine HEAD: `4640af454c20502ebd09a1da074009959bc5b730`, worktree pulito
  all’osservazione; package installato `0.1.0`, Pydantic `2.14.1`.
- Consultati sorgenti attivi, registro fonti, schema esportato, modelli Pydantic,
  OpenAPI, catalogo requirements, esempi sintetici e soli aggregati delle cache.
- Nessuna richiesta HTTP, sincronizzazione, ispezione di record di pazienti,
  valutazione di criteri, lettura/hash del FASTA o suite pesante.
- Cache e configurazione sono quelle risolte dal processo dell’audit. Un server
  HELPER avviato con ambiente diverso potrebbe usare altri percorsi/dataset.

## 1. Fonti registrate e stato locale

Il [registro](../helper_next/src/helper_variants/source_registry.py) espone
11 sorgenti. `on_demand` descrive la modalità d’uso: non è un health check remoto
né una verifica della freschezza di tutti i record.

| Fonte | Accesso implementato | Versione realmente identificabile | Dati locali osservati | Trasferimento automatico al contratto Task 22 |
| --- | --- | --- | --- | --- |
| ClinVar | NCBI E-utilities, arricchimento dell’allele esatto | Nessuna release globale numerata acquisita dal client; date dei record | 38 entry cache; ultima acquisizione 21/10; massimo `record_updated` 27/09/2026 | Nessuna evidenza tipizzata; annotazioni VCF conservate nel workspace |
| GenCC | Export CSV | Assertion individuali con ID/versione; snapshot locale 21/10 | 30.345 assertion; cache pronta, non scaduta; massimo submitted run 11/10 | Gene/malattia e, se selezionata, ereditarietà; non tutta la curazione di validità |
| Gene2Phenotype | Export completo dei pannelli | Record con ID, confidence, requisito allelico, meccanismo, pubblicazioni e last review; snapshot locale | 3.856 record; snapshot 21/10, cache non scaduta | Meccanismo non trasportato dall’adapter attuale |
| HPO | `phenotype.hpoa` e `hp.obo` da release/latest | Release upstream non conservata; conservati snapshot e fonte delle annotazioni | 268.791 righe di associazione malattia–fenotipo, non 268.791 termini; snapshot 21/10 | Nessun `PHENOTYPIC`/`FAMILY` strutturato |
| ClinGen Dosage Sensitivity | Export TSV GRCh38 | Data di valutazione per record e PMIDs; snapshot locale, senza release globale numerata | 1.537 record; massimo last evaluated 14/10; snapshot 21/10 | Non trasportato come valutazione di meccanismo PVS1 |
| Orphadata | XML Product 1 | Release upstream non conservata; mapping e qualificatori originali | 15.318 righe `disease_codes`, non numero di malattie; snapshot 21/10 | Supporto alla consultazione/mappatura; nessuna observation dedicata |
| gnomAD constraint | GraphQL, ricerca per gene GRCh38 | UI/codice dichiarano v4.1.2; la query non verifica una release restituita dal servizio | 10 record; ultimo aggiornamento 21/10; durata cache 30 giorni | Non trasferito in una valutazione del meccanismo LoF |
| gnomAD frequenze | GraphQL genomes, allele e coverage del locus | Configurati `gnomad_r2_1`/2.1.1 per GRCh37 e `gnomad_r4`/4.1 per GRCh38 | 14 entry; **release effettivamente in cache: solo 2.1.1** | `POPULATION`, solo per lookup già disponibile e coerente con l’allele |
| NCBI Variation Services | SPDI API v0, accession RefSeq per assembly | API/accession fissi; nessuna release globale di database | 22 entry di proiezione; ultima acquisizione 21/10 | Non applica automaticamente liftover al payload ACMG |
| PanelApp | API/catálogo e dettaglio pannelli versionati | Versione per pannello | 433 pannelli; sync 06/10; **cache scaduta** secondo TTL di 24 ore | Selezione/prioritizzazione, non evidenza ACMG tipizzata |
| ACMG Secondary Findings | Liste incorporate | v3.0, 3.1, 3.2, 3.3; versione corrente locale 3.3 | 84 geni nella lista 3.3 | Nessuna evidenza PVS1 o valutazione di patogenicità generata |

Per GenCC/G2P/HPO/dosage/Orphadata la sincronizzazione condivisa è
`2026-10-21T12:33:28Z`. I conteggi sono righe/entry di tabelle differenti e non
sono confrontabili come numero di evidenze indipendenti. Le date massime dei
record non attestano una release completa del database. Gli orari esatti e gli
URL osservati sono nel manifest JSON.

### Identificazione delle fonti nel codice

- [gene_phenotype.py](../helper_next/src/helper_variants/gene_phenotype.py): GenCC,
  HPO, G2P, dosage, Orphadata e constraint. Cache schema `4`, TTL principale
  7 giorni. L’ETag/Last-Modified della risposta GenCC non versiona tutte le
  sorgenti secondarie importate nella stessa sincronizzazione.
- [clinvar.py](../helper_next/src/helper_variants/clinvar.py): cache positiva
  7 giorni e negativa 1 giorno. L’etichetta del registro “Current NCBI weekly
  aggregate” non identifica una release numerata verificata da questo client.
- [gnomad_frequency.py](../helper_next/src/helper_variants/gnomad_frequency.py):
  dataset distinti per assembly, AC/AN/omozigoti/emizigoti/populations e coverage.
  La release è dichiarata dalla configurazione del client; la query non ne
  certifica indipendentemente l’identità. Assenza, scarsa coverage e dati mancanti
  restano stati distinti. L’adeguatezza locale usa mean >=20 e over_20 >=0.8:
  queste sono euristiche già presenti in HELPER, non soglie PM2 dell’engine.
- [panelapp.py](../helper_next/src/helper_variants/panelapp.py),
  [liftover.py](../helper_next/src/helper_variants/liftover.py),
  [secondary_findings.py](../helper_next/src/helper_variants/secondary_findings.py):
  versioni dei pannelli, proiezioni di alleli e liste locali rispettivamente.

Il registro assegna alle cinque sorgenti del gene cache lo stesso stato generale
di sincronizzazione. Per verificare una specifica sorgente occorre controllare
anche la relativa tabella e i suoi metadati; uno stato comune non prova da solo
che ogni import opzionale sia completo.

## 2. Altre sorgenti di HELPER fuori dal registro

| Risorsa | Cosa conserva o permette | Limite per l’Evidence Contract |
| --- | --- | --- |
| VCF di run esistenti e VCF/VCF.gz standalone | Stesso parser/index/query; ALT separati; INFO/FORMAT originali; GT, DP, AD, AF, GQ, FILTER | Un call VCF non diventa automaticamente evidenza familiare, de novo o funzionale |
| ANN/CSQ VEP/SnpEff compatibili | Campi originali per allele e trascritto, consequence, HGVS, canonical; header/layout e checksum del VCF | Annotator può essere registrato come ANN/CSQ; la versione scientifica non viene sempre ricostruita dal contenuto dell’header |
| Configurazione VEP e plugin | Default HGVS, transcript_version, exon numbers, canonical; SIFT/PolyPhen e plugin GeneSplicer/MaxEntScan/SpliceRegion/dbNSFP | Sono opzioni configurabili, non prova che il singolo VCF contenga risultati o release specifiche. Non è stato eseguito VEP |
| FASTA e `.fai` | Verifica REF e normalizzazione usando il codice esistente; identity della reference tramite digest e versione dichiarata | Nessun FASTA è stato controllato in questo audit; `HELPER_ACMG_REFERENCE_CONFIG` non era impostato nell’ambiente dell’audit. Una run può comunque fornire una reference |
| Liste trascritti/pannelli, BED target | Selezione dei pannelli/trascritti e regioni catturate | Target BED e appartenenza al pannello non attestano modello completo o rilevanza clinica |
| File di esoni `All_genes_all_stranscripts_exons_info.txt` | File presente, 95.411.902 byte; gene/ENSG/ENST/RefSeq, strand, cromosoma, coordinate esoni e rank | Nell’header non sono dichiarati assembly, release, versioni transcript, CDS o completezza; controllato solo header/metadati, non tutto il file |
| RefSeq in IGV | Traccia remota UCSC per visualizzare trascritti/esoni | Non è un provider backend locale versionato per PVS1 |
| Metadati di campione/famiglia e confronti VCF | Ruoli, parentela e dati clinici quando registrati; confronti fra callset | Non vengono trasformati oggi nei modelli `FAMILY`, `CASE`, `ALLELIC` o `BENIGN` del Task 22 |
| Contesto ed evidenze manuali | Identificativi espliciti, correzioni, motivazioni e reviewer locali | Sono dichiarazioni del provider; non autenticazione, verifica scientifica automatica o fonti aggiuntive scaricate |

Nel parser le annotazioni multialleliche non assegnabili con sicurezza all’ALT
non vengono attribuite arbitrariamente. Tutti i campi ANN/CSQ disponibili sono
conservati in `metadata.fields`, ma soltanto una parte è adattata per l’engine.

## 3. Quali dati attraversano oggi il confine REST

Flusso verificato nel codice:

`query.variant_detail → acmg_workbench.prepare → snapshot locale →
acmg_task22.provider_contract → /v1/evidence-contracts/validate →
/v1/evidence/requirements oppure /v1/criteria/evaluate`.

| Contenuto | Payload attuale | Provenienza e limite |
| --- | --- | --- |
| Variante | Identità, tipo, normalizzazione, reference_resource | HELPER controlla la reference disponibile e rifiuta conflitti |
| Annotazione | Gene, trascritto/versione selezionati, consequence e HGVS | Provenance della selezione del contesto; non una release verificata dell’annotatore |
| Contesto | Gene, malattia, trascritto; gene_disease con ereditarietà se fornita | Meccanismo G2P, validità completa e fenotipo non vengono copiati nel contesto normalizzato |
| REVEL | `COMPUTATIONAL`, score dell’annotation selezionata | `predictor_version = null`; nessuna calibrazione selezionata |
| SpliceAI | `COMPUTATIONAL`, delta AG/AL/DG/DL disponibili e trascritto | Release non stabilita; nessun massimo inventato, nessun prodotto RNA/LoF dedotto |
| gnomAD da ANN/CSQ/INFO | `POPULATION`, AC/AN/AF quando attribuibili all’ALT | Dataset/release/strato e qualità spesso mancanti; il digest del record VCF non li sostituisce |
| gnomAD da cache | `POPULATION`, dataset, release dichiarata, allele, counts/AF, populations e coverage disponibili | Nessuna fetch durante prepare; rappresentatività ancestrale e callabilità per popolazione non stabilite |
| Famiglie diverse | Nessuna mappatura automatica | Possibile invio API di envelope completi con provenance MANUAL; form tipizzato iniziale per due famiglie |
| Dipendenze | `dependencies: []` nel normale snapshot prodotto | Le dipendenze tra evidenze non vengono costruite automaticamente |

L’engine riceve automaticamente soltanto `POPULATION` e `COMPUTATIONAL`.
Per le evidenze automatiche l’envelope ha `quality_status: UNKNOWN` e
`validation_status: UNVERIFIED`. Alcune righe popolazionali possono avere un
proprio QC PASS: è un livello distinto dall’envelope e non lo promuove.

### Contenuto locale che non viene inoltrato come campo del contratto

L’`EvidencePacket` locale usa `evidence-packet-v1` e contiene anche
`source_snapshots`, `annotation_versions`, `quality_information`,
`transcript_designations` e `missing_evidence`. Questi campi **non sono campi
radice dell’EvidenceContract** e `provider_contract()` non li copia nel nuovo
envelope. Rimangono nel workspace; l’engine riceve ciò che è stato effettivamente
inserito in variant/context/evidence.provenance e ricalcola i propri missing.

`received_json` conserva l’evidenza costruita dall’adapter prima della sua
serializzazione canonica. Non è necessariamente il JSON originale del servizio
remoto: il lookup gnomAD in cache è già una rappresentazione elaborata da HELPER,
con AF calcolata da AC/AN e coverage qualificata dal codice locale.

Il dettaglio VCF conserva ClinVar dalle annotazioni; l’endpoint viewer può
arricchirlo tramite E-utilities. La preparazione ACMG interroga direttamente
`query.variant_detail`, senza passare dall’endpoint arricchito del viewer:
l’arricchimento remoto ClinVar non è quindi garantito nel workspace. In ogni
caso non viene costruita un’evidenza ClinVar tipizzata né imposta una categoria.

## 4. Schema autorevole e versioni

| Artefatto | Stato verificato |
| --- | --- |
| [Schema portabile](../../acmg-engine/docs/schemas/evidence-contract-1.0.json) | 262.525 byte, **141 definizioni**, identico come oggetto JSON a `EvidenceContract.model_json_schema()` runtime |
| SHA-256 dello schema portabile | `b9bc8f2b4a7ff8b07af4554b77e4810eb1a017ccb7860dad861fff5606c1c141` |
| Versione contratto | `evidence-contract-1.0` |
| Versione envelope per item | `provider-evidence-1.0` |
| Risposta validazione | `validated-evidence-context-1.0` |
| Risposta requirements | `evidence-requirements-1.1`; catalogo interno `evidence-requirements-catalog-1.0` |
| Snapshot riusato | `1.0` |
| Matrice / tree / trace | `criteria-matrix-1.0` / `decision-tree-1.0` / `criterion-execution-1.0` |
| OpenAPI | Componenti distinti `EvidenceContract-Input` e `EvidenceContract-Output`; validate usa il primo. Nessun componente generico `EvidenceContract` nel file osservato |

La versione package `0.1.0`, le versioni di contratto e la versione dei protocolli
`1.0.0` sono identificativi diversi. Il confronto di uguaglianza runtime è stato
eseguito sullo schema portabile; non si rivendica una verifica byte-per-byte
dell’intero OpenAPI contro un server live.

## 5. Modelli e campi obbligatori

Qui “obbligatorio” indica il `required` dello schema, prima dei controlli
semantici. Un campo obbligatorio può ammettere `null`; un campo con default può
essere omesso. Il manifest contiene proprietà, default, ref e vincoli dei modelli
di confine e delle 16 observation; lo schema originale contiene tutte le 141
definizioni annidate.

| Modello | Campi obbligatori | Default/opzionali rilevanti |
| --- | --- | --- |
| `EvidenceContract` | `variant`, `context`, `evidence` | schema_version fissata; dependencies vuoto. `evidence: []` è ammesso |
| `Variant` | `identity`, `variant_type`, `normalization` | reference_resource, HGVS genomico, annotations, transcript_selection |
| `GenomicIdentity` | `assembly`, `chromosome`, `position`, `reference`, `alternate` | Alleli di sequenza A/C/G/T/N; posizione intera positiva |
| `StructuralIdentity` | `assembly`, `chromosome`, `position`, `end`, `event_type` | kind STRUCTURAL; intervalli di confidenza opzionali; delezione/duplicazione |
| `Normalization` | `status`, `reference_validated`, `provenance` | reference_validated è nullable nello schema, ma NORMALIZED richiede true semanticamente |
| `InterpretationContext` | Nessuno | gene/disease/gene_disease null; transcripts vuoto; `{}` valido |
| `ProviderEvidence` | `value`, `received_json`, `quality_status`, `validation_status` | schema_version fissata; transformations vuoto; af_consistency_tolerance null |
| `EvidenceBase` | `id`, `provenance`, più observation nel modello specializzato | related_evidence_ids e limitations vuoti; kind discrimina il modello |
| `EvidenceTransformation` | `method`, `software_version`, `formula`, `input_json`, `output_json`, `performed_at`, `validation_checks` | Almeno un controllo; JSON di input/output validi |
| `EvidenceDependency` | `id`, `kind`, `evidence_ids`, `explanation`, `provenance` | Almeno due evidence_ids unici; dependent_evidence_id per DERIVED_FROM |

Il contratto non contiene protocollo, soglie o risultato. La richiesta
`CriteriaEvaluationRequest` contiene separatamente `evidence` e `protocol`, più
eventuali profili/specializzazioni e usage RESEARCH. Il preflight richiede
variant/context/protocol e, opzionalmente, criteria e il contratto `supplied`
coerente con quella stessa variante e quel contesto.

`value.kind` deve identificare la famiglia nella union discriminata. I singoli
modelli possono dichiarare un default per kind: questo non autorizza a omettere
il discriminatore quando si invia un’evidenza tramite la union del contratto.

### Provenance e attestazioni

`Provenance` richiede le chiavi `source`, `source_identifier`, `source_version`,
`acquired_at`, `extraction_method`, `software_version`, `verification_status`.
source_version e software_version possono essere null, con limitazioni
esplicite; questo non rende i dati automaticamente utilizzabili.

Sono opzionali references/source_url, artifact_digest, limitations e verification.
Le estrazioni ammesse sono DIRECT_IMPORT, MANUAL, ALGORITHM, LLM e SYNTHETIC:
la presenza dell’enum LLM nello schema non indica che HELPER abbia un estrattore
LLM implementato.

`VERIFIED` e `REJECTED` richiedono `HumanVerification` con reviewer_id,
verified_at e rationale. UNVERIFIED non deve includere una verifica umana
contraddittoria. `validation_status` dell’envelope deve coincidere con
`value.provenance.verification_status`. Il server controlla queste attestazioni
strutturalmente; non autentica il revisore o le citazioni e non conferisce una
validazione clinica.

## 6. Tutte le 16 famiglie accettate

I consumatori qui sotto provengono dal **catalogo requirements attuale**; non
sono una promessa di valutabilità per qualsiasi observation dello stesso tipo.

| kind | Observation | Campi obbligatori principali nello schema | Criteri consumatori dichiarati | Mappatura automatica HELPER |
| --- | --- | --- | --- | --- |
| ALLELIC | AllelicObservation | phase | BP2, PM3 | No |
| BENIGN | BenignEvidenceSet | Nessuno | BP5, BP7, BS2 | No |
| CASE | CaseObservation | cohort_key | PS4 | No |
| COMPUTATIONAL | ComputationalObservation | predictor, predictor_version, score; ultimi due nullable | BP4, PP3 | REVEL e SpliceAI, parziale |
| DE_NOVO | DeNovoObservation | status, parentage | Nessuno nel catalogo corrente | No |
| EXTENSION | ExtensionObservation | schema_id, schema_version, fields | BP6, PP5 | No |
| FAMILY | FamilyEvidenceSet | families, members | BS4, PM6, PP1, PS2 | No |
| FUNCTIONAL | FunctionalObservation | assay_id, assay_version, result, assay_validity | BS3, PS3 | No |
| LITERATURE | LiteratureObservation | publications, extraction_status | BP6, PP5 | No |
| MISSENSE | MissenseObservation | protein_consequence, disease | PM1, PM5, PS1 | No |
| PHENOTYPIC | PhenotypicObservation | Nessuno | BP1, PP2, PP4 | No |
| POPULATION | PopulationObservation | Nessuno | BA1, BS1, PM2 | gnomAD, parziale |
| PROTEIN_LENGTH | ProteinLengthObservation | variant_id, variant_identity, gene, disease, consequence, annotation_version, provenance | BP3, PM4 | No |
| PVS1 | PVS1Observation | variant_identity | PVS1 | No: adapter solo progettato |
| SEGREGATION | SegregationObservation | Nessuno | Nessuno nel catalogo corrente | No |
| SPLICE_EQUIVALENCE | SpliceEquivalenceObservation | gene, disease, mechanism, current, comparison, reference_classification, baseline, baseline_evidence_ids, context_review | PS1 | No |

DE_NOVO e SEGREGATION sono modelli accettati dalla union, ma il catalogo attuale
usa FAMILY per i relativi criteri. Un tipo accettato dallo schema senza
consumatore dichiarato può richiedere review e non alimentare l’albero atteso.

Per PP5/BP6 ClinGen General dichiara NOT_APPLICABLE/ritiro; nel percorso storico
il report `EXTENSION` riconosciuto richiede anche il modello tipizzato
`acmg-2015-reputable-report/1.0.0`. Un riassunto libero o un’etichetta ClinVar non
completano questi requisiti.

## 7. Vincoli semantici non esauriti dal JSON Schema

I [modelli Pydantic](../../acmg-engine/src/acmg_engine/domain/evidence_contract.py)
e quelli richiamati dal dominio impongono anche:

- NORMALIZED richiede reference_validated=true e una reference_resource
  versionata con digest. Il server accetta un’attestazione del provider: non
  apre un FASTA né verifica autonomamente quell’assembly.
- REF/ALT, variant_type e intervalli strutturali devono essere coerenti.
- Versioni esplicite: `latest`, `unknown`, `unversioned` non sono accettati come
  Version. I trascritti pertinenti/selezionati devono avere versione e annotation
  corrispondente; le associazioni del contesto devono usare gli stessi ID.
- Coerenza di allele/build, gene e trascritto nelle componenti controllate;
  compatibilità della malattia può essere ulteriormente verificata dal modello
  o dal criterio specifico. Coerenza degli ID non prova l’esistenza/curazione
  dell’entità in un’ontologia remota.
- ID unici, riferimenti ad altre evidenze esistenti, no auto-riferimenti e no
  cicli DERIVED_FROM. Ogni dipendenza deve esplicitare i propri membri e fonte.
- `received_json` e gli input/output delle trasformazioni rifiutano numeri non
  finiti e chiavi duplicate. Senza trasformazioni l’originale deve coincidere
  con la serializzazione tipizzata di value, inclusi default/canonicalizzazioni.
  Con trasformazioni la catena deve essere continua e terminare esattamente in
  quel valore. Le formule dichiarate dal provider non vengono eseguite.
- Conteggi popolazionali interi non negativi, AC<=AN; AF/FAF frazioni e non
  percentuali; AN=0 può essere rappresentabile senza AF ma non rende il dato
  utilizzabile. AF, FAF e confidence level restano campi distinti.
- AF/AC/AN incoerenti vengono segnalati; `af_consistency_tolerance` è esplicita,
  compresa fra 0 e 1 e di default null, trattato come tolleranza zero.

### Verifiche leggere effettivamente eseguite

Su fixture sintetica Task 22, senza valutare alcun criterio:

| Caso | JSON Schema | Pydantic |
| --- | --- | --- |
| Contratto parziale valido, zero evidenze | Accetta | Accetta |
| Stesso contratto con context vuoto | Accetta | Accetta |
| NORMALIZED con reference_validated=false | Accetta | **Rifiuta** |
| source_version=latest | Accetta | **Rifiuta** |
| Versione contratto errata | Rifiuta | Rifiuta |
| Chiave context mancante | Rifiuta | Rifiuta |

Anche l’esempio `contract_complete.json` è stato validato dal modello reale
(una evidenza popolazionale). “Complete” non significa completo per tutti i
criteri. L’uguaglianza dello schema esportato e i risultati delle sei sonde sono
conservati nel manifest. Queste verifiche non sono una suite end-to-end.

## 8. Stati dati, requirements e risultato scientifico

`normalize_contract()` produce assessments, correlations, snapshot, contract e
input_digest. `scientific_validation` è sempre NOT_PERFORMED. I sette stati dati
sono AVAILABLE_VALID, AVAILABLE_INVALID, MISSING, INSUFFICIENT_QUALITY,
CONFLICTING, NOT_APPLICABLE e REQUIRES_REVIEW.

I dati fuori schema possono generare un errore di richiesta, anziché un
assessment AVAILABLE_INVALID. Nel normalizzatore quest’ultimo è usato, fra
l’altro, quando la fonte è dichiarata REJECTED. Missing, qualità e review hanno
una precedenza nell’implementazione: non tutti i problemi diventano lo stato
principale, quindi vanno letti anche missing_fields e issues.

Il motore rileva osservazioni duplicate, stesso artefatto, dataset/release
correlati, misure discordanti e dipendenze esplicite. Non combina automaticamente
release diverse e non dimostra l’indipendenza scientifica delle osservazioni.

La Requirements API distingue START/PATH_COMPLETION e alternative non richieste.
Il readiness del catalogo è un preflight, non la verifica esaustiva di tutti i
gate interni di ciascun albero. Gli stati dei criteri sono separati: ACTIVE,
INACTIVE, NOT_EVALUABLE, NOT_APPLICABLE, CONFLICTING_EVIDENCE, REQUIRES_REVIEW.
AVAILABLE_VALID non assegna un criterio; MISSING non equivale a INACTIVE.

## 9. Risultati dell’audit e lacune da affrontare

| ID | Risultato verificato o rischio circoscritto | Effetto |
| --- | --- | --- |
| A01 | 11 sorgenti disponibili nel browser, solo 2 famiglie adattate automaticamente | L’inventario delle fonti non equivale alla copertura dei criteri ACMG |
| A02 | PVS1, FAMILY, FUNCTIONAL, CASE e altre observation non costruite | Mancano payload scientifici essenziali; la matrice può correttamente mostrare NOT_EVALUABLE |
| A03 | G2P/dosage esistono in cache, ma non arrivano come MechanismAssessment | PVS1 richiede collegamento, contesto esatto e curazione, non il solo download di nuove fonti |
| A04 | source_version basata sul checksum di record VCF/contesto; annotation provenance della selezione | Versiona l’artefatto locale, non certifica release di VEP, gnomAD o predittore |
| A05 | HPO/Orphadata non conservano release upstream; gnomAD constraint v4.1.2 è un’etichetta locale | Provenance insufficiente per attribuire automaticamente una release scientifica verificata |
| A06 | G2P può essere arricchito con fallback per simbolo; dati dosage sono a livello di gene | Prima del riuso PVS1 servono match stabile gene–malattia–ereditarietà e gestione dei conflitti |
| A07 | Envelope automatici UNKNOWN/UNVERIFIED; dati di rappresentatività, release/calibrazione o riferimenti spesso mancanti | Validazione sintattica può riuscire senza rendere le osservazioni utilizzabili |
| A08 | AF gnomAD calcolata con divisione float; tolleranza dell’envelope lasciata null | Rischio di CONFLICTING per arrotondamento rispetto al controllo Decimal AC/AN; rischio da codice, non osservato su record di pazienti in questo audit |
| A09 | source_snapshots, annotation_versions e QC del packet non sono copiati integralmente nel contratto | L’engine non vede automaticamente tutto ciò che HELPER conserva localmente |
| A10 | Nessuna dependency costruita dal normale adapter; correlazioni rilevate dall’engine solo nei casi supportati | Indipendenza e riuso delle evidenze richiedono lavoro dedicato |
| A11 | PanelApp scaduta; supporto GRCh38 gnomAD non coincide con record GRCh38 già presenti | Stato e presenza vanno dichiarati per fonte/dataset, senza assumere sincronizzazione completa |
| A12 | Schema portabile coincide col runtime; JSON Schema non contiene tutti i model_validator | Mantenere la validazione Pydantic via API come controllo autorevole |
| A13 | Contesto vuoto ammesso dall’engine; HELPER esige gene, malattia, annotation e trascritto versionato | HELPER applica un sottoinsieme di ingressi più restrittivo rispetto al contratto generale |
| A14 | Revisioni locali ed evidence verification non sono la stessa azione | Confermare un criterio non deve promuovere automaticamente le sue fonti a VERIFIED |

Il [progetto PVS1](TASK23_PVS1_ADAPTER_DESIGN.md) affronta A02/A03/A06: riuso delle
fonti, provider trascrizionale qualificato, stop validato e attestazioni curate.
Il catalogo VCEP dichiarato dall’engine presenta inoltre il conflitto di route
già verificato nel [resoconto Task 23](TASK23_ACMG_INTEGRATION.md); la raggiungibilità
HTTP non è stata riprovata in questo audit offline.

## 10. Esito e modifiche di questo incremento

Creati questo report e il manifest JSON; aggiunto il collegamento dal resoconto
Task 23. Nessuna modifica a parser, adapter, engine, cache o flussi applicativi.
Verificati schema/runtime, due fixture sintetiche, sei sonde strutturali, link
locali e coerenza del diff. Suite completa, servizi remoti e test pesanti non
eseguiti, in continuità con la scelta dell’utente di fermarsi ai test mirati.
