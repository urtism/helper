"""Offline policy and regression checks; not scientific validation."""
from copy import deepcopy
import json
import math
from pathlib import Path
import socket

import pytest

from helper_prioritization import (
    DEFAULT_PROFILE, LEGACY_PROFILE, POPULATION_V2_PROFILE, apply_clinvar_evidence, get_profile, score_variant,
)
from helper_variants import gnomad_frequency as g


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", lambda *a: pytest.fail("Unexpected network"))


def disease(mcaf=0.001, disease_id="MONDO:1"):
    return {"gene": "GENE1", "disease_id": disease_id, "mode_of_inheritance": "AD",
            "mcaf": mcaf, "source": "synthetic-reviewed-MCAF", "version": "test-1",
            "validated": True, "parameters": {"note": "synthetic, not a real clinical MCAF"}}


def product(af=1e-5, faf=None, an=1000000, **extra):
    ac = round(af * an) if af is not None and an is not None and math.isfinite(af) else None
    return {"presence": "PRESENT", "ac": ac, "an": an, "af": af,
            "filters": [], "flags": [], "coverage": {}, "populations": [],
            "grpmax_faf95": faf, "grpmax_faf95_population": "nfe" if faf is not None else None,
            **extra}


def payload(datasets=None, **extra):
    return {"status": "observed", "retrieval_status": "FOUND", "release": g.FREQUENCY_RELEASE,
            "parser_version": g.PARSER_VERSION, "datasets": datasets or {"joint": product()}, **extra}


def run(data=None, context=True, profile=None, **variant):
    inputs = {"gene": "GENE1", "population_frequency_evidence": data if data is not None else payload()}
    if context:
        inputs["population_mcaf_context"] = disease() if context is True else context
    inputs.update(variant)
    return score_variant(inputs, profile or POPULATION_V2_PROFILE)


def maf(result):
    return next(c for c in result["components"] if c["key"] == "maf")


@pytest.mark.parametrize("af,faf,expected", [
    (1e-6, 0, 25), (1e-5, 0, 25), (0.000011, 0, 20),
    (0.0001, 0, 20), (0.000101, 0, 10), (0.0005, 0, 10),
    (0.000501, 0, 5), (0.001, 0, 5), (0.001001, 0, 0),
    (0.002, 0.001, 0), (0.002, 0.001001, -15),
    (0.01, 0.005, -15), (0.01, 0.005001, -25),
    (0.000001, 0.005001, -25),  # FAF precedence; groups need not match global AF.
    (0.00001, None, 25), (0.002, None, 0),
])
def test_context_aware_boundaries_and_faf_precedence(af, faf, expected):
    c = maf(run(payload({"joint": product(af, faf)})))
    assert c["score"] == expected
    assert c["observed_af"] == af and c["faf95"] == faf
    assert c["scoring_mode"] == "context_aware"
    if faf is None:
        assert any("FAF95 unavailable" in warning for warning in c["warnings"])


@pytest.mark.parametrize("af,expected", [(1e-6,25),(1e-5,20),(1e-4,10),(1e-3,5),(0.01,0),(0.2,0)])
def test_generic_monotone_bins_have_no_disease_penalties(af, expected):
    c = maf(run(payload({"joint": product(af, 0.1)}), context=False))
    assert c["score"] == expected
    assert c["mcaf"] is None and c["scoring_mode"] == "context_agnostic"


@pytest.mark.parametrize("data,status", [
    ({}, "NOT_FOUND_UNVERIFIED"),
    (payload(status="not_observed_coverage_unknown", datasets={"genomes": {"presence": "NOT_OBSERVED"}}), "NOT_FOUND_UNVERIFIED"),
    ({"status": "unsupported"}, "UNSUPPORTED"),
    ({"status": "unavailable", "error": "timeout"}, "ERROR"),
    (payload(parser_version="old"), "UNRELIABLE"),
    (payload(release="4.0"), "UNRELIABLE"),
    (payload(partial=True), "UNRELIABLE"),
    (payload(variant_flags=["lcr"]), "UNRELIABLE"),
])
def test_unusable_evidence_is_neutral_and_stays_in_denominator(data, status):
    result = run(data)
    c = maf(result)
    assert (c["score"], c["frequency_status"], c["evaluated"], c["applicable"]) == (0, status, False, True)
    assert "Population frequency" in result["missing_evidence"]
    assert result["max_score"] >= 25


@pytest.mark.parametrize("extra", [
    {"af": None}, {"af": float("nan")}, {"af": float("inf")}, {"af": -1},
    {"af": 2}, {"an": 0}, {"an": None}, {"an": 0.5}, {"ac": 0},
    {"filters": ["RF"]}, {"filters": None}, {"flags": ["lcr"]},
    {"grpmax_faf95": float("nan")}, {"coverage": {"available": True, "adequate": False}},
])
def test_invalid_metrics_and_quality(extra):
    assert maf(run(payload({"joint": product(**extra)})))["score"] == 0


def test_absence_requires_site_an_callability_pass_and_no_other_observation():
    zero = product(0, coverage={"available": True, "adequate": True, "mean": 25, "over_20": 0.8})
    c = maf(run(payload({"genomes": zero})))
    assert c["score"] == 25 and c["frequency_status"] == "NOT_OBSERVED_EVALUABLE"
    for change in ({"an": 100}, {"coverage": {"mean": 100}}, {"coverage": {}},
                   {"filters": None}, {"presence": "NOT_OBSERVED"}, {"grpmax_faf95": 1e-5}):
        assert maf(run(payload({"genomes": dict(zero, **change)})))["score"] == 0
    data = payload({"joint": zero, "exomes": product(0.01)})
    c = maf(run(data))
    assert c["score"] == 0 and c["quality_status"] == "DISCORDANT"
    # The legacy boolean absence/coverage shortcut is insufficient in v2.
    assert maf(run({}, population_absent=True, population_coverage_adequate=True))["score"] == 0


def test_joint_preferred_and_fallback_uses_highest_af_with_independent_faf_source():
    datasets = {"joint": product(1e-5, 0), "exomes": product(0.0001, 0.00005),
                "genomes": product(0.0005, 0.00001)}
    c = maf(run(payload(datasets)))
    assert c["observed_af_source"]["dataset"] == "joint"
    assert c["faf95_source"]["dataset"] == "joint"
    datasets["joint"]["filters"] = ["RF"]
    c = maf(run(payload(datasets)))
    assert c["observed_af"] == 0.0005
    assert c["observed_af_source"]["dataset"] == "genomes"
    assert c["faf95_source"]["dataset"] == "exomes"
    assert c["faf95"] == 0.00005


@pytest.mark.parametrize("name", ["exomes", "genomes"])
def test_single_observed_dataset(name):
    c = maf(run(payload({name: product(1e-5)})))
    assert c["score"] == 25 and c["observed_af_source"]["dataset"] == name


@pytest.mark.parametrize("extra", [
    {"discordant": True},
    {"freq_comparison_stats": {"stat_union": {"p_value": 0.0001}}},
])
def test_discordance_is_uncertainty_not_independent_penalties(extra):
    c = maf(run(payload({"joint": product(**extra)})))
    assert c["score"] == 0 and c["quality_status"] == "DISCORDANT"


@pytest.mark.parametrize("profile", [POPULATION_V2_PROFILE, DEFAULT_PROFILE], ids=["v2.0", "default"])
@pytest.mark.parametrize("name", ["stat_union", "contingency_table_test", "cochran_mantel_haenszel_test"])
@pytest.mark.parametrize("tests,discordant", [
    ({"p_value": 0.0001}, True),
    ([{"p_value": 0.5}, {"p_value": 0.0001}], True),
    ([None, {"p_value": None}, {"p_value": 0.0001}], True),
    ({"p_value": 0.001}, False),
    ([{"p_value": 0.001}, {"p_value": 0.5}], False),
    ([], False), (None, False), ([None, {}, "invalid"], False),
])
def test_discordance_statistics_accept_dict_list_and_null(profile, name, tests, discordant):
    data = payload({"joint": product(freq_comparison_stats={name: tests})})
    before = deepcopy(data)
    c = maf(run(data, profile=profile))
    assert data == before
    if discordant and profile is POPULATION_V2_PROFILE:
        assert (c["score"], c["quality_status"], c["evaluated"]) == (0, "DISCORDANT", False)
    else:
        assert c["score"] > 0 and c["quality_status"] == "PASS"
        if discordant:
            assert any("discrepan" in message.lower() for message in c["warnings"])


@pytest.mark.parametrize("profile", [POPULATION_V2_PROFILE, DEFAULT_PROFILE], ids=["v2.0", "default"])
def test_official_comparison_statistics_from_existing_cache_do_not_crash(tmp_path, profile):
    fixture = json.loads((Path(__file__).parent / "fixtures/gnomad_v4/frequency_4.1.1.json").read_text())
    allele = ("GRCh38", "1", 55039974, "G", "T")
    data = g._parse_response({"data": {"variant": fixture["data"]["v0_all"]}},
                             g.DATASETS["GRCh38"], allele, "")
    stats = data["datasets"]["joint"]["freq_comparison_stats"]
    assert isinstance(stats["contingency_table_test"], list)
    assert isinstance(stats["stat_union"], dict)
    database = tmp_path / "frequencies.sqlite3"
    g._store(database, g.cache_key(*allele), data)
    before = database.read_bytes()
    context = g.cached_contexts([allele], database, scoring_version=profile["version"])[0]
    c = maf(score_variant(context, profile))
    if profile is POPULATION_V2_PROFILE:
        assert (c["score"], c["quality_status"]) == (0, "DISCORDANT")
    else:
        assert c["evaluated"] and c["quality_status"] == "PASS"
        assert any("discrepan" in message.lower() for message in c["warnings"])
    assert database.read_bytes() == before


@pytest.mark.parametrize("population", ["nfe", "asj", "fin", "ami"])
def test_higher_population_af_including_founders_prevents_dilution(population):
    row = product(0.0001, populations=[dict(product(0.01, an=1000), id=population)])
    c = maf(run(payload({"joint": row})))
    assert c["observed_af"] == 0.01 and c["score"] == 0
    assert c["observed_af_source"]["population"] == population
    row["populations"] = [dict(product(0.1, an=100), id=population)]
    assert maf(run(payload({"joint": row})))["frequency_status"] == "UNRELIABLE"


def test_mandatory_fixture_parser_to_old_and_new_scoring():
    fixture = json.loads((Path(__file__).parent / "fixtures/gnomad_v4/priority_01_required.json").read_text())
    data = g._parse_response(fixture["response"], g.DATASETS["GRCh38"], fixture["allele"], "")
    assert maf(score_variant(g.priority_context(data), LEGACY_PROFILE))["score"] == fixture["expected_v1"] == 10
    generic = maf(score_variant(g.priority_context(data, scoring_version=POPULATION_V2_PROFILE["version"]), POPULATION_V2_PROFILE))
    aware = maf(run(data))
    assert generic["score"] == fixture["expected_v2_generic"] == 20
    assert aware["score"] == fixture["expected_v2_context_mcaf_0_001"] == 25
    assert generic["observed_af"] == 4/1480618
    assert generic["faf95"] == 6e-6
    assert data["datasets"]["genomes"]["filter"] is None
    assert data["datasets"]["genomes"]["an"] is None


def test_explicit_disease_contexts_produce_distinct_scores_without_best_selection():
    data = payload({"joint": product(0.0001, 0.00005)})
    assert maf(run(data, disease(0.001, "MONDO:1")))["score"] == 20
    assert maf(run(data, disease(0.000001, "MONDO:2")))["score"] == -25
    c = maf(run(data, [disease(), disease(0.000001)]))
    assert c["scoring_mode"] == "context_agnostic" and c["mcaf"] is None


@pytest.mark.parametrize("change", [{"validated": False}, {"source": None}, {"version": None},
                                    {"gene": "OTHER"}, {"mcaf": 0}, {"mcaf": math.nan}])
def test_incomplete_or_wrong_gene_context_does_not_use_free_mcaf_or_vcep(change):
    c = maf(run(context=dict(disease(), **change), max_credible_af=1e-10, ba1_af=1e-10))
    assert c["mcaf"] is None and c["scoring_mode"] == "context_agnostic"
    assert c["score"] == 20


def test_mcaf_extremes_are_ratio_based_without_old_absolute_thresholds():
    assert maf(run(payload({"joint": product(1e-6, 2e-7)}), disease(1e-9)))["score"] == -25
    assert maf(run(payload({"joint": product(0.06, 0.05)}), disease(0.1)))["score"] == 5
    assert maf(run(context=disease("0.001")))["mcaf"] == 0.001


def test_neutral_population_does_not_change_other_components_or_denominator():
    data = payload({"joint": product(1e-5)})
    good = run(data, consequence="frameshift_variant", disease_mechanisms=["loss of function"])
    missing = run({}, consequence="frameshift_variant", disease_mechanisms=["loss of function"])
    assert good["max_score"] == missing["max_score"]
    assert good["score"] - missing["score"] == 25
    assert missing["normalized_score"] == round(100 * missing["score"] / missing["max_score"])
    assert [c for c in good["components"] if c["key"] != "maf"] == [c for c in missing["components"] if c["key"] != "maf"]
    zero = maf(run(payload({"joint": product(0.01, 0.001)})))
    assert zero["evaluated"] and zero["evaluation_status"] == "evaluated"
    assert not maf(missing)["evaluated"]
    assert any(not c["applicable"] for c in missing["components"])


def test_version_preserved_on_clinvar_update_and_inputs_not_mutated():
    data = payload()
    before = deepcopy(data)
    first = run(data)
    assert run(data) == first and data == before
    json.dumps(first, allow_nan=False)
    assert "datasets" not in json.dumps(first)
    updated = apply_clinvar_evidence(first, {})
    assert updated["ruleset"] == POPULATION_V2_PROFILE["version"]
    assert maf(updated) == maf(first)
    with pytest.raises(ValueError, match="mix Priority"):
        apply_clinvar_evidence(first, {}, DEFAULT_PROFILE)
    copied = get_profile(POPULATION_V2_PROFILE["version"])
    copied["maf"]["rare_ratios"] = ((1, 3),)
    assert maf(run(profile=copied))["score"] == 3
    assert LEGACY_PROFILE["version"] == "germline-wes-v1.9.2"
    assert maf(score_variant({}, LEGACY_PROFILE))["score"] == 10


def test_versioned_query_ranking_cache_and_browser_contract(tmp_path, monkeypatch):
    from helper_variants import query
    from test_variant_query import query_store
    path, sample_id, _ = query_store(tmp_path)
    data = payload({"joint": product(0.00001, 0), "genomes": {"presence": "NOT_OBSERVED", "filters": None}})

    def contexts(alleles, **kwargs):
        return [g.priority_context(data, scoring_version=kwargs.get("scoring_version")) for _ in alleles]

    monkeypatch.setattr(g, "cached_contexts", contexts)
    first = query.list_variants(path, sample_id, limit=2)
    second = query.list_variants(path, sample_id, limit=2, scoring_version=POPULATION_V2_PROFILE["version"])
    assert first["items"][0]["priority"]["ruleset"] == DEFAULT_PROFILE["version"]
    assert all(item["priority"]["ruleset"] == POPULATION_V2_PROFILE["version"] for item in second["items"])
    assert all(maf(item["priority"])["observed_af_source"]["dataset"] == "joint" for item in second["items"])
    assert first["next_cursor"] != second["next_cursor"]
    with pytest.raises(query.VariantQueryError):
        query.list_variants(path, sample_id, cursor=first["next_cursor"], scoring_version=POPULATION_V2_PROFILE["version"])
    with pytest.raises(query.VariantQueryError, match="scoring version"):
        query.list_variants(path, sample_id, scoring_version="not-a-profile")


@pytest.mark.parametrize("inputs,expected", [
    ({}, 10), ({"population_af": 1e-6}, 25), ({"population_af": 0.0001}, 20),
    ({"population_af": 0.0005}, 15), ({"population_af": 0.001}, 10),
    ({"population_af": 0.005}, 0), ({"population_af": 0.005001}, -15),
    ({"population_af": 0.05}, -25),
    ({"population_af": 0.000001, "population_faf": 0.0008}, 10),
    ({"population_absent": True, "population_coverage_adequate": True}, 25),
])
def test_legacy_golden_population_results(inputs, expected):
    assert maf(score_variant(inputs, LEGACY_PROFILE))["score"] == expected
    assert score_variant(inputs, LEGACY_PROFILE) == score_variant(inputs, get_profile("germline-wes-v1.9.2"))


def test_site_an_callability_and_population_thresholds_are_configurable():
    config = get_profile(POPULATION_V2_PROFILE["version"])
    config["maf"]["reliability"]["minimum_observed_an"] = 2000000
    assert maf(run(profile=config))["score"] == 0
    config["maf"]["reliability"]["minimum_observed_an"] = 1
    zero = payload({"exomes": product(0, an=100, coverage={"over_20": 0.7})})
    assert maf(run(zero, profile=config))["score"] == 0
    config["maf"]["reliability"].update(minimum_absence_an=100, minimum_absence_callability=0.7)
    assert maf(run(zero, profile=config))["score"] == 25


def test_v2_reads_existing_cache_without_writes_or_reusing_a_score(tmp_path):
    allele = ("GRCh38", "1", 1000, "A", "G")
    fixture = json.loads((Path(__file__).parent / "fixtures/gnomad_v4/priority_01_required.json").read_text())
    data = g._parse_response(fixture["response"], g.DATASETS["GRCh38"], allele, "")
    db = tmp_path / "frequencies.sqlite3"
    g._store(db, g.cache_key(*allele), data)
    before = db.read_bytes()
    old = g.cached_contexts([allele], db)[0]
    new = g.cached_contexts([allele], db, scoring_version=POPULATION_V2_PROFILE["version"])[0]
    assert maf(score_variant(old, LEGACY_PROFILE))["score"] == 10
    assert maf(score_variant(new, POPULATION_V2_PROFILE))["score"] == 20
    assert db.read_bytes() == before
    data["parser_version"] = "obsolete"
    g._store(db, g.cache_key(*allele), data)
    missing = g.cached_contexts([allele], db, scoring_version=POPULATION_V2_PROFILE["version"])[0]
    assert missing == {}
    assert maf(score_variant(missing, POPULATION_V2_PROFILE))["score"] == 0
    data["parser_version"] = g.PARSER_VERSION
    data["alternate"] = "T"
    g._store(db, g.cache_key(*allele), data)
    assert g.cached_contexts([allele], db, scoring_version=POPULATION_V2_PROFILE["version"]) == [{}]


@pytest.mark.parametrize("variant", [{"alternate": "<DEL>"}, {"alternate": "*"},
                                    {"chromosome": "MT"}, {"chromosome": "chrUn"}])
def test_unsupported_alleles_do_not_become_unverified_absence(variant):
    c = maf(run({}, **variant))
    assert c["score"] == 0 and c["frequency_status"] == "UNSUPPORTED"


def test_offline_benchmark_preserves_vus_and_requires_known_causal_labels():
    import importlib.util
    spec = importlib.util.spec_from_file_location("priority_benchmark", Path(__file__).parents[2] / "scripts/benchmark_population_frequency_v2.py")
    benchmark = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(benchmark)
    records = benchmark.synthetic_records()
    originals = deepcopy(records)
    report = benchmark.compare(records)
    assert records == originals
    assert report["summary"]["causal_ranking"]["v2"]["top_k"]["1"] is None
    assert report["summary"]["denominator_changes"] == 0
    assert report["summary"]["positive_to_neutral_or_negative"] == 3
    records[0].update(classification="VUS", causal=None)
    records[3].update(classification="P", causal=True)
    report = benchmark.compare(records)
    assert report["summary"]["causal_ranking"]["v2"]["top_k"]["1"] == 1
    assert "VUS" in report["summary"]["by_reviewed_classification"]
    assert len(report["rows"]) == 5


def test_api_version_is_explicit_and_detail_keeps_the_same_population_component(tmp_path, monkeypatch):
    from helper_next.api import variants
    from helper_next.core import biological_identity
    from helper_next.core.acmg_sources import SourceManager
    from test_variants_api import local_index
    sample = local_index(tmp_path, monkeypatch, "Likely benign")
    monkeypatch.setattr(biological_identity, "allele_refs", lambda *a, **kw: [{"status": "UNSUPPORTED"}])
    monkeypatch.setattr(SourceManager, "vcep_batch", lambda *a, **kw: [{}])
    monkeypatch.setattr(variants.acmg_context, "build", lambda *a, **kw: {})
    default = variants.sample_variants("RUN", sample, limit=100)
    assert default["items"][0]["priority"]["ruleset"] == DEFAULT_PROFILE["version"]
    version = POPULATION_V2_PROFILE["version"]
    page = variants.sample_variants("RUN", sample, limit=100, scoring_version=version)
    item = next(item for item in page["items"] if item["variant_id"] == 1)
    detail = variants.sample_variant_detail("RUN", sample, 1, scoring_version=version)
    assert item["priority"]["ruleset"] == detail["priority"]["ruleset"] == version
    assert maf(item["priority"]) == maf(detail["priority"])
    assert maf(item["priority"])["score"] == 0  # Unqualified VCF AF is not gnomAD evidence.
