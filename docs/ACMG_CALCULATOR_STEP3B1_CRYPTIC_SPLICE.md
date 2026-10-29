# ACMG Calculator — STEP 3B.1: Cryptic Splice Sites

`reconstruct_splice_product(sample, reference, event, product_ref)` supporta anche donor e acceptor criptici **esonici esplicitamente indicati**.
Lavora esclusivamente sull'accession/versione di `sample.transcript`, verificato contro il riferimento qualificato fornito: nessuna ricerca, selezione o valutazione biologica di altri trascritti.

## Input e confini

Si usa il record `MolecularProductData` esistente, con un solo nuovo campo opzionale indispensabile: `retained_exon_interval`.

```python
event = {
    "basis": "PREDICTED", "event_type": "CRYPTIC_SITE",
    "involved_exons": [2], "retained_exon_interval": [4, 9],
}
result = reconstruct_splice_product(sample, reference, event, "CRYPTIC_RNA.1")
```

L'intervallo conservato è base 1, chiuso, sull'RNA **reference** orientato 5′→3′; l'unico esone coinvolto usa l'indice reference base 1.
Donor: si conserva l'inizio originale e si anticipa la fine; il sito è l'ultima base conservata. Esempio: esone `[4, 12]` → `[4, 9]`.
Acceptor: si posticipa l'inizio e si conserva la fine; il sito è la prima base conservata. Esempio: esone `[7, 12]` → `[10, 12]`.
Il confine esplicito determina il tipo senza cercare siti nella sequenza. Occorre un esone a valle per il donor, a monte per l'acceptor.
Intervallo mancante, fuori esone, invariato, con entrambi i confini modificati o più esoni coinvolti: `INCOMPLETE` con motivo.
`EXON_SKIPPING` conserva il proprio comportamento; non accetta il nuovo campo valorizzato.

## Calcoli, output e provenance

Il nuovo ramo prepara lo span RNA rimosso e l'esone accorciato, poi usa il percorso comune dello STEP 3B per CDS, frame, traduzione, PTC e regione proteica.
Riusa `_reference`, `transcript_facts`, `mrna_to_genomic`, `reconstruct_cds`, `frame_effect`, `translate_altered_cds`, `junction_distances`, `protein_region_change` e la validazione `PVS1Input`.
Tutte le giunzioni risultanti sono riposizionate; gli estremi genomici orientati e il flag `new` comprendono il confine criptico anche sullo strand meno.
Le distanze restano firmate: ultima base esonica sul prodotto meno prima base del PTC; nessuna decisione NMD.
L'output conserva `data.transcript.accession` e `calculation.reference_transcript`; anche i risultati incompleti riportano l'accession/versione d'ingresso.
L'audit comprende evento originale, tipo/posizione del sito criptico e calcoli; fonti RNA, release/checksum del riferimento e versione software accompagnano i risultati.
`PREDICTED`/`OBSERVED` non cambiano; `UNKNOWN` resta incompleto. OBSERVED richiede una fonte sulla descrizione dell'evento, incluso il nuovo intervallo.
La ricostruzione non conferma sperimentalmente l'evento e non valuta qualità/quantità RNA. Nessun input o prodotto preesistente viene modificato.

## Limiti e verifica

Restano esclusi siti intronici, intron retention, pseudoesoni, ricerca automatica da VEP/SpliceAI/sequenza, analisi multitranscritto e rilevanza biologica.
Valgono i limiti dello STEP 3A/3B: riferimento completo qualificato, codice standard, nessun re-inizio/estensione UTR; START/STOP coinvolti o stop non risolto danno `INCOMPLETE` senza proteine/PTC inventati.
Non sono introdotti modelli aggiuntivi, servizi, database, API/frontend, strength PVS1 o regole ClinGen/VCEP.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=helper_next/src python -m unittest discover -s tests -p test_pvs1_molecular.py -v
```

**29 test passati: 7 nuovi test criptici e 22 molecolari preesistenti.** Fixture sintetiche qualificate, strand ±, donor/acceptor in-frame, frameshift con PTC, giunzioni/distanze e riuso tramite spy, UTR, START/STOP persi, coordinate insufficienti/invalide, basis/provenance/trascritto preservati, input immutabili e regressioni exon skipping.
Eseguito soltanto il file molecolare; nessuna suite completa, modifica al vecchio Engine o commit. Nessuno step successivo avviato.
