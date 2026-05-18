# Struttura del progetto

Questo documento descrive la struttura attuale dopo la prima pulizia dei file legacy.

## Codice attivo

- `Helper.py`: entry point della GUI.
- `HelperGUI/`: package PyQt5 usato da `Helper.py`.
- `bin/`: motore della pipeline e wrapper degli strumenti esterni.
- `scripts/`: script di supporto per VCF, annotazione, feature extraction e sample sheet.
- `configs/`: configurazioni JSON/CFG e definizioni delle pipeline.
- `files/`: risorse statiche usate dalle configurazioni.
- `helper_next/`: sottoprogetto sperimentale per una nuova app web locale.

## Legacy

- `legacy/root_gui/`: copie generate dei moduli GUI che prima erano nella root. Sono conservate per confronto storico, ma il codice attivo importa da `HelperGUI/`.

La cartella `Powercall/` è stata rimossa perché non risultava importata dal codice attivo ed era una copia storica con file UI/build duplicati.

## Prossimi refactor consigliati

- Convertire `bin/` in un package Python con import relativi espliciti.
- Espandere `helper_next/` con builder per samplesheet, pipeline e log streaming.
- Centralizzare path e nomi ambiente Conda in un modulo/config dedicato.
- Eliminare o archiviare i file legacy dopo una verifica funzionale della GUI.
- Aggiungere test minimi prima di cambiare la logica dei filtri e delle feature.
