"""Durable run metadata. Never reconstruct history from working directories."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


def database_path():
    base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    return Path(os.environ.get("HELPER_ANALYSIS_HISTORY_DB", str(base / "helper_next/analysis_history.sqlite3"))).expanduser()


@contextmanager
def connect():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=30)
    db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created TEXT NOT NULL, document TEXT NOT NULL)")
    try:
        with db:
            yield db
    finally:
        db.close()


def create(document):
    document = dict(document, id=uuid4().hex, created_at=now(), updated_at=now())
    with connect() as db:
        db.execute("INSERT INTO runs VALUES (?, ?, ?)", (document["id"], document["created_at"], json.dumps(document)))
    return document


def get(identifier):
    with connect() as db:
        row = db.execute("SELECT document FROM runs WHERE id = ?", (identifier,)).fetchone()
    return json.loads(row[0]) if row else None


def list_runs():
    with connect() as db:
        return [json.loads(row[0]) for row in db.execute("SELECT document FROM runs ORDER BY created DESC")]


def update(identifier, **changes):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT document FROM runs WHERE id = ?", (identifier,)).fetchone()
        if row:
            document = dict(json.loads(row[0]), **changes, updated_at=now())
            db.execute("UPDATE runs SET document = ? WHERE id = ?", (json.dumps(document), identifier))


def delete(identifier):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT document FROM runs WHERE id = ?", (identifier,)).fetchone()
        if not row:
            return False
        document = json.loads(row[0])
        parent_id = document.get("parent_id")
        children = db.execute("SELECT id, document FROM runs").fetchall()
        for child_id, child_json in children:
            child = json.loads(child_json)
            if child.get("parent_id") != identifier:
                continue
            child["parent_id"] = parent_id
            child["updated_at"] = now()
            db.execute("UPDATE runs SET document = ? WHERE id = ?", (json.dumps(child), child_id))
        db.execute("DELETE FROM runs WHERE id = ?", (identifier,))
    return True
