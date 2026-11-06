# PRIORITY-01 — Population Frequency v2

**Stato corrente:** il profilo predefinito è `germline-wes-v2.2.0`, con la scala
AF −10/+25 della sezione 13 e il bonus euristico per ricerca negativa con
copertura regionale adeguata della sezione 18. Le sezioni precedenti documentano
il comportamento al completamento dei rispettivi interventi; v1.9.2, v2.0.0 e
v2.1.0 restano selezionabili per riproducibilità.

## 1. Audit precedente all'implementazione

Audit del working tree iniziale, inclusi gli aggiornamenti locali già presenti.
Il default è `germline-wes-v1.9.2`, in `helper_prioritization/profiles.py`.

Flusso reale: GraphQL gnomAD → `gnomad_frequency._parse_response` →
cache SQLite condivisa → `cached_contexts` / `priority_context` →
`query._compact_variant` → `score_variant` / `_score_maf` → normalizzazione →
Variant Browser (badge e dettaglio espandibile esistenti).

* Il parser conserva Exomes, Genomes e Joint separati, calcola AF da AC/AN,
  conserva la Grpmax FAF95 ufficiale e verifica identità allelica e assembly.
  I campi riassuntivi legacy e il contesto Priority usano **solo Genomes**.
* `priority_context` accetta frequenze osservate solo con filtri noti e vuoti
  (PASS), usa il massimo tra AF globale e AF dei gruppi principali. Include
  anche ami/asj/fin e non pone un minimo AN ai gruppi.
* Exomes e Joint non contribuiscono al vecchio punteggio. FILTERED non passa
  frequenze; No variant è presenza NOT_OBSERVED, con filtro e conteggi nulli,
  non PASS né AF=0. Lo stato tecnico del risultato deriva comunque da Genomes.
* Copertura adeguata legacy: media ≥20 **e** quota over_20 ≥0.8. Assenza:
  AC=0, AN positivo specifico del dataset, PASS e copertura adeguata. Non basta
  record non trovato o profondità media. Manca un controllo della presenza
  attendibile in altri dataset prima di assegnare il bonus di assenza.
* `_score_maf` sostituisce sempre AF con FAF95 se disponibile; prima verifica
  l'assenza, poi dato mancante (+10, evaluated=True), BA1 (≥0.05: −25),
  rarità assoluta (≤1e-6: +25), quindi rapporto con MCAF: ≤0.1 +20,
  ≤0.5 +15, ≤1 +10, ≤5 zero, altrimenti −15.
* MCAF proviene dal campo libero `max_credible_af` oppure dal default 0.001;
  non richiede malattia, fonte o validazione. `ba1_af` può sovrascrivere 0.05.
  Gene2P/GenCC forniscono meccanismi, ereditarietà e ambiguità, **non MCAF**.
  Nessun calcolatore MCAF verificato è presente in questo percorso.
* La query combina l'AF di annotazione e il contesto tramite massimo, ma
  l'espansione finale di population_context può ripristinare il campo cached.
  La colonna AF_max e la frequenza realmente usata dallo score possono divergere.
* Normalizzazione: somma dei punti dei componenti applicabili / somma dei loro
  massimi ×100, clamp 0–100 e arrotondamento. `evaluated=False` non rimuove un
  componente dal denominatore. Prediction e run occurrence possono essere N/A.
  Non serve cambiare il normalizzatore per mantenere il massimo Population=25
  anche quando il nuovo componente non è valutabile.
* Source Manager espone la cache esistente con release 4.1.1; non calcola
  punteggi. La cache frequenze conserva dati, non risultati Priority. Identità,
  release e parser vengono controllati in lettura. Il ranking in memoria usa
  versione delle regole, impronte delle cache e snapshot ClinVar nella chiave.
* Criticità: AF/FAF intercambiabili, +10 senza evidenza, MCAF generica impropria,
  esclusione sistematica di Exomes/Joint, assenza non verificata tra dataset,
  nessun minimo AN dei gruppi. Gli override MCAF molto bassi/alti possono rendere
  alcuni rami di rapporto irraggiungibili per precedenza delle soglie assolute.
  `_number` legacy accetta inoltre NaN/infinito: il nuovo ramo li deve rifiutare
  senza cambiare retroattivamente v1.

### Caso obbligatorio

Exomes AC=4/AN=1335596, AF≈2.995e-6, FAF95=8.140e-6; Genomes No variant,
AF/FAF95 null; Joint AC=4/AN=1480618, AF≈2.702e-6, FAF95=6e-6.
L'adapter legacy non seleziona Exomes né Joint: mancano AF/FAF utilizzabili,
l'assenza non è verificata, quindi **v1.9.2 = +10**. Con AF di annotazione
aggiuntiva il risultato dipende anche da quell'input, non specificato nel caso.
Le cifre visualizzate sono arrotondate; il parser conserva il rapporto AC/AN.

L'audit sopra è stato completato prima delle modifiche al codice.

## 2. Implementazione e versionamento

Implementato `germline-wes-v2.0.0` come profilo sperimentale nello **stesso**
motore `score_variant`, tramite dispatch del solo componente `maf`.
`germline-wes-v1.9.2` rimane il default; il corpo del suo `_score_maf` è invariato.
I pesi restano Population 25, Mechanism 25, ClinVar 20, Inheritance 15,
Prediction 10, Run occurrence 15 (solo quando applicabili).

Uso Python:

```python
from helper_prioritization import get_profile, score_variant
from helper_variants import gnomad_frequency

profile = get_profile("germline-wes-v2.0.0")
# result è il risultato già recuperato/cached con il provider esistente.
inputs = gnomad_frequency.priority_context(result, scoring_version=profile["version"])
priority = score_variant(inputs, profile)
```

Lista e dettaglio Variant Browser/API accettano `scoring_version=germline-wes-v2.0.0`
esplicito. Senza parametro rimangono v1. La UI continua a mostrare motivo ed
evidenze nel dettaglio espandibile già esistente: nessun nuovo pannello o default.
Non è stato aggiunto un selettore UI di attivazione prima della validazione.
La versione entra nella firma di filtri/cursori e quindi nella chiave del ranking;
un cursore v1 non può essere riutilizzato per v2. La ricalcolazione ClinVar
conserva la versione originale e rifiuta un profilo esplicitamente discordante.

## 3. Sorgenti e separazione AF/FAF95

Si consumano esclusivamente i dati già parsati da `gnomad_frequency`:
`datasets.exomes/genomes/joint`, `presence`, `filters`, `flags`, `ac`, `an`,
`af`, `populations[].{id,ac,an,af}`, `grpmax_faf95`,
`grpmax_faf95_population`, `coverage`, `freq_comparison_stats`, `variant_flags`,
release e versione parser. Non si modifica il recupero GraphQL né si costruisce
un Joint sommando dataset. AF deriva dal rapporto osservato AC/AN del provider;
FAF95 è esclusivamente il valore ufficiale, mai ricalcolato dai conteggi globali.

La Grpmax FAF95 è un limite inferiore statistico riferito al gruppo eleggibile
con FAF massima, che può differire dal gruppo con AF osservata massima.
Riferimenti verificati: [gnomAD, spiegazione Grpmax/FAF](https://discuss.gnomad.broadinstitute.org/t/difference-between-popmax-in-the-vcf-and-popmax-grpmaxfaf-in-the-website/63/2),
[implementazione ufficiale FAF e grpmax](https://broadinstitute.github.io/gnomad_methods/api_reference/utils/annotations.html).
Queste fonti giustificano la distinzione tra metriche; **non validano le scale
numeriche di ranking proposte in questo task**.

AF determina i bonus di rarità. FAF95 determina soltanto l'incompatibilità
supportata con la MCAF selezionata. Null rimane null e genera un avviso;
AF>MCAF con FAF mancante produce zero e non una dichiarazione di compatibilità.
Con AF mancante/non valida il dataset non sostiene uno score, anche se contiene FAF.

## 4. Policy dataset e popolazioni

1. Richiedere identità/release/parser verificati dal percorso di lettura esistente,
   record PRESENT, FILTER PASS (`filters=[]`), conteggi finiti interi coerenti,
   AN positivo e AF coerente con AC/AN. Rifiutare flag di qualità non risolti e
   callability esplicitamente inadeguata. Callability ignota permette l'uso di
   conteggi osservati, con avviso; non permette di dimostrare l'assenza.
2. Preferire Joint utilizzabile. Non sostituirlo con il dataset che dà più punti.
3. Senza Joint utilizzabile, valutare Exomes e Genomes indipendentemente:
   selezionare la **massima AF osservata** utilizzabile. Parità: AN maggiore,
   poi nome dataset, per determinismo. Nessuna somma dei conteggi.
4. Nel dataset, AF usata = massimo tra globale e gruppi configurati sufficientemente
   rappresentati: afr, ami, amr, asj, eas, fin, mid, nfe, sas. Includere i gruppi
   fondatori nel calcolo di rarità osservata è una scelta conservativa esplicita.
   Non usarli per ricostruire o cambiare la FAF ufficiale.
   Gruppi aggregati remaining/oth, sesso e sottogruppi sovrapposti non partecipano
   alla selezione; le loro frequenze restano disponibili nel provider originale.
5. Un gruppo con AN insufficiente e AF superiore alla globale rende il dataset
   incerto: non ignorarlo assegnando un bonus favorevole. Gruppi con AN=0/AC=0
   e AF null non dimostrano assenza; generano un avviso. Conteggi di gruppo
   maggiori di quelli globali rendono il dataset incoerente.
6. FAF95 segue Joint quando selezionato. Senza Joint, usare il massimo limite
   ufficiale dei dataset utilizzabili e conservarne una provenienza distinta
   da quella dell'AF. Non confrontare AF e FAF come stime dello stesso gruppo.
7. Flag espliciti di discordanza o test ufficiali con p<0.001 producono zero e
   qualità DISCORDANT, senza scegliere arbitrariamente un dataset. Una Joint
   AC=0 con osservazione attendibile altrove è discordante. Differenze numeriche
   ordinarie Exomes/Genomes non sono automaticamente un problema biologico.

Soglie configurabili in `profiles.py`, **euristiche sperimentali di affidabilità**:

| Parametro | Default | Significato e limite |
|---|---:|---|
| AN osservato minimo | 1 | Validità strutturale; non precisione clinica |
| AN di gruppo minimo | 1000 | Salvaguardia sperimentale contro stime instabili |
| AN per assenza minimo | 10000 | Salvaguardia sperimentale; non potere statistico validato |
| Quota callable over_20 per assenza | 0.8 | Riprende la quota già usata dal provider; non basta la media |
| p discordanza | 0.001 | Trigger sperimentale di incertezza; nessun punto autonomo |

Non esiste una fonte clinica che convalidi AN=1000/10000 o p=0.001 per questo
ranking. Sono proposte esplicitamente sperimentali da sottoporre a sensibilità
e revisione prima dell'attivazione, non soglie BA1/BS1. Il provider conserva
anche il suo preesistente criterio di copertura media ≥20 e over_20≥0.8;
il nuovo componente non ne modifica i dati.

## 5. Stati, assenza e dati mancanti

| Stato | Significato | Punti |
|---|---|---:|
| OBSERVED | Conteggi e AF osservata utilizzabili | Scala della modalità |
| NOT_OBSERVED_EVALUABLE | AC=0, AN sito/dataset adeguato, callable adeguata, PASS e nessuna discordanza | +25 |
| NOT_FOUND_UNVERIFIED | Nessun record oppure assenza insufficientemente valutabile | 0 |
| UNRELIABLE | QC/conteggi/release/parser/discordanza impediscono l'uso | 0 |
| UNSUPPORTED | Allele/contig non supportato dalla sorgente nucleare | 0 |
| ERROR | Errore tecnico/recupero, distinto dall'assenza biologica | 0 |

AF=0 non basta per +25: richiede AC=0 e tutti i requisiti di assenza. No variant
non è PASS e non fornisce implicitamente AN specifico dell'allele. La sola media
di copertura non basta. Un dataset rifiutato impedisce il bonus di assenza
perché può contenere evidenza discordante non risolta. FAF positiva con AC=0
non sostiene l'assenza. Per Joint senza callability specifica disponibile si
restituisce zero sull'assenza: non si trasferisce automaticamente la copertura
Exomes/Genomes alla Joint.

## 6. MCAF e contesto gene-malattia

La modalità è context-aware soltanto con `population_mcaf_context` esplicitamente
selezionato e documentato:

```json
{
  "gene": "GENE1",
  "disease_id": "MONDO:...",
  "mode_of_inheritance": "AD",
  "mcaf": 0.001,
  "source": "fonte verificata dal chiamante",
  "version": "versione della fonte",
  "validated": true,
  "parameters": {"nota": "eventuali parametri documentati del calcolo originale"}
}
```

Esempio strutturale, **non una MCAF clinica proposta**. Si richiedono MCAF finita
0<MCAF≤1, fonte, versione, malattia, ereditarietà e gene coerente con la variante.
`validated=true` attesta una verifica eseguita dal chiamante: il componente non
certifica autonomamente la fonte scientifica. Non si calcola MCAF da prevalenza,
penetranza o eterogeneità incomplete; non si convertono BA1/BS1/VCEP in MCAF.
`max_credible_af` e `ba1_af` legacy non abilitano il ramo context-aware.

Gene2P/GenCC nel percorso attuale non espongono MCAF verificate: il normale
Variant Browser v2 usa quindi la modalità generica. Il contratto del calcolatore
Python permette a un chiamante con MCAF verificata di passare il contesto.
Non è stata aggiunta una nuova infrastruttura di configurazione o persistenza
MCAF. Un elenco di contesti non viene ottimizzato: si segnala che occorre
selezionarne uno; in mancanza si usa soltanto rarità generale. Per confrontare
due malattie dello stesso gene chiamare il componente separatamente per ciascun
contesto, conservando separati i risultati e senza scegliere il migliore.

## 7. Tabelle complete v2

Precedenza context-aware: qualità/identità → contesto → FAF incompatibile → AF;
il caso speciale AC=0 passa soltanto dalla verifica di assenza, mai dalle bande AF.

| Condizione, dopo qualità e assenza | Punti |
|---|---:|
| Assenza verificata con AN/callability adeguati | +25 |
| FAF95 > 5×MCAF | −25 |
| MCAF < FAF95 ≤ 5×MCAF | −15 |
| Nessuna incompatibilità supportata e AF ≤ 0.01×MCAF | +25 |
| 0.01×MCAF < AF ≤ 0.1×MCAF | +20 |
| 0.1×MCAF < AF ≤ 0.5×MCAF | +10 |
| 0.5×MCAF < AF ≤ MCAF | +5 |
| AF > MCAF senza FAF95 superiore, inclusa FAF95 null | 0 |
| Dati non utilizzabili | 0 |

FAF95 null consente solo i rami AF giustificati e mantiene l'avviso di incertezza.
Nessun limite BA1 assoluto o scorciatoia AF≤1e-6 precede i rapporti con MCAF.

Scala context-agnostic: **proposta euristica sperimentale**, nessuna soglia
clinica o penalità per una malattia non selezionata. I bin decimali rendono il
comportamento semplice da confrontare e configurare; la scelta dei punti e dei
confini non è stata calibrata su coorti cliniche.

| AF osservata utilizzabile | Punti |
|---|---:|
| Assenza verificata | +25 |
| 0 < AF ≤ 1e-6 | +25 |
| 1e-6 < AF ≤ 1e-5 | +20 |
| 1e-5 < AF ≤ 1e-4 | +10 |
| 1e-4 < AF ≤ 1e-3 | +5 |
| AF > 1e-3 | 0 |
| AF=0 con assenza non verificata; dato mancante/non affidabile | 0 |

FAF resta visibile come metrica, senza generare punti nel ramo generico.
Il componente limita sempre i punti a −25/+25, e a 0/+25 nel ramo generico.

## 8. Output e normalizzazione

Il componente conserva il contratto `key,label,score,max_score,reason,evaluated,
applicable,evidence` e aggiunge `scoring_version`, `scoring_mode`,
`frequency_status`, `quality_status`, `observed_af`, `observed_af_source`,
`faf95`, `faf95_source`, `mcaf`, `mcaf_source`, `disease_context`, `warnings`,
`evaluation_status`, `quality_evidence` (AN del sito e quota callable selezionati).
Il dettaglio dell'assenza riporta anche i valori e le soglie AN/callability usati.
Le provenienze contengono metrica, dataset, release e gruppo;
la provenienza FAF resta distinta anche quando il dataset differisce.
Nessun payload originale gnomAD viene duplicato nel risultato Priority.

`evaluated=True` distingue uno zero valutato (es. AF comune generica) da
`evaluated=False`/`not_evaluable` per dati mancanti. Il componente Population
resta sempre `applicable=True` con massimo 25; altri componenti N/A rimangono
esclusi secondo le regole preesistenti. Non si modifica il denominatore, il peso
degli altri componenti o la loro valutazione. Nei test i risultati degli altri
componenti sono identici con Population disponibile o mancante.

La formula esistente resta clamp(round(100×somma punti/somma massimi applicabili),
0,100). Uno zero Population riduce soltanto il numeratore rispetto al bonus
legacy, senza riponderazione implicita. Gli score negativi possono portare il
totale sotto zero, con normalizzato finale zero come prima.

## 9. Cache e moduli modificati

* `helper_prioritization/profiles.py`: nuovo profilo, registro e selezione esplicita;
  deepcopy mantiene isolato v1 e permette configurazione locale dei parametri.
* `helper_prioritization/population_frequency.py`: policy pura del componente v2,
  senza I/O, cache o servizi; il motore esistente la richiama per `maf`.
* `helper_prioritization/engine.py` e `__init__.py`: dispatch e conservazione
  versione negli aggiornamenti ClinVar.
* `helper_variants/gnomad_frequency.py`: solo adapter opzionale del risultato già
  presente; recupero, parsing, cache, release e query upstream invariati.
* `helper_variants/query.py`: profilo esplicito, firma/cursore e inoltro input
  al componente, senza mischiare AF di annotazione non qualificata al nuovo score.
  La colonna AF_max preesistente resta distinta dalle metriche spiegate nello score.
* `helper_next/api/variants.py`: parametro opzionale della versione su lista e dettaglio.
* Nuovi test, fixture, script benchmark e questo report. Il wrapper di conteggio
  nel test query esistente accetta il nuovo argomento opzionale del profilo.

Nessun motore ACMG modificato, nuovo database, cache ricostruita, servizio,
aggiornamento gnomAD o commit. Il vecchio adapter mantiene il comportamento
legacy. V2 rifiuta payload con release/parser incompatibili; la lettura cache
esistente verifica già allele, dataset, release e parser. Un vecchio record
rifiutato diventa evidenza insufficiente senza essere riscritto dal calcolatore.

## 10. Verifiche e benchmark

Test offline in `test_population_frequency_v2.py`: tutti i rami e confini,
FAF prima dei bonus, AF/FAF mancanti e non finite, AF zero, record non trovato,
assenza con/senza AN/callability, FILTER, exomes-only, genomes-only, Joint,
discordanza, popolazioni/fondatori e AN insufficiente, contesti diversi per lo
stesso gene, MCAF estrema/sopra il vecchio BA1, normalizzazione, risultati golden
v1, riproducibilità, versione durante aggiornamento ClinVar, cache obsolete e
immutabilità dei dati cached. Il test blocca ogni accesso socket.
Coperti anche selezione API/query, isolamento dei cursori e ranking tra versioni.

Comandi di verifica ed esito definitivo sono riportati nella sezione finale.

Benchmark riproducibile, nessuna rete:

```bash
PYTHONPATH=helper_next/src python scripts/benchmark_population_frequency_v2.py \
  --output /tmp/priority_01_population_benchmark.json
```

Per dati indipendenti: `--input reviewed_variants.json`, elenco di record con
`sample_id`, `variant_id`, `variant` (input del motore con evidenza gnomAD parsata),
opzionali `classification` e `causal`. Il confronto usa gli **stessi dati** per
v1/v2. Riporta Population, Priority totale, bande, ranking e distribuzioni,
quota di dati insufficienti, positivi→neutri/negativi, effetto ancestrie,
contesto MCAF, denominatori, Top-1/5/10 e candidati medi per campione a soglia
esplicita (default 50, euristica di reporting). Le VUS restano un gruppo separato.
Senza etichette causali, Top-k è null. Il programma non dichiara mai validazione
scientifica automaticamente, nemmeno con un file esterno.

Controlli aggiuntivi a dati congelati: v2 limitata a Genomes, v2 solo AF globale,
v2 senza MCAF. Questi aiutano a distinguere gli effetti di selezione, ancestrie
e contesto. Il controllo Genomes conserva le nuove regole QC: non separa ogni
singola regola dal resto della policy. Nessun effetto è attribuito a un aggiornamento
gnomAD perché i dati non vengono aggiornati.

### Risultati sintetici (non retrospettivi clinici)

Cinque righe di un campione artificiale; contesti ripetuti della stessa fixture
servono soltanto a dimostrare sensibilità alla MCAF, non sono varianti indipendenti.
Tutti gli altri input, inclusa consequence missense, sono identici.

| Scenario | Population v1 | Population v2 | Priority v1→v2 | Rank v1→v2 |
|---|---:|---:|---|---|
| Fixture obbligatoria, generica | +10 | +20 | 21→32 | 1→2 |
| Nessun dato | +10 | 0 | 21→11 | 2→3 |
| Errore tecnico | +10 | 0 | 21→11 | 3→4 |
| Fixture, MCAF sintetica 0.001 | +10 | +25 | 21→37 | 4→1 |
| Fixture, MCAF sintetica 1e-7 | +10 | −25 | 21→0 | 5→5 |

Denominatore 95 invariato in tutte le righe; 40% evidenza insufficiente,
2 cambi di fascia, 3 passaggi da Population positiva a neutra/negativa,
2 effetti del contesto MCAF. Top-k causali non calcolabili. Nessuna etichetta
P/LP/B/LB/VUS o causalità è inventata per queste righe.

## 11. Limitazioni e stato di validazione

**Codice implementato:** componente versionato deterministico, due modalità,
provenienza separata, QC, zero per assenza non verificata, opt-in e confronto offline.

**Comportamento verificato:** test sintetici e regressioni offline; non equivalgono
a una stima di sensibilità, specificità o performance clinica.

**Assunzioni euristiche:** scale generiche e context-aware, cut-off AN/callability
e discordanza, gestione conservativa dei gruppi piccoli e dei flag non risolti.
Nessuna è presentata come criterio ACMG/AMP validato.

**Validazione scientifica ancora necessaria:** non è stato individuato un dataset
di validazione clinica indipendente nel percorso esaminato. Non sono stati letti
database di pazienti o cache runtime per costruire una coorte. Occorrono coorti
annotate P/LP, B/LB, VUS e causali note per campione, congelamento della release
dati, verifica delle MCAF da esperti, revisione di gruppi fondatori e cut-off AN,
analisi per ascendenza/ereditarietà, sensibilità alle soglie e regioni problematiche,
controllo della callability e confronto dei ranking prima di cambiare il default.

Il GraphQL attuale non espone all-sites AN per i record non trovati né FAF per
ogni gruppo: molti casi di assenza resteranno correttamente a zero. Joint non
dispone sempre di callability specifica. Non si ricalcolano FAF o denominatori
mancanti e non si deduce affidabilità da metriche di qualità prive di policy
validata. La verifica scientifica della MCAF resta responsabilità del chiamante;
Gene2P da solo non la fornisce. Il default deve restare v1.9.2 fino a revisione
dei risultati comparativi e autorizzazione esplicita dell'attivazione.

## 12. Esito finale delle verifiche

Eseguito il 4 novembre 2026:

```bash
PYTHONPATH=helper_next/src python -m pytest -q \
  helper_next/tests/test_population_frequency_v2.py \
  helper_next/tests/test_prioritization.py \
  helper_next/tests/test_gnomad_frequency.py \
  helper_next/tests/test_variant_query.py \
  helper_next/tests/test_variants_api.py \
  helper_next/tests/test_variant_viewer.py \
  -k 'not igv_manifest_and_file_endpoint_support_byte_ranges' --tb=short
```

**276 passed, 1 deselected**, 44.69 secondi. Di questi, **84 test** appartengono
al nuovo modulo v2, inclusi i test offline di integrazione lista/dettaglio API.
Un avviso preesistente della dipendenza Starlette invita a usare python_multipart.

Il test `test_igv_manifest_and_file_endpoint_support_byte_ranges` è stato
interrotto e poi escluso: rimaneva in attesa asincrona durante lo streaming file
(`test_variants_api.py:267`, stack asyncio/anyio rilevato con faulthandler dopo
30 secondi). Quel percorso IGV non è stato modificato né diagnosticato oltre;
non è dichiarato superato. Nessuna suite generale Nextflow/ACMG o verifica
browser interattiva è stata eseguita per questa modifica circoscritta.

Eseguiti anche il benchmark sintetico offline (output JSON in
`/tmp/priority_01_population_benchmark.json`, risultati riportati sopra) e
`git diff --check`, entrambi con esito positivo. I test golden e la suite v1
verificano che il vecchio algoritmo continui a produrre i risultati precedenti.
Il benchmark è uno strumento di confronto, **non validazione scientifica**.

## 13. Successiva richiesta: scala AF −10/+25

Implementata la scala indicata dall'utente in un nuovo profilo
`germline-wes-v2.1.0`, adottato come default per il calcolo corrente. La richiesta
successiva definisce direttamente la scala da applicare; il profilo v2.0.0
precedente resta selezionabile per confronto, senza modifiche retroattive.
L'adozione di questa euristica non costituisce validazione scientifica.

| Frequenza gnomAD utilizzabile | Punti |
|---|---:|
| Assenza verificata, ricerca valida | +25 |
| 0 < AF ≤ 0.000001 | +25 |
| 0.000001 < AF ≤ 0.00001 | +20 |
| 0.00001 < AF ≤ 0.0001 | +15 |
| 0.0001 < AF ≤ 0.0005 | +10 |
| 0.0005 < AF ≤ 0.001 | +5 |
| 0.001 < AF ≤ 0.01 | 0 |
| AF > 0.01 | −10 |
| Dati mancanti, non affidabili, errore o assenza non verificata | 0 (N/A) |

Ogni intervallo comprende il limite superiore. Il nuovo profilo usa AF osservata
e non applica i rami MCAF/FAF95 dello snapshot v2.0.0. FAF95 resta disponibile
come metrica informativa, senza sostituire AF o determinare penalizzazioni di
frequenza. Restano i controlli di qualità, la selezione Joint/fallback e la
verifica dell'assenza: AF=0 da sola o un record non trovato non dimostrano
assenza. Le soglie sono euristiche di prioritizzazione, non criteri clinici.

Population mantiene massimo 25 e minimo −10. I dati non valutabili restano
`applicable=True`, `evaluated=False`, score zero e massimo 25, per non alterare
il peso relativo degli altri componenti. Il dettaglio esistente visualizza
`0 / 25 · N/A`; uno zero valutato, come AF=0.01, non è marcato N/A.

Moduli aggiornati: profili/versione predefinita ed esportazioni, componente
Population, adapter del contesto gnomAD e indicazione N/A nel Variant Browser.
I test storici che documentano v1 usano ora esplicitamente quel profilo;
il benchmark v1/v2 congela esplicitamente v1 anziché dipendere dal default.
Nessuna modifica al recupero gnomAD, alle cache persistenti o al motore ACMG.
La versione diversa invalida il ranking in memoria tramite la chiave esistente.

Nuovi test in `test_population_frequency_scale.py`: soglia esatta, valore
immediatamente inferiore e immediatamente superiore per tutti i sei confini;
AF comune fino a 1; indipendenza da MCAF/FAF95; errore/dato non affidabile;
assenza verificata; denominatore e altri componenti invariati; percorso query
con AF Joint nella cache esistente. Ogni accesso socket nei nuovi test è bloccato.

Verifica finale: **290 passed, 1 deselected**, 45.03 secondi, usando lo stesso
comando della sezione 12 con l'aggiunta di
`helper_next/tests/test_population_frequency_scale.py`. Resta escluso soltanto
il test IGV di streaming già descritto. Superati anche `node --check` sul file
Variant Browser, `git diff --check` e il benchmark sintetico offline v1/v2.
Non eseguita validazione clinica o browser interattiva; nessun commit.

## 14. Correzione del formato delle statistiche di confronto gnomAD

Corretto un errore a runtime in `_discordant`: il codice assumeva un dizionario
per ogni test, mentre `contingency_table_test` nella fixture gnomAD 4.1.1 è
una lista di risultati. La lettura ora accetta sia dizionari sia liste, esamina
ogni p-value disponibile e gestisce risultati nulli senza chiamare `.get` su
una lista. La soglia di discordanza e la scala AF restano invariate.

Aggiunti 50 casi di regressione: entrambi i profili v2, i tre tipi di test,
dizionari/liste, p-value sul confine e valori nulli; inoltre la fixture gnomAD
completa passa dal parser alla cache esistente e al calcolatore. Quest'ultimo
percorso non era coperto dai test precedenti e riproduce l'errore segnalato.
Il controllo verifica che la cache non sia modificata dal calcolo.

Verifica: **284 test superati** nelle suite Population v2, nuova scala AF,
regressioni v1, gnomAD e query. `git diff --check` superato. Non rieseguite le
suite API/UI per questa correzione circoscritta al lettore delle statistiche.

## 15. Diagnosi chr2:48032123 T>TA (GRCh37)

Verificato il caso segnalato dall'utente, senza modificare le cache operative.
La proiezione allelica già memorizzata è corretta: GRCh38 chr2:47804984 T>TA.
La normalizzazione sorgente con la FASTA hg19 del run restituisce lo stesso
allele. Riproducendo `resolve_alleles(..., record=run, fetch=False)`, la sorgente
è RESOLVED e la proiezione mapped, ma il target è UNRESOLVED:
`Local reference FASTA/.fai is required for sufficient indel/complex-allele normalization`.

Il percorso target non dispone di una FASTA GRCh38 configurata; il file hg38
individuato è compresso `.fa.gz` e non è utilizzabile dal lettore attuale,
che richiede FASTA non compressa e indice `.fai`. Il controllo ferma il recupero
prima della richiesta gnomAD v4. La cache contiene soltanto il precedente
record gnomAD 2.1.1 per l'allele GRCh37, non un record v4 riutilizzabile.
Per questa variante non è presente metadata `gnomad_enrichment` nell'indice
ispezionato. Priority, che legge solo la cache, riceve quindi un contesto vuoto
e mostra NOT_FOUND_UNVERIFIED: non è un NOT_FOUND restituito da gnomAD.

La richiesta diagnostica diretta alla API ufficiale conferma invece la presenza:
Exomes AC=14/AN=1461806, Genomes AC=1/AN=152198, Joint AC=15/AN=1614004,
con PASS. [Record gnomAD GRCh38](https://gnomad.broadinstitute.org/variant/2-47804984-T-TA?dataset=gnomad_r4).
Passando questa risposta al parser e al componente corrente, senza salvarla
nella cache operativa, il risultato è **OBSERVED, PASS, +15**: AF selezionata
Joint/EAS = 0.000044543429844097995, contro AF globale Joint ≈0.00000929366.
La scala funziona; il blocco precede il recupero dei dati.

Per rendere disponibile il punteggio nel percorso ordinario occorre configurare
la FASTA GRCh38 non compressa con `.fai` tramite la configurazione di riferimento
esistente e ripetere il recupero dell'allele. Non serve ricostruire la cache.
La perdita del motivo di normalizzazione fra recupero on-demand e Priority è
un limite diagnostico distinto dalla presenza biologica della variante.

## 16. Rimozione del requisito FASTA locale su richiesta dell'utente

La successiva istruzione dell'utente supera il prerequisito descritto nella
sezione 15: correttezza e normalizzazione degli alleli forniti appartengono
all'analisi secondaria e a chi invia il VCF.

Il resolver gnomAD non invoca più `allele_refs_batch`, il lettore FASTA o il
controllo locale REF. Usa posizione/REF/ALT come dichiarate nel VCF, dopo i
controlli sintattici esistenti e la risoluzione degli alias assembly/contig.
Per GRCh37 riutilizza l'unica proiezione NCBI esistente e la sua cache; richiede
una proiezione univoca su GRCh38 e verifica anche l'allele sorgente della
proiezione. La risposta gnomAD deve ancora corrispondere esattamente all'allele
richiesto. Indel non trovati restano assenza non verificata, senza bonus.

La provenienza espone `ref_status=NOT_CHECKED`, normalizzazione `AS_SUPPLIED`
oppure `ASSEMBLY_PROJECTION`. La descrizione del lookup non produce un
identificatore ga2 verificato (`allele_ref=null`) né afferma una verifica locale.
Il contratto di riferimento condiviso e il motore ACMG non vengono modificati.
La cache delle frequenze, release, parser e regole di punteggio restano gli
stessi; nessuna ricostruzione delle cache operative.

Modificati `gnomad_frequency.py`, la descrizione dell'endpoint in
`api/variants.py`, la nota del Source Registry e i test del provider.
Aggiunta la fixture offline ridotta `frequency_2_47804984_T_TA.json` con i
conteggi pubblici del caso segnalato e il gruppo EAS selezionato.

Verifiche: **216 test superati** nelle suite gnomAD, arricchimento, Population
v2, nuova scala AF, query e Source Registry; `git diff --check` superato.
I test controllano che neppure una FASTA/configurazione locale presente venga
letta, che l'indel sia richiesto come fornito, che entrambe le rappresentazioni
del caso segnalato raggiungano l'allele GRCh38 corretto e producano **+15**, e
che la lettura successiva/offline riutilizzi la stessa cache. Restano coperti
gli errori di proiezione e le risposte per un allele diverso.

Diagnostica locale ripetuta con la proiezione operativa esistente: la sorgente
hg19 chr2:48032123 T>TA ora risolve GRCh38 chr2:47804984 T>TA senza FASTA;
la risposta pubblica già acquisita produce OBSERVED, PASS, +15. Non sono state
scritte cache operative. Non rieseguite le suite generali ACMG/UI; nessun commit.

## 17. Copertura della regione per varianti non trovate (5 novembre 2026)

Quando la ricerca allelica restituisce realmente NOT_FOUND, il provider esistente
interroga anche la copertura regionale gnomAD, separatamente per Exomes e Genomes.
Finestra: tratto REF interessato più 25 basi per lato; per inserzioni si include
anche la base adiacente all'ancoraggio. Coordinate sempre GRCh38, dopo l'eventuale
proiezione GRCh37. Non viene usata una FASTA locale.

Una regione è ADEQUATE in un dataset soltanto se tutte le basi richieste hanno
metriche disponibili, profondità media ≥20× e frazione over_20 ≥0.8. Sono soglie
operative euristiche già presenti nel provider, non criteri clinici validati.
Una buona media regionale non compensa una base poco coperta. Il risultato
distingue ADEQUATE, LOW, INCOMPLETE, UNAVAILABLE, ERROR e finestre UNSUPPORTED.
Conserva anche lo stato delle basi del sito, minimi di copertura/frazione,
numero di posizioni attese/valutate e provenienza dei due dataset.

Schema verificato su [RegionCoverage](https://github.com/broadinstitute/gnomad-browser/blob/main/graphql-api/src/graphql/types/region.graphql)
e [CoverageBin](https://github.com/broadinstitute/gnomad-browser/blob/main/graphql-api/src/graphql/types/coverage.graphql).
Il [resolver ufficiale](https://github.com/broadinstitute/gnomad-browser/blob/main/graphql-api/src/queries/coverage-queries.ts)
aggiunge 75 basi ai bordi della query: vengono escluse dal riassunto. La finestra
massima è 250 basi per mantenere risoluzione per base; finestre più grandi sono
esplicitamente non valutate. Il browser v4 usa coverage Exomes v4 e coverage
Genomes v3: le provenienze sono conservate, senza inventare coverage Joint.
La precisione resta quella dei valori esposti dall'API.

La sintesi regionale viene salvata nello stesso record della cache frequenze.
I vecchi risultati negativi vengono integrati al successivo recupero, senza
rifare la ricerca allelica né ricostruire la cache. Le letture della lista restano
locali e senza rete. Il dettaglio segnala i negativi ancora privi di copertura
e richiede l'integrazione; aggiorna quindi la spiegazione Priority. Policy o
soglie cambiate invalidano soltanto la sintesi regionale. Errori di copertura
restano separati dal risultato negativo e vengono ritentati dopo almeno 30 secondi.
Query coverage in batch di massimo due regioni, deduplicate per allele; costo
delle richieste incluso nel throttling esistente.

La UI aggiunge una nota compatta alla scheda gnomAD esistente, con intervallo,
stato per dataset e minimi; non viene creato un nuovo pannello. Priority distingue
ora un sito circondato da buona copertura da una regione scarsamente coperta o
non valutabile. **Copertura regionale adeguata non fornisce AN specifico del sito**:
non si inventano AC=0, AN o AF=0. Per un record non trovato il punteggio resta zero,
NOT_FOUND_UNVERIFIED; +25 richiede ancora i requisiti di assenza verificata.

Moduli: `gnomad_frequency.py`, dettaglio espandibile in `variant-browser.js`,
spiegazione del componente in `population_frequency.py`; test coverage dedicati
e aggiornamento dei test browser alle intestazioni e nomi popolazione correnti.
Nessun cambiamento alle altre componenti Priority, al normalizzatore o ad ACMG.

Verificato lo schema anche con due query regionali reali in una richiesta API,
senza scrivere cache operative. Nel locus GRCh38 chr2:47804984 T>TA entrambe le
coperture hanno tutte le 52 basi richieste valutate, con minimo over_20 di 0.96
per Exomes e 0.97 per Genomes; la variante è comunque osservata e conserva il
normale punteggio AF. Questo controllo diagnostico non entra nei test offline.

Verifiche finali: **236 test Python superati**, inclusi 20 casi dedicati a
copertura, errori, cache, policy e proiezione; **1 test browser superato** anche
a larghezze 360/420/600 px. Chrome è stato eseguito fuori sandbox perché il
profilo ristretto ne bloccava i socket. Superati `node --check` e
`git diff --check`. Non eseguite suite generali ACMG/Nextflow; nessun commit.

## 18. Bonus euristico per ricerca negativa con copertura adeguata

Su conferma esplicita dell'utente, la regola corrente assegna **+25** quando
la ricerca gnomAD è riuscita, l'allele non è stato trovato e almeno uno fra
Exomes/Genomes ha copertura regionale adeguata. Per questo bonus euristico non
è più richiesto AN specifico del sito. La regola sostituisce il vincolo dello
zero documentato nella sezione 17 soltanto nel nuovo profilo v2.2.0.

`COVERAGE_AWARE_PROFILE` in `profiles.py` è una copia del profilo AF v2.1.0,
con `regional_absence_policy=successful_not_found_with_adequate_regional_coverage`
e `regional_absence_score=25`. Diventa il default; i vecchi profili mantengono
le proprie regole e producono ancora zero in questo caso. Le bande AF osservate,
i pesi e il denominatore del Priority Score restano invariati. La diversa
versione separa le chiavi di ranking e i cursori dai risultati precedenti.

Condizioni del bonus: NOT_FOUND con disponibilità AVAILABLE, nessun errore,
risultato parziale, flag di inaffidabilità o discordanza; sintesi regionale
ADEQUATE con sito ADEQUATE, tutte le posizioni attese valutate e frazione di basi
adeguate pari a 1 in un dataset identificato. Sintesi da aggiornare, copertura
incompleta o non disponibile non ricevono il bonus.

Output: score 25, `evaluated=true`, `frequency_status=NOT_FOUND_COVERED`,
`quality_status=REGION_COVERED_NO_SITE_AN`, provenienza del metodo
`absence_evidence=regional_coverage_heuristic`. Il motivo esplicita il bonus
euristico e AN non disponibile. Restano `absence_verified=false`,
`site_an_available=false`, AF null e i conteggi originali: non si inventa una
frequenza zero né si presenta una prova di assenza basata su AN. Il bonus è
prioritizzazione sperimentale, senza effetto su ACMG o classificazione clinica.

Caso segnalato verificato sulla cache reale in sola lettura:
GRCh37 chr11:108153607 GTA>G → GRCh38 chr11:108282880 GTA>G.
Finestra GRCh38 chr11:108282855–108282907 (53 basi): Genomes ADEQUATE,
profondità media minima ≈30.974× e over_20 minimo 0.98; Exomes LOW,
over_20 minimo 0.52. Con gli stessi dati, **v2.1.0 = 0**, **v2.2.0 = +25**.
Nessuna nuova richiesta online o scrittura delle cache operative necessaria.

Aggiunte regressioni offline per il caso della delezione (copertura sintetica
esplicitamente indicata), comportamento dei vecchi profili, riepiloghi incoerenti,
errori/risultati parziali, copertura da aggiornare, tracciabilità del bonus e
denominatore invariato. Il test query controlla anche il nuovo default e il
rifiuto di cursori ottenuti con il profilo precedente.

Verifica estesa: 381 test superati nella prima esecuzione; una sola aspettativa
statica ancora richiedeva l'import ga2 rimosso da gnomAD su precedente richiesta
dell'utente. Aggiornato quel controllo, tutti i 27 test Variant Viewer superano
la verifica: **382 test distinti verificati**, nessun errore irrisolto. Resta
escluso il test IGV di streaming già documentato. `git diff --check` superato.
Nessun commit o modifica al motore ACMG.
