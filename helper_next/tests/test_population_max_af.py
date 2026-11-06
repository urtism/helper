"""Current Priority uses the largest usable observed gnomAD/VEP frequency."""
from copy import deepcopy

import pytest

from helper_prioritization import DEFAULT_PROFILE, POPULATION_V2_PROFILE, score_variant
from helper_variants import gnomad_frequency as g, query
from test_population_frequency_v2 import maf, payload, product
from test_variant_query import query_store


@pytest.mark.parametrize("vep,gnomad,expected,points,source", [
    (0.02, 0.00001, 0.02, -10, "vep"),
    (0.00001, 0.02, 0.02, -10, "joint"),
    (None, 0.001, 0.001, 5, "joint"),
    (0, 0.0001, 0.0001, 15, "joint"),
    (0.0001, 0, 0.0001, 15, "vep"),
])
def test_largest_af_wins_without_replacing_it_with_faf(vep, gnomad, expected, points, source):
    data = payload({"joint": product(gnomad, 0.5)})
    before = deepcopy(data)
    component = maf(score_variant({"population_af": vep, "population_frequency_evidence": data}))
    assert component["observed_af"] == expected
    assert component["score"] == points
    assert component["observed_af_source"]["dataset"] == source
    assert data == before


def test_maximum_covers_joint_exomes_genomes_and_eligible_ancestry_groups():
    genome = product(0.002)
    genome["populations"] = [{"id": "afr", "ac": 10, "an": 1000, "af": 0.01}]
    data = payload({"joint": product(0.00001), "exomes": product(0.005), "genomes": genome})
    component = maf(score_variant({"population_af": 0.0001, "population_frequency_evidence": data}))
    assert component["observed_af"] == 0.01
    assert component["score"] == 0
    assert component["observed_af_source"]["dataset"] == "genomes"
    assert component["observed_af_source"]["population"] == "afr"


@pytest.mark.parametrize("location", ["variant_flags", "flags", "filters", "statistics", "discordant"])
@pytest.mark.parametrize("vep,expected,source", [(0.0001, 0.02, "joint"), (0.03, 0.03, "vep")])
def test_discrepant_frequencies_remain_usable_with_warning(location, vep, expected, source):
    data = payload({"joint": product(0.02)})
    if location == "variant_flags":
        data[location] = ["discrepant_frequencies"]
    elif location == "statistics":
        data["datasets"]["joint"]["freq_comparison_stats"] = {"stat_union": {"p_value": 1e-8}}
    elif location == "discordant":
        data["discordant"] = True
    else:
        data["datasets"]["joint"][location] = ["discrepant_frequencies"]
    before = deepcopy(data)
    component = maf(score_variant({"population_af": vep, "population_frequency_evidence": data}))
    assert component["score"] == -10 and component["evaluated"]
    assert component["observed_af"] == expected
    assert component["observed_af_source"]["dataset"] == source
    assert any("discrepan" in message.lower() for message in component["warnings"])
    assert data == before


@pytest.mark.parametrize("data", [{}, {"status": "unavailable", "error": "timeout"},
                                  payload({"joint": {"presence": "NOT_OBSERVED"}})])
def test_vep_observed_frequency_is_available_without_gnomad_absence_inference(data):
    component = maf(score_variant({"population_af": 0.02, "population_frequency_evidence": data}))
    assert component["score"] == -10
    assert component["observed_af_source"]["dataset"] == "vep"
    assert "gnomAD" not in next(line for line in component["evidence"] if line.startswith("AF "))
    assert maf(score_variant({"population_af": 0, "population_frequency_evidence": data}))["score"] == 0


def test_positive_vep_af_prevents_a_gnomad_absence_bonus():
    data = payload({"genomes": product(0, coverage={"over_20": 0.8})})
    component = maf(score_variant({"population_af": 0.02, "population_frequency_evidence": data}))
    assert component["frequency_status"] == "OBSERVED" and component["score"] == -10


def test_other_qc_flags_are_not_silently_ignored_or_rescued_by_vep():
    for data in (payload(variant_flags=["lcr"]), payload({"joint": product(0.01, filters=["RF"])}),
                 payload({"joint": product(0.01, filters=["discrepant_frequencies", "AC0"])})):
        component = maf(score_variant({"population_af": 0.00001, "population_frequency_evidence": data}))
        assert component["score"] == 0 and not component["evaluated"]


def test_query_connects_vep_summary_and_cached_gnomad_to_priority_and_display(tmp_path):
    database, sample, _ = query_store(tmp_path)
    allele = ("GRCh38", "1", 1, "A", "G")
    data = payload({"joint": product(0.02)}, variant_flags=["discrepant_frequencies"])
    data.update(reference_build="GRCh38", chromosome="1", position=1, reference="A", alternate="G", dataset="gnomad_r4")
    g._store(g.cache_path(), g.cache_key(*allele), data)
    item = query.list_variants(database, sample, variant_id=1)["items"][0]
    component = maf(item["priority"])
    assert component["vep_max_af"] == 0.001
    assert component["observed_af"] == item["population_af"] == 0.02
    assert component["score"] == -10
    historical = query.list_variants(database, sample, variant_id=1, scoring_version=POPULATION_V2_PROFILE["version"])["items"][0]
    assert maf(historical["priority"])["score"] == 0
    assert DEFAULT_PROFILE["version"] == item["priority"]["ruleset"]
