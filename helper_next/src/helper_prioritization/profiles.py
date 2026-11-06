"""Versioned rule profiles for review prioritization, not clinical classification."""

from copy import deepcopy

RULESET_VERSION = "germline-wes-v2.2.0"

LEGACY_PROFILE = {
    "id": "germline-wes",
    "version": "germline-wes-v1.9.2",
    "experimental": True,
    "component_maxima": {
        "maf": 25,
        "mechanism": 25,
        "clinvar": 20,
        "inheritance": 15,
        "prediction": 10,
        "run_occurrence": 15,
    },
    "maf": {
        "default_max_credible_af": 0.001,
        "very_rare_af": 0.000001,
        "ba1_af": 0.05,
        "rare_ratios": ((0.1, 20), (0.5, 15), (1.0, 10), (5.0, 0)),
        "missing_af_score": 10,
        "too_common_score": -15,
        "ba1_score": -25,
    },
    "mechanism_confidence": {
        "definitive": 1.0,
        "confirmed": 1.0,
        "strong": 0.9,
        "probable": 0.8,
        "moderate": 0.7,
        "supportive": 0.55,
        "limited": 0.4,
        "inferred": 0.4,
        "unknown": 1.0,
    },
    "clinvar": {
        "star_weights": {0: 0.5, 1: 0.75, 2: 1.0, 3: 1.0, 4: 1.0},
        "vus_conflict_weight": 0.75,
    },
    "priority_bands": ((75, "P1"), (50, "P2"), (25, "P3"), (0, "P4")),
}

# Preserve previous profiles unchanged for reproducible comparisons.
POPULATION_V2_PROFILE = deepcopy(LEGACY_PROFILE)
POPULATION_V2_PROFILE.update(version="germline-wes-v2.0.0")
POPULATION_V2_PROFILE["maf"] = {
    "algorithm": "population-v2",
    "scoring_mode": "auto_explicit_context",
    "selection_policy": "joint_then_highest_observed_af",
    "missing_data_policy": "neutral_keep_denominator",
    "mcaf_policy": "explicit_validated_gene_disease_context_only",
    "data_release": "4.1.1",
    "data_parser_version": "gnomad-frequency-2",
    "missing_af_score": 0,
    "absence_score": 25,
    "rare_ratios": ((0.01, 25), (0.1, 20), (0.5, 10), (1.0, 5)),
    "faf_severe_ratio": 5.0,
    "faf_incompatible_score": -15,
    "faf_severe_score": -25,
    # Experimental ranking bins, not clinical thresholds or BA1/BS1.
    "generic_af_bands": ((1e-6, 25), (1e-5, 20), (1e-4, 10), (1e-3, 5)),
    "reliability": {
        "minimum_observed_an": 1,  # Structural validity, not proof of sensitivity.
        "minimum_population_an": 1000,  # Experimental precision safeguard.
        "minimum_absence_an": 10000,  # Experimental; requires callability too.
        "minimum_absence_callability": 0.8,
        "discordance_p_value": 0.001,  # Experimental QC trigger, not clinical evidence.
        "populations": ("afr", "ami", "amr", "asj", "eas", "fin", "mid", "nfe", "sas"),
        "unknown_flags": "exclude_dataset",
    },
}

ALLELE_FREQUENCY_PROFILE = deepcopy(POPULATION_V2_PROFILE)
ALLELE_FREQUENCY_PROFILE["version"] = "germline-wes-v2.1.0"
ALLELE_FREQUENCY_PROFILE["maf"].update({
    "scoring_mode": "observed_af",
    "mcaf_policy": "not_used",
    "minimum_score": -10,
    "generic_af_bands": (
        (1e-6, 25), (1e-5, 20), (1e-4, 15), (5e-4, 10), (1e-3, 5), (1e-2, 0),
    ),
    "generic_common_score": -10,
})
COVERAGE_AWARE_PROFILE = deepcopy(ALLELE_FREQUENCY_PROFILE)
COVERAGE_AWARE_PROFILE["version"] = RULESET_VERSION
COVERAGE_AWARE_PROFILE["maf"].update({
    "selection_policy": "maximum_gnomad_and_vep_af",
    "regional_absence_policy": "successful_not_found_with_adequate_regional_coverage",
    "regional_absence_score": 25,
})
COVERAGE_AWARE_PROFILE["maf"]["reliability"]["nonblocking_flags"] = ("discrepant_frequencies",)
DEFAULT_PROFILE = COVERAGE_AWARE_PROFILE

PROFILES = {profile["version"]: profile for profile in (
    LEGACY_PROFILE, POPULATION_V2_PROFILE, ALLELE_FREQUENCY_PROFILE, COVERAGE_AWARE_PROFILE,
)}


def get_profile(version=None):
    """Explicit version selection; callers configuring thresholds receive a copy."""
    return deepcopy(PROFILES[version or RULESET_VERSION])
