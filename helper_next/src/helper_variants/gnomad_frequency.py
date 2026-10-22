"""Allele-specific gnomAD genome frequencies with coverage-aware absence states."""
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_URL = "https://gnomad.broadinstitute.org/api"
SOURCE_URL = "https://gnomad.broadinstitute.org/"
USER_AGENT = "HelperVariantBrowser/0.1 (gnomAD genome frequency)"
ALLELE_RE = re.compile(r"^[ACGT]+$")
MIN_MEAN_COVERAGE = 20.0
MIN_OVER_20 = 0.8

DATASETS = {
    "GRCh37": {
        "id": "gnomad_r2_1", "release": "2.1.1", "reference_genome": "GRCh37",
    },
    "GRCh38": {
        "id": "gnomad_r4", "release": "4.1", "reference_genome": "GRCh38",
    },
}

# Sex-stratified, sub-population, HGDP and 1000 Genomes rows are intentionally
# excluded from the compact clinical summary. They remain available at the source URL.
MAJOR_POPULATIONS = {
    "afr", "ami", "amr", "asj", "eas", "fin", "mid", "nfe", "oth", "remaining", "sas",
}

GRAPHQL_QUERY = """
query VariantGenomeFrequency(
  $variantId: String!, $datasetId: DatasetId!, $chrom: String!,
  $start: Int!, $stop: Int!, $referenceGenome: ReferenceGenomeId!
) {
  variant(variantId: $variantId, dataset: $datasetId) {
    variant_id reference_genome chrom pos ref alt
    coverage { genome { mean median over_20 } }
    genome {
      ac an ac_hom ac_hemi filters
      populations { id ac an ac_hom ac_hemi }
    }
  }
  region(
    chrom: $chrom, start: $start, stop: $stop,
    reference_genome: $referenceGenome
  ) {
    coverage(dataset: $datasetId) {
      genome { pos mean median over_20 }
    }
  }
}
"""

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
    if not database.is_file():
        return {
            "status": "missing", "database": str(database), "record_count": 0,
            "synchronized_at": "", "releases": [],
        }
    try:
        with sqlite3.connect(str(database)) as connection:
            count, latest = connection.execute(
                "SELECT COUNT(*), COALESCE(MAX(retrieved_at), '') FROM frequencies"
            ).fetchone()
            releases = [row[0] for row in connection.execute(
                "SELECT DISTINCT release FROM frequencies ORDER BY release"
            )]
    except sqlite3.Error as exc:
        return {
            "status": "invalid", "database": str(database), "record_count": 0,
            "synchronized_at": "", "releases": [], "error": str(exc),
        }
    return {
        "status": "ready", "database": str(database), "record_count": int(count or 0),
        "synchronized_at": str(latest or ""), "releases": releases,
    }


def lookup_variant(reference_build, chromosome, position, reference, alternate,
                   database=None, timeout=12):
    """Retrieve one exact allele from the assembly-matched gnomAD genomes release."""
    try:
        allele = _allele(reference_build, chromosome, position, reference, alternate)
    except (TypeError, ValueError) as exc:
        return _empty_result("unsupported", message=str(exc))

    build, chromosome, position, reference, alternate = allele
    dataset = DATASETS[build]
    variant_id = "{}-{}-{}-{}".format(chromosome, position, reference, alternate)
    source_url = "{}variant/{}?dataset={}".format(SOURCE_URL, variant_id, dataset["id"])
    key = cache_key(*allele)
    database = Path(database or cache_path())
    cached = _cached(database, key)
    if cached is not None:
        cached.update({"cache": "hit", "source_url": source_url})
        return cached

    if os.environ.get("HELPER_GNOMAD_OFFLINE", "").strip().lower() in ("1", "true", "yes"):
        return _empty_result(
            "unavailable", dataset=dataset, allele=allele, source_url=source_url,
            cache="miss", message="gnomAD is in offline mode and no cached result is available.",
        )

    variables = {
        "variantId": variant_id, "datasetId": dataset["id"], "chrom": chromosome,
        "start": position, "stop": position, "referenceGenome": dataset["reference_genome"],
    }
    try:
        response = _request_graphql(GRAPHQL_QUERY, variables, timeout)
        result = _parse_response(response, dataset, allele, source_url)
    except (GnomadFrequencyError, HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        return _empty_result(
            "unavailable", dataset=dataset, allele=allele, source_url=source_url,
            cache="miss", message="gnomAD frequency is temporarily unavailable.", error=str(exc),
        )
    result["cache"] = "miss"
    try:
        _store(database, key, result)
    except (OSError, sqlite3.Error):
        pass
    return result


def region_variants(reference_build, chromosome, start, end, timeout=12):
    """Return compact IGV features for variants in one visible genomic window."""
    if os.environ.get("HELPER_GNOMAD_OFFLINE", "").strip().lower() in ("1", "true", "yes"):
        raise GnomadFrequencyError("gnomAD is disabled in offline mode.")
    build, normalized_chromosome = _reference_context(reference_build, chromosome)
    start, end = int(start), int(end)
    if start < 1 or end < start or end - start > 100_000:
        raise ValueError("gnomAD track windows must span 1-100000 bases.")
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


def cached_variant(reference_build, chromosome, position, reference, alternate, database=None):
    """Return the full existing allele-specific lookup, without a network request."""
    try:
        key = cache_key(reference_build, chromosome, position, reference, alternate)
    except (TypeError, ValueError):
        return None
    result = _cached(Path(database or cache_path()), key)
    if not isinstance(result, dict):
        return None
    try:
        stored_key = cache_key(*(result.get(k) for k in (
            "reference_build", "chromosome", "position", "reference", "alternate"
        )))
    except (TypeError, ValueError):
        return None
    return result if stored_key == key else None


def cached_context(reference_build, chromosome, position, reference, alternate, database=None):
    """Return priority-engine fields for an already cached exact allele only."""
    return priority_context(cached_variant(
        reference_build, chromosome, position, reference, alternate, database
    ))


def cached_contexts(alleles, database=None):
    """Return priority contexts for many alleles with a single cache connection."""
    keys = []
    for allele in alleles:
        try:
            keys.append(cache_key(*allele))
        except (TypeError, ValueError):
            keys.append("")
    database = Path(database or cache_path())
    payloads = {}
    valid_keys = [key for key in keys if key]
    if database.is_file():
        try:
            with sqlite3.connect(str(database)) as connection:
                for offset in range(0, len(valid_keys), 500):
                    batch = valid_keys[offset:offset + 500]
                    placeholders = ",".join("?" for _ in batch)
                    for key, payload in connection.execute(
                        "SELECT cache_key, payload FROM frequencies WHERE cache_key IN ({})".format(
                            placeholders
                        ),
                        batch,
                    ):
                        try:
                            payloads[key] = json.loads(payload)
                        except (TypeError, json.JSONDecodeError):
                            continue
        except sqlite3.Error:
            pass
    return [priority_context(payloads.get(key)) for key in keys]


def priority_context(result):
    """Translate a frequency result into conservative priority-engine evidence."""
    if not result:
        return {}
    status = str(result.get("status") or "")
    context = {
        "population_frequency_status": status,
        "population_frequency_source": "gnomAD genomes v{}".format(result.get("release") or ""),
    }
    if status == "observed" and not result.get("filters"):
        values = [result.get("af"), result.get("max_population_af")]
        numeric = [float(value) for value in values if value is not None]
        if numeric:
            context["population_af"] = max(numeric)
    elif status == "not_observed_covered":
        context.update({
            "population_absent": True,
            "population_coverage_adequate": True,
        })
    return context


def cache_key(reference_build, chromosome, position, reference, alternate):
    build, chromosome, position, reference, alternate = _allele(
        reference_build, chromosome, position, reference, alternate
    )
    return "|".join((
        DATASETS[build]["id"], build, chromosome, str(position), reference, alternate,
    ))


def _parse_response(response, dataset, allele, source_url):
    build, chromosome, position, reference, alternate = allele
    data = response.get("data") or {}
    variant = data.get("variant")
    region_rows = (((data.get("region") or {}).get("coverage") or {}).get("genome") or [])
    region_coverage = next(
        (row for row in region_rows if _integer(row.get("pos")) == position), None
    )
    variant_coverage = (((variant or {}).get("coverage") or {}).get("genome") or {})
    coverage = _coverage(region_coverage or variant_coverage)
    base = _empty_result(
        "not_observed_coverage_unknown", dataset=dataset, allele=allele,
        source_url=source_url,
    )
    base["coverage"] = coverage
    if variant is None:
        if coverage.get("adequate"):
            base.update({
                "status": "not_observed_covered",
                "population_absent": True,
                "population_coverage_adequate": True,
                "message": (
                    "The allele is not present in this genomes release and the locus meets "
                    "the configured coverage heuristic."
                ),
            })
        elif coverage.get("available"):
            base.update({
                "status": "not_observed_low_coverage",
                "message": (
                    "The allele is not present in this genomes release, but locus coverage "
                    "is insufficient to interpret absence."
                ),
            })
        else:
            base["message"] = (
                "The allele is not present in this genomes release and locus coverage is unavailable."
            )
        return base

    genome = variant.get("genome")
    if not genome:
        base.update({
            "status": "not_observed_coverage_unknown",
            "message": "No genome frequency record is available for this allele.",
        })
        return base

    ac = _integer(genome.get("ac"))
    an = _integer(genome.get("an"))
    populations = []
    for row in genome.get("populations") or []:
        population_id = str(row.get("id") or "")
        if population_id not in MAJOR_POPULATIONS:
            continue
        population_ac = _integer(row.get("ac"))
        population_an = _integer(row.get("an"))
        populations.append({
            "id": population_id, "ac": population_ac, "an": population_an,
            "af": _frequency(population_ac, population_an),
            "ac_hom": _integer(row.get("ac_hom")),
            "ac_hemi": _integer(row.get("ac_hemi")),
            "status": (
                "observed" if population_ac and population_an
                else "not_observed" if population_an else "not_covered"
            ),
        })
    population_frequencies = [
        row["af"] for row in populations if row.get("af") is not None
    ]
    filters = [str(value) for value in (genome.get("filters") or []) if str(value)]
    base.update({
        "status": "observed" if ac and an else (
            "not_observed_covered" if coverage.get("adequate") else "not_observed_low_coverage"
        ),
        "ac": ac, "an": an, "af": _frequency(ac, an),
        "ac_hom": _integer(genome.get("ac_hom")),
        "ac_hemi": _integer(genome.get("ac_hemi")),
        "filters": filters, "populations": populations,
        "max_population_af": max(population_frequencies) if population_frequencies else None,
        "population_absent": not bool(ac) and bool(coverage.get("adequate")),
        "population_coverage_adequate": bool(coverage.get("adequate")),
        "message": "Allele-specific genome counts retrieved from gnomAD.",
    })
    return base


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
    return {
        "status": status, "dataset": dataset.get("id", ""),
        "release": dataset.get("release", ""), "data_type": "genomes",
        "reference_build": build, "chromosome": chromosome, "position": position,
        "reference": reference, "alternate": alternate,
        "ac": None, "an": None, "af": None, "ac_hom": None, "ac_hemi": None,
        "filters": [], "populations": [], "max_population_af": None,
        "coverage": {}, "population_absent": False,
        "population_coverage_adequate": False,
        "source_url": source_url, "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "cache": cache, "message": message, "error": error,
    }


def _request_graphql(query, variables, timeout):
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = Request(
        API_URL, data=body, method="POST",
        headers={
            "Accept": "application/json", "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    last_error = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            errors = payload.get("errors") or []
            unexpected = [
                str(error.get("message") or error) for error in errors
                if "variant not found" not in str(error.get("message") or error).casefold()
            ]
            if unexpected:
                raise GnomadFrequencyError("; ".join(unexpected))
            if not payload.get("data"):
                raise GnomadFrequencyError("gnomAD returned no data")
            return payload
        except HTTPError as exc:
            last_error = exc
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
            try:
                delay = min(float(retry_after), 5.0)
            except (TypeError, ValueError):
                delay = 0.75 * (attempt + 1)
            time.sleep(delay)
    raise GnomadFrequencyError(str(last_error or "gnomAD request failed"))


def _allele(reference_build, chromosome, position, reference, alternate):
    build, chromosome = _reference_context(reference_build, chromosome)
    position = int(position)
    reference = str(reference or "").upper()
    alternate = str(alternate or "").upper()
    if position < 1 or not ALLELE_RE.match(reference) or not ALLELE_RE.match(alternate):
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
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _cached(database, key):
    if not database.is_file():
        return None
    try:
        with sqlite3.connect(str(database)) as connection:
            row = connection.execute(
                "SELECT payload FROM frequencies WHERE cache_key = ?", (key,)
            ).fetchone()
    except sqlite3.Error:
        return None
    if not row:
        return None
    try:
        return json.loads(row[0])
    except (TypeError, json.JSONDecodeError):
        return None


def _store(database, key, result):
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(database)) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS frequencies ("
            "cache_key TEXT PRIMARY KEY, release TEXT NOT NULL, payload TEXT NOT NULL, "
            "retrieved_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT OR REPLACE INTO frequencies (cache_key, release, payload, retrieved_at) "
            "VALUES (?, ?, ?, ?)",
            (
                key, str(result.get("release") or ""),
                json.dumps(result, sort_keys=True, separators=(",", ":")),
                str(result.get("retrieved_at") or datetime.now(timezone.utc).isoformat()),
            ),
        )
        connection.commit()
