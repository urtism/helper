"""Offline PRIORITY-01 comparison; synthetic runs are not scientific validation.

PYTHONPATH=helper_next/src python scripts/benchmark_population_frequency_v2.py
Optional --input JSON: list of {sample_id, variant_id, variant, classification?, causal?}.
`variant` contains the existing engine inputs plus population_frequency_evidence
(the parsed cached gnomAD result), and optionally population_mcaf_context.
Classification/causality labels must come from independent reviewed ground truth.
"""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import json
from pathlib import Path

from helper_prioritization import LEGACY_PROFILE, POPULATION_V2_PROFILE, score_variant
from helper_variants import gnomad_frequency as g


def _maf(result):
    return next(c for c in result["components"] if c["key"] == "maf")


def _variant_order(identifier):
    try:
        return (0, int(identifier))
    except ValueError:
        return (1, identifier)


def synthetic_records():
    fixture = Path(__file__).resolve().parents[1] / "helper_next/tests/fixtures/gnomad_v4/priority_01_required.json"
    f = json.loads(fixture.read_text())
    required = g._parse_response(f["response"], g.DATASETS["GRCh38"], f["allele"], "")
    rows = []
    for i, data in enumerate((required, {}, dict(required, status="unavailable", error="synthetic timeout"))):
        rows.append({"sample_id": "synthetic-1", "variant_id": str(i + 1), "variant": {
            "gene": "GENE1", "consequence": "missense_variant",
            "population_frequency_evidence": data,
        }})
    context = {"gene": "GENE1", "disease_id": "synthetic-disease", "mode_of_inheritance": "AD",
               "mcaf": 0.001, "validated": True, "source": "synthetic-test", "version": "1"}
    for mcaf in (0.001, 1e-7):
        row = deepcopy(rows[0])
        row["variant_id"] = str(len(rows) + 1)
        row["variant"]["population_mcaf_context"] = dict(context, mcaf=mcaf)
        rows.append(row)
    return rows


def compare(records, candidate_threshold=50):
    rows = []
    for record in records:
        variant = dict(record["variant"])
        data = variant.get("population_frequency_evidence") or {}
        old = score_variant({**variant, **g.priority_context(data)}, LEGACY_PROFILE)
        new = score_variant(variant, POPULATION_V2_PROFILE)
        # Freeze the same source release/allele and restrict selection to genomes.
        # This comparison separates the v2 policy/scoring change from using Joint.
        genomes = deepcopy(data)
        genomes["datasets"] = {"genomes": (data.get("datasets") or {}).get("genomes") or {}}
        same_dataset = score_variant({**variant, "population_frequency_evidence": genomes}, POPULATION_V2_PROFILE)
        global_data = deepcopy(data)
        for dataset in (global_data.get("datasets") or {}).values():
            dataset["populations"] = []
        global_only = score_variant({**variant, "population_frequency_evidence": global_data}, POPULATION_V2_PROFILE)
        generic_input = {k: v for k, v in variant.items() if k != "population_mcaf_context"}
        generic = score_variant(generic_input, POPULATION_V2_PROFILE)
        c = _maf(new)
        rows.append({
            "sample_id": str(record["sample_id"]), "variant_id": str(record["variant_id"]),
            "classification": record.get("classification"), "causal": record.get("causal"),
            "population_v1": _maf(old)["score"], "population_v2": c["score"],
            "population_v2_genomes_only": _maf(same_dataset)["score"],
            "population_v2_global_only": _maf(global_only)["score"],
            "population_v2_generic": _maf(generic)["score"],
            "mode": c["scoring_mode"], "mcaf": c["mcaf"], "frequency_status": c["frequency_status"],
            "release": data.get("release"),
            "priority_v1": old["normalized_score"], "priority_v2": new["normalized_score"],
            "raw_v1": old["score"], "raw_v2": new["score"],
            "denominator_v1": old["max_score"], "denominator_v2": new["max_score"],
            "band_v1": old["band"], "band_v2": new["band"],
        })
    groups = defaultdict(list)
    for row in rows:
        groups[row["sample_id"]].append(row)
    causal = {}
    candidates = {}
    for version in ("v1", "v2"):
        for group in groups.values():
            # Match Variant Browser tie-breaking: normalized, raw, variant ID.
            ordered = sorted(group, key=lambda r: (-r["priority_" + version], -r["raw_" + version], _variant_order(r["variant_id"])))
            for rank, row in enumerate(ordered, 1):
                row["rank_" + version] = rank
        known_samples = [group for group in groups.values() if any(r["causal"] is True for r in group)]
        causal[version] = {"samples_with_known_causal_variant": len(known_samples),
                           "top_k": {str(k): sum(any(r["causal"] is True and r["rank_" + version] <= k for r in group)
                                                 for group in known_samples) / len(known_samples)
                                     if known_samples else None for k in (1, 5, 10)}}
        candidates[version] = sum(r["priority_" + version] >= candidate_threshold for r in rows) / len(groups) if groups else None
    classified = defaultdict(list)
    for row in rows:
        if row["classification"]:
            classified[row["classification"]].append(row)
    summary = {
        "variants": len(rows), "samples": len(groups),
        "insufficient_gnomad_fraction": sum(r["frequency_status"] not in {"OBSERVED", "NOT_OBSERVED_EVALUABLE"} for r in rows) / len(rows) if rows else None,
        "score_distributions": {v: dict(Counter(r["population_" + v] for r in rows)) for v in ("v1", "v2")},
        "priority_distributions": {v: dict(Counter(r["priority_" + v] for r in rows)) for v in ("v1", "v2")},
        "rank_changes": sum(r["rank_v1"] != r["rank_v2"] for r in rows),
        "band_changes": sum(r["band_v1"] != r["band_v2"] for r in rows),
        "positive_to_neutral_or_negative": sum(r["population_v1"] > 0 and r["population_v2"] <= 0 for r in rows),
        "ancestry_af_effect_count": sum(r["population_v2"] != r["population_v2_global_only"] for r in rows),
        "mcaf_context_effect_count": sum(r["population_v2"] != r["population_v2_generic"] for r in rows),
        "denominator_changes": sum(r["denominator_v1"] != r["denominator_v2"] for r in rows),
        "causal_ranking": causal, "candidate_threshold": candidate_threshold,
        "mean_candidates_per_sample": candidates,
        "by_reviewed_classification": {label: {v: dict(Counter(r["population_" + v] for r in subset))
                                               for v in ("v1", "v2")} for label, subset in classified.items()},
    }
    return {"summary": summary, "rows": rows,
            "limitations": ["Paired scores use identical input data; no gnomAD update or HTTP request.",
                            "Genomes-only control retains v2 quality/AF policy; it does not isolate every individual rule.",
                            "VUS are reported as their own group, never assumed negative controls.",
                            "Top-k values require independently reviewed causal labels; absent labels yield null.",
                            "Synthetic records and unit tests do not establish scientific validity."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--candidate-threshold", type=float, default=50)
    args = parser.parse_args()
    records = json.loads(args.input.read_text()) if args.input else synthetic_records()
    report = compare(records, args.candidate_threshold)
    report["mode"] = "external_offline_data" if args.input else "synthetic_only_not_validated"
    report["scientifically_validated"] = False
    output = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(output)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
