from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from helper_next.api.analysis import router as analysis_router
from helper_next.api.pipelines import router as pipelines_router
from helper_next.api.samplesheet import router as samplesheet_router
from helper_next.api.tools import router as tools_router
from helper_next.api.variants import router as variants_router
from helper_next.api.acmg import router as acmg_router
from helper_next.core.panels import load_panel_registry
from helper_next.core.acmg_service import ACMGService
from helper_next.core.project import get_project_paths, list_named_files
import helper_variants


def create_app():
    app = FastAPI(title="Helper Next", version="0.1.0")
    acmg_service = ACMGService()
    app.add_event_handler("startup", acmg_service.start)
    app.add_event_handler("shutdown", acmg_service.stop)
    app.include_router(samplesheet_router)
    app.include_router(analysis_router)
    app.include_router(pipelines_router)
    app.include_router(tools_router)
    app.include_router(variants_router)
    app.include_router(acmg_router)

    static_dir = Path(__file__).resolve().parents[1] / "web" / "static"
    variant_static_dir = Path(helper_variants.__file__).resolve().parent / "web" / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    app.mount("/variant-module", StaticFiles(directory=str(variant_static_dir)), name="variant-module")

    @app.get("/")
    def index():
        return FileResponse(str(static_dir / "index.html"))

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/project")
    def project():
        paths = get_project_paths()
        panel_registry = load_panel_registry(paths.configs)
        return {
            "root": str(paths.root),
            "configs": str(paths.configs),
            "pipelines": list_named_files(paths.pipelines, (".pipeline",)),
            "tool_configs": list_named_files(paths.configs, (".json", ".cfg")),
            "tool_config_files": list_tool_config_files(paths.configs),
            "gene_panel_designs": panel_registry["list"],
            "gene_panel_design_details": panel_registry,
            "scripts": list_named_files(paths.scripts, (".py",)),
        }

    return app


def list_tool_config_files(configs_dir):
    if not configs_dir.exists():
        return []
    return sorted(
        str(item.relative_to(configs_dir))
        for item in configs_dir.rglob("*")
        if item.is_file() and item.name.lower().endswith((".json", ".cfg")) and "tool" in item.name.lower()
    )


def list_gene_panel_designs(configs_dir):
    return load_panel_registry(configs_dir)["list"]


def load_gene_panel_design_details(configs_dir):
    return load_panel_registry(configs_dir)
