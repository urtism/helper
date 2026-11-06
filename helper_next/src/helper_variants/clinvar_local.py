"""Explicit ClinVar tabular snapshot builder and offline SQLite reader.

Independent of clinvar_evidence.sqlite3 and of all application consumers.
Published files are immutable: only a symlink is switched; readers pin its target.
"""
import argparse
import csv
import fcntl
import gzip
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from helper_next.core import biological_identity
from helper_variants import indexer
from helper_variants.liftover import _assembly


SCHEMA_VERSION = 1
BASE_URL = "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/"
FILES = ("variant_summary.txt.gz", "submission_summary.txt.gz")
BATCH_SIZE = 5000
VARIANT_REQUIRED = {
    "AlleleID", "VariationID", "Type", "Name", "GeneID", "GeneSymbol", "HGNC_ID",
    "ClinicalSignificance", "LastEvaluated", "ReviewStatus", "NumberSubmitters",
    "RCVaccession", "PhenotypeIDS", "PhenotypeList", "Origin", "Assembly",
    "ChromosomeAccession", "Chromosome", "PositionVCF", "ReferenceAlleleVCF", "AlternateAlleleVCF",
}
SUBMISSION_REQUIRED = {
    "VariationID", "ClinicalSignificance", "DateLastEvaluated", "Description",
    "SubmittedPhenotypeInfo", "ReportedPhenotypeInfo", "ReviewStatus", "CollectionMethod",
    "OriginCounts", "Submitter", "SCV", "SubmittedGeneSymbol", "ExplanationOfInterpretation",
}
KINDS = (
    ("germline", "ClinicalSignificance", "LastEvaluated", "ReviewStatus", "SCVsForAggregateGermlineClassification"),
    ("somatic_clinical_impact", "SomaticClinicalImpact", "SomaticClinicalImpactLastEvaluated", "ReviewStatusClinicalImpact", "SCVsForAggregateSomaticClinicalImpact"),
    ("oncogenicity", "Oncogenicity", "OncogenicityLastEvaluated", "ReviewStatusOncogenicity", "SCVsForAggregateOncogenicityClassification"),
)
SCHEMA = """
PRAGMA user_version=1;
CREATE TABLE variants (
 variation_id INTEGER PRIMARY KEY, allele_id INTEGER, vcv TEXT, vcv_version INTEGER,
 name TEXT, variant_type TEXT, gene_symbol TEXT, gene_id TEXT, hgnc_id TEXT,
 origins TEXT, number_submitters INTEGER, details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE genomic_positions (
 variation_id INTEGER NOT NULL REFERENCES variants, assembly TEXT NOT NULL,
 chromosome TEXT, position INTEGER, reference TEXT, alternate TEXT,
 match_status TEXT NOT NULL, match_reason TEXT, details_json TEXT NOT NULL
);
CREATE TABLE classifications (
 variation_id INTEGER NOT NULL REFERENCES variants, scope TEXT NOT NULL,
 kind TEXT NOT NULL, classification TEXT, review_status TEXT, stars INTEGER,
 last_evaluated TEXT, condition_name TEXT, condition_ids TEXT, rcv TEXT,
 has_conflict INTEGER, contributing_scvs TEXT,
 UNIQUE(variation_id,scope,kind,rcv)
);
CREATE TABLE submissions (
 source_row INTEGER PRIMARY KEY, scv TEXT NOT NULL, scv_accession TEXT NOT NULL, scv_version INTEGER,
 variation_id INTEGER NOT NULL REFERENCES variants, submitter TEXT,
 clinical_significance TEXT, review_status TEXT, stars INTEGER, last_evaluated TEXT,
 condition_name TEXT, submitted_condition TEXT, somatic_clinical_impact TEXT,
 oncogenicity TEXT, contributes_to_aggregate TEXT, details_json TEXT NOT NULL
);
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class ClinVarLocalError(RuntimeError):
    pass


def database_path():
    configured = os.environ.get("HELPER_CLINVAR_LOCAL_DB", "").strip()
    if configured:
        return Path(configured).expanduser().absolute()
    data = os.environ.get("XDG_DATA_HOME", "").strip()
    root = Path(data).expanduser() if data else Path.home() / ".local" / "share"
    return (root / "helper_variants" / "clinvar_local.sqlite3").absolute()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _text(value):
    return None if value in (None, "", "-", "na", "not available") else value


def _integer(value):
    return int(value) if str(value).isdigit() and int(value) > 0 else None


def _count(value):
    return int(value) if str(value).isdigit() else None


def _id(value):
    result = _integer(value)
    if result is None:
        raise ClinVarLocalError("Invalid ClinVar identifier: {!r}".format(value))
    return result


def review_stars(status, kind="germline"):
    """Official review vocabulary; unknown/new statuses have no inferred rating."""
    ratings = {
        "practice guideline": 4, "reviewed by expert panel": 3,
        "criteria provided, multiple submitters, no conflicts": 2,
        "criteria provided, conflicting classifications": 1,
        "criteria provided, conflicting interpretations": 1,
        "criteria provided, single submitter": 1,
        "no assertion criteria provided": 0, "no classification provided": 0,
        "no assertion provided": 0, "no classification for the individual variant": 0,
        "no classifications from unflagged records": 0, "flagged submission": 0,
    }
    if kind == "somatic_clinical_impact":
        ratings["criteria provided, multiple submitters"] = 2
    return ratings.get(str(status or "").casefold())


def clinvar_url(identifier):
    """Documented Variation/RCV routes; SCV searches open the containing VCV."""
    value = str(identifier)
    if _integer(value):
        return "https://www.ncbi.nlm.nih.gov/clinvar/variation/{}/".format(int(value))
    if re.fullmatch(r"VCV[0-9]{9,}(?:\.[1-9][0-9]*)?", value):
        return "https://www.ncbi.nlm.nih.gov/clinvar/variation/{}/".format(value)
    if re.fullmatch(r"RCV[0-9]{9,}(?:\.[1-9][0-9]*)?", value):
        return "https://www.ncbi.nlm.nih.gov/clinvar/{}/".format(value)
    if re.fullmatch(r"SCV[0-9]{9,}(?:\.[1-9][0-9]*)?", value):
        return "https://www.ncbi.nlm.nih.gov/clinvar/?" + urlencode({"term": value + "[clv_acc]"})
    raise ValueError("Expected a Variation ID or ClinVar accession")


def _hashes(path):
    sha, md5 = hashlib.sha256(), hashlib.md5()
    size = 0
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha.update(chunk)
            md5.update(chunk)
            size += len(chunk)
    return dict(sha256=sha.hexdigest(), md5=md5.hexdigest(), size_bytes=size)


def _expected_md5(text, filename):
    # NCBI uses the BSD form: MD5 (filename) = digest. Also accept md5sum.
    patterns = (r"MD5 \(" + re.escape(filename) + r"\)\s*=\s*([0-9a-fA-F]{32})",
                r"([0-9a-fA-F]{32})\s+\*?(?:[^\r\n]*/)?" + re.escape(filename))
    for pattern in patterns:
        match = re.fullmatch(pattern, text.strip())
        if match:
            return match.group(1).lower()
    raise ClinVarLocalError("Unrecognized NCBI MD5 manifest for " + filename)


def _request(url, method="GET", timeout=120):
    return urlopen(Request(url, method=method, headers={"User-Agent": "HELPER-ClinVarLocal/1"}), timeout=timeout)


def download_sources(directory, *, expected_checksums=None, progress=None):
    """Explicit acquisition, once per file. Never used by the reader."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    _cleanup_download_parts(directory)
    sources = {}
    for filename in FILES:
        url = BASE_URL + filename
        with _request(url + ".md5") as response:
            manifest = response.read(4096).decode("ascii")
        expected = _expected_md5(manifest, filename)
        if expected_checksums is not None and expected != expected_checksums.get(filename):
            raise ClinVarLocalError("NCBI files changed since approval; check again: " + filename)
        path = directory / filename
        # Do not overwrite a previous valid download on failure.
        with tempfile.NamedTemporaryFile(dir=str(directory), prefix=".clinvar-download-", suffix=".part", delete=False) as output:
            fcntl.flock(output.fileno(), fcntl.LOCK_EX)
            partial = Path(output.name)
            try:
                with _request(url) as response:
                    headers = dict(response.headers.items())
                    declared = next((v for k, v in headers.items() if k.lower() == "content-length"), None)
                    transferred = 0
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        output.write(block)
                        transferred += len(block)
                        if progress:
                            progress(dict(phase="DOWNLOADING", filename=filename, bytes=transferred,
                                          total_bytes=int(declared) if declared is not None else None))
                output.flush()
                os.fsync(output.fileno())
                if progress:
                    progress(dict(phase="VALIDATING_DOWNLOAD", filename=filename))
                hashes = _hashes(partial)
                if declared is not None and hashes["size_bytes"] != int(declared):
                    raise ClinVarLocalError("Incomplete download: " + filename)
                if hashes["md5"] != expected:
                    raise ClinVarLocalError("NCBI checksum mismatch: " + filename)
                os.replace(str(partial), str(path))
            finally:
                if partial.exists():
                    partial.unlink()
        sources[filename] = dict(url=url, filename=filename, original_path=str(path.absolute()),
                                 downloaded_at=_now(), http_headers=headers,
                                 expected_md5=expected, checksum_verified=True, **hashes)
    return sources


def check_for_updates(database=None, *, timeout=15):
    """Explicit network operation; compare each published upstream checksum."""
    with ClinVarLocal(database) as reader:
        installed = reader.release()["sources"]
    results = {}
    for name in FILES:
        with _request(BASE_URL + name + ".md5", timeout=timeout) as response:
            current = _expected_md5(response.read(4096).decode("ascii"), name)
        results[name] = dict(installed_md5=installed[name]["md5"], remote_md5=current,
                             changed=current != installed[name]["md5"])
    return results


def installation_status(database=None):
    """Describe CURRENT/BACKUP using pinned readers; never install or clean up."""
    target = Path(database or database_path()).expanduser().absolute()
    result = dict(database=str(target), installed=False, status="missing", error=None,
                  managed=target.is_symlink(), builder_busy=False)
    if not target.exists() and not target.is_symlink():
        return result
    try:
        with _publication_lock(target.parent, exclusive=False):
            # Legacy regular files are still readable, but have no managed BACKUP.
            backup = _roles(target)[1] if target.is_symlink() else None
            with ClinVarLocal(target) as reader:
                result.update(installed=True, status="installed", manifest=reader.release(),
                              snapshot_path=str(reader.path), size_bytes=reader.path.stat().st_size)
            result["backup"] = None
            if backup is not None:
                with ClinVarLocal(backup) as reader:
                    result["backup"] = dict(snapshot_id=reader.release().get("snapshot_id"),
                                            path=str(reader.path), size_bytes=reader.path.stat().st_size)
            versions = target.parent / (target.name + ".snapshots")
            if versions.is_dir():
                try:
                    with _publication_lock(versions, exclusive=False, blocking=False):
                        pass
                except ClinVarLocalError:
                    result["builder_busy"] = True
    except (OSError, sqlite3.Error, ValueError, KeyError, ClinVarLocalError) as exc:
        result.update(status="error", error=str(exc))
    return result


@contextmanager
def _rows(path, required):
    """Read actual header, including submission_summary's commented preamble."""
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(str(path), "rt", encoding="utf-8", newline="") as handle:
        for line in handle:
            if line.startswith("##") or not line.strip():
                continue
            header = line.rstrip("\r\n").lstrip("#").split("\t")
            if "VariationID" in header and len(header) > 1:
                break
            if not line.startswith("#"):
                raise ClinVarLocalError("Missing tabular header in " + str(path))
        else:
            raise ClinVarLocalError("Empty dataset: " + str(path))
        missing = required.difference(header)
        if missing or len(set(header)) != len(header):
            raise ClinVarLocalError("Unsupported header in {}: missing {}".format(path, sorted(missing)))

        def records():
            for number, values in enumerate(csv.reader(handle, delimiter="\t", quoting=csv.QUOTE_NONE), 1):
                if not values:
                    continue
                if len(values) != len(header):
                    raise ClinVarLocalError("Malformed row {} in {}: {} columns, expected {}".format(number, path, len(values), len(header)))
                yield dict(zip(header, values))
        yield header, records()


@lru_cache(maxsize=256)
def _source_contig(assembly, accession, chromosome):
    """Cache qualification of repeated source contigs, never allele identities."""
    build = _assembly(assembly)
    canonical, _ = biological_identity._allele_contig(build, accession or chromosome, None)
    if chromosome not in ("MT", "M", "-", "na"):
        labelled, _ = biological_identity._allele_contig(build, chromosome, None)
        if labelled != canonical:
            raise ValueError("Chromosome label and accession disagree")
    return build, canonical


def _position(row):
    assembly = row["Assembly"]
    position = _integer(row["PositionVCF"])
    ref, alt = _text(row["ReferenceAlleleVCF"]), _text(row["AlternateAlleleVCF"])
    chrom = _text(row["ChromosomeAccession"])
    status, reason = "unqueryable", "No sequence-resolved genomic VCF location"
    try:
        assembly, chrom = _source_contig(assembly, chrom, row["Chromosome"])
        if position and ref and alt and re.fullmatch("[ACGT]+", ref) and re.fullmatch("[ACGT]+", alt) and ref != alt:
            # NCBI explicitly documents these fields as left-shifted VCF alleles.
            position, ref, alt = indexer.normalize_allele(position, ref, alt)
            status, reason = "queryable", "NCBI left-shifted VCF representation; local REF not verified"
    except (ValueError, TypeError, AttributeError) as exc:
        reason = str(exc)
    source = {key: row[key] for key in (
        "Assembly", "Chromosome", "ChromosomeAccession", "Start", "Stop", "ReferenceAllele",
        "AlternateAllele", "PositionVCF", "ReferenceAlleleVCF", "AlternateAlleleVCF", "Cytogenetic") if key in row}
    return (assembly, chrom, position, ref, alt, status, reason, _json(source))


def _variant(row):
    stored = {"VariationID", "AlleleID", "Name", "Type", "GeneSymbol", "GeneID", "HGNC_ID", "Origin", "NumberSubmitters"}
    stored.update({"Assembly", "Chromosome", "ChromosomeAccession", "Start", "Stop", "ReferenceAllele", "AlternateAllele",
                   "PositionVCF", "ReferenceAlleleVCF", "AlternateAlleleVCF", "Cytogenetic", "RCVaccession", "PhenotypeIDS", "PhenotypeList"})
    stored.update(field for kind in KINDS for field in kind[1:])
    extra = {key: value for key, value in row.items() if key not in stored}
    if len(row["RCVaccession"].split("|")) != len(row["PhenotypeList"].split("|")) or len(row["RCVaccession"].split("|")) != len(row["PhenotypeIDS"].split("|")):
        extra["unaligned_condition_source"] = {key: row[key] for key in ("RCVaccession", "PhenotypeList", "PhenotypeIDS")}
    return (_id(row["VariationID"]), _integer(row["AlleleID"]), _text(row["Name"]), _text(row["Type"]),
            _text(row["GeneSymbol"]), _text(row["GeneID"]), _text(row["HGNC_ID"]), _text(row["Origin"]),
            _count(row["NumberSubmitters"]), _json(extra))


def _classifications(row):
    variation_id = _id(row["VariationID"])
    for kind, field, evaluated, review, scvs in KINDS:
        label, status = _text(row.get(field)), _text(row.get(review))
        if label is None and status is None:
            continue
        conflict = int(bool(re.search(r"\bconflict(?:s|ing)?\b", label or "", re.I))) if kind != "somatic_clinical_impact" else None
        yield (variation_id, "variant", kind, label, status, review_stars(status, kind),
               _text(row.get(evaluated)), None, None, "", conflict, _text(row.get(scvs)))
    accessions = (row["RCVaccession"] or "").split("|")
    names, identifiers = row["PhenotypeList"].split("|"), row["PhenotypeIDS"].split("|")
    for index, rcv in enumerate(accessions):
        if not _text(rcv):
            continue
        if not re.fullmatch(r"RCV[0-9]{9,}(?:\.[1-9][0-9]*)?", rcv):
            raise ClinVarLocalError("Invalid RCV: " + rcv)
        # No per-RCV classification in either input file. Never copy the variant aggregate.
        name = _text(names[index]) if len(names) == len(accessions) else None
        ids = _text(identifiers[index]) if len(identifiers) == len(accessions) else None
        yield (variation_id, "condition_reference", "reference", None, None, None, None, name, ids, rcv, None, None)


def _submission(row):
    match = re.fullmatch(r"(SCV[0-9]{9,})(?:\.([1-9][0-9]*))?", row["SCV"])
    if match is None:
        raise ClinVarLocalError("Invalid SCV: " + row["SCV"])
    stored = {"SCV", "VariationID", "Submitter", "ClinicalSignificance", "ReviewStatus", "DateLastEvaluated",
              "ReportedPhenotypeInfo", "SubmittedPhenotypeInfo", "SomaticClinicalImpact", "Oncogenicity", "ContributesToAggregateClassification"}
    return (row["SCV"], match[1], int(match[2]) if match[2] else None, _id(row["VariationID"]),
            _text(row["Submitter"]), _text(row["ClinicalSignificance"]), _text(row["ReviewStatus"]),
            review_stars(row["ReviewStatus"]), _text(row["DateLastEvaluated"]),
            _text(row["ReportedPhenotypeInfo"]), _text(row["SubmittedPhenotypeInfo"]),
            _text(row.get("SomaticClinicalImpact")), _text(row.get("Oncogenicity")),
            _text(row.get("ContributesToAggregateClassification")),
            _json({key: value for key, value in row.items() if key not in stored}))


def _batches(rows, size=BATCH_SIZE):
    batch = []
    for row in rows:
        batch.append(row)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _put_metadata(db, key, value):
    db.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, _json(value)))


def build_database(variant_summary, submission_summary, database=None, *, sources=None, progress=None):
    """One builder per store; failed acquisition/import never changes either role."""
    target = Path(database or database_path()).expanduser().absolute()
    with _build_session(target):
        return _build_database(variant_summary, submission_summary, target, sources=sources, progress=progress)


@contextmanager
def _build_session(target):
    """The existing build/retention lock, shared by CLI and supervised updates."""
    versions = target.parent / (target.name + ".snapshots")
    versions.mkdir(parents=True, exist_ok=True)
    with _publication_lock(versions, blocking=False):
        try:
            yield
        finally:
            try:
                with _publication_lock(target.parent):
                    current, backup, generation = _roles(target)
                    if generation is not None:
                        with _retirement_guards([p for p in _snapshots(versions) if p not in (current, backup)]):
                            for path in _snapshots(versions):
                                if path not in (current, backup):
                                    path.unlink()
                    _remove_stale_artifacts(target)
            except (OSError, ClinVarLocalError):
                pass  # Cleanup cannot turn a failed import into a pointer change.


def download_and_build(directory, database=None, *, expected_current=None, expected_checksums=None,
                       before_download=None, progress=None):
    """Reuse acquisition and builder under one lock, optionally bound to approval."""
    target = Path(database or database_path()).expanduser().absolute()
    with _build_session(target):
        if expected_current is not None:
            with ClinVarLocal(target) as reader:
                if reader.release()["snapshot_id"] != expected_current:
                    raise ClinVarLocalError("CURRENT changed; check again and approve the current snapshot")
            if progress:
                progress(dict(phase="CHECKING"))
            remote = check_for_updates(target)
            if {name: value["remote_md5"] for name, value in remote.items()} != expected_checksums:
                raise ClinVarLocalError("NCBI files changed since approval; check again and approve the new files")
        if before_download:
            before_download()
        if progress:
            progress(dict(phase="DOWNLOADING"))
        sources = download_sources(directory, expected_checksums=expected_checksums, progress=progress)
        result = _build_database(*(Path(directory) / name for name in FILES), database=target,
                                 sources=sources, progress=progress, expected_current=expected_current)
        if progress:
            progress(dict(phase="CLEANING"))
        return result


def _build_database(variant_summary, submission_summary, database, *, sources=None, progress=None,
                    expected_current=None):
    """Stream into staging, validate, then atomically select CURRENT and BACKUP."""
    target = Path(database or database_path()).expanduser().absolute()
    target.parent.mkdir(parents=True, exist_ok=True)
    versions = target.parent / (target.name + ".snapshots")
    versions.mkdir(exist_ok=True)
    started = time.monotonic()
    imported_at = _now()
    manifests = {}
    for filename, path in zip(FILES, (variant_summary, submission_summary)):
        manifest = dict((sources or {}).get(filename, {}))
        hashes = _hashes(path)
        expected = manifest.get("expected_md5")
        sidecar = Path(str(path) + ".md5")
        if expected is None and sidecar.is_file():
            expected = _expected_md5(sidecar.read_text(), filename)
        if expected and hashes["md5"] != expected:
            raise ClinVarLocalError("Source checksum mismatch: " + filename)
        manifest.update(hashes, filename=filename, original_path=str(Path(path).absolute()),
                        expected_md5=expected, checksum_verified=bool(expected))
        manifest.setdefault("url", BASE_URL + filename)
        manifest.setdefault("downloaded_at", None)
        manifests[filename] = manifest
    snapshot_id = "composite-sha256:" + hashlib.sha256(_json({name: item["sha256"] for name, item in manifests.items()}).encode()).hexdigest()
    if progress:
        progress(dict(phase="BUILDING"))
    with tempfile.TemporaryDirectory(prefix=".clinvar-build-", dir=str(versions)) as staging:
        pending = Path(staging) / "dataset.sqlite3"
        db = sqlite3.connect(str(pending))
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA cache_size=-32768")
            db.execute("PRAGMA temp_store=FILE")
            db.executescript(SCHEMA)
            # Duplicate assembly rows must agree on shared variant/aggregate data.
            # Fail closed on an upstream change instead of discarding a new value.
            variant_fields = ("allele_id", "name", "variant_type", "gene_symbol", "gene_id", "hgnc_id", "origins", "number_submitters", "details_json")
            class_fields = ("classification", "review_status", "stars", "last_evaluated", "condition_name", "condition_ids", "has_conflict", "contributing_scvs")
            for table, fields, where in (
                ("variants", variant_fields, "old.variation_id=NEW.variation_id AND NEW.name IS NOT NULL"),
                ("classifications", class_fields, "old.variation_id=NEW.variation_id AND old.scope=NEW.scope AND old.kind=NEW.kind AND old.rcv=NEW.rcv"),
            ):
                differences = " OR ".join("old.{0} IS NOT NEW.{0}".format(field) for field in fields)
                db.execute("CREATE TEMP TRIGGER verify_{0} BEFORE INSERT ON {0} WHEN EXISTS (SELECT 1 FROM {0} old WHERE {1} AND ({2})) BEGIN SELECT RAISE(ABORT,'Inconsistent duplicate ClinVar {0} record'); END".format(table, where, differences))
            counts = {"variant_summary_rows": 0, "submission_summary_rows": 0}
            with _rows(variant_summary, VARIANT_REQUIRED) as (header, rows):
                manifests[FILES[0]]["columns"] = header
                for batch in _batches(rows):
                    db.executemany("INSERT OR IGNORE INTO variants (variation_id,allele_id,name,variant_type,gene_symbol,gene_id,hgnc_id,origins,number_submitters,details_json) VALUES (?,?,?,?,?,?,?,?,?,?)", map(_variant, batch))
                    db.executemany("INSERT INTO genomic_positions VALUES (?,?,?,?,?,?,?,?,?)", ((_id(row["VariationID"]),) + _position(row) for row in batch))
                    db.executemany("INSERT OR IGNORE INTO classifications VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (item for row in batch for item in _classifications(row)))
                    counts["variant_summary_rows"] += len(batch)
                    db.commit()
                    if progress:
                        progress(dict(counts))
            with _rows(submission_summary, SUBMISSION_REQUIRED) as (header, rows):
                manifests[FILES[1]]["columns"] = header
                for batch in _batches(rows):
                    # Haplotype/genotype IDs missing from variant_summary remain identifiable.
                    db.executemany("INSERT OR IGNORE INTO variants(variation_id) VALUES (?)", ((_id(row["VariationID"]),) for row in batch))
                    db.executemany("INSERT INTO submissions VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", map(_submission, batch))
                    counts["submission_summary_rows"] += len(batch)
                    db.commit()
                    if progress:
                        progress(dict(counts))
            if not all(counts.values()):
                raise ClinVarLocalError("Refusing to publish an empty input dataset")
            if progress:
                progress({"phase": "indexing"})
            db.executescript("""
                CREATE INDEX positions_allele ON genomic_positions(assembly,chromosome,position,reference,alternate) WHERE match_status='queryable';
                CREATE INDEX positions_variant ON genomic_positions(variation_id);
                CREATE INDEX classifications_variant ON classifications(variation_id,scope,kind);
                CREATE INDEX submissions_variant ON submissions(variation_id,scv);
                ANALYZE;
            """)
            if progress:
                progress(dict(phase="VALIDATING_DATABASE"))
            for table in ("variants", "genomic_positions", "classifications", "submissions"):
                counts[table] = db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
            counts["coverage"] = [dict(assembly=r[0], match_status=r[1], rows=r[2]) for r in db.execute("SELECT assembly,match_status,COUNT(*) FROM genomic_positions GROUP BY assembly,match_status")]
            counts["distinct_scvs"] = db.execute("SELECT COUNT(DISTINCT scv) FROM submissions").fetchone()[0]
            counts["variants_without_queryable_position"] = db.execute("SELECT COUNT(*) FROM variants v WHERE NOT EXISTS (SELECT 1 FROM genomic_positions p WHERE p.variation_id=v.variation_id AND p.match_status='queryable')").fetchone()[0]
            if counts["submissions"] != counts["submission_summary_rows"]:
                raise ClinVarLocalError("Submission row count mismatch")
            if counts["genomic_positions"] != counts["variant_summary_rows"]:
                raise ClinVarLocalError("Variant location row count mismatch")
            _put_metadata(db, "release", dict(source="NCBI ClinVar", snapshot_id=snapshot_id,
                          snapshot_kind="composite", common_release_verified=False,
                          schema_version=SCHEMA_VERSION, imported_at=imported_at, sources=manifests,
                          counts=counts, validation="complete", import_seconds=time.monotonic() - started))
            db.commit()
            if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)] or db.execute("PRAGMA foreign_key_check").fetchone():
                raise ClinVarLocalError("SQLite integrity validation failed")
        finally:
            db.close()
        # Validate with the same read-only contract used by consumers.
        with ClinVarLocal(pending) as reader:
            release = reader.release()
        with pending.open("rb") as handle:
            os.fsync(handle.fileno())
        if progress:
            progress(dict(phase="PUBLISHING", snapshot_id=snapshot_id))
        with _publication_lock(target.parent):
            current, backup, _ = _roles(target)
            if expected_current is not None and (current is None or _manifest(current).get("snapshot_id") != expected_current):
                raise ClinVarLocalError("CURRENT changed before publication; a new approval is required")
            previous = str(current) if current else None
            # Do not create a third persistent snapshot while the old backup is pinned.
            obsolete = [p for p in _snapshots(versions) if p != current]
            with _retirement_guards(obsolete):
                published = versions / (snapshot_id.split(":", 1)[1][:20] + "-" + uuid.uuid4().hex + ".sqlite3")
                os.rename(str(pending), str(published))
                os.chmod(str(published), 0o444)
                _fsync_directory(versions)
                try:
                    _select_roles(target, published, current)
                except BaseException:
                    # Before commit this file is only an unpublished candidate.
                    # After commit retain it and recover obsolete files on the next cleanup.
                    if _roles(target)[0] != published:
                        published.unlink()
                    raise
                for path in obsolete:
                    path.unlink()
                _remove_stale_artifacts(target)
        return dict(release, database=str(target), snapshot_path=str(published), previous_snapshot=previous,
                    size_bytes=published.stat().st_size, total_seconds=time.monotonic() - started)


@contextmanager
def _publication_lock(directory, *, exclusive=True, blocking=True):
    descriptor = os.open(str(directory), os.O_RDONLY | os.O_DIRECTORY)
    try:
        operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        try:
            fcntl.flock(descriptor, operation | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError as exc:
            raise ClinVarLocalError("ClinVar snapshot operation is busy") from exc
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _switch_pointer(target, published):
    temporary = target.parent / ("." + target.name + "." + uuid.uuid4().hex)
    try:
        temporary.symlink_to(os.path.relpath(str(published), str(target.parent)))
        os.replace(str(temporary), str(target))
        descriptor = os.open(str(target.parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if temporary.is_symlink():
            temporary.unlink()


def _fsync_directory(path):
    descriptor = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _snapshots(versions):
    return sorted(p for p in versions.glob("*.sqlite3") if not p.name.startswith(".") and not p.is_symlink())


def _roles(target):
    """One public symlink selects a directory containing both immutable roles."""
    versions = target.parent / (target.name + ".snapshots")
    if not target.is_symlink():
        if target.exists():
            raise ClinVarLocalError("Refusing to replace an unmanaged regular database: " + str(target))
        return None, None, None
    entry = Path(os.path.abspath(str(target.parent / os.readlink(str(target)))))
    generation = entry.parent if entry.name == "CURRENT" and entry.parent.name.startswith(".roles-") else None
    if generation is not None and generation.parent != versions:
        raise ClinVarLocalError("Unmanaged ClinVar role directory")
    current = target.resolve(strict=True)
    backup_link = generation / "BACKUP" if generation else None
    backup = backup_link.resolve(strict=True) if backup_link and backup_link.is_symlink() else None
    for path in (current, backup):
        if path is not None and path.parent != versions.resolve():
            raise ClinVarLocalError("Snapshot is outside its managed directory")
    return current, backup, generation


def _select_roles(target, current, backup):
    versions = target.parent / (target.name + ".snapshots")
    generation = versions / (".roles-" + uuid.uuid4().hex)
    generation.mkdir()
    try:
        (generation / "CURRENT").symlink_to("../" + current.name)
        if backup is not None:
            (generation / "BACKUP").symlink_to("../" + backup.name)
        _fsync_directory(generation)
        _fsync_directory(versions)
        _switch_pointer(target, generation / "CURRENT")
    except BaseException:
        # A failure after the atomic replace must not break the committed pair.
        if _roles(target)[2] != generation:
            shutil.rmtree(str(generation))
        raise


def _manifest(path):
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        row = db.execute("SELECT value FROM metadata WHERE key='release'").fetchone()
        value = json.loads(row[0]) if row else {}
        if db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION or value.get("validation") != "complete" or value.get("source") != "NCBI ClinVar":
            raise ClinVarLocalError("Unvalidated or unmanaged ClinVar snapshot: " + str(path))
    finally:
        db.close()
    return value


def _open_elsewhere(path, ignored_fd):
    """Also protect already-open, same-user SQLite readers predating file leases.

    New readers coordinate with flock. /proc is a conservative extra check for
    legacy idle connections; arbitrary new uncoordinated opens are unsupported.
    """
    identity = (path.stat().st_dev, path.stat().st_ino)
    proc = Path("/proc")
    if not proc.is_dir():
        return True
    for process in proc.iterdir():
        if not process.name.isdigit():
            continue
        try:
            if process.stat().st_uid != os.getuid():
                continue
            for descriptor in (process / "fd").iterdir():
                if int(process.name) == os.getpid() and descriptor.name == str(ignored_fd):
                    continue
                try:
                    stat = descriptor.stat()
                    if (stat.st_dev, stat.st_ino) == identity:
                        return True
                except FileNotFoundError:
                    continue
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            # Desktop credential helpers deliberately hide their descriptors.
            # They do not execute HELPER/SQLite queries; all other inaccessible
            # same-user processes remain a conservative retirement veto.
            try:
                if (process / "comm").read_text().strip() in {"(sd-pam)", "gnome-keyring-d", "ssh-agent"}:
                    continue
            except OSError:
                pass
            return True
    return False


@contextmanager
def _retirement_guards(paths, *, validate=True):
    handles = []
    try:
        for path in paths:
            if validate:
                _manifest(path)
            handle = path.open("rb")
            handles.append(handle)
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ClinVarLocalError("Snapshot has active readers: " + str(path)) from exc
            if _open_elsewhere(path, handle.fileno()):
                raise ClinVarLocalError("Snapshot has active or uninspectable readers: " + str(path))
        yield
    finally:
        for handle in reversed(handles):
            handle.close()


def _remove_stale_artifacts(target):
    """Called with the store's builder lock and publication lock held."""
    versions = target.parent / (target.name + ".snapshots")
    current, backup, active = _roles(target)
    removed, deferred = [], []
    for path in versions.iterdir():
        if path == active or path.is_symlink():
            continue
        if path.is_dir() and path.name.startswith(".roles-"):
            # Only our two symlinks are owned here, never arbitrary directory contents.
            if all(child.is_symlink() and child.name in ("CURRENT", "BACKUP") for child in path.iterdir()):
                shutil.rmtree(str(path))
                removed.append(str(path))
        elif path.is_dir() and path.name.startswith(".clinvar-build-"):
            files = [child for child in path.iterdir() if child.is_file() and not child.is_symlink()]
            if any(child.name not in ("dataset.sqlite3", "dataset.sqlite3-journal", "dataset.sqlite3-wal", "dataset.sqlite3-shm") for child in path.iterdir()):
                deferred.append(str(path))
                continue
            try:
                with _retirement_guards(files, validate=False):
                    shutil.rmtree(str(path))
                removed.append(str(path))
            except ClinVarLocalError:
                deferred.append(str(path))
        elif path.is_file() and path.name.startswith(".install-") and path.suffix == ".sqlite3":
            try:
                with _retirement_guards([path], validate=False):
                    path.unlink()
                removed.append(str(path))
            except ClinVarLocalError:
                deferred.append(str(path))
    # Interrupted pointer publication can leave only a temporary symlink.
    for path in target.parent.glob("." + target.name + ".*"):
        if path.is_symlink() and re.fullmatch(re.escape("." + target.name + ".") + "[0-9a-f]{32}", path.name):
            path.unlink()
            removed.append(str(path))
    _fsync_directory(versions)
    return removed, deferred


def cleanup_snapshots(database=None, *, legacy_backup=None):
    """Keep CURRENT/BACKUP only; refuse unknown legacy history or pinned retirees."""
    target = Path(database or database_path()).expanduser().absolute()
    versions = target.parent / (target.name + ".snapshots")
    if not versions.is_dir():
        return dict(current=None, backup=None, removed=[], deferred=[])
    with _publication_lock(versions, blocking=False), _publication_lock(target.parent):
        current, backup, generation = _roles(target)
        if current:
            _manifest(current)
        if generation is None and current:
            extras = [p for p in _snapshots(versions) if p != current]
            if legacy_backup is not None:
                backup = Path(legacy_backup).resolve(strict=True)
                if backup not in extras:
                    raise ClinVarLocalError("Legacy backup must be an installed snapshot distinct from CURRENT")
            elif extras:
                raise ClinVarLocalError("Legacy backup history is unknown; select --legacy-backup explicitly")
        if backup:
            _manifest(backup)
        obsolete = [p for p in _snapshots(versions) if p not in (current, backup)]
        with _retirement_guards(obsolete):
            if generation is None and current:
                _select_roles(target, current, backup)
            for path in obsolete:
                path.unlink()
            removed, deferred = _remove_stale_artifacts(target)
        return dict(current=str(current) if current else None, backup=str(backup) if backup else None,
                    removed=[str(p) for p in obsolete] + removed, deferred=deferred)


def rollback(database=None):
    """Atomically swap both roles; leave manifests and database bytes untouched."""
    target = Path(database or database_path()).expanduser().absolute()
    versions = target.parent / (target.name + ".snapshots")
    with _publication_lock(versions, blocking=False), _publication_lock(target.parent):
        current, backup, _ = _roles(target)
        if backup is None:
            raise ClinVarLocalError("No BACKUP is available for rollback")
        _manifest(current)
        _manifest(backup)
        _select_roles(target, backup, current)
        removed, deferred = _remove_stale_artifacts(target)
        return dict(current=str(backup), backup=str(current), removed=removed, deferred=deferred)


def _reader_owner(path):
    for parent in list(path.parents)[:3]:
        if parent.name.endswith(".snapshots"):
            return parent.parent / parent.name[:-len(".snapshots")]
    return path


def _cleanup_download_parts(directory):
    removed, deferred = [], []
    for path in Path(directory).glob(".clinvar-download-*.part"):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            with _retirement_guards([path], validate=False):
                path.unlink()
            removed.append(str(path))
        except ClinVarLocalError:
            deferred.append(str(path))
    return dict(removed=removed, deferred=deferred)


class ClinVarLocal:
    """Pinned offline snapshot. Close explicitly or use as a context manager."""

    def __init__(self, database=None):
        path = Path(database or database_path()).expanduser()
        self._owner = _reader_owner(path.absolute())
        self._lease = None
        try:
            with _publication_lock(self._owner.parent, exclusive=False):
                self.path = path.resolve(strict=True)
                self._lease = self.path.open("rb")
                fcntl.flock(self._lease.fileno(), fcntl.LOCK_SH)
                self.connection = sqlite3.connect(self.path.as_uri() + "?mode=ro&immutable=1", uri=True)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA query_only=ON")
            if self.connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                raise ClinVarLocalError("Unsupported ClinVar local schema")
            if self.release().get("validation") != "complete":
                raise ClinVarLocalError("Snapshot has not passed validation")
        except (OSError, sqlite3.Error, ValueError, KeyError, ClinVarLocalError) as exc:
            if hasattr(self, "connection"):
                self.connection.close()
            if self._lease is not None:
                self._lease.close()
            raise ClinVarLocalError(str(exc)) from exc

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.connection.close()
        if self._lease is not None:
            self._lease.close()
            self._lease = None

    def release(self):
        row = self.connection.execute("SELECT value FROM metadata WHERE key='release'").fetchone()
        if row is None:
            raise ClinVarLocalError("Missing snapshot metadata")
        result = json.loads(row[0])
        if not isinstance(result, dict):
            raise ClinVarLocalError("Invalid snapshot metadata")
        return result

    def variant(self, variation_id):
        row = self.connection.execute("SELECT * FROM variants WHERE variation_id=?", (_id(variation_id),)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["details"] = json.loads(result.pop("details_json"))
        result["source_url"] = clinvar_url(result["variation_id"])
        return result

    def aggregate(self, variation_id):
        return [dict(row) for row in self.connection.execute("SELECT * FROM classifications WHERE variation_id=? AND scope='variant' ORDER BY kind", (_id(variation_id),))]

    def positions(self, variation_id):
        results = []
        for row in self.connection.execute("SELECT * FROM genomic_positions WHERE variation_id=? ORDER BY assembly,chromosome,position", (_id(variation_id),)):
            item = dict(row)
            item["source_coordinates"] = json.loads(item.pop("details_json"))
            results.append(item)
        return results

    def conditions(self, variation_id):
        """RCV references, with unavailable aggregate values explicitly null."""
        return [dict(row, source_url=clinvar_url(row["rcv"]), classification_availability="NOT_IN_SELECTED_DATASETS")
                for row in self.connection.execute("SELECT * FROM classifications WHERE variation_id=? AND scope='condition_reference' ORDER BY rcv", (_id(variation_id),))]

    def condition_classifications(self, variation_id, *, limit=100, offset=0):
        """Disease-specific SCV assertions, explicitly distinct from RCV aggregates.

        Submitted and reported condition strings are retained intact; the files
        do not supply a reliable SCV-to-RCV join or a per-RCV aggregate.
        """
        if not isinstance(limit, int) or not 1 <= limit <= 10000 or not isinstance(offset, int) or offset < 0:
            raise ValueError("Use a limit between 1 and 10000 and a non-negative offset")
        return [dict(row, scope="submission_condition", source_url=clinvar_url(row["scv"]))
                for row in self.connection.execute("""SELECT source_row, scv, variation_id, submitter,
                    clinical_significance, somatic_clinical_impact, oncogenicity,
                    review_status, stars, last_evaluated, condition_name, submitted_condition,
                    contributes_to_aggregate FROM submissions WHERE variation_id=? ORDER BY scv,source_row LIMIT ? OFFSET ?""",
                    (_id(variation_id), limit, offset))]

    def submission_counts(self, variation_id):
        row = self.connection.execute("SELECT COUNT(DISTINCT scv) AS submissions,COUNT(*) AS interpretation_rows,COUNT(DISTINCT submitter) AS submitters FROM submissions WHERE variation_id=?", (_id(variation_id),)).fetchone()
        return dict(row)

    def submission_classification_counts(self, variation_id, *, min_stars=0):
        """Count distinct SCVs per germline label across all pages, not an aggregate."""
        return self.submission_classification_counts_batch([variation_id], min_stars=min_stars).get(_id(variation_id), [])

    def submission_classification_counts_batch(self, variation_ids, *, min_stars=0):
        """Read only grouped counts for list cells, without loading individual SCVs."""
        identifiers = sorted({_id(identifier) for identifier in variation_ids})
        result = {}
        for start in range(0, len(identifiers), 500):
            chunk = identifiers[start:start + 500]
            marks = ",".join("?" for _ in chunk)
            review_filter = " AND stars >= ?" if min_stars else ""
            for row in self.connection.execute("""
                SELECT variation_id, clinical_significance AS label, COUNT(DISTINCT scv) AS count
                FROM submissions WHERE variation_id IN (""" + marks + """) AND clinical_significance IS NOT NULL
                """ + review_filter + """
                GROUP BY variation_id, clinical_significance ORDER BY variation_id, count DESC, label
            """, chunk + [min_stars] if min_stars else chunk):
                result.setdefault(row["variation_id"], []).append(dict(label=row["label"], count=row["count"]))
        return result

    def submissions(self, variation_id, *, limit=100, offset=0):
        if not isinstance(limit, int) or not 1 <= limit <= 10000 or not isinstance(offset, int) or offset < 0:
            raise ValueError("Use a limit between 1 and 10000 and a non-negative offset")
        result = []
        for row in self.connection.execute("SELECT * FROM submissions WHERE variation_id=? ORDER BY scv,source_row LIMIT ? OFFSET ?", (_id(variation_id), limit, offset)):
            item = dict(row)
            item["details"] = json.loads(item.pop("details_json"))
            item["source_url"] = clinvar_url(item["scv"])
            result.append(item)
        return result

    def lookup(self, assembly, chromosome, position, reference, alternate, *, record=None):
        return self.lookup_batch([(assembly, chromosome, position, reference, alternate)], record=record)[0]

    def lookup_batch(self, alleles, *, record=None):
        """One result per request, preserving duplicates/order; one ALT per request.

        Query ga2-qualified coordinates when possible. An indel without FASTA may
        match the exact documented NCBI VCF representation, but never an inferred
        equivalent. An unmatched unnormalized indel is UNRESOLVED, not NOT_FOUND.
        Per-allele REF/normalization checks do not scan/hash the whole FASTA.
        """
        alleles = list(alleles)
        qualified_queries = iter(biological_identity.allele_refs_batch(
            (query for query in alleles if isinstance(query, (list, tuple)) and len(query) == 5),
            record=record, checksum_reference=False,
        ))
        results, keys = [], {}
        for query in alleles:
            if not isinstance(query, (list, tuple)) or len(query) != 5:
                results.append(dict(status="UNRESOLVED", reason="Expected assembly, chromosome, position, REF, ALT", matches=[]))
                continue
            assembly, chromosome, position, ref, alt = query
            identity = next(qualified_queries)
            result = dict(status="UNRESOLVED", matches=[], allele_identity=identity, reason="One sequence-resolved ALT is required")
            results.append(result)
            if len(identity) != 1:
                continue
            qualified = identity[0]
            result["reason"] = qualified["reason"]
            if qualified["status"] == "RESOLVED":
                value = qualified["identity"]
                key = tuple(value[field] for field in ("assembly", "chromosome", "position", "reference", "alternate"))
                result.update(status="NOT_FOUND", match_method="ga2")
            else:
                # Only exact, unchanged upstream VCF coordinates qualify without FASTA.
                if "FASTA/.fai is required" not in qualified["reason"]:
                    continue
                try:
                    build = _assembly(assembly)
                    contig, _ = biological_identity._allele_contig(build, chromosome, None)
                    key = (build, contig, int(position), ref.upper(), alt.upper())
                    result["match_method"] = "exact_ncbi_vcf"
                except (ValueError, TypeError, AttributeError):
                    continue
            keys.setdefault(key, []).append(len(results) - 1)
        unique = list(keys)
        for batch in _batches(unique, 150):  # 750 parameters, compatible with SQLite's older 999 limit.
            values = ",".join("(?,?,?,?,?)" for key in batch)
            sql = """WITH requested(assembly,chromosome,position,reference,alternate) AS (VALUES {})
                SELECT p.* FROM requested r JOIN genomic_positions p
                ON p.assembly=r.assembly AND p.chromosome=r.chromosome AND p.position=r.position
                AND p.reference=r.reference AND p.alternate=r.alternate WHERE p.match_status='queryable'""".format(values)
            found = {}
            for row in self.connection.execute(sql, [value for key in batch for value in key]):
                key = tuple(row[field] for field in ("assembly", "chromosome", "position", "reference", "alternate"))
                found.setdefault(key, set()).add(row["variation_id"])
            for key, ids in found.items():
                ids = sorted(ids)
                for index in keys[key]:
                    results[index].update(status="FOUND" if len(ids) == 1 else "AMBIGUOUS",
                                          reason="Exact allele in the installed snapshot" if len(ids) == 1 else "Multiple ClinVar Variation IDs share this allele",
                                          matches=[dict(variation_id=i, source_url=clinvar_url(i)) for i in ids])
        return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", help="Override HELPER_CLINVAR_LOCAL_DB")
    sub = parser.add_subparsers(dest="command")
    build = sub.add_parser("build", help="Build and safely publish from local official tabular files")
    build.add_argument("--variant-summary", required=True)
    build.add_argument("--submission-summary", required=True)
    download = sub.add_parser("download-build", help="Explicitly download, verify, import and publish")
    download.add_argument("--download-dir", required=True)
    sub.add_parser("info", help="Read installed snapshot metadata without network")
    sub.add_parser("check-updates", help="Explicitly compare official NCBI checksums")
    sub.add_parser("rollback", help="Atomically swap CURRENT and BACKUP without rebuilding")
    cleanup = sub.add_parser("cleanup", help="Apply two-snapshot retention and remove abandoned staging")
    cleanup.add_argument("--legacy-backup", help="Explicit predecessor when migrating legacy stores with unknown history")
    cleanup.add_argument("--download-dir", help="Also clean inactive HELPER partial downloads")
    args = parser.parse_args(argv)
    if args.command is None:
        parser.error("A command is required: build, download-build, info, check-updates, rollback or cleanup")
    try:
        if args.command in ("build", "download-build"):
            if args.command == "download-build":
                result = download_and_build(args.download_dir, database=args.database)
            else:
                result = build_database(args.variant_summary, args.submission_summary, database=args.database)
        elif args.command == "check-updates":
            result = check_for_updates(args.database)
        elif args.command == "rollback":
            result = rollback(args.database)
        elif args.command == "cleanup":
            result = cleanup_snapshots(args.database, legacy_backup=args.legacy_backup)
            if args.download_dir:
                result["downloads"] = _cleanup_download_parts(args.download_dir)
        else:
            with ClinVarLocal(args.database) as reader:
                result = reader.release()
    except (ClinVarLocalError, OSError, sqlite3.Error, ValueError, EOFError) as exc:
        parser.exit(1, "ClinVar local: {}\n".format(exc))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
