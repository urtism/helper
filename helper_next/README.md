# Helper Next

ACMG Interpretation Workbench (research): [installazione e uso](../docs/TASK22_WORKBENCH.md),
[stato e verifiche TASK 22](../docs/TASK22_STATUS.md),
[contratto ACMG Engine e limiti dell'audit](../docs/TASK22_ACMG_CONTRACT.md).

Task 23 criteria-only workspace: [audit, compatibility matrix, setup and validation](../docs/TASK23_ACMG_INTEGRATION.md).
The Task 22 engine protocols appear inside the existing variant detail, with
criteria status/strength, actual decision graphs and trace inspection, protocol
comparison, separate reviews, typed evidence corrections and JSON/CSV exports.

Prototype for the next Helper interface.

The goal is to develop a local web app without touching the existing PyQt GUI.
It reuses the current repository resources (`configs/`, `files/`, `scripts/`,
and `bin/`) while new code lives under `helper_next/`.

## Run

From this directory:

```bash
python -m pip install -e .
helper-next serve
```

Il server avvia anche ACMG Engine locale, se installato nel repository adiacente
`acmg-engine/.venv` o disponibile nel `PATH`, e riutilizza un motore già attivo.
Per un altro eseguibile usare `HELPER_ACMG_COMMAND`; per disabilitare l'avvio
automatico usare `HELPER_ACMG_AUTOSTART=0`.
I sei profili sperimentali selezionati sono elencati in
`configs/acmg_engine.json`; `ACMG_PROFILES_DIR` ha priorità su questa selezione.
La stessa configurazione abilita l'esecuzione research; l'ambiente
`ACMG_ENABLE_RESEARCH_INTERPRETATION` ha priorità su tale impostazione.
[Installazione e configurazione ACMG](../docs/TASK22_WORKBENCH.md).

Use `python -m pip` rather than plain `pip` in the `gatk43` environment. On
some workstations the `pip` command still points to Python 2.7.

Then open:

```text
http://127.0.0.1:8765
```

During early development you can also run:

```bash
uvicorn helper_next.api.app:create_app --factory --reload --port 8765
```

## Structure

- `src/helper_next/api/`: FastAPI app and HTTP routes.
- `src/helper_next/core/`: repository discovery and future pipeline services.
- `src/helper_next/web/static/`: first static frontend.
- `tests/`: future tests for API and core services.

## Migration Strategy

1. Keep the current PyQt GUI working.
2. Expose read-only project/config discovery in Helper Next.
3. Add safe builders for samplesheets and pipeline commands.
4. Add execution and log streaming after the command layer is tested.

## Nextflow Bridge

Helper Next can now generate a stable TSV manifest from the existing Helper
samplesheet JSON:

```bash
helper-next nextflow-manifest \
  --samplesheet run.samplesheet \
  --pipeline ../configs/pipelines/Germline.pipeline \
  --tools ../configs/tools_cfg/tools.cfg \
  --out work/manifest.tsv \
  --run-config work/run_config.json
```

See `../docs/NEXTFLOW_MIGRATION.md` for the initial Nextflow workflow.
