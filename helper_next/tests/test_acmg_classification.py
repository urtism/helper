"""Synthetic transport regressions to run later; no clinical assertions."""
import copy

import pytest

from helper_next.core import acmg_classification as bridge
from helper_next.core import acmg_evidence as evidence_builder
from helper_next.core.acmg_client import EngineError
from helper_next.core.acmg_task22 import Task22Client


def confidence_contract():
    return {"evidence": [{"value": {"kind": "PVS1", "observation": {
        "mechanism": {"confidence_assessment": {"mechanism_confidence": "INFERRED"}}}}}]}


def test_old_classifier_request_schema_blocks_before_post(monkeypatch):
    engine = Task22Client()
    engine.openapi = {"paths": {"/v1/evidence-packets/interpret": {"post": {
        "requestBody": {"content": {"application/json": {"schema": {
            "type": "object", "additionalProperties": False}}}}}}}}
    def unexpected(*args, **kwargs):
        pytest.fail("Incompatible classification must not be posted")
    monkeypatch.setattr(engine, "invoke", unexpected)
    with pytest.raises(EngineError) as error:
        bridge.classification_call(engine, "/v1/evidence-packets/interpret", {"packet": {}})
    assert error.value.code == "ENGINE_CLASSIFICATION_CONTRACT_UNSUPPORTED"


def test_legacy_pvs1_result_cannot_masquerade_as_confidence_integration():
    result = {"criterion_results": [{"code": "PVS1", "status": "MET"}],
              "classification": {"status": "CLASSIFIED", "category": "Pathogenic"}}
    original = copy.deepcopy(result)
    with pytest.raises(EngineError) as error:
        bridge.require_pvs1_result(result, confidence_contract())
    assert error.value.code == "ENGINE_PVS1_CLASSIFICATION_METADATA_MISSING"
    assert result == original


def test_exploratory_decision_and_final_classification_remain_engine_owned():
    evaluation = {"status": "EXPLORATORY", "active": False, "mechanism": "LOSS_OF_FUNCTION",
        "mechanism_confidence": "INFERRED", "mechanism_scope": "GENE_LEVEL",
        "calculated_strength": "VERY_STRONG", "applied_strength": None, "classification_eligible": False,
        "warnings": ["Synthetic fixture"], "requires_review": True, "reason": "Synthetic Engine decision",
        "source_evidence_json": "[]", "decision_trace": ["SYNTHETIC_TRACE"]}
    result = {"criterion_results": [{"code": "PVS1", "pvs1_evaluation": evaluation}],
              "classification": {"status": "NOT_CLASSIFIED", "included_criteria": []}}
    original = copy.deepcopy(result)
    bridge.require_pvs1_result(result, confidence_contract())
    assert result == original


def test_classify_uses_coordinator_and_retains_contract_and_original_workspace(monkeypatch):
    calls = []
    packet = {"snapshot": {"variant": {"identity": {}}, "context": {"gene": {}, "disease": {}},
                           "evidence": [], "dependencies": []}, "source_snapshots": [], "packet_id": "original"}
    contract = {"schema_version": "evidence-contract-1.1", "variant": packet["snapshot"]["variant"],
                "context": packet["snapshot"]["context"], "evidence": [], "dependencies": []}
    document = {"normalized_evidence": packet}
    original = copy.deepcopy(document)
    class Coordinator:
        def __init__(self, engine):
            pass

        def build(self, workspace, protocol, additions=(), mechanism_request=None):
            calls.append((workspace, protocol, mechanism_request))
            return {"contract": contract, "packet": packet, "errors": [], "validated": {},
                    "mechanism_assessment": {"mechanism_confidence": "UNKNOWN"}}
    monkeypatch.setattr(evidence_builder, "EvidenceCoordinator", Coordinator)
    supplied, audit = bridge.coordinated_packet(object(), document, [{"strategy": "CLINGEN_GUIDED"}], [])
    assert len(calls) == 1 and calls[0][1]["protocol"] == "CLINGEN_GENERAL"
    assert audit["automatic_contract"] == audit["contract"] == contract
    assert supplied["packet_id"].startswith("helper-coordinated-")
    assert document == original


def test_coordinator_errors_prevent_classifier_handoff(monkeypatch):
    class Coordinator:
        def __init__(self, engine):
            pass

        def build(self, *args, **kwargs):
            return {"errors": [{"code": "ENGINE_CONTRACT_VERSION_UNSUPPORTED", "message": "1.1 required", "status": 409}]}
    monkeypatch.setattr(evidence_builder, "EvidenceCoordinator", Coordinator)
    with pytest.raises(EngineError) as error:
        bridge.coordinated_packet(object(), {"normalized_evidence": {"snapshot": {"context": {}}}},
                                  [{"strategy": "CLINGEN_GUIDED"}], [])
    assert error.value.code == "ENGINE_CONTRACT_VERSION_UNSUPPORTED"
