"""Transport/audit tests use mocked scientific outcomes, never clinical validation."""
import copy
import json
from pathlib import Path
from urllib.error import URLError

import pytest
from fastapi import HTTPException

from helper_next.api import acmg
from helper_next.core import acmg_client, acmg_store, acmg_workbench as wb


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("HELPER_ACMG_DB", str(tmp_path / "reviews.sqlite"))
    fasta = tmp_path / "synthetic.fa"
    fasta.write_text(">14\n" + "A" * 200 + "\n")
    Path(str(fasta) + ".fai").write_text("14\t200\t4\t200\t201\n")
    reference_config = tmp_path / "reference.json"
    reference_config.write_text(json.dumps({"GRCh38": {"fasta": str(fasta), "version": "synthetic-reference-1"}}))
    monkeypatch.setenv("HELPER_ACMG_REFERENCE_CONFIG", str(reference_config))
    detail = {"id": 1, "reference_build": "GRCh38", "chromosome": "14", "position": 100,
              "reference": "A", "alternate": "G", "variant_type": "SNV", "metadata": {"original_vcf": {"filter": "PASS", "info": {"AF": "0.1"}}},
              "calls": [{"genotype": "0/1", "phased": False}],
              "annotations": [{"transcript": "ENST000001.1", "gene": "MYH7", "consequence": "missense_variant",
                               "hgvsc": "c.1A>G", "hgvsp": "p.Lys1Arg", "metadata": {"fields": {"REVEL": "0.73", "IMPACT": "HIGH", "CLIN_SIG": "pathogenic"}}}]}
    context = {"gene": {"namespace": "HGNC", "identifier": "HGNC:7577"},
               "disease": {"namespace": "MONDO", "identifier": "MONDO:0005045"}}
    prepared = wb.prepare(detail, {"source_id": "run-1", "sample_id": 1, "variant_id": 1}, context, "ENST000001.1", "GRCh38")
    return acmg_store.save("workspace", prepared)


def scientific_result(status="MET"):
    # Synthetic boundary audit copied verbatim as text, no calculation in HELPER.
    criterion = {"code": "PM2", "status": status, "activation": "ENABLED", "reason_code": "METHOD_DISCORDANCE" if status == "MANUAL_REVIEW_REQUIRED" else "FIXTURE",
                 "strength": {"direction": "PATHOGENIC", "level": "SUPPORTING"} if status == "MET" else None,
                 "explanation": "Mocked outcome, not clinical evidence", "population_upper_ci": [{
                     "binomial_upper95": "0.00003999991265", "poisson_upper95": "0.00004000054402", "threshold": "0.00004",
                     "primary_candidate_met": True, "sensitivity_candidate_met": False, "method_discordance": True}],
                 "rules": [{"rule_id": "fixture", "version": "1", "parameters": [{"name": "operator", "value": "LE"}]}]}
    return {"result_id": "fixture-result", "criterion_results": [criterion], "classification": {
        "status": "NOT_CLASSIFIED", "category": None, "included_criteria": [], "effective_strengths": [],
        "dependencies": [{"criterion_codes": ["PM2"], "disposition": "EXCLUDE"}] if status == "MET" else [],
        "excluded_criteria": [{"code": "PM2", "reason": "dependency fixture"}] if status == "MET" else []}}


def test_mapping_preserves_original_and_declares_missing(workspace):
    doc = workspace["document"]
    packet = doc["normalized_evidence"]
    assert doc["original_vcf_evidence"]["metadata"]["original_vcf"]["info"]["AF"] == "0.1"
    assert packet["snapshot"]["evidence"][0]["observation"]["score"] == 0.73
    assert len(packet["snapshot"]["evidence"]) == 1  # No ClinVar, impact or inferred AC/AN evidence.
    assert packet["snapshot"]["variant"]["normalization"]["status"] == "NORMALIZED"
    assert any("inheritance_modes" in m["path"] for m in packet["missing_evidence"])
    assert "calls" not in json.dumps(packet)


@pytest.mark.parametrize("status", ["MET", "NOT_MET", "NOT_APPLICABLE", "INSUFFICIENT_EVIDENCE", "MANUAL_REVIEW_REQUIRED", "NOT_EVALUATED"])
def test_all_statuses_and_candidate_effective_separation(status):
    rows = wb.criterion_rows(scientific_result(status))
    assert len(rows) == 28
    row = next(c for c in rows if c["code"] == "PM2")
    assert row["engine_status"] == status
    assert row["candidate_active"] == {"MET": True, "NOT_MET": False}.get(status)
    assert row["effective_active"] is False
    assert row["effective_strength"] is None
    if status == "MET":
        assert row["display_status"] == "EXCLUDED_BY_DEPENDENCY"
    assert next(c for c in rows if c["code"] == "PP5")["display_status"] == "DEPRECATED"
    assert row["raw"]["population_upper_ci"][0]["binomial_upper95"] != row["raw"]["population_upper_ci"][0]["poisson_upper95"]


def test_missing_fields_not_invented():
    row = wb.criterion_rows({"criterion_results": []})[0]
    assert row["effective_active"] is None and row["raw"] is None


def test_context_assembly_transcript_and_structural_guards(workspace):
    doc = workspace["document"]
    detail = copy.deepcopy(doc["original_vcf_evidence"])
    context = doc["normalized_evidence"]["snapshot"]["context"]
    with pytest.raises(ValueError, match="Assembly conflicts"):
        wb.prepare(detail, {}, context, "ENST000001.1", "GRCh37")
    with pytest.raises(ValueError, match="transcript"):
        wb.prepare(detail, {}, context, "WRONG", "GRCh38")
    with pytest.raises(ValueError, match="gene and disease"):
        wb.prepare(detail, {}, {}, "ENST000001.1", "GRCh38")
    detail["alternate"] = "<DEL>"
    with pytest.raises(ValueError, match="Unsupported"):
        wb.prepare(detail, {}, context, "ENST000001.1", "GRCh38")


def test_reference_mismatch_and_missing_reference_do_not_claim_verification(workspace, monkeypatch):
    doc = workspace["document"]
    detail = copy.deepcopy(doc["original_vcf_evidence"])
    context = doc["normalized_evidence"]["snapshot"]["context"]
    detail["reference"] = "T"
    with pytest.raises(ValueError, match="REF does not match"):
        wb.prepare(detail, {}, context, "ENST000001.1", "GRCh38")
    monkeypatch.delenv("HELPER_ACMG_REFERENCE_CONFIG")
    prepared = wb.prepare(detail, {}, context, "ENST000001.1", "GRCh38")
    assert prepared["normalized_evidence"]["snapshot"]["variant"]["normalization"]["status"] == "UNVERIFIED"


def test_allele_specific_population_counts_and_spliceai_vector(workspace):
    doc = workspace["document"]
    detail = copy.deepcopy(doc["original_vcf_evidence"])
    a = detail["annotations"][0]
    a["metadata"]["fields"].update({"SpliceAI_pred_DS_AG": "0.12", "SpliceAI_pred_DS_AL": "0.2"})
    detail["metadata"]["original_vcf"].update({"alternates": ["C", "G"], "alt_index": 2,
        "info": {"gnomADg_AC": "2,1", "gnomADg_AN": "118595", "gnomADg_AF": "0.1,0.00001", "AC": "999,999"}})
    a["release_resources"] = {"info_definitions": {"gnomADg_AC": {"number": "A"}, "gnomADg_AN": {"number": "1"}, "gnomADg_AF": {"number": "A"}}}
    packet = wb.prepare(detail, {}, doc["normalized_evidence"]["snapshot"]["context"], "ENST000001.1", "GRCh38")["normalized_evidence"]
    evidence = packet["snapshot"]["evidence"]
    pop = next(e for e in evidence if e["kind"] == "POPULATION")
    assert pop["observation"]["aggregate"]["allele_count"] == 1
    assert pop["observation"]["aggregate"]["allele_number"] == 118595
    assert pop["observation"]["aggregate"]["allele_frequency"] == 0.00001
    splice = next(e for e in evidence if e["id"] == "imported-spliceai")["observation"]
    assert splice["spliceai"]["acceptor_gain"] == 0.12
    assert "maximum_delta" not in splice["spliceai"]
    assert "donor_gain" not in splice["spliceai"]


def profiles():
    return [{"profile_id": "baseline", "version": "1.0", "strategy": "CLINGEN_GUIDED", "release_status": "EXPERIMENTAL",
             "applicability": {"specificity": "NONE"}, "overridable_criteria": []},
            {"profile_id": "vcep", "version": "2.0", "strategy": "CLINGEN_GUIDED", "release_status": "EXPERIMENTAL",
             "applicability": {"specificity": "GENE_DISEASE"}}]


@pytest.mark.parametrize("ac", [0, 2])
def test_helper_gnomad_cache_counts_and_source_are_sent_unchanged(workspace, monkeypatch, ac):
    from helper_variants import gnomad_frequency
    detail = copy.deepcopy(workspace["document"]["original_vcf_evidence"])
    raw = gnomad_frequency._parse_response({"data": {
        "variant": {"genome": {"ac": ac, "an": 100000, "ac_hom": 0, "ac_hemi": 0,
            "filters": [], "populations": [{"id": "nfe", "ac": ac, "an": 50000}]}},
        "region": {"coverage": {"genome": [{"pos": 100, "mean": 31, "over_20": .94}]}},
    }}, gnomad_frequency.DATASETS["GRCh38"], ("GRCh38", "14", 100, "A", "G"), "https://gnomad.broadinstitute.org/")
    detail["gnomad_frequency"] = raw
    prepared = wb.prepare(detail, {}, workspace["document"]["normalized_evidence"]["snapshot"]["context"], "ENST000001.1", "GRCh38")
    packet = prepared["normalized_evidence"]
    pop = next(e for e in packet["snapshot"]["evidence"] if e["id"] == "helper-gnomad-genomes")
    obs = pop["observation"]
    assert obs["aggregate"]["allele_count"] == ac
    assert obs["aggregate"]["allele_frequency"] == ac / 100000
    assert obs["aggregate"]["allele_number"] == 100000
    assert obs["aggregate"]["callable"] is True
    assert obs["aggregate"]["coverage_fraction"] == .94
    assert obs["aggregate"]["mean_depth"] == 31.0
    assert obs["aggregate"]["quality_status"] == "PASS"
    assert obs["populations"][0]["allele_number"] == 50000
    assert obs["populations"][0]["allele_count"] == ac
    assert "callable" not in obs["populations"][0]
    assert "representation" not in obs["aggregate"]
    assert pop["provenance"]["source_identifier"] == "gnomAD"
    assert pop["provenance"]["source_version"] == "4.1"
    assert obs["dataset_id"] == "gnomad_r4" and obs["dataset_kind"] == "GENOME"
    source = next(s for s in packet["source_snapshots"] if s["source_id"] == "gnomAD")
    assert source["checksum"] == pop["provenance"]["artifact_digest"] == acmg_client.digest(raw)
    assert {"name": "gnomAD_genomes", "value": "4.1"} in packet["annotation_versions"]
    assert not any(m["path"] == "/snapshot/evidence/population" for m in packet["missing_evidence"])
    captured = []
    class PopulationEngine(FakeEngine):
        def call(self, path, payload):
            captured.append(copy.deepcopy(payload))
            return super().call(path, payload)
    monkeypatch.setattr(acmg, "ACMGClient", PopulationEngine)
    item = acmg_store.save("workspace", prepared)
    result = acmg.interpret(item["id"], acmg.ExecuteRequest(selections=selection()))
    assert captured[0]["packet"] == packet == result["document"]["packet"]
    detail["gnomad_frequency"]["ac"] = 999
    assert acmg_store.get(item["id"])["document"]["normalized_evidence"] == packet


@pytest.mark.parametrize("coverage", [None, {"pos": 100, "mean": 12, "over_20": .2}, {"pos": 100, "mean": 31, "over_20": .94}])
def test_cached_not_observed_state_keeps_unknown_counts_unknown(workspace, coverage):
    from helper_variants import gnomad_frequency
    detail = copy.deepcopy(workspace["document"]["original_vcf_evidence"])
    detail["gnomad_frequency"] = gnomad_frequency._parse_response({"data": {
        "variant": None, "region": {"coverage": {"genome": [coverage] if coverage else []}},
    }}, gnomad_frequency.DATASETS["GRCh38"], ("GRCh38", "14", 100, "A", "G"), "https://gnomad.broadinstitute.org/")
    raw = copy.deepcopy(detail["gnomad_frequency"])
    packet = wb.prepare(detail, {}, workspace["document"]["normalized_evidence"]["snapshot"]["context"], "ENST000001.1", "GRCh38")["normalized_evidence"]
    pop = next(e for e in packet["snapshot"]["evidence"] if e["id"] == "helper-gnomad-genomes")
    assert "allele_count" not in pop["observation"]["aggregate"]
    assert "allele_frequency" not in pop["observation"]["aggregate"]
    assert "allele_number" not in pop["observation"]["aggregate"]
    quality = {v["name"]: v["value"] for v in packet["quality_information"]}
    assert quality["HELPER_GNOMAD_STATUS"] == raw["status"]
    assert quality["HELPER_GNOMAD_ABSENCE_REPORTED"] == raw["population_absent"]
    assert any(m["path"].endswith("/counts") for m in packet["missing_evidence"])
    assert detail["gnomad_frequency"] == raw


def test_cached_population_for_another_allele_is_not_transmitted(workspace):
    detail = copy.deepcopy(workspace["document"]["original_vcf_evidence"])
    detail["gnomad_frequency"] = {"reference_build": "GRCh38", "chromosome": "14", "position": 100,
        "reference": "A", "alternate": "T", "status": "observed", "ac": 0, "an": 100000, "af": 0,
        "release": "4.1", "dataset": "gnomad_r4"}
    packet = wb.prepare(detail, {}, workspace["document"]["normalized_evidence"]["snapshot"]["context"], "ENST000001.1", "GRCh38")["normalized_evidence"]
    assert not any(e["kind"] == "POPULATION" for e in packet["snapshot"]["evidence"])
    assert any("different allele" in m["reason"] for m in packet["missing_evidence"])


def selection():
    return [{"profile_id": "baseline", "version": "1.0"}]


def test_explicit_profile_version_and_no_invented_strategy():
    config = acmg_client.configuration(profiles(), selection())
    assert config["strategy"] == "CLINGEN_GUIDED" and config["profile_usage"] == "RESEARCH"
    assert config["incomplete_evidence_policy"] == "REPORT_WITHOUT_CLASSIFICATION"
    with pytest.raises(ValueError):
        acmg_client.configuration(profiles(), [{"profile_id": "baseline", "version": "latest"}])
    config = acmg_client.configuration(profiles(), selection() + [{"profile_id": "vcep", "version": "2.0"}])
    assert config["specificity"] == "GENE_DISEASE"


class FakeEngine:
    def discover(self):
        return {"capabilities": {"research_execution_enabled": True, "strategies": [{"strategy": "CLINGEN_GUIDED", "status": "PARTIAL_RESEARCH"}]}}

    def profiles(self, context):
        return profiles()

    def call(self, path, payload):
        if path == "/v1/evidence-packets/interpret":
            return {"schema_version": "evidence-packet-result-v1", "result": scientific_result()}
        assert path == "/v1/interpretations/compare"
        assert "snapshot" in payload and "packet" not in payload
        return {"schema_version": "1.0", "branches": [], "comparisons": []}


def test_rerun_review_persistence_exports_and_immutable_results(workspace, monkeypatch):
    monkeypatch.setattr(acmg, "ACMGClient", FakeEngine)
    first = acmg.interpret(workspace["id"], acmg.ExecuteRequest(selections=selection()))
    saved = copy.deepcopy(first)
    review = acmg.review(first["id"], acmg.ReviewRequest(criterion="PM2", decision="CONTEST", comments="Inspect dependency", discrepancy="DEPENDENCY_ERROR"))
    second = acmg.interpret(workspace["id"], acmg.ExecuteRequest(selections=selection(), parent_id=first["id"]))
    assert acmg_store.get(first["id"]) == saved
    assert review["document"]["interpretation_id"] == first["id"]
    assert review["document"]["result_fingerprint"] == first["fingerprint"]
    diff = acmg.rerun_diff(second["id"], first["id"])
    assert len(diff["criteria"]) == 28
    assert json.loads(acmg.export(second["id"], "reviews").body) == []
    for fmt in ("engine", "table", "evidence", "report", "troubleshooting", "reviews", "rerun"):
        assert acmg.export(second["id"], fmt).status_code == 200
    with pytest.raises(HTTPException):
        acmg.export(second["id"], "comparison")
    with pytest.raises(HTTPException):
        acmg.review(first["id"], acmg.ReviewRequest(criterion="UNKNOWN", decision="CONFIRM", comments="x"))


def test_comparison_sends_identical_snapshot(workspace, monkeypatch):
    monkeypatch.setattr(acmg, "ACMGClient", FakeEngine)
    value = acmg.compare(workspace["id"], acmg.CompareRequest(selections=[selection(), selection() + [{"profile_id": "vcep", "version": "2.0"}]]))
    assert value["kind"] == "comparison"
    assert value["document"]["packet"] == workspace["document"]["normalized_evidence"]


def test_manual_correction_requires_explicit_provenance_and_leaves_original(workspace):
    original = copy.deepcopy(workspace["document"]["normalized_evidence"])
    item = copy.deepcopy(original["snapshot"]["evidence"][0])
    item["provenance"]["extraction_method"] = "MANUAL"
    item["observation"]["score"] = 0.8
    change = {"replaces": item["id"], "comment": "Source release corrected", "evidence": item, "source": original["source_snapshots"][0]}
    modified = wb.corrected_packet(original, [change])
    assert modified["snapshot"]["evidence"][0]["observation"]["score"] == 0.8
    assert original == workspace["document"]["normalized_evidence"]
    with pytest.raises(ValueError, match="threshold"):
        wb.corrected_packet(original, [dict(change, threshold=1)])
    change["evidence"]["provenance"]["source_version"] = None
    with pytest.raises(ValueError, match="versioned"):
        wb.corrected_packet(original, [change])


def test_unavailable_and_version_compatibility(monkeypatch):
    def fail(*args, **kwargs):
        raise URLError("unreachable")
    monkeypatch.setattr(acmg_client, "build_opener", lambda *args: type("Opener", (), {"open": fail})())
    with pytest.raises(acmg_client.EngineError) as error:
        acmg_client.ACMGClient().call("/health")
    assert error.value.code == "ENGINE_UNAVAILABLE"
    assert error.value.details["reason"] == "CONNECTION_FAILED"
    client = acmg_client.ACMGClient()
    monkeypatch.setattr(client, "call", lambda path: {"service": "acmg-engine", "status": "ok", "api_version": "v2", "schema_version": "1.0"})
    with pytest.raises(acmg_client.EngineError, match="v1"):
        client.discover()


@pytest.mark.parametrize("cause,reason", [
    (ConnectionRefusedError(), "CONNECTION_REFUSED"),
    (TimeoutError(), "TIMEOUT"),
    (URLError(TimeoutError()), "TIMEOUT"),
    (URLError(ConnectionRefusedError()), "CONNECTION_REFUSED"),
])
def test_connection_error_has_actionable_diagnostics(monkeypatch, cause, reason):
    monkeypatch.setenv("ACMG_ENGINE_URL", "http://127.0.0.1:8012")
    monkeypatch.setenv("ACMG_ENGINE_TIMEOUT", "3")
    def fail(*args, **kwargs):
        raise cause
    monkeypatch.setattr(acmg_client, "build_opener", lambda *args: type("Opener", (), {"open": fail})())
    with pytest.raises(acmg_client.EngineError) as error:
        acmg_client.ACMGClient().call("/health")
    assert error.value.status == 503
    assert error.value.details == {"engine_url": "http://127.0.0.1:8012", "reason": reason, "timeout_seconds": 3.0}
    assert "ACMG_ENGINE_URL" in str(error.value)
    assert "http://127.0.0.1:8012" in str(error.value)


def test_frontend_exposes_audit_and_review_controls():
    script = (Path(__file__).resolve().parents[1] / "src/helper_variants/web/static/acmg-workbench.js").read_text()
    for text in ("NOT_RECORDED", "population_upper_ci", "effective_strengths", "CONTEST", "REQUEST_REVIEW", "Compare Standard vs VCEP", "FIRST NOT_RECORDED"):
        assert text in script
