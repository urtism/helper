# Architecture Map For Codex

Keep context small. Start from the user request, then open only the listed area.

## Active Areas

- `Helper.py`: legacy PyQt GUI entry point.
- `HelperGUI/`: active PyQt widgets and GUI pages.
- `bin/`: legacy pipeline engine, tool wrappers, and execution helpers used by the PyQt side.
- `scripts/`: standalone utility scripts for VCF, annotation, features, sample sheets, and demos.
- `configs/`: JSON/CFG tool, pipeline, panel, and experiment definitions.
- `files/` and `target/`: static panel/reference resources; inspect filenames first, not contents.
- `helper_next/`: newer local web app, API, core services, Nextflow bridge, and tests.
- `workflows/nextflow/`: Nextflow workflow and process modules.
- `docs/`: human documentation. `docs/codex/` is Codex-specific working guidance.

## Helper Next Layout

- `helper_next/src/helper_next/api/`: FastAPI app and route handlers.
- `helper_next/src/helper_next/core/`: project discovery, samplesheets, panels, annotation, tool resolution, Nextflow manifest/run config builders.
- `helper_next/src/helper_next/core/tool_wrappers/`: tool invocation model and wrapper registry.
- `helper_next/src/helper_next/web/static/`: static frontend (`app.js`, `styles.css`, `sections/`).
- `helper_next/tests/`: focused tests for core/API behavior.

## Legacy Notes

- `legacy/root_gui/` contains old GUI copies for comparison. Do not edit unless specifically asked.
- Root-level `README.md`, `docs/STRUCTURE.md`, and `helper_next/README.md` already provide high-level project notes.
- Avoid scanning `.nextflow/`, `work/`, and logs for architecture questions.
