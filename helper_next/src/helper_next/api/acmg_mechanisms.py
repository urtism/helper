"""Additive public mechanism-cache consultation; no review/approval endpoint."""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, StrictStr

from helper_next.core.acmg_mechanism_models import CachePolicy
from helper_next.core.acmg_mechanism_store import MechanismStore, compare_snapshots
from helper_next.core.acmg_mechanisms import MechanismEvidenceCache


router = APIRouter(prefix="/api/acmg/mechanisms", tags=["acmg-mechanisms"])


@router.get("/ontology")
def ontology(identifier: Optional[str] = None):
    from helper_next.core.acmg_ontology import OntologyMappingRegistry
    registry = OntologyMappingRegistry()
    return execute(lambda: registry.lookup(identifier) if identifier else registry.manifest())


class MechanismRequest(BaseModel):
    gene: StrictStr
    disease: StrictStr
    allelic_requirement: Optional[StrictStr] = None
    cache_policy: CachePolicy = "REFRESH_IF_STALE"
    snapshot_id: Optional[StrictStr] = None
    symbol: Optional[StrictStr] = None
    disease_name: Optional[StrictStr] = None

    class Config:
        extra = "forbid"


def execute(action):
    try:
        return action()
    except KeyError:
        raise HTTPException(404, {"code": "MECHANISM_RECORD_NOT_FOUND"}) from None
    except ValueError as exc:
        raise HTTPException(422, {"code": "INVALID_MECHANISM_REQUEST", "message": str(exc)}) from None
    except TimeoutError:
        raise HTTPException(503, {"code": "MECHANISM_REFRESH_BUSY"}) from None


@router.post("/resolve")
def resolve(request: MechanismRequest):
    return execute(lambda: MechanismEvidenceCache().resolve_gene_disease_mechanism(**request.dict()).dict())


@router.get("/snapshots/{snapshot_id}")
def snapshot(snapshot_id: str):
    return execute(lambda: MechanismStore().snapshot(snapshot_id).dict())


@router.get("/source-records/{record_id}")
def source_record(record_id: str):
    return execute(lambda: MechanismStore().source_record(record_id))


class ComparisonRequest(BaseModel):
    previous_snapshot: StrictStr
    current_snapshot: StrictStr


@router.post("/snapshots/compare")
def compare(request: ComparisonRequest):
    def perform():
        store = MechanismStore()
        before, after = store.snapshot(request.previous_snapshot), store.snapshot(request.current_snapshot)
        if (before.identity.gene_id, before.identity.disease_id, before.identity.allelic_requirement) != (
                after.identity.gene_id, after.identity.disease_id, after.identity.allelic_requirement):
            raise ValueError("Snapshots belong to different gene-disease/allelic-requirement associations")
        return compare_snapshots(before, after)
    return execute(perform)
