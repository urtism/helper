"""Indexed classification heads and append-only revisions in the run database."""
import json
import sqlite3
from datetime import datetime, timezone

from helper_next.core.acmg_digest import digest
from helper_next.core.acmg_pvs1_store import path, MAX_SNAPSHOT_BYTES


def variant_key(identity):
    return digest({key: identity[key] for key in ("sample", "assembly", "chromosome", "position", "reference", "alternate")})["value"]


def _decode(row):
    if row is None:
        return None
    value = dict(row)
    value["identity"] = json.loads(value.pop("identity_json"))
    if "payload_json" in value:
        value["assessment"] = json.loads(value.pop("payload_json"))
    value.pop("identity_key", None)
    value.pop("content_hash", None)
    return value


def _exists(db):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='classification_heads'").fetchone())


def latest(run_dir, identity):
    database = path(run_dir)
    if not database.is_file():
        return None
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        if not _exists(db):
            return None
        return _decode(db.execute("SELECT r.* FROM classification_heads h JOIN classification_revisions r "
                                  "ON r.identity_key=h.identity_key AND r.revision=h.revision WHERE h.identity_key=?",
                                  (digest(identity)["value"],)).fetchone())


def summaries(run_dir, identity):
    return batch_summaries(run_dir, [identity]).get(variant_key(identity), [])


def batch_summaries(run_dir, identities):
    """Read current heads and compact applied criteria in bounded indexed batches."""
    database = path(run_dir)
    if not database.is_file():
        return {}
    keys = list(dict.fromkeys(variant_key(identity) for identity in identities))
    result = {}
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        if not _exists(db):
            return {}
        for start in range(0, len(keys), 400):
            batch = keys[start:start + 400]
            placeholders = ",".join("?" for _ in batch)
            rows = db.execute("SELECT h.variant_key,r.identity_json,h.revision,h.classification,h.points,h.requires_review,h.saved_at, "
                              "json_extract(r.payload_json,'$.criteria') AS criteria_json "
                              "FROM classification_heads h JOIN classification_revisions r "
                              "ON r.identity_key=h.identity_key AND r.revision=h.revision "
                              f"WHERE h.variant_key IN ({placeholders})", batch).fetchall()
            for row in rows:
                record = _decode(row)
                record["applied_criteria"] = [
                    {"code": criterion["code"], "strength": criterion["strength"]}
                    for criterion in json.loads(record.pop("criteria_json") or "[]")]
                result.setdefault(record.pop("variant_key"), []).append(record)
    return result


def save(run_dir, identity, signature, assessment, note="", expected_revision=0):
    if not isinstance(note, str) or len(note) > 1000 or type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("Nota o revisione della classificazione non valida")
    payload = json.dumps(assessment, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(payload.encode()) > MAX_SNAPSHOT_BYTES:
        raise ValueError("Classificazione troppo grande")
    key = digest(identity)["value"]
    content = digest([signature, assessment, note.strip()])["value"]
    database = path(run_dir)
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database, timeout=5) as db:
        db.row_factory = sqlite3.Row
        db.executescript("CREATE TABLE IF NOT EXISTS classification_revisions ("
                         "identity_key TEXT NOT NULL,revision INTEGER NOT NULL,identity_json TEXT NOT NULL,"
                         "signature TEXT NOT NULL,payload_json TEXT NOT NULL,note TEXT NOT NULL,saved_at TEXT NOT NULL,"
                         "content_hash TEXT NOT NULL,PRIMARY KEY(identity_key,revision));"
                         "CREATE TABLE IF NOT EXISTS classification_heads (identity_key TEXT PRIMARY KEY,variant_key TEXT NOT NULL,"
                         "revision INTEGER NOT NULL,classification TEXT NOT NULL,points INTEGER NOT NULL,requires_review INTEGER NOT NULL,saved_at TEXT NOT NULL);"
                         "CREATE INDEX IF NOT EXISTS classification_variant ON classification_heads(variant_key);")
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT r.* FROM classification_heads h JOIN classification_revisions r "
                              "ON r.identity_key=h.identity_key AND r.revision=h.revision WHERE h.identity_key=?", (key,)).fetchone()
        if previous and previous["content_hash"] == content:
            return _decode(previous)
        if (previous["revision"] if previous else 0) != expected_revision:
            raise ValueError("Classificazione aggiornata da un'altra scheda: riaprila prima di salvare")
        revision = (previous["revision"] if previous else 0) + 1
        now = datetime.now(timezone.utc).isoformat()
        db.execute("INSERT INTO classification_revisions VALUES (?,?,?,?,?,?,?,?)", (
            key, revision, json.dumps(identity, sort_keys=True), signature, payload, note.strip(), now, content))
        db.execute("INSERT INTO classification_heads VALUES (?,?,?,?,?,?,?) ON CONFLICT(identity_key) DO UPDATE SET "
                   "revision=excluded.revision,classification=excluded.classification,points=excluded.points,"
                   "requires_review=excluded.requires_review,saved_at=excluded.saved_at", (
                       key, variant_key(identity), revision, assessment["classification"], assessment["total_points"], int(assessment["requires_review"]), now))
        return _decode(db.execute("SELECT * FROM classification_revisions WHERE identity_key=? AND revision=?", (key, revision)).fetchone())
