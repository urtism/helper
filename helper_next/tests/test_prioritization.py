import pytest

from helper_prioritization import RULESET_VERSION, apply_clinvar_evidence, score_variant


def component(result, key):
    return next(item for item in result["components"] if item["key"] == key)


def test_scores_strong_lof_case_and_explains_exact_sum():
    result = score_variant({
        "population_af": 0.00001,
        "max_credible_af": 0.001,
        "consequence": "frameshift_variant",
        "disease_mechanisms": ["loss of function"],
        "mechanism_confidence": ["definitive"],
        "clinical_significance": "Pathogenic",
        "clinvar_stars": 3,
        "clinvar_condition_match": "exact",
        "inheritance_modes": ["Autosomal recessive"],
        "zygosities": ["hom_alt"],
        "filter_status": ["PASS"],
        "depth": 30,
        "quality": 50,
    })

    assert result["ruleset"] == RULESET_VERSION
    assert result["score"] == 85
    assert result["max_score"] == 85
    assert result["normalized_score"] == 100
    assert result["band"] == "P1"
    assert result["formula"] == "25 + 25 + 20 + 15 = 85 / 85"
    assert component(result, "prediction")["applicable"] is False
    assert result["call_confidence"]["status"] == "high"


@pytest.mark.parametrize(
    "consequence, expected_mechanism_score",
    [("frameshift_variant", 25), ("start_lost", 20)],
)
def test_compatible_lof_keeps_mechanism_and_inheritance_points_across_contexts(
    consequence, expected_mechanism_score
):
    result = score_variant({
        "consequence": consequence,
        "disease_mechanisms": ["loss of function", "gain of function"],
        "mechanism_confidence": ["definitive"],
        "gene_context_ambiguous": True,
        "inheritance_modes": ["Autosomal dominant"],
        "zygosities": ["het"],
    })

    assert component(result, "mechanism")["score"] == expected_mechanism_score
    assert component(result, "inheritance")["score"] == 10
    assert "confidence is reduced" not in component(result, "mechanism")["reason"]


@pytest.mark.parametrize(
    "de_novo_status, expected_score",
    [("", 10), ("confirmed", 10)],
)
def test_ad_context_uses_max_standard_inheritance_score_without_ambiguity_penalty(
    de_novo_status, expected_score
):
    result = score_variant({
        "gene_context_ambiguous": True,
        "inheritance_modes": ["Autosomal dominant", "Autosomal recessive"],
        "zygosities": ["het"],
        "de_novo_status": de_novo_status,
    })

    inheritance = component(result, "inheritance")
    assert inheritance["score"] == expected_score
    assert "Multiple gene-disease contexts reduce confidence" not in inheritance["reason"]


@pytest.mark.parametrize(
    "unrelated_count, sample_count, expected_score",
    [(1, 1, 15), (1, 2, 10), (2, 2, 0), (3, 3, -10)],
)
def test_run_occurrence_priority_uses_singleton_and_recurrence_rules(
    unrelated_count, sample_count, expected_score
):
    result = score_variant({
        "unrelated_subject_count": unrelated_count,
        "sample_carrier_count": sample_count,
    })

    assert component(result, "run_occurrence")["score"] == expected_score
    assert component(result, "run_occurrence")["max_score"] == 15


def test_missing_evidence_is_not_silently_treated_as_negative():
    result = score_variant({"consequence": "missense_variant"})

    assert "Population frequency" not in result["missing_evidence"]
    assert "ClinVar" in result["missing_evidence"]
    assert "Zygosity × inheritance" in result["missing_evidence"]
    assert component(result, "maf")["score"] == 10
    assert component(result, "maf")["evaluated"] is True
    assert component(result, "run_occurrence")["applicable"] is False


@pytest.mark.parametrize(
    "coverage_available, coverage_adequate, expected_score, expected_text",
    [
        (True, False, 10, "coverage is inadequate"),
        (False, False, 10, "coverage are unavailable"),
        (True, True, 10, "despite adequate locus coverage"),
    ],
)
def test_missing_population_af_keeps_positive_score_when_absence_is_unverified(
    coverage_available, coverage_adequate, expected_score, expected_text
):
    maf = component(score_variant({
        "population_coverage_available": coverage_available,
        "population_coverage_adequate": coverage_adequate,
        "population_frequency_source": "gnomAD genomes v4.1",
    }), "maf")

    assert maf["score"] == expected_score
    assert maf["evaluated"] is True
    assert expected_text in maf["reason"]


@pytest.mark.parametrize(
    "significance, conflict_classifications, expected_score, expected_reason",
    [
        ("Pathogenic", ["Pathogenic(2)", "Uncertain_significance(1)"], 15, "P/LP and VUS"),
        ("Likely_pathogenic", ["Likely_pathogenic(2)", "VUS(1)"], 15, "P/LP and VUS"),
        ("Benign", ["Benign(2)", "Uncertain_significance(1)"], -15, "B/LB and VUS"),
        ("Likely_benign", ["Likely_benign(2)", "VUS(1)"], -15, "B/LB and VUS"),
    ],
)
def test_clinvar_pathogenic_or_benign_vs_vus_conflict_keeps_reduced_directional_score(
    significance, conflict_classifications, expected_score, expected_reason
):
    clinvar = component(score_variant({
        "clinical_significance": significance,
        "clinvar_conflict": True,
        "clinvar_conflict_classifications": conflict_classifications,
        "clinvar_stars": 2,
        "clinvar_condition_match": "exact",
    }), "clinvar")

    assert clinvar["score"] == expected_score
    assert expected_reason in clinvar["reason"]


def test_clinvar_pathogenic_benign_conflict_receives_zero_points():
    clinvar = component(score_variant({
        "clinical_significance": "Pathogenic",
        "clinvar_conflict": True,
        "clinvar_conflict_classifications": ["Pathogenic(2)", "Benign(1)"],
        "clinvar_stars": 3,
    }), "clinvar")

    assert clinvar["score"] == 0
    assert "both pathogenic and benign" in clinvar["reason"]


@pytest.mark.parametrize("classification", ["Pathogenic", "Likely pathogenic", "Pathogenic/Likely pathogenic", "P/LP"])
@pytest.mark.parametrize("stars, expected", [(0, 10), (1, 15), (2, 20), (3, 20), (4, 20)])
def test_detail_clinvar_pathogenic_score_depends_only_on_review_strength(classification, stars, expected):
    result = apply_clinvar_evidence(score_variant({}), {
        "classifications": [classification],
        "review_statuses": [{"label": "germline review", "stars": stars}],
    })

    assert component(result, "clinvar")["score"] == expected
    assert "ClinVar condition match" not in result["missing_evidence"]


@pytest.mark.parametrize("stars, expected", [(0, 7.5), (1, 11.2), (2, 15), (3, 15), (4, 15)])
def test_detail_clinvar_submission_breakdown_resolves_plp_vus_conflict(stars, expected):
    result = apply_clinvar_evidence(score_variant({}), {
        "classifications": ["Conflicting classifications of pathogenicity"],
        "classification_breakdown": [
            {"label": "Likely pathogenic", "count": 2},
            {"label": "Uncertain significance", "count": 10},
        ],
        "review_statuses": [{"label": "germline review", "stars": stars}],
    })

    assert component(result, "clinvar")["score"] == expected
    assert "P/LP and VUS" in component(result, "clinvar")["reason"]


@pytest.mark.parametrize("extra_classifications", [[], ["Uncertain significance"]])
def test_detail_clinvar_plp_blb_conflict_is_neutral(extra_classifications):
    result = apply_clinvar_evidence(score_variant({}), {
        "classifications": ["Conflicting classifications of pathogenicity"],
        "classification_breakdown": [
            {"label": label, "count": 1}
            for label in ["Pathogenic", "Likely benign"] + extra_classifications
        ],
        "review_statuses": [{"label": "germline review", "stars": 4}],
    })

    assert component(result, "clinvar")["score"] == 0
    assert component(result, "clinvar")["evaluated"] is True


@pytest.mark.parametrize("evidence, evaluated", [
    ({"classifications": ["Conflicting classifications of pathogenicity"]}, True),
    ({"classifications": ["Uncertain significance"]}, True),
    ({"retrieval_status": "unavailable"}, False),
    ({"retrieval_status": "not_found"}, False),
])
def test_unresolved_or_missing_clinvar_never_retains_old_positive_points(evidence, evaluated):
    previous = score_variant({"clinical_significance": "Pathogenic", "clinvar_stars": 4})
    updated = apply_clinvar_evidence(previous, evidence)

    assert component(previous, "clinvar")["score"] == 20
    assert component(updated, "clinvar")["score"] == 0
    assert component(updated, "clinvar")["evaluated"] is evaluated
    assert updated["score"] == previous["score"] - 20
    assert updated["max_score"] == previous["max_score"]


def test_splice_and_missense_predictors_use_calibrated_rules():
    splice = score_variant({
        "consequence": "splice_region_variant",
        "prediction_fields": {"SpliceAI_pred_DS_AG": "0.67"},
    })
    missense = score_variant({
        "consequence": "missense_variant", "prediction_fields": {"REVEL": "0.80"},
    })

    assert component(splice, "prediction")["score"] == 10
    assert component(missense, "prediction")["score"] == 8


def test_compound_candidate_is_weighted_only_with_recessive_context():
    result = score_variant({
        "consequence": "missense_variant",
        "inheritance_modes": ["biallelic_autosomal"],
        "zygosities": ["het"],
        "compound_status": "phase_unknown",
    })

    assert component(result, "inheritance")["score"] == 9
    assert "phase is unknown" in component(result, "inheritance")["reason"]


@pytest.mark.parametrize(
    "zygosities, compound_status",
    [(["hom_alt"], ""), (["het"], "confirmed_in_trans")],
)
def test_confirmed_recessive_genotypes_receive_full_zygosity_points(
    zygosities, compound_status
):
    result = score_variant({
        "inheritance_modes": ["Autosomal recessive"],
        "zygosities": zygosities,
        "compound_status": compound_status,
    })

    inheritance = component(result, "inheritance")
    assert inheritance["score"] == 15
    assert inheritance["max_score"] == 15


def test_sex_linked_modes_are_not_collapsed_to_dominant_or_recessive():
    x_linked = score_variant({
        "inheritance_modes": ["X-linked recessive"], "zygosities": ["hemizygous"],
    })
    y_linked = score_variant({
        "inheritance_modes": ["Y-linked"], "zygosities": ["hemizygous"],
        "chromosome": "chrY",
    })

    assert component(x_linked, "inheritance")["score"] == 13
    assert component(y_linked, "inheritance")["score"] == 13


def test_common_benign_variant_can_have_negative_raw_score_but_zero_priority():
    result = score_variant({
        "population_af": 0.1,
        "consequence": "missense_variant",
        "clinical_significance": "Benign",
        "clinvar_stars": 2,
        "clinvar_condition_match": "exact",
        "prediction_fields": {"REVEL": "0.001"},
        "filter_status": ["LOW_DP"],
        "depth": 7,
    })

    assert result["score"] < 0
    assert result["normalized_score"] == 0
    assert result["band"] == "P4"
    assert result["call_confidence"]["status"] == "low"
