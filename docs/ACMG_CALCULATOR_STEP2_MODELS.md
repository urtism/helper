# ACMG Calculator — STEP 2: Minimal PVS1 Input and Output

Contratto condiviso per stop-gain, frameshift e splice canoniche/non canoniche, basato sugli [STEP 0](ACMG_CALCULATOR_STEP0_PVS1_MODEL.md) e [STEP 1](ACMG_CALCULATOR_STEP1_RULES_DESIGN.md). Due dataclass; i TypedDict descrivono quattro blocchi e un unico record di prodotto riusato per tutte le conseguenze, senza classi per variante/evidenza.
Conteggio: **27 campi comuni nei blocchi Variant/Disease context/Transcript**, esclusi contenitori e dati molecolari condizionali; Molecular effect ha 8 campi, il prodotto condiviso 18 dopo le due aggiunte dello [STEP 3A](ACMG_CALCULATOR_STEP3A_EVIDENCE_FUNCTIONS.md), PVS1Result 10. I quattro contenitori di PVS1Input non sono inclusi nel conteggio dei campi interni.
O = comune obbligatorio per identificare l'input; C = condizionale, necessario solo nel ramo pertinente; S = opzionale supplementare. I campi scientifici possono essere omessi o `null`; gli enum ammettono anche `UNKNOWN` dove dichiarato. `false` resta un'asserzione negativa esplicita; non significa dato mancante. I blocchi tecnici omessi restano `None`.
Validazione minima alla costruzione: forma/tipi, chiavi riconosciute, enum, interi e intervalli validi, etichette/riferimenti delle coordinate presenti, allineamento delle fasi agli esoni e forma delle citazioni. Non verifica verità biologica, normalizzazione, sequence matching, traduzione o completezza scientifica. Le modifiche successive ai dizionari non sono validate automaticamente.
`source_refs` mappa il nome del campo a liste di riferimenti essenziali (identificativo/URL, versione e sezione quando disponibili). Ogni evidenza decisionale disponibile deve conservarne il riferimento; fonti mancanti restano riconoscibili. `evidence_quality` descrive tecnica, tessuto, controlli e limiti disponibili, senza un punteggio dedotto.
Coordinate: Variant = punto base 1 nel contig/assembly; alleli già normalizzati. CDS = RNA reference maturo 5′→3′, intervallo chiuso base 1, incluso stop normale. Esoni genomici = intervalli chiusi base 1 sul contig di Variant, elencati in ordine trascrizionale; strand esplicito. Giunzioni reference derivabili dagli esoni, senza duplicarle.
`cds_edit_interval` = tratto della CDS reference interessato, base 0 semiaperto, senza ancora VCF: inserzione `[k,k)`. Il relativo indel è soltanto in Variant. Fasi 0/1/2 = basi fino al primo codone completo al bordo 5′ del segmento codificante; `null` se non noto/non codificante. Nessuna fase o alterazione di frame viene calcolata.
Prodotto = RNA risultante identificato da `transcript_ref`, con sequenza completa 5′→3′ oppure riferimento qualificato/versionato; `ptc_start` è la prima base del codone stop su questo RNA, base 1, non una posizione genomica/HGVS `c.`. Frame/PTC sono asserzioni fornite, con proprie fonti anche per eventi RNA OBSERVED. Intervalli proteici chiusi base 1 sul riferimento proteico versionato.
`genomic_junctions` = coppie orientate (ultima base esonica a monte, prima base esonica a valle), base 1 sul contig di Variant; sullo strand meno possono essere decrescenti. `involved_exons` usa indici reference base 1 nell'ordine trascrizionale. Offset splice firmato nella direzione del trascritto dall'ultima base esonica donor/prima base esonica acceptor; ancoraggio genomico dichiarato. Nessuna conversione implicita.
Serializzazione: `json.dumps(dataclasses.asdict(modello))`; tuple → array JSON, `None` → `null`. Predizioni e osservazioni restano prodotti separati; non si presume un PTC da frameshift, uno skipping da splice canonica o una prova RNA da VEP/predittore.

| Campo | Tipo variante | Significato biologico | Obbligatorietà | Origine HELPER | Uso futuro |
|---|---|---|---|---|---|
| `variant.assembly` | Tutte | Assembly genomico | O comune | Normalizzazione | Identità |
| `variant.contig` | Tutte | Sequenza genomica di riferimento | O comune | Normalizzazione | Identità |
| `variant.position` | Tutte | Prima base dell'allele REF | O comune | Normalizzazione | Identità |
| `variant.reference_allele`, `alternate_allele` | Tutte | REF/ALT normalizzati, anche indel | O comuni | Normalizzazione | Ricostruzione futura, senza duplicare l'indel |
| `variant.consequence` | Tutte | Annotazione ricevuta, ad esempio `frameshift_variant` | O comune | VEP/annotazione | Percorso futuro, non esito |
| `variant.coordinate_system` | Tutte | `genomic_1_based`, punto | O comune | Contratto coordinate | Interpretare POS |
| `disease_context.gene` | Tutte | Identificativo gene | O comune | Annotazione | Contesto |
| `disease_context.disease`, `inheritance` | Tutte | Malattia ed ereditarietà valutate | C comuni | Associazione curata | Pertinenza del profilo |
| `disease_context.molecular_mechanism` | Tutte | `LoF/GoF/DN/OTHER/UNKNOWN` | C comune | Curazione meccanismo | Pertinenza LoF, senza dedurla |
| `disease_context.confidence` | Tutte | `DEFINITIVE/INFERRED/DISPUTED/UNKNOWN` | C comune | Curazione meccanismo | Incertezza |
| `disease_context.scope` | Tutte | `DISEASE_SPECIFIC/GENE_LEVEL` | C comune | Ambito della fonte | Evitare estensioni indebite |
| `transcript.accession`, `strand` | Tutte | Identificativo con versione e orientamento `+/-` | C comuni | Annotazione trascritto | Riferimenti e orientamento |
| `transcript.coordinate_system`, `cds_interval` | Tutte | `transcript_1_based_closed` e CDS reference | C comuni | Annotazione CDS | Interpretare la CDS |
| `transcript.exon_genomic_intervals`, `exon_coordinate_system` | Tutte | Esoni e `genomic_1_based_closed` | C comuni | Annotazione esonica | Mappatura e giunzioni reference |
| `transcript.exon_phases` | Tutte | Fasi 0/1/2 allineate agli esoni | C comune | Annotazione codificante | Ricostruzione futura del frame |
| `transcript.biologically_relevant`, `affected_exon_relevant` | Tutte | Rilevanza documentata del trascritto/esone interessato | C comuni | Curazione funzionale/espressiva | Valutazione biologica |
| `transcript.sequence`, `sequence_ref` | Tutte | Sequenza reference completa o riferimento qualificato | C comuni | Risorsa di sequenza | Ricostruzione futura; nessun fetch qui |
| `molecular_effect.cds_edit_interval`, `cds_coordinate_system` | Frameshift | Span dell'edit e `cds_0_based_half_open` | C | Conseguenza preparata | Localizzare indel sulla CDS |
| `molecular_effect.splice_site_type` | Splice | `DONOR/ACCEPTOR/OTHER/UNKNOWN` | C | Annotazione splice | Contesto del sito |
| `molecular_effect.splice_site_genomic_position`, `splice_site_offset` | Splice | Ancora del sito e distanza firmata | C | Mappatura splice | Distinguere posizione e conseguenza |
| `molecular_effect.native_splice_motif` | Splice | Motivo nativo disponibile | C | Sequenza/annotazione | Interpretazione futura |
| `molecular_effect.products` | Tutte | Lista di prodotti, anche multipli, o `null` | C | Annotazione/predizione/RNA | Conservare scenari separati |
| `products[].basis` | Tutte | `PREDICTED/OBSERVED/UNKNOWN` per evento/prodotto RNA | Richiesto per ogni record | Natura dell'evidenza | Non confondere predetto e osservato |
| `products[].event_type` | Splice | `EXON_SKIPPING/CRYPTIC_SITE/INTRON_RETENTION/OTHER/UNKNOWN` | C | Predizione o RNA | Tipo di evento, mai assunto |
| `products[].involved_exons`, `genomic_junctions` | Splice | Esoni/nuove giunzioni coinvolti | C | Predizione o RNA | Ricostruire i prodotti |
| `products[].transcript_ref`, `coordinate_system`, `sequence` | Tutte | Riferimento risultante, `transcript_1_based_closed`, eventuale sequenza | C; riferimento/sistema richiesti con PTC | Ricostruzione/RNA | Interpretare il prodotto alterato |
| `products[].frame_effect` | Frameshift/splice | `IN_FRAME/OUT_OF_FRAME/UNKNOWN` | C | Conseguenza preparata | Frame risultante, non dedotto |
| `products[].ptc_start`, `ptc_junction_distances` | Tutte | Prima base del PTC; coppie (giunzione RNA base 1, distanza firmata dalla prima base del PTC) | C | Conseguenza preparata | Geometria del prodotto; nessuna soglia NMD |
| `products[].protein_accession`, `protein_coordinate_system`, `lost_protein_region`, `altered_protein_region` | Tutte | Riferimento e intervalli perso/alterato, `protein_1_based_closed`; anche identificatore immutabile della sequenza | C | Annotazione proteica | Futuro ramo senza NMD, senza assumere criticità |
| `products[].lost_region_critical`, `functional_evidence` | Tutte | Asserzione di criticità e descrizioni disponibili | C / S | Curazione funzionale/clinica | Motivazione e revisione |
| `products[].evidence_quality` | Tutte | Qualità/limiti descritti della specifica evidenza | S, necessaria quando discrimina il ramo | Dati del saggio/predittore | Affidabilità futura, senza score automatico |
| `source_refs` in ciascun blocco/prodotto | Tutte | Fonti puntuali delle asserzioni | C | Fonti/versioni usate | Provenance minima |
| `status` | Risultato | `ACTIVE/INACTIVE/NOT_EVALUABLE/REQUIRES_REVIEW/EXPLORATORY` | Richiesto al chiamante | Output futuro | Stato, mai selezionato qui |
| `calculated_strength`, `applied_strength` | Risultato | `VERY_STRONG/STRONG/MODERATE/SUPPORTING` o `null` | Opzionali | Output futuro | Strength distinte, nessuna copia automatica |
| `reason` | Risultato | Motivazione esplicita | Richiesta al chiamante | Output futuro | Spiegabilità |
| `warnings`, `missing_data`, `decision_trace` | Risultato | Liste di stringhe; percorsi mancanti e traccia ordinata | Liste vuote di default | Output futuro | Nessun popolamento automatico |
| `requires_review` | Risultato | Flag esplicito, distinto dallo status | Opzionale, default `None` | Chiamante | Nessuna derivazione dallo status |
| `ruleset_id`, `ruleset_version` | Risultato | Regole effettivamente usate | Opzionali, default `None` | Output futuro | Riproducibilità |

Quattro JSON di input completamente sintetici: `DEMO_*` non identifica risorse cliniche reali. Le fonti sono segnaposto; gli esempi non classificano varianti.

1. Stop-gain con dati molecolari disponibili:

```json
{
  "variant": {"assembly":"DEMO_ASSEMBLY_1","contig":"DEMO_CONTIG_1","position":2031,"reference_allele":"C","alternate_allele":"T","consequence":"stop_gained","coordinate_system":"genomic_1_based","source_refs":{"consequence":["DEMO_ANNOTATION:v1"]}},
  "disease_context": {"gene":"DEMO_GENE","disease":"DEMO_DISEASE","inheritance":"AD","molecular_mechanism":"LoF","confidence":"DEFINITIVE","scope":"DISEASE_SPECIFIC","source_refs":{"molecular_mechanism":["DEMO_CURATION:v1"],"confidence":["DEMO_CURATION:v1"],"scope":["DEMO_CURATION:v1"],"inheritance":["DEMO_CURATION:v1"]}},
  "transcript": {"accession":"DEMO_TRANSCRIPT.1","strand":"+","coordinate_system":"transcript_1_based_closed","cds_interval":[31,420],"exon_genomic_intervals":[[1001,1150],[2001,2150],[3001,3150]],"exon_coordinate_system":"genomic_1_based_closed","exon_phases":[0,0,0],"sequence_ref":"DEMO_TRANSCRIPT.1#spliced_dna:v1","source_refs":{"cds_interval":["DEMO_ANNOTATION:v1"],"exon_genomic_intervals":["DEMO_ANNOTATION:v1"],"exon_phases":["DEMO_ANNOTATION:v1"]}},
  "molecular_effect": {"products":[{"basis":"PREDICTED","transcript_ref":"DEMO_STOP_RNA.1#sequence:v1","coordinate_system":"transcript_1_based_closed","ptc_start":181,"protein_accession":"DEMO_PROTEIN.1","protein_coordinate_system":"protein_1_based_closed","lost_protein_region":[51,129],"lost_region_critical":null,"source_refs":{"ptc_start":["DEMO_ANNOTATION:v1"],"lost_protein_region":["DEMO_ANNOTATION:v1"]}}]}
}
```

2. Frameshift con nuovo PTC determinato esternamente; riferimento alla sequenza alterata:

```json
{
  "variant": {"assembly":"DEMO_ASSEMBLY_1","contig":"DEMO_CONTIG_1","position":2030,"reference_allele":"AC","alternate_allele":"A","consequence":"frameshift_variant","coordinate_system":"genomic_1_based","source_refs":{"consequence":["DEMO_ANNOTATION:v1"]}},
  "disease_context": {"gene":"DEMO_GENE","disease":"DEMO_DISEASE","inheritance":"AD","molecular_mechanism":"LoF","confidence":"DEFINITIVE","scope":"DISEASE_SPECIFIC","source_refs":{"molecular_mechanism":["DEMO_CURATION:v1"],"confidence":["DEMO_CURATION:v1"],"scope":["DEMO_CURATION:v1"],"inheritance":["DEMO_CURATION:v1"]}},
  "transcript": {"accession":"DEMO_TRANSCRIPT.1","strand":"+","coordinate_system":"transcript_1_based_closed","cds_interval":[31,420],"exon_genomic_intervals":[[1001,1150],[2001,2150],[3001,3150]],"exon_coordinate_system":"genomic_1_based_closed","exon_phases":[0,0,0],"sequence_ref":"DEMO_TRANSCRIPT.1#spliced_dna:v1","source_refs":{"cds_interval":["DEMO_ANNOTATION:v1"],"exon_genomic_intervals":["DEMO_ANNOTATION:v1"],"exon_phases":["DEMO_ANNOTATION:v1"]}},
  "molecular_effect": {"cds_edit_interval":[150,151],"cds_coordinate_system":"cds_0_based_half_open","source_refs":{"cds_edit_interval":["DEMO_MAPPING:v1"]},"products":[{"basis":"PREDICTED","frame_effect":"OUT_OF_FRAME","transcript_ref":"DEMO_FS_RNA.1#sequence:v1","coordinate_system":"transcript_1_based_closed","ptc_start":196,"source_refs":{"frame_effect":["DEMO_RECONSTRUCTION:v1"],"ptc_start":["DEMO_RECONSTRUCTION:v1"]}}]}
}
```

3. Splice donor canonica con skipping osservato in RNA; frame fornito dalla ricostruzione, PTC non determinato:

```json
{
  "variant": {"assembly":"DEMO_ASSEMBLY_1","contig":"DEMO_CONTIG_1","position":2151,"reference_allele":"G","alternate_allele":"A","consequence":"splice_donor_variant","coordinate_system":"genomic_1_based","source_refs":{"consequence":["DEMO_VEP:v1"]}},
  "disease_context": {"gene":"DEMO_GENE","disease":"DEMO_DISEASE","inheritance":"AD","molecular_mechanism":"LoF","confidence":"DEFINITIVE","scope":"DISEASE_SPECIFIC","source_refs":{"molecular_mechanism":["DEMO_CURATION:v1"],"confidence":["DEMO_CURATION:v1"],"scope":["DEMO_CURATION:v1"],"inheritance":["DEMO_CURATION:v1"]}},
  "transcript": {"accession":"DEMO_TRANSCRIPT.1","strand":"+","coordinate_system":"transcript_1_based_closed","cds_interval":[31,420],"exon_genomic_intervals":[[1001,1150],[2001,2150],[3001,3150]],"exon_coordinate_system":"genomic_1_based_closed","exon_phases":[0,0,0],"sequence_ref":"DEMO_TRANSCRIPT.1#spliced_dna:v1","source_refs":{"cds_interval":["DEMO_ANNOTATION:v1"],"exon_genomic_intervals":["DEMO_ANNOTATION:v1"],"exon_phases":["DEMO_ANNOTATION:v1"]}},
  "molecular_effect": {"splice_site_type":"DONOR","splice_site_genomic_position":2150,"splice_site_offset":1,"native_splice_motif":"GT","source_refs":{"splice_site_offset":["DEMO_MAPPING:v1"],"native_splice_motif":["DEMO_SEQUENCE:v1"]},"products":[{"basis":"OBSERVED","event_type":"EXON_SKIPPING","involved_exons":[2],"genomic_junctions":[[1150,3001]],"transcript_ref":"DEMO_SPLICE_RNA.1#sequence:v1","coordinate_system":"transcript_1_based_closed","frame_effect":"IN_FRAME","ptc_start":null,"evidence_quality":"Saggio RNA sintetico con controlli; nessuna calibrazione clinica reale.","source_refs":{"event_type":["DEMO_RNA:v1"],"involved_exons":["DEMO_RNA:v1"],"genomic_junctions":["DEMO_RNA:v1"],"frame_effect":["DEMO_RECONSTRUCTION:v1"],"evidence_quality":["DEMO_RNA:v1"]}}]}
}
```

4. Splice non canonica con sola annotazione VEP; nessun evento, frame o PTC noto:

```json
{
  "variant": {"assembly":"DEMO_ASSEMBLY_1","contig":"DEMO_CONTIG_1","position":2155,"reference_allele":"G","alternate_allele":"A","consequence":"splice_region_variant","coordinate_system":"genomic_1_based","source_refs":{"consequence":["DEMO_VEP:v1"]}},
  "disease_context": {"gene":"DEMO_GENE","disease":"DEMO_DISEASE","molecular_mechanism":"UNKNOWN","confidence":"UNKNOWN","scope":null},
  "transcript": {"accession":"DEMO_TRANSCRIPT.1","strand":"+","cds_interval":null,"exon_genomic_intervals":null,"sequence_ref":null},
  "molecular_effect": {"splice_site_type":"DONOR","splice_site_genomic_position":2150,"splice_site_offset":5,"source_refs":{"splice_site_offset":["DEMO_VEP:v1"]},"products":[{"basis":"UNKNOWN","event_type":"UNKNOWN","frame_effect":"UNKNOWN","ptc_start":null}]}
}
```
