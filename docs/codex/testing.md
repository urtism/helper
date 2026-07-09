# Testing Guide

Run the narrowest relevant tests from the repository root.

```bash
python -m pytest helper_next/tests
```

Focused examples:

```bash
python -m pytest helper_next/tests/test_nextflow.py
python -m pytest helper_next/tests/test_analysis.py
python -m pytest helper_next/tests/test_samplesheet.py
python -m pytest helper_next/tests/test_tool_resolver.py helper_next/tests/test_tool_wrappers.py
```

## Map

- `test_nextflow.py`: manifest, validation, workflow selection, run config.
- `test_analysis.py`: API-side run submission, status, logs, normalized pipeline behavior.
- `test_samplesheet.py`: sample-sheet build/load behavior.
- `test_annotation.py`: VEP/annotation argument normalization.
- `test_tool_resolver.py` and `test_tool_wrappers.py`: tool invocation resolution.
- `test_project.py`: repository path discovery and panel listing.

## Rules

- Docs-only changes do not need tests; say so in the final response.
- For Python logic changes, run targeted tests for the touched module.
- For broad core/export changes, run all `helper_next/tests`.
- Do not run expensive real Nextflow jobs unless explicitly requested.
