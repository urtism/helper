"""Read-only ERepo matching and external assertions; no clinical decisions.

The bounded process cache contains UUID references only, qualified by snapshot.
Every operation pins a fresh reader and retrieves details from that snapshot.
"""
import copy
import re
import sqlite3
import threading
from collections import OrderedDict

from helper_variants import clingen_vcep_local as local
from helper_variants import clinvar_local


SOURCE_ID = "clingen_vcep_variants"
_ERRORS = (OSError, sqlite3.Error, ValueError, TypeError, KeyError,
           local.ClinGenVCEPLocalError, clinvar_local.ClinVarLocalError)
_REFERENCES = OrderedDict()
_CACHE_LOCK = threading.Lock()
_CACHE_SIZE = 4096
_HGVS = re.compile(r"[A-Za-z][A-Za-z0-9_]*\.[1-9][0-9]*(?:\([^()\s]+\))?:[gcnmr]\.\S+")


def _values(value):
    if value is None:
        return []
    return list(value) if isinstance(value, (tuple, list, set)) else [value]


def variant_context(detail):
    """Use allele-specific indexed fields, never loose display-ID extraction.

    Site-level INFO/ID on multiallelic records is not proof for an individual
    ALT. Annotation rows have already passed indexer's allele assignment.
    """
    context = dict(assembly=detail.get("reference_build"),
                   **{key: detail.get(key) for key in ("chromosome", "position", "reference", "alternate")},
                   variation_ids=[], caids=[], hgvs=[], allele_identity=detail.get("allele_identity"))
    evidence = detail.get("clinvar_evidence") or {}
    if evidence.get("matching_status") == "FOUND" and evidence.get("variation_id"):
        context["variation_ids"].append(evidence["variation_id"])
    metadata = detail.get("metadata") or {}
    original = metadata.get("original_vcf") or {}
    fields = []
    if len(original.get("alternates") or []) <= 1:
        fields.extend((metadata.get("clinvar") or {}).items())
        fields.extend((original.get("info") or {}).items())
        for value in str(metadata.get("vcf_id") or "").split(";"):
            if re.fullmatch(r"CA[0-9]+", value):
                context["caids"].append(value)
    for annotation in detail.get("annotations") or []:
        context["hgvs"].extend(_values(annotation.get("hgvsc")))
        fields.extend((annotation.get("metadata", {}).get("fields") or {}).items())
    for key, raw in fields:
        key = str(key).upper().replace("-", "_")
        for value in _values(raw):
            if key in {"CLNVID", "CLINVARVARIATIONID", "CLINVAR_VARIATION_ID", "CLINVAR_ID", "CLINVARID"}:
                # No digit scraping from RCV/SCV accessions or descriptive text.
                if type(value) is int or re.fullmatch(r"[1-9][0-9]*", str(value)):
                    context["variation_ids"].append(value)
            elif key in {"CAID", "CLINGEN_CAID", "ALLELE_REGISTRY_ID", "CLINGEN_ALLELE_REGISTRY_ID"}:
                if re.fullmatch(r"CA[0-9]+", str(value)):
                    context["caids"].append(value)
            elif key in {"HGVSC", "HGVS.C", "HGVSG", "HGVS.G", "HGVS"}:
                context["hgvs"].append(value)
    return context


def _keys(context):
    keys = {}
    for raw in _values(context.get("variation_ids")):
        if not isinstance(raw, bool) and re.fullmatch(r"[1-9][0-9]*", str(raw)):
            keys[("variation_id", int(raw))] = "EXACT_CLINVAR_VARIATION_ID"
    for raw in _values(context.get("caids")):
        if isinstance(raw, str) and re.fullmatch(r"CA[0-9]+", raw):
            keys[("caid", raw)] = "EXACT_ALLELE_REGISTRY_ID"
    for raw in _values(context.get("hgvs")):
        if isinstance(raw, str) and _HGVS.fullmatch(raw):
            keys[("hgvs", raw)] = "EXACT_VERSIONED_HGVS"
    identity = context.get("allele_identity") or {}
    qualified = identity.get("identity") or {}
    if identity.get("status") == "RESOLVED":
        # Only primary nuclear SNVs supported by CACHE-07; ga2 may also resolve
        # indels, MNVs and other contigs, which must not widen this capability.
        primary = local.ASSEMBLY_ACCESSIONS.get(qualified.get("assembly"), {})
        if (qualified.get("chromosome") in {v for k, v in primary.items() if k != "MT"}
                and re.fullmatch(r"[ACGT]", qualified.get("reference", ""))
                and re.fullmatch(r"[ACGT]", qualified.get("alternate", ""))):
            expression = "{}:g.{}{}>{}".format(qualified["chromosome"], qualified["position"],
                                               qualified["reference"], qualified["alternate"])
            keys[("hgvs", expression)] = "EXACT_GENOMIC_SNV_HGVS"
    return keys


def _lookup_keys(reader, keys):
    """Indexed, lightweight batch matching; no whole-dataset preload."""
    hits = {key: {} for key in keys}
    for kind in ("variation_id", "caid", "hgvs"):
        selected = [key[1] for key in keys if key[0] == kind]
        for start in range(0, len(selected), 500):
            chunk = selected[start:start + 500]
            marks = ",".join("?" for _ in chunk)
            if kind == "hgvs":
                sql = ("SELECT h.expression AS alias,a.classification_id,a.caid,a.variation_id FROM hgvs h "
                       "JOIN assertions a ON a.classification_id=h.classification_id WHERE h.expression IN (" + marks + ")")
            else:
                sql = "SELECT " + kind + " AS alias,classification_id,caid,variation_id FROM assertions WHERE " + kind + " IN (" + marks + ")"
            for row in reader.connection.execute(sql, chunk):
                hits[(kind, row["alias"])][row["classification_id"]] = (row["caid"], row["variation_id"])
    return hits


def _cached(key):
    with _CACHE_LOCK:
        result = _REFERENCES.get(key)
        if result is not None:
            _REFERENCES.move_to_end(key)
        return copy.deepcopy(result)


def _remember(key, references):
    with _CACHE_LOCK:
        _REFERENCES[key] = copy.deepcopy(references)
        _REFERENCES.move_to_end(key)
        while len(_REFERENCES) > _CACHE_SIZE:
            _REFERENCES.popitem(last=False)


def _assertion(row):
    # Transport source facts; no default strength or interpretation of codes.
    fields = ("classification_id", "classification_version", "version_availability", "caid", "variation_id",
              "gene_symbol", "gene_id", "disease", "disease_id", "mode_of_inheritance", "classification",
              "expert_panel", "expert_panel_id", "approval_date", "published_date", "retracted", "summary",
              "guideline_url", "available_versions", "official_url", "source_url", "pubmed_articles", "snapshot_id")
    result = {field: row.get(field) for field in fields}
    result.update(source_id=SOURCE_ID, classification_origin="EXTERNAL_VCEP_ASSERTION")
    result["criteria"] = [dict(item, strength=item["code"].partition("_")[2] or None) for item in row["criteria"]]
    result["met_codes"] = [item["code"] for item in row["criteria"] if item["status"] == "Met"]
    result["not_met_codes"] = [item["code"] for item in row["criteria"] if item["status"] == "Not Met"]
    return result


def _conflict(keys, attempts, records):
    for kind, column in (("caid", "caid"), ("variation_id", "variation_id")):
        requested = {value for key_kind, value in keys if key_kind == kind}
        observed = {record[column] for record in records if record[column] is not None}
        if len(requested) > 1 or len(observed) > 1 or (requested and observed and not observed.issubset(requested)):
            return "Discordant " + kind + " identifiers; no allele equivalence selected"
    # A source omission is not a contradiction. A different HGVS on the SAME
    # accession/version is a concrete discrepancy and must remain ambiguous.
    missing_hgvs = [attempt["value"] for attempt in attempts
                    if attempt["kind"] == "hgvs" and not attempt["assertion_ids"]]
    for expression in missing_hgvs:
        accession = expression.split(":", 1)[0] + ":"
        for row in records:
            if any(value.startswith(accession) for value in row["hgvs"]):
                return "Discordant exact HGVS on the same accession/version"
    return None


def _packet(status, context, manifest=None, *, reason=None, attempts=None, records=(), methods=None):
    methods = methods or []
    result = dict(source_id=SOURCE_ID, source="ClinGen VCEP ERepo", status=status, matching_status=status,
                  availability="AVAILABLE" if status == "FOUND" else status,
                  snapshot_id=(manifest or {}).get("snapshot_id"), provenance=manifest or {},
                  freshness="SNAPSHOT" if manifest else "UNKNOWN", reason=reason,
                  match_methods=methods, match_attempts=attempts or [],
                  reference_status="UNVERIFIED" if "EXACT_GENOMIC_SNV_HGVS" in methods else "NOT_APPLICABLE",
                  allele_identity=context.get("allele_identity"), clinical_context_status="NOT_SELECTED",
                  application="INFORMATION_ONLY", assertions=[], candidate_assertions=[])
    if status in {"FOUND", "AMBIGUOUS"}:
        result["assertions" if status == "FOUND" else "candidate_assertions"] = [_assertion(row) for row in records]
    return result


def lookup_batch(contexts, database=None):
    """Caller supplies qualified ga2 identities; pin current and fail locally."""
    contexts = list(contexts)
    if not contexts:
        return []
    try:
        with local.ClinGenVCEPLocal(database) as reader:
            manifest = reader.release()
            key_sets = [_keys(context) for context in contexts]
            cache_keys = [(manifest["snapshot_id"], tuple(sorted(keys))) for keys in key_sets]
            references = [_cached(key) if keys else None for key, keys in zip(cache_keys, key_sets)]
            needed = set(key for keys, cached in zip(key_sets, references) if cached is None for key in keys)
            hits = _lookup_keys(reader, needed)
            for index, keys in enumerate(key_sets):
                if references[index] is None:
                    references[index] = [dict(kind=kind, value=value, assertion_ids=sorted(hits[(kind, value)]))
                                         for kind, value in keys]
            ids = sorted({identifier for attempts in references for attempt in attempts for identifier in attempt["assertion_ids"]})
            records = {row["classification_id"]: row for row in reader.assertions_by_ids(ids)}
            if set(ids) != records.keys():
                raise local.ClinGenVCEPLocalError("Cached UUID absent from the selected snapshot")
            results = []
            for context, keys, key, attempts in zip(contexts, key_sets, cache_keys, references):
                ids = sorted({identifier for attempt in attempts for identifier in attempt["assertion_ids"]})
                selected = [records[identifier] for identifier in ids]
                reason = _conflict(keys, attempts, selected)
                status = "UNSUPPORTED" if not keys else "AMBIGUOUS" if reason else "FOUND" if ids else "NOT_FOUND"
                if not keys:
                    reason = "No supported exact identifier/HGVS or qualified primary SNV; indels require trusted identifiers or exact HGVS"
                methods = sorted({method for alias, method in keys.items() if any(
                    attempt["kind"] == alias[0] and attempt["value"] == alias[1] and attempt["assertion_ids"] for attempt in attempts)})
                # A genomic attempt remains unverified even when it found no row.
                packet = _packet(status, context, manifest, reason=reason, attempts=attempts, records=selected, methods=methods)
                if "EXACT_GENOMIC_SNV_HGVS" in keys.values():
                    packet["reference_status"] = "UNVERIFIED"
                results.append(packet)
                if keys:
                    _remember(key, attempts)
            return results
    except _ERRORS as exc:
        return [_packet("ERROR", context, reason=str(exc)) for context in contexts]
