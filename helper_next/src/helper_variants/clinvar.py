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


def cache_status(database=None):
    """Describe the on-demand cache without creating or refreshing it."""
    database = Path(database or cache_path())
    if not database.is_file():
        return {
            "status": "missing", "database": str(database), "record_count": 0,
            "synchronized_at": "", "latest_record_update": "",
        }
    latest_record_update = ""
    try:
        with sqlite3.connect(str(database)) as connection:
            rows = connection.execute(
                "SELECT payload, retrieved_at FROM evidence ORDER BY retrieved_at DESC"
            ).fetchall()
    except sqlite3.Error as exc:
        return {
            "status": "invalid", "database": str(database), "record_count": 0,
            "synchronized_at": "", "latest_record_update": "", "error": str(exc),
        }
    for payload, _ in rows:
        try:
            record_update = str(json.loads(payload).get("record_updated") or "")
        except (TypeError, json.JSONDecodeError):
            continue
        if record_update > latest_record_update:
            latest_record_update = record_update
    return {
        "status": "ready", "database": str(database), "record_count": len(rows),
        "synchronized_at": str(rows[0][1] or "") if rows else "",
        "latest_record_update": latest_record_update,
        "cache_max_age_days": CACHE_MAX_AGE.days,
    }


def lookup_variant(reference_build, chromosome, position, reference, alternate,
                   database=None, timeout=12, refresh=False, fetch=True,
                   require_breakdown=False):
    """Cache-first exact allele lookup. Submission counts are optional enrichment.

    ``fetch=False`` and HELPER_CLINVAR_OFFLINE forbid every HTTP request, even
    explicit refreshes/enrichments. Failed attempts retain the last usable record
    and its acquisition time; TTL always refers to that acquisition.
    """
    database = Path(database or cache_path())
    try:
        allele = _allele(reference_build, chromosome, position, reference, alternate)
    except (TypeError, ValueError) as exc:
        return _access_metadata({"status": "unsupported", "error": str(exc)})
    key = "|".join(str(value) for value in allele)
    cache_error = None
    try:
        cached = _cached(database, key, include_stale=True)
    except (ClinVarError, OSError, sqlite3.Error) as exc:
        cached = None
        cache_error = str(exc)
    allow_fetch = fetch and os.environ.get("HELPER_CLINVAR_OFFLINE", "").strip().lower() not in (
        "1", "true", "yes",
    )
    if cached is not None:
        cached["cache"] = "hit"
    if not allow_fetch:
        return cached if cached is not None else _access_metadata({
            "status": "unavailable" if cache_error else "not_queried", "cache": "miss",
            "last_error": cache_error,
        })
    try:
        if cached is not None and not refresh and cached["freshness"] == "FRESH" and _complete(cached):
            if require_breakdown and cached["status"] == "available" and "classification_breakdown" not in cached:
                variation_id = next(
                    (str(value) for value in cached.get("identifiers", [])
                     if str(value).isdigit()), ""
                )
                if variation_id:
                    cached["classification_breakdown"] = _classification_breakdown(
                        variation_id, timeout
                    )
                    cached.pop("last_error", None)
                    _store(database, key, cached)
                    return _access_metadata(cached)
                # No source ID: retrieve the aggregate rather than guess an ID.
            else:
                return cached
        result = _retrieve(*allele, timeout=timeout)
        if result.get("status") not in ("available", "not_found"):
            raise ClinVarError("Invalid ClinVar evidence status")
    except (
        ClinVarError, HTTPError, URLError, TimeoutError, OSError, ValueError,
        sqlite3.Error, ElementTree.ParseError, TypeError, AttributeError,
    ) as exc:
        error = str(exc) or type(exc).__name__
        if cached is not None:
            cached["last_error"] = error
            try:
                if cached.get("retrieved_at"):
                    _store(database, key, cached)
            except (OSError, sqlite3.Error):
                pass
            return cached
        return _access_metadata({"status": "unavailable", "cache": "miss", "last_error": error})
    result["cache"] = "miss"
    result = _access_metadata(result)
    try:
        _store(database, key, result)
    except (OSError, sqlite3.Error):
        pass
    return result


def _complete(payload):
    """The UI can display aggregate assertions without submission counts."""
    return payload.get("status") == "not_found" or (
        isinstance(payload.get("classifications"), list)
        and isinstance(payload.get("review_statuses"), list)
    )


def _access_metadata(payload, retrieved_at=None):
    """Add access state without changing the biological/legacy status."""
    result = dict(payload)
    result["source"] = "ClinVar"
    result["availability"] = {
        "available": "AVAILABLE", "not_found": "NOT_FOUND",
        "not_queried": "NOT_QUERIED", "unsupported": "UNSUPPORTED",
    }.get(result.get("status"), "ERROR")
    result["freshness"] = "UNKNOWN"
    acquired = retrieved_at or result.get("retrieved_at")
    if acquired:
        result["retrieved_at"] = acquired
    try:
        retrieved = datetime.fromisoformat(acquired.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - retrieved
        if retrieved.tzinfo is not None and age >= timedelta(0):
            ttl = CACHE_MAX_AGE if result.get("status") == "available" else NEGATIVE_CACHE_MAX_AGE
            result["freshness"] = "STALE" if age > ttl else "FRESH"
    except (AttributeError, TypeError, ValueError):
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
        "source", "availability", "freshness", "last_error", "breakdown_error",
        "provenance",
    ):
        if retrieved.get(key) not in (None, ""):
            result[key] = retrieved[key]
    result["has_conflict"] = bool(result.get("conflicts")) or any(
        _has_conflict_text(value)
        for value in result.get("classifications", []) + [
            row.get("label", "") for row in result.get("review_statuses", [])
        ]
    )
    result.setdefault("status", retrieved.get("status", "not_queried"))
    if retrieved.get("status") == "available" or any(result.get(key) for key in (
        "classifications", "review_statuses", "conditions", "identifiers",
    )):
        result["status"] = "available"
    result["retrieval_status"] = retrieved.get("status", "not_found")
    return result


def cached_evidence(alleles, database=None, include_stale=True):
    """Read exact-allele detail evidence in bulk, without network requests."""
    keys = []
    for allele in alleles:
        try:
            keys.append("|".join(str(value) for value in _allele(*allele)))
        except (TypeError, ValueError):
            keys.append("")
    database = Path(database or cache_path())
    payloads = {}
    valid_keys = list(dict.fromkeys(key for key in keys if key))
    if database.is_file() and valid_keys:
        try:
            with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
                for offset in range(0, len(valid_keys), 500):
                    batch = valid_keys[offset:offset + 500]
                    placeholders = ",".join("?" for _ in batch)
                    for key, payload, retrieved_at in connection.execute(
                        "SELECT allele_key, payload, retrieved_at FROM evidence "
                        "WHERE allele_key IN ({})".format(placeholders), batch,
                    ):
                        parsed = _parse_cached(payload, retrieved_at, include_stale=True)
                        if parsed is None:
                            payloads[key] = _access_metadata({
                                "status": "unavailable", "last_error": "Invalid ClinVar cache payload",
                            })
                        elif include_stale or parsed["freshness"] == "FRESH":
                            parsed["cache"] = "hit"
                            payloads[key] = merge_evidence({}, parsed)
        except (OSError, sqlite3.Error) as exc:
            for key in valid_keys:
                payloads.setdefault(key, _access_metadata({"status": "unavailable", "last_error": str(exc)}))
    return [payloads.get(key, {}) for key in keys]


def _retrieve(reference_build, chromosome, position, reference, alternate, timeout):
    assembly, position_field = _assembly(reference_build)
    term = "{}[chr] AND {}[{}]".format(chromosome, position, position_field)
    search = _json_request("esearch.fcgi", {
        "db": "clinvar", "term": term, "retmode": "json", "retmax": "100",
        "tool": "helper_variant_browser",
    }, timeout)
    search_result = search.get("esearchresult")
    if not isinstance(search_result, dict) or not isinstance(search_result.get("idlist"), list) or search_result.get("ERROR") or search.get("error"):
        raise ClinVarError("Invalid ClinVar search response")
    identifiers = search_result["idlist"]
    if not identifiers:
        return _empty_result()
    summary = _json_request("esummary.fcgi", {
        "db": "clinvar", "id": ",".join(str(value) for value in identifiers),
        "retmode": "json", "tool": "helper_variant_browser",
    }, timeout)
    records = summary.get("result")
    if not isinstance(records, dict) or not records.get("uids") or summary.get("error"):
        raise ClinVarError("Invalid ClinVar summary response")
    for identifier in records.get("uids") or identifiers:
        record = records.get(str(identifier)) or {}
        if not record or record.get("error"):
            raise ClinVarError("Incomplete ClinVar summary response")
        if _summary_matches(record, assembly, chromosome, position, reference, alternate):
            evidence = _summary_evidence(record)
            try:
                evidence["classification_breakdown"] = _classification_breakdown(
                    str(record.get("uid") or identifier), timeout
                )
            except (
                ClinVarError, HTTPError, URLError, TimeoutError, OSError,
                ValueError, ElementTree.ParseError,
            ) as exc:
                evidence["breakdown_error"] = str(exc) or type(exc).__name__
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
    if (not chromosome or not reference or not alternate or "," in reference
            or "," in alternate or int(position) < 1 or reference == alternate):
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


def _cached(database, key, include_stale=False):
    if not database.is_file():
        return None
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        row = connection.execute(
            "SELECT payload, retrieved_at FROM evidence WHERE allele_key = ?", (key,)
        ).fetchone()
    if row is None:
        return None
    parsed = _parse_cached(*row, include_stale=True)
    if parsed is None:
        raise ClinVarError("Invalid ClinVar cache payload")
    return parsed if include_stale or parsed["freshness"] == "FRESH" else None


def _parse_cached(raw_payload, retrieved_at, include_stale=False):
    try:
        payload = json.loads(raw_payload)
        if not isinstance(payload, dict) or payload.get("status") not in ("available", "not_found"):
            return None
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        return None
    for field in ("identifiers", "classifications", "review_statuses", "classification_breakdown"):
        if field in payload and not isinstance(payload[field], list):
            return None
    for field in ("review_statuses", "oncogenicity_review_statuses", "somatic_review_statuses", "classification_breakdown"):
        if field in payload and (
            not isinstance(payload[field], list)
            or any(not isinstance(row, dict) for row in payload[field])
        ):
            return None
    try:
        for field in ("review_statuses", "oncogenicity_review_statuses", "somatic_review_statuses"):
            for row in payload.get(field, []):
                int(row.get("stars") or 0)
    except (TypeError, ValueError):
        return None
    payload = _access_metadata(payload, retrieved_at)
    if not include_stale and payload["freshness"] != "FRESH":
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
