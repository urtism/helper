# Helper

Repository di un progetto Python per la gestione di pipeline NGS e GUI PyQt5.

## Avvio

- Ambiente consigliato: `conda activate gatk43`
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
- `HelperGUI/`: codice di interfaccia PyQt5 e componenti GUI attivi
- `bin/`: motore pipeline e funzioni di esecuzione
- `configs/`: file di configurazione JSON e CFG
- `scripts/`: script di utilità per VCF, features, sample sheet
- `files/`: risorse di pannelli, target, trascritti e modelli
- `helper_next/`: prototipo web locale per una futura interfaccia FastAPI
- `legacy/root_gui/`: vecchie copie dei moduli GUI generati che prima erano nella root

La vecchia cartella `Powercall/` era una copia legacy non importata dal codice attivo ed è stata rimossa dalla struttura del progetto.

## Note di miglioramento

- completare la migrazione da import assoluti a package import
- sviluppare la nuova interfaccia in `helper_next/` senza bloccare la GUI PyQt
- sostituire path assoluti con percorsi configurabili
- aggiungere test automatici su parsing config, samplesheet e costruzione comandi
- definire un entry point CLI reale e stabile
