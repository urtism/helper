# Data And Config Model

Use this for samplesheet, config, panel, and tool-resolution tasks.

## Main Data Sources

- `configs/pipelines/*.pipeline`: pipeline definitions and enabled workflow steps.
- `configs/tools_cfg/tools.cfg`: newer tool configuration used by Helper Next.
- `configs/Tools*.cfg*`: legacy tool configuration.
- `configs/Powercall*.json`: legacy analysis/panel presets.
- `configs/experiment_list.cfg` and `configs/panel.cfg`: panel/experiment lookup data.
- `files/` and `target/`: static panel, transcript, exon, and target resources.

## Core Code To Inspect

- Samplesheets: `helper_next/src/helper_next/core/samplesheet.py`
- Panels: `helper_next/src/helper_next/core/panels.py`
- Project paths: `helper_next/src/helper_next/core/project.py`
- Tool resolution: `helper_next/src/helper_next/core/tool_resolver.py`
- Tool wrappers: `helper_next/src/helper_next/core/tool_wrappers/`
- Legacy parsing/execution: `bin/functions.py`, `bin/functions2.py`, `bin/pipeline.py`, `bin/pipeline2.py`

## Rules

- Preserve existing keys and nested structures unless a schema migration is requested.
- Use JSON parsing for JSON-like files; avoid regex edits to structured config.
- Inspect one representative config before changing parsing logic.
- Do not bulk-edit generated config/data files.
- When adding fields, add tests that prove old configs still work.
