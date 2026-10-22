"""Local ACMG workspaces over the independent, versioned engine REST API."""
import csv
import io
import json

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from helper_next.api.variants import _entry, _entry_database
from helper_next.core import acmg_store as store
from helper_next.core import acmg_workbench as workbench
from helper_next.core import acmg_context
from helper_next.core.acmg_client import ACMGClient, EngineError, configuration
from helper_variants import query


router = APIRouter(prefix="/api/acmg", tags=["acmg-research"])


class PrepareRequest(BaseModel):
    source_id: str
    sample_id: int
    variant_id: int
    transcript: str
    assembly: str
    context: dict = Field(default_factory=dict)
    annotation_id: int | None = None
    context_id: str = ""
    context_fingerprint: str = ""
    inheritance_mode: str = ""


class ExecuteRequest(BaseModel):
    selections: list
    corrections: list = Field(default_factory=list)
    parent_id: str = ""


class CompareRequest(BaseModel):
    selections: list
    corrections: list = Field(default_factory=list)


class ReviewRequest(BaseModel):
    criterion: str
    decision: str
    comments: str = Field(..., min_length=1, max_length=20000)
    discrepancy: str = "OTHER"
    reviewer_id: str = Field("", max_length=200)
    evidence: list = Field(default_factory=list)


def entry(identifier, kind=None):
    value = store.get(identifier)
    if value is None or (kind and value["kind"] != kind):
        raise HTTPException(404, "ACMG workspace/result not found")
    return value


def client_call(fn):
    try:
        return fn()
    except EngineError as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": str(exc), "engine_error": exc.details})
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise HTTPException(422, str(exc))


@router.get("/discovery")
def discovery():
    return client_call(lambda: ACMGClient().discover())


@router.post("/workspaces", status_code=201)
def prepare(payload: PrepareRequest):
    source = _entry(payload.source_id)
    detail = query.variant_detail(_entry_database(source), payload.sample_id, payload.variant_id)
    if detail is None:
        raise HTTPException(404, "Variant not found for selected sample")
    locator = {"source_id": payload.source_id, "source_type": source["record"].get("source_type", "RUN_ASSOCIATED"),
               "sample_id": payload.sample_id, "variant_id": payload.variant_id}
    def create():
        context, resolution = payload.context, None
        if payload.context_id or not context:
            if payload.context:
                raise ValueError("Use either a HELPER context selection or an explicit manual context")
            context, resolution = acmg_context.select(acmg_context.build(detail), payload.annotation_id, payload.transcript,
                                                       payload.context_id, payload.context_fingerprint, payload.inheritance_mode)
        return store.save("workspace", workbench.prepare(detail, locator, context, payload.transcript, payload.assembly,
                                                         source["record"], payload.annotation_id, resolution))
    return client_call(create)


@router.get("/contexts")
def variant_contexts(source_id: str, sample_id: int, variant_id: int):
    source = _entry(source_id)
    detail = query.variant_detail(_entry_database(source), sample_id, variant_id)
    if detail is None:
        raise HTTPException(404, "Variant not found for selected sample")
    return client_call(lambda: acmg_context.build(detail))


@router.get("/workspaces")
def list_workspaces(source_id: str, sample_id: int, variant_id: int):
    return {"workspaces": [{"id": e["id"], "created_at": e["created_at"], "context": e["document"]["normalized_evidence"]["snapshot"]["context"]}
                           for e in store.workspaces(source_id, sample_id, variant_id)]}


@router.get("/workspaces/{identifier}")
def workspace(identifier: str):
    value = entry(identifier, "workspace")
    return {"workspace": value, "history": store.history(identifier)}


@router.get("/workspaces/{identifier}/profiles")
def profiles(identifier: str):
    value = entry(identifier, "workspace")
    return client_call(lambda: {"profiles": ACMGClient().profiles(value["document"]["normalized_evidence"]["snapshot"]["context"])})


def execution_inputs(identifier, selections, corrections):
    value = entry(identifier, "workspace")
    engine = ACMGClient()
    discovered = engine.discover()
    cap = discovered["capabilities"]
    if not cap.get("research_execution_enabled"):
        raise EngineError("RESEARCH_DISABLED", "Enable research interpretation explicitly in ACMG Engine", 409)
    packet = workbench.corrected_packet(value["document"]["normalized_evidence"], corrections)
    normalization = packet["snapshot"]["variant"]["normalization"]
    if packet["snapshot"]["evidence"] and (normalization["status"] != "NORMALIZED" or normalization["reference_validated"] is not True):
        raise EngineError("PACKET_NORMALIZATION_REQUIRED", "Configure a matching local reference FASTA and prepare the workspace again before executing structured evidence", 409)
    available = engine.profiles(packet["snapshot"]["context"])
    configs = [configuration(available, selection) for selection in selections]
    executable = {s["strategy"] for s in cap["strategies"] if s["status"] == "PARTIAL_RESEARCH"}
    if any(c["strategy"] not in executable for c in configs):
        raise ValueError("Strategy is not executable on this engine")
    return engine, packet, configs


@router.post("/workspaces/{identifier}/interpret", status_code=201)
def interpret(identifier: str, payload: ExecuteRequest):
    def execute():
        if payload.parent_id and entry(payload.parent_id, "interpretation")["workspace_id"] != identifier:
            raise ValueError("Rerun parent belongs to another workspace")
        engine, packet, configs = execution_inputs(identifier, [payload.selections], payload.corrections)
        result = engine.call("/v1/evidence-packets/interpret", {"packet": packet, "configuration": configs[0]})
        if result.get("schema_version") != "evidence-packet-result-v1" or "criterion_results" not in result.get("result", {}):
            raise EngineError("INVALID_RESULT_CONTRACT", "Missing criterion-level interpretation result")
        return store.save("interpretation", {"packet": packet, "configuration": configs[0], "engine_result": result,
                          "context_resolution": entry(identifier, "workspace")["document"].get("context_resolution"),
                          "corrections": payload.corrections, "parent_id": payload.parent_id,
                          "rows": workbench.criterion_rows(result["result"])}, identifier)
    return client_call(execute)


@router.post("/workspaces/{identifier}/compare", status_code=201)
def compare(identifier: str, payload: CompareRequest):
    def execute():
        engine, packet, configs = execution_inputs(identifier, payload.selections, payload.corrections)
        if len(configs) < 2:
            raise ValueError("Select at least two supported configurations")
        result = engine.call("/v1/interpretations/compare", {"schema_version": "1.0", "snapshot": packet["snapshot"], "configurations": configs})
        return store.save("comparison", {"packet": packet, "engine_result": result, "configurations": configs,
                          "context_resolution": entry(identifier, "workspace")["document"].get("context_resolution")}, identifier)
    return client_call(execute)


@router.get("/results/{identifier}")
def result(identifier: str):
    return entry(identifier)


@router.post("/results/{identifier}/reviews", status_code=201)
def review(identifier: str, payload: ReviewRequest):
    value = entry(identifier, "interpretation")
    if payload.criterion not in workbench.CRITERIA or payload.decision not in ("CONFIRM", "CONTEST", "REQUEST_REVIEW") or payload.discrepancy not in workbench.DISCREPANCIES:
        raise HTTPException(422, "Invalid criterion, review action or discrepancy category")
    criterion = next((c for c in value["document"]["engine_result"]["result"]["criterion_results"] if c["code"] == payload.criterion), None)
    if criterion is None:
        raise HTTPException(422, "Criterion not recorded by engine")
    return store.save("review", dict(payload.dict(), interpretation_id=identifier,
                     result_fingerprint=value["fingerprint"], criterion_fingerprint=workbench.digest(criterion),
                     engine_interpretation_id=value["document"]["engine_result"]["result"]["result_id"],
                     engine_status=criterion["status"], engine_strength=criterion.get("strength")), value["workspace_id"])


@router.get("/results/{identifier}/diff/{previous}")
def rerun_diff(identifier: str, previous: str):
    after, before = entry(identifier, "interpretation"), entry(previous, "interpretation")
    if after["workspace_id"] != before["workspace_id"]:
        raise HTTPException(422, "Results belong to different variants/workspaces")
    a, b = before["document"], after["document"]
    return {"before_id": previous, "after_id": identifier,
            "criteria": workbench.compare_results(a["engine_result"]["result"], b["engine_result"]["result"]),
            "before_packet": a["packet"], "after_packet": b["packet"],
            "before_classification": a["engine_result"]["result"]["classification"],
            "after_classification": b["engine_result"]["result"]["classification"]}


def readable_report(value, reviews):
    document = value["document"]
    packet = document.get("packet", {})
    snapshot = packet.get("snapshot", {})
    lines = ["# HELPER ACMG — RESEARCH ONLY / EXPERIMENTAL", "",
             "No clinical validation or scientific profile approval is claimed.", "",
             "Interpretation version: " + value["id"], "Created: " + value["created_at"],
             "Result fingerprint: " + value["fingerprint"]["value"], "",
             "## Variant and scientific context", "",
             json.dumps(snapshot.get("variant", {}).get("identity", {}), ensure_ascii=False),
             json.dumps(snapshot.get("context", {}), ensure_ascii=False), ""]
    if document.get("context_resolution"):
        lines.extend(["## Structured context supplied by HELPER", "", "```json",
                      json.dumps(document["context_resolution"], ensure_ascii=False, indent=2), "```", ""])
    response = document.get("engine_result", {})
    result = response.get("result", {})
    classification = result.get("classification", {})
    lines.extend(["## Configuration and engine classification", "",
                  json.dumps(document.get("configuration", document.get("configurations", [])), ensure_ascii=False), "",
                  "Engine classification status: " + str(classification.get("status", "NOT_RECORDED")),
                  "Final category: " + str(classification.get("category") if classification.get("status") == "CLASSIFIED" else "NOT_CLASSIFIED"),
                  "Classification method: " + str(classification.get("method", "NOT_RECORDED")),
                  "Completeness: " + str(response.get("evidence_completeness", "NOT_RECORDED")), "",
                  "## Criterion evaluation", "",
                  "| Criterion | Engine status | Display status | Candidate strength | Effective strength |",
                  "| --- | --- | --- | --- | --- |"])
    for row in document.get("rows", []):
        lines.append("| {} | {} | {} | {} | {} |".format(row["code"], row["engine_status"], row["display_status"],
                     (row.get("candidate_strength") or {}).get("level", "NOT_RECORDED"),
                     (row.get("effective_strength") or {}).get("level", "NOT_RECORDED")))
    for row in document.get("rows", []):
        raw = row.get("raw") or {}
        lines.extend(["", "### " + row["code"], "", raw.get("explanation", "NOT_RECORDED"), "",
                      "Reason: " + str(raw.get("reason_code", "NOT_RECORDED")),
                      "Candidate / effective activation: {} / {}".format(row.get("candidate_active"), row.get("effective_active")),
                      "", "Scientific rules, numerical values, operators, thresholds, calculations, decision branches and provenance:", "", "```json",
                      json.dumps({k: v for k, v in raw.items() if k in ("rules", "provenance", "population_upper_ci", "excluded_evidence", "required_manual_actions", "warnings") or k.endswith("_audit")}, ensure_ascii=False, indent=2), "```"])
    lines.extend(["", "## Missing evidence and warnings", "", "```json",
                  json.dumps({"missing_evidence": packet.get("missing_evidence"), "warnings": result.get("warnings"), "limitations": response.get("limitations"),
                              "comparison": response if value["kind"] == "comparison" else None}, ensure_ascii=False, indent=2), "```",
                  "", "## Independent human validation", "", "```json", json.dumps(reviews, ensure_ascii=False, indent=2), "```",
                  "", "NOT_RECORDED indicates an absent engine audit field; missing evidence is not negative evidence."])
    return "\n".join(lines) + "\n"


@router.get("/results/{identifier}/export/{format}")
def export(identifier: str, format: str):
    value = entry(identifier)
    document = value["document"]
    reviews = [e for e in store.history(value["workspace_id"]) if e["kind"] == "review" and e["document"].get("interpretation_id") == identifier]
    media, suffix = "application/json", "json"
    if format == "engine":
        content = document.get("engine_result")
    elif format == "evidence":
        content = document.get("packet")
    elif format == "reviews":
        content = reviews
    elif format == "comparison":
        if value["kind"] != "comparison":
            raise HTTPException(409, "This entry is not a profile comparison")
        content = {"entry": value, "reviews": reviews}
    elif format == "troubleshooting":
        content = {"entry": value, "reviews": reviews}
    elif format == "rerun":
        if not document.get("parent_id"):
            raise HTTPException(409, "No previous result selected for this rerun")
        content = rerun_diff(identifier, document["parent_id"])
    elif format == "table":
        output = io.StringIO()
        fields = ["code", "engine_status", "display_status", "candidate_active", "effective_active", "candidate_strength", "effective_strength", "explanation", "scientific_audit_json"]
        writer = csv.DictWriter(output, fields, extrasaction="ignore")
        writer.writeheader()
        for row in document.get("rows", []):
            exported = dict(row, scientific_audit_json=json.dumps(row.get("raw"), ensure_ascii=False))
            writer.writerow({k: ("'" + str(v) if isinstance(v, str) and v.startswith(("=", "+", "-", "@")) else v) for k, v in exported.items()})
        content, media, suffix = output.getvalue(), "text/csv", "csv"
    elif format == "report":
        content = readable_report(value, reviews)
        media, suffix = "text/markdown", "md"
    else:
        raise HTTPException(404, "Unknown export format")
    if media == "application/json":
        content = json.dumps(content, ensure_ascii=False, indent=2, allow_nan=False)
    return Response(content, media_type=media, headers={"Content-Disposition": 'attachment; filename="acmg-{}.{}"'.format(format, suffix)})
