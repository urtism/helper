"""Official ERepo tabular assertions, optional bulk summary metadata, offline reader.

No clinical consumer is connected here. Snapshot publication and reader protection
reuse ClinVar's filesystem primitives; the biological schemas remain independent.
"""
import argparse
import csv
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import uuid
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

from helper_variants import clinvar_local as snapshots
from helper_variants.liftover import ASSEMBLY_ACCESSIONS, _assembly, _chromosome


SCHEMA_VERSION = 1
SOURCE = "ClinGen ERepo VCEP"
SOURCE_URL = "https://erepo.clinicalgenome.org/evrepo/"
EXPORT_URL = SOURCE_URL + "api/summary/classifications/download"
SUMMARY_URL = SOURCE_URL + "api/summary/classifications"
TERMS_URL = "https://www.clinicalgenome.org/docs/terms-of-use/"
COLUMNS = (
    "Variation", "ClinVar Variation Id", "Allele Registry Id", "HGVS Expressions",
    "HGNC Gene Symbol", "Disease", "Mondo Id", "Mode of Inheritance", "Assertion",
    "Applied Evidence Codes (Met)", "Applied Evidence Codes (Not Met)",
    "Summary of interpretation", "PubMed Articles", "Expert Panel", "Guideline",
    "Approval Date", "Published Date", "Retracted", "Evidence Repo Link", "Uuid",
)
SCHEMA = """
PRAGMA user_version=1;
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE assertions (
 classification_id TEXT PRIMARY KEY, classification_version TEXT,
 caid TEXT, variation_id INTEGER, scv TEXT, variation TEXT, gene_symbol TEXT,
 gene_id TEXT, disease TEXT, disease_id TEXT, mode_of_inheritance TEXT,
 classification TEXT NOT NULL, expert_panel TEXT NOT NULL, expert_panel_id TEXT,
 guideline_url TEXT, approval_date TEXT, published_date TEXT,
 retracted INTEGER CHECK(retracted IN (0,1)), source_url TEXT NOT NULL,
 summary TEXT, pubmed_json TEXT NOT NULL, versions_json TEXT NOT NULL,
 content_sha256 TEXT NOT NULL, original_json TEXT NOT NULL, summary_metadata_json TEXT
);
CREATE TABLE hgvs (
 classification_id TEXT NOT NULL REFERENCES assertions,
 expression TEXT NOT NULL, PRIMARY KEY(classification_id,expression)
);
CREATE TABLE criteria (
 classification_id TEXT NOT NULL REFERENCES assertions,
 ordinal INTEGER NOT NULL, code TEXT NOT NULL, status TEXT NOT NULL,
 PRIMARY KEY(classification_id,status,ordinal)
);
CREATE INDEX assertions_caid ON assertions(caid);
CREATE INDEX assertions_variation ON assertions(variation_id);
CREATE INDEX assertions_gene ON assertions(gene_symbol COLLATE NOCASE);
CREATE INDEX assertions_disease ON assertions(disease_id);
CREATE INDEX assertions_panel ON assertions(expert_panel);
CREATE INDEX assertions_panel_id ON assertions(expert_panel_id);
CREATE INDEX hgvs_expression ON hgvs(expression,classification_id);
CREATE INDEX criteria_code ON criteria(code,status,classification_id);
"""


class ClinGenVCEPLocalError(RuntimeError):
    pass


def database_path():
    configured = os.environ.get("HELPER_CLINGEN_VCEP_LOCAL_DB", "").strip()
    if configured:
        return Path(configured).expanduser().absolute()
    data = os.environ.get("XDG_DATA_HOME", "").strip()
    root = Path(data).expanduser() if data else Path.home() / ".local/share"
    return (root / "helper_variants/clingen_vcep_local.sqlite3").absolute()


def classification_url(identifier):
    return SOURCE_URL + "ui/classification/" + str(uuid.UUID(str(identifier)))


def _list(value):
    return [part.strip() for part in value.split(",") if part.strip()]


@contextmanager
def _rows(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle, delimiter="\t", strict=True)
        header = rows.fieldnames or []
        if not set(COLUMNS).issubset(header) or len(set(header)) != len(header):
            raise ClinGenVCEPLocalError("Missing/duplicate ERepo TSV columns: " + str(sorted(set(COLUMNS) - set(header))))
        yield header, rows


def _request(url):
    return urlopen(Request(url, headers={"User-Agent": "HELPER-ClinGenVCEP/1"}), timeout=120)


def download_sources(directory, *, with_summary=True):
    """Explicit downloads only. Summary pages add versions/IDs absent from TSV.

    No per-variant API calls or detailed evidence documents. The summary API's
    default excludes retracted records; those remain intact from the TSV.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    sources = {}
    path = directory / "erepo.tsv"
    with tempfile.NamedTemporaryFile(dir=directory, prefix=".vcep-download-", delete=False) as output:
        pending = Path(output.name)
        try:
            with _request(EXPORT_URL) as response:
                headers = dict(response.headers.items())
                length = response.headers.get("Content-Length")
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
            if length is not None and pending.stat().st_size != int(length):
                raise ClinGenVCEPLocalError("Incomplete ERepo download")
            with _rows(pending):
                pass
            os.replace(pending, path)
        finally:
            pending.unlink(missing_ok=True)
    sources["export"] = dict(url=EXPORT_URL, downloaded_at=snapshots._now(), http_headers=headers,
                             upstream_checksum_verified=False, **snapshots._hashes(path))
    if with_summary:
        records, pages = [], []
        # Large bulk pages, with explicit pagination if ERepo grows beyond one.
        for page in range(1, 1001):
            url = SUMMARY_URL + "?pgSize=20000&pg=" + str(page)
            with _request(url) as response:
                payload = json.load(response)
            data = payload.get("data")
            if payload.get("status", {}).get("code") != 200 or not isinstance(data, list):
                raise ClinGenVCEPLocalError("Invalid ERepo summary response")
            records.extend(data)
            pages.append(dict(url=url, metadata=payload.get("metadata")))
            if len(data) < 20000:
                break
        else:
            raise ClinGenVCEPLocalError("ERepo summary pagination limit exceeded")
        path = directory / "erepo-summary.json"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         prefix=".vcep-download-", delete=False) as output:
            pending = Path(output.name)
            try:
                json.dump(dict(data=records, pages=pages), output, ensure_ascii=False)
                output.flush()
                os.fsync(output.fileno())
                os.replace(pending, path)
            finally:
                pending.unlink(missing_ok=True)
        sources["summary"] = dict(url=SUMMARY_URL, pages=pages, downloaded_at=snapshots._now(),
                                  upstream_checksum_verified=False, **snapshots._hashes(path))
    return sources


def _summary_records(path):
    if path is None:
        return {}
    with Path(path).open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ClinGenVCEPLocalError("Expected an official ERepo summary data array")
    if "status" in payload and payload["status"].get("code") != 200:
        raise ClinGenVCEPLocalError("ERepo summary reports an error")
    result = {}
    for item in payload["data"]:
        if not isinstance(item, dict):
            raise ClinGenVCEPLocalError("Invalid ERepo summary record")
        identifier = item.get("uuid")
        if not identifier or identifier in result:
            raise ClinGenVCEPLocalError("Missing/duplicate summary UUID")
        result[identifier] = item
    return result


def _assertion(row, summary):
    identifier = str(uuid.UUID(row["Uuid"]))
    if identifier != row["Uuid"]:
        raise ClinGenVCEPLocalError("Noncanonical ERepo UUID")
    for key in ("Assertion", "Expert Panel", "Evidence Repo Link"):
        if not row[key].strip():
            raise ClinGenVCEPLocalError("Missing assertion field: " + key)
    variation_id = row["ClinVar Variation Id"] or None
    if variation_id is not None and (not variation_id.isdigit() or int(variation_id) <= 0):
        raise ClinGenVCEPLocalError("Invalid ClinVar Variation ID")
    caid = row["Allele Registry Id"] or None
    if caid and not re.fullmatch(r"CA[0-9]+", caid):
        raise ClinGenVCEPLocalError("Invalid CAid")
    for key in ("Approval Date", "Published Date"):
        if row[key]:
            date.fromisoformat(row[key])
    if row["Retracted"] not in ("", "true", "false"):
        raise ClinGenVCEPLocalError("Unknown retraction state")
    metadata = None
    if summary is not None:
        # Never attach another context/version to an assertion by variant alone.
        for field, column in (("caId", "Allele Registry Id"), ("cvId", "ClinVar Variation Id"),
                              ("gene", "HGNC Gene Symbol"), ("mondoId", "Mondo Id"),
                              ("condition", "Disease"), ("moi", "Mode of Inheritance"),
                              ("preferredVarTitle", "Variation"),
                              ("classification", "Assertion"), ("ep", "Expert Panel"),
                              ("approvedDate", "Approval Date"), ("publishedDate", "Published Date")):
            if str(summary.get(field) or "") != row[column]:
                raise ClinGenVCEPLocalError("TSV/summary mismatch for {}: {}".format(identifier, field))
        if summary.get("retracted") is not {"": None, "true": True, "false": False}[row["Retracted"]]:
            raise ClinGenVCEPLocalError("TSV/summary mismatch for {}: retracted".format(identifier))
        # ERepo flattens whitespace in TSV narrative fields. Retain those bytes
        # unchanged, but compare the words before binding document metadata.
        if " ".join(str(summary.get("summaryDesc") or "").split()) != " ".join(row["Summary of interpretation"].split()):
            raise ClinGenVCEPLocalError("TSV/summary mismatch for {}: summaryDesc".format(identifier))
        for field, column in (("metCodes", "Applied Evidence Codes (Met)"),
                              ("unMetCodes", "Applied Evidence Codes (Not Met)")):
            if set(summary.get(field) or []) != set(_list(row[column])):
                raise ClinGenVCEPLocalError("TSV/summary mismatch for {}: {}".format(identifier, field))
        # A few source labels contain commas (e.g. 'ETHE1, EX4DEL'). The API
        # array removes this ambiguity; validate its original joined form.
        if ",".join(summary.get("hgvs") or []) != row["HGVS Expressions"]:
            raise ClinGenVCEPLocalError("TSV/summary mismatch for {}: hgvs".format(identifier))
        metadata = {key: summary.get(key) for key in ("PCERDocID", "docVersion", "versionsList", "geneNcbiId", "affiliationId")}
        version = metadata["docVersion"]
        if version is not None and not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
            raise ClinGenVCEPLocalError("Invalid classification document version")
        versions = metadata["versionsList"]
        if versions is not None and (not isinstance(versions, list) or any(not isinstance(v, str) for v in versions)):
            raise ClinGenVCEPLocalError("Invalid ERepo versions list")
    original = snapshots._json(row)
    encoded_metadata = snapshots._json(metadata) if metadata is not None else None
    content_hash = hashlib.sha256(snapshots._json(dict(export=row, summary=metadata)).encode()).hexdigest()
    return (identifier, metadata.get("docVersion") if metadata else None,
            caid, int(variation_id) if variation_id else None, None, row["Variation"] or None,
            row["HGNC Gene Symbol"] or None,
            "NCBI_GENE:" + str(metadata["geneNcbiId"]) if metadata and metadata.get("geneNcbiId") else None,
            row["Disease"] or None, row["Mondo Id"] or None, row["Mode of Inheritance"] or None,
            row["Assertion"], row["Expert Panel"], metadata.get("affiliationId") if metadata else None,
            row["Guideline"] or None, row["Approval Date"] or None, row["Published Date"] or None,
            {"": None, "true": 1, "false": 0}[row["Retracted"]], row["Evidence Repo Link"],
            row["Summary of interpretation"] or None, snapshots._json(_list(row["PubMed Articles"])),
            snapshots._json(metadata.get("versionsList") if metadata else None), content_hash, original, encoded_metadata)


def build_database(export, database=None, *, summary=None, sources=None):
    """Validate in staging; errors never change CURRENT or BACKUP."""
    target = Path(database or database_path()).expanduser().absolute()
    versions = target.parent / (target.name + ".snapshots")
    versions.mkdir(parents=True, exist_ok=True)
    with snapshots._publication_lock(versions, blocking=False):
        manifests = {}
        for name, path, url in (("export", export, EXPORT_URL), ("summary", summary, SUMMARY_URL)):
            if path is None:
                continue
            item = dict((sources or {}).get(name, {}))
            hashes = snapshots._hashes(path)
            if item.get("sha256") and item["sha256"] != hashes["sha256"]:
                raise ClinGenVCEPLocalError("Source SHA-256 mismatch: " + name)
            item.update(hashes, original_path=str(Path(path).absolute()))
            item.setdefault("url", url)
            item.setdefault("downloaded_at", None)
            item.setdefault("upstream_checksum_verified", False)
            manifests[name] = item
        snapshot_id = "erepo-sha256:" + hashlib.sha256(snapshots._json(dict(
            schema_version=SCHEMA_VERSION,
            sources={key: value["sha256"] for key, value in manifests.items()})).encode()).hexdigest()
        summaries = _summary_records(summary)
        seen = set()
        with tempfile.TemporaryDirectory(prefix=".vcep-build-", dir=versions) as staging:
            pending = Path(staging) / "dataset.sqlite3"
            db = sqlite3.connect(str(pending))
            try:
                db.execute("PRAGMA foreign_keys=ON")
                db.executescript(SCHEMA)
                with _rows(export) as (header, rows):
                    manifests["export"]["columns"] = header
                    for row in rows:
                        if None in row or any(value is None for value in row.values()):
                            raise ClinGenVCEPLocalError("Ragged TSV row at line " + str(rows.line_num))
                        if summary is not None and row["Uuid"] not in summaries and row["Retracted"] != "true":
                            raise ClinGenVCEPLocalError("Incomplete bulk summary; active UUID missing: " + row["Uuid"])
                        item = _assertion(row, summaries.get(row["Uuid"]))
                        identifier = item[0]
                        db.execute("INSERT INTO assertions VALUES (" + ",".join("?" for _ in item) + ")", item)
                        expressions = (summaries[identifier]["hgvs"] if identifier in summaries
                                       else _list(row["HGVS Expressions"]))
                        # Only accession-qualified HGVS expressions are identity
                        # aliases; arbitrary variant titles remain in original.
                        db.executemany("INSERT OR IGNORE INTO hgvs VALUES (?,?)",
                                       ((identifier, value) for value in expressions
                                        if re.match(r"^[A-Za-z][A-Za-z0-9_]*\.[0-9]+(?:\([^)]*\))?:[gcnmrp]\.", value)))
                        for status, column in (("Met", "Applied Evidence Codes (Met)"),
                                               ("Not Met", "Applied Evidence Codes (Not Met)")):
                            db.executemany("INSERT INTO criteria VALUES (?,?,?,?)",
                                           ((identifier, i, code, status) for i, code in enumerate(_list(row[column]), 1)))
                        seen.add(identifier)
                if not seen:
                    raise ClinGenVCEPLocalError("Refusing to publish an empty export")
                if summaries.keys() - seen:
                    raise ClinGenVCEPLocalError("Summary contains UUIDs absent from TSV; acquire both sources again")
                counts = {table: db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                          for table in ("assertions", "hgvs", "criteria")}
                for key, sql in (
                    ("versioned_assertions", "classification_version IS NOT NULL"),
                    ("retracted_assertions", "retracted=1"), ("unknown_retraction", "retracted IS NULL"),
                    ("without_caid", "caid IS NULL"), ("without_variation_id", "variation_id IS NULL")):
                    counts[key] = db.execute("SELECT COUNT(*) FROM assertions WHERE " + sql).fetchone()[0]
                counts["expert_panels"] = db.execute("SELECT COUNT(DISTINCT expert_panel) FROM assertions").fetchone()[0]
                release = dict(source=SOURCE, schema_version=SCHEMA_VERSION, snapshot_id=snapshot_id,
                               imported_at=snapshots._now(), source_version=None, sources=manifests,
                               counts=counts, validation="complete", license="CC0-1.0", terms_url=TERMS_URL,
                               attribution="Clinical Genome Resource (ClinGen), Evidence Repository; see downloaded_at for access dates.",
                               limitations=["TSV has no classification version, SCV or stable gene IDs; summary metadata is optional.",
                                            "Summary defaults to non-retracted records; missing versions remain null.",
                                            "versionsList lists known versions; historical assertion contents are not downloaded.",
                                            "HGVS matching is exact and accession-version specific; genomic lookup supports primary nuclear SNVs only."])
                db.execute("INSERT INTO metadata VALUES ('release',?)", (snapshots._json(release),))
                db.execute("ANALYZE")
                db.commit()
                if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)] or db.execute("PRAGMA foreign_key_check").fetchone():
                    raise ClinGenVCEPLocalError("SQLite integrity validation failed")
            finally:
                db.close()
            with ClinGenVCEPLocal(pending):
                pass
            with pending.open("rb") as handle:
                os.fsync(handle.fileno())
            with snapshots._publication_lock(target.parent):
                current, backup, _ = snapshots._roles(target)
                for path in (current, backup):
                    if path:
                        _validate_snapshot(path)
                obsolete = [path for path in snapshots._snapshots(versions) if path != current]
                for path in obsolete:
                    _validate_snapshot(path)
                with snapshots._retirement_guards(obsolete, validate=False):
                    published = versions / (uuid.uuid4().hex + ".sqlite3")
                    os.rename(pending, published)
                    os.chmod(published, 0o444)
                    snapshots._fsync_directory(versions)
                    try:
                        snapshots._select_roles(target, published, current)
                    except BaseException:
                        if snapshots._roles(target)[0] != published:
                            published.unlink()
                        raise
                    for path in obsolete:
                        path.unlink()
                    snapshots._remove_stale_artifacts(target)
            return dict(release, database=str(target), snapshot_path=str(published), size_bytes=published.stat().st_size)


def _validate_snapshot(path):
    # Caller already holds the publication lock. Avoid acquiring it recursively.
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        _release(db)
    finally:
        db.close()


def _release(connection):
    row = connection.execute("SELECT value FROM metadata WHERE key='release'").fetchone()
    value = json.loads(row[0]) if row else {}
    if (not isinstance(value, dict) or value.get("source") != SOURCE
            or value.get("validation") != "complete" or not value.get("snapshot_id")
            or connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION):
        raise ClinGenVCEPLocalError("Invalid or incompatible ClinGen VCEP snapshot")
    return value


def installation_status(database=None):
    target = Path(database or database_path()).expanduser().absolute()
    result = dict(database=str(target), installed=False, status="missing", error=None, managed=target.is_symlink())
    if not target.exists() and not target.is_symlink():
        return result
    try:
        with snapshots._publication_lock(target.parent, exclusive=False):
            current, backup, _ = snapshots._roles(target) if target.is_symlink() else (target, None, None)
            result["manifest"] = _read_manifest(current)
            result.update(installed=True, status="installed", snapshot_path=str(current), size_bytes=current.stat().st_size)
            result["backup"] = dict(path=str(backup), snapshot_id=_read_manifest(backup)["snapshot_id"],
                                    size_bytes=backup.stat().st_size) if backup else None
    except (OSError, sqlite3.Error, ValueError, ClinGenVCEPLocalError, snapshots.ClinVarLocalError) as exc:
        result.update(installed=False, status="error", error=str(exc))
    return result


def _read_manifest(path):
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        return _release(connection)
    finally:
        connection.close()


def rollback(database=None):
    target = Path(database or database_path()).expanduser().absolute()
    versions = target.parent / (target.name + ".snapshots")
    with snapshots._publication_lock(versions, blocking=False), snapshots._publication_lock(target.parent):
        current, backup, _ = snapshots._roles(target)
        if backup is None:
            raise ClinGenVCEPLocalError("No BACKUP is available")
        _validate_snapshot(current)
        _validate_snapshot(backup)
        snapshots._select_roles(target, backup, current)
        snapshots._remove_stale_artifacts(target)
    return installation_status(target)


def cleanup_snapshots(database=None):
    """Recover interrupted builds/publications, protecting every active reader."""
    target = Path(database or database_path()).expanduser().absolute()
    versions = target.parent / (target.name + ".snapshots")
    if not versions.is_dir():
        return dict(removed=[], deferred=[])
    with snapshots._publication_lock(versions, blocking=False), snapshots._publication_lock(target.parent):
        current, backup, _ = snapshots._roles(target)
        obsolete = [path for path in snapshots._snapshots(versions) if path not in (current, backup)]
        for path in (current, backup, *obsolete):
            if path:
                _validate_snapshot(path)
        with snapshots._retirement_guards(obsolete, validate=False):
            for path in obsolete:
                path.unlink()
        removed, deferred = snapshots._remove_stale_artifacts(target)
        for path in versions.glob(".vcep-build-*"):
            if path.is_symlink() or not path.is_dir():
                continue
            children = list(path.iterdir())
            if any(child.is_symlink() or not child.is_file() or child.name not in
                   ("dataset.sqlite3", "dataset.sqlite3-journal", "dataset.sqlite3-wal", "dataset.sqlite3-shm")
                   for child in children):
                deferred.append(str(path))
                continue
            try:
                with snapshots._retirement_guards(children, validate=False):
                    for child in children:
                        child.unlink()
                    path.rmdir()
                removed.append(str(path))
            except snapshots.ClinVarLocalError:
                deferred.append(str(path))
        snapshots._fsync_directory(versions)
        return dict(removed=[str(path) for path in obsolete] + removed, deferred=deferred)


class ClinGenVCEPLocal:
    """Read-only, pinned snapshot; all lookups retain individual assertions."""

    def __init__(self, database=None):
        path = Path(database or database_path()).expanduser().absolute()
        self._lease = None
        self.connection = None
        try:
            owner = snapshots._reader_owner(path)
            with snapshots._publication_lock(owner.parent, exclusive=False):
                self.path = path.resolve(strict=True)
                self._lease = self.path.open("rb")
                fcntl.flock(self._lease.fileno(), fcntl.LOCK_SH)
                self.connection = sqlite3.connect(self.path.as_uri() + "?mode=ro&immutable=1", uri=True)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA query_only=ON")
            self._manifest = _release(self.connection)
        except (OSError, sqlite3.Error, ValueError, ClinGenVCEPLocalError, snapshots.ClinVarLocalError) as exc:
            self.close()
            raise ClinGenVCEPLocalError(str(exc)) from exc

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self.connection is not None:
            self.connection.close()
        if self._lease is not None:
            self._lease.close()
            self._lease = None

    def release(self):
        return dict(self._manifest)

    def query(self, *, classification_id=None, caid=None, variation_id=None, hgvs=None,
              gene=None, disease_id=None, expert_panel=None, expert_panel_id=None,
              include_retracted=True, limit=100, offset=0):
        if type(limit) is not int or not 1 <= limit <= 10000 or type(offset) is not int or offset < 0:
            raise ValueError("Use limit 1..10000 and a non-negative offset")
        clauses, values = [], []
        for field, value in (("classification_id", classification_id), ("caid", caid),
                             ("variation_id", variation_id), ("gene_symbol", gene),
                             ("disease_id", disease_id), ("expert_panel", expert_panel),
                             ("expert_panel_id", expert_panel_id)):
            if value is not None:
                clauses.append("a." + field + "=?" + (" COLLATE NOCASE" if field == "gene_symbol" else ""))
                values.append(value)
        if hgvs is not None:
            clauses.append("a.classification_id IN (SELECT classification_id FROM hgvs WHERE expression=?)")
            values.append(hgvs)
        if not include_retracted:
            # Unknown state is retained, with null exposed; it is not 'false'.
            clauses.append("(a.retracted IS NULL OR a.retracted=0)")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self.connection.execute("SELECT a.* FROM assertions a" + where +
                                       " ORDER BY a.classification_id LIMIT ? OFFSET ?", values + [limit, offset])
        return self._records(rows)

    def assertions_by_ids(self, identifiers):
        """Fetch only selected UUIDs, sharing the existing batch child queries."""
        identifiers = list(dict.fromkeys(identifiers))
        results = []
        for start in range(0, len(identifiers), 500):
            chunk = identifiers[start:start + 500]
            marks = ",".join("?" for _ in chunk)
            rows = self.connection.execute("SELECT * FROM assertions WHERE classification_id IN (" + marks +
                                           ") ORDER BY classification_id", chunk)
            results.extend(self._records(rows))
        return results

    def _records(self, rows):
        results = [self._decode(row) for row in rows]
        indexed = {item["classification_id"]: item for item in results}
        identifiers = list(indexed)
        for start in range(0, len(identifiers), 500):
            chunk = identifiers[start:start + 500]
            marks = ",".join("?" for _ in chunk)
            for row in self.connection.execute("SELECT * FROM criteria WHERE classification_id IN (" + marks +
                                                ") ORDER BY classification_id,status,ordinal", chunk):
                indexed[row["classification_id"]]["criteria"].append(
                    {key: row[key] for key in ("code", "status", "ordinal")})
            for row in self.connection.execute("SELECT * FROM hgvs WHERE classification_id IN (" + marks +
                                                ") ORDER BY classification_id,expression", chunk):
                indexed[row["classification_id"]]["hgvs"].append(row["expression"])
        return results

    def _decode(self, row):
        result = dict(row)
        for field, target in (("pubmed_json", "pubmed_articles"), ("original_json", "original"),
                              ("versions_json", "available_versions"), ("summary_metadata_json", "summary_metadata")):
            value = result.pop(field)
            result[target] = json.loads(value) if value is not None else None
        result["retracted"] = bool(result["retracted"]) if result["retracted"] is not None else None
        result["official_url"] = classification_url(result["classification_id"])
        result["version_availability"] = "AVAILABLE" if result["classification_version"] else "NOT_IN_SELECTED_EXPORTS"
        result["snapshot_id"] = self.release()["snapshot_id"]
        result.update(criteria=[], hgvs=[])
        return result

    def lookup_genomic(self, assembly, chromosome, position, reference, alternate):
        """Exact primary nuclear SNV HGVS only; no HGVS rewriting or liftover."""
        try:
            build = _assembly(assembly)
            name = _chromosome(chromosome)
            accessions = {k: v for k, v in ASSEMBLY_ACCESSIONS[build].items() if k != "MT"}
            accession = accessions.get(name) or next((v for v in accessions.values() if v == name), None)
            if (accession is None or isinstance(position, bool) or not re.fullmatch(r"[1-9][0-9]*", str(position))
                    or not isinstance(reference, str) or not isinstance(alternate, str)
                    or not re.fullmatch("[ACGT]", reference.upper()) or not re.fullmatch("[ACGT]", alternate.upper())
                    or reference.upper() == alternate.upper()):
                raise ValueError("Exact primary nuclear SNV coordinates are required")
            expression = "{}:g.{}{}>{}".format(accession, position, reference.upper(), alternate.upper())
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            return dict(status="UNSUPPORTED", reason=str(exc), matches=[])
        matches = self.query(hgvs=expression, limit=10000)
        return dict(status="FOUND" if matches else "NOT_FOUND", matches=matches,
                    match_method="EXACT_VERSIONED_GENOMIC_HGVS", reference_status="UNVERIFIED",
                    snapshot_id=self.release()["snapshot_id"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("export")
    build.add_argument("--summary")
    download = sub.add_parser("download-build")
    download.add_argument("directory")
    download.add_argument("--tsv-only", action="store_true")
    sub.add_parser("info")
    sub.add_parser("rollback")
    sub.add_parser("cleanup")
    query = sub.add_parser("query")
    for field in ("classification-id", "caid", "variation-id", "hgvs", "gene", "disease-id", "expert-panel"):
        query.add_argument("--" + field)
    query.add_argument("--limit", type=int, default=100)
    query.add_argument("--offset", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = build_database(args.export, args.database, summary=args.summary)
        elif args.command == "download-build":
            sources = download_sources(args.directory, with_summary=not args.tsv_only)
            result = build_database(Path(args.directory) / "erepo.tsv", args.database,
                                    summary=Path(args.directory) / "erepo-summary.json" if not args.tsv_only else None,
                                    sources=sources)
        elif args.command == "info":
            result = installation_status(args.database)
        elif args.command == "rollback":
            result = rollback(args.database)
        elif args.command == "cleanup":
            result = cleanup_snapshots(args.database)
        else:
            with ClinGenVCEPLocal(args.database) as reader:
                result = reader.query(**{key: value for key, value in vars(args).items() if key not in ("command", "database")})
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, sqlite3.Error, csv.Error, ClinGenVCEPLocalError, snapshots.ClinVarLocalError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
