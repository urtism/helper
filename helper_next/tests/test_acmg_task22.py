"""Focused contract tests; real REST checks are explicit and single-variant only."""
import copy
import json
import os
from pathlib import Path

import pytest

from helper_next.api import acmg_task22 as api
from helper_next.core import acmg_store
from helper_next.core.acmg_client import EngineError
from helper_next.core.acmg_task22 import Task22Client, provider_contract
from helper_next.core.acmg_workbench import prepare
from fastapi import HTTPException


ENGINE = Path(__file__).resolve().parents[2].parent / "acmg-engine"
LIVE = pytest.mark.skipif(os.environ.get("HELPER_TEST_TASK22_SERVICE") != "1", reason="Opt-in local Task 22 REST verification")


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    fasta = tmp_path / "reference.fa"
    fasta.write_text(">1\n" + "A" * 200 + "\n")
    Path(str(fasta) + ".fai").write_text("1\t200\t3\t200\t201\n")
    config = tmp_path / "reference.json"
    config.write_text(json.dumps({"GRCh38": {"fasta": str(fasta), "version": "synthetic-task23-1"}}))
    monkeypatch.setenv("HELPER_ACMG_REFERENCE_CONFIG", str(config))
    detail = {"reference_build": "GRCh38", "chromosome": "1", "position": 100,
              "reference": "A", "alternate": "G", "metadata": {}, "annotations": [
                  {"id": 1, "gene": "DEMO", "transcript": "ENST000001.1", "consequence": "missense_variant",
                   "hgvsc": "c.1A>G", "hgvsp": "p.Lys1Arg", "metadata": {"fields": {
                       "REVEL": "0.73", "gnomAD_AF": "0.00001", "SpliceAI_pred_DS_AG": "0.1"}}}]}
    context = {"gene": {"namespace": "DEMO", "identifier": "GENE-1"},
               "disease": {"namespace": "DEMO", "identifier": "DISEASE-1"}}
    return acmg_store.save("workspace", prepare(detail, {"source_id": "synthetic-contract"}, context, "ENST000001.1", "GRCh38"))


def test_adapter_preserves_original_values_and_never_promotes_quality(workspace):
    document = workspace["document"]
    before = copy.deepcopy(document)
    contract = provider_contract(document)
    assert document == before
    assert contract["schema_version"] == "evidence-contract-1.0"
    assert all(e["quality_status"] == "UNKNOWN" and e["validation_status"] == "UNVERIFIED" for e in contract["evidence"])
    original = document["normalized_evidence"]["snapshot"]["evidence"]
    assert [json.loads(e["received_json"]) for e in contract["evidence"]] == original
    assert contract["evidence"][0]["value"]["observation"]["score"] == .73
    assert "classification" not in contract


def test_adapter_requires_reference_and_transcript_version(workspace):
    document = copy.deepcopy(workspace["document"])
    document["normalized_evidence"]["snapshot"]["variant"]["normalization"]["status"] = "UNVERIFIED"
    with pytest.raises(EngineError, match="FASTA"):
        provider_contract(document)
    document = copy.deepcopy(workspace["document"])
    document["normalized_evidence"]["snapshot"]["context"]["transcripts"][0]["version"] = None
    with pytest.raises(EngineError, match="versioned transcript"):
        provider_contract(document)


def test_schema_errors_do_not_expose_values():
    client = Task22Client()
    client.openapi = {}
    with pytest.raises(EngineError) as error:
        client.validate({"clinical": "PRIVATE"}, {"type": "object", "additionalProperties": False})
    assert "PRIVATE" not in str(error.value) + json.dumps(error.value.details)


def test_transport_retries_reads_only(monkeypatch):
    calls = []
    def fail(self, path, payload=None, allow_array=False):
        calls.append((path, payload))
        raise EngineError("ENGINE_UNAVAILABLE", "Unavailable", 503)
    monkeypatch.setattr("helper_next.core.acmg_client.ACMGClient.call", fail)
    client = Task22Client()
    with pytest.raises(EngineError):
        client.call("/health")
    assert len(calls) == 2
    calls.clear()
    with pytest.raises(EngineError):
        client.call("/v1/criteria/evaluate", {})
    assert len(calls) == 1


def test_bad_manual_correction_does_not_change_snapshot(workspace):
    before = copy.deepcopy(workspace["document"])
    with pytest.raises(ValueError, match="reason"):
        provider_contract(before, [{"value": {}}])
    assert before == workspace["document"]


@LIVE
def test_real_helper_adapter_validation_matrix_and_archived_nodes(workspace):
    client = Task22Client()
    discovery = client.discover_task22()
    assert len(discovery["protocols"]) == 2
    request = api.EvaluationRequest(protocol=discovery["protocols"][0]["selection"])
    preflight = api.preflight(workspace["id"], request)
    assert preflight["requirements"]["schema_version"] == "evidence-requirements-1.1"
    result = api.evaluate(workspace["id"], request)
    matrix = result["document"]["engine_result"]
    assert matrix["schema_version"] == "criteria-matrix-1.0"
    assert len(matrix["criteria"]) == 28
    assert "classification" not in matrix
    bundles = api.artifacts(result["id"])
    assert len(bundles) == 28
    for code in ("PM2", "PVS1"):
        criterion = next(c for c in matrix["criteria"] if c["criterion_id"] == code)
        assert criterion["execution"] == bundles[code]["trace"]
        for node in bundles[code]["tree"]["nodes"]:
            detail = api.node(result["id"], code, node["node_id"])
            assert detail["definition"] == node
            if not detail["execution"]["executed"]:
                assert detail["execution"]["outcome"] == "SKIPPED"
                assert detail["execution"]["calculated_value_json"] is None
    assert json.loads(api.export(result["id"], "engine").body) == matrix


@LIVE
def test_real_corrections_reviews_rerun_comparison_and_offline_audit(workspace, monkeypatch):
    request = api.EvaluationRequest(protocol={"protocol": "ACMG_2015", "version": "1.0.0"})
    first = api.evaluate(workspace["id"], request)
    immutable = copy.deepcopy(first)
    item = copy.deepcopy(workspace["document"]["normalized_evidence"]["snapshot"]["evidence"][0])
    item["provenance"]["extraction_method"] = "MANUAL"
    item["observation"]["score"] = .51
    corrections = [{"value": item, "replaces": item["id"], "comment": "Synthetic score correction"}]
    second = api.evaluate(workspace["id"], api.EvaluationRequest(protocol=request.protocol, corrections=corrections, parent_id=first["id"]))
    assert first["id"] != second["id"]
    assert first["document"]["engine_result"]["criteria"][0]["execution"]["execution_id"] != second["document"]["engine_result"]["criteria"][0]["execution"]["execution_id"]
    review = api.review(second["id"], api.ReviewRequest(criterion="PM2", decision="CONTEST", reviewer_id="synthetic-reviewer", rationale="Synthetic review only"))
    assert review["document"]["execution_id"]
    manual = api.review(second["id"], api.ReviewRequest(criterion="PM2", decision="MANUAL_DECISION", reviewer_id="synthetic-reviewer", rationale="Synthetic manual decision", revised_status="INACTIVE"))
    assert manual["document"]["revised_status"] == "INACTIVE"
    with pytest.raises(HTTPException):
        api.review(second["id"], api.ReviewRequest(criterion="PM2", decision="MANUAL_DECISION", reviewer_id="synthetic-reviewer", rationale="Invalid", revised_status="ACTIVE"))
    difference = api.diff(second["id"], first["id"])
    assert difference["before_evidence"] != difference["after_evidence"]
    trace_difference = api.compare_trace(second["id"], first["id"], "PM2")
    assert "first_divergent_index" in trace_difference["document"]["engine_result"]
    comparison = api.compare(workspace["id"], request)
    assert len(comparison["document"]["engine_result"]["differences"]) == 28
    assert {r["protocol"]["protocol"] for r in comparison["document"]["engine_result"]["results"]} == {"ACMG_2015", "CLINGEN_GENERAL"}
    assert acmg_store.get(first["id"]) == immutable
    monkeypatch.setattr(api, "Task22Client", lambda: (_ for _ in ()).throw(AssertionError("Offline audit must not contact the engine")))
    for format in ("engine", "audit", "csv"):
        assert api.export(second["id"], format).status_code == 200
        assert api.export(comparison["id"], format).status_code == 200
    bundle = api.artifacts(second["id"])["PM2"]
    assert api.node(second["id"], "PM2", bundle["trace"]["terminal_node"])["execution"]["executed"]
    assert len(json.loads(api.export(second["id"], "audit").body)["reviews"]) == 2


@LIVE
@pytest.mark.parametrize("code", ["pm2", "pvs1"])
def test_real_task22_replay_fixtures_via_rest(code):
    path = ENGINE / "docs/examples/task22" / ("acmg_2015_" + code + "_replay.json")
    fixture = json.loads(path.read_text())
    client = Task22Client()
    result = client.invoke("/v1/criteria/evaluate", fixture["request"])
    criterion = next(c for c in result["criteria"] if c["criterion_id"] == code.upper())
    assert criterion["execution"] == fixture["trace"]
    bundle = client.invoke("/v1/criteria/executions/" + criterion["execution"]["execution_id"] + "/replay-bundle",
                           template="/v1/criteria/executions/{execution_id}/replay-bundle")
    assert bundle["tree"] == fixture["tree"]
