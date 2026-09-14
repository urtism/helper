import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from helper_next.core.pipelines import (
    PIPELINE_CATALOG,
    PipelineError,
    delete_pipeline,
    list_pipelines,
    load_pipeline,
    new_pipeline_config,
    pipeline_tool_catalog,
    save_pipeline,
    validate_pipeline,
)
from helper_next.core.project import get_project_paths


router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])


class PipelineDraft(BaseModel):
    config: Dict[str, Any]


class PipelineSaveRequest(PipelineDraft):
    name: str
    overwrite: bool = False


class NewPipelineRequest(BaseModel):
    template: Optional[Dict[str, Any]] = None


def api_error(exc, status_code=400):
    raise HTTPException(status_code=status_code, detail=str(exc))


@router.get("")
def pipeline_index():
    paths = get_project_paths()
    references = []
    tools_config = {}
    tools_path = paths.configs / "tools_cfg" / "tools.cfg"
    try:
        with tools_path.open() as handle:
            tools_config = json.load(handle)
        references = tools_config.get("refGenomes_list", [])
    except (OSError, ValueError):
        pass
    return {
        "pipelines": list_pipelines(paths.pipelines),
        "catalog": PIPELINE_CATALOG,
        "analysis_types": ["germline", "somatic", "cfDNA"],
        "designs": ["single-sample", "cohort", "case-control", "trio", "tumor-normal"],
        "references": references,
        "tool_catalog": pipeline_tool_catalog(tools_config),
    }


@router.get("/{name}")
def pipeline_detail(name: str):
    try:
        result = load_pipeline(get_project_paths().pipelines, name)
    except PipelineError as exc:
        api_error(exc, 404 if "not found" in str(exc).lower() else 400)
    errors, warnings = validate_pipeline(result["config"])
    result.update({"errors": errors, "warnings": warnings})
    return result


@router.post("/new/draft")
def pipeline_new(payload: NewPipelineRequest):
    try:
        config = new_pipeline_config(payload.template)
    except PipelineError as exc:
        api_error(exc)
    return {"config": config}


@router.post("/validate/draft")
def pipeline_validate(payload: PipelineDraft):
    errors, warnings = validate_pipeline(payload.config)
    return {"valid": not errors, "errors": errors, "warnings": warnings}


@router.put("")
def pipeline_save(payload: PipelineSaveRequest):
    try:
        return save_pipeline(get_project_paths().pipelines, payload.name, payload.config, payload.overwrite)
    except PipelineError as exc:
        api_error(exc, 409 if "already exists" in str(exc).lower() else 400)


@router.delete("/{name}")
def pipeline_delete(name: str):
    try:
        filename = delete_pipeline(get_project_paths().pipelines, name)
    except PipelineError as exc:
        api_error(exc, 404 if "not found" in str(exc).lower() else 400)
    return {"deleted": filename}
