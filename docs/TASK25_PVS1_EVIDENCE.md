# Riferimenti trascrizionali e ricostruzione nonsense locale

Aggiornato il 2026-10-29 dopo la [pulizia strutturale](HELPER_STRUCTURAL_CLEANUP.md).
Il precedente documento Task 25 e la sua integrazione con il servizio esterno
sono recuperabili nel branch `archive/helper-before-structural-cleanup-20261029`.

## Componenti conservati

- `core/acmg_transcripts.py`: `TranscriptReferenceProvider`, qualificazione di
  release/assembly/accession, catalogo del gene, esoni, cDNA/CDS/proteina,
  conversione coordinate e cache JSON delle risposte pubbliche Ensembl.
- `core/acmg_pvs1.py:nonsense`: ricostruzione della sostituzione stop-gain,
  verifica del REF sul trascritto, codoni, posizione del PTC e distanze dalle
  giunzioni. Il corpo della funzione e la versione della formula sono invariati.
- `core/acmg_sources.py:SourceManager`: accesso alle fonti biologiche esistenti.
- `pvs1/molecular.py`: riusa `nonsense()` e le primitive trascrizionali; gestisce
  i prodotti molecolari locali senza richiamare servizi di valutazione.
- `tests/fixtures/task25/hbb_ensembl_116.json` sotto `helper_next/`: fixture
  pubblica HBB conservata e verificata direttamente con il calcolo nonsense.

Questi componenti tecnici non scelgono una strength. La decisione sul trascritto
selezionato appartiene a `pvs1/calculator.py`; l'analisi comparativa di tutti i
trascritti appartiene a `core/acmg_molecular_impact.py` e `pvs1/impact.py`.

Il transformer del vecchio Evidence Contract, Coordinator, Assembler e i test
del validatore remoto sono stati rimossi. Nessuna regola PVS1 è stata migrata
o riscritta. Per il percorso attuale e i suoi limiti vedere
[ACMG Calculator PVS1](HELPER_NEW_ACMG_PVS1_MVP.md).

## Verifiche locali

```bash
PYTHONPATH=helper_next/src python -m pytest -q tests helper_next/tests/test_acmg_pvs1.py
```

La fixture HBB usa esclusivamente risposte pubbliche salvate; non scarica dati
e non importa o avvia un valutatore esterno.
