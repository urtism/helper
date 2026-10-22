"""Transport HELPER's existing gnomAD lookup using the engine population contract."""
from helper_next.core.acmg_client import digest
from helper_variants.gnomad_frequency import cache_key


def import_cached(detail, identity, acquired_at):
    """Return evidence, source, versions, quality and missing-data declarations.

    No lookup, absence inference, threshold or scientific eligibility calculation.
    """
    raw = detail.get("gnomad_frequency")
    quality = []
    missing = []

    def unavailable(reason):
        return [], [], [], quality, [{"path": "/snapshot/evidence/population", "reason": reason}]

    if not raw:
        return unavailable("No cached HELPER gnomAD lookup; VCF population annotations, if present, retain their original provenance limitations")
    quality.append({"name": "HELPER_GNOMAD_STATUS", "value": raw.get("status")})
    try:
        observed_key = cache_key(*(raw.get(k) for k in (
            "reference_build", "chromosome", "position", "reference", "alternate")))
        selected_key = cache_key(identity["assembly"], identity["chromosome"], identity["position"],
                                 identity["reference"], identity["alternate"])
    except (TypeError, ValueError):
        return unavailable("HELPER gnomAD lookup has no valid exact allele identity")
    if observed_key != selected_key:
        return unavailable("HELPER gnomAD lookup belongs to a different allele or assembly")
    if not raw.get("release") or not raw.get("dataset"):
        return unavailable("HELPER gnomAD lookup is missing its dataset or release")
    if raw.get("status") not in ("observed", "not_observed_covered", "not_observed_low_coverage", "not_observed_coverage_unknown"):
        return unavailable("HELPER gnomAD lookup is unavailable or unsupported")

    checksum = digest(raw)
    limitations = ["Coverage adequacy is the existing HELPER locus heuristic, not ancestry representation or scientific approval",
                   "Counts and ancestry-specific coverage not returned by the source remain unknown"]
    provenance = {"source": "HELPER cached gnomAD genomes lookup", "source_identifier": "gnomAD",
                  "source_version": raw["release"], "acquired_at": raw.get("retrieved_at") or acquired_at,
                  "extraction_method": "DIRECT_IMPORT", "software_version": "helper-gnomad-frequency-v1",
                  "verification_status": "UNVERIFIED", "artifact_digest": checksum,
                  "source_url": raw.get("source_url") or None, "limitations": limitations}
    source = {"source_id": "gnomAD", "version": raw["release"], "checksum": checksum,
              "url": raw.get("source_url") or None, "limitations": limitations}
    coverage = raw.get("coverage") or {}
    filters = list(raw.get("filters") or [])
    # Empty filters on an absent database record do not assert a PASS call.
    has_counts = raw.get("ac") is not None and raw.get("an") is not None
    quality_status = "FILTERED" if filters else "PASS" if has_counts else None

    def frequency(record, population, aggregate=False):
        row = {"population": population, "filters": filters, "quality_status": quality_status}
        for name, target in (("ac", "allele_count"), ("an", "allele_number"), ("af", "allele_frequency"),
                             ("ac_hom", "homozygous_count"), ("ac_hemi", "hemizygous_count")):
            if record.get(name) is not None:
                row[target] = record[name]
        if aggregate:
            row["callable"] = bool(coverage.get("adequate")) if coverage.get("available") else None
            if coverage.get("mean") is not None:
                row["mean_depth"] = float(coverage["mean"])
            if coverage.get("over_20") is not None:
                row["coverage_fraction"] = float(coverage["over_20"])
        # Locus coverage does not establish ancestry representation, nor coverage
        # of each ancestry stratum. The engine retains those missing prerequisites.
        return row

    observation = {"dataset_id": raw["dataset"], "dataset_kind": "GENOME", "variant_identity": identity,
                   "variant_identifier": "-".join(map(str, (identity["chromosome"], identity["position"], identity["reference"], identity["alternate"]))),
                   "aggregate": frequency(raw, "global", aggregate=True),
                   "populations": [frequency(p, p["id"]) for p in raw.get("populations", []) if p.get("id")],
                   "coverage_notes": ["HELPER lookup status: " + str(raw.get("status")), *limitations]}
    quality.extend([{"name": "HELPER_GNOMAD_ABSENCE_REPORTED", "value": raw.get("population_absent")},
                    {"name": "HELPER_GNOMAD_COVERAGE_ADEQUATE", "value": raw.get("population_coverage_adequate")}])
    if not has_counts:
        missing.append({"path": "/snapshot/evidence/helper-gnomad-genomes/observation/aggregate/counts",
                        "reason": "gnomAD lookup did not return AC/AN; a not-observed state does not supply measured counts or a denominator"})
    missing.append({"path": "/snapshot/evidence/helper-gnomad-genomes/observation/representation",
                    "reason": "HELPER lookup does not establish adequate ancestry representation or ancestry-specific callability"})
    if not coverage.get("adequate"):
        missing.append({"path": "/snapshot/evidence/helper-gnomad-genomes/observation/aggregate/callable",
                        "reason": "Existing HELPER gnomAD lookup reports inadequate or unknown locus coverage"})
    evidence = {"id": "helper-gnomad-genomes", "kind": "POPULATION", "provenance": provenance,
                "observation": observation, "limitations": limitations}
    return [evidence], [source], [{"name": "gnomAD_genomes", "value": raw["release"]}], quality, missing
