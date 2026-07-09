# Codex Prompt Templates

Use these to keep future sessions narrow. Replace placeholders and name exact files when possible.

## General

```text
Read AGENTS.md and docs/codex/<relevant-doc>.md first.
Change only <files or area>. Avoid work/, .nextflow/, target/, and legacy/ unless needed.
Preserve existing behavior and data structures except <specific requested behavior>.
Run <targeted test command> if code changes; skip tests for docs-only changes.
Final response: changed files, tests, risks only.
```

## Nextflow Or Export

```text
Read AGENTS.md and docs/codex/export_rules.md.
Start with helper_next/src/helper_next/core/nextflow.py, helper_next/src/helper_next/api/analysis.py, workflows/nextflow/, and targeted tests.
Do not change manifest columns or run directory shape unless explicitly requested.
```

## UI

```text
Read AGENTS.md and docs/codex/ui_rules.md.
Helper Next UI: inspect only the target section, api.js if needed, index.html, and styles.css.
PyQt: inspect only the target widget in HelperGUI/ and its direct caller.
Do not restyle unrelated screens.
```

## Config Or Data

```text
Read AGENTS.md and docs/codex/data_model.md.
Inspect one representative config and the parser/resolver that consumes it.
Preserve keys and backward compatibility. Do not bulk-edit config/resource files.
```
