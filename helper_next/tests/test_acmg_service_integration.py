"""Opt-in real REST contract verification; no dependency on a running engine by default."""
import os
import json
from pathlib import Path

import pytest

from helper_next.core.acmg_client import ACMGClient, configuration
from helper_next.core.acmg_workbench import prepare
from helper_variants import gnomad_frequency


pytestmark = pytest.mark.skipif(os.environ.get("HELPER_TEST_ACMG_SERVICE") != "1", reason="Explicit local ACMG service test opt-in required")


@pytest.mark.parametrize("ac", [0, None])
def test_real_local_packet_profiles_and_comparison(tmp_path, monkeypatch, ac):
    client = ACMGClient()
    discovery = client.discover()
    assert discovery["capabilities"]["research_execution_enabled"]
    context = {"gene": {"namespace": "HGNC", "identifier": "HGNC:7577"},
               "disease": {"namespace": "MONDO", "identifier": "MONDO:0005045"}}
    profiles = client.profiles(context)
    generics = [p for p in profiles if p["applicability"]["specificity"] == "NONE"]
    assert len(generics) >= 2, "Load the documented TASK20 research profile fixtures"
    fasta = tmp_path / "synthetic.fa"
    fasta.write_text(">14\n" + "A" * 200 + "\n")
    Path(str(fasta) + ".fai").write_text("14\t200\t4\t200\t201\n")
    config = tmp_path / "reference.json"
    config.write_text(json.dumps({"GRCh38": {"fasta": str(fasta), "version": "synthetic-contract-reference-1"}}))
    monkeypatch.setenv("HELPER_ACMG_REFERENCE_CONFIG", str(config))
    detail = {"id": 1, "reference_build": "GRCh38", "chromosome": "14", "position": 100,
              "reference": "A", "alternate": "G", "metadata": {}, "calls": [],
              "annotations": [{"gene": "MYH7", "transcript": "ENST000001.1", "consequence": "missense_variant",
                               "hgvsc": "c.1A>G", "hgvsp": "p.Lys1Arg", "metadata": {"fields": {"REVEL": "0.73", "gnomAD_AF": "0.00001", "SpliceAI_pred_DS_AG": "0.1"}}}]}
    detail["gnomad_frequency"] = gnomad_frequency._parse_response({"data": {
        "variant": {"genome": {"ac": ac, "an": 100000, "filters": [], "populations": []}} if ac is not None else None,
        "region": {"coverage": {"genome": [{"pos": 100, "mean": 31, "over_20": .94}]}},
    }}, gnomad_frequency.DATASETS["GRCh38"], ("GRCh38", "14", 100, "A", "G"), "https://gnomad.broadinstitute.org/")
    packet = prepare(detail, {"source_id": "synthetic-contract-test"}, context, "ENST000001.1", "GRCh38")["normalized_evidence"]
    configs = [configuration(profiles, [{"profile_id": p["profile_id"], "version": p["version"]}]) for p in generics[:2]]
    outcome = client.call("/v1/evidence-packets/interpret", {"packet": packet, "configuration": configs[0]})
    assert len(outcome["result"]["criterion_results"]) == 28
    assert outcome["result"]["classification"]["status"] == "NOT_CLASSIFIED"
    imported = next(e for e in packet["snapshot"]["evidence"] if e["id"] == "helper-gnomad-genomes")
    assert imported["observation"]["aggregate"].get("allele_count") == ac
    assert any(s["source_id"] == "gnomAD" and s["version"] == "4.1" and s["checksum"] == imported["provenance"]["artifact_digest"] for s in outcome["source_versions"])
    comparison = client.call("/v1/interpretations/compare", {"snapshot": packet["snapshot"], "configurations": configs})
    assert len(comparison["branches"]) == 2
    assert all(b["execution_status"] == "SUCCEEDED" for b in comparison["branches"])


def test_real_myh7_method_discordance_from_engine_fixture():
    fixture = os.environ.get("HELPER_TEST_ACMG_BOUNDARY_REQUEST")
    if not fixture:
        pytest.skip("Provide an exported synthetic engine upper_request(ac=1, an=118595) fixture")
    result = ACMGClient().call("/v1/interpretations", json.loads(Path(fixture).read_text()))
    criterion = next(c for c in result["criterion_results"] if c["code"] == "PM2")
    assert criterion["status"] == "MANUAL_REVIEW_REQUIRED"
    assert criterion["reason_code"] == "METHOD_DISCORDANCE"
    assert criterion["strength"] is None
    assert "PM2" not in result["classification"]["included_criteria"]
    trace = criterion["population_upper_ci"][0]
    assert isinstance(trace["binomial_upper95"], str) and isinstance(trace["poisson_upper95"], str)
    assert trace["binomial_upper95"] != trace["poisson_upper95"]
    assert trace["primary_candidate_met"] and not trace["sensitivity_candidate_met"]
    assert trace["method_discordance"]
