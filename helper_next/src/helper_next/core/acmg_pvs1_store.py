"""Small, explicit PVS1 saves, independent of rebuildable variant indexes.

No reference fetch, sequence hashing or interpretation occurs in this module.
Only server-produced compact summaries enter the bounded pending-save cache.
"""
import copy
import json
import sqlite3
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from helper_next.core.acmg_digest import digest


MAX_SNAPSHOT_BYTES = 64 * 1024
MAX_PENDING = 128
PENDING_TTL = 1800
_pending = OrderedDict()
_lock = threading.Lock()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def path(run_dir):
    return Path(run_dir) / "results" / "INTERPRETATIONS" / "interpretations.sqlite"


def file_states(paths):
    result = {}
    for filename in sorted(set(paths)):
        try:
            stat = Path(filename).stat()
            result[filename] = [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]
        except OSError:
            result[filename] = None
    return result


def compact_snapshot(response, annotation=None):
    """Keep outcome, molecular facts and citations, never transcript sequences."""
    sample = response["input"]
    result = response["result"]
    report = response.get("mechanism_assessment") or {}
    row = next((r for r in (response.get("molecular_impact") or {}).get("transcripts", []) if r.get("selected")), {})
    product = (sample.get("molecular_effect") or {}).get("products", [])
    product = product[0] if len(product) == 1 else {}
    scenarios = (row.get("splice_analysis") or {}).get("scenarios", [])
    scenario = scenarios[0] if len(scenarios) == 1 else {}
    references = []
    evidence = {e["evidence_id"]: e for e in (*report.get("supporting_evidence", []), *report.get("conflicting_evidence", []))}
    for item in evidence.values():
        raw = item.get("raw_assertion") or {}
        references.append({**{key: item.get(key) for key in (
            "source", "source_record_id", "source_record_ref", "source_record_hash", "source_record_version",
            "source_updated_at", "source_classification", "original_mechanism")},
            "url": raw.get("record_url") or raw.get("report_url") or raw.get("public_report_url") or raw.get("source_url"),
            "hi_score": raw.get("hi_score"), "pli": raw.get("pli")})
    provenance = row.get("provenance") or {}
    files = [unquote(urlparse(url).path) for url in (provenance.get("source_urls") or {}).values()
             if isinstance(url, str) and url.startswith("file://")]
    snapshot = {
        "schema_version": 1,
        "transcript_variant": (annotation or {}).get("hgvsc"),
        "result": {key: result.get(key) for key in (
            "status", "reason", "calculated_strength", "applied_strength", "requires_review", "missing_data",
            "warnings", "ruleset_id", "ruleset_version")},
        "strength_override": response.get("strength_override"),
        "mechanism": {key: sample["disease_context"].get(key) for key in ("molecular_mechanism", "confidence", "mechanism_scope")},
        "molecular": {**{key: row.get(key) for key in (
            "consequence", "reference_protein_length", "predicted_protein_length", "cds_length_nt", "nmd_predicted", "nmd_distance_nt")},
            "event": product.get("event_type"), "basis": product.get("basis"),
            "exons": product.get("involved_exons"), "frame": product.get("frame_effect"), "ptc": product.get("ptc_start"),
            "cds_removed_nt": scenario.get("coding_deleted_nt", row.get("physical_deleted_nt"))},
        "trace": [{key: step.get(key) for key in ("id", "status", "value", "threshold", "reason", "rule")}
                  for step in map(json.loads, result.get("decision_trace", []))],
        "sources": references,
        "provenance": {key: provenance.get(key) for key in ("annotation_release", "artifact_digest", "reference_origin", "source_urls")},
        "mechanism_snapshot": report.get("snapshot_id"),
        "reference_files": file_states(files),
    }
    if len(_json(snapshot).encode()) > MAX_SNAPSHOT_BYTES:
        raise ValueError("Riepilogo PVS1 troppo grande per il salvataggio compatto")
    return snapshot


def remember(scope, selection, identity, signature, snapshot):
    now = time.monotonic()
    token = uuid.uuid4().hex
    pending = dict(scope=str(Path(scope).resolve()), selection=selection, identity=identity,
                   signature=signature, snapshot=snapshot)
    with _lock:
        expired = [key for key, (created, _) in _pending.items() if now - created >= PENDING_TTL]
        for key in expired:
            del _pending[key]
        while len(_pending) >= MAX_PENDING:
            _pending.popitem(last=False)
        _pending[token] = (now, copy.deepcopy(pending))
    return token


def pending(token, scope):
    with _lock:
        entry = _pending.get(token)
        if not entry or time.monotonic() - entry[0] >= PENDING_TTL:
            _pending.pop(token, None)
            raise ValueError("Valutazione scaduta: premi Valuta PVS1 prima di salvare")
        value = entry[1]
        if value["scope"] != str(Path(scope).resolve()):
            raise ValueError("La valutazione non appartiene alla run selezionata")
        return copy.deepcopy(value)


def _record(row):
    if row is None:
        return None
    result = dict(row)
    result.pop("identity_key", None)
    result.pop("content_hash", None)
    result["identity"] = json.loads(result.pop("identity_json"))
    result["snapshot"] = json.loads(result.pop("snapshot_json"))
    return result


def history(run_dir, identity, before=None, limit=20):
    database = path(run_dir)
    if not database.is_file():
        return []
    limit = max(1, min(int(limit), 20))
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pvs1_evaluations'").fetchone():
            return []
        rows = db.execute("SELECT * FROM pvs1_evaluations WHERE identity_key = ? AND revision < ? "
                          "ORDER BY revision DESC LIMIT ?", (digest(identity)["value"], before or 9223372036854775807, limit)).fetchall()
    return [_record(row) for row in rows]


def latest(run_dir, identity):
    rows = history(run_dir, identity, limit=1)
    return rows[0] if rows else None


def save(run_dir, identity, signature, snapshot, note=""):
    if not isinstance(note, str) or len(note) > 1000:
        raise ValueError("La nota deve contenere al massimo 1000 caratteri")
    payload = _json(snapshot)
    if len(payload.encode()) > MAX_SNAPSHOT_BYTES:
        raise ValueError("Riepilogo PVS1 troppo grande")
    note = note.strip()
    key = digest(identity)["value"]
    content = digest([signature, snapshot, note])["value"]
    database = path(run_dir)
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database, timeout=5) as db:
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE IF NOT EXISTS pvs1_evaluations ("
                   "identity_key TEXT NOT NULL, revision INTEGER NOT NULL, identity_json TEXT NOT NULL, "
                   "signature TEXT NOT NULL, snapshot_json TEXT NOT NULL, note TEXT NOT NULL, "
                   "saved_at TEXT NOT NULL, content_hash TEXT NOT NULL, PRIMARY KEY(identity_key, revision))")
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT * FROM pvs1_evaluations WHERE identity_key = ? ORDER BY revision DESC LIMIT 1", (key,)).fetchone()
        if previous and previous["content_hash"] == content:
            return _record(previous)
        revision = previous["revision"] + 1 if previous else 1
        db.execute("INSERT INTO pvs1_evaluations VALUES (?,?,?,?,?,?,?,?)", (
            key, revision, _json(identity), signature, payload, note, datetime.now(timezone.utc).isoformat(), content))
        return _record(db.execute("SELECT * FROM pvs1_evaluations WHERE identity_key = ? AND revision = ?", (key, revision)).fetchone())


def needs_review(record, signature):
    previous = record["snapshot"].get("reference_files", {})
    return record["signature"] != signature or file_states(previous) != previous
