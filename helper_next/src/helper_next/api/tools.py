from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from helper_next.core.project import get_project_paths
from helper_next.core.tools import ToolsError, load_tools, save_tools, test_resource, validate_tools


router = APIRouter(prefix="/api/tools", tags=["tools"])


class ToolsDraft(BaseModel):
    config: Dict[str, Any]


class ToolsSaveRequest(ToolsDraft):
    filename: str = "tools_cfg/tools.cfg"
    revision: Optional[str] = None


class ToolTestRequest(BaseModel):
    resource_type: str
    name: str
    config: Dict[str, Any]


def api_error(exc, status_code=400):
    raise HTTPException(status_code=status_code, detail=str(exc))


@router.get("")
def tools_detail(filename="tools_cfg/tools.cfg"):
    paths = get_project_paths()
    try:
        return load_tools(paths.configs, paths.pipelines, filename)
    except ToolsError as exc:
        api_error(exc, 404 if "not found" in str(exc).lower() else 400)


@router.post("/validate/draft")
def tools_validate(payload: ToolsDraft):
    paths = get_project_paths()
    errors, warnings = validate_tools(payload.config, paths.pipelines)
    return {"valid": not errors, "errors": errors, "warnings": warnings}


@router.put("")
def tools_save(payload: ToolsSaveRequest):
    paths = get_project_paths()
    try:
        return save_tools(
            paths.configs,
            paths.pipelines,
            payload.filename,
            payload.config,
            payload.revision,
        )
    except ToolsError as exc:
        api_error(exc, 409 if "changed on disk" in str(exc).lower() else 400)


@router.post("/test")
def tools_test(payload: ToolTestRequest):
    try:
        return test_resource(payload.resource_type, payload.name, payload.config)
    except ToolsError as exc:
        api_error(exc)
