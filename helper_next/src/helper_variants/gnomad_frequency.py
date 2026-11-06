"""Allele-specific gnomAD v4 frequencies in the existing shared SQLite cache."""
import copy
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import threading
import os
import re
import sqlite3
import time
from itertools import islice
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from helper_variants.acquisition import frequency_flights
from helper_variants import gnomad_coverage


API_URL = "https://gnomad.broadinstitute.org/api"
SOURCE_URL = "https://gnomad.broadinstitute.org/"
USER_AGENT = "HelperVariantBrowser/0.1 (gnomAD v4 frequencies)"
ALLELE_RE = re.compile(r"^[ACGT]+$")
MIN_MEAN_COVERAGE = 20.0
MIN_OVER_20 = 0.8
REGION_COVERAGE_FLANK = 25
REGION_COVERAGE_MAX_SPAN = 250
REGION_COVERAGE_POLICY = "gnomad-region-coverage-1"

FREQUENCY_RELEASE = "4.1.1"
PARSER_VERSION = "gnomad-frequency-2"
DATASETS = {"GRCh38": {"id": "gnomad_r4", "release": FREQUENCY_RELEASE,
                         "reference_genome": "GRCh38"}}
PRODUCTS = {"exomes": "exome", "genomes": "genome", "joint": "joint"}
_projection_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="helper-projection")
_request_lock = threading.Lock()
_last_request = 0.0
_last_cost = 0
ERROR_RETRY_SECONDS = 30

# Sex-stratified, sub-population, HGDP and 1000 Genomes rows are intentionally
# excluded from the compact clinical summary. They remain available at the source URL.
MAJOR_POPULATIONS = {
    "afr", "ami", "amr", "asj", "eas", "fin", "mid", "nfe", "oth", "remaining", "sas",
}

# Verified against VariantDetails, not the different regional Variant type.
# Population FAF is not exposed by this API; preserve explicit nulls.
_COUNTS = """
  ac an homozygote_count hemizygote_count filters
  populations { id ac an homozygote_count hemizygote_count }
  faf95 { popmax popmax_population } faf99 { popmax popmax_population }
  quality_metrics { site_quality_metrics { metric value } }
"""
_VARIANT_FIELDS = """
  variant_id reference_genome chrom pos ref alt flags
  coverage { exome { mean median over_20 } genome { mean median over_20 } }
  exome { COUNTS flags } genome { COUNTS flags }
  joint { COUNTS freq_comparison_stats {
    contingency_table_test { p_value odds_ratio }
    cochran_mantel_haenszel_test { chisq p_value }
    stat_union { p_value stat_test_name gen_ancs }
  } }
""".replace("COUNTS", _COUNTS)
GRAPHQL_QUERY = """
query VariantFrequency($variantId: String!, $datasetId: DatasetId!) {
  variant(variantId: $variantId, dataset: $datasetId) { FIELDS }
}
""".replace("FIELDS", _VARIANT_FIELDS)

REGION_VARIANTS_QUERY = """
query RegionVariants(
  $chrom: String!, $start: Int!, $stop: Int!,
  $datasetId: DatasetId!, $referenceGenome: ReferenceGenomeId!
) {
  region(
    chrom: $chrom, start: $start, stop: $stop,
    reference_genome: $referenceGenome
  ) {
    variants(dataset: $datasetId) {
      variant_id pos ref alt
      genome { ac an }
      exome { ac an }
    }
  }
}
"""


class GnomadFrequencyError(RuntimeError):
    pass


def cache_path():
    configured = os.environ.get("HELPER_GNOMAD_FREQUENCY_CACHE", "").strip()
    if configured:
        return Path(configured).expanduser()
    data_home = os.environ.get("XDG_DATA_HOME", "").strip()
    root = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return root / "helper_variants" / "gnomad_frequency.sqlite3"


def cache_status(database=None):
    """Describe the immutable-release cache without making a network request."""
    database = Path(database or cache_path())
    context = dict(target_release=FREQUENCY_RELEASE, assembly="GRCh38", access_mode="graphql_alias_batches",
                   products=list(PRODUCTS), parser_version=PARSER_VERSION)
    if not database.is_file():
        return {
            "status": "missing", "database": str(database), "record_count": 0,
            "synchronized_at": "", "releases": [], **context,
        }
    try:
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
            count, latest = connection.execute(
                "SELECT COUNT(*), COALESCE(MAX(retrieved_at), '') FROM frequencies"
            ).fetchone()
            releases = [row[0] for row in connection.execute(
                "SELECT DISTINCT release FROM frequencies ORDER BY release"
            )]
            latest_row = connection.execute("SELECT payload FROM frequencies ORDER BY retrieved_at DESC LIMIT 1").fetchone()
            latest_error = json.loads(latest_row[0]).get("error") if latest_row else None
            current_count = connection.execute("SELECT COUNT(*) FROM frequencies WHERE release=?", (FREQUENCY_RELEASE,)).fetchone()[0]
    except (sqlite3.Error, ValueError, AttributeError) as exc:
        return {
            "status": "invalid", "database": str(database), "record_count": 0,
            "synchronized_at": "", "releases": [], "error": str(exc), **context,
        }
    return {
        "status": "ready", "database": str(database), "record_count": int(count or 0),
        "synchronized_at": str(latest or ""), "releases": releases, **context,
        "current_release_record_count": current_count, "error": latest_error,
    }


def _offline():
    return os.environ.get("HELPER_GNOMAD_OFFLINE", "").strip().lower() in ("1", "true", "yes")


def _identity_allele(identity):
    return _allele(identity["assembly"], identity["chromosome"], identity["position"],
                   identity["reference"], identity["alternate"])


def _lookup_identity(allele, normalization="AS_SUPPLIED"):
    """Describe a lookup address without claiming local REF/ga2 verification."""
    return {
        "status": "RESOLVED", "allele_ref": None,
        "identity": dict(zip(("assembly", "chromosome", "position", "reference", "alternate"), allele)),
        "reason": "Lookup allele supplied by the analysis or assembly projection; no local FASTA check.",
        "reference_provenance": {
            "source_file": None, "digest": None, "ref_status": "NOT_CHECKED",
            "normalization": normalization,
        },
    }


def _supplied_target(original, metadata):
    """Require an entire, source-bound hg38 allele; coordinates alone never qualify."""
    if not metadata:
        return None
    allele = _allele(*original)
    resolution = ((metadata.get("gnomad_enrichment") or {}).get("identity_resolution") or {})
    target = resolution.get("target_identity") or {}
    try:
        if (target.get("status") == "RESOLVED" and _allele(*resolution["original"]) == allele):
            supplied = _identity_allele(target["identity"])
            if supplied[0] == "GRCh38":
                attached_key = (metadata.get("gnomad_enrichment") or {}).get("cache_key")
                if attached_key and attached_key != cache_key(*supplied):
                    return None
                return supplied
    except (TypeError, ValueError, KeyError):
        pass
    vcf = metadata.get("original_vcf") or {}
    try:
        if _allele(allele[0], vcf["chromosome"], vcf["position"], vcf["reference"], vcf["alternate"]) != allele:
            return None
        fields = {str(k).upper(): v for k, v in (vcf.get("info") or {}).items()}
        index = int(vcf.get("alt_index", 1)) - 1
        def selected(value):
            parts = str(value).split(",")
            if len(parts) > 1:
                if len(parts) != len(vcf.get("alternates") or []):
                    raise ValueError("Projection must contain one complete allele per ALT")
                return parts[index]
            if len(vcf.get("alternates") or []) > 1:
                raise ValueError("Multiallelic projection requires per-ALT values")
            return parts[0]
        for prefix in ("HG38", "GRCH38"):
            names = [prefix + "_" + name for name in ("CHROM", "POS", "REF", "ALT")]
            if all(name in fields for name in names):
                return _allele("GRCh38", *(selected(fields[name]) for name in names))
            if prefix in fields:
                parts = selected(fields[prefix]).split(":")
                if len(parts) == 4:
                    return _allele("GRCh38", *parts)
    except (TypeError, ValueError, KeyError, IndexError):
        pass
    return None


def _resolve_one(original, metadata=None, *, fetch=True, timeout=12):
    from helper_variants import liftover
    context = {"original": list(original)}
    try:
        allele = _allele(*original)
        context["source_identity"] = _lookup_identity(allele)
        if allele[0] == "GRCh37":
            supplied = _supplied_target(original, metadata)
            if supplied is not None:
                context["target_identity"] = _lookup_identity(supplied, "SUPPLIED_ASSEMBLY_PROJECTION")
                return [supplied, context]
            projection = (liftover.project_variant(*allele, timeout=timeout) if fetch and not _offline()
                          else liftover._cached(liftover.cache_path(), "|".join(map(str, allele))))
            context["projection"] = projection
            if not projection or projection.get("status") != "mapped":
                state = (projection or {}).get("status", "unavailable")
                context.update(status="unavailable" if state == "unavailable" else "unsupported",
                               message="GRCh38 projection: " + state)
                return [None, context]
            fields = ("reference_build", "chromosome", "position", "reference", "alternate")
            if _allele(*(projection.get("source", {}).get(k) for k in fields)) != allele:
                raise ValueError("Projection source allele mismatch")
            allele = _allele(*(projection.get("target", {}).get(k) for k in fields))
            if allele[0] != "GRCh38":
                raise ValueError("Projection did not identify a GRCh38 allele")
            context["target_identity"] = _lookup_identity(allele, "ASSEMBLY_PROJECTION")
        else:
            context["target_identity"] = context["source_identity"]
        return [allele, context]
    except (ValueError, TypeError, KeyError) as exc:
        context.update(status="unsupported", message=str(exc))
        return [None, context]


def _iter_resolutions(alleles, metadata, *, fetch=True, timeout=12):
    # Three futures at most; do not queue an entire run in RAM or on shutdown.
    items = iter(zip(alleles, metadata))
    parallel = fetch and not _offline() and len(alleles) > 1 and any(
        str(a[0]).lower() not in ("grch38", "hg38", "38") for a in alleles)
    if not parallel:
        for original, attached in items:
            yield _resolve_one(original, attached, fetch=fetch, timeout=timeout)
        return
    pending = deque()
    def submit_next():
        item = next(items, None)
        if item is not None:
            pending.append(_projection_pool.submit(_resolve_one, *item, fetch=fetch, timeout=timeout))
    try:
        for _ in range(3):
            submit_next()
        while pending:
            result = pending.popleft().result()
            submit_next()
            yield result
    finally:
        for future in pending:
            future.cancel()


def resolve_alleles(alleles, *, record=None, fetch=True, timeout=12, metadata=None):
    """Use submitted VCF alleles and the existing projection, without local FASTA I/O.

    The submitting analysis owns REF correctness and normalization. These lookup
    addresses do not assert a reference-verified biological identity.
    """
    alleles = list(alleles)
    metadata = list(metadata) if metadata is not None else [None] * len(alleles)
    if len(metadata) != len(alleles):
        raise ValueError("One metadata entry is required per allele")
    return list(_iter_resolutions(alleles, metadata, fetch=fetch, timeout=timeout))


def lookup_variant(reference_build, chromosome, position, reference, alternate,
                   database=None, timeout=12, *, record=None, metadata=None, include_non_ukb=True):
    return lookup_variants([(reference_build, chromosome, position, reference, alternate)],
                           database=database, timeout=timeout, record=record,
                           metadata=[metadata], include_non_ukb=include_non_ukb)[0]


def _reusable(result, *, include_non_ukb=True):
    if not result:
        return False
    if result.get("error") == "Incomplete GraphQL response":
        # Retry responses whose aliases belonged to a different HTTP request.
        return False
    if include_non_ukb and result.get("non_ukb_pending"):
        acquired = result.get("non_ukb_attempted_at")
        try:
            if (datetime.now(timezone.utc) - datetime.fromisoformat(acquired)).total_seconds() < ERROR_RETRY_SECONDS:
                return True
        except (TypeError, ValueError):
            pass
        return False
    if result.get("availability") == "AVAILABLE" and not result.get("partial") and result.get("parser_version") == PARSER_VERSION:
        return True
    try:
        acquired = datetime.fromisoformat(result["retrieved_at"].replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - acquired).total_seconds() < ERROR_RETRY_SECONDS
    except (ValueError, KeyError, TypeError):
        return False


def _priority_signature(result):
    if not result:
        return None
    region = dict(result.get("region_coverage") or {})
    region.pop("retrieved_at", None)
    return json.dumps({key: result.get(key) for key in (
        "datasets", "variant_flags", "retrieval_status", "status", "error", "partial")},
        sort_keys=True, default=str) + json.dumps(region, sort_keys=True, default=str)


def _acquire_frequency_batch(alleles, database, timeout, include_non_ukb):
    keys = [cache_key(*a) for a in alleles]
    before = _cached_many(database, keys)
    def acquire(owned):
        # Recheck after claiming: a competing request may just have stored data.
        cached = _cached_many(database, [key[1] for key in owned])
        output, pending = {}, []
        for key in owned:
            current = cached.get(key[1])
            if _reusable(current, include_non_ukb=include_non_ukb):
                output[key] = current
            elif _offline():
                output[key] = current or _empty_result("unavailable", DATASETS["GRCh38"],
                    by_key[key[1]], cache="miss", message="gnomAD offline; no valid cached result.")
            else:
                pending.append(key)
        if pending:
            fetched = _fetch_batch([by_key[key[1]] for key in pending], timeout,
                                   include_non_ukb=include_non_ukb)
            for key, value in zip(pending, fetched):
                old = cached.get(key[1]) or {}
                if old.get("region_coverage") and not value.get("region_coverage"):
                    value["region_coverage"] = old["region_coverage"]
                subset = (old.get("subsets") or {}).get("non_ukb") or {}
                if value.get("non_ukb_pending") and subset.get("availability") == "AVAILABLE":
                    value.setdefault("subsets", {})["non_ukb"] = subset
                    value["non_ukb_pending"] = False
            _store_many(database, [(key[1], value) for key, value in zip(pending, fetched)])
            output.update(zip(pending, fetched))
        if not _offline():
            coverage_pending = [key for key in owned if _needs_region_coverage(output[key])]
            for offset in range(0, len(coverage_pending), 2):
                batch = coverage_pending[offset:offset + 2]
                coverages = _fetch_region_coverages([by_key[key[1]] for key in batch], timeout)
                for key, coverage in zip(batch, coverages):
                    output[key].update(region_coverage=coverage, cache="miss")
                _store_many(database, [(key[1], output[key]) for key in batch])
        return output
    by_key = dict(zip(keys, alleles))
    flights = [(str(database.resolve()), key) for key in keys]
    acquired = frequency_flights.batch(flights, acquire)
    # A main-only owner can finish while a detail caller waits on the same flight.
    missing_optional = [key for key in flights if include_non_ukb
                        and not _reusable(acquired[key], include_non_ukb=True)
                        and acquired[key].get("non_ukb_pending")
                        and not acquired[key].get("non_ukb_attempted_at")]
    if missing_optional and not _offline():
        acquired.update(frequency_flights.batch(missing_optional, acquire))
    output = {}
    for key, allele in zip(keys, alleles):
        value = acquired[(str(database.resolve()), key)]
        value["priority_evidence_changed"] = _priority_signature(value) != _priority_signature(before.get(key))
        output[allele] = value
    return output


def lookup_variants(alleles, database=None, timeout=12, *, record=None, batch_size=10,
                    metadata=None, include_non_ukb=True):
    """Bounded pipeline: share active work; priority needs only the full cohort."""
    database = Path(database or cache_path())
    inputs = [tuple(a) for a in alleles]
    originals = list(dict.fromkeys(inputs))
    metadata = list(metadata) if metadata is not None else [None] * len(inputs)
    if len(metadata) != len(inputs):
        raise ValueError("One metadata entry is required per allele")
    attached = {}
    for original, data in zip(inputs, metadata):
        if data or original not in attached:
            attached[original] = data
    resolved_items = iter(zip(originals, _iter_resolutions(
        originals, [attached[a] for a in originals], timeout=timeout)))
    output, resolution_map = {}, {}
    width = max(1, min(int(batch_size), 12 if include_non_ukb else 24))
    while True:
        items = list(islice(resolved_items, width))
        if not items:
            break
        resolution_map.update(items)
        unique = list(dict.fromkeys(value[0] for _, value in items if value[0] is not None))
        output.update(_acquire_frequency_batch(unique, database, timeout, include_non_ukb))
    results = []
    for original in inputs:
        allele, resolution = resolution_map[original]
        result = copy.deepcopy(output[allele]) if allele is not None else _empty_result(
            resolution.get("status", "unsupported"), message=resolution.get("message", ""))
        result["identity_resolution"] = resolution
        results.append(_access_metadata(result))
    return results


def _needs_region_coverage(result):
    if (result.get("retrieval_status") != "NOT_FOUND" or result.get("error")
            or result.get("partial") or result.get("availability") != "AVAILABLE"):
        return False
    coverage = result.get("region_coverage") or {}
    if (coverage.get("policy_version") != REGION_COVERAGE_POLICY
            or coverage.get("flank") != REGION_COVERAGE_FLANK
            or coverage.get("maximum_span") != REGION_COVERAGE_MAX_SPAN
            or coverage.get("minimum_mean") != MIN_MEAN_COVERAGE
            or coverage.get("minimum_over_20") != MIN_OVER_20):
        return True
    if coverage.get("status") != "ERROR":
        return False
    try:
        acquired = datetime.fromisoformat(coverage["retrieved_at"].replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - acquired).total_seconds() >= ERROR_RETRY_SECONDS
    except (ValueError, KeyError, TypeError):
        return True


def _region_coverage_context(allele):
    _, chromosome, position, reference, alternate = allele
    # Include both sides of an insertion as well as the full deleted REF span.
    locus_end = position + len(reference) - 1 + (len(alternate) > len(reference))
    return {
        "policy_version": REGION_COVERAGE_POLICY, "status": "UNAVAILABLE",
        "reference_build": "GRCh38", "chromosome": chromosome,
        "start": max(1, position - REGION_COVERAGE_FLANK),
        "stop": locus_end + REGION_COVERAGE_FLANK,
        "locus_start": position, "locus_stop": locus_end,
        "flank": REGION_COVERAGE_FLANK,
        "maximum_span": REGION_COVERAGE_MAX_SPAN,
        "minimum_mean": MIN_MEAN_COVERAGE, "minimum_over_20": MIN_OVER_20,
        "datasets": {}, "adequate_datasets": [], "absence_verified": False,
        "site_an_available": False, "source_url": API_URL,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


def _summarize_region_coverage(rows, context):
    """Require complete per-base evidence; never infer missing bases or site AN."""
    start, stop = context["start"], context["stop"]
    expected = stop - start + 1
    by_position = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        position = _integer(row.get("pos"))
        if position is None or not start <= position <= stop:
            continue  # The official API includes additional flanking positions.
        mean, over_20 = _number(row.get("mean")), _number(row.get("over_20"))
        if mean is None or mean < 0 or over_20 is None or not 0 <= over_20 <= 1:
            continue
        if position in by_position:
            raise GnomadFrequencyError("Duplicate regional coverage position")
        by_position[position] = (mean, over_20)
    passing = {p for p, (m, f) in by_position.items() if m >= MIN_MEAN_COVERAGE and f >= MIN_OVER_20}
    locus = set(range(context["locus_start"], context["locus_stop"] + 1))
    status = ("UNAVAILABLE" if not by_position else "INCOMPLETE" if len(by_position) != expected
              else "ADEQUATE" if len(passing) == expected else "LOW")
    return {
        "status": status, "available": bool(by_position), "adequate": status == "ADEQUATE",
        "positions_evaluated": len(by_position), "positions_expected": expected,
        "mean": sum(m for m, _ in by_position.values()) / len(by_position) if by_position else None,
        "mean_min": min((m for m, _ in by_position.values()), default=None),
        "over_20_min": min((f for _, f in by_position.values()), default=None),
        "fraction_bases_adequate": len(passing) / expected,
        "locus_status": "INCOMPLETE" if not locus <= by_position.keys() else
                        "ADEQUATE" if locus <= passing else "LOW",
    }


def _apply_region_coverage(context, coverage, sources=None):
    for name, field, source in (("exomes", "exome", "gnomAD v4 exome coverage"),
                                ("genomes", "genome", "gnomAD v3 genome coverage used by the v4 browser")):
        provenance = (sources or {}).get(field, {})
        context["datasets"][name] = dict(_summarize_region_coverage(coverage.get(field), context),
                                         source=provenance.get("source", source))
        if provenance:
            context["datasets"][name]["source_files"] = provenance
    context["adequate_datasets"] = [n for n, c in context["datasets"].items() if c["adequate"]]
    statuses = {c["status"] for c in context["datasets"].values()}
    context["status"] = ("ADEQUATE" if context["adequate_datasets"] else "INCOMPLETE" if "INCOMPLETE" in statuses
                         else "LOW" if "LOW" in statuses else "UNAVAILABLE")


def _fetch_region_coverages(alleles, timeout):
    contexts = [_region_coverage_context(a) for a in alleles]
    fields, variables, declarations = [], {}, []
    pending, indexed = [], {}
    for i, context in enumerate(contexts):
        if context["stop"] - context["start"] + 1 > REGION_COVERAGE_MAX_SPAN:
            context.update(status="UNSUPPORTED", error="Regional coverage window exceeds the per-base limit")
            continue
        result = gnomad_coverage.read_region(context["chromosome"], context["start"], context["stop"])
        indexed[i] = result
        if result.get("data"):
            _apply_region_coverage(context, result["data"], result.get("sources"))
        if all(name in result.get("data", {}) for name in ("exome", "genome")):
            continue
        declarations.extend((f"$chrom{i}: String!", f"$start{i}: Int!", f"$stop{i}: Int!"))
        variables.update({f"chrom{i}": context["chromosome"], f"start{i}": context["start"], f"stop{i}": context["stop"]})
        fields.append(f"coverage{i}: region(chrom: $chrom{i}, start: $start{i}, stop: $stop{i}, reference_genome: GRCh38) "
                      "{ chrom start stop reference_genome coverage(dataset: gnomad_r4) "
                      "{ exome { pos mean over_20 } genome { pos mean over_20 } } }")
        pending.append(i)
    if not pending:
        return contexts
    try:
        response = _request_graphql("query RegionCoverage(" + ",".join(declarations) + ") {" + " ".join(fields) + "}", variables, timeout)
    except (GnomadFrequencyError, HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        for i in pending:
            contexts[i]["error"] = str(exc)
            if not indexed[i].get("data"):
                contexts[i]["status"] = "ERROR"
        return contexts
    for i in pending:
        context, alias = contexts[i], f"coverage{i}"
        try:
            errors = [e for e in response.get("errors", []) if not e.get("path") or e["path"][0] == alias]
            region = (response.get("data") or {}).get(alias)
            if errors or not isinstance(region, dict):
                raise GnomadFrequencyError("; ".join(str(e.get("message", e)) for e in errors) or "Regional coverage unavailable")
            if (region.get("chrom"), region.get("start"), region.get("stop"), region.get("reference_genome")) != (
                    context["chromosome"], context["start"], context["stop"], "GRCh38"):
                raise GnomadFrequencyError("gnomAD returned a different coverage region/assembly")
            coverage = dict(region.get("coverage") or {})
            coverage.update(indexed[i].get("data", {}))
            _apply_region_coverage(context, coverage, indexed[i].get("sources"))
        except (GnomadFrequencyError, TypeError, ValueError, AttributeError) as exc:
            context["error"] = str(exc)
            if not indexed[i].get("data"):
                context.update(status="ERROR", datasets={}, adequate_datasets=[])
    return contexts


def _fetch_batch(alleles, timeout, *, include_non_ukb=True):
    fields, variables, declarations = [], {}, []
    requested_subsets = ("all", "non_ukb") if include_non_ukb else ("all",)
    for i, (_, chrom, pos, ref, alt) in enumerate(alleles):
        declarations.append(f"$id{i}: String!")
        variables[f"id{i}"] = f"{chrom}-{pos}-{ref}-{alt}"
        for subset, dataset in (("all", "gnomad_r4"), ("non_ukb", "gnomad_r4_non_ukb")):
            if subset not in requested_subsets:
                continue
            fields.append(f"v{i}_{subset}: variant(variantId: $id{i}, dataset: {dataset}) {{ {_VARIANT_FIELDS} }}")
    query = "query Frequencies(" + ",".join(declarations) + ") {" + " ".join(fields) + "}"
    try:
        response = _request_graphql(query, variables, timeout)
    except (GnomadFrequencyError, HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        return [_empty_result("unavailable", DATASETS["GRCh38"], a, cache="miss", error=str(exc)) for a in alleles]
    results = []
    for i, allele in enumerate(alleles):
        subsets, errors = {}, []
        for subset in requested_subsets:
            alias = f"v{i}_{subset}"
            scoped = [e for e in response.get("errors", []) if not e.get("path") or e["path"][0] == alias]
            data = response.get("data") or {}
            # Some deployed API errors omit GraphQL paths; don't convert such errors to absence.
            unexpected = [e for e in scoped if "variant not found" not in str(e.get("message", "")).lower()]
            if alias not in data or unexpected:
                errors.extend(str(e.get("message", e)) for e in unexpected)
                subsets[subset] = _empty_result("unavailable", DATASETS["GRCh38"], allele,
                    error="; ".join(errors) or "Incomplete GraphQL response")
                continue
            try:
                subsets[subset] = _parse_response({"data": {"variant": data[alias]}}, DATASETS["GRCh38"], allele, "")
            except (GnomadFrequencyError, TypeError, ValueError) as exc:
                subsets[subset] = _empty_result("unavailable", DATASETS["GRCh38"], allele, error=str(exc))
        result = subsets.pop("all")
        result["subsets"] = subsets
        result["non_ukb_pending"] = not include_non_ukb or subsets["non_ukb"]["availability"] != "AVAILABLE"
        if include_non_ukb and result["non_ukb_pending"]:
            result["non_ukb_attempted_at"] = datetime.now(timezone.utc).isoformat()
            result["subset_errors"] = {"non_ukb": subsets["non_ukb"].get("error") or "Non-UKB unavailable"}
        result["cache"] = "miss"
        results.append(result)
    return results


def region_variants(reference_build, chromosome, start, end, timeout=12):
    """Return compact IGV features for variants in one visible genomic window."""
    if os.environ.get("HELPER_GNOMAD_OFFLINE", "").strip().lower() in ("1", "true", "yes"):
        raise GnomadFrequencyError("gnomAD is disabled in offline mode.")
    build, normalized_chromosome = _reference_context(reference_build, chromosome)
    start, end = int(start), int(end)
    if start < 1 or end < start or end - start > 100_000:
        raise ValueError("gnomAD track windows must span 1-100000 bases.")
    if build != "GRCh38":
        raise GnomadFrequencyError("The v4 regional track requires a GRCh38 window.")
    dataset = DATASETS[build]
    variables = {
        "chrom": normalized_chromosome, "start": start, "stop": end,
        "datasetId": dataset["id"], "referenceGenome": dataset["reference_genome"],
    }
    try:
        response = _request_graphql(REGION_VARIANTS_QUERY, variables, timeout)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise GnomadFrequencyError("gnomAD regional variants are temporarily unavailable.") from exc

    rows = ((((response.get("data") or {}).get("region") or {}).get("variants")) or [])
    display_chromosome = str(chromosome or "").strip()
    features = []
    for row in rows:
        position = _integer(row.get("pos"))
        reference = str(row.get("ref") or "").upper()
        alternate = str(row.get("alt") or "").upper()
        if position is None or not reference or not alternate:
            continue
        genome = row.get("genome") or {}
        exome = row.get("exome") or {}
        genome_ac, genome_an = _integer(genome.get("ac")), _integer(genome.get("an"))
        exome_ac, exome_an = _integer(exome.get("ac")), _integer(exome.get("an"))
        genome_af = _frequency(genome_ac, genome_an)
        exome_af = _frequency(exome_ac, exome_an)
        frequencies = [value for value in (genome_af, exome_af) if value is not None]
        frequency = max(frequencies) if frequencies else None
        variant_id = str(row.get("variant_id") or (
            f"{normalized_chromosome}-{position}-{reference}-{alternate}"
        ))
        features.append({
            "chr": display_chromosome, "start": position - 1,
            "end": position - 1 + max(1, len(reference)),
            "name": f"{reference}>{alternate} · AF {_format_frequency(frequency)}",
            "variant_id": variant_id, "position": position,
            "reference": reference, "alternate": alternate,
            "af": frequency, "genome_af": genome_af, "genome_ac": genome_ac,
            "genome_an": genome_an, "exome_af": exome_af, "exome_ac": exome_ac,
            "exome_an": exome_an, "release": dataset["release"],
            "source": f"gnomAD v{dataset['release']}",
            "url": f"{SOURCE_URL}variant/{variant_id}?dataset={dataset['id']}",
        })
    return features


def _metadata_key(allele, metadata=None):
    if _allele(*allele)[0] == "GRCh37":
        target = _supplied_target(allele, metadata)
        if target is not None:
            return cache_key(*target)
    return cache_key(*allele)


def cached_variant(reference_build, chromosome, position, reference, alternate, database=None, *, metadata=None):
    """Return the full existing allele-specific lookup, without a network request."""
    try:
        key = _metadata_key((reference_build, chromosome, position, reference, alternate), metadata)
    except (TypeError, ValueError):
        return None
    result = _cached(Path(database or cache_path()), key)
    return result


def _matches_context(result, key):
    """Validate payload identity AND configured release against the old key."""
    if not isinstance(result, dict):
        return False
    try:
        stored_key = cache_key(*(result.get(k) for k in (
            "reference_build", "chromosome", "position", "reference", "alternate"
        )))
    except (TypeError, ValueError):
        return False
    dataset = DATASETS.get(key.split("|")[1], {})
    return (stored_key == key and result.get("dataset") == dataset["id"]
            and result.get("release") == dataset.get("release")
            and result.get("parser_version") == PARSER_VERSION)


def cached_context(reference_build, chromosome, position, reference, alternate, database=None):
    """Return priority-engine fields for an already cached exact allele only."""
    return priority_context(cached_variant(
        reference_build, chromosome, position, reference, alternate, database
    ))


def _cached_many(database, keys, *, priority_only=False):
    payloads = {}
    keys = list(dict.fromkeys(k for k in keys if k))
    if not database.is_file():
        return payloads
    try:
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
            for offset in range(0, len(keys), 500):
                batch = keys[offset:offset + 500]
                for key, payload, release, acquired in connection.execute(
                    "SELECT cache_key,payload,release,retrieved_at FROM frequencies WHERE cache_key IN ("
                    + ",".join("?" for _ in batch) + ")", batch):
                    parsed = _parse_cached(payload, key, release, acquired)
                    if parsed is not None:
                        if priority_only:
                            # Existing full-detail cache entries can be large.
                            # Priority uses main datasets; the root population
                            # rows duplicate the genome rows already in datasets.
                            parsed.pop("subsets", None)
                            parsed.pop("populations", None)
                        payloads[key] = parsed
    except sqlite3.Error:
        pass
    return payloads


def cached_variants(alleles, database=None, *, metadata=None, priority_only=False):
    """Read full cached results in input order without fetching or projecting."""
    keys = []
    alleles = list(alleles)
    metadata = list(metadata) if metadata is not None else [None] * len(alleles)
    if len(metadata) != len(alleles):
        raise ValueError("One metadata entry is required per allele")
    for allele, attached in zip(alleles, metadata):
        try:
            keys.append(_metadata_key(allele, attached))
        except (TypeError, ValueError):
            keys.append("")
    payloads = _cached_many(Path(database or cache_path()), keys, priority_only=priority_only)
    return [payloads.get(key) for key in keys]


def cached_contexts(alleles, database=None, *, metadata=None, scoring_version=None):
    """Local-only batch reads; no normalization fetches or liftover requests."""
    return [priority_context(result, scoring_version=scoring_version)
            for result in cached_variants(alleles, database, metadata=metadata, priority_only=True)]


def priority_context(result, *, scoring_version=None):
    """Translate a frequency result into conservative priority-engine evidence."""
    if not result:
        return {}
    if scoring_version in {"germline-wes-v2.0.0", "germline-wes-v2.1.0", "germline-wes-v2.2.0"}:
        # Internal input only; the scorer emits selected metrics, not this payload.
        return {"population_frequency_evidence": result}
    status = str(result.get("status") or "")
    context = {
        "population_frequency_status": status,
        "population_frequency_source": "gnomAD genomes v{}".format(result.get("release") or ""),
    }
    coverage = result.get("coverage") or {}
    context["population_coverage_available"] = bool(coverage.get("available"))
    context["population_coverage_adequate"] = bool(coverage.get("adequate"))
    qc_known = not result.get("datasets") or result["datasets"]["genomes"].get("filters") is not None
    if status == "observed" and qc_known and not result.get("filters"):
        values = [result.get("af"), result.get("max_population_af")]
        numeric = [float(value) for value in values if value is not None]
        if numeric:
            context["population_af"] = max(numeric)
        genome = (result.get("datasets") or {}).get("genomes") or {}
        faf = genome.get("grpmax_faf95", result.get("grpmax_faf95"))
        if faf is not None:
            context["population_faf"] = float(faf)
    elif status == "not_observed_covered":
        context.update({
            "population_absent": True,
            "population_coverage_adequate": True,
        })
        genome = (result.get("datasets") or {}).get("genomes") or {}
        faf = genome.get("grpmax_faf95", result.get("grpmax_faf95"))
        if faf is not None:
            context["population_faf"] = float(faf)
    return context


def cache_key(reference_build, chromosome, position, reference, alternate):
    allele = _allele(reference_build, chromosome, position, reference, alternate)
    if allele[0] == "GRCh37":
        from helper_variants import liftover
        projection = liftover._cached(liftover.cache_path(), "|".join(map(str, allele)))
        if not projection or projection.get("status") != "mapped":
            raise ValueError("No cached, unambiguous GRCh38 allelic projection")
        target = projection.get("target") or {}
        source = projection.get("source") or {}
        fields = ("reference_build", "chromosome", "position", "reference", "alternate")
        if _allele(*(source.get(k) for k in fields)) != allele:
            raise ValueError("Cached projection source allele mismatch")
        allele = _allele(*(target.get(k) for k in fields))
        if allele[0] != "GRCh38":
            raise ValueError("Cached projection target must be GRCh38")
    return "|".join((DATASETS["GRCh38"]["id"] + "@" + FREQUENCY_RELEASE, *map(str, allele)))


def _counts(raw):
    ac, an = _integer(raw.get("ac")), _integer(raw.get("an"))
    if ac is not None and ac < 0 or an is not None and an < 0 or ac is not None and an is not None and ac > an:
        raise GnomadFrequencyError("Invalid gnomAD allele counts")
    return {"ac": ac, "an": an, "af": _frequency(ac, an),
            "ac_hom": _integer(raw.get("homozygote_count", raw.get("ac_hom"))),
            "ac_hemi": _integer(raw.get("hemizygote_count", raw.get("ac_hemi")))}


def _product(raw, coverage=None):
    result = dict(_counts(raw or {}), presence="NOT_OBSERVED" if raw is None else "PRESENT",
                  filters=None, filter=None, flags=[], populations=[], grpmax_faf95=None,
                  grpmax_faf95_population=None, grpmax_faf99=None, grpmax_faf99_population=None,
                  coverage=_coverage(coverage), quality_metrics=None)
    if raw is None:
        return result  # No variant is a presence state, never a QC filter or AF=0.
    filters = raw.get("filters")
    result.update(filters=filters, filter=(";".join(filters) if filters else "PASS") if filters is not None else None,
                  flags=raw.get("flags") or [], quality_metrics=raw.get("quality_metrics"),
                  freq_comparison_stats=raw.get("freq_comparison_stats"))
    for suffix in ("95", "99"):
        faf = raw.get("faf" + suffix) or {}
        result["grpmax_faf" + suffix] = _number(faf.get("popmax"))
        result["grpmax_faf" + suffix + "_population"] = faf.get("popmax_population")
    for population in raw.get("populations") or []:
        result["populations"].append(dict(_counts(population), id=str(population["id"]),
            faf95=None, faf99=None, status="observed" if population.get("ac") else
            "not_observed" if population.get("an") else "not_covered"))
    return result


def _parse_response(response, dataset, allele, source_url):
    data = response.get("data") or {}
    if not isinstance(data, dict) or "variant" not in data:
        raise GnomadFrequencyError("Invalid gnomAD allele response")
    variant = data["variant"]
    base = _empty_result("not_observed_coverage_unknown", dataset, allele, source_url)
    if variant is not None:
        expected = f"{allele[1]}-{allele[2]}-{allele[3]}-{allele[4]}"
        if variant.get("variant_id") != expected:
            raise GnomadFrequencyError("gnomAD returned a different allele")
        if variant.get("reference_genome", "GRCh38") != "GRCh38":
            raise GnomadFrequencyError("gnomAD returned a different assembly")
        for name, expected_value in zip(("chrom", "pos", "ref", "alt"), allele[1:]):
            if name in variant and variant[name] != expected_value:
                raise GnomadFrequencyError("gnomAD allele fields disagree")
    coverage = (variant or {}).get("coverage") or {}
    base["datasets"] = {product: _product((variant or {}).get(field), coverage.get(field))
                        for product, field in PRODUCTS.items()}
    genome = base["datasets"]["genomes"]
    # Prioritization uses genomes-only AF/FAF95; this is not clinical classification.
    base.update({k: genome[k] for k in ("ac", "an", "af", "ac_hom", "ac_hemi", "flags", "populations", "coverage")})
    base["filters"] = genome["filters"] if genome["filters"] is not None else []
    base["variant_flags"] = (variant or {}).get("flags") or []
    frequencies = [p["af"] for p in genome["populations"] if p["id"] in MAJOR_POPULATIONS and p["af"] is not None]
    base["max_population_af"] = max(frequencies) if frequencies else None
    if genome["ac"] is not None and genome["ac"] > 0 and genome["an"]:
        base["status"] = "observed"
    elif (
        genome["ac"] == 0 and genome["an"] and genome["filters"] == []
        and genome["coverage"]["adequate"]
    ):
        base["status"] = "not_observed_covered"
        base["population_absent"] = True
        base["population_coverage_adequate"] = True
    base["retrieval_status"] = "FOUND" if variant is not None else "NOT_FOUND"
    base["message"] = "" if variant is not None else "Allele not observed; all-sites AN is unavailable through GraphQL."
    # Coverage alone is not an allele-specific denominator; never fabricate zero.
    base["source_url"] = source_url or f"{SOURCE_URL}variant/{allele[1]}-{allele[2]}-{allele[3]}-{allele[4]}?dataset=gnomad_r4"
    base["limitations"] = ["Per-population FAF95/99 and all-sites AN are not exposed by this GraphQL schema.",
        "API dataset ID has no machine-readable release token; release is qualified by official download/source metadata."]
    return _access_metadata(base)


def _coverage(raw):
    if not raw:
        return {
            "available": False, "adequate": False,
            "minimum_mean": MIN_MEAN_COVERAGE, "minimum_over_20": MIN_OVER_20,
        }
    mean = _number(raw.get("mean"))
    over_20 = _number(raw.get("over_20"))
    return {
        "available": mean is not None or over_20 is not None,
        "mean": mean, "median": _number(raw.get("median")), "over_20": over_20,
        "adequate": bool(
            mean is not None and mean >= MIN_MEAN_COVERAGE
            and over_20 is not None and over_20 >= MIN_OVER_20
        ),
        "minimum_mean": MIN_MEAN_COVERAGE, "minimum_over_20": MIN_OVER_20,
    }


def _empty_result(status, dataset=None, allele=None, source_url=SOURCE_URL,
                  cache="", message="", error=""):
    dataset = dataset or {}
    build, chromosome, position, reference, alternate = allele or ("", "", None, "", "")
    return _access_metadata({
        "status": status, "dataset": dataset.get("id", ""),
        "release": dataset.get("release", ""), "data_type": "genomes",
        "parser_version": PARSER_VERSION,
        "retrieval_status": "UNSUPPORTED" if status == "unsupported" else "UNAVAILABLE" if status == "unavailable" else "NOT_FOUND",
        "provenance": {"url": API_URL, "release_basis": "official_gnomad_downloads",
                       "release_verified_in_response": False, "assembly": "GRCh38"},
        "reference_build": build, "chromosome": chromosome, "position": position,
        "reference": reference, "alternate": alternate,
        "ac": None, "an": None, "af": None, "ac_hom": None, "ac_hemi": None,
        "filters": [], "populations": [], "max_population_af": None,
        "coverage": {}, "population_absent": False,
        "population_coverage_adequate": False,
        "source_url": source_url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "cache": cache, "message": message, "error": error,
    })


def _access_metadata(result):
    result = dict(result)
    status = result.get("status")
    result.setdefault("retrieval_status", "FOUND" if status == "observed" else
                      "UNSUPPORTED" if status == "unsupported" else "NOT_FOUND" if
                      str(status).startswith("not_observed") else "UNAVAILABLE")
    result["source"] = "gnomAD"
    result["availability"] = (
        "AVAILABLE" if status in (
            "observed", "not_observed_covered", "not_observed_low_coverage",
            "not_observed_coverage_unknown",
        ) else "UNSUPPORTED" if status == "unsupported"
        else "ERROR" if result.get("error") else "NOT_QUERIED"
    )
    # Release-qualified data has no time TTL. This is not a live release check.
    result["freshness"] = "FRESH" if result["availability"] == "AVAILABLE" and result.get("release") else "UNKNOWN"
    result["last_error"] = result.get("error") or None
    result["region_coverage_pending"] = _needs_region_coverage(result)
    return result


def _request_graphql(query, variables, timeout):
    body = json.dumps({"query": query, "variables": variables}, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    # Qualify the HTTP cache identity by the complete POST payload. The shared
    # endpoint has returned cached aliases from unrelated queries in production.
    separator = "&" if "?" in API_URL else "?"
    request_url = API_URL + separator + "request=" + hashlib.sha256(body).hexdigest()
    request = Request(
        request_url, data=body, method="POST",
        headers={
            "Accept": "application/json", "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Cache-Control": "no-cache",
        },
    )
    last_error = None
    for attempt in range(3):
        try:
            global _last_request, _last_cost
            with _request_lock:
                # Official defaults: 30 requests/minute, cost 100/minute.
                # Pace by the previous request's cost, allowing a first cache miss immediately.
                delay = max(0, max(2.05, _last_cost * 0.61) - (time.monotonic() - _last_request))
                if delay:
                    time.sleep(delay)
                _last_request = time.monotonic()
                _last_cost = max(1, len(re.findall(r"\bvariant\s*\(", query))
                                 + 10 * len(re.findall(r"\bcoverage\s*\(", query)))
                with urlopen(request, timeout=timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise GnomadFrequencyError("Invalid GraphQL response")
            if not payload.get("data"):
                raise GnomadFrequencyError("gnomAD returned no data")
            return payload
        except HTTPError as exc:
            last_error = exc
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
            try:
                delay = max(0, min(float(retry_after), 60.0))
            except (TypeError, ValueError):
                delay = 0.75 * (attempt + 1)
            time.sleep(delay)
    raise GnomadFrequencyError(str(last_error or "gnomAD request failed"))


def _allele(reference_build, chromosome, position, reference, alternate):
    build, chromosome = _reference_context(reference_build, chromosome)
    position = int(position)
    reference = str(reference or "").upper()
    alternate = str(alternate or "").upper()
    if position < 1 or reference == alternate or not ALLELE_RE.match(reference) or not ALLELE_RE.match(alternate):
        raise ValueError("Lookup requires a positive position and sequence-resolved A/C/G/T alleles.")
    return build, chromosome, position, reference, alternate


def _reference_context(reference_build, chromosome):
    compact = re.sub(r"[^a-z0-9]", "", str(reference_build or "").lower())
    if compact in ("grch37", "hg19", "b37", "37", "grch37hg19"):
        build = "GRCh37"
    elif compact in ("grch38", "hg38", "b38", "38", "grch38hg38"):
        build = "GRCh38"
    else:
        raise ValueError("Only GRCh37/hg19 and GRCh38/hg38 are supported by this lookup.")
    chromosome = str(chromosome or "").strip()
    chromosome = chromosome[3:] if chromosome.lower().startswith("chr") else chromosome
    chromosome = chromosome.upper()
    from helper_variants.liftover import ASSEMBLY_ACCESSIONS
    chromosome = next((label for label, accession in ASSEMBLY_ACCESSIONS[build].items()
                       if chromosome == accession), chromosome)
    chromosome = {"23": "X", "24": "Y"}.get(chromosome, chromosome)
    if chromosome in ("M", "MT", "MITO"):
        raise ValueError("Mitochondrial variants require the separate gnomAD mitochondrial dataset.")
    if chromosome not in {str(value) for value in range(1, 23)} | {"X", "Y"}:
        raise ValueError("Only primary chromosomes 1–22, X and Y are supported.")
    return build, chromosome


def _frequency(ac, an):
    return float(ac) / float(an) if ac is not None and an else None


def _format_frequency(value):
    if value is None:
        return "n/a"
    if value == 0:
        return "0"
    return f"{value:.3g}"


def _integer(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _number(value):
    try:
        number = float(value) if value is not None else None
        return number if number is not None and math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _cached(database, key):
    if not database.is_file():
        return None
    try:
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
            row = connection.execute(
                "SELECT payload, release, retrieved_at FROM frequencies WHERE cache_key = ?", (key,)
            ).fetchone()
    except sqlite3.Error as exc:
        return _access_metadata({"status": "unavailable", "error": str(exc)})
    if not row:
        return None
    return _parse_cached(row[0], key, row[1], row[2])


def _parse_cached(payload, key, release, retrieved_at):
    try:
        result = json.loads(payload)
    except (TypeError, json.JSONDecodeError):
        return _access_metadata({"status": "unavailable", "error": "Invalid gnomAD cache payload"})
    if not _matches_context(result, key) or result.get("release") != release:
        return None
    result.update(cache="hit", retrieved_at=retrieved_at)
    return _access_metadata(result)


def _store(database, key, result):
    _store_many(Path(database), [(key, result)])


def _store_many(database, rows):
    if not rows:
        return
    try:
        database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(database), timeout=30) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS frequencies (cache_key TEXT PRIMARY KEY, "
                               "release TEXT NOT NULL, payload TEXT NOT NULL, retrieved_at TEXT NOT NULL)")
            connection.executemany("INSERT INTO frequencies VALUES (?,?,?,?) ON CONFLICT(cache_key) DO UPDATE SET "
                "release=excluded.release,payload=excluded.payload,retrieved_at=excluded.retrieved_at",
                [(key, str(result.get("release") or ""), json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False),
                  str(result.get("retrieved_at") or datetime.now(timezone.utc).isoformat())) for key, result in rows])
    except (OSError, sqlite3.Error) as exc:
        for _, result in rows:
            result.update(cache_write_error=str(exc), partial=True)
