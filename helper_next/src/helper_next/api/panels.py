from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from helper_next.core.panels import (
    PanelDesignError,
    delete_panel_design,
    load_panel_config,
    save_panel_design,
    validate_panel_design,
)
from helper_next.core.project import get_project_paths


router = APIRouter(prefix="/api/panels", tags=["panels"])


class PanelSaveRequest(BaseModel):
    name: str
    design: Dict[str, Any]
    original_name: Optional[str] = None


def api_error(exc):
    message = str(exc)
    raise HTTPException(status_code=404 if "not found" in message.lower() else 400, detail=message)


@router.get("")
def panels_index():
    try:
        data = load_panel_config(get_project_paths().configs)
    except PanelDesignError as exc:
        api_error(exc)
    panels = []
    for name in data["list"]:
        if not isinstance(name, str):
            continue
        design = data.get(name, {})
        if not isinstance(design, dict):
            design = {}
        errors = validate_panel_design(
            {"assets": {"target_bed": str(design.get("target_bed") or "").strip()}}
        )
        panels.append({"name": name, "design": design, "errors": errors})
    return {"panels": panels}


@router.put("")
def panel_save(payload: PanelSaveRequest):
    try:
        return save_panel_design(
            get_project_paths().configs,
            payload.name,
            payload.design,
            payload.original_name,
        )
    except PanelDesignError as exc:
        api_error(exc)


@router.delete("/{name}")
def panel_delete(name: str):
    try:
        return delete_panel_design(get_project_paths().configs, name)
    except PanelDesignError as exc:
        api_error(exc)
