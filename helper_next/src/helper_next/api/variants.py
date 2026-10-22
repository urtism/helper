"""API for creating and inspecting run-local variant indexes."""
import logging
import math
import re
import sqlite3
import threading
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from helper_next.api.samplesheet import consume_picker_selection
from helper_next.core import analysis_history as history
from helper_next.core import external_vcf
from helper_next.core import acmg_context
from helper_next.core.variant_import import ArchivedRunImportError, create_archived_run
from helper_variants import clinvar
from helper_variants import gene_phenotype
from helper_variants import gnomad_frequency
from helper_variants import indexer as variant_indexer
from helper_variants import igv
from helper_variants import liftover
from helper_variants import panelapp
from helper_variants import query as variant_query
from helper_variants import secondary_findings
from helper_variants import source_registry


router = APIRouter(prefix="/api/variants", tags=["variants"])
_active = set()
_active_lock = threading.Lock()


@router.get("/knowledge/sources")
def knowledge_sources():
    return source_registry.catalog()


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
    try:
        record = external_vcf.get(identifier) if identifier.startswith("external-") else history.get(identifier)
    except ValueError:
        raise HTTPException(status_code=404, detail="External VCF source not found")
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
        "kind": "external" if record.get("source_type") == "EXTERNAL_UPLOAD" else "analysis", "record": record,
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
    return {"runs": runs + external_vcf.public_sources()}


@router.post("/external-sources", status_code=201)
async def upload_external_vcf(request: Request, filename: str = Header(..., alias="X-VCF-Filename"), assembly: str = Query(...)):
    """Raw streamed file body avoids multipart buffering and synthetic run history."""
    identifier = None
    try:
        filename = unquote(filename, errors="strict")
        if assembly not in ("GRCh37", "GRCh38"):
            raise ValueError("Explicit GRCh37 or GRCh38 confirmation is required")
        identifier, path = external_vcf.allocate(filename)
        size = 0
        with path.open("xb") as handle:
            async for chunk in request.stream():
                size += len(chunk)
                if size > external_vcf.MAX_UPLOAD:
                    raise HTTPException(status_code=413, detail="VCF upload size limit exceeded")
                handle.write(chunk)
        record = await run_in_threadpool(external_vcf.finish, identifier, path, filename, assembly)
        return {"source_id": identifier, "source_type": "EXTERNAL_UPLOAD", "sha256": record["sha256"]}
    except HTTPException:
        if identifier:
            external_vcf.discard(identifier)
        raise
    except (OSError, ValueError, EOFError) as exc:
        if identifier:
            external_vcf.discard(identifier)
        raise HTTPException(status_code=422, detail=str(exc))
    except BaseException:
        if identifier:
            external_vcf.discard(identifier)
        raise


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


@router.get("/runs/{identifier}/samples/{sample_id}/igv-manifest")
def sample_igv_manifest(identifier: str, sample_id: int):
    entry = _entry(identifier)
    sample = _igv_sample(entry, sample_id)
    try:
        payload, _ = igv.manifest(entry["record"], sample)
    except igv.IgvResourceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    resource_base = (
        f"{router.prefix}/runs/{identifier}/samples/{sample_id}/igv-files"
    )
    reference = dict(payload["reference"])
    if reference.get("local"):
        reference["fasta_url"] = f"{resource_base}/reference"
        reference["index_url"] = f"{resource_base}/reference-index"
        if reference.get("compressed_index_resource"):
            reference["compressed_index_url"] = f"{resource_base}/reference-compressed-index"
    tracks = []
    for track in payload["tracks"]:
        public_track = dict(track)
        if track.get("resource"):
            public_track["url"] = f"{resource_base}/{track['resource']}"
        elif track.get("url_template") == "gnomad-region":
            public_track["url"] = (
                f"{router.prefix}/runs/{identifier}/samples/{sample_id}/igv-gnomad"
                "?chr=$CHR&start=$START&end=$END"
            )
        if track.get("index_resource"):
            public_track["index_url"] = f"{resource_base}/{track['index_resource']}"
        tracks.append(public_track)
    return {**payload, "reference": reference, "tracks": tracks}


@router.api_route(
    "/runs/{identifier}/samples/{sample_id}/igv-files/{kind}", methods=["GET", "HEAD"]
)
def sample_igv_file(identifier: str, sample_id: int, kind: str, request: Request):
    entry = _entry(identifier)
    sample = _igv_sample(entry, sample_id)
    try:
        path = igv.resource(entry["record"], sample, kind)
    except igv.IgvResourceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _range_response(path, request, kind)


@router.get("/runs/{identifier}/samples/{sample_id}/igv-gnomad")
def sample_igv_gnomad_region(
    identifier: str, sample_id: int, chr: str,
    start: float = Query(ge=0), end: float = Query(ge=1),
):
    entry = _entry(identifier)
    sample = _igv_sample(entry, sample_id)
    if not math.isfinite(start) or not math.isfinite(end):
        raise HTTPException(status_code=422, detail="gnomAD track coordinates must be finite")
    # IGV expands cached windows with fractional coordinates. Convert its zero-based
    # interval outward so the requested bases remain covered by the integer API.
    region_start = max(0, math.floor(start))
    region_end = math.ceil(end)
    if region_end <= region_start or region_end - region_start > 100_000:
        raise HTTPException(status_code=422, detail="gnomAD track windows must span 1-100000 bases")
    try:
        payload, _ = igv.manifest(entry["record"], sample)
        return gnomad_frequency.region_variants(
            payload["reference_build"], chr, region_start + 1, region_end,
        )
    except (gnomad_frequency.GnomadFrequencyError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _igv_sample(entry, sample_id):
    try:
        samples = variant_query.list_samples(_entry_database(entry))
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    sample = next((item for item in samples if item["sample_id"] == int(sample_id)), None)
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    return sample


def _range_response(path, request, kind):
    size = path.stat().st_size
    range_header = request.headers.get("range", "")
    lowered = path.name.lower()
    if lowered.endswith((".vcf", ".bed", ".fai")):
        content_type = "text/plain; charset=utf-8"
    elif lowered.endswith(".gz"):
        content_type = "application/gzip"
    else:
        content_type = "application/octet-stream"
    headers = {
        "Accept-Ranges": "bytes", "Content-Length": str(size),
        "ETag": f'"{path.stat().st_mtime_ns:x}-{size:x}"',
        "Cache-Control": "private, max-age=0, must-revalidate",
    }
    if request.method == "HEAD":
        return Response(status_code=200, media_type=content_type, headers=headers)
    if not range_header:
        return StreamingResponse(
            _file_chunks(path, 0, max(0, size - 1)), media_type=content_type, headers=headers
        )
    try:
        start, end = _parse_byte_range(range_header, size)
    except ValueError as exc:
        raise HTTPException(
            status_code=416, detail=str(exc), headers={"Content-Range": f"bytes */{size}"}
        ) from exc
    headers.update({
        "Content-Range": f"bytes {start}-{end}/{size}",
        "Content-Length": str(end - start + 1),
    })
    return StreamingResponse(
        _file_chunks(path, start, end), status_code=206, media_type=content_type, headers=headers
    )


def _parse_byte_range(header, size):
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", str(header).strip())
    if not match or size <= 0:
        raise ValueError("Invalid byte range")
    first, last = match.groups()
    if not first and not last:
        raise ValueError("Invalid byte range")
    if first:
        start = int(first)
        end = int(last) if last else size - 1
    else:
        length = int(last)
        if length <= 0:
            raise ValueError("Invalid byte range")
        start, end = max(0, size - length), size - 1
    if start >= size or start < 0 or end < start:
        raise ValueError("Requested byte range is outside the resource")
    return start, min(end, size - 1)


def _file_chunks(path, start, end, chunk_size=1024 * 1024):
    remaining = end - start + 1
    with path.open("rb") as handle:
        handle.seek(start)
        while remaining > 0:
            chunk = handle.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@router.get("/runs/{identifier}/samples/{sample_id}/variants")
def sample_variants(identifier: str, sample_id: int, cursor: str = "",
                    limit: int = Query(100, ge=1, le=500),
                    gene: str = "", variant_id: int | None = None,
                    genes: str = "", max_af: float | None = None,
                    population_frequency: str = "MAX_AF", include_missing_af: bool = True,
                    consequences: str = "",
                    clinical_significances: str = "", inheritance_candidates: str = "",
                    family_evidence: str = "", family_pattern: str = "",
                    priority_classes: str = "", min_priority: float | None = None,
                    max_priority: float | None = None,
                    filter_mode: str = "all", filter_statuses: str = "", zygosities: str = "",
                    min_depth: float | None = None, min_vaf: float | None = None,
                    min_quality: float | None = None, possible_compound: bool = False,
                    sort_by: str = "priority", sort_direction: str = ""):
    entry = _entry(identifier)
    try:
        result = variant_query.list_variants(
            _entry_database(entry), sample_id, cursor=cursor or None, limit=limit, gene=gene,
            variant_id=variant_id,
            genes=genes, max_af=max_af, population_frequency=population_frequency,
            include_missing_af=include_missing_af,
            consequences=consequences, clinical_significances=clinical_significances,
            inheritance_candidates=inheritance_candidates, family_evidence=family_evidence,
            family_pattern=family_pattern,
            priority_classes=priority_classes, min_priority=min_priority,
            max_priority=max_priority,
            filter_mode=filter_mode,
            filter_statuses=filter_statuses, zygosities=zygosities, min_depth=min_depth,
            min_vaf=min_vaf, min_quality=min_quality, possible_compound=possible_compound,
            sort_by=sort_by, sort_direction=sort_direction,
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
    _include_clinvar_identifiers(detail)
    detail["interpretation_context"] = acmg_context.build(detail)
    return detail


def _include_clinvar_identifiers(detail):
    """Expose exact ClinVar Variation/VCV identifiers in the common identifier block."""
    database_ids = detail.setdefault("database_ids", {})
    existing = list(database_ids.get("clinvar") or [])
    evidence = detail.get("clinvar_evidence") or {}
    candidates = existing + list(evidence.get("identifiers") or [])
    seen = set()
    identifiers = []
    for candidate in candidates:
        identifier = str(candidate or "").strip()
        folded = identifier.casefold()
        if not identifier or folded in seen:
            continue
        seen.add(folded)
        identifiers.append(identifier)
    database_ids["clinvar"] = identifiers


@router.get("/runs/{identifier}/samples/{sample_id}/variants/{variant_id}/liftover")
def sample_variant_liftover(identifier: str, sample_id: int, variant_id: int):
    entry = _entry(identifier)
    try:
        detail = variant_query.variant_detail(_entry_database(entry), sample_id, variant_id)
    except variant_query.VariantQueryError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if detail is None:
        raise HTTPException(status_code=404, detail="Variant not found for this sample")
    return liftover.project_variant(
        detail["reference_build"], detail["chromosome"], detail["position"],
        detail["reference"], detail["alternate"],
    )


@router.get("/runs/{identifier}/samples/{sample_id}/variants/{variant_id}/gnomad-frequency")
def sample_variant_gnomad_frequency(identifier: str, sample_id: int, variant_id: int):
    """Retrieve assembly-matched, allele-specific gnomAD genome frequency evidence."""
    entry = _entry(identifier)
    try:
        detail = variant_query.variant_detail(_entry_database(entry), sample_id, variant_id)
    except variant_query.VariantQueryError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if detail is None:
        raise HTTPException(status_code=404, detail="Variant not found for this sample")
    return gnomad_frequency.lookup_variant(
        detail["reference_build"], detail["chromosome"], detail["position"],
        detail["reference"], detail["alternate"],
    )


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
