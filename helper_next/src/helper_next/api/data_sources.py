"""Administrative local-only view; the application has no user/role system."""
from ipaddress import ip_address

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from helper_next.core import data_source_checks, clinvar_update
from helper_variants import clinvar_local, source_registry


async def local_administration(request: Request):
    def loopback(value):
        try:
            return ip_address(value).is_loopback
        except ValueError:
            return False

    host = request.url.hostname or ""
    peer = request.client.host if request.client else ""
    origin = request.headers.get("origin")
    if (not loopback(peer) or not (host == "localhost" or loopback(host))
            or request.headers.get("sec-fetch-site") == "cross-site"
            or (origin and origin != request.url.scheme + "://" + request.url.netloc)):
        raise HTTPException(status_code=403, detail="Data Sources requires same-origin local administration.")


router = APIRouter(prefix="/api/data-sources", tags=["data-sources"], dependencies=[Depends(local_administration)])


def _attach_check(source):
    if source["source_id"] == "clinvar":
        operation = clinvar_update.operation_status()
        check = data_source_checks.check_status(snapshot_id=source["snapshot_id"])
        postpone = clinvar_update.postpone_status(check)
        _, path, _ = data_source_checks._paths()
        try:
            last_update = data_source_checks._load(path).get("last_successful_update")
        except (OSError, ValueError):
            last_update = None
        installed_at = (last_update.get("completed_at") if isinstance(last_update, dict)
                        and last_update.get("snapshot_id") == source["snapshot_id"] else None)
        ready = (source["status"] == "installed"
                 and check.get("matches_current") and check.get("update_available") is True
                 and check.get("status") == "complete" and operation.get("status") != "running")
        source.update(last_checked=check.get("last_checked"), update_available=check.get("update_available"),
                      check=check, update=operation, postpone=postpone,
                      can_update=bool(ready and source["details"].get("managed") and not source["details"].get("builder_busy")),
                      can_postpone=bool(ready),
                      last_successful_update=last_update, installed_at=installed_at,
                      notification=check.get("update_available") is True and not postpone["silenced"])
    return source


def _source(source_id):
    rows = source_registry.administrative_catalog(source_id)["sources"]
    if not rows:
        raise HTTPException(status_code=404, detail="Unknown data source")
    return _attach_check(rows[0])


@router.get("")
def sources_index():
    result = source_registry.administrative_catalog()
    result["sources"] = [_attach_check(source) for source in result["sources"]]
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@router.get("/{source_id}")
def source_detail(source_id: str):
    return JSONResponse(_source(source_id), headers={"Cache-Control": "no-store"})


@router.get("/{source_id}/check")
def source_check_status(source_id: str):
    source = _source(source_id)
    if source_id != "clinvar":
        raise HTTPException(status_code=400, detail="Update checking is not supported for this source")
    return JSONResponse(source["check"], headers={"Cache-Control": "no-store"})


@router.post("/{source_id}/check", status_code=202)
def source_check(source_id: str):
    source = _source(source_id)
    if not source["update_supported"]:
        raise HTTPException(status_code=400, detail="Update checking is not available for this source")
    try:
        result = data_source_checks.start_clinvar_check()
    except (OSError, ValueError, clinvar_local.ClinVarLocalError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse(result, status_code=202, headers={"Cache-Control": "no-store"})


class ClinVarSelection(BaseModel):
    snapshot_id: str
    update_id: str
    confirmed: bool = False


@router.post("/clinvar/update", status_code=202)
def clinvar_update_start(payload: ClinVarSelection):
    try:
        result = clinvar_update.start_update(payload.snapshot_id, payload.update_id, confirmed=payload.confirmed)
    except clinvar_update.UpdateConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (OSError, ValueError, clinvar_local.ClinVarLocalError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse(result, status_code=202, headers={"Cache-Control": "no-store"})


@router.post("/clinvar/postpone")
def clinvar_postpone(payload: ClinVarSelection):
    try:
        result = clinvar_update.postpone(payload.snapshot_id, payload.update_id)
    except clinvar_update.UpdateConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (OSError, ValueError, clinvar_local.ClinVarLocalError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@router.get("/clinvar/update/status")
def clinvar_operation_status():
    return JSONResponse(clinvar_update.operation_status(), headers={"Cache-Control": "no-store"})
