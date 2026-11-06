"""Manual/weekly ClinVar checksum checks and their administrative receipt.

The small receipt is separate from immutable biological snapshots. flock also
deduplicates requests across local API workers; no scheduler is involved.
"""
import fcntl
import asyncio
import hashlib
import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

from helper_variants import clinvar_local


def _now():
    return datetime.now(timezone.utc).isoformat()


def _paths(database=None):
    target = Path(database or clinvar_local.database_path()).expanduser().absolute()
    base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    directory = Path(os.environ.get("HELPER_DATA_SOURCES_STATE_DIR", str(base / "helper_next/data_sources"))).expanduser()
    key = hashlib.sha256(str(target).encode()).hexdigest()
    return target, directory / (key + ".json"), directory / (key + ".lock")


def _load(path):
    if not path.is_file():
        return dict(status="idle", last_checked=None, update_available=None, error=None)
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or value.get("status") not in ("idle", "running", "complete", "error"):
        raise ValueError("Invalid ClinVar check receipt")
    return value


def _save(path, value):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=str(path.parent), delete=False) as stream:
            temporary = stream.name
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, str(path))
        temporary = None
        clinvar_local._fsync_directory(path.parent)
    finally:
        if temporary is not None:
            os.unlink(temporary)


def edit_state(database, change):
    """Short read/modify/write transaction; preserve independent operation fields."""
    _, path, _ = _paths(database)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.with_suffix(".state.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = _load(path)
        change(state)
        _save(path, state)
        return state


def lock_active(path):
    if path.is_file():
        with path.open("rb") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
    return False


def update_identity(files):
    """A checksum-set identity, not a common scientific release."""
    checksums = {name: files[name]["remote_md5"] for name in clinvar_local.FILES}
    return "ncbi-md5:" + hashlib.sha256(json.dumps(checksums, sort_keys=True).encode()).hexdigest()


def check_status(database=None, snapshot_id=None):
    """Read the last result; interrupted checks never remain apparently active."""
    _, path, lock_path = _paths(database)
    try:
        state = _load(path)
        if state["status"] == "running":
            if not lock_active(lock_path):
                state.update(status="error", update_available=None, error="Previous check was interrupted; retry manually.")
        for field in ("update", "postpone", "last_successful_update"):
            state.pop(field, None)
        if state.get("status") == "complete" and state.get("files"):
            state["update_id"] = update_identity(state["files"])
        state["matches_current"] = bool(snapshot_id and state.get("snapshot_id") == snapshot_id)
        if not state["matches_current"]:
            state["update_available"] = None
        return state
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return dict(status="error", last_checked=None, update_available=None, error=str(exc), matches_current=False)


def start_clinvar_check(database=None, *, automatic=False):
    """Return immediately, keeping one lock for the complete remote check."""
    target, path, lock_path = _paths(database)
    # Fail locally before creating a job for an absent/invalid installation.
    with clinvar_local.ClinVarLocal(target) as reader:
        snapshot = reader.release()["snapshot_id"]
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = lock_path.open("a+b")
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            if automatic:
                return None
            raw = _load(path)
            if raw.get("update", {}).get("status") == "running":
                raise clinvar_local.ClinVarLocalError("ClinVar update is busy")
            state = check_status(target, snapshot)
            # The first worker may hold the lock before publishing its receipt.
            state.update(status="running", update_available=None, error=None)
            return state
        state = dict(status="running", started_at=_now(), last_checked=None,
                     snapshot_id=snapshot, update_available=None, error=None,
                     trigger="automatic" if automatic else "manual")
        previous = check_status(target, snapshot)
        if automatic and not check_due(previous):
            lock.close()
            return None
        state["last_checked"] = previous.get("last_checked")
        edit_state(target, lambda receipt: receipt.update(state))
        thread = threading.Thread(target=_run, args=(target, path, lock, state), daemon=True,
                                  name="helper-clinvar-check")
        thread.start()
    except BaseException:
        lock.close()
        raise
    return dict(state)


def _run(target, path, lock, state):
    try:
        # Pin the actual snapshot during comparison; retention cannot retire it.
        with clinvar_local.ClinVarLocal(target) as reader:
            state["snapshot_id"] = reader.release()["snapshot_id"]
            result = clinvar_local.check_for_updates(reader.path, timeout=15)
        state.update(status="complete", files=result, update_id=update_identity(result),
                     update_available=any(value["changed"] for value in result.values()))
    except Exception as exc:
        state.update(status="error", update_available=None, error=str(exc))
    finally:
        state["last_checked"] = _now()
        try:
            edit_state(target, lambda receipt: receipt.update(state))
        finally:
            lock.close()


def check_due(state, now=None):
    if state.get("status") == "running":
        return False
    try:
        checked = datetime.fromisoformat(state["last_checked"].replace("Z", "+00:00"))
        return (now or datetime.now(timezone.utc)) - checked >= timedelta(days=7)
    except (ValueError, TypeError, KeyError):
        return True


def check_if_due(database=None):
    """Called by one local leader, never by page/list/detail requests."""
    from helper_next.core.clinvar_update import operation_status
    try:
        operation_status(database)  # Reconcile an interrupted installer first.
        _, path, _ = _paths(database)
        if _load(path).get("update", {}).get("status") == "running":
            return None
        if check_due(check_status(database)):
            return start_clinvar_check(database, automatic=True)
    except (OSError, ValueError, clinvar_local.ClinVarLocalError):
        # No installed dataset, busy external builder, or unusable state: no fetch.
        return None


async def periodic_checks():
    """One flock leader across API workers; hourly local tick, seven-day due date."""
    _, path, _ = _paths()
    leader = None
    try:
        while True:
            try:
                if leader is None:
                    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    candidate = path.with_suffix(".scheduler.lock").open("a+b")
                    try:
                        fcntl.flock(candidate, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        leader = candidate
                    except BlockingIOError:
                        candidate.close()
                if leader is not None:
                    await asyncio.get_running_loop().run_in_executor(None, check_if_due)
            except Exception:
                logging.getLogger(__name__).exception("ClinVar automatic check could not start")
            await asyncio.sleep(3600)
    finally:
        if leader is not None:
            leader.close()
