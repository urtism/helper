"""Bridge coordinated evidence to the existing Engine classifiers; no ACMG rules."""
import copy
import os

from helper_next.core.acmg_client import EngineError, digest
from helper_next.core.acmg_evidence import prepare_evidence


def coordinated_packet(engine, workspace, configurations, corrections, protocol=None):
    """Build once and preserve both automatic evidence and manual corrections.

    The legacy classifier consumes a packet rather than provider envelopes. Its
    authoritative request schema must accept every coordinated observation.
    There is no fallback that strips mechanism confidence to fit an old Engine.
    """
    if protocol is None:
        # Transport selection only; the manifest and every scientific rule remain
        # owned by the Engine. Custom strategies require an explicit protocol.
        names = {"CLINGEN_GUIDED": "CLINGEN_GENERAL", "ACMG_2015": "ACMG_2015"}
        selected = {names.get(c["strategy"]) for c in configurations}
        if len(selected) != 1 or None in selected:
            raise EngineError("CLASSIFICATION_PROTOCOL_REQUIRED",
                              "Select one explicit Engine criteria protocol for these classification configurations", 409)
        protocol = {"protocol": selected.pop(),
                    "version": os.environ.get("ACMG_CRITERIA_PROTOCOL_VERSION", "1.0.0")}
    built = prepare_evidence(engine, workspace, protocol, packet_corrections=corrections)
    packet = copy.deepcopy(built["packet"])
    packet["packet_id"] = "helper-coordinated-" + digest(packet)["value"]
    audit = {k: v for k, v in built.items() if k not in {"packet", "contract", "validated"}}
    audit.update(protocol=protocol, contract=built["contract"],
                 corrections=copy.deepcopy(corrections))
    return packet, audit


def classification_call(engine, path, request):
    """Reject an incompatible classifier before sending the interpretation POST."""
    if engine.openapi is None:
        engine.openapi = engine.call("/openapi.json")
    operation = engine.openapi.get("paths", {}).get(path, {}).get("post")
    if not operation:
        raise EngineError("ENGINE_CLASSIFICATION_UNAVAILABLE", "Required Engine classification operation is absent", 409)
    try:
        engine.validate(request, operation["requestBody"]["content"]["application/json"]["schema"])
    except EngineError as exc:
        raise EngineError("ENGINE_CLASSIFICATION_CONTRACT_UNSUPPORTED",
                          "The Engine classifier cannot consume the coordinated evidence; an Engine integration update is required",
                          409, {"operation": path, "validation": exc.details}) from None
    return engine.invoke(path, request)


def require_pvs1_result(result, contract):
    """Check response completeness, never determine activation or strength."""
    has_assessment = any(e["value"]["kind"] == "PVS1" and
                         (e["value"]["observation"].get("mechanism") or {}).get("confidence_assessment")
                         for e in contract["evidence"])
    if not has_assessment:
        return
    criterion = next((c for c in result.get("criterion_results", []) if c.get("code") == "PVS1"), {})
    evaluation = criterion.get("pvs1_evaluation") or {}
    required = {"status", "active", "mechanism", "mechanism_confidence", "mechanism_scope", "calculated_strength", "applied_strength",
                "classification_eligible", "warnings", "requires_review", "reason", "source_evidence_json", "decision_trace"}
    if not required.issubset(evaluation):
        raise EngineError("ENGINE_PVS1_CLASSIFICATION_METADATA_MISSING",
                          "Engine classification does not expose the required PVS1 confidence decision and audit", 409)
