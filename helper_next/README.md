# Helper Next

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
