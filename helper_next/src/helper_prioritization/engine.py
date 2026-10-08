"""Pure decision engine for explainable germline variant review prioritization.

The engine accepts ordinary dictionaries and returns JSON-serializable dictionaries.
It deliberately has no database, web, pipeline, or UI dependencies.
"""

import re

from helper_prioritization.profiles import DEFAULT_PROFILE


_LOF_CONSEQUENCES = {
    "transcript_ablation", "frameshift_variant", "stop_gained",
    "splice_acceptor_variant", "splice_donor_variant",
}
_PARTIAL_LOF_CONSEQUENCES = {
    "start_lost", "stop_lost", "transcript_amplification",
}
_MISSENSE_CONSEQUENCES = {
    "missense_variant", "protein_altering_variant", "inframe_insertion",
    "inframe_deletion",
}
_SPLICE_RELEVANT_CONSEQUENCES = {
    "splice_region_variant", "splice_donor_5th_base_variant",
    "splice_polypyrimidine_tract_variant", "synonymous_variant",
    "intron_variant",
}
_PREDICTOR_PATTERN = re.compile(
    r"SIFT|POLYPHEN|LRT|MUTATIONTASTER|MUTATIONASSESSOR|FATHMM|PROVEAN|"
    r"VEST4|METASVM|METALR|M[-_]?CAP|REVEL|MUTPRED|MVP|MPC|PRIMATEAI|"
    r"DEOGEN2|ALOFT|CADD|DANN|SPLICEAI|ALPHAMISSENSE|CLINPRED|BAYESDEL",
    re.IGNORECASE,
)


def score_variant(variant, profile=None):
    """Return a versioned, explainable review-priority assessment."""
    profile = profile or DEFAULT_PROFILE
    components = [
        _score_maf(variant, profile),
        _score_mechanism(variant, profile),
        _score_clinvar(variant, profile),
        _score_inheritance(variant, profile),
        _score_prediction(variant, profile),
    ]
    applicable = [component for component in components if component["applicable"]]
    raw_score = round(sum(component["score"] for component in applicable), 1)
    maximum = sum(component["max_score"] for component in applicable)
    normalized = round(max(0.0, min(100.0, raw_score * 100.0 / maximum))) if maximum else 0
    band = next(
        label for threshold, label in profile["priority_bands"] if normalized >= threshold
    )
    missing = [
        component["label"] for component in applicable if not component["evaluated"]
    ]
    if not _values(variant.get("disease_mechanisms")):
        missing.append("Disease mechanism")
    if (_values(variant.get("clinical_significance"))
            and str(variant.get("clinvar_condition_match") or "unknown").casefold() == "unknown"):
        missing.append("ClinVar condition match")
    if str(variant.get("compound_status") or "").casefold().replace(" ", "_") in {
            "phase_unknown", "possible"}:
        missing.append("Compound phase")
    missing = list(dict.fromkeys(missing))
    return {
        "ruleset": profile["version"],
        "profile": profile["id"],
        "experimental": bool(profile.get("experimental", True)),
        "score": raw_score,
        "max_score": maximum,
        "normalized_score": normalized,
        "band": band,
        "components": components,
        "formula": " + ".join(_format_number(item["score"]) for item in applicable)
        + " = {} / {}".format(_format_number(raw_score), maximum),
        "missing_evidence": missing,
        "call_confidence": _call_confidence(variant),
    }


def _component(key, label, score, maximum, reason, evaluated=True,
               applicable=True, evidence=None):
    return {
        "key": key, "label": label, "score": round(float(score), 1),
        "max_score": int(maximum), "reason": reason,
        "evaluated": bool(evaluated), "applicable": bool(applicable),
        "evidence": list(evidence or []),
    }


def _score_maf(variant, profile):
    maximum = profile["component_maxima"]["maf"]
    af = _number(variant.get("population_af"))
    threshold = _number(variant.get("max_credible_af"))
    threshold = threshold if threshold is not None else profile["maf"]["default_max_credible_af"]
    if af is None:
        if variant.get("population_absent") and variant.get("population_coverage_adequate"):
            return _component(
                "maf", "Population frequency", maximum, maximum,
                "Absent from a population resource with adequate coverage.",
                evidence=["Population absence verified", "Maximum credible AF {}".format(threshold)],
            )
        return _component(
            "maf", "Population frequency", 0, maximum,
            "Population AF is not available; missing AF is not treated as zero.",
            evaluated=False,
        )
    ba1 = _number(variant.get("ba1_af"))
    ba1 = ba1 if ba1 is not None else profile["maf"]["ba1_af"]
    if af >= ba1:
        return _component(
            "maf", "Population frequency", profile["maf"]["ba1_score"], maximum,
            "Population AF is at or above the general BA1-level threshold.",
            evidence=["AF {}".format(af), "BA1 threshold {}".format(ba1)],
        )
    ratio = af / threshold if threshold > 0 else float("inf")
    for limit, score in profile["maf"]["rare_ratios"]:
        if ratio <= limit:
            reason = (
                "Population AF is compatible with the configured maximum credible AF."
                if score else
                "Population AF exceeds the maximum credible AF and receives no rarity points."
            )
            return _component(
                "maf", "Population frequency", score, maximum, reason,
                evidence=["AF {}".format(af), "Maximum credible AF {}".format(threshold),
                          "AF / threshold {:.3g}".format(ratio)],
            )
    return _component(
        "maf", "Population frequency", profile["maf"]["too_common_score"], maximum,
        "Population AF is substantially above the configured maximum credible AF.",
        evidence=["AF {}".format(af), "Maximum credible AF {}".format(threshold),
                  "AF / threshold {:.3g}".format(ratio)],
    )


def _score_mechanism(variant, profile):
    maximum = profile["component_maxima"]["mechanism"]
    consequences = _terms(variant.get("consequence"))
    mechanisms = {_normalize_mechanism(item) for item in _values(variant.get("disease_mechanisms"))}
    mechanisms.discard("")
    lof = "loss of function" in mechanisms
    gain_or_dn = bool(mechanisms.intersection({"gain of function", "dominant negative"}))
    mechanism_known = lof or gain_or_dn
    if lof and consequences.intersection(_LOF_CONSEQUENCES):
        base, reason = 25, "Predicted loss-of-function consequence matches a known LoF mechanism."
    elif lof and consequences.intersection(_PARTIAL_LOF_CONSEQUENCES):
        base, reason = 20, "Protein-truncating consequence is compatible with a known LoF mechanism."
    elif gain_or_dn and consequences.intersection(_MISSENSE_CONSEQUENCES):
        if variant.get("hotspot_or_domain"):
            base, reason = 25, "Missense/in-frame change matches a GoF/DN mechanism and a relevant hotspot or domain."
        else:
            base, reason = 15, "Missense/in-frame change is compatible with a known GoF/DN mechanism."
    elif mechanism_known:
        base, reason = 0, "Variant consequence is not clearly compatible with the documented disease mechanism."
    elif consequences.intersection(_LOF_CONSEQUENCES):
        base, reason = 15, "High-impact consequence, but the disease mechanism is not established."
    elif consequences.intersection(_PARTIAL_LOF_CONSEQUENCES):
        base, reason = 12, "Potential protein-truncating consequence with unknown disease mechanism."
    elif consequences.intersection(_MISSENSE_CONSEQUENCES):
        base, reason = 10, "Missense/in-frame consequence with unknown disease mechanism."
    elif consequences.intersection(_SPLICE_RELEVANT_CONSEQUENCES):
        base, reason = 5, "Potential splice-relevant consequence; computational evidence is assessed separately."
    else:
        base, reason = 0, "No consequence rule currently raises review priority."
    confidence = _mechanism_confidence(variant, profile) if mechanism_known else 1.0
    if variant.get("gene_context_ambiguous") and mechanism_known:
        confidence = min(confidence, 0.7)
        reason += " Gene-level records cover multiple disease contexts, so confidence is reduced."
    score = round(base * confidence, 1)
    evidence = ["Consequence: {}".format(" & ".join(sorted(consequences)) or "not reported")]
    if mechanisms:
        evidence.append("Mechanism: {}".format("; ".join(sorted(mechanisms))))
        evidence.append("Mechanism confidence ×{}".format(confidence))
    sources = _values(variant.get("gene_context_sources"))
    if sources:
        evidence.append("Gene context: {}".format("; ".join(sources)))
    return _component(
        "mechanism", "Consequence × disease mechanism", score, maximum, reason,
        evaluated=bool(consequences), evidence=evidence,
    )


def _score_clinvar(variant, profile):
    maximum = profile["component_maxima"]["clinvar"]
    significance = " ".join(_values(variant.get("clinical_significance"))).casefold()
    if not significance or significance == ".":
        return _component(
            "clinvar", "ClinVar", 0, maximum,
            "No ClinVar germline classification is available.", evaluated=False,
        )
    pathogenic = "pathogenic" in significance and "benign" not in significance
    benign = "benign" in significance and "pathogenic" not in significance
    conflicting = bool(variant.get("clinvar_conflict")) or ("pathogenic" in significance and "benign" in significance)
    if conflicting or "conflict" in significance:
        return _component(
            "clinvar", "ClinVar", 0, maximum,
            "ClinVar reports conflicting classifications; no priority points are assigned.",
            evidence=[significance],
        )
    if "uncertain" in significance or "vus" in significance:
        return _component(
            "clinvar", "ClinVar", 0, maximum,
            "ClinVar reports uncertain significance.", evidence=[significance],
        )
    if not pathogenic and not benign:
        return _component(
            "clinvar", "ClinVar", 0, maximum,
            "ClinVar classification is not mapped to a prioritization rule.",
            evidence=[significance],
        )
    stars = max(0, min(4, int(_number(variant.get("clinvar_stars")) or 0)))
    magnitude = {0: 5, 1: 10, 2: 16, 3: 20, 4: 20}[stars]
    if "likely" in significance:
        magnitude = max(0, magnitude - 2)
    match = str(variant.get("clinvar_condition_match") or "unknown").casefold()
    multiplier = {"exact": 1.0, "related": 0.5, "unrelated": 0.0, "unknown": 0.5}.get(match, 0.5)
    score = round(magnitude * multiplier * (1 if pathogenic else -1), 1)
    reason = (
        "ClinVar P/LP evidence is weighted by review status and disease match."
        if pathogenic else
        "ClinVar B/LB evidence lowers review priority according to review status and disease match."
    )
    return _component(
        "clinvar", "ClinVar", score, maximum, reason,
        evidence=["Classification: {}".format(significance), "Review stars: {}".format(stars),
                  "Condition match: {} (×{})".format(match, multiplier)],
    )


def _score_inheritance(variant, profile):
    maximum = profile["component_maxima"]["inheritance"]
    modes = {_normalize_inheritance(item) for item in _values(variant.get("inheritance_modes"))}
    modes.discard("")
    zygosities = {item.casefold().replace("-", "_") for item in _values(variant.get("zygosities"))}
    compound = str(variant.get("compound_status") or "").casefold().replace(" ", "_")
    if not modes:
        reason = "Gene-level inheritance or allelic requirement is not available."
        if compound:
            reason += " A possible compound candidate is recorded but cannot be weighted yet."
        de_novo = str(variant.get("de_novo_status") or "").strip()
        if de_novo:
            reason += " De novo evidence is recorded but cannot be weighted without an inheritance model."
        evidence = ["Zygosity: {}".format(", ".join(sorted(zygosities)) or "not reported")]
        if de_novo:
            evidence.append("De novo status: {}".format(de_novo))
        return _component(
            "inheritance", "Zygosity × inheritance", 0, maximum, reason,
            evaluated=False, evidence=evidence,
        )
    candidates = []
    if "dominant" in modes:
        de_novo = str(variant.get("de_novo_status") or "").casefold()
        if de_novo == "confirmed":
            candidates.append((20, "Confirmed de novo call is compatible with dominant inheritance."))
        elif de_novo in {"assumed", "candidate"}:
            candidates.append((18, "De novo candidate is compatible with dominant inheritance."))
        elif zygosities.intersection({"het", "heterozygous"}):
            candidates.append((12, "Heterozygous call is compatible with dominant inheritance."))
    if "recessive" in modes:
        if compound in {"confirmed_in_trans", "in_trans"}:
            candidates.append((20, "Two qualifying variants are confirmed in trans."))
        elif compound in {"likely_in_trans", "one_per_parent", "parental_compound"}:
            candidates.append((18, "One qualifying variant per parent supports an in-trans configuration."))
        elif compound in {"phase_unknown", "possible"}:
            candidates.append((12, "Two heterozygous variants form a compound candidate, but phase is unknown."))
        elif zygosities.intersection({"hom_alt", "homozygous", "homozygous_alternate"}):
            candidates.append((20, "Homozygous alternate call is compatible with recessive inheritance."))
        elif zygosities.intersection({"het", "heterozygous"}):
            candidates.append((2, "A single heterozygous call in a recessive context is usually carrier evidence."))
    if "x_linked" in modes:
        if zygosities.intersection({"hemi", "hemizygous"}):
            candidates.append((18, "Hemizygous call is compatible with X-linked inheritance."))
        elif zygosities.intersection({"het", "heterozygous"}):
            candidates.append((10, "Heterozygous call may be compatible with an X-linked disorder."))
    if "y_linked" in modes:
        chromosome = str(variant.get("chromosome") or "").upper().replace("CHR", "")
        if chromosome == "Y" and zygosities.intersection({"hemi", "hemizygous"}):
            candidates.append((18, "Hemizygous call on chromosome Y is compatible with Y-linked inheritance."))
        elif chromosome == "Y":
            candidates.append((12, "Call on chromosome Y is compatible with Y-linked inheritance."))
    if "mitochondrial" in modes:
        candidates.append((12, "Mitochondrial location/inheritance is compatible; heteroplasmy is not yet evaluated."))
    score, reason = max(candidates, default=(0, "Zygosity is not compatible with the available inheritance models."))
    if len(modes) > 1 or variant.get("gene_context_ambiguous"):
        score = round(score * 0.75, 1)
        reason += " Multiple gene-disease contexts reduce confidence."
    evidence = ["Inheritance: {}".format("; ".join(sorted(modes))),
                "Zygosity: {}".format("; ".join(sorted(zygosities)) or "not reported"),
                "Compound status: {}".format(compound or "not reported")]
    de_novo = str(variant.get("de_novo_status") or "").strip()
    if de_novo:
        evidence.append("De novo status: {}".format(de_novo))
    sources = _values(variant.get("gene_context_sources"))
    if sources:
        evidence.append("Gene context: {}".format("; ".join(sources)))
    return _component(
        "inheritance", "Zygosity × inheritance", score, maximum, reason,
        evidence=evidence,
    )


def _score_prediction(variant, profile):
    maximum = profile["component_maxima"]["prediction"]
    fields = variant.get("prediction_fields") or {}
    consequences = _terms(variant.get("consequence"))
    mechanisms = {_normalize_mechanism(item) for item in _values(variant.get("disease_mechanisms"))}
    clear_lof = bool(consequences.intersection(_LOF_CONSEQUENCES) and "loss of function" in mechanisms)
    if clear_lof:
        return _component(
            "prediction", "Computational prediction", 0, maximum,
            "Not applicable: computational prediction is not counted again for a clear LoF consequence.",
            applicable=False,
        )
    splice_score = _field_score(fields, "SPLICEAI")
    if splice_score is not None:
        if splice_score >= 0.5:
            score, reason = 10, "SpliceAI is at or above 0.5."
        elif splice_score >= 0.2:
            score, reason = 7, "SpliceAI is in the generic spliceogenic range (≥0.2)."
        elif splice_score <= 0.1:
            score, reason = -5, "SpliceAI is in the generic non-spliceogenic range (≤0.1)."
        else:
            score, reason = 0, "SpliceAI is in the indeterminate range."
        return _component(
            "prediction", "Computational prediction", score, maximum, reason,
            evidence=["Maximum SpliceAI score {}".format(splice_score)],
        )
    revel = _field_score(fields, "REVEL")
    if revel is not None and consequences.intersection(_MISSENSE_CONSEQUENCES):
        if revel >= 0.932:
            score, reason = 10, "REVEL reaches the calibrated strong pathogenic range."
        elif revel >= 0.773:
            score, reason = 8, "REVEL reaches the calibrated moderate pathogenic range."
        elif revel >= 0.644:
            score, reason = 5, "REVEL reaches the calibrated supporting pathogenic range."
        elif revel <= 0.003:
            score, reason = -10, "REVEL reaches the calibrated strong benign range."
        elif revel <= 0.016:
            score, reason = -8, "REVEL reaches the calibrated moderate benign range."
        elif revel <= 0.183:
            score, reason = -5, "REVEL reaches the calibrated supporting benign range."
        else:
            score, reason = 0, "REVEL is in an indeterminate range."
        return _component(
            "prediction", "Computational prediction", score, maximum, reason,
            evidence=["REVEL {}".format(revel)],
        )
    present = sorted(key for key, value in fields.items() if value not in (None, "", ".") and _PREDICTOR_PATTERN.search(str(key)))
    applicable = bool(present or consequences.intersection(_MISSENSE_CONSEQUENCES | _SPLICE_RELEVANT_CONSEQUENCES))
    if present:
        return _component(
            "prediction", "Computational prediction", 0, maximum,
            "Predictor values are available, but this profile has no generic calibrated scoring rule for them.",
            evidence=present,
        )
    return _component(
        "prediction", "Computational prediction", 0, maximum,
        "No calibrated prediction is available for this variant type.",
        evaluated=not applicable, applicable=applicable,
    )


def _call_confidence(variant):
    warnings = []
    filters = [item.upper() for item in _values(variant.get("filter_status"))]
    failing = [item for item in filters if item not in {"", ".", "PASS"}]
    depth = _number(variant.get("depth"))
    quality = _number(variant.get("quality"))
    if failing:
        warnings.append("VCF FILTER: {}".format(", ".join(failing)))
    if depth is None:
        warnings.append("DP not available")
    elif depth < 10:
        warnings.append("DP below 10")
    elif depth < 20:
        warnings.append("DP below 20")
    if quality is not None and quality < 20:
        warnings.append("QUAL below 20")
    status = "low" if failing or (depth is not None and depth < 10) else "warning" if warnings else "high"
    return {
        "status": status,
        "warnings": warnings,
        "note": "Call confidence is reported separately and is not pathogenicity evidence.",
    }


def _mechanism_confidence(variant, profile):
    values = [item.casefold() for item in _values(variant.get("mechanism_confidence"))]
    if not values:
        return 1.0
    factors = profile["mechanism_confidence"]
    return max(factors.get(value, 0.4) for value in values)


def _normalize_mechanism(value):
    text = " ".join(str(value or "").strip().casefold().replace("_", " ").split())
    if text in {"lof", "loss of function", "absent gene product"}:
        return "loss of function"
    if text in {"gof", "gain of function"}:
        return "gain of function"
    if text in {"dn", "dominant negative"}:
        return "dominant negative"
    return text if text not in {"unknown", "not known", "not specified"} else ""


def _normalize_inheritance(value):
    text = " ".join(str(value or "").strip().casefold().replace("_", " ").split())
    if "x-linked" in text or "x linked" in text:
        return "x_linked"
    if "y-linked" in text or "y linked" in text:
        return "y_linked"
    if "mitochond" in text or "maternal" in text:
        return "mitochondrial"
    if any(token in text for token in ("biallelic", "autosomal recessive", "recessive")):
        return "recessive"
    if any(token in text for token in ("monoallelic", "autosomal dominant", "dominant")):
        return "dominant"
    return ""


def _field_score(fields, marker):
    values = []
    for key, value in fields.items():
        if marker.casefold() not in str(key).casefold() or value in (None, "", "."):
            continue
        values.extend(number for number in _numbers(value) if 0 <= number <= 1)
    return max(values) if values else None


def _numbers(value):
    return [float(item) for item in re.findall(r"(?<![A-Za-z])[-+]?(?:\d+\.\d+|\d+)(?:[eE][-+]?\d+)?", str(value))]


def _terms(value):
    return {
        item.strip().casefold() for raw in _values(value)
        for item in re.split(r"[&,|]", raw) if item.strip()
    }


def _values(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in re.split(r"[;,|]", str(value)) if item.strip()]


def _number(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_number(value):
    number = float(value)
    return str(int(number)) if number.is_integer() else str(round(number, 1))
