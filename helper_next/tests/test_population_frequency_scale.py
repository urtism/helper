"""Requested observed-AF scale, inclusive boundaries and default integration."""
import math
import socket

import pytest

from helper_prioritization import DEFAULT_PROFILE, LEGACY_PROFILE, RULESET_VERSION, get_profile, score_variant
from helper_variants import gnomad_frequency as g
from test_population_frequency_v2 import disease, maf, payload, product


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", lambda *a: pytest.fail("Unexpected network"))


def score(af, **extra):
    return score_variant({"population_frequency_evidence": payload({"joint": product(af, 0.1)}), **extra})


@pytest.mark.parametrize("upper,points,next_points", [
    (1e-6, 25, 20), (1e-5, 20, 15), (1e-4, 15, 10),
    (5e-4, 10, 5), (1e-3, 5, 0), (1e-2, 0, -10),
])
def test_each_upper_boundary_is_inclusive(upper, points, next_points):
    assert maf(score(math.nextafter(upper, 0)))["score"] == points
    exact = maf(score(upper))
    assert exact["score"] == points
    assert exact["evaluated"] is True
    assert maf(score(math.nextafter(upper, math.inf)))["score"] == next_points


def test_current_profile_uses_af_without_mcaf_or_faf_penalties():
    for context in (disease(1e-9), disease(0.1)):
        c = maf(score(0.0001, population_mcaf_context=context))
        assert c["score"] == 15
        assert c["scoring_mode"] == "observed_af"
        assert c["mcaf"] is None
        assert c["faf95"] == 0.1  # Informative only, never substituted for AF.
    assert maf(score(1))["score"] == -10
    assert RULESET_VERSION == DEFAULT_PROFILE["version"] == "germline-wes-v2.2.0"
    assert get_profile("germline-wes-v1.9.2")["maf"]["missing_af_score"] == 10
    assert get_profile("germline-wes-v2.0.0")["maf"]["generic_af_bands"][2] == (1e-4, 10)


@pytest.mark.parametrize("data", [{}, {"status": "unavailable", "error": "timeout"},
                                  payload({"joint": product(0.001, filters=["RF"])}),
                                  payload({"joint": dict(product(0.001), af=None)})])
def test_missing_unreliable_or_failed_lookup_is_zero_and_not_evaluable(data):
    result = score_variant({"population_frequency_evidence": data})
    c = maf(result)
    assert c["score"] == 0 and c["evaluated"] is False
    assert c["applicable"] is True and c["max_score"] == 25
    assert "Population frequency" in result["missing_evidence"]


def test_absence_requires_valid_site_evidence_and_keeps_normalization_weight():
    absent = payload({"genomes": product(0, coverage={"over_20": 0.8})})
    valid = score_variant({"population_frequency_evidence": absent})
    unknown = score_variant({})
    assert maf(valid)["score"] == 25
    assert maf(valid)["frequency_status"] == "NOT_OBSERVED_EVALUABLE"
    assert maf(score(0))["score"] == 0
    assert valid["max_score"] == unknown["max_score"]
    assert [c for c in valid["components"] if c["key"] != "maf"] == [c for c in unknown["components"] if c["key"] != "maf"]


def test_default_query_uses_maximum_vep_and_cached_gnomad_af(tmp_path):
    from helper_variants import query
    from test_variant_query import query_store
    path, sample_id, _ = query_store(tmp_path)
    allele = ("GRCh38", "1", 1, "A", "G")
    data = payload({"joint": product(0.0001, 0.1)})
    data.update(reference_build="GRCh38", chromosome="1", position=1, reference="A", alternate="G", dataset="gnomad_r4")
    g._store(g.cache_path(), g.cache_key(*allele), data)
    item = query.list_variants(path, sample_id, variant_id=1)["items"][0]
    assert item["priority"]["ruleset"] == RULESET_VERSION
    assert maf(item["priority"])["score"] == 5
    assert maf(item["priority"])["observed_af"] == 0.001
    assert maf(item["priority"])["observed_af_source"]["dataset"] == "vep"


def test_other_components_match_legacy_and_unavailable_population_keeps_maximum():
    variant = {"consequence": "missense_variant", "clinical_significance": "Pathogenic", "clinvar_stars": 3}
    new = score_variant(variant)
    old = score_variant(variant, LEGACY_PROFILE)
    assert new["max_score"] == old["max_score"]
    assert [c for c in new["components"] if c["key"] != "maf"] == [c for c in old["components"] if c["key"] != "maf"]
