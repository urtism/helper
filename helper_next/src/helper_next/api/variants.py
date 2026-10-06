"""API for creating and inspecting run-local variant indexes."""
import logging
import sqlite3
import threading
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from helper_next.api.samplesheet import consume_picker_selection
from helper_next.core import analysis_history as history
from helper_next.core.variant_import import ArchivedRunImportError, create_archived_run
from helper_variants import clinvar
from helper_variants import gene_phenotype
from helper_variants import indexer as variant_indexer
from helper_variants import panelapp
from helper_variants import query as variant_query
from helper_variants import secondary_findings


router = APIRouter(prefix="/api/variants", tags=["variants"])
_active = set()
_active_lock = threading.Lock()


@router.get("/knowledge/panelapp/panels")
def panelapp_panels(q: str, limit: int = Query(20, ge=1, le=50)):
    try:
        return panelapp.search_panels(q, limit=limit)
    except panelapp.PanelAppError as exc:
        raise HTTPException(status_code=400 if "requires" in str(exc) else 502, detail=str(exc))


@router.get("/knowledge/panelapp/panels/{panel_id}")
def panelapp_panel(panel_id: int, version: str = ""):
    try:
        return panelapp.panel_detail(panel_id, version=version)
    except panelapp.PanelAppError as exc:
        raise HTTPException(status_code=400 if "invalid" in str(exc) else 502, detail=str(exc))


@router.get("/knowledge/gene-panels")
def gene_panel_catalog():
    sf_panels = secondary_findings.catalog()
    warning = ""
    try:
        remote = panelapp.list_panels()
        panelapp_panels = [{**item, "source": "panelapp"} for item in remote["panels"]]
        synced_at = remote.get("synced_at", "")
        cache_path = remote.get("cache_path", "")
    except panelapp.PanelAppError as exc:
        panelapp_panels = []
        synced_at = ""
        cache_path = str(panelapp.cache_path())
        warning = str(exc)
    return {
        "panels": sf_panels + panelapp_panels, "panelapp_count": len(panelapp_panels),
        "sf_count": len(sf_panels), "synced_at": synced_at, "cache_path": cache_path,
        "warning": warning,
    }


@router.post("/knowledge/gene-panels/sync")
def sync_gene_panel_catalog():
    try:
        return panelapp.sync_panels()
    except panelapp.PanelAppError as exc:
        raise HTTPException(status_code=429 if "429" in str(exc) else 502, detail=str(exc))


@router.get("/knowledge/gene-panels/{source}/{identifier}")
def gene_panel_detail(source: str, identifier: str):
    if source == "acmg":
        detail = secondary_findings.detail(identifier)
        if detail is None:
            raise HTTPException(status_code=404, detail="ACMG SF panel version not found")
        return detail
    if source == "panelapp":
        try:
            return {**panelapp.panel_detail(identifier), "source": "panelapp"}
        except panelapp.PanelAppError as exc:
            raise HTTPException(status_code=429 if "429" in str(exc) else 502, detail=str(exc))
    raise HTTPException(status_code=404, detail="gene panel source not found")


class ArchivedRunRequest(BaseModel):
    picker_id: str
    name: str
    reference_build: str
    panel: str = ""


def _record(identifier):
    record = history.get(identifier)
    if record is None:
        raise HTTPException(status_code=404, detail="Archived analysis not found")
    return record


def _database(record):
    database = variant_indexer.index_path(record["run_dir"])
    if not database.is_file():
        raise HTTPException(status_code=409, detail="Variant index is not available for this run")
    return database


def _entry(identifier):
    record = _record(identifier)
    return {
        "kind": "analysis", "record": record,
        "database": variant_indexer.index_path(record["run_dir"]),
        "run_id": record.get("run_id", ""), "identifier": identifier,
    }


def _entry_database(entry):
    if not entry["database"].is_file():
        raise HTTPException(status_code=409, detail="Variant index is not available for this run")
    return entry["database"]


def _physical_run_key(record):
    return str(Path(record["run_dir"]).expanduser().resolve())


def _public_run(record):
    pipeline = record.get("pipeline_config", {})
    request = record.get("request", {})
    pipeline_name = pipeline.get("id", "") if isinstance(pipeline, dict) else ""
    if not pipeline_name and request.get("pipeline_path"):
        pipeline_name = Path(request["pipeline_path"]).stem
    sample_names = {
        str(row.get("sample_name") or row.get("sample_id"))
        for row in record.get("samples", [])
        if isinstance(row, dict) and (row.get("sample_name") or row.get("sample_id"))
    }
    return {
        "history_id": record["id"],
        "run_id": record.get("run_id", ""),
        "status": record.get("status", ""),
        "created_at": record.get("started_at") or record.get("created_at", ""),
        "reference_build": variant_indexer.reference_build(record),
        "panel": request.get("gene_panel_design", ""),
        "pipeline": pipeline_name,
        "sample_count": len(sample_names),
    }


def _used_tools(record):
    pipeline = record.get("pipeline_config", {})
    tools_config = record.get("tools_config", {})
    if not isinstance(pipeline, dict):
        return []
    resolved = pipeline.get("resolved_tools", {})
    if not isinstance(resolved, dict) or not resolved:
        resolved = {
            step: pipeline.get(step, {})
            for step in pipeline.get("workflow", record.get("workflow", []))
            if isinstance(pipeline.get(step), dict)
        }
    found = {}

    def visit(value, step, operation=""):
        if isinstance(value, dict):
            tool = value.get("tool")
            if tool:
                configured = tools_config.get(tool, {}) if isinstance(tools_config, dict) else {}
                configured = configured if isinstance(configured, dict) else {}
                version = str(value.get("version") or configured.get("version") or configured.get("versione") or "")
                key = (str(tool), version)
                item = found.setdefault(key, {"name": str(tool), "version": version, "uses": []})
                use = {"step": str(step), "operation": str(operation or "tool")}
                if use not in item["uses"]:
                    item["uses"].append(use)
            for child_key, child in value.items():
                if child_key not in ("invocation", "args", "resolved_args"):
                    visit(child, step, operation or child_key)
        elif isinstance(value, list):
            for child in value:
                visit(child, step, operation)

    for step, config in resolved.items():
        visit(config, step)
    return sorted(found.values(), key=lambda item: item["name"].lower())


@router.get("/knowledge/gene-phenotypes/{gene}")
def gene_phenotypes(gene: str, background_tasks: BackgroundTasks,
                    hgnc_id: str = Query("", max_length=32)):
    gene = str(gene).strip()
    if not gene or len(gene) > 64:
        raise HTTPException(status_code=422, detail="Gene symbol must contain 1 to 64 characters")
    result = gene_phenotype.query_gene(gene, hgnc_id)
    cache = result["cache"]
    if cache["status"] != "ready" or cache.get("stale"):
        if gene_phenotype.begin_refresh():
            background_tasks.add_task(_refresh_gene_phenotype_cache)
        cache["refreshing"] = True
    else:
        constraint = result.get("gene_constraint", {})
        if constraint.get("status") == "missing" or constraint.get("stale"):
            if gene_phenotype.begin_constraint_refresh(gene):
                background_tasks.add_task(_refresh_gene_constraint, gene)
            constraint["refreshing"] = True
    return result


@router.post("/knowledge/gene-phenotypes/refresh", status_code=202)
def refresh_gene_phenotypes(background_tasks: BackgroundTasks):
    if not gene_phenotype.begin_refresh():
        return {"status": "refreshing", "cache": gene_phenotype.cache_status()}
    background_tasks.add_task(_refresh_gene_phenotype_cache)
    return {"status": "refreshing", "cache": gene_phenotype.cache_status()}


def _refresh_gene_phenotype_cache():
    try:
        gene_phenotype.refresh_cache()
    except Exception:
        logging.getLogger(__name__).exception("Cannot refresh the gene-phenotype cache")
    finally:
        gene_phenotype.finish_refresh()


def _refresh_gene_constraint(gene):
    try:
        gene_phenotype.refresh_gnomad_constraint(gene)
    except Exception:
        logging.getLogger(__name__).exception(
            "Cannot refresh gnomAD constraint data for %s", gene
        )
    finally:
        gene_phenotype.finish_constraint_refresh(gene)


@router.get("/runs")
def indexed_variant_runs():
    runs = []
    seen_run_dirs = set()
    for record in history.list_runs():
        physical_key = _physical_run_key(record)
        if physical_key in seen_run_dirs:
            continue
        seen_run_dirs.add(physical_key)
        database = variant_indexer.index_path(record["run_dir"])
        summary = None
        try:
            status = variant_indexer.index_status(record["run_dir"])
            if database.is_file():
                summary = variant_query.run_summary(database)
        except (OSError, sqlite3.Error, ValueError) as exc:
            status = {"status": "failed", "error": str(exc)}
        public_run = _public_run(record)
        runs.append({
            "history_id": record["id"], "run_id": record.get("run_id", ""),
            "created_at": public_run["created_at"], "run_status": record.get("status", ""),
            "index_status": status["status"], "summary": summary,
            "panel": public_run["panel"], "pipeline": public_run["pipeline"],
            "reference_build": public_run["reference_build"],
            "sample_count": public_run["sample_count"],
        })
    return {"runs": runs}


@router.post("/archived-runs", status_code=202)
def add_archived_variant_run(payload: ArchivedRunRequest, background_tasks: BackgroundTasks):
    files = consume_picker_selection(payload.picker_id)
    try:
        record = create_archived_run(
            files, payload.name, payload.reference_build, payload.panel
        )
    except (OSError, ArchivedRunImportError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    physical_key = _physical_run_key(record)
    with _active_lock:
        _active.add(physical_key)
    background_tasks.add_task(_index_in_background, record["id"], physical_key, record)
    return {
        "status": "indexing", "history_id": record["id"],
        "run_id": record["run_id"], "artifacts": len(record["variant_sources"]),
    }


@router.get("/runs/{identifier}/index-status")
def variant_index_status(identifier: str):
    record = _record(identifier)
    try:
        result = variant_indexer.index_status(record["run_dir"])
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    with _active_lock:
        if _physical_run_key(record) in _active:
            result["status"] = "indexing"
    result.update({"history_id": identifier, "run_id": record.get("run_id", "")})
    return result


@router.get("/runs/{identifier}/samples")
def variant_samples(identifier: str):
    entry = _entry(identifier)
    try:
        database = _entry_database(entry)
        return {
            "history_id": identifier, "run_id": entry["run_id"],
            "run": _public_run(entry["record"]),
            "summary": variant_query.run_summary(database),
            "samples": variant_query.list_samples(database),
        }
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/runs/{identifier}/tools")
def variant_run_tools(identifier: str):
    record = _record(identifier)
    return {
        "history_id": identifier, "run_id": record.get("run_id", ""),
        "pipeline": _public_run(record)["pipeline"], "tools": _used_tools(record),
    }


@router.get("/runs/{identifier}/samples/{sample_id}/variants")
def sample_variants(identifier: str, sample_id: int, cursor: str = "",
                    limit: int = Query(100, ge=1, le=500),
                    gene: str = "", genes: str = "", max_af: float | None = None,
                    population_frequency: str = "MAX_AF", include_missing_af: bool = True,
                    consequences: str = "",
                    clinical_significances: str = "", inheritance_candidates: str = "",
                    filter_mode: str = "all", filter_statuses: str = "", zygosities: str = "",
                    min_depth: float | None = None, min_vaf: float | None = None,
                    min_quality: float | None = None, possible_compound: bool = False):
    entry = _entry(identifier)
    try:
        result = variant_query.list_variants(
            _entry_database(entry), sample_id, cursor=cursor or None, limit=limit, gene=gene,
            genes=genes, max_af=max_af, population_frequency=population_frequency,
            include_missing_af=include_missing_af,
            consequences=consequences, clinical_significances=clinical_significances,
            inheritance_candidates=inheritance_candidates, filter_mode=filter_mode,
            filter_statuses=filter_statuses, zygosities=zygosities, min_depth=min_depth,
            min_vaf=min_vaf, min_quality=min_quality, possible_compound=possible_compound,
        )
    except variant_query.VariantQueryError as exc:
        raise HTTPException(status_code=404 if "sample not found" in str(exc) else 400, detail=str(exc))
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    result.update({"history_id": identifier, "sample_id": sample_id})
    return result


@router.get("/runs/{identifier}/samples/{sample_id}/filter-options")
def sample_variant_filter_options(identifier: str, sample_id: int):
    entry = _entry(identifier)
    try:
        return variant_query.variant_filter_options(_entry_database(entry), sample_id)
    except variant_query.VariantQueryError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/runs/{identifier}/samples/{sample_id}/variants/{variant_id}")
def sample_variant_detail(identifier: str, sample_id: int, variant_id: int):
    entry = _entry(identifier)
    try:
        detail = variant_query.variant_detail(_entry_database(entry), sample_id, variant_id)
    except variant_query.VariantQueryError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if detail is None:
        raise HTTPException(status_code=404, detail="Variant not found for this sample")
    evidence = detail.get("clinvar_evidence") or {}
    should_enrich = bool(
        evidence.get("classifications")
        or evidence.get("identifiers")
        or (detail.get("database_ids") or {}).get("dbsnp")
    ) and not evidence.get("source_url")
    if should_enrich:
        try:
            retrieved = clinvar.lookup_variant(
                detail["reference_build"], detail["chromosome"], detail["position"],
                detail["reference"], detail["alternate"],
            )
            detail["clinvar_evidence"] = clinvar.merge_evidence(evidence, retrieved)
        except clinvar.ClinVarError:
            detail["clinvar_evidence"] = dict(evidence, retrieval_status="unavailable")
    return detail


@router.get("/runs/{identifier}/samples/{sample_id}/variants/{variant_id}/carriers")
def sample_variant_carriers(identifier: str, sample_id: int, variant_id: int):
    entry = _entry(identifier)
    try:
        database = _entry_database(entry)
        detail = variant_query.variant_detail(database, sample_id, variant_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Variant not found for this sample")
        allele = (
            detail["reference_build"], detail["chromosome"], detail["position"],
            detail["reference"], detail["alternate"],
        )
        same_run = variant_query.variant_carriers(database, *allele)
    except HTTPException:
        raise
    except variant_query.VariantQueryError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    historical = []
    skipped = []
    current_key = _physical_run_key(entry["record"])
    seen_run_dirs = {current_key}
    for record in history.list_runs():
        physical_key = _physical_run_key(record)
        if physical_key in seen_run_dirs:
            continue
        seen_run_dirs.add(physical_key)
        other_database = variant_indexer.index_path(record["run_dir"])
        if not other_database.is_file():
            continue
        try:
            carriers = variant_query.variant_carriers(other_database, *allele)
        except (OSError, sqlite3.Error, ValueError) as exc:
            skipped.append({"history_id": record["id"], "error": str(exc)})
            continue
        for carrier in carriers:
            carrier.update({
                "history_id": record["id"], "run_id": record.get("run_id", ""),
                "created_at": record.get("started_at") or record.get("created_at", ""),
            })
            historical.append(carrier)
    historical.sort(key=lambda item: (item["created_at"], item["run_id"]), reverse=True)
    return {
        "history_id": identifier, "sample_id": sample_id, "variant_id": variant_id,
        "same_run": same_run, "historical": historical, "skipped": skipped,
    }


@router.post("/runs/{identifier}/index", status_code=202)
def start_variant_index(identifier: str, background_tasks: BackgroundTasks):
    record = _record(identifier)
    physical_key = _physical_run_key(record)
    try:
        artifacts = variant_indexer.discover_run_vcfs(record["run_dir"])
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not artifacts:
        raise HTTPException(status_code=409, detail="No VCF artifacts found in known result directories")
    with _active_lock:
        if physical_key in _active:
            raise HTTPException(status_code=409, detail="Variant indexing is already running")
        _active.add(physical_key)
    background_tasks.add_task(_index_in_background, identifier, physical_key, record)
    return {
        "status": "indexing", "history_id": identifier,
        "run_id": record.get("run_id", ""),
        "database": str(variant_indexer.index_path(record["run_dir"])),
        "artifacts": len(artifacts),
    }


def _index_in_background(identifier, physical_key, record):
    try:
        variant_indexer.index_run(record)
    except Exception:
        logging.getLogger(__name__).exception("Cannot index variants for analysis %s", identifier)
    finally:
        with _active_lock:
            _active.discard(physical_key)
