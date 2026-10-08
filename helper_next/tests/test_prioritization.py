from helper_prioritization import RULESET_VERSION, score_variant


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
    assert result["score"] == 90
    assert result["max_score"] == 90
    assert result["normalized_score"] == 100
    assert result["band"] == "P1"
    assert result["formula"] == "25 + 25 + 20 + 20 = 90 / 90"
    assert component(result, "prediction")["applicable"] is False
    assert result["call_confidence"]["status"] == "high"


def test_missing_evidence_is_not_silently_treated_as_negative():
    result = score_variant({"consequence": "missense_variant"})

    assert "Population frequency" in result["missing_evidence"]
    assert "ClinVar" in result["missing_evidence"]
    assert "Zygosity × inheritance" in result["missing_evidence"]
    assert component(result, "maf")["score"] == 0


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

    assert component(result, "inheritance")["score"] == 12
    assert "phase is unknown" in component(result, "inheritance")["reason"]


def test_sex_linked_modes_are_not_collapsed_to_dominant_or_recessive():
    x_linked = score_variant({
        "inheritance_modes": ["X-linked recessive"], "zygosities": ["hemizygous"],
    })
    y_linked = score_variant({
        "inheritance_modes": ["Y-linked"], "zygosities": ["hemizygous"],
        "chromosome": "chrY",
    })

    assert component(x_linked, "inheritance")["score"] == 18
    assert component(y_linked, "inheritance")["score"] == 18


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
