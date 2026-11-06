"""Transactional public mechanism cache. Snapshots and source revisions are append-only."""
import json
import os
import sqlite3
import time
import threading
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from helper_next.core.acmg_digest import digest
from helper_next.core.acmg_mechanism_models import GeneDiseaseMechanismResult
from helper_next.core.acmg_mechanism_normalizer import describe, NORMALIZATION_VERSION
from helper_next.core.analysis_history import now


SCHEMA_VERSION = 3
_SCHEMA = """
CREATE TABLE IF NOT EXISTS source_records (
 id TEXT PRIMARY KEY, source_name TEXT NOT NULL, source_record_id TEXT NOT NULL,
 source_record_version TEXT, dataset_version TEXT, source_url TEXT, retrieved_at TEXT NOT NULL,
 source_updated_at TEXT, content_hash TEXT NOT NULL, raw_payload TEXT NOT NULL,
 normalization_version TEXT NOT NULL, fetch_status TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS mechanism_source_lookup ON source_records(source_name,source_record_id,source_record_version);
CREATE TABLE IF NOT EXISTS mechanism_snapshots (
 snapshot_id TEXT PRIMARY KEY, gene_disease_key TEXT NOT NULL, matrix_hash TEXT NOT NULL,
 normalization_version TEXT NOT NULL, reconciliation_version TEXT NOT NULL,
 mapping_version TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS mechanism_snapshot_key ON mechanism_snapshots(gene_disease_key,created_at);
CREATE TABLE IF NOT EXISTS snapshot_records (
 snapshot_id TEXT NOT NULL REFERENCES mechanism_snapshots(snapshot_id),
 source_record_ref TEXT NOT NULL REFERENCES source_records(id), evidence_id TEXT NOT NULL,
 PRIMARY KEY(snapshot_id,evidence_id));
CREATE TABLE IF NOT EXISTS gene_disease_mechanisms (
 gene_disease_key TEXT PRIMARY KEY, gene_hgnc_id TEXT, gene_id TEXT NOT NULL, disease_id TEXT NOT NULL,
 allelic_requirement TEXT NOT NULL, snapshot_id TEXT NOT NULL REFERENCES mechanism_snapshots(snapshot_id),
 resolution_status TEXT NOT NULL, normalization_version TEXT NOT NULL, reconciliation_version TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS mechanism_gene_disease ON gene_disease_mechanisms(gene_id,disease_id,allelic_requirement);
CREATE INDEX IF NOT EXISTS mechanism_hgnc ON gene_disease_mechanisms(gene_hgnc_id);
CREATE TABLE IF NOT EXISTS mechanism_reviews (
 review_id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL REFERENCES mechanism_snapshots(snapshot_id),
 reviewer_id TEXT NOT NULL, review_status TEXT NOT NULL, reviewed_mechanism TEXT,
 review_rationale TEXT NOT NULL, reviewed_at TEXT NOT NULL, review_version TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mechanism_source_state (
 gene_id TEXT NOT NULL, source_name TEXT NOT NULL, status TEXT NOT NULL, checked_at REAL NOT NULL,
 expires_at REAL NOT NULL, local_revision TEXT NOT NULL, payload TEXT, error_code TEXT,
 PRIMARY KEY(gene_id,source_name));
CREATE INDEX IF NOT EXISTS mechanism_source_expiration ON mechanism_source_state(expires_at);
CREATE TABLE IF NOT EXISTS mechanism_refresh_leases (resource TEXT PRIMARY KEY, token TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS mechanism_changes (
 id TEXT PRIMARY KEY, gene_disease_key TEXT NOT NULL, previous_snapshot TEXT, current_snapshot TEXT NOT NULL,
 created_at TEXT NOT NULL, changes TEXT NOT NULL);
"""


_BULK_SCHEMA = """
CREATE TABLE IF NOT EXISTS mechanism_bulk_runs (
 run_id TEXT PRIMARY KEY, inventory_hash TEXT NOT NULL, status TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, options TEXT NOT NULL,
 inventory_report TEXT NOT NULL, elapsed_seconds REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS mechanism_bulk_items (
 run_id TEXT NOT NULL REFERENCES mechanism_bulk_runs(run_id), association_key TEXT NOT NULL,
 ordinal INTEGER NOT NULL, association TEXT NOT NULL, input_hash TEXT NOT NULL,
 status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, initial_snapshot_id TEXT,
 snapshot_id TEXT REFERENCES mechanism_snapshots(snapshot_id), summary TEXT, error_code TEXT,
 updated_at TEXT NOT NULL, PRIMARY KEY(run_id,association_key));
CREATE INDEX IF NOT EXISTS mechanism_bulk_order ON mechanism_bulk_items(run_id,status,ordinal);
CREATE INDEX IF NOT EXISTS mechanism_bulk_history ON mechanism_bulk_items(association_key,updated_at);
CREATE TABLE IF NOT EXISTS mechanism_bulk_publications (
 run_id TEXT NOT NULL REFERENCES mechanism_bulk_runs(run_id),
 snapshot_id TEXT NOT NULL REFERENCES mechanism_snapshots(snapshot_id),
 PRIMARY KEY(run_id,snapshot_id));
"""


def json_text(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def record_reference(packet, row):
    info = describe(packet.source, row)
    return "msr-" + digest({"source": packet.source, "record_id": info["source_record_id"],
                            "record_version": info["version"], "dataset_version": packet.dataset_version,
                            "content_hash": digest(row)["value"]})["value"]


def all_evidence(result):
    return {e.evidence_id: e for e in (*result.direct_evidence, *result.contextual_evidence, *result.contradictory_evidence)}


def matrix_digest(result):
    content = result.dict(exclude={"snapshot_id", "source_status", "provenance"})
    if "ontology_registry" not in result.provenance:
        content.pop("mapping_uncertainty", None)  # Legacy snapshot bytes/hash stay valid.
    content["versions"] = {k: result.provenance[k] for k in (
        "normalization_version", "reconciliation_version", "mapping_version", "rules")}
    content["source_availability"] = [(s.source, s.status, s.dataset_version) for s in result.source_status]
    if "ontology_registry" in result.provenance:
        content["ontology_registry"] = result.provenance["ontology_registry"]
    return digest(content)["value"]


def load_snapshot(row):
    result = GeneDiseaseMechanismResult.parse_raw(row["payload"])
    if matrix_digest(result) != row["matrix_hash"] or result.provenance.get("matrix_hash") != row["matrix_hash"]:
        raise ValueError("Mechanism snapshot integrity failure")
    return result


def compare_snapshots(left, right):
    def by_origin(result):
        return {(e.source, e.source_record_id): e for e in all_evidence(result).values()}
    before, after = by_origin(left), by_origin(right)
    def changed(keys):
        return [list(k) for k in sorted(keys)]
    def mapping(result):
        return {tuple(e[k] for k in ("left", "right", "relation")) for e in result.mapping_evidence}
    shared = before.keys() & after.keys()
    result = {"new_evidence": changed(after.keys() - before.keys()),
            "removed_evidence": changed(before.keys() - after.keys()),
            "changed_evidence": changed(k for k in shared if before[k].source_record_hash != after[k].source_record_hash),
            "mechanism_status_changed": (left.resolution_status != right.resolution_status or left.candidate_mechanisms != right.candidate_mechanisms),
            "mapping_changed": mapping(left) != mapping(right) or left.identity.disease_aliases != right.identity.disease_aliases,
            "source_version_changed": (any((before[k].source_record_version, before[k].source_dataset_version)
                                           != (after[k].source_record_version, after[k].source_dataset_version) for k in shared)
                                       or {(s.source, s.dataset_version) for s in left.source_status} != {(s.source, s.dataset_version) for s in right.source_status}),
            "normalizer_version_changed": left.provenance.get("normalization_version") != right.provenance.get("normalization_version"),
            "reconciliation_version_changed": left.provenance.get("reconciliation_version") != right.provenance.get("reconciliation_version"),
            "mapping_version_changed": left.provenance.get("mapping_version") != right.provenance.get("mapping_version")}
    result["ontology_registry_changed"] = left.provenance.get("ontology_registry") != right.provenance.get("ontology_registry")
    result["source_data_changed"] = any(result[k] for k in ("new_evidence", "removed_evidence", "changed_evidence"))
    return result


class MechanismStore:
    def __init__(self, database=None):
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
        self.path = Path(database or os.environ.get("HELPER_MECHANISM_DB", base / "helper_next/mechanisms.sqlite3"))
        self._publication_context = threading.local()

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(self.path), timeout=30)
        db.row_factory = sqlite3.Row
        self.path.chmod(0o600)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise ValueError("Mechanism cache schema is newer than this reader")
            if version == 0:
                db.executescript(_SCHEMA)
                for table in ("source_records", "mechanism_snapshots", "snapshot_records"):
                    for action in ("UPDATE", "DELETE"):
                        db.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Immutable mechanism history'); END")
                db.execute("PRAGMA user_version=1")
                db.commit()
            if version < 2:
                db.executescript(_BULK_SCHEMA)
                db.execute("PRAGMA user_version=2")
                db.commit()
            if version < 3:
                from helper_next.core.acmg_ontology import SCHEMA
                db.executescript(SCHEMA)
                for table in ("ontology_registry_releases", "ontology_mapping_records"):
                    for action in ("UPDATE", "DELETE"):
                        db.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Immutable ontology history'); END")
                db.execute("PRAGMA user_version=3")
                db.commit()
            with db:
                yield db
        finally:
            db.close()

    def current(self, key):
        with self.connect() as db:
            row = db.execute("SELECT s.payload,s.matrix_hash FROM gene_disease_mechanisms c JOIN mechanism_snapshots s ON c.snapshot_id=s.snapshot_id WHERE c.gene_disease_key=?", (key,)).fetchone()
        return load_snapshot(row) if row else None

    def snapshot(self, snapshot_id, key=None):
        with self.connect() as db:
            row = db.execute("SELECT gene_disease_key,payload,matrix_hash FROM mechanism_snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone()
        if row is None:
            raise KeyError("Mechanism snapshot not found")
        if key is not None and row["gene_disease_key"] != key:
            raise ValueError("Snapshot belongs to a different gene-disease/allelic-requirement association")
        return load_snapshot(row)

    def source_record(self, reference):
        with self.connect() as db:
            row = db.execute("SELECT * FROM source_records WHERE id=?", (reference,)).fetchone()
        if row is None:
            raise KeyError("Mechanism source record not found")
        result = dict(row)
        result["raw_payload"] = json.loads(result["raw_payload"])
        if digest(result["raw_payload"])["value"] != result["content_hash"]:
            raise ValueError("Mechanism source record integrity failure")
        return result

    def states(self, gene_id):
        with self.connect() as db:
            return {r["source_name"]: dict(r) for r in db.execute("SELECT * FROM mechanism_source_state WHERE gene_id=?", (gene_id,))}

    def save_states(self, db, gene_id, states):
        for row in states:
            db.execute("INSERT INTO mechanism_source_state VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(gene_id,source_name) DO UPDATE SET status=excluded.status,checked_at=excluded.checked_at,expires_at=excluded.expires_at,local_revision=excluded.local_revision,payload=excluded.payload,error_code=excluded.error_code",
                       (gene_id, row["source"], row["status"], row["checked_at"], row["expires_at"], row["local_revision"], row.get("payload"), row.get("error_code")))

    @contextmanager
    def refresh_lock(self, resource, timeout=60):
        token, deadline = uuid4().hex, time.monotonic() + timeout
        while True:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("DELETE FROM mechanism_refresh_leases WHERE resource=? AND expires_at<?", (resource, time.time()))
                acquired = db.execute("INSERT OR IGNORE INTO mechanism_refresh_leases VALUES(?,?,?)", (resource, token, time.time() + timeout + 60)).rowcount
            if acquired:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("Another mechanism refresh is still running")
            time.sleep(0.03)
        try:
            yield token
        finally:
            with self.connect() as db:
                db.execute("DELETE FROM mechanism_refresh_leases WHERE resource=? AND token=?", (resource, token))

    def publish(self, key, result, records, states):
        # Technical timestamps/staleness are reported but do not create new
        # scientific versions when the same acquired source content is reused.
        matrix_hash = matrix_digest(result)
        snapshot_id = "mss-" + digest({"key": key, "matrix_hash": matrix_hash})["value"]
        created = now()
        refs = {e.source_record_ref for e in all_evidence(result).values()} | {m["source_record_ref"] for m in result.mapping_evidence if m.get("source_record_ref")}
        provenance = dict(result.provenance, matrix_hash=matrix_hash, created_at=created,
                          source_record_refs=sorted(refs),
                          source_record_hashes={ref: digest(row)["value"] for _, row, ref in records if ref in refs})
        saved = result.copy(update={"snapshot_id": snapshot_id, "provenance": provenance})
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT s.payload FROM gene_disease_mechanisms c JOIN mechanism_snapshots s ON c.snapshot_id=s.snapshot_id WHERE c.gene_disease_key=?", (key,)).fetchone()
            self.save_states(db, result.identity.gene_id, states)
            pertinent = set(provenance["source_record_refs"])
            from helper_next.core.acmg_ontology import save_records
            save_records(db, [m for m in result.mapping_evidence if m.get("mapping_id")])
            for packet, row, ref in records:
                if ref not in pertinent:
                    continue
                info = describe(packet.source, row)
                db.execute("INSERT OR IGNORE INTO source_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                           (ref, packet.source, info["source_record_id"], info["version"], packet.dataset_version,
                            info["url"] or packet.source_url, packet.retrieved_at, packet.source_updated_at,
                            digest(row)["value"], json_text(row), NORMALIZATION_VERSION, packet.status))
            inserted = db.execute("INSERT OR IGNORE INTO mechanism_snapshots VALUES(?,?,?,?,?,?,?,?)",
                       (snapshot_id, key, matrix_hash, result.provenance["normalization_version"],
                        result.provenance["reconciliation_version"], result.provenance["mapping_version"], created, json_text(saved.dict()))).rowcount
            bulk_run = getattr(self._publication_context, "run_id", None)
            if inserted and bulk_run:
                db.execute("INSERT INTO mechanism_bulk_publications VALUES(?,?)", (bulk_run, snapshot_id))
            for e in all_evidence(result).values():
                db.execute("INSERT OR IGNORE INTO snapshot_records VALUES(?,?,?)", (snapshot_id, e.source_record_ref, e.evidence_id))
            for m in result.mapping_evidence:
                if m.get("source_record_ref"):
                    db.execute("INSERT OR IGNORE INTO snapshot_records VALUES(?,?,?)", (snapshot_id, m["source_record_ref"], "mapping-" + m["source_record_ref"]))
            db.execute("INSERT INTO gene_disease_mechanisms VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(gene_disease_key) DO UPDATE SET snapshot_id=excluded.snapshot_id,resolution_status=excluded.resolution_status,normalization_version=excluded.normalization_version,reconciliation_version=excluded.reconciliation_version,updated_at=excluded.updated_at",
                       (key, result.identity.gene_hgnc_id, result.identity.gene_id, result.identity.disease_id,
                        result.identity.allelic_requirement, snapshot_id, result.resolution_status,
                        result.provenance["normalization_version"], result.provenance["reconciliation_version"], created, created))
            if previous and GeneDiseaseMechanismResult.parse_raw(previous[0]).snapshot_id != snapshot_id:
                before = GeneDiseaseMechanismResult.parse_raw(previous[0])
                db.execute("INSERT INTO mechanism_changes VALUES(?,?,?,?,?,?)", (uuid4().hex, key, before.snapshot_id, snapshot_id, created, json_text(compare_snapshots(before, saved))))
        return self.snapshot(snapshot_id, key)

    @contextmanager
    def bulk_publications(self, run_id):
        previous = getattr(self._publication_context, "run_id", None)
        self._publication_context.run_id = run_id
        try:
            yield
        finally:
            self._publication_context.run_id = previous

    @contextmanager
    def readonly(self):
        if not self.path.is_file():
            yield None
            return
        db = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    def statistics(self):
        result = {"database": str(self.path), "exists": self.path.is_file(), "matrices": 0, "snapshots": 0, "source_records": 0}
        with self.readonly() as db:
            if db is not None:
                for field, table in (("matrices", "gene_disease_mechanisms"), ("snapshots", "mechanism_snapshots"), ("source_records", "source_records")):
                    result[field] = db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
        return result

    def peek(self, key):
        """Read without creating/migrating a database (dry-run and bulk planning)."""
        with self.readonly() as db:
            row = db.execute("SELECT s.payload,s.matrix_hash FROM gene_disease_mechanisms c JOIN mechanism_snapshots s ON c.snapshot_id=s.snapshot_id WHERE c.gene_disease_key=?", (key,)).fetchone() if db else None
        return load_snapshot(row) if row else None

    def peek_states(self, gene_id):
        with self.readonly() as db:
            return {r["source_name"]: dict(r) for r in db.execute("SELECT * FROM mechanism_source_state WHERE gene_id=?", (gene_id,))} if db else {}

    def bulk_run(self, run_id=None):
        with self.readonly() as db:
            if db is None or not db.execute("SELECT 1 FROM sqlite_master WHERE name='mechanism_bulk_runs'").fetchone():
                return None
            row = db.execute("SELECT * FROM mechanism_bulk_runs WHERE run_id=?", (run_id,)).fetchone() if run_id else db.execute(
                "SELECT * FROM mechanism_bulk_runs ORDER BY created_at DESC,rowid DESC LIMIT 1").fetchone()
        if not row:
            return None
        result = dict(row)
        result["options"] = json.loads(result["options"])
        result["inventory_report"] = json.loads(result["inventory_report"])
        return result

    def create_bulk_run(self, inventory_hash, report, associations, options):
        run_id, stamp = uuid4().hex, now()
        with self.connect() as db:
            db.execute("INSERT INTO mechanism_bulk_runs VALUES(?,?,?,?,?,?,?,0)",
                       (run_id, inventory_hash, "RUNNING", stamp, stamp, json_text(options), json_text(report)))
            for ordinal, association in enumerate(associations):
                key = association["key"]
                existing = db.execute("SELECT snapshot_id FROM gene_disease_mechanisms WHERE gene_disease_key=?", (key,)).fetchone()
                db.execute("INSERT INTO mechanism_bulk_items VALUES(?,?,?,?,?,'PENDING',0,?,NULL,NULL,NULL,?)",
                           (run_id, key, ordinal, json_text(association), association["input_hash"], existing[0] if existing else None, stamp))
        return run_id

    def bulk_items(self, run_id):
        with self.readonly() as db:
            rows = db.execute("SELECT * FROM mechanism_bulk_items WHERE run_id=? ORDER BY ordinal", (run_id,)).fetchall() if db else []
        return [dict(r, association=json.loads(r["association"]), summary=json.loads(r["summary"]) if r["summary"] else None) for r in rows]

    def bulk_baseline(self, key):
        with self.readonly() as db:
            if db is None or not db.execute("SELECT 1 FROM sqlite_master WHERE name='mechanism_bulk_items'").fetchone():
                return None
            row = db.execute("SELECT input_hash,snapshot_id FROM mechanism_bulk_items WHERE association_key=? AND status='SUCCESS' ORDER BY updated_at DESC,rowid DESC LIMIT 1", (key,)).fetchone()
        return dict(row) if row else None

    def begin_bulk_item(self, run_id, key):
        with self.connect() as db:
            db.execute("UPDATE mechanism_bulk_items SET status='RUNNING',attempts=attempts+1,updated_at=? WHERE run_id=? AND association_key=?", (now(), run_id, key))

    def finish_bulk_item(self, run_id, key, summary, error_code=None):
        with self.connect() as db:
            db.execute("UPDATE mechanism_bulk_items SET status=?,snapshot_id=?,summary=?,error_code=?,updated_at=? WHERE run_id=? AND association_key=?",
                       ("ERROR" if error_code else "SUCCESS", summary.get("snapshot_id"), json_text(summary), error_code, now(), run_id, key))

    def finish_bulk_run(self, run_id, status, elapsed):
        with self.connect() as db:
            db.execute("UPDATE mechanism_bulk_runs SET status=?,updated_at=?,elapsed_seconds=elapsed_seconds+? WHERE run_id=?", (status, now(), elapsed, run_id))

    def bulk_snapshot_count(self, run_id):
        with self.readonly() as db:
            return db.execute("SELECT COUNT(*) FROM mechanism_bulk_publications WHERE run_id=?", (run_id,)).fetchone()[0] if db else 0

    def renew_lease(self, resource, token, lifetime):
        with self.connect() as db:
            changed = db.execute("UPDATE mechanism_refresh_leases SET expires_at=? WHERE resource=? AND token=?", (time.time() + lifetime, resource, token)).rowcount
            if not changed:
                raise TimeoutError("Bulk population lease is no longer held")
