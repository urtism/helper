"""Versioned rule profiles for review prioritization, not clinical classification."""

RULESET_VERSION = "germline-wes-v1.0.0"

DEFAULT_PROFILE = {
    "id": "germline-wes",
    "version": RULESET_VERSION,
    "experimental": True,
    "component_maxima": {
        "maf": 25,
        "mechanism": 25,
        "clinvar": 20,
        "inheritance": 20,
        "prediction": 10,
    },
    "maf": {
        "default_max_credible_af": 0.001,
        "ba1_af": 0.05,
        "rare_ratios": ((0.1, 25), (0.5, 20), (1.0, 15), (5.0, 0)),
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
    "priority_bands": ((75, "P1"), (50, "P2"), (25, "P3"), (0, "P4")),
}
