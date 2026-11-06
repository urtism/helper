"""Pure v2 population policy used by the existing Priority engine.

Consumes the existing parsed gnomAD contract; never retrieves or caches data.
Quality cutoffs are experimental ranking safeguards configured in profiles.py.
"""

import math


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def _frequency(value):
    value = _number(value)
    return value if value is not None and 0 <= value <= 1 else None


def _counts(row):
    ac, an, af = _number(row.get("ac")), _number(row.get("an")), _frequency(row.get("af"))
    valid = (ac is not None and an is not None and ac.is_integer() and an.is_integer()
             and 0 <= ac <= an and an > 0 and af is not None
             and math.isclose(af, ac / an, rel_tol=1e-5, abs_tol=1e-12))
    return (ac, an, af) if valid else None


def _discordant(row, policy):
    if row.get("discordant"):
        return True
    stats = row.get("freq_comparison_stats") or {}
    if not isinstance(stats, dict):
        return False
    for name in ("stat_union", "contingency_table_test", "cochran_mantel_haenszel_test"):
        tests = stats.get(name)
        if isinstance(tests, dict):
            tests = [tests]
        if not isinstance(tests, list):
            continue
        for test in tests:
            if not isinstance(test, dict):
                continue
            p = _frequency(test.get("p_value"))
            if p is not None and p < policy["discordance_p_value"]:
                return True
    return False


def _dataset(name, row, policy, release):
    """AF is the maximum observed global/eligible-group AF, never the minimum."""
    if row.get("presence") != "PRESENT":
        return None, None
    allowed_flags = policy.get("nonblocking_flags", ())
    filters, flags = row.get("filters"), row.get("flags") or []
    if (not isinstance(filters, list) or not isinstance(flags, list)
            or any(flag not in allowed_flags for flag in filters + flags) or row.get("unreliable")):
        return None, name + ": FILTER unknown/non-PASS or quality flag"
    counts = _counts(row)
    if not counts or counts[1] < policy["minimum_observed_an"]:
        return None, name + ": invalid AF/AC/AN or insufficient site AN"
    coverage = row.get("coverage") or {}
    if coverage.get("available") and coverage.get("adequate") is False:
        return None, name + ": known inadequate locus callability"
    ac, an, af = counts
    source = {"dataset": name, "release": release, "metric": "AF", "population": None}
    warnings = [name + ": discrepant_frequencies retained; using the maximum observed AF"] if filters or flags else []
    for group in row.get("populations") or []:
        if group.get("id") not in policy["populations"]:
            continue
        group_counts = _counts(group)
        if not group_counts:
            if group.get("an") == 0 and group.get("ac") == 0 and group.get("af") is None:
                warnings.append("Population {} has no callable alleles".format(group["id"]))
                continue
            return None, name + ": invalid eligible population AF/AC/AN"
        group_ac, group_an, group_af = group_counts
        if group_ac > ac or group_an > an:
            return None, name + ": population counts exceed global counts"
        if group_an < policy["minimum_population_an"]:
            warnings.append("Population {} has insufficient AN".format(group["id"]))
            if group_af > af:
                # Ignoring the higher estimate would create a favourable rarity bias.
                return None, name + ": higher population AF has insufficient AN"
            continue
        if group_af > af:
            af = group_af
            source = dict(source, population=group["id"])
    if not row.get("populations"):
        warnings.append("Ancestry AF unavailable; observed rarity uses global AF only")
    if not coverage.get("available"):
        warnings.append("Callability unavailable; observed AF relies on site-specific counts")
    faf = _frequency(row.get("grpmax_faf95"))
    if row.get("grpmax_faf95") is not None and faf is None:
        return None, name + ": invalid official Grpmax FAF95"
    return {
        "name": name, "row": row, "ac": ac, "an": an, "af": af,
        "af_source": source, "faf95": faf,
        "faf95_source": dict(source, metric="official_grpmax_faf95",
                             population=row.get("grpmax_faf95_population")) if faf is not None else None,
        "warnings": warnings,
    }, None


def _context(variant, warnings):
    context = variant.get("population_mcaf_context")
    if not context:
        warnings.append("No validated gene-disease MCAF; experimental general rarity mode")
        return None
    if not isinstance(context, dict):
        warnings.append("Select one explicit MCAF context; no best-context selection is performed")
        return None
    mcaf = _frequency(context.get("mcaf"))
    required = ("gene", "disease_id", "mode_of_inheritance", "source", "version")
    gene = str(variant.get("gene") or "").strip().upper()
    if (context.get("validated") is not True or mcaf is None or mcaf <= 0
            or any(not context.get(key) for key in required)
            or (gene and gene != str(context["gene"]).strip().upper())):
        warnings.append("Invalid/incomplete MCAF context ignored; no clinical threshold inferred")
        return None
    return {key: context[key] for key in required} | {
        "mcaf": mcaf, "parameters": context.get("parameters"), "validated": True,
    }


def score_population(variant, profile):
    """Return one compact component; raw source payloads never enter the output."""
    config = profile["maf"]
    policy = config["reliability"]
    warnings = []
    af_only = config["scoring_mode"] == "observed_af"
    maximum_af = config["selection_policy"] == "maximum_gnomad_and_vep_af"
    vep_af = _frequency(variant.get("vep_max_af", variant.get("population_af"))) if maximum_af else None
    context = None if af_only else _context(variant, warnings)
    if af_only:
        warnings.append("Experimental observed-AF ranking; thresholds are not clinical criteria")
    result = {
        "key": "maf", "label": "Population frequency", "score": 0.0,
        "max_score": profile["component_maxima"]["maf"], "applicable": True,
        "evaluated": False, "evaluation_status": "not_evaluable",
        "scoring_version": profile["version"],
        "scoring_mode": "observed_af" if af_only else "context_aware" if context else "context_agnostic",
        "frequency_status": "NOT_FOUND_UNVERIFIED", "quality_status": "UNKNOWN",
        "quality_evidence": None,
        "observed_af": None, "observed_af_source": None,
        "faf95": None, "faf95_source": None,
        "mcaf": context["mcaf"] if context else None,
        "mcaf_source": {"source": context["source"], "version": context["version"]} if context else None,
        "disease_context": context, "warnings": warnings, "evidence": [],
        "reason": "Neutral: insufficient evidence; absence is not verified.",
    }
    if maximum_af:
        result.update(vep_max_af=vep_af, gnomad_observed_af=None)

    def finish(score=0, reason=None, status=None, quality=None, evaluated=False):
        # A positive VEP observation can exceed observed gnomAD AF or veto an
        # absence bonus. It cannot rescue explicitly failed/unsupported gnomAD QC.
        if (maximum_af and vep_af is not None and vep_af > 0
                and status not in ("UNRELIABLE", "UNSUPPORTED")
                and (result["observed_af"] is None or vep_af > result["observed_af"])):
            if reason:
                warnings.append("gnomAD: " + reason)
            previous = result["observed_af"]
            result.update(observed_af=vep_af, observed_af_source={
                "dataset": "vep", "release": variant.get("vep_version"), "metric": "MAX_AF", "population": None,
            })
            score = next((points for limit, points in config["generic_af_bands"] if vep_af <= limit),
                         config.get("generic_common_score", 0))
            reason = "Largest available observed AF is VEP summary MAX_AF; gnomAD is lower or unavailable."
            status, quality, evaluated = "OBSERVED", "PASS" if previous is not None else "VEP_ONLY", True
        minimum = config.get("minimum_score", -25 if context else 0)
        result["score"] = round(max(minimum, min(25, score)), 1)
        if reason:
            result["reason"] = reason
        if status:
            result["frequency_status"] = status
        if quality:
            result["quality_status"] = quality
        result["evaluated"] = evaluated
        result["evaluation_status"] = "evaluated" if evaluated else "not_evaluable"
        result["evidence"] = [
            "{} · {} · {}".format(result["scoring_mode"], result["frequency_status"], result["quality_status"]),
        ]
        for key, source_key, label in (("observed_af", "observed_af_source", "AF"),
                                       ("faf95", "faf95_source", "FAF95")):
            source = result[source_key]
            if source:
                if source["dataset"] == "vep":
                    result["evidence"].append("AF {:.6g} · VEP summary MAX_AF".format(result[key]))
                    continue
                result["evidence"].append("{} {:.6g} · {}{} · gnomAD {}".format(
                    label, result[key], source["dataset"],
                    "/" + source["population"] if source["population"] else "", source["release"]))
        if context:
            result["evidence"].append("MCAF {} · {} · {} · {}".format(
                context["mcaf"], context["disease_id"], context["source"], context["version"]))
        if result["frequency_status"] == "NOT_OBSERVED_EVALUABLE":
            qc = result["quality_evidence"]
            result["evidence"].append("Site AN {} ≥ {}; callable fraction {} ≥ {}".format(
                qc["site_an"], policy["minimum_absence_an"], qc["callable_fraction"],
                policy["minimum_absence_callability"]))
        if result["frequency_status"] == "NOT_FOUND_COVERED":
            qc = result["quality_evidence"]
            region = qc["region"]
            result["evidence"].append("Regional coverage: {} · {}:{}–{} · {}".format(
                region["reference_build"], region["chromosome"], region["start"], region["stop"],
                ", ".join(qc["adequate_datasets"])))
        result["evidence"].extend(warnings)
        return result

    chromosome = str(variant.get("chromosome") or "").removeprefix("chr").upper()
    unsupported_sequence = any(
        variant.get(key) is not None and (not str(variant[key]) or set(str(variant[key]).upper()) - set("ACGT"))
        for key in ("reference", "alternate")
    )
    if unsupported_sequence or (chromosome and chromosome not in {str(i) for i in range(1, 23)} | {"X", "Y"}):
        return finish(status="UNSUPPORTED", reason="Neutral: allele is unsupported by the gnomAD nuclear sequence-variant source.")
    data = variant.get("population_frequency_evidence") or {}
    if data.get("status") == "unsupported" or data.get("retrieval_status") == "UNSUPPORTED":
        return finish(status="UNSUPPORTED")
    if data.get("error") or data.get("status") == "unavailable" or data.get("availability") == "ERROR":
        return finish(status="ERROR", reason="Neutral: technical retrieval error; no biological absence inferred.")
    if not data:
        return finish()
    # Legacy flattened caches cannot provide dataset-specific provenance and QC.
    if (data.get("parser_version") != config["data_parser_version"]
            or data.get("release") != config["data_release"]):
        return finish(status="UNRELIABLE", quality="STALE_SCHEMA",
                      reason="Neutral: incompatible gnomAD release/parser; existing cache left unchanged.")
    variant_flags = data.get("variant_flags") or []
    if (data.get("partial") or any(flag not in policy.get("nonblocking_flags", ()) for flag in variant_flags)
            or data.get("unreliable")):
        return finish(status="UNRELIABLE", quality="FAIL", reason="Neutral: partial or flagged gnomAD data.")
    if variant_flags:
        warnings.append("gnomAD discrepant_frequencies retained; maximum observed AF is used")
    datasets = data.get("datasets") or {}
    if data.get("discordant") or any(_discordant(row, policy) for row in datasets.values()):
        if maximum_af:
            warnings.append("gnomAD frequency discrepancy retained; Exomes/Genomes discordance does not block maximum AF")
        else:
            return finish(status="UNRELIABLE", quality="DISCORDANT",
                          reason="Neutral: Exomes/Genomes discordance; dataset choice is uncertain.")
    usable = []
    rejected = []
    for name in ("joint", "exomes", "genomes"):
        selected, warning = _dataset(name, datasets.get(name) or {}, policy, data["release"])
        if warning:
            rejected.append(warning)
        if selected:
            usable.append(selected)
    warnings.extend(rejected)
    if not usable:
        if rejected:
            return finish(status="UNRELIABLE", quality="FAIL")
        coverage = data.get("region_coverage")
        if data.get("retrieval_status") == "NOT_FOUND" and isinstance(coverage, dict):
            status = coverage.get("status", "UNAVAILABLE")
            result["quality_evidence"] = {
                "region_coverage_status": status,
                "region": {k: coverage.get(k) for k in ("reference_build", "chromosome", "start", "stop")},
                "adequate_datasets": coverage.get("adequate_datasets", []),
                "absence_verified": False, "site_an_available": False,
            }
            warnings.append("Regional depth coverage does not provide site-specific AN or verify allele absence")
            if status == "ADEQUATE":
                # The AF ranking profile may explicitly accept regional coverage
                # as heuristic rarity evidence; retain the missing-AN qualifier.
                adequate = []
                summaries = coverage.get("datasets") or {}
                for name in coverage.get("adequate_datasets") or []:
                    summary = summaries.get(name) if isinstance(summaries, dict) else None
                    if name not in {"exomes", "genomes"} or not isinstance(summary, dict):
                        continue
                    expected = _number(summary.get("positions_expected"))
                    if (summary.get("status") == "ADEQUATE" and summary.get("adequate") is True
                            and summary.get("locus_status") == "ADEQUATE"
                            and expected is not None and expected > 0
                            and summary.get("positions_evaluated") == expected
                            and summary.get("fraction_bases_adequate") == 1):
                        adequate.append(name)
                if (config.get("regional_absence_policy") == "successful_not_found_with_adequate_regional_coverage"
                        and data.get("availability") == "AVAILABLE" and adequate
                        and not data.get("region_coverage_pending")):
                    result["quality_evidence"].update(adequate_datasets=adequate,
                                                      absence_evidence="regional_coverage_heuristic")
                    return finish(config["regional_absence_score"], reason=(
                        "Variant not found by a successful gnomAD lookup; surrounding region adequately covered in {}. "
                        "Heuristic rarity bonus; site-specific AN unavailable."
                    ).format(", ".join(adequate)), status="NOT_FOUND_COVERED",
                        quality="REGION_COVERED_NO_SITE_AN", evaluated=True)
                return finish(quality="REGION_COVERED_NO_SITE_AN", reason=(
                    "Variant not found; surrounding region adequately covered in {}. "
                    "Site-specific AN unavailable; absence remains unverified."
                ).format(", ".join(coverage.get("adequate_datasets") or [])))
            return finish(quality="REGION_COVERAGE_" + status, reason=(
                "Variant not found; surrounding region coverage is {}. Absence remains unverified."
            ).format(status.lower()))
        return finish()
    # A recorded alternative in any valid dataset prevents an absence bonus.
    observed = [item for item in usable if item["ac"] > 0]
    joint = next((item for item in usable if item["name"] == "joint"), None)
    if joint and joint["ac"] == 0 and observed and not maximum_af:
        return finish(status="UNRELIABLE", quality="DISCORDANT",
                      reason="Neutral: Joint absence conflicts with an observed allele.")
    chosen = (None if maximum_af else joint) or max(observed or usable, key=lambda item: (item["af"], item["an"], item["name"]))
    for item in usable if maximum_af else [chosen]:
        warnings.extend(item["warnings"])
    # FAF uses the preferred dataset. With no Joint, retain the strongest official
    # lower bound from the independently usable datasets, with its own provenance.
    faf_candidates = [joint] if joint else usable
    faf_item = max((item for item in faf_candidates if item["faf95"] is not None),
                   key=lambda item: item["faf95"], default=None)
    result.update(observed_af=chosen["af"], observed_af_source=chosen["af_source"],
                  faf95=faf_item["faf95"] if faf_item else None,
                  faf95_source=faf_item["faf95_source"] if faf_item else None,
                  quality_evidence={"site_an": chosen["an"],
                                    "callable_fraction": _frequency((chosen["row"].get("coverage") or {}).get("over_20"))})
    if maximum_af:
        result["gnomad_observed_af"] = chosen["af"]
    if not faf_item:
        warnings.append("FAF95 unavailable; statistical compatibility is unknown")
    elif not faf_item["faf95_source"]["population"]:
        warnings.append("Official Grpmax FAF95 ancestry label unavailable")
    if chosen["ac"] == 0:
        coverage = chosen["row"].get("coverage") or {}
        callability = _frequency(coverage.get("over_20"))
        if (not rejected and not observed and chosen["af"] == 0
                and chosen["an"] >= policy["minimum_absence_an"]
                and callability is not None and callability >= policy["minimum_absence_callability"]
                and not (faf_item and faf_item["faf95"] > 0)):
            return finish(config["absence_score"], "Verified absence: site AN and callable fraction meet policy.",
                          "NOT_OBSERVED_EVALUABLE", "PASS", True)
        return finish(status="NOT_FOUND_UNVERIFIED", quality="INSUFFICIENT_ABSENCE_EVIDENCE")
    af, faf, mcaf = chosen["af"], result["faf95"], result["mcaf"]
    if context and faf is not None and faf > mcaf:
        severe = faf > config["faf_severe_ratio"] * mcaf
        return finish(config["faf_severe_score"] if severe else config["faf_incompatible_score"],
                      "FAF95 > {}MCAF: statistically supported frequency incompatibility for this context.".format(
                          "{} × ".format(config["faf_severe_ratio"]) if severe else ""),
                      "OBSERVED", "PASS", True)
    bands = config["rare_ratios"] if context else config["generic_af_bands"]
    for limit, points in bands:
        if af <= (limit * mcaf if context else limit):
            reason = "AF ≤ {} × MCAF".format(limit) if context else "AF ≤ {} (experimental general rarity)".format(limit)
            return finish(points, reason, "OBSERVED", "PASS", True)
    common_score = config.get("generic_common_score", 0)
    reason = "AF > MCAF; no supported FAF95 incompatibility." if context else (
        "AF > {} (experimental observed-AF ranking)".format(bands[-1][0]) if af_only else
        "No general rarity bonus at this observed AF.")
    return finish(common_score, reason, "OBSERVED", "PASS", True)
