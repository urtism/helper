# ACMG Calculator — STEP 3A: Molecular Evidence Computation

> Nota 2026-10-29: audit/inventario storico. I riferimenti al Workbench, ai relativi test e al vecchio contratto descrivono lo stato precedente alla rimozione; non sono istruzioni operative attuali. Per componenti conservati, cache e verifiche aggiornate vedere [HELPER_STRUCTURAL_CLEANUP.md](HELPER_STRUCTURAL_CLEANUP.md).

Libreria tecnica locale, senza strength, NMD decisionale o inferenze cliniche. Riferimenti di perimetro: [STEP 0](ACMG_CALCULATOR_STEP0_PVS1_MODEL.md), [STEP 1](ACMG_CALCULATOR_STEP1_RULES_DESIGN.md), [STEP 2](ACMG_CALCULATOR_STEP2_MODELS.md), [Task 25](TASK25_PVS1_EVIDENCE.md) e [Mechanism Evidence Cache](TASK27A_MECHANISM_EVIDENCE_CACHE.md).

## Differenze minime del contratto, definite prima dell'implementazione

I 27 campi comuni rimangono invariati. Il record condiviso `MolecularProductData` necessita di due proprietà opzionali aggiuntive:

- `ptc_junction_distances`: coppie `(posizione_giunzione_RNA, distanza_nt)` sul prodotto risultante, dove posizione = ultima base dell'esone a monte, base 1; distanza firmata = posizione − prima base del PTC. Comprende anche giunzioni a monte; non applica soglie NMD. La ridondanza conserva il calcolo trasportato e la sua convenzione verificabile.
- `altered_protein_region`: intervallo chiuso base 1 della proteina reference che differisce dal prodotto; può comprendere residui sostituiti, non solo persi. Usa `protein_accession` e `protein_coordinate_system`. Non implica criticità funzionale.

CDS modificata, edit e quantificazioni restano nei dizionari tecnici restituiti dalle funzioni; il prodotto compatibile con PVS1Input conserva la sequenza RNA risultante e i due fatti necessari sopra. Nessun modello parallelo, resolver o framework di orchestrazione.

## Contratto e confini dei calcoli

Il modulo unico è `pvs1/molecular.py`. Gli ingressi principali sono `PVS1Input` e il **payload `data` qualificato** del `TranscriptReferenceProvider` Task 25, non un generico record VEP. Nessun provider o database viene istanziato. Le funzioni importate da HELPER sono funzioni pure; non viene chiamato il vecchio Engine.

Ogni funzione pubblica restituisce un dizionario tecnico con `status: COMPLETE/INCOMPLETE`, `data`, `missing_data` e `warnings`. Non è un PVS1Result. In caso di dati insufficienti `data` può essere nullo oppure contenere soltanto risultati parziali verificati. `COMPLETE` riguarda l'operazione, non la completezza di una classe PVS1 né la sua applicabilità clinica.

`compute_molecular_evidence` restituisce `data.transcript` e `data.molecular_effect` compatibili con il solo PVS1Input, più `data.calculation` per formule, sequenze intermedie e quantificazioni. Non modifica l'input, non sostituisce evidenze RNA preesistenti e non sceglie VCEP/policy. Il prodotto generato è **PREDICTED** sullo splicing reference; non è prova RNA e non esclude un diverso effetto splice.

- Identità: transcript accession/versione esatta, gene, assembly e contig devono concordare con il riferimento. Richiesti release, convenzione qualificata e checksum del bundle sorgente. Sono ricontrollati cDNA/CDS/proteina, esoni e giunzioni. Il checksum identifica il bundle originale: acquisizione e verifica del bundle restano responsabilità del provider esistente.
- Sequenze: riferimento completo e non ambiguo, cromosomi nucleari primari, codice genetico standard. Sequenze ambigue, CDS parziali, codici alternativi e riferimenti mancanti non ricevono sostituzioni inventate. Le funzioni primitive su stringhe richiedono un riferimento dichiarato e dati già qualificati dal chiamante.
- Varianti: REF/ALT letterali già normalizzati da HELPER; validazione del REF completo contro il cDNA, reverse complement e mappatura riusati. L'ancora VCF viene rimossa sull'asse genomico **prima** dell'orientamento, evitando lo spostamento del locus in ripetizioni sullo strand meno. Non è una nuova normalizzazione VCF/HGVS.
- Mappatura: genoma e RNA base 1; span degli edit CDS/RNA base 0 semiaperti. Indel non contigui o al confine esonico, varianti introniche e alleli simbolici sono incompleti, senza inferire un evento splice/CNV. L'identità cromosomica è esatta, senza alias impliciti.
- Traduzione: per `stop_gained` il PTC viene da **`acmg_pvs1.nonsense` Task 25**, chiamato direttamente. La nuova funzione traduce indel qualificati usando `acmg_transcripts.translate`; uno stop normale conservato ma spostato da un indel in-frame non è un nuovo PTC. Inizio/stop nativo coinvolti o assenza di stop nel tratto CDS disponibile producono INCOMPLETE; nessun re-inizio o allungamento automatico nel 3′UTR.
- Geometria: le giunzioni RNA downstream dell'edit sono spostate del delta di lunghezza sul prodotto. Distanza = fine dell'esone a monte − prima base del PTC, senza la correzione inclusiva +1 del vecchio contratto e senza soglie ClinGen/VCEP. Per giunzioni a monte il valore è negativo; nessuna downstream significa offset next/last nullo, non un verdetto NMD.
- Proteina: confronto di prefisso e suffisso comuni non sovrapposti; conteggio e frazione dei residui reference differenti, senza allineamento funzionale. Ripetizioni possono rendere non unica la localizzazione biologica: l'intervallo è una convenzione deterministica di confronto delle stringhe. `lost_protein_region` è valorizzato solo per una delezione pura della sequenza; alterazioni miste restano `altered_protein_region`. Nessuna criticità o funzione residua viene dedotta.
- Provenance: riferimento/versione/release/checksum e versione dell'algoritmo accompagnano i campi calcolati. Se il provider non conserva un accession proteico, il riferimento proteico è l'identificatore immutabile `sha256` della sequenza reference realmente usata; non viene inventato un ENSP/RefSeq. Le evidenze biologiche dell'input restano inalterate, comprese quelle sconosciute.

## Inventario di riuso prima delle nuove funzioni

Percorsi abbreviati: **M** = `pvs1/molecular.py`; **T** = `helper_next/src/helper_next/core/acmg_transcripts.py`; **N** = `helper_next/src/helper_next/core/acmg_pvs1.py`; **I** = `helper_next/src/helper_variants/indexer.py`; **C** = `helper_next/src/helper_next/core/acmg_mechanism_store.py`.
Le funzioni “proposte” mancanti sotto sono nomi di inventario, non stub o nuove infrastrutture implementate.

| Nome proposto/utilizzato | Funzione esistente riutilizzabile | File | Input | Output | Varianti | Limiti |
|---|---|---|---|---|---|---|
| Parsing/normalizzazione già esistenti | `read_vcf`, `normalize_allele`, `_record_annotations` | I | VCF/header/CSQ/ANN, FASTA qualificato per left alignment | Allele normalizzato e annotation selezionata | Tutte come annotazioni | `_record_annotations` scrive nell'indice; non è un parser puro nuovo. Senza FASTA il left alignment non è completo; annotazione non dimostra conseguenza molecolare. |
| Riferimento trascrizionale esistente | `TranscriptReferenceProvider.get`, `qualify` | T | Transcript/versione, assembly, release; cache/bundle | Riferimento qualificato con cDNA/CDS/esoni/proteina | Tutte | Nessuna nuova acquisizione in STEP 3A; RefSeq diretto e codici non standard esclusi dal provider. `qualify` è usato anche nelle fixture sintetiche. |
| `transcript_facts` | `genomic_to_mrna`, `mrna_to_genomic` e struttura già qualificata | M + T | PVS1Input e riferimento | Blocco Transcript, fasi codificanti | Tutte, come base tecnica | Rilevanza biologica non calcolabile; accession/versione indispensabili. |
| `map_variant_to_cds` | `genomic_to_mrna`, `mrna_to_genomic`, `complement` | M + T | Allele e riferimento coerenti | Edit CDS/RNA e REF/ALT orientati | Nonsense, frameshift, indel in-frame; base per start-loss | Nessuna mappatura di indel intronici, crossing o confini non qualificati; non ricostruisce CNV/splice. |
| `reconstruct_cds` | Nessuna funzione indel completa trovata nel perimetro | M | CDS, span, REF/ALT trimmed, riferimento fonte | CDS modificata | Ogni evento già espresso come edit CDS esatto | Non seleziona l'evento; verifica il REF e gli estremi; nessuna sequenza genomica inventata. |
| PTC nonsense | `nonsense` | N, richiamato da M | Identità, annotation selezionata, riferimento | PTC, codoni e audit Task 25 | Stop-gain, sostituzioni contigue di uguale lunghezza | Nessuna duplicazione della ricerca PTC nonsense; nessun frameshift nel Task 25. |
| `translate_altered_cds` | `translate` | M + T | CDS reference/modificata, edit, inizio CDS RNA e fonte | Proteina, primo stop e nuovo PTC se determinato | Indel qualificati; riusabile dopo eventi specificati | Non è un analizzatore splice/CNV; richiede inizio e stop reference conservati come contesto. Nessun re-inizio. |
| `frame_effect` | Nessuna funzione indel equivalente trovata | M | Due CDS e fonte | Delta nt e IN_FRAME/OUT_OF_FRAME | Tutti gli edit già qualificati | Aritmetica, non funzione proteica. |
| `junction_distances` | Convenzione geometrica in `nonsense` | M + N | PTC, giunzioni RNA del prodotto e riferimento | Coppie posizione/offset, next/last downstream | Tutti i prodotti qualificati | Nessuna soglia NMD; il wrapper aggiorna soltanto giunzioni di edit esonici locali. |
| `protein_region_change` | Proteina reference già presente nel provider | M + T | Proteine complete e fonte | Regioni differenti/perse, conteggi e frazione | Tutti i prodotti traducibili | Nessuna criticità, domini, percentuale di funzione o rescue dedotti. |
| `compute_molecular_evidence` | `nonsense` e primitive sopra | M | PVS1Input, riferimento, identificativo del prodotto | Blocchi compatibili e audit; possibile risultato parziale | Nonsense/indel locali; start-loss resta parziale | Sola composizione delle funzioni comuni, senza orchestratore di fonti, regole o classificazioni. |
| `reconstruct_splice_product` (proposta) | Nessuna ricostruzione specifica trovata; `technical_consequence` riconosce solo annotation | Da realizzare; N per annotation | Evento esplicito, coordinate, sequenze e basis | Prodotto RNA ricostruito | Splice canoniche/non canoniche | Non implementata; non basta il dinucleotide o uno score splice. |
| `find_candidate_start_codons` (proposta) | Nessuna funzione specifica trovata | Da realizzare | Sequenza qualificata e frame | Candidati di sequenza e posizione | Start-loss | Non implementata; un ATG candidato non dimostra un inizio funzionale. |
| `map_exon_event` / `reconstruct_exon_event` (proposte) | Esoni e coordinate di T; nessun interprete CNV qualificato trovato | Da realizzare | Breakpoint, esoni, copie, sede, orientamento/tandem | Evento e CDS risultante | Delezioni/duplicazioni esoniche | Nessuna ricostruzione CNV specifica implementata; la sola etichetta VEP non basta. |
| Lettura meccanismo dalla cache esistente | `MechanismStore.peek`, `source_record`; `resolve_gene_disease_mechanism` | C; `core/acmg_mechanisms.py` | Chiave gene–malattia–ereditarietà qualificata, eventuale snapshot | Asserzioni, conflitti, provenance | Tutte | `peek` è read-only senza creazione DB; resolver/record access hanno altri side effect e non sono invocati qui. Il resolver default può aggiornare le fonti: non usarlo implicitamente offline. Nessuna promozione automatica a DEFINITIVE. |
| Lettura rilevanza/regioni/rescue/RNA (necessaria) | Campi/unknown Task 25 e dati curati eventualmente forniti | N / fonti curate esterne | Curazioni, trascritti pertinenti e saggi | Evidenze biologiche con fonti e limiti | Tutte secondo ramo | Non è stato trovato nel perimetro un recupero completo autonomo; nessuna ricostruzione da MANE, constraint o sola sequenza. |

## Matrice di copertura dei dati PVS1

Stati: **IMPLEMENTED** = calcolo presente e verificato in questo step; **EXISTING_REUSABLE** = funzione preesistente individuata; **PARTIAL** = disponibili solo componenti o un sottocaso; **MISSING** = funzione specifica assente; **REQUIRES_EXTERNAL_EVIDENCE** = fatto biologico non deducibile deterministicamente dalla sola sequenza. “Non eseguito” non equivale a funzione mancante.

| Dato PVS1 | Funzione | Fonte | Varianti | Implementato | Testato |
|---|---|---|---|---|---|
| Identità VCF/VEP | `read_vcf`, `normalize_allele`, `_record_annotations` | I, VCF/FASTA/CSQ/ANN | Tutte, solo annotazione | EXISTING_REUSABLE | Non rieseguiti indexer/DB |
| Riferimento CDS/esoni qualificato | `TranscriptReferenceProvider.get`, `qualify` | T, cache/bundle versionato | Tutte | EXISTING_REUSABLE | `qualify` su fixture locali; nessun get/HTTP |
| Coordinate trascrizionali e fasi | `transcript_facts`, mapping T | M + T | Tutte come base tecnica | IMPLEMENTED | Entrambi gli strand, fasi parzialmente note e discordanti |
| Giunzioni reference | `qualify`, `transcript_facts` | Esoni T | Tutte | EXISTING_REUSABLE | Coerenza RNA/esoni e coordinate |
| Variante sulla CDS | `map_variant_to_cds` | M + T | Nonsense/frameshift/indel locali | IMPLEMENTED | REF errato, strand ±, ancora ripetuta sul meno, confini |
| CDS modificata | `reconstruct_cds` | M, edit verificato | Tutti gli edit già specificati | IMPLEMENTED | Sostituzione, inserzione, delezione; mismatch/incompletezza |
| Frame del prodotto | `frame_effect` | M, lunghezze delle CDS | Tutti gli edit già specificati | IMPLEMENTED | Frameshift e indel in-frame |
| PTC nonsense | `nonsense` Task 25 | N, CDS e reference | Stop-gain | EXISTING_REUSABLE | Richiamo diretto verificato con spy, strand ± |
| Nuovo stop/PTC da indel | `translate_altered_cds` | M + `translate` T | Frameshift/indel qualificati | IMPLEMENTED | Nuovo PTC; stop normale spostato; nessuno stop nel tratto |
| Distanze dalle giunzioni del prodotto | `junction_distances` | M, geometria RNA aggiornata | Prodotti locali qualificati | IMPLEMENTED | Giunzione a distanza 0, shift da indel, esone terminale e nessuna giunzione |
| Regione proteica alterata/persa | `protein_region_change` | M, sequenze | Prodotti traducibili | IMPLEMENTED | Sostituzione/alterazione, perdita, inserzione, frazioni |
| Evento splice canonico specificato | `reconstruct_splice_product` (proposta) | Evento e riferimenti richiesti | Splice canoniche | MISSING | Verificato il rifiuto di inferenza dal sito |
| Evento non canonico specificato | Stessa funzione proposta | Evento e riferimenti richiesti | Splice non canoniche | MISSING | Nessun test di ricostruzione specifica |
| Prodotto/frame/PTC di un evento splice | Primitive CDS/traduzione, dopo qualificazione del prodotto | M + dato evento esterno | Splice canoniche/non canoniche | PARTIAL | Primitive comuni testate; nessun adapter splice completo |
| Natura PREDICTED/OBSERVED/UNKNOWN | `MolecularProductData`; wrapper genera solo PREDICTED | PVS1Input e provenance | Tutte | PARTIAL | Nessuna osservazione RNA inventata o sostituita; acquisizione RNA non implementata |
| Start originario modificato | Mappatura/CDS; traduzione si arresta come incompleta | M + riferimento | Start-loss | PARTIAL | Nessun PTC/re-inizio assegnato automaticamente |
| ATG alternativi, posizione/differenza del prodotto | `find_candidate_start_codons` (proposta) | Sequenza qualificata | Start-loss | MISSING | Non implementato/testato |
| Inizio alternativo funzionale dimostrato | Lettura evidenza dedicata | Curazione funzionale/clinica | Start-loss e rescue | REQUIRES_EXTERNAL_EVIDENCE | Nessuna deduzione da ATG |
| Esoni e breakpoint di una delezione | `map_exon_event` (proposta); esoni T disponibili | Evento strutturale qualificato | Delezioni esoniche | PARTIAL | Solo primitive di edit; nessuna delezione multiesonica ricostruita |
| Struttura/tandem di una duplicazione | `map_exon_event` (proposta) | Copie, sede, orientamento documentati | Duplicazioni esoniche | MISSING | Non implementato/testato |
| CDS/frame/PTC da CNV qualificata | `reconstruct_exon_event` proposta + primitive comuni | Evento strutturale e CDS | Delezioni/duplicazioni esoniche | PARTIAL | Nessun adapter CNV completo o analisi di riarrangiamenti complessi |
| Meccanismo gene–malattia/ereditarietà | Accessi cache esistenti | C, G2P/GenCC/Dosage e loro limiti | Tutte | EXISTING_REUSABLE | Ispezione soltanto; nessuna lettura DB/fonte in questo step |
| LoF clinicamente pertinente e confidence | Curazione delle asserzioni/conflitti | Cache + evidenza specifica | Tutte | REQUIRES_EXTERNAL_EVIDENCE | Non calcolabile dalla sequenza; nessuna conversione automatica |
| Rilevanza del trascritto/esone | Evidenza funzionale/espressiva documentata | Fonti curate; MANE da solo insufficiente | Tutte secondo ramo | REQUIRES_EXTERNAL_EVIDENCE | Campi dell'input conservati; nessuna deduzione |
| Regioni proteiche critiche | Curazione funzionale/clinica | Saggi/varianti pertinenti | Prodotti senza NMD e in-frame | REQUIRES_EXTERNAL_EVIDENCE | Intervallo differente non diventa critico |
| Rescue e livelli funzionali residui | Curazione isoforme, espressione e funzione | Dati gene–malattia/tessuto specifici | Tutte secondo ramo | REQUIRES_EXTERNAL_EVIDENCE | Nessuna deduzione da sequenza/constraint |
| Evidenza e qualità RNA | Lettura di saggi con fonte, tessuto/controlli/quantità | Dati RNA esterni | Splice e altri rescue | REQUIRES_EXTERNAL_EVIDENCE | Nessun saggio/predittore introdotto |
| Provenance computazionale | Citation del riferimento e versione algoritmo | M + provider Task 25 | Tutti i calcoli implementati | IMPLEMENTED | Riporto nei blocchi compatibili; input non modificato |

## Verifica mirata e limiti residui

Nuovo file unico: `tests/test_pvs1_molecular.py`. **12 test passati**; riferimenti sintetici coerenti qualificati con `qualify` esistente. Coperti nonsense, frameshift con stop, indel in-frame, strand ±, ripetizione/ancora sul meno, posizioni del PTC, distanza giunzionale, riferimenti insufficienti, coordinate/alleli incoerenti, start-loss/splice non risolti e compatibilità delle due proprietà aggiunte al modello.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=helper_next/src python -m unittest discover -s tests -p test_pvs1_molecular.py -v
```

Eseguiti soltanto i nuovi test mirati; nessuna suite completa, HTTP, server, benchmark o commit. I test preesistenti di modelli, indexer, provider remoto e Mechanism Cache non sono stati eseguiti. Nessuna modifica a HELPER, vecchio Engine, frontend, calculator.py o rules.py.

Le sette categorie sono tutte rappresentate nella mappa delle necessità; non sono tutte implementate integralmente. Restano da realizzare funzioni specifiche per eventi splice, candidati start alternativi e CNV; meccanismo clinico, criticità, rilevanza, RNA e rescue richiedono evidenze esterne appropriate. Nessuna strength né decisione NMD/ClinGen/VCEP viene prodotta. Non è iniziato lo STEP 3B.
