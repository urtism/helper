"""Append-only local workspaces, interpretations and human reviews."""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from helper_next.core.analysis_history import now
from helper_next.core.acmg_client import digest


@contextmanager
def connect():
    base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    path = Path(os.environ.get("HELPER_ACMG_DB", str(base / "helper_next/acmg.sqlite3")))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=30)
    path.chmod(0o600)
    db.execute("CREATE TABLE IF NOT EXISTS entries (id TEXT PRIMARY KEY, workspace TEXT, kind TEXT, created TEXT, document TEXT)")
    try:
        with db:
            yield db
    finally:
        db.close()


def save(kind, document, workspace=None):
    identifier = uuid4().hex
    entry = {"id": identifier, "workspace_id": workspace or identifier, "kind": kind,
             "created_at": now(), "fingerprint": digest(document), "document": document}
    with connect() as db:
        db.execute("INSERT INTO entries VALUES (?, ?, ?, ?, ?)",
                   (identifier, entry["workspace_id"], kind, entry["created_at"], json.dumps(entry, allow_nan=False)))
    return entry


def get(identifier):
    with connect() as db:
        row = db.execute("SELECT document FROM entries WHERE id = ?", (identifier,)).fetchone()
    return json.loads(row[0]) if row else None


def history(workspace):
    with connect() as db:
        return [json.loads(row[0]) for row in db.execute(
            "SELECT document FROM entries WHERE workspace = ? ORDER BY created, id", (workspace,))]


def workspaces(source_id, sample_id, variant_id):
    with connect() as db:
        return [json.loads(row[0]) for row in db.execute(
            "SELECT document FROM entries WHERE kind = 'workspace' "
            "AND json_extract(document, '$.document.locator.source_id') = ? "
            "AND json_extract(document, '$.document.locator.sample_id') = ? "
            "AND json_extract(document, '$.document.locator.variant_id') = ? ORDER BY created DESC",
            (source_id, sample_id, variant_id))]
