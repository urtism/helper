# Task 27A.1 — Audit scientifico prima del popolamento completo

> Nota 2026-10-29: audit/inventario storico. I riferimenti al Workbench, ai relativi test e al vecchio contratto descrivono lo stato precedente alla rimozione; non sono istruzioni operative attuali. Per componenti conservati, cache e verifiche aggiornate vedere [HELPER_STRUCTURAL_CLEANUP.md](HELPER_STRUCTURAL_CLEANUP.md).

**Documento storico:** i rischi qui identificati sono ora isolati a runtime
dal Task 27A.2. Il nuovo inventario e il GO conservativo sono documentati in
[TASK27A2_ONTOLOGY_MAPPING_REGISTRY.md](TASK27A2_ONTOLOGY_MAPPING_REGISTRY.md).
Questo audit e il relativo JSON rimangono invariati nei risultati originari.

Data del report: **27 ottobre 2026**. Giudizio: **NO-GO per il popolamento
completo nello stato corrente**. La correzione del vocabolario ereditario è
verificata; restano collegamenti ontologici non sufficientemente qualificati.
Non sono necessari PVS1 ACTIVE o meccanismi clinicamente approvati per superare
questo audit: occorre invece che identità, scope e incertezze siano attendibili.

**Non sono stati avviati il popolamento completo, Task 27B o commit.** Nessuna
modifica al motore ACMG, alle regole PVS1, alle strength o agli stati di review.
La cache ordinaria conserva il pilot precedente: **20 matrici, 20 snapshot**.
Il nuovo pilot è separato e contiene 30 matrici, tutte `NOT_REVIEWED`.

I risultati strutturati, con identificativi dei record, snapshot, hash e
verifiche per matrice, sono in
[TASK27A1_PREPOPULATION_AUDIT_RESULTS.json](TASK27A1_PREPOPULATION_AUDIT_RESULTS.json).
Lo script riproducibile è [audit_mechanism_inventory.py](../scripts/audit_mechanism_inventory.py).

## 1. Dati effettivamente esaminati

Indice locale: `/home/jarvis/.local/share/helper_variants/gene_phenotype.sqlite3`,
schema 4, acquisizione registrata **2026-10-21T12:33:28Z**.

| Fonte/tabella | Record |
| --- | ---: |
| G2P / `g2p_records` | 3.856 |
| GenCC / `assertions` | 30.345 |
| Orphadata / `orpha_aliases` | 25.405 |
| ClinGen Dosage | 1.537 |
| gnomAD constraint | 10, di cui 5 con dati e 5 con esito negativo |

Le associazioni sono state enumerate attraverso il Source Manager e l'accessor
Task 27A.1 esistenti. **232 righe G2P prive di disease ID** restano escluse;
non si ricavano identificativi dal nome. Gli HGNC presenti sono identificativi
stabili numerici; il match non usa soltanto il simbolo. Non è stata eseguita
una riconciliazione HGNC storica esterna per tutti i geni.

Controlli esterni mirati:

* mapping ufficiali MONDO **v2026-10-06**, file SSSOM di 13.124.886 byte;
  sono stati letti i mapping `skos:exactMatch` verso OMIM/Orphanet;
* sette risposte pubbliche G2P per `G2P03300`, `G2P03279`, `G2P02320`,
  `G2P02748`, `G2P03295`, `G2P02315`, `G2P00850`;
* terminologia G2P/HPO documentata nella pubblicazione originale.

Il file MONDO è un riferimento **solo per l'audit**: non viene caricato nel
resolver e non modifica le equivalenze operative. Non sono stati scaricati
nuovi dataset completi G2P/GenCC o l'ontologia MONDO completa. Il pilot usa
esclusivamente gli indici locali; nessun fetch gnomAD è stato effettuato.

## 2. Perché le sovrapposizioni erano soltanto 7

La chiave è SHA-256 del JSON canonico contenente
`gene HGNC + disease ID canonico + requisito allelico normalizzato`.
Il disease ID canonico deriva dalle componenti di cross-reference dei record
dello stesso gene e dai mapping esatti dell'indice Orphadata. Se una componente
contiene più ID della stessa ontologia, il resolver conserva il disease ID
richiesto e segnala l'ambiguità. I nomi non generano equivalenze.

Il normalizzatore 1.0 separava termini G2P qualificati dai corrispondenti termini
GenCC: `monoallelic_autosomal` non coincideva con AD;
`biallelic_autosomal` e i termini X-linked completi finivano inoltre in `OTHER:*`.
Ciò produceva chiavi diverse anche in presenza del medesimo HGNC e MONDO.

| Misura | Risultato |
| --- | ---: |
| HGNC condivisi fra fonti | 3.006 |
| Coppie gene + disease ID primario identico, ignorando inheritance | 3.341 |
| Chiavi complete identiche prima dei mapping, normalizzatore 1.0 | 6 |
| Chiavi complete condivise dopo i mapping, normalizzatore 1.0 | 7 |
| Chiavi complete con ID primario identico, normalizzatore 1.1 | 3.220 |
| Chiavi condivise dopo i mapping operativi, normalizzatore 1.1 | 3.374 |

**Le 7 sovrapposizioni dipendevano soprattutto dalla normalizzazione, non da una
copertura biologica quasi disgiunta.** Non è stato usato il nome della malattia
per aumentare l'intersezione.

### Correzione applicata

Il crosswalk dei termini **completamente qualificati** è documentato nella
tabella 2 di [Roberts et al., Genetics in Medicine, 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11039201/):

| Termine G2P | Scope ereditario | HPO |
| --- | --- | --- |
| `monoallelic_autosomal` | Autosomal dominant | HP:0000006 |
| `biallelic_autosomal` | Autosomal recessive | HP:0000007 |
| `monoallelic_X_hemizygous` | X-linked recessive | HP:0001419 |
| `monoallelic_X_heterozygous` | X-linked dominant | HP:0001423 |
| `monoallelic_Y_hemizygous` | Y-linked | HP:0001450 |

Monoallelic/biallelic generici, X-linked non qualificato, semidominant e modalità
differenti restano separati. Il termine originale rimane nell'evidenza e la
citazione del crosswalk nella provenance. Non è una deduzione clinica dal gene.

Il nuovo dry-run produce:

* G2P: **3.614** associazioni;
* GenCC: **15.350** associazioni;
* intersezione: **3.374**;
* unione: **15.590**;
* mapping ambigui nell'unione corrente: **2.031**.

La diminuzione da 2.436 a 2.031 associazioni ambigue deriva dall'accorpamento di
scope ereditari ora allineati. **Non significa che 405 mapping ontologici siano
stati risolti.**

## 3. Controllo ontologico e mapping ambiguo

Il [riferimento MONDO versionato](https://raw.githubusercontent.com/monarch-initiative/mondo/v2026-10-06/src/ontology/mappings/mondo.sssom.tsv)
ha SHA-256:

```text
ec15afdb32fab3d3cb679d357e25ef4fb38b5e2c468ff4ac5456da10e2f6c80b
```

Il confronto considera esclusivamente relazioni esplicite `skos:exactMatch` e
la loro componente pertinente agli ID locali. Non usa similarità dei nomi,
gerarchie padre–figlio, close/broad/narrow match o il solo fatto che due ID siano
coassegnati. La [documentazione MONDO](https://mondo.monarchinitiative.org/pages/faq/)
distingue exact match ed equivalenza logica OWL: l'audit non li confonde e non
interpreta automaticamente componenti con cardinalità multipla come un'unica
malattia clinica.

### Cause delle 2.436 associazioni ambigue originarie

| Causa topologica | Associazioni |
| --- | ---: |
| Ambiguità già nei cross-reference coassegnati G2P/GenCC | 405 |
| Ambiguità introdotta soltanto dai collegamenti via Orphadata | 2.031 |

La seconda categoria indica concatenazioni di mapping che collegano più concetti,
anche quando ogni riga importata è etichettata E. L'etichetta Orphadata e la sua
provenienza sono conservate; non viene elevata a dimostrazione universale di
identità. [Specifiche ufficiali Orphadata](https://www.orphadata.com/docs/OrphadataFreeAccessProductsDescription.pdf).

| Namespace con più ID nella stessa componente | Associazioni |
| --- | ---: |
| MONDO | 2.251 |
| MONDO + ORPHA | 116 |
| MONDO + OMIM | 25 |
| ORPHA | 18 |
| MONDO + OMIM + ORPHA | 22 |
| OMIM | 4 |

### Quante potrebbero essere chiarite con mapping qualificati

È stato costruito un **controfattuale di audit**, senza pubblicare nuove
matrici o cambiare il resolver: per ciascun ID pertinente si segue il grafo
exact-match della release MONDO fissata, compresi collegamenti fra ID presenti
in record diversi.

| Esito sulle 2.436 associazioni originarie | Numero |
| --- | ---: |
| Componente di riferimento non ambigua con almeno un mapping verificabile | **2.100** |
| Nessun mapping pertinente verificabile | **267** |
| Componente ancora con cardinalità multipla | **69** |

Le 2.100 sono **candidate a una qualificazione automatica riproducibile**;
non sono 2.100 identità cliniche già approvate, né sono state risolte nel DB.
Le altre **336** rimangono irrisolte nell'audit. Anche la separazione di una
componente può richiedere una segnalazione del cross-reference originario
scartato; l'assenza di un mapping non dimostra che i concetti siano diversi.

### Rischio residuo anche nelle componenti oggi non ambigue

Fra le righe con due disease ID coassegnati:

| Fonte | Coppia confermata exact | Non confermata exact |
| --- | ---: | ---: |
| G2P | 2.821 | 34 |
| GenCC | 21.223 | 590 |

Sono conteggi di **righe**, non di malattie o osservazioni indipendenti.
Delle 624 coppie non confermate, 597 hanno un target MONDO differente nel
riferimento; 27 non hanno un exact match disponibile. Non è sufficiente per
chiamarle tutte errori: possono riflettere concetti più ampi, versioni differenti
o mapping da rivedere. **171 righe appartengono tuttavia a componenti operative
non ambigue**, quindi la sola guardia sulla cardinalità non le qualifica.

Delle 154 intersezioni correnti che richiedono ID primari diversi, **151** sono
confermate come componenti non ambigue nel riferimento; **3** richiedono review:

| Gene | G2P primario | Canonico operativo | Esito del riferimento |
| --- | --- | --- | --- |
| HOXA1 / HGNC:5099 | OMIM:601536 | MONDO:0011099 | exact target MONDO:7770750 |
| NEU1 / HGNC:7758 | OMIM:256550 | MONDO:0009738 | componente con due OMIM; mantenere review |
| PEX6 / HGNC:8859 | OMIM:616617 | MONDO:0014709 | exact target MONDO:0100263 |

Questi casi sono **irrisolti nell'audit**, non nuove equivalenze proposte. Non
sono stati elaborati dal nuovo pilot. Il resolver operativo conserva ancora la
politica di cross-reference Task 27A: la verifica MONDO dell'audit non è una
protezione runtime. Per questo **15.590 non è ancora un inventario scientifico
approvato per il popolamento completo**.

Esempio cardiogenetico: `FLNA/G2P00850` coassegna MONDO:0019027 e OMIM:304120,
mentre la release MONDO associa quest'ultimo a MONDO:0010571. La risposta G2P
mirata conferma che entrambi gli ID sono davvero nella fonte. Il parser non li
ha inventati; la coassegnazione richiede qualificazione semantica.

## 4. Perché il vecchio pilot aveva soltanto 4 assertion dirette

Il pilot iniziale era costituito dalle prime 20 chiavi ordinate lessicalmente
per HGNC: non era stratificato per fonte o disponibilità di meccanismo.

| Categoria | Matrici |
| --- | ---: |
| Assertion G2P esplicita e applicabile | 4 |
| Nessun record G2P per quella malattia | 9 |
| G2P presente, meccanismo `undetermined` | 2 |
| G2P presente, inheritance allora differente | 5 |

Fra le 9 senza G2P pertinente, **7** non hanno record G2P per il gene negli
indici locali; **2** hanno record per altre malattie/ID: RGS9 e RHO. Non si
trasferiscono le loro assertion alla malattia richiesta.

Delle 5 con inheritance differente, **4** sono riallineabili con il crosswalk
qualificato: RGS7-AR, RGS9-AR, RHO-AD, RHO-AR. Il quinto caso RHO-semidominant
resta distinto: non era un errore di parsing da correggere. Le righe sconosciute
rimangono tali. GenCC documenta validity e inheritance; non fornisce in queste
colonne un'assertion di meccanismo da ricostruire.

È stata inoltre corretta la classificazione di
`undetermined non-loss-of-function`: resta `UNKNOWN` con testo originale,
senza convertirlo in un meccanismo definito `OTHER` a supporto. Riguarda 15
record dell'indice G2P. La restrizione non equivale a un'assertion GoF o DN.

## 5. Pilot stratificato e confronto con i record originali

DB separato: `/tmp/task27a1-audit/stratified.sqlite3`.
Tutte le pubblicazioni attraversano il **Mechanism Resolver e MechanismStore**
esistenti, con snapshot immutabili. Non vengono scritte direttamente tabelle
scientifiche. Lo script ha un limite rigido di **30 associazioni**.

| Strato della chiave gene–malattia–scope | Matrici |
| --- | ---: |
| G2P + GenCC | 12 |
| G2P soltanto | 9 |
| GenCC soltanto | 9 |
| **Totale** | **30** |
| Con assertion diretta applicabile | **11** |
| Con sole evidenze contestuali/non informative | **19** |
| Con mapping ambiguo ancora segnalato | **4** |

Lo strato si riferisce alla **chiave completa**, non all'assenza della fonte
per l'intero gene. Per esempio GLA-X-linked generico e GLA-X-linked recessive
restano chiavi diverse.

Controlli cardiogenetici selezionati:

| Gene / record | Dato originale verificato | Risultato |
| --- | --- | --- |
| MYH7 / G2P03300, MONDO:0008647 | meccanismo undetermined | nessuna assertion LoF/GoF inventata |
| MYBPC3 / G2P03279, MONDO:0007268 | loss of function, monoallelic_autosomal | candidato LoF in AD; non trasferito ad AR |
| LMNA / G2P02320, MONDO:0030781 | gain of function, monoallelic_autosomal | candidato GoF in AD |
| LMNA / G2P02748, stessa malattia | loss of function, biallelic_autosomal | candidato LoF in AR, distinto da AD |
| LMNA / G2P01342, MONDO:0021569 | loss of function | candidato LoF nello scope indicato |
| GLA / G2P03295, MONDO:0010526 | loss of function, monoallelic_X_hemizygous | candidato LoF nello scope XR; nessun trasferimento a X-linked generico |
| FLNA / G2P02315, MONDO:0010233 | loss of function, monoallelic_X_heterozygous | candidato LoF nello scope XD |
| FLNA / G2P00775, MONDO:0024550 | gain of function, monoallelic_X_hemizygous | candidato GoF nello scope XR |

**169 occorrenze di record originali** sono state confrontate campo per campo
con le rispettive tabelle locali; alcune ricorrono in più matrici. Verificati
anche hash del raw record, scope delle assertion dirette e replay dello snapshot.
I record immutabili distinti nel DB del pilot sono 104. Il database contiene
30 snapshot; rieseguire il pilot crea **0 nuovi snapshot**.

Per sette record G2P sono state controllate anche risposte API ufficiali mirate:
**0 differenze** in HGNC, simbolo, disease IDs, genotype, mechanism,
mechanism_support e confidence. URL, data di acquisizione, last_updated e
SHA-256 delle risposte sono nel JSON. Questo confronto non attesta una nuova
sincronizzazione di tutti gli indici, né un'immutabilità dell'endpoint live.
I record GenCC del pilot sono verificati contro l'export indicizzato e le
versioni originali; non è stato riscaricato l'intero export per confrontarlo.

Una assertion diretta indica una dichiarazione esplicita della fonte: anche
`mechanism_support=inferred` è conservato, non trasformato in dimostrazione
sperimentale. Tutte le matrici rimangono `NOT_REVIEWED`.

## 6. Versionamento e riproducibilità

`dataset_version=null` è corretto quando il vecchio indice non registra una
release scientifica. Non si sostituiscono release con schema SQLite, data del
file o etichetta hardcoded.

Già disponibili e conservati:

* acquisizione dell'indice, URL originali e date di review dei record;
* GenCC `sgc_id/version_number`, con versioni individuali da 1 a 5;
* ETag GenCC `"794f9f3b1ba6ae6b344cd18bcbca6f59"` e Last-Modified
  `Wed, 14 Oct 2026 19:15:08 GMT`, quali metadati HTTP, non release;
* hash dei record e snapshot immutabili Task 27A;
* normalizzatore **1.1**, bulk **1.1**, citazione del crosswalk nella provenance;
* release e checksum del riferimento MONDO, separati dalle fonti operative.

Aggiunti al report bulk `dataset_fingerprints`: SHA-256 deterministico del JSON
canonico della lista ordinata degli hash delle righe, con conteggio, tabella e
scope `LOCAL_INDEXED_ROWS_V1`. L'ordine SQLite non modifica il fingerprint.
Non sono checksum dei byte originali scaricati, né comprendono colonne che
l'importatore legacy ha scartato. I fingerprint completi delle cinque fonti
sono nel JSON dell'audit.

Per gli import successivi è raccomandato conservare un manifest per fonte:
release ufficiale **solo se dichiarata**, URL versionata quando disponibile,
acquisizione separata, header HTTP, SHA-256 dei byte acquisiti, schema/parser e
versioni dei record. Gli archivi originali mancanti non sono ricostruibili a
posteriori. Questa nuova pipeline di acquisizione non è implementata qui.

Il nuovo normalizzatore cambia chiavi e fingerprint: il vecchio job bulk non è
riprendibile con `--resume`. Gli snapshot storici restano consultabili per ID;
non vengono riscritti o cancellati. Un futuro piano corretto dovrà esplicitare
come trattare i vecchi puntatori con scope precedenti, mantenendo lo storico.

## 7. gnomAD e ClinVar

I **20 CACHE_MISS** iniziali sono assenze locali reali: nessuno dei geni iniziali
ha una riga in `gnomad_constraints`. Le 10 righe presenti riguardano ATP7A,
COL11A1, COL5A2, PKD1, PKD2 e cinque lookup negativi di simboli LOC/RP11.
`--offline` impedisce al Source Manager di effettuare fetch, anche con variabili
d'ambiente abilitate. Un miss non equivale a LOEUF=0 o assenza di constraint.

L'adapter esistente `refresh_gnomad_constraint` usa già la query mirata
GraphQL `gene/gnomad_constraint`, GRCh38, e salva pLI, LOEUF, observed/expected,
z-score e trascritto. Il nuovo pilot include COL5A2: **1 AVAILABLE, 29 CACHE_MISS**,
con constraint conservato come contesto. Non è stato eseguito un test remoto
di disponibilità di questo endpoint: il controllo è del codice e dei dati locali.
Il simbolo collega il lookup; l'identità HGNC↔Ensembl non viene dichiarata
verificata dal solo simbolo. L'etichetta legacy v4.1.2 non è una release attestata
nella risposta memorizzata.

**Soluzione proposta, non implementata o eseguita:** una fase preliminare sui
soli geni distinti con constraint mancante/obsoleto, riutilizzando
`refresh_gnomad_constraint`, con rate limiting, retry e timestamp già previsti;
poi congelare il manifest e avviare il popolamento offline. Evita una richiesta
per ogni malattia e conserva i lookup negativi. Non richiede un nuovo adapter
o Task 27B; il constraint rimane evidenza contestuale.

ClinVar resta **NOT_SUPPORTED** per il lookup gene–malattia: l'adapter corrente
è allele-specifico e non espone un indice di meccanismi gene–malattia. Il pilot
ha 30 NOT_SUPPORTED, non 30 errori di rete. Nessuna nuova estrazione ClinVar.

## 8. Modifiche e test

Modifiche di produzione circoscritte:

* normalizzatore: crosswalk qualificato e gestione di undetermined non-LoF;
* resolver: policy/provenance del crosswalk, senza cambiamenti ACMG;
* inventario/CLI: intersezione esplicita per fonte, membership delle chiavi e
  fingerprint riproducibili delle proiezioni indicizzate;
* script di audit separato, fixture sintetiche e documentazione aggiornata.

Regressione mirata:

```bash
python -m pytest -q -o pythonpath=helper_next/src \
  helper_next/tests/test_acmg_mechanisms_audit.py \
  helper_next/tests/test_acmg_mechanisms_bulk.py \
  helper_next/tests/test_acmg_mechanisms.py \
  helper_next/tests/test_acmg_evidence.py \
  helper_next/tests/test_acmg_pvs1.py \
  helper_next/tests/test_acmg_task22.py \
  helper_next/tests/test_acmg_workbench.py \
  helper_next/tests/test_acmg_context.py \
  helper_next/tests/test_gene_phenotype.py \
  helper_next/tests/test_gnomad_frequency.py \
  helper_next/tests/test_clinvar.py \
  helper_next/tests/test_source_registry.py
```

Risultato finale: **181 passed, 5 skipped**, nessun fallimento. I cinque skip
sono i test REST esterni opt-in già presenti. Il test HTTP locale in-process e
il confronto con il motore reale, su criteri e protocolli invariati, passano.
Il test HTTP è stato eseguito fuori dal sandbox per il vincolo ambientale già
riscontrato. Warning preesistente Starlette su `python_multipart`.
Non sono state eseguite suite massive, pipeline Nextflow o analisi di pazienti.

Per riprodurre l'audit con i riferimenti già acquisiti:

```bash
PYTHONPATH=helper_next/src python scripts/audit_mechanism_inventory.py \
  --mondo-mappings /tmp/task27a1-audit/mondo-v2026-10-06.sssom.tsv \
  --g2p-response-dir /tmp/task27a1-audit \
  --pilot-db /tmp/task27a1-audit/stratified.sqlite3 \
  --report /tmp/task27a1-audit/repeat-audit.json
```

Senza `--pilot-db` esegue soltanto l'audit; lo script non ha modalità di
popolamento completo e non esegue HTTP. File temporanei e DB del pilot sotto
`/tmp` possono essere rimossi dal sistema: il report JSON nel repository
conserva i risultati e gli hash. La release MONDO deve corrispondere al checksum
fissato nel codice; una release diversa non viene accettata silenziosamente.

## 9. Decisione e prossimo incremento

**NO-GO al popolamento completo.** La logica tecnica e l'idempotenza funzionano,
ma il controllo di cardinalità non qualifica tutti i cross-reference. In
particolare non si approvano automaticamente le 3 intersezioni da rivedere,
le 171 righe non confermate in componenti non ambigue o le 336 associazioni
senza esito ontologico non ambiguo. Le categorie si sovrappongono e non vanno
sommate come un unico conteggio di malattie.

Il prossimo incremento raccomandato è un **registro di mapping ontologici
versionato**, che distingua cross-reference osservati, exact match verificati,
concetti più ampi e mapping mancanti/discordanti; deve essere usato sia dal
bulk sia dal resolver e conservare ogni collegamento scartato e la sua ragione.
I casi senza corrispondenza attendibile devono rimanere separati e in review,
senza trasferimento di assertion fra malattie. Dopo questo incremento servirà
un nuovo dry-run e un pilot mirato ai casi HOXA1, NEU1, PEX6 e FLNA, prima
di riconsiderare il GO. La mancanza di constraint gnomAD o di release legacy,
se esposta correttamente, da sola non richiede di inventare dati o meccanismi.
