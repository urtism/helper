# ACMG Calculator — STEP 3B: Splice Exon-Skipping Reconstruction

Estensione locale dello [STEP 3A](ACMG_CALCULATOR_STEP3A_EVIDENCE_FUNCTIONS.md), nel perimetro scientifico dello [STEP 0](ACMG_CALCULATOR_STEP0_PVS1_MODEL.md). Una sola nuova funzione pubblica in `pvs1/molecular.py`; nessuna modifica ai modelli, al vecchio Engine o al frontend.

## Input effettivi

```python
reconstruct_splice_product(sample, reference, event=None, product_ref=None)
```

- `sample`: `PVS1Input` esistente. `transcript.accession` deve contenere la versione esatta. Gene, assembly e contig identificano il riferimento; REF/ALT e conseguenza VEP non selezionano l'evento e non vengono applicati alla sequenza. Questa funzione calcola esclusivamente lo skipping dichiarato, senza sommarvi un secondo edit allelico.
- `reference`: payload `data` qualificato del `TranscriptReferenceProvider` Task 25, già fornito dal chiamante. Richiesti release, checksum SHA-256 del bundle, convenzione coordinata, cDNA, CDS completa con START/STOP, proteina, esoni e giunzioni coerenti. Nessun accesso a rete/file o acquisizione automatica.
- `event`: record del modello esistente `MolecularProductData`. Richiede `basis` esplicita, `event_type="EXON_SKIPPING"` e `involved_exons` non vuoto. Gli esoni sono **indici base 1 nell'ordine 5′→3′ del trascritto selezionato e versionato**, anche sullo strand meno. La lista deve essere crescente, consecutiva e senza duplicati; ogni indice deve appartenere al riferimento. Esoni, CDS, sequenza, strand ed eventuali fasi dichiarati in `sample.transcript` vengono confrontati con il riferimento.
- `product_ref`: identificatore non vuoto dell'RNA risultante, distinto dall'accession del trascritto reference. Identifica l'asse delle coordinate calcolate; non è un accession sperimentale assegnato automaticamente.

Esempio di evento previsto:

```python
event = {
    "basis": "PREDICTED",
    "event_type": "EXON_SKIPPING",
    "involved_exons": [2, 3],
    "source_refs": {"involved_exons": ["synthetic:explicit-hypothesis:v1"]},
}
result = reconstruct_splice_product(sample, reference, event, "SKIP_RNA.1")
```

Per `OBSERVED` occorre almeno un riferimento all'evidenza RNA originale in `source_refs` su `basis`, `event_type` o `involved_exons`. È una verifica di presenza della provenance: la funzione non verifica il saggio o il contenuto della fonte. `functional_evidence`, `evidence_quality` e le fonti originali relative alla descrizione dell'evento vengono conservati. Eventuali conseguenze già presenti nel record d'ingresso rimangono nell'audit `calculation.input_event`; non sostituiscono i calcoli né vengono adottate come risultati sperimentali.

## Output e coordinate

Il risultato usa il contratto tecnico dello STEP 3A: `status` (`COMPLETE`/`INCOMPLETE`), `data`, `missing_data`, `warnings`. Non è un `PVS1Result`.

| Percorso | Contenuto |
|---|---|
| `data.transcript` | Fatti del trascritto **reference**, compatibili con `PVS1Input`, con fonti e fasi verificate. |
| `data.molecular_effect.products[0]` | Un prodotto con basis originale, tipo di evento, esoni saltati, RNA risultante, giunzioni genomiche, frame e PTC se determinabile. Regioni proteiche e distanze sono aggiunte solo quando calcolabili. |
| `data.molecular_effect.cds_edit_interval` | Span rimosso dalla CDS reference, base 0 semiaperto; omesso se lo skipping è esclusivamente non codificante. |
| `data.calculation.input_event` | Copia integrale dell'evento originale, separata dai risultati calcolati. Nessuna mutazione degli input o sostituzione di altri prodotti già presenti in `sample`. |
| `data.calculation.mrna_edit_interval` | Span rimosso dall'RNA reference, base 0 semiaperto, con etichetta coordinata esplicita. |
| `data.calculation.retained_exons`, `.junctions` | Indici reference degli esoni conservati e tutte le giunzioni effettive: esoni a monte/valle, ultima base esonica sull'RNA risultante, coppia genomica orientata e flag `new`. |
| `data.calculation.altered_cds` | Sequenza dei nucleotidi della CDS reference sopravvissuti allo skipping. Se START/STOP è perso, è una proiezione di sequenza, non una nuova ORF funzionale dimostrata. |
| `data.calculation.product_cds_start` | Posizione base 1 dello START originale sul prodotto, nulla se il codone è coinvolto nello skipping. |
| `data.calculation.original_start_retained`, `.original_stop_retained` | Integrità dei tre nucleotidi dei codoni originali, inclusi codoni distribuiti su più esoni. |
| `data.calculation.frame`, `.translation`, `.ptc_geometry`, `.protein_change` | Risultati tecnici delle primitive riutilizzate; i due ultimi blocchi compaiono solo se determinabili. |
| `data.calculation.source_ref`, `.software_version` | Identità/versione/release/checksum del riferimento e versione del modulo molecolare. Le fonti dei campi calcolati includono anche la provenance dell'evento, se fornita. |

RNA e CDS usano stringhe `ACGT` orientate come il trascritto, come nello STEP 3A. Non si applica un secondo reverse complement a un cDNA già orientato. Le giunzioni genomiche sono coppie `(ultima base dell'esone a monte, prima base dell'esone a valle)`, genomiche base 1: crescenti sullo strand più e decrescenti sul meno. Dopo uno skipping interno viene costruita la nuova giunzione fra gli esoni conservati adiacenti; tutte le giunzioni residue vengono riposizionate sull'RNA effettivo. Una perdita terminale non crea una giunzione inesistente.

`ptc_start` indica la prima base dello stop prematuro sull'RNA **risultante**, base 1. Le distanze firmate seguono esattamente lo STEP 3A: `ultima_base_esone_a_monte − ptc_start`, senza soglie o decisioni NMD. Lo stop originale conservato e spostato da uno skipping in-frame non diventa un nuovo PTC.

Le regioni proteiche sono intervalli chiusi base 1 sulla proteina reference, identificata dal suo accession disponibile o dal checksum della sequenza realmente usata. Il confronto conserva la convenzione di prefisso/suffisso comuni dello STEP 3A; `lost_protein_region` compare come intervallo solo per una perdita pura. Nessuna criticità funzionale viene dedotta.

## Ricostruzione e riuso

La funzione seleziona gli esoni esclusivamente dall'evento esplicito, concatena le parti conservate del cDNA e interseca lo span rimosso con la CDS reference. Ricostruisce le giunzioni dagli esoni conservati e orienta i loro estremi usando lo strand.

Sono riutilizzati `_reference` e `transcript_facts` per la qualificazione; `PVS1Input` per la compatibilità strutturale; `reconstruct_cds` per la delezione codificante; `frame_effect` per il delta e la congruenza modulo 3; `translate_altered_cds` per proteina, primo stop e nuovo PTC; `junction_distances` per la geometria; `protein_region_change` per la regione alterata/persa e le frazioni. Non sono duplicati traduzione, ricerca PTC, confronto proteico o formula delle distanze. Per uno skipping esclusivamente non codificante vengono conservate CDS e traduzione del riferimento già verificato, aggiornando l'asse RNA.

Esempi verificati con fixture sintetiche qualificate, entrambi gli strand: cDNA reference `GGGATGAAACTAAAGCAATAACCC`, CDS `ATGAAACTAAAGCAATAA`, proteina `MKLKQ`.

| Lunghezze esoni, in ordine trascrizionale | Skipping | Risultato |
|---|---|---|
| `[6, 3, 6, 9]` | `[2]` | CDS `ATGCTAAAGCAATAA`, `IN_FRAME`, proteina `MLKQ`, nessun nuovo PTC, residuo reference perso `[2, 2]`, giunzioni RNA `[6, 12]`. |
| `[6, 1, 5, 12]` | `[2]` | CDS `ATGAACTAAAGCAATAA`, `OUT_OF_FRAME`, proteina `MN`, nuovo PTC RNA `10`, giunzioni RNA `[6, 11]`, distanze `[[6, -4], [11, 1]]`. |
| `[6, 1, 2, 6, 9]` | `[2, 3]` | Stesso prodotto in-frame del primo esempio; nuova adiacenza fra esoni reference 1 e 4. |
| `[7, 3, 5, 9]` | `[2]` | Delezione a cavallo di codoni, `IN_FRAME`, proteina `MIKQ`, regione alterata reference `[2, 3]`, nessuna perdita pura assegnata. |

## Stati dell'evidenza e incompletezza

- `PREDICTED` resta `PREDICTED`: è la conseguenza calcolata di un evento ipotizzato esplicitamente dal chiamante.
- `OBSERVED` resta `OBSERVED` e conserva il riferimento RNA originale: descrive la base dell'**evento**, mentre sequenza, frame, PTC e regione proteica qui prodotti sono calcoli. Un warning esplicita che la ricostruzione non valida sperimentalmente l'evento. Non vengono interpretati qualità o quantità del saggio.
- Evento assente, non specificato o con basis `UNKNOWN`: `INCOMPLETE`, motivo in `missing_data`, nessuna sequenza/evento inventato da annotazione VEP, sito splice o score. L'evento originale, anche UNKNOWN, resta nell'audit.

`COMPLETE` riguarda questa operazione di sequenza e non dimostra un effetto biologico o una conseguenza clinica. Con START/STOP originale interamente o parzialmente rimosso, si restituiscono RNA, proiezione CDS, giunzioni e delta di lunghezza verificabili, ma `INCOMPLETE`, PTC nullo e nessuna proteina ricostruita. Il frame è in questo caso sola aritmetica di lunghezza rispetto alla CDS reference, non una dichiarazione su una nuova ORF. Non si scelgono start alternativi o stop nel 3′UTR. Se non è presente uno stop nella CDS modificata disponibile, può comparire `translated_prefix`, che non è una proteina completa; nessun intervallo proteico viene assegnato.

Errori di identità/versione, riferimenti insufficienti o incoerenti, esoni estranei e altre richieste non supportate restituiscono `INCOMPLETE` con motivo, conservando nell'audit soltanto l'evento d'ingresso quando non esiste una ricostruzione verificata. Un riferimento senza CDS completa e qualificata non è sufficiente per questo adapter, anche se dispone di frammenti RNA.

Supportati: un esone o un blocco consecutivo di esoni interi, codificanti, non codificanti o misti, strand più/meno; eventi in-frame/out-of-frame; perdite iniziali/terminali come ricostruzioni parziali quando compromettono START/STOP. Non supportati: esoni non consecutivi nello stesso evento, ordine invertito/duplicato, perdita di tutti gli esoni, esoni parziali, siti criptici, intron retention, pseudoesoni, riarrangiamenti complessi e riferimenti non qualificabili secondo lo STEP 3A. Eventi multipli rimangono chiamate e prodotti distinti; non se ne quantificano le proporzioni.

## Test eseguiti e limiti

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=helper_next/src python -m unittest discover -s tests -p test_pvs1_molecular.py -v
```

**22 test passati: 10 nuovi test splice e 12 test molecolari dello STEP 3A direttamente coinvolti.** Le fixture sono sintetiche e usano il `qualify` esistente; nessun saggio biologico o accesso remoto. Coperti skipping in-frame, frame alterato con PTC, strand più/meno, blocchi multiesonici, codoni attraversati dalla delezione, giunzioni effettive e riuso delle primitive tramite spy, UTR iniziali/interne/terminali, START/STOP persi anche parzialmente, stop non risolto, eventi assenti/UNKNOWN/non rappresentabili, riferimenti incompatibili/incompleti, conservazione di basis/provenance e immutabilità degli input.

Eseguito soltanto questo file di test. Nessuna suite completa, modifica al vecchio ACMG Engine/frontend, decisione NMD, strength PVS1, VCEP, calculator/classificatore, nuovo predittore, servizio/database o commit. Lo STEP 3C non è stato iniziato.
