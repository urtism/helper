"""Gene-wide molecular analysis using SourceManager's Ensembl JSON cache.

No clinical strength selection. VEP rows are immutable evidence, not a complete
transcript catalog. All cache/network access is public gene/reference data.
"""
import copy
import os
import re
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from helper_next.core.acmg_sources import SourceManager
from helper_next.core.acmg_transcripts import TranscriptReferenceProvider
from pvs1.impact import VERSION, molecular_impact


_FAILURES = OrderedDict()
_FAILURE_LOCK = threading.Lock()


@lru_cache(maxsize=512)
def _source_lock(key):
    return threading.Lock()


def _reference_source(manager, method, identifier, assembly, fetch):
    """Single flight per public reference; short negative cache for outages."""
    provider = manager.transcript_provider
    key = (str(provider.cache), provider.release, provider.rest_url, method, identifier, assembly, fetch)
    with _source_lock(key):
        with _FAILURE_LOCK:
            previous = _FAILURES.get(key)
            if previous and time.monotonic() - previous[0] < 30:
                return copy.deepcopy(previous[1])
        result = getattr(manager, method)(identifier, assembly, fetch=fetch)
        if not result.get("data"):
            with _FAILURE_LOCK:
                _FAILURES[key] = (time.monotonic(), copy.deepcopy(result))
                while len(_FAILURES) > 128:
                    _FAILURES.popitem(last=False)
        return result


def annotation_release(annotation):
    """Read the indexed original VCF header; never equate VEP software with a cache release silently."""
    resources = annotation.get("release_resources") or {}
    candidates = set()
    for key in ("ensembl_release", "cache_version"):
        if str(resources.get(key, "")).isdigit():
            candidates.add(str(resources[key]))
    headers = resources.get("header_metadata") or []
    for line in headers:
        for pattern in (r"\bensembl(?:_release)?\s*[=:]\s*['\"]?(\d+)", r"--cache_version[ =]+['\"]?(\d+)"):
            candidates.update(re.findall(pattern, line, re.IGNORECASE))
    # Standard ##VEP="v116" header is a fallback, explicitly reported as such.
    basis = "VCF cache/Ensembl release"
    if not candidates:
        for line in headers:
            candidates.update(re.findall(r"^##VEP=[\"']?v?(\d+)(?:\D|$)", line))
        basis = "VCF VEP major version (cache release not separately recorded)"
    if len(candidates) > 1:
        return None, "Conflicting Ensembl releases in original annotation header"
    return (next(iter(candidates)), basis) if candidates else (None, "Annotation Ensembl release is not recorded")


def _gene(annotation):
    fields = annotation.get("metadata", {}).get("fields", {})
    for candidate in (fields.get("Gene"), fields.get("Gene_ID"), annotation.get("gene")):
        if candidate and re.fullmatch(r"ENSG[0-9]+(?:\.[0-9]+)?", candidate):
            return candidate
    return None


def analyze_transcripts(detail, selected, manager=None):
    """Return every catalog member plus indexed rows absent from that release.

    Retrieval defaults to enabled for this explicitly requested analysis; the
    existing HELPER_TRANSCRIPT_FETCH=0 switch keeps it strictly offline.
    A missing/mismatched release is surfaced, never replaced by latest Ensembl.
    """
    gene = _gene(selected)
    release, release_basis = annotation_release(selected)
    configured = os.environ.get("HELPER_ENSEMBL_RELEASE", "")
    warnings = []
    release_verified = release is not None
    if not release and configured.isdigit() and "Conflicting" not in release_basis:
        release = configured
        warnings.append(release_basis + "; using explicitly configured HELPER_ENSEMBL_RELEASE for comparison only")
    elif not release:
        warnings.append(release_basis)
    manager = manager or SourceManager(transcript_provider=TranscriptReferenceProvider(release=release or ""))
    if manager.transcript_provider.release != str(release or ""):
        raise ValueError("Source Manager reference release differs from the annotation release")
    assembly = {"hg19": "GRCh37", "hg38": "GRCh38", "grch37": "GRCh37", "grch38": "GRCh38"}.get(
        str(detail["reference_build"]).lower(), detail["reference_build"])
    variant = {"assembly": assembly, "contig": detail["chromosome"], "position": detail["position"],
               "reference_allele": detail["reference"], "alternate_allele": detail["alternate"],
               "coordinate_system": "genomic_1_based"}
    fetch = os.environ.get("HELPER_TRANSCRIPT_FETCH", "1") != "0"
    catalog = _reference_source(manager, "gene_transcripts", gene, assembly, fetch) if gene and release else {}
    data = catalog.get("data") or {}
    if data and (data.get("gene") != gene.split(".")[0] or data.get("assembly") != assembly
                 or data.get("chromosome") != variant["contig"] or data.get("annotation_release") != release):
        data = {}
        warnings.append("Gene catalog does not match the selected allele/gene/assembly/release")
    if not data:
        warnings.append(catalog.get("missing") or "Complete gene transcript catalog unavailable; showing indexed transcripts only")
    annotations = []
    for annotation in detail.get("annotations", []):
        if selected.get("release_key") and annotation.get("release_key") != selected["release_key"]:
            continue
        if (gene and _gene(annotation) == gene) or annotation is selected:
            annotations.append(annotation)
    entries = {tx["transcript"]: copy.deepcopy(tx) for tx in data.get("transcripts", [])}
    by_transcript = {}
    for annotation in annotations:
        name = annotation.get("transcript")
        if not name:
            continue
        resolved = name
        if re.fullmatch(r"ENST[0-9]+", name):
            matches = [tx for tx in entries if tx.split(".")[0] == name]
            if len(matches) == 1:
                resolved = matches[0]
        by_transcript.setdefault(resolved, []).append(annotation)
        if resolved not in entries:
            fields = annotation.get("metadata", {}).get("fields", {})
            entries[resolved] = {"transcript": resolved, "biotype": fields.get("BIOTYPE") or fields.get("Transcript_BioType"),
                                 "outside_catalog": bool(data)}
    selected_name = selected.get("transcript")
    if selected_name and selected_name not in entries and not any(tx.split(".")[0] == selected_name for tx in entries):
        entries[selected_name] = {"transcript": selected_name, "outside_catalog": bool(data)}

    def evaluate(entry):
        name = entry["transcript"]
        rows = by_transcript.get(name, [])
        annotation = next((a for a in rows if a.get("id") == selected.get("id")), rows[0] if rows else None)
        terms = set(term for a in rows for term in (a.get("consequence") or "").replace(",", "&").split("&") if term)
        consequence = "&".join(sorted(terms))
        fields = (annotation or {}).get("metadata", {}).get("fields", {})
        mane_select = fields.get("MANE_SELECT") not in (None, "", "-", ".")
        mane_plus = fields.get("MANE_PLUS_CLINICAL") not in (None, "", "-", ".")
        flags = {"mane": entry.get("mane") if entry.get("mane") in {"SELECT", "PLUS_CLINICAL"} else
                         "SELECT" if mane_select else "PLUS_CLINICAL" if mane_plus else "NONE",
                 "canonical": bool(entry.get("canonical") or (annotation or {}).get("canonical")),
                 "appris": entry.get("appris") or fields.get("APPRIS"), "biotype": entry.get("biotype"),
                 "strand": entry.get("strand"), "exons": entry.get("exons"),
                 "has_translation": entry.get("has_translation"),
                 "selected": name == selected_name or any(a.get("id") == selected.get("id") for a in rows)}
        noncoding = entry.get("has_translation") is False or (
            entry.get("has_translation") is None and flags["biotype"] in {"lncRNA", "miRNA", "snRNA", "snoRNA", "rRNA", "processed_pseudogene"})
        source = {}
        if noncoding:
            row = molecular_impact(variant, gene or "UNKNOWN", name, None, consequence)
            row.update(status="NON_CODING", missing_data=[], warnings=["No applicable CDS"], provenance={"gene_catalog": data.get("artifact_digest")})
        elif entry.get("outside_catalog") or not gene or not release or not re.fullmatch(r"ENST[0-9]+\.[0-9]+", name):
            row = molecular_impact(variant, gene or "UNKNOWN", name, None, consequence)
            row["missing_data"].append("Exact transcript version/gene/release is unavailable or differs from the gene catalog")
        else:
            source = _reference_source(manager, "transcript", name, assembly, fetch and bool(data))
            reference = source.get("data")
            if reference and str(reference.get("annotation_release")) != release:
                reference = None
            row = molecular_impact(variant, gene.split(".")[0], name, reference, consequence, annotation)
            if not reference:
                row["missing_data"].append(source.get("missing") or "Reference release mismatch")
        row.update({k: v for k, v in flags.items() if v is not None})
        row["provenance"].update(annotation_ids=[a.get("id") for a in rows],
                                 annotation_release_basis=release_basis, release_verified=release_verified,
                                 source_status=source.get("status"), gene_catalog_digest=data.get("artifact_digest"))
        return row

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(evaluate, entries.values()))
    results.sort(key=lambda row: (0 if row["selected"] else 1 if row.get("mane") == "SELECT" else
                                 2 if row.get("mane") == "PLUS_CLINICAL" else 3 if row.get("has_translation") or row.get("biotype") == "protein_coding" else 4,
                                 row["transcript"]))
    return {"algorithm_version": VERSION, "gene": gene, "assembly": assembly, "release": release,
            "release_basis": release_basis, "release_verified": release_verified,
            "catalog_complete": bool(data.get("complete")), "warnings": warnings, "transcripts": results}
