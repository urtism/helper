"""Additive criteria-only workspace API over the independent Task 22 service."""
import csv
import io
import json
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from helper_next.api.acmg import client_call, entry
from helper_next.core import acmg_store as store
from helper_next.core.acmg_client import digest, EngineError
from helper_next.core.acmg_task22 import Task22Client, provider_contract
from helper_next.core.analysis_history import now


router = APIRouter(prefix="/api/acmg", tags=["acmg-task22"])


class EvaluationRequest(BaseModel):
    protocol: dict
    corrections: list = Field(default_factory=list)
    node_specializations: list = Field(default_factory=list)
    parent_id: str = ""


@router.get("/task22/discovery")
def discovery():
    return client_call(lambda: Task22Client().discover_task22())


def inputs(identifier, payload, engine):
    workspace = entry(identifier, "workspace")
    contract = provider_contract(workspace["document"], payload.corrections)
    validated = engine.invoke("/v1/evidence-contracts/validate", contract)
    request = {"evidence": validated["contract"], "protocol": payload.protocol,
               "node_specializations": payload.node_specializations, "usage": "RESEARCH"}
    return request, validated


@router.post("/workspaces/{identifier}/criteria/preflight")
def preflight(identifier: str, payload: EvaluationRequest):
    def execute():
        engine = Task22Client()
        request, validated = inputs(identifier, payload, engine)
        contract = request["evidence"]
        requirements = engine.invoke("/v1/evidence/requirements", {
            "variant": contract["variant"], "context": contract["context"],
            "protocol": payload.protocol, "supplied": contract})
        return {"validated": validated, "requirements": requirements, "correlation_id": engine.correlation_id}
    return client_call(execute)


@router.post("/workspaces/{identifier}/criteria/evaluate", status_code=201)
def evaluate(identifier: str, payload: EvaluationRequest):
    def execute():
        if payload.parent_id and entry(payload.parent_id, "criteria_evaluation")["workspace_id"] != identifier:
            raise ValueError("Previous evaluation belongs to another workspace")
        engine = Task22Client()
        request, validated = inputs(identifier, payload, engine)
        result = engine.invoke("/v1/criteria/evaluate", request)
        # Save the automatic result before fetching bundles: an interrupted GET
        # must never cause loss or a repeated scientific evaluation.
        saved = store.save("criteria_evaluation", {
            "request": request, "validated": validated, "engine_result": result,
            "corrections": payload.corrections, "parent_id": payload.parent_id,
            "provenance": {"correlation_id": engine.correlation_id, "engine_url": engine.url,
                           "evaluated_at": now(), "schema": "criteria-matrix-1.0",
                           "transport_requests": list(engine.transport_requests)}}, identifier)
        try:
            store.save("criteria_artifacts", {"result_id": saved["id"], "bundles": engine.bundles(result),
                       "transport_requests": engine.transport_requests}, identifier)
        except EngineError:
            # Matrix and trace are already durable. Artifact retrieval can be
            # retried explicitly; do not silently replace the result.
            raise HTTPException(502, {"code": "ARTIFACT_ARCHIVE_INCOMPLETE", "result_id": saved["id"],
                                      "message": "Evaluation saved. Retry saving its replay bundles from history."})
        return saved
    return client_call(execute)


@router.get("/results/{identifier}/criteria/artifacts")
def artifacts(identifier: str):
    value = entry(identifier, "criteria_evaluation")
    found = [e for e in store.history(value["workspace_id"]) if e["kind"] == "criteria_artifacts" and e["document"]["result_id"] == identifier]
    return found[-1]["document"]["bundles"] if found else {}


@router.post("/results/{identifier}/criteria/archive")
def archive(identifier: str):
    def execute():
        value = entry(identifier, "criteria_evaluation")
        bundles = Task22Client().bundles(value["document"]["engine_result"])
        return store.save("criteria_artifacts", {"result_id": identifier, "bundles": bundles}, value["workspace_id"])
    return client_call(execute)


@router.get("/results/{identifier}/criteria/{criterion}/nodes/{node_id}")
def node(identifier: str, criterion: str, node_id: str):
    bundle = artifacts(identifier).get(criterion)
    if bundle is None:
        raise HTTPException(409, "Replay bundle has not been archived")
    definition = next((n for n in bundle["tree"]["nodes"] if n["node_id"] == node_id), None)
    record = next((n for n in bundle["trace"]["records"] if n["node_id"] == node_id), None)
    if definition is None or record is None:
        raise HTTPException(404, "Node not found in the engine bundle")
    return {"definition": definition, "execution": record,
            "evidence_values": [e for e in bundle["trace"]["evidence_values"] if e["value"]["id"] in record["evidence_ids"]]}


@router.post("/workspaces/{identifier}/criteria/compare", status_code=201)
def compare(identifier: str, payload: EvaluationRequest):
    def execute():
        engine = Task22Client()
        request, validated = inputs(identifier, payload, engine)
        discovered = engine.discover_task22()
        configurations = [dict(request, protocol=m["selection"],
                               node_specializations=payload.node_specializations if m["selection"]["protocol"] == "CLINGEN_GENERAL" else [])
                          for m in discovered["protocols"]]
        result = engine.invoke("/v1/criteria/compare", {"evidence": request["evidence"], "configurations": configurations})
        saved = store.save("criteria_comparison", {"request": request, "validated": validated,
                           "engine_result": result, "correlation_id": engine.correlation_id}, identifier)
        for matrix in result["results"]:
            store.save("criteria_artifacts", {"result_id": saved["id"], "protocol": matrix["protocol"],
                       "bundles": engine.bundles(matrix)}, identifier)
        return saved
    return client_call(execute)


class ReviewRequest(BaseModel):
    criterion: str
    decision: str
    rationale: str = Field(..., min_length=1, max_length=20000)
    reviewer_id: str = Field(..., min_length=1, max_length=200)
    revised_status: str | None = None
    revised_strength: dict | None = None


@router.post("/results/{identifier}/criteria/reviews", status_code=201)
def review(identifier: str, payload: ReviewRequest):
    value = entry(identifier, "criteria_evaluation")
    criterion = next((c for c in value["document"]["engine_result"]["criteria"] if c["criterion_id"] == payload.criterion), None)
    statuses = {"ACTIVE", "INACTIVE", "NOT_EVALUABLE", "NOT_APPLICABLE", "CONFLICTING_EVIDENCE", "REQUIRES_REVIEW"}
    if criterion is None or payload.decision not in ("CONFIRM", "CONTEST", "REQUEST_REVIEW", "MANUAL_DECISION"):
        raise HTTPException(422, "Invalid criterion or review action")
    if not payload.rationale.strip() or not payload.reviewer_id.strip():
        raise HTTPException(422, "Reviewer and rationale are required")
    if payload.decision == "MANUAL_DECISION":
        if payload.revised_status not in statuses or (payload.revised_status == "ACTIVE") != (payload.revised_strength is not None):
            raise HTTPException(422, "Manual decision requires a status; strength is assigned only for ACTIVE")
        if payload.revised_strength is not None:
            # Validate against the exact locally saved rule's permitted strengths.
            allowed = criterion["rule"]["permitted_strengths"]
            direction = "BENIGN" if payload.criterion.startswith("B") else "PATHOGENIC"
            if set(payload.revised_strength) != {"direction", "level"} or payload.revised_strength["direction"] != direction or payload.revised_strength["level"] not in allowed:
                raise HTTPException(422, "Strength must be permitted by the recorded rule")
    elif payload.revised_status is not None or payload.revised_strength is not None:
        raise HTTPException(422, "Only a manual decision can include a revised outcome")
    return store.save("criteria_review", dict(payload.dict(), result_id=identifier,
                      automatic_fingerprint=digest(criterion), execution_id=criterion["execution"]["execution_id"]), value["workspace_id"])


@router.get("/results/{identifier}/criteria/diff/{previous}")
def diff(identifier: str, previous: str):
    after, before = entry(identifier, "criteria_evaluation"), entry(previous, "criteria_evaluation")
    if after["workspace_id"] != before["workspace_id"]:
        raise HTTPException(422, "Results belong to different workspaces")
    left = {c["criterion_id"]: c for c in before["document"]["engine_result"]["criteria"]}
    return {"before_id": previous, "after_id": identifier,
            "before_evidence": before["document"]["request"]["evidence"],
            "after_evidence": after["document"]["request"]["evidence"],
            "criteria": [{"criterion": c["criterion_id"], "before": left[c["criterion_id"]], "after": c,
                          "changed": left[c["criterion_id"]] != c} for c in after["document"]["engine_result"]["criteria"]]}


@router.post("/results/{identifier}/criteria/trace-compare/{previous}/{criterion}")
def compare_trace(identifier: str, previous: str, criterion: str):
    comparison = diff(identifier, previous)
    row = next((c for c in comparison["criteria"] if c["criterion"] == criterion), None)
    if row is None:
        raise HTTPException(404, "Criterion not found")
    def execute():
        engine = Task22Client()
        result = engine.invoke("/v1/criteria/executions/compare", {
            "left_execution": row["before"]["execution"]["execution_id"],
            "right_execution": row["after"]["execution"]["execution_id"]})
        return store.save("criteria_trace_comparison", {"before_id": previous, "after_id": identifier,
                          "criterion": criterion, "engine_result": result}, entry(identifier)["workspace_id"])
    return client_call(execute)


@router.get("/results/{identifier}/criteria/export/{format}")
def export(identifier: str, format: str):
    value = entry(identifier)
    if value["kind"] not in ("criteria_evaluation", "criteria_comparison"):
        raise HTTPException(409, "Not a Task 22 result")
    result = value["document"]["engine_result"]
    reviews = [e for e in store.history(value["workspace_id"]) if e["kind"] == "criteria_review" and e["document"]["result_id"] == identifier]
    media, suffix = "application/json", "json"
    if format == "engine":
        content = result
    elif format == "audit":
        content = {"entry": value, "reviews": reviews,
                   "artifacts": [e for e in store.history(value["workspace_id"]) if e["kind"] == "criteria_artifacts" and e["document"]["result_id"] == identifier]}
    elif format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["criterion", "status", "strength", "protocol", "version", "rule", "rationale", "execution_id", "manual_reviews"])
        for matrix in result.get("results", [result]):
            for c in matrix["criteria"]:
                cells = [c["criterion_id"], c["activation_status"], json.dumps(c["assigned_strength"]),
                         matrix["protocol"]["protocol"], matrix["protocol"]["version"], c["rule"]["rule_id"], c["rationale"],
                         c["execution"]["execution_id"], json.dumps([e["document"] for e in reviews if e["document"]["criterion"] == c["criterion_id"]])]
                writer.writerow(["'" + str(x) if str(x).startswith(("=", "+", "-", "@")) else x for x in cells])
        content, media, suffix = output.getvalue(), "text/csv", "csv"
    else:
        raise HTTPException(404, "Unknown export format")
    if media == "application/json":
        content = json.dumps(content, ensure_ascii=False, indent=2, allow_nan=False)
    return Response(content, media_type=media, headers={"Content-Disposition": 'attachment; filename="acmg-task22-{}.{}"'.format(format, suffix)})
