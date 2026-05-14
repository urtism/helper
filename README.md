# Helper

Repository di un progetto Python per la gestione di pipeline NGS e GUI PyQt5.

## Avvio

- GUI principale: `python Helper.py`
- CLI minimale: `python bin/main.py --help`

## Dipendenze

Installa le dipendenze con:

```bash
pip install -r requirements.txt
```

## Struttura principale

- `Helper.py`: entry point della GUI principale
- `bin/main.py`: entry point CLI iniziale (placeholder per la pipeline)
- `HelperGUI/`: codice di interfaccia PyQt5 e componenti GUI
- `bin/`: motore pipeline e funzioni di esecuzione
- `configs/`: file di configurazione JSON e CFG
- `scripts/`: script di utilità per VCF, features, sample sheet

## Note di miglioramento

- separare la logica applicativa dalla UI generata da PyQt5
- consolidare i file duplicati e i moduli legacy
- aggiungere test automatici e infrastruttura di packaging
- definire un entry point CLI reale e stabile
