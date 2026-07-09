# Codex Working Rules

Use this repository with a narrow context budget.

## First Steps

- Read this file first, then only the relevant file in `docs/codex/`.
- Prefer `rg --files`, `find -maxdepth`, and targeted `rg -n` over broad scans.
- Do not read full files unless the task requires implementation details from that file.
- Ignore generated/runtime folders unless explicitly requested: `.git/`, `.nextflow/`, `work/`, `target/`, `__pycache__/`, `.pytest_cache/`, `helper_next/src/helper_next.egg-info/`.

## Scope Rules

- Modify only files directly related to the user request.
- Do not refactor broadly, rename modules, reformat unrelated files, or change application behavior unless requested.
- Preserve existing JSON/CFG/pipeline/sample-sheet structures unless the user asks for a schema change.
- Treat `legacy/root_gui/` as reference material only; active GUI code is in `HelperGUI/`.
- Prefer the newer `helper_next/` implementation for web/API/Nextflow work.

## Where To Look

- Architecture map: `docs/codex/architecture.md`
- UI rules: `docs/codex/ui_rules.md`
- Data/config model: `docs/codex/data_model.md`
- Nextflow/export behavior: `docs/codex/export_rules.md`
- Tests: `docs/codex/testing.md`
- Prompt patterns: `docs/codex/prompt_templates.md`

## Reporting

- Do not print full files in final responses.
- Summarize only changed files, verification performed, and remaining risks.
- Mention skipped tests or commands when relevant.
