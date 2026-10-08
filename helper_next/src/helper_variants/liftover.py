"""Allele-aware GRCh37/GRCh38 projection with a persistent local cache."""
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


API_ROOT = "https://api.ncbi.nlm.nih.gov/variation/v0"
SOURCE_URL = "https://www.ncbi.nlm.nih.gov/variation/services/"
USER_AGENT = "HelperVariantBrowser/0.1 (assembly projection)"
ALLELE_RE = re.compile(r"^[ACGT]+$")

# Exact RefSeq accessions make the assembly interpretation explicit and stable.
ASSEMBLY_ACCESSIONS = {
    "GRCh37": {
        "1": "NC_000001.10", "2": "NC_000002.11", "3": "NC_000003.11",
        "4": "NC_000004.11", "5": "NC_000005.9", "6": "NC_000006.11",
        "7": "NC_000007.13", "8": "NC_000008.10", "9": "NC_000009.11",
        "10": "NC_000010.10", "11": "NC_000011.9", "12": "NC_000012.11",
        "13": "NC_000013.10", "14": "NC_000014.8", "15": "NC_000015.9",
        "16": "NC_000016.9", "17": "NC_000017.10", "18": "NC_000018.9",
        "19": "NC_000019.9", "20": "NC_000020.10", "21": "NC_000021.8",
        "22": "NC_000022.10", "X": "NC_000023.10", "Y": "NC_000024.9",
        "MT": "NC_012920.1",
    },
    "GRCh38": {
        "1": "NC_000001.11", "2": "NC_000002.12", "3": "NC_000003.12",
        "4": "NC_000004.12", "5": "NC_000005.10", "6": "NC_000006.12",
        "7": "NC_000007.14", "8": "NC_000008.11", "9": "NC_000009.12",
        "10": "NC_000010.11", "11": "NC_000011.10", "12": "NC_000012.12",
        "13": "NC_000013.11", "14": "NC_000014.9", "15": "NC_000015.10",
        "16": "NC_000016.10", "17": "NC_000017.11", "18": "NC_000018.10",
        "19": "NC_000019.10", "20": "NC_000020.11", "21": "NC_000021.9",
        "22": "NC_000022.11", "X": "NC_000023.11", "Y": "NC_000024.10",
        "MT": "NC_012920.1",
    },
}


class LiftoverError(RuntimeError):
    pass


def cache_path():
    configured = os.environ.get("HELPER_LIFTOVER_CACHE", "").strip()
    if configured:
        return Path(configured).expanduser()
    data_home = os.environ.get("XDG_DATA_HOME", "").strip()
    root = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return root / "helper_variants" / "assembly_projection.sqlite3"


def cache_status(database=None):
    database = Path(database or cache_path())
    if not database.is_file():
        return {
            "status": "missing", "database": str(database), "record_count": 0,
            "synchronized_at": "",
        }
    try:
        with sqlite3.connect(str(database)) as connection:
            count, latest = connection.execute(
                "SELECT COUNT(*), COALESCE(MAX(retrieved_at), '') FROM projections"
            ).fetchone()
    except sqlite3.Error as exc:
        return {
            "status": "invalid", "database": str(database), "record_count": 0,
            "synchronized_at": "", "error": str(exc),
        }
    return {
        "status": "ready", "database": str(database), "record_count": int(count or 0),
        "synchronized_at": str(latest or ""),
    }


def project_variant(reference_build, chromosome, position, reference, alternate,
                    database=None, timeout=8):
    """Project one exact VCF allele to the other primary human assembly."""
    try:
        source_build = _assembly(reference_build)
        chromosome = _chromosome(chromosome)
        position = int(position)
        reference = str(reference or "").upper()
        alternate = str(alternate or "").upper()
    except (TypeError, ValueError) as exc:
        return _result("unsupported", message=str(exc))

    target_build = "GRCh38" if source_build == "GRCh37" else "GRCh37"
    source = _locus(source_build, chromosome, position, reference, alternate)
    if chromosome == "MT":
        return _result(
            "same_reference", source=source,
            target=_locus(target_build, chromosome, position, reference, alternate),
            target_build=target_build,
            message="The mitochondrial RefSeq accession is shared by GRCh37 and GRCh38.",
        )
    if chromosome not in ASSEMBLY_ACCESSIONS[source_build]:
        return _result(
            "unsupported", source=source, target_build=target_build,
            message="Only primary chromosomes 1–22, X, Y and MT are supported.",
        )
    if position < 1 or not ALLELE_RE.match(reference) or not ALLELE_RE.match(alternate):
        return _result(
            "unsupported", source=source, target_build=target_build,
            message="Projection requires a positive position and sequence-resolved A/C/G/T alleles.",
        )

    key = "|".join((source_build, chromosome, str(position), reference, alternate))
    database = Path(database or cache_path())
    cached = _cached(database, key)
    if cached is not None:
        cached["cache"] = "hit"
        cached["source_url"] = SOURCE_URL
        return cached

    if os.environ.get("HELPER_LIFTOVER_OFFLINE", "").strip().lower() in ("1", "true", "yes"):
        return _result(
            "unavailable", source=source, target_build=target_build, cache="miss",
            message="Assembly projection is in offline mode and no cached result is available.",
        )

    try:
        projected = _retrieve(
            source_build, target_build, chromosome, position, reference, alternate, timeout
        )
    except (LiftoverError, HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        return _result(
            "unavailable", source=source, target_build=target_build, cache="miss",
            message="NCBI assembly projection is temporarily unavailable.", error=str(exc),
        )
    projected["cache"] = "miss"
    try:
        _store(database, key, projected)
    except (OSError, sqlite3.Error):
        pass
    return projected


def _retrieve(source_build, target_build, chromosome, position, reference, alternate, timeout):
    source_accession = ASSEMBLY_ACCESSIONS[source_build][chromosome]
    target_accession = ASSEMBLY_ACCESSIONS[target_build][chromosome]
    source_spdi = "{}:{}:{}:{}".format(source_accession, position - 1, reference, alternate)
    equivalents = _request_json(
        "/spdi/{}/all_equivalent_contextual".format(quote(source_spdi, safe="")), timeout
    )
    matches = [
        item for item in ((equivalents.get("data") or {}).get("spdis") or [])
        if item.get("seq_id") == target_accession
    ]
    source = _locus(source_build, chromosome, position, reference, alternate)
    if not matches:
        return _result(
            "not_mapped", source=source, target_build=target_build,
            message="No equivalent allele was returned on the target assembly.",
        )
    if len(matches) != 1:
        return _result(
            "ambiguous", source=source, target_build=target_build,
            message="Multiple equivalent alleles were returned on the target assembly.",
        )

    match = matches[0]
    target_spdi = "{}:{}:{}:{}".format(
        match["seq_id"], match["position"], match["deleted_sequence"],
        match["inserted_sequence"],
    )
    converted = _request_json(
        "/spdi/{}/vcf_fields".format(quote(target_spdi, safe="")), timeout
    ).get("data") or {}
    if converted.get("chrom") != target_accession:
        raise LiftoverError("NCBI returned VCF fields for an unexpected target accession")
    target = _locus(
        target_build, chromosome, int(converted["pos"]), converted["ref"], converted["alt"]
    )
    target["accession"] = target_accession
    source["accession"] = source_accession
    return _result(
        "mapped", source=source, target=target, target_build=target_build,
        validation={
            "status": "contextual_allele", "reference_match": None,
            "label": "Allele projected and normalized by NCBI Variation Services",
        },
    )


def _request_json(path, timeout):
    request = Request(
        API_ROOT + path, headers={"Accept": "application/json", "User-Agent": USER_AGENT}
    )
    last_error = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            last_error = exc
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
            try:
                delay = min(float(retry_after), 3.0)
            except (TypeError, ValueError):
                delay = 0.4 * (attempt + 1)
            time.sleep(delay)
    raise LiftoverError(str(last_error or "assembly projection request failed"))


def _result(status, source=None, target=None, target_build="", message="", error="",
            validation=None, cache=""):
    return {
        "status": status, "source": source, "target": target,
        "target_build": target_build or ((target or {}).get("reference_build") or ""),
        "method": "NCBI Variation Services SPDI", "api_version": "v0",
        "source_url": SOURCE_URL, "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "validation": validation or {}, "message": message, "error": error, "cache": cache,
    }


def _locus(build, chromosome, position, reference, alternate):
    return {
        "reference_build": build, "browser_name": "hg19" if build == "GRCh37" else "hg38",
        "chromosome": chromosome, "position": int(position),
        "reference": str(reference).upper(), "alternate": str(alternate).upper(),
    }


def _assembly(value):
    compact = re.sub(r"[^a-z0-9]", "", str(value or "").lower())
    if compact in ("grch37", "hg19", "b37", "37", "grch37hg19"):
        return "GRCh37"
    if compact in ("grch38", "hg38", "b38", "38", "grch38hg38"):
        return "GRCh38"
    raise ValueError("Only GRCh37/hg19 and GRCh38/hg38 can be projected.")


def _chromosome(value):
    chromosome = str(value or "").strip()
    if chromosome.lower().startswith("chr"):
        chromosome = chromosome[3:]
    chromosome = chromosome.upper()
    aliases = {"23": "X", "24": "Y", "M": "MT", "MITO": "MT"}
    return aliases.get(chromosome, chromosome)


def _cached(database, key):
    if not database.is_file():
        return None
    try:
        with sqlite3.connect(str(database)) as connection:
            row = connection.execute(
                "SELECT payload FROM projections WHERE cache_key = ?", (key,)
            ).fetchone()
    except sqlite3.Error:
        return None
    if not row:
        return None
    try:
        return json.loads(row[0])
    except (TypeError, ValueError):
        return None


def _store(database, key, payload):
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(database)) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS projections ("
            "cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, retrieved_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT OR REPLACE INTO projections(cache_key, payload, retrieved_at) VALUES (?, ?, ?)",
            (key, json.dumps(payload, sort_keys=True), payload.get("retrieved_at", "")),
        )
