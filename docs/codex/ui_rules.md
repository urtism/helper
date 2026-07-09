# UI Rules

Use this only for UI-facing tasks.

## PyQt GUI

- Active PyQt code lives in `HelperGUI/`; `Helper.py` wires the main window.
- Common pages:
  - `HelperGUI/analysis_page.py`
  - `HelperGUI/sample_organizer.py`
  - `HelperGUI/samplesheet_designer.py`
  - `HelperGUI/pipeline_designer.py`
  - `HelperGUI/tool_settings.py`
- Preserve existing widget names, signal patterns, and file formats.
- Do not modernize or restyle the PyQt app unless requested.

## Helper Next Web UI

- Static frontend lives in `helper_next/src/helper_next/web/static/`.
- Main files:
  - `index.html`: shell markup.
  - `app.js`: app bootstrapping and shared behavior.
  - `api.js`: HTTP helpers.
  - `styles.css`: visual rules.
  - `sections/samplesheet.js`, `sections/analysis.js`, `sections/file_picker.js`: page-specific logic.
- API routes are under `helper_next/src/helper_next/api/`.
- Keep controls consistent with existing dense workflow UI. Avoid marketing-style pages.

## Context Budget

- For UI changes, inspect the target section file plus `index.html` and `styles.css` only when needed.
- Do not read all static JS before making a small section-level change.
