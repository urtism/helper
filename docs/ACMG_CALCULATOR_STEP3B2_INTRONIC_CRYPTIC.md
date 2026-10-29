# ACMG Calculator — STEP 3B.2: Intronic Cryptic Splice Sites

`reconstruct_splice_product()` supporta un donor intronico che estende l'esone a monte o un acceptor intronico che estende quello a valle, su strand ±.
Usa esclusivamente l'accession/versione fornito in `PVS1Input`, verificato contro il riferimento trascrizionale qualificato; nessuna ricerca o scelta di trascritti.
Nessuna modifica a `models.py`: l'evento riusa `CRYPTIC_SITE`, un solo `involved_exons` e una sola coppia orientata `genomic_junctions`, senza `retained_exon_interval`.
La coppia è `(ultima base a monte, prima base a valle)` genomica base 1: un confine si estende nell'introne adiacente, l'altro coincide con quello nativo.

## Input esplicito ed evidenza

Esempio sintetico sul più: esone 1 termina a 105, esone 2 inizia a 200; il nuovo donor a 108 include 106–108 nell'esone 1.

```python
event = {"basis": "PREDICTED", "event_type": "CRYPTIC_SITE", "involved_exons": [1],
         "genomic_junctions": [[108, 200]],
         "source_refs": {"genomic_junctions": ["synthetic:prediction:v1"],
                         "method": ["synthetic-algorithm"], "method_version": ["1.0"]}}
result = reconstruct_splice_product(sample, reference, event, "INTRONIC_RNA.1",
                                    genomic_reference=genome, intronic_sequence=supplied)
```

`genomic_reference` è un dizionario con `assembly`, `chromosome`, `source_ref`, `source_version`, `artifact_digest={"algorithm":"sha256","value":...}` e `reader`: un `IndexedFasta` già aperto dal chiamante.
Il chiamante gestisce apertura/chiusura e stabilità del file durante il calcolo. Le coordinate/letture FASTA sono genomiche ascendenti sullo strand più; gli alias cromosomici non sono ammessi implicitamente.
`intronic_sequence` è opzionale: se assente, si legge il tratto direttamente dal FASTA fornito.
Se presente, richiede `assembly`, `chromosome`, `genomic_interval=[inizio,fine]`, `strand`, `coordinate_system="genomic_1_based_closed"`, `sequence`, `source_ref`, `source_version`.
La sequenza fornita è orientata 5′→3′ come il trascritto; sul meno viene confrontata con il reverse complement della lettura genomica.
Il riferimento genomico deve concordare per assembly/cromosoma, checksum reale, basi dei due esoni adiacenti e copertura del tratto intronico. Il frammento fornito deve coincidere esattamente per intervallo, strand, lunghezza e basi non ambigue.
La sola provenance non verifica una sequenza: senza FASTA verificabile, con metadati mancanti o con discordanza si restituisce `INCOMPLETE`, senza prodotto inventato.
Il checksum legge l'intero FASTA a ogni chiamata intronica; non è introdotta una nuova cache. Il riferimento trascrizionale giuntato esistente non contiene gli introni.

Ogni nuovo evento intronico richiede fonte dell'evento e metodo in `source_refs`; la versione disponibile va in `source_refs.method_version`.
Le fonti possono descrivere algoritmo/predizione o evidenza RNA originale; `functional_evidence`, `evidence_quality` e tutte le fonti dell'evento sono conservati.
`PREDICTED` non diventa `OBSERVED`; OBSERVED richiede un riferimento originale sulla descrizione dell'evento, non soltanto il nome del metodo. UNKNOWN restituisce `INCOMPLETE`.
La ricostruzione computazionale non conferma il saggio: la valutazione della qualità e del valore biologico resta al futuro Calculator.

## Riuso e output

Riusa `IndexedFasta.sequence`, `sha256_file`, `complement` e le verifiche del trascritto; nessun nuovo provider o accesso remoto.
Lo span d'inclusione passa nel percorso comune: `reconstruct_cds`, `frame_effect`, `translate_altered_cds`, `junction_distances`, `protein_region_change`, validazione `PVS1Input`.
Si restituiscono RNA/CDS, frame, proteina/PTC quando determinabili, tutte le giunzioni effettive e distanze firmate sul prodotto. Lo stop nativo conservato/spostato non è un nuovo PTC.
L'audit conserva accession/versione, evento originale, sequenza verificata e sue fonti, copia dell'eventuale frammento fornito, confine genomico criptico e risultati tecnici.
Inclusioni UTR conservano la CDS e aggiornano le coordinate; inserzioni dentro START/STOP o terminazione irrisolta restano incomplete senza proteina/PTC inventati.
Restano esclusi intron retention completa, pseudoesoni, eventi multipli, ricerca automatica di siti, rilevanza biologica, NMD decisionale, strength PVS1 e regole VCEP.

## Verifica

`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=helper_next/src python -m unittest discover -s tests -p test_pvs1_molecular.py -v`

**37 test passati: 8 nuovi e 29 preesistenti**, soltanto il file molecolare. Fixture sintetiche FASTA/FAI: donor/acceptor ±, in-frame e frameshift con PTC, giunzioni/distanze, riuso delle primitive, metadati/checksum/basi/esoni discordanti, riferimento assente, limiti geometrici, UTR/START/STOP e conservazione di basis/fonti/metodo/versione/trascritto e input.
Nessuna modifica ai percorsi precedenti richiesta dall'interfaccia; regressioni exon skipping e criptici esonici superate. Nessuna suite completa, modifica al vecchio Engine/Calculator/frontend, commit o step successivo.
