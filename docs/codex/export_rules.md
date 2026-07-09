# Export And Nextflow Rules

Use this for manifest, run config, workflow, and execution-output tasks.

## Main Files

- `helper_next/src/helper_next/core/nextflow.py`: manifest rows, validation, enabled workflow, run config writing.
- `helper_next/src/helper_next/api/analysis.py`: analysis submission, status, log/run reporting.
- `workflows/nextflow/main.nf`: workflow orchestration.
- `workflows/nextflow/modules/*.nf`: step implementations.
- `workflows/nextflow/nextflow.config`: profiles and runtime settings.
- `docs/NEXTFLOW_MIGRATION.md`: existing behavior notes and examples.

## Stable Export Concepts

- Manifest columns are intentionally stable; check `test_nextflow.py` before changing them.
- Run directories contain input snapshots, `manifest.tsv`, `run_config.json`, Nextflow logs/traces, `work/`, and `results/`.
- Step output/log directories are workflow-aware and should not be created for disabled steps.
- Status is built from manifest rows, per-sample status TSVs, trace files, and process liveness.

## Rules

- Do not change workflow semantics while editing docs or UI.
- If changing export shape, update tests and `docs/NEXTFLOW_MIGRATION.md`.
- Prefer focused tests in `helper_next/tests/test_nextflow.py` or `test_analysis.py`.
- Do not inspect `.nextflow/` or `work/` unless debugging a specific run.
