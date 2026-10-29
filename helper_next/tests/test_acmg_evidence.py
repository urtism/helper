"""Synthetic offline builder checks against the actual adjacent engine validator."""
import copy
import io
import json
import os
import subprocess
from pathlib import Path
from urllib.error import URLError

import pytest
from jsonschema import Draft202012Validator

from helper_next.api import acmg_task22 as api
from helper_next.core import acmg_store
from helper_next.core.acmg_workbench import prepare
from helper_next.core.acmg_client import EngineError
from helper_next.core.acmg_evidence import EvidenceAssembler, EvidenceCoordinator, gene_disease_candidates
from helper_next.core.acmg_sources import SourceManager
from helper_variants import gene_phenotype, gnomad_frequency
from test_acmg_task22 import workspace  # Reuse the existing synthetic FASTA/workspace fixture.


ENGINE = Path(os.environ.get("HELPER_TEST_ENGINE_ROOT", Path(__file__).resolve().parents[2].parent / "acmg-engine"))
PROTOCOL = {"protocol": "ACMG_2015", "version": "1.0.0"}


@pytest.fixture
def engine():
    executable = Path(os.environ.get("HELPER_TEST_ENGINE_PYTHON", ENGINE / ".venv/bin/python"))
    if not executable.is_file():
        pytest.skip("Adjacent engine runtime required for authoritative builder validation")
    # Separate runtime: HELPER keeps its existing Pydantic version and no engine imports.
    script = """
import json, sys
from acmg_engine.domain.evidence_contract import EvidenceContract, EvidenceRequirementsRequest
from acmg_engine.services.evidence_contract import normalize_contract, evidence_requirements
for line in sys.stdin:
    path, payload = json.loads(line)
    try:
        if path == '/v1/evidence-contracts/validate':
            result = normalize_contract(EvidenceContract.model_validate(payload))
        else:
            assert path == '/v1/evidence/requirements'
            result = evidence_requirements(EvidenceRequirementsRequest.model_validate(payload))
        print(json.dumps({'result': result.model_dump(mode='json')}), flush=True)
    except Exception as exc:
        print(json.dumps({'error': type(exc).__name__}), flush=True)
"""
    env = dict(os.environ, PYTHONPATH=str(ENGINE / "src"))
    process = subprocess.Popen([str(executable), "-u", "-c", script], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)

    class RealEngine:
        correlation_id = "synthetic-builder"

        def __init__(self):
            self.calls = []

        def invoke(self, path, payload):
            self.calls.append((path, copy.deepcopy(payload)))
            process.stdin.write(json.dumps([path, payload]) + "\n")
            process.stdin.flush()
            line = process.stdout.readline()
            assert line, process.stderr.read()
            result = json.loads(line)
            if "error" in result:
                raise EngineError("INVALID_TASK22_CONTRACT", "Real engine rejected synthetic contract", 422, result)
            return result["result"]

    yield RealEngine()
    process.stdin.close()
    process.wait(timeout=10)
    assert process.returncode == 0, process.stderr.read()


def population(ac=1, an=3, af=None):
    return {"reference_build": "GRCh38", "chromosome": "1", "position": 100,
            "reference": "A", "alternate": "G", "dataset": "gnomad_r4", "release": "4.1",
            "status": "observed", "ac": ac, "an": an, "af": ac / an if af is None else af,
            "populations": [], "filters": [], "retrieved_at": "2026-01-01T12:00:00Z",
            "source_url": "https://gnomad.broadinstitute.org/", "coverage": {"available": False}}


def cache_population(raw):
    gnomad_frequency._store(gnomad_frequency.cache_path(),
                           gnomad_frequency.cache_key("GRCh38", "1", 100, "A", "G"), raw)


def test_source_cache_reuse_and_explicit_fetch(workspace, monkeypatch):
    identity = workspace["document"]["normalized_evidence"]["snapshot"]["variant"]["identity"]
    calls = []
    monkeypatch.setattr(gnomad_frequency, "lookup_variant", lambda *a, **k: calls.append(a) or population())
    manager = SourceManager()
    assert manager.population(identity)["data"] is None
    assert not calls
    assert manager.population(identity, fetch=True)["data"]["release"] == "4.1"
    assert len(calls) == 1
    cache_population(population())
    assert manager.population(identity)["status"] == "CACHED"
    assert manager.population(identity, fetch=True)["data"] == population()
    assert len(calls) == 1
    assert manager.population(dict(identity, alternate="T"))["data"] is None


@pytest.mark.parametrize("status,stale,expected", [("ready", False, "CACHED"), ("ready", True, "STALE"),
                                                  ("invalid", False, "ERROR"), ("missing", False, "AVAILABLE")])
def test_source_states_and_snapshot_not_release(monkeypatch, status, stale, expected):
    monkeypatch.setattr(gene_phenotype, "query_gene", lambda *a, **k: {
        "cache": {"status": status, "stale": stale, "updated_at": "2026-01-01T00:00:00Z"}})
    source = SourceManager().gene_disease("DEMO", "HGNC:1")
    assert source["status"] == expected
    assert source["release"] is None
    assert source["acquired_at"] == "2026-01-01T00:00:00Z"


def test_unreachable_is_only_reported_after_access_failure(monkeypatch, workspace):
    identity = workspace["document"]["normalized_evidence"]["snapshot"]["variant"]["identity"]
    monkeypatch.setattr(gnomad_frequency, "lookup_variant", lambda *a, **k: (_ for _ in ()).throw(URLError("offline")))
    manager = SourceManager()
    assert manager.population(identity)["status"] == "AVAILABLE"
    assert manager.population(identity, fetch=True)["status"] == "UNREACHABLE"
    assert manager.population(identity, attached={"status": "unavailable", "error": "Invalid response"})["status"] == "ERROR"


@pytest.mark.parametrize("ac,an", [(1, 3), (1, 118595), (2, 7), (0, 100), (100, 100)])
def test_real_assembler_does_not_conflict_on_float_roundoff(workspace, engine, ac, an):
    raw = population(ac, an)
    cache_population(raw)
    before = copy.deepcopy(workspace)
    result = EvidenceCoordinator(engine).build(workspace["document"], PROTOCOL)
    assert result["errors"] == []
    assert workspace == before
    contract = result["contract"]
    schema = json.loads((ENGINE / "docs/schemas/evidence-contract-1.0.json").read_text())
    Draft202012Validator(schema).validate(contract)
    item = next(e for e in contract["evidence"] if e["value"]["kind"] == "POPULATION" and e["value"]["id"] == "helper-gnomad-genomes")
    assessment = next(e for e in result["validated"]["assessments"] if e["evidence_id"] == "helper-gnomad-genomes")
    assert assessment["status"] != "CONFLICTING"
    assert item["value"]["observation"]["aggregate"]["allele_frequency"] == ac / an
    assert json.loads(item["received_json"])["record"] == raw
    assert item["validation_status"] == "UNVERIFIED" and item["quality_status"] == "UNKNOWN"
    assert item["value"]["provenance"]["source_version"] == "4.1"
    assert item["transformations"]


def test_true_af_conflict_is_preserved(workspace, engine):
    cache_population(population(1, 3, .9))
    result = EvidenceCoordinator(engine).build(workspace["document"], PROTOCOL)
    assert not result["errors"]
    assessment = next(a for a in result["validated"]["assessments"] if a["evidence_id"] == "helper-gnomad-genomes")
    assert assessment["status"] == "CONFLICTING"


def test_missing_counts_versions_and_partial_spliceai_remain_missing(workspace, engine):
    raw = population()
    raw.update(ac=None, an=None, af=None, status="not_observed_coverage_unknown")
    cache_population(raw)
    result = EvidenceCoordinator(engine).build(workspace["document"], PROTOCOL)
    assert not result["errors"]
    items = {e["value"]["id"]: e for e in result["contract"]["evidence"]}
    assert items["helper-gnomad-genomes"]["value"]["observation"]["aggregate"]["allele_count"] is None
    assert items["imported-revel"]["value"]["observation"]["predictor_version"] is None
    splice = items["imported-spliceai"]["value"]["observation"]["spliceai"]
    assert splice["maximum_delta"] is None and splice["donor_gain"] is None
    assert any(m["path"].endswith("/counts") for m in result["missing_evidence"])
    assert result["deferred_transformers"][0]["status"] == "DEFERRED"
    assert all(e["value"]["kind"] != "PVS1" for e in items.values())


def test_requirements_select_sources_and_protocols_reuse_public_cache(workspace, engine, monkeypatch):
    cache_population(population())
    monkeypatch.setattr(gnomad_frequency, "lookup_variant", lambda *a, **k: pytest.fail("No network fetch"))
    coordinator = EvidenceCoordinator(engine)
    first = coordinator.build(workspace["document"], PROTOCOL)
    second = coordinator.build(workspace["document"], dict(PROTOCOL, protocol="CLINGEN_GENERAL"))
    assert not first["errors"] and not second["errors"]
    assert first["contract"] == second["contract"]
    assert engine.calls[0][0] == "/v1/evidence/requirements"
    assert all("evaluate" not in path for path, _ in engine.calls)
    assert first["contract"]["dependencies"]  # Shared VCF artifact, no inferred predictor derivation.
    assert all(d["kind"] == "CORRELATED" for d in first["contract"]["dependencies"])
    assert "calls" not in json.dumps(first["contract"])

    class RequirementsOnly:
        def invoke(self, path, payload):
            if path == "/v1/evidence/requirements":
                return {"requirements": []}
            return engine.invoke(path, payload)

    manager = SourceManager()
    monkeypatch.setattr(manager, "population", lambda *a, **k: pytest.fail("Population not required"))
    monkeypatch.setattr(manager, "gene_disease", lambda *a, **k: pytest.fail("Gene-disease not required"))
    assert not EvidenceCoordinator(RequirementsOnly(), manager).build(workspace["document"], PROTOCOL)["errors"]


def test_assembler_structured_failure_and_existing_adapter_guard(workspace, engine):
    broken = copy.deepcopy(workspace["document"])
    broken["normalized_evidence"]["snapshot"]["variant"]["normalization"]["status"] = "UNVERIFIED"
    result = EvidenceAssembler(engine).assemble(broken)
    assert result["contract"] is None and result["errors"][0]["code"] == "REFERENCE_REQUIRED"
    assert engine.calls == []
    broken = copy.deepcopy(workspace["document"])
    item = broken["normalized_evidence"]["snapshot"]["evidence"][0]
    item["related_evidence_ids"] = ["missing-id"]
    result = EvidenceAssembler(engine).assemble(broken)
    assert result["errors"][0]["code"] == "INVALID_TASK22_CONTRACT"


def test_existing_preflight_api_uses_builder(workspace, engine, monkeypatch):
    monkeypatch.setattr(api, "Task22Client", lambda: engine)
    result = api.preflight(workspace["id"], api.EvaluationRequest(protocol=PROTOCOL))
    assert result["validated"]["scientific_validation"] == "NOT_PERFORMED"
    assert result["requirements"]["schema_version"] == "evidence-requirements-1.1"
    assert result["builder"]["sources"]
    assert acmg_store.get(workspace["id"]) == workspace


def test_real_gene_cache_retains_exact_context_and_unverified_candidates(workspace, engine):
    from test_gene_phenotype import HEADER

    gencc = HEADER + (
        "SGC-1,2,HGNC:1,DEMO,MONDO:1,Disease one,OMIM:1,D1,Strong,,Autosomal dominant,ClinGen,"
        "2026-01-01,https://example.test/assertion,PMID:1,,2026-01-02\n"
        "SGC-2,1,HGNC:1,DEMO,MONDO:2,Disease two,,,Definitive,,Autosomal dominant,ClinGen,"
        "2026-01-01,https://example.test/other,PMID:2,,2026-01-02\n")
    g2p = (
        "g2p id,gene symbol,hgnc id,disease name,disease mim,disease MONDO,"
        "allelic requirement,confidence,molecular mechanism,date of last review\n"
        "G2P-1,DEMO,HGNC:1,Disease one,1,MONDO:1,monoallelic_autosomal,strong,loss of function,2026-01-03\n"
        "G2P-2,DEMO,HGNC:1,Disease one,1,MONDO:1,biallelic,strong,gain of function,2026-01-03\n"
        "G2P-3,DEMO,HGNC:1,Disease two,2,MONDO:2,monoallelic_autosomal,strong,loss of function,2026-01-03\n")
    dosage = (
        "#Gene Symbol\tGene ID\tGenomic Location\tHaploinsufficiency Score\tTriplosensitivity Score\t"
        "Haploinsufficiency Disease ID\tDate Last Evaluated\n"
        "DEMO\t1234\tchr1:1-100\t3\t0\tMONDO:1\t2026-01-04\n")
    gene_phenotype.build_cache(io.StringIO(gencc), gene_phenotype.cache_path(),
                              g2p_stream=io.StringIO(g2p), dosage_stream=io.StringIO(dosage))
    context = {"gene": {"namespace": "HGNC", "identifier": "HGNC:1"},
               "disease": {"namespace": "MONDO", "identifier": "MONDO:1"},
               "inheritance_modes": ["AUTOSOMAL_DOMINANT"]}
    document = prepare(workspace["document"]["original_vcf_evidence"], {}, context, "ENST000001.1", "GRCh38")
    result = EvidenceCoordinator(engine).build(document, PROTOCOL)
    assert not result["errors"]
    candidates = {e["value"]["id"]: e for e in result["contract"]["evidence"] if e["value"]["kind"] == "EXTENSION"}
    assert set(candidates) == {"helper-gencc-candidates", "helper-g2p-candidates", "helper-clingen_dosage-candidates"}
    raw = {k: json.loads(e["received_json"]) for k, e in candidates.items()}
    assert raw["helper-gencc-candidates"]["records"][0]["version"] == 2
    g2p_rows = raw["helper-g2p-candidates"]["records"]
    assert {r["id"] for r in g2p_rows} == {"G2P-1", "G2P-2"}
    assert {r["mechanism"] for r in g2p_rows} == {"loss of function", "gain of function"}
    assert all(r["gene_id"] == "HGNC:1" and r["disease_id"] == "MONDO:1" for r in g2p_rows)
    assert {r["allelic_requirement"] for r in g2p_rows} == {"monoallelic_autosomal", "biallelic"}
    dosage_row = raw["helper-clingen_dosage-candidates"]["records"][0]
    assert dosage_row["gene_id"] == "1234" and dosage_row["gene_identity_match"] == "UNVERIFIED"
    assert result["contract"]["context"]["gene_disease"]["mechanism"] is None
    assert all(e["validation_status"] == "UNVERIFIED" for e in candidates.values())
    assert all(e["value"]["provenance"]["source_version"] is None for e in candidates.values())
    assert len(result["deferred_transformers"][0]["candidate_evidence_ids"]) == 3


def test_gene_symbol_fallback_and_other_disease_are_not_identity_proof():
    context = {"gene": {"namespace": "HGNC", "identifier": "HGNC:1"},
               "disease": {"namespace": "MONDO", "identifier": "MONDO:1"}}
    knowledge = {"associations": [{"disease_id": "MONDO:1", "assertions": [{"gene_id": "HGNC:1"}],
                                  "molecular_mechanism": {"records": [
                                      {"gene_id": "HGNC:2", "disease_id": "MONDO:1"},
                                      {"gene_id": "HGNC:1", "disease_id": "MONDO:2"}]}}]}
    candidates, _ = gene_disease_candidates(knowledge, context, "2026-01-01T00:00:00Z")
    assert [e["id"] for e in candidates] == ["helper-gencc-candidates"]


def test_distinct_clinical_workspaces_do_not_share_context(workspace, engine):
    first = copy.deepcopy(workspace["document"])
    second = copy.deepcopy(first)
    second["normalized_evidence"]["snapshot"]["context"]["disease"]["identifier"] = "OTHER-DISEASE"
    coordinator = EvidenceCoordinator(engine)
    a = coordinator.build(first, PROTOCOL)
    b = coordinator.build(second, PROTOCOL)
    assert not a["errors"] and not b["errors"]
    assert a["contract"]["context"]["disease"]["identifier"] == "DISEASE-1"
    assert b["contract"]["context"]["disease"]["identifier"] == "OTHER-DISEASE"


def test_manual_replacement_preserves_original_and_dependency_references(workspace, engine):
    document = workspace["document"]
    item = copy.deepcopy(document["normalized_evidence"]["snapshot"]["evidence"][0])
    replaced = item["id"]
    item["id"] = "manual-revel"
    item["provenance"]["extraction_method"] = "MANUAL"
    item["observation"]["score"] = .42
    result = EvidenceCoordinator(engine).build(document, PROTOCOL, [
        {"value": item, "replaces": replaced, "comment": "Synthetic manual replacement"}])
    assert not result["errors"]
    manual = next(e for e in result["contract"]["evidence"] if e["value"]["id"] == "manual-revel")
    assert json.loads(manual["received_json"]) == item
    assert manual["value"]["observation"]["score"] == .42
    assert all(replaced not in dep["evidence_ids"] for dep in result["contract"]["dependencies"])


def test_existing_evaluate_and_compare_archive_builder_without_extra_fetches(workspace, engine, monkeypatch):
    invoke = engine.invoke
    engine.url = "synthetic-offline-engine"
    engine.transport_requests = []
    engine.bundles = lambda result: {}
    engine.discover_task22 = lambda: {"protocols": [{"selection": PROTOCOL},
        {"selection": dict(PROTOCOL, protocol="CLINGEN_GENERAL")}]}
    requests = []

    def dispatch(path, payload):
        if path in ("/v1/criteria/evaluate", "/v1/criteria/compare"):
            requests.append((path, payload))
            return {"criteria": [], "results": [], "differences": []}
        return invoke(path, payload)

    engine.invoke = dispatch
    monkeypatch.setattr(api, "Task22Client", lambda: engine)
    monkeypatch.setattr(gnomad_frequency, "lookup_variant", lambda *a, **k: pytest.fail("Unexpected download"))
    evaluated = api.evaluate(workspace["id"], api.EvaluationRequest(protocol=PROTOCOL))
    compared = api.compare(workspace["id"], api.EvaluationRequest(protocol=PROTOCOL))
    assert evaluated["document"]["validated"]["scientific_validation"] == "NOT_PERFORMED"
    assert compared["document"]["builder"]["deferred_transformers"][0]["status"] == "DEFERRED"
    configurations = requests[1][1]["configurations"]
    assert len(configurations) == 2
    assert configurations[0]["evidence"] == configurations[1]["evidence"]
    assert acmg_store.get(workspace["id"]) == workspace


def test_coordinator_contract_errors_are_structured(workspace, engine):
    result = EvidenceCoordinator(engine).build(workspace["document"], PROTOCOL, [{"value": {}}])
    assert result["errors"][0]["code"] == "INVALID_BUILDER_INPUT"
    assert engine.calls == []
