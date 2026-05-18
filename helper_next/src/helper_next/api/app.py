from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from helper_next.api.samplesheet import router as samplesheet_router
from helper_next.core.project import get_project_paths, list_named_files


def create_app():
    app = FastAPI(title="Helper Next", version="0.1.0")
    app.include_router(samplesheet_router)

    static_dir = Path(__file__).resolve().parents[1] / "web" / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(static_dir / "index.html"))

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/project")
    def project():
        paths = get_project_paths()
        return {
            "root": str(paths.root),
            "configs": str(paths.configs),
            "pipelines": list_named_files(paths.pipelines, (".pipeline",)),
            "tool_configs": list_named_files(paths.configs, (".json", ".cfg")),
            "scripts": list_named_files(paths.scripts, (".py",)),
        }

    return app
