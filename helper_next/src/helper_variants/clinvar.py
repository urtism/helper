"""Exact, cached ClinVar enrichment for variant-detail responses."""
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree


EUTILS_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
CACHE_MAX_AGE = timedelta(days=7)
NEGATIVE_CACHE_MAX_AGE = timedelta(days=1)
USER_AGENT = "HelperVariantBrowser/0.1 (ClinVar evidence)"


class ClinVarError(RuntimeError):
    pass


def cache_path():
    configured = os.environ.get("HELPER_CLINVAR_CACHE", "").strip()
    if configured:
        return Path(configured).expanduser()
    data_home = os.environ.get("XDG_DATA_HOME", "").strip()
    root = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return root / "helper_variants" / "clinvar_evidence.sqlite3"


def lookup_variant(reference_build, chromosome, position, reference, alternate,
                   database=None, timeout=12):
    """Return the current aggregate ClinVar assertion for one exact VCF allele."""
    database = Path(database or cache_path())
    try:
        allele = _allele(reference_build, chromosome, position, reference, alternate)
        key = "|".join(str(value) for value in allele)
        cached = _cached(database, key)
        if cached is not None:
            if "classification_breakdown" not in cached:
                variation_id = next(
                    (str(value) for value in cached.get("identifiers", [])
                     if str(value).isdigit()), ""
                )
                try:
                    cached["classification_breakdown"] = _classification_breakdown(
                        variation_id, timeout
                    )
                    _store(database, key, cached)
                except (
                    ClinVarError, HTTPError, URLError, TimeoutError, OSError,
                    ValueError, sqlite3.Error, ElementTree.ParseError,
                ):
                    cached["classification_breakdown"] = []
            cached["cache"] = "hit"
            return cached
        result = _retrieve(*allele, timeout=timeout)
    except (
        HTTPError, URLError, TimeoutError, OSError, ValueError,
        sqlite3.Error,
    ) as exc:
        raise ClinVarError("ClinVar enrichment is temporarily unavailable") from exc
    result["cache"] = "miss"
    try:
        _store(database, key, result)
    except (OSError, sqlite3.Error):
        pass
    return result


def merge_evidence(indexed, retrieved):
    """Merge authoritative remote fields without discarding indexed annotations."""
    result = dict(indexed or {})
    result["identifiers"] = _unique(
        (result.get("identifiers") or []) + (retrieved.get("identifiers") or [])
    )
    for key in (
        "classifications", "conditions", "condition_ids", "conflicts", "origins",
        "last_evaluated", "oncogenicity", "somatic_clinical_impact", "rcv_accessions",
    ):
        result[key] = _unique(retrieved.get(key) or result.get(key) or [])
    for key in (
        "review_statuses", "oncogenicity_review_statuses", "somatic_review_statuses",
    ):
        result[key] = _review_statuses(retrieved.get(key) or result.get(key) or [])
    result["classification_breakdown"] = (
        retrieved.get("classification_breakdown")
        or result.get("classification_breakdown") or []
    )
    for key in (
        "submission_count", "submitter_count", "record_updated", "most_recent_submission",
        "source_url", "retrieved_at", "cache",
    ):
        if retrieved.get(key) not in (None, ""):
            result[key] = retrieved[key]
    result["has_conflict"] = bool(result.get("conflicts")) or any(
        _has_conflict_text(value)
        for value in result.get("classifications", []) + [
            row.get("label", "") for row in result.get("review_statuses", [])
        ]
    )
    if retrieved.get("status") == "available" or any(result.get(key) for key in (
        "classifications", "review_statuses", "conditions", "identifiers",
    )):
        result["status"] = "available"
    result["retrieval_status"] = retrieved.get("status", "not_found")
    return result


def _retrieve(reference_build, chromosome, position, reference, alternate, timeout):
    assembly, position_field = _assembly(reference_build)
    term = "{}[chr] AND {}[{}]".format(chromosome, position, position_field)
    search = _json_request("esearch.fcgi", {
        "db": "clinvar", "term": term, "retmode": "json", "retmax": "100",
        "tool": "helper_variant_browser",
    }, timeout)
    identifiers = (search.get("esearchresult") or {}).get("idlist") or []
    if not identifiers:
        return _empty_result()
    summary = _json_request("esummary.fcgi", {
        "db": "clinvar", "id": ",".join(str(value) for value in identifiers),
        "retmode": "json", "tool": "helper_variant_browser",
    }, timeout)
    records = summary.get("result") or {}
    for identifier in records.get("uids") or identifiers:
        record = records.get(str(identifier)) or {}
        if _summary_matches(record, assembly, chromosome, position, reference, alternate):
            evidence = _summary_evidence(record)
            try:
                evidence["classification_breakdown"] = _classification_breakdown(
                    str(record.get("uid") or identifier), timeout
                )
            except (
                ClinVarError, HTTPError, URLError, TimeoutError, OSError,
                ValueError, ElementTree.ParseError,
            ):
                evidence["classification_breakdown"] = []
            return evidence
    return _empty_result()


def _summary_matches(record, assembly, chromosome, position, reference, alternate):
    expected_deleted, expected_inserted = _spdi_change(reference, alternate)
    for variation in record.get("variation_set") or []:
        locations = variation.get("variation_loc") or []
        location_match = any(
            str(location.get("assembly_name") or "") == assembly
            and _chromosome(location.get("chr")) == chromosome
            and str(location.get("start") or "") == str(position)
            for location in locations
        )
        if not location_match:
            continue
        spdi = str(variation.get("canonical_spdi") or "").split(":", 3)
        if len(spdi) == 4:
            deleted, inserted = spdi[2].upper(), spdi[3].upper()
            if deleted == expected_deleted and inserted == expected_inserted:
                return True
        for location in locations:
            located_ref = str(location.get("ref") or "").upper()
            located_alt = str(location.get("alt") or "").upper()
            if located_ref == reference and located_alt == alternate:
                return True
    return False


def _spdi_change(reference, alternate):
    reference = str(reference).upper()
    alternate = str(alternate).upper()
    while reference and alternate and reference[0] == alternate[0]:
        reference, alternate = reference[1:], alternate[1:]
    while reference and alternate and reference[-1] == alternate[-1]:
        reference, alternate = reference[:-1], alternate[:-1]
    return reference, alternate


def _summary_evidence(record):
    variation_id = str(record.get("uid") or "")
    accession_version = str(record.get("accession_version") or record.get("accession") or "")
    identifiers = _unique(value for value in (variation_id, accession_version) if value)
    germline = record.get("germline_classification") or {}
    oncogenicity = record.get("oncogenicity_classification") or {}
    somatic = record.get("clinical_impact_classification") or {}
    classifications = _classification_descriptions(germline)
    review_statuses = _summary_reviews(germline)
    conditions, condition_ids = _summary_conditions(germline)
    supporting = record.get("supporting_submissions") or {}
    scv_accessions = supporting.get("scv") or []
    rcv_accessions = supporting.get("rcv") or []
    retrieved_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "status": "available", "identifiers": identifiers,
        "classifications": classifications, "review_statuses": review_statuses,
        "classification_breakdown": [],
        "conditions": conditions, "condition_ids": condition_ids,
        "conflicts": classifications if any(
            _has_conflict_text(value) for value in classifications
        ) else [],
        "origins": [], "last_evaluated": _summary_dates(germline),
        "oncogenicity": _classification_descriptions(oncogenicity),
        "oncogenicity_review_statuses": _summary_reviews(oncogenicity),
        "somatic_clinical_impact": _classification_descriptions(somatic),
        "somatic_review_statuses": _summary_reviews(somatic),
        "submission_count": len(scv_accessions), "submitter_count": None,
        "record_updated": "", "most_recent_submission": "",
        "rcv_accessions": _unique(rcv_accessions),
        "source_url": (
            "https://www.ncbi.nlm.nih.gov/clinvar/variation/{}/".format(variation_id)
            if variation_id else "https://www.ncbi.nlm.nih.gov/clinvar/"
        ),
        "retrieved_at": retrieved_at,
    }


def _classification_breakdown(variation_id, timeout):
    if not str(variation_id).isdigit():
        return []
    document = _request("efetch.fcgi", {
        "db": "clinvar", "rettype": "vcv", "is_variationid": "true",
        "id": str(variation_id), "tool": "helper_variant_browser",
    }, timeout)
    root = ElementTree.fromstring(document)
    explanation = root.find(
        ".//VariationArchive/ClassifiedRecord/Classifications/"
        "GermlineClassification/Explanation[@DataSource='ClinVar']"
    )
    if explanation is None or not explanation.text:
        return []
    result = []
    seen = set()
    for match in re.finditer(
        r"(?:^|;)\s*(.+?)\s*\((\d+)\)(?=\s*(?:;|$))", explanation.text
    ):
        label = " ".join(match.group(1).strip().split())
        folded = label.casefold()
        if label and folded not in seen:
            seen.add(folded)
            result.append({"label": label, "count": int(match.group(2))})
    return result


def _summary_conditions(classification):
    names = []
    identifiers = []
    for trait in classification.get("trait_set") or []:
        if trait.get("trait_name"):
            names.append(trait["trait_name"])
        for xref in trait.get("trait_xrefs") or []:
            source = str(xref.get("db_source") or "").strip()
            value = str(xref.get("db_id") or "").strip()
            if not source or not value:
                continue
            if source.casefold() == "mondo" and value.upper().startswith("MONDO:"):
                identifiers.append(value.upper())
            else:
                identifiers.append("{}:{}".format(source, value))
    return _unique(names), _unique(identifiers)


def _classification_descriptions(classification):
    description = str(classification.get("description") or "").strip()
    return [description] if description else []


def _summary_reviews(classification):
    status = str(classification.get("review_status") or "").strip()
    return [{"label": status, "stars": _review_stars(status)}] if status else []


def _summary_dates(classification):
    value = str(classification.get("last_evaluated") or "").strip()
    if not value or value.startswith("1/01/01"):
        return []
    return [value.split(" ", 1)[0].replace("/", "-")]


def _review_stars(status):
    value = str(status or "").casefold()
    if "practice guideline" in value:
        return 4
    if "expert panel" in value:
        return 3
    if "multiple submitters" in value and "no conflict" in value:
        return 2
    if "criteria provided" in value:
        return 1
    return 0


def _has_conflict_text(value):
    normalized = " ".join(str(value or "").casefold().replace("_", " ").split())
    normalized = re.sub(
        r"\b(?:no|without)\s+conflicts?\b|\bnot\s+conflicting\b", "", normalized
    )
    return bool(re.search(r"\bconflict(?:s|ed|ing)?\b", normalized))


def _review_statuses(rows):
    result = []
    positions = {}
    for row in rows:
        label = str(row.get("label") or "").strip()
        if not label:
            continue
        folded = label.casefold()
        normalized = {"label": label, "stars": int(row.get("stars") or 0)}
        if folded in positions:
            position = positions[folded]
            result[position]["stars"] = max(result[position]["stars"], normalized["stars"])
        else:
            positions[folded] = len(result)
            result.append(normalized)
    return result


def _empty_result():
    return {
        "status": "not_found", "identifiers": [], "classifications": [],
        "review_statuses": [], "conditions": [], "condition_ids": [], "conflicts": [],
        "classification_breakdown": [],
        "origins": [], "last_evaluated": [], "oncogenicity": [],
        "oncogenicity_review_statuses": [], "somatic_clinical_impact": [],
        "somatic_review_statuses": [], "rcv_accessions": [],
        "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _allele(reference_build, chromosome, position, reference, alternate):
    assembly, _ = _assembly(reference_build)
    chromosome = _chromosome(chromosome)
    reference = str(reference or "").upper().strip()
    alternate = str(alternate or "").upper().strip()
    if not chromosome or not reference or not alternate:
        raise ValueError("An exact chromosome, REF and ALT are required")
    return assembly, chromosome, int(position), reference, alternate


def _assembly(reference_build):
    value = str(reference_build or "").casefold().replace("_", "").replace("-", "")
    if "37" in value or "hg19" in value:
        return "GRCh37", "chrpos37"
    if "38" in value or "hg38" in value:
        return "GRCh38", "chrpos38"
    raise ValueError("ClinVar lookup requires GRCh37/hg19 or GRCh38/hg38")


def _chromosome(value):
    chromosome = str(value or "").strip()
    if chromosome.casefold().startswith("chr"):
        chromosome = chromosome[3:]
    return chromosome.upper()


def _request(endpoint, parameters, timeout):
    url = "{}/{}?{}".format(EUTILS_URL, endpoint, urlencode(parameters))
    request = Request(url, headers={"Accept": "application/xml", "User-Agent": USER_AGENT})
    for attempt in range(2):
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt:
                raise
            retry_after = exc.headers.get("Retry-After", "")
            time.sleep(min(int(retry_after) if str(retry_after).isdigit() else 1, 3))
    raise ClinVarError("ClinVar request failed")


def _json_request(endpoint, parameters, timeout):
    return json.loads(_request(endpoint, parameters, timeout).decode("utf-8"))


def _connect(database):
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database), timeout=10)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS evidence ("
        "allele_key TEXT PRIMARY KEY, payload TEXT NOT NULL, retrieved_at TEXT NOT NULL)"
    )
    return connection


def _cached(database, key):
    if not database.is_file():
        return None
    with _connect(database) as connection:
        row = connection.execute(
            "SELECT payload, retrieved_at FROM evidence WHERE allele_key = ?", (key,)
        ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(row[0])
        retrieved = datetime.fromisoformat(row[1].replace("Z", "+00:00"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    max_age = CACHE_MAX_AGE if payload.get("status") == "available" else NEGATIVE_CACHE_MAX_AGE
    if datetime.now(timezone.utc) - retrieved > max_age:
        return None
    return payload


def _store(database, key, payload):
    retrieved_at = payload.get("retrieved_at") or datetime.now(timezone.utc).isoformat()
    with _connect(database) as connection:
        connection.execute(
            "INSERT INTO evidence (allele_key, payload, retrieved_at) VALUES (?, ?, ?) "
            "ON CONFLICT(allele_key) DO UPDATE SET payload=excluded.payload, "
            "retrieved_at=excluded.retrieved_at",
            (key, json.dumps(payload, sort_keys=True), retrieved_at),
        )


def _unique(values):
    result = []
    seen = set()
    for value in values:
        value = str(value or "").strip()
        if value and value.casefold() not in seen:
            seen.add(value.casefold())
            result.append(value)
    return result
