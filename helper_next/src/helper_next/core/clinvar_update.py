"""A detached, explicitly approved ClinVar installation using the existing builder."""
import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid

from helper_next.core import data_source_checks as checks
from helper_variants import clinvar_local as local


class UpdateConflict(local.ClinVarLocalError):
    pass


def _selection(state, target, snapshot_id, update_id, require_managed=True):
    try:
        selected_id = checks.update_identity(state.get("files", {}))
    except (ValueError, KeyError, TypeError):
        selected_id = None
    if (state.get("status") != "complete" or state.get("update_available") is not True
            or state.get("snapshot_id") != snapshot_id or selected_id != update_id):
        raise UpdateConflict("The selected check is no longer valid; check again and approve the current files")
    if require_managed:
        installation = local.installation_status(target)
        if installation["status"] != "installed" or not installation["managed"]:
            raise UpdateConflict("A valid managed CURRENT/BACKUP installation is required")
        if installation["builder_busy"]:
            raise UpdateConflict("The ClinVar builder is already busy")
    with local.ClinVarLocal(target) as reader:
        if reader.release()["snapshot_id"] != snapshot_id:
            raise UpdateConflict("CURRENT changed; check again before updating")
    return {name: state["files"][name]["remote_md5"] for name in local.FILES}


def postpone(snapshot_id, update_id, database=None):
    target, _, _ = checks._paths(database)
    def change(state):
        if state.get("update", {}).get("status") == "running":
            raise UpdateConflict("ClinVar update is busy")
        _selection(state, target, snapshot_id, update_id, require_managed=False)
        now = datetime.now(timezone.utc)
        state["postpone"] = dict(update_id=update_id, postponed_at=now.isoformat(),
                                 remind_after=(now + timedelta(days=7)).isoformat())
    return checks.edit_state(target, change)["postpone"]


def postpone_status(check, database=None):
    _, path, _ = checks._paths(database)
    try:
        value = checks._load(path).get("postpone") or {}
        if not isinstance(value, dict):
            raise ValueError("Invalid postpone receipt")
    except (OSError, ValueError, TypeError) as exc:
        return dict(silenced=False, error=str(exc))
    try:
        until = datetime.fromisoformat(value["remind_after"])
        silenced = value["update_id"] == check.get("update_id") and until > datetime.now(timezone.utc)
    except (KeyError, ValueError, TypeError):
        silenced = False
    return dict(value, silenced=silenced)


def start_update(snapshot_id, update_id, *, confirmed=False, database=None):
    if confirmed is not True:
        raise UpdateConflict("Explicit confirmation is required before downloading ClinVar")
    target, path, lock_path = checks._paths(database)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = lock_path.open("a+b")
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise UpdateConflict("A ClinVar check or update is already running")
        operation = uuid.uuid4().hex
        def accept(state):
            selected = _selection(state, target, snapshot_id, update_id)
            state["update"] = dict(operation_id=operation, status="running", phase="CHECKING",
                                   approved_current=snapshot_id, update_id=update_id,
                                   checksums=selected, checked_at=state.get("last_checked"),
                                   started_at=checks._now(), error=None, progress={})
        state = checks.edit_state(target, accept)
        versions = target.parent / (target.name + ".snapshots")
        environment = os.environ.copy()
        source_root = str(Path(__file__).resolve().parents[2])
        environment["PYTHONPATH"] = os.pathsep.join(filter(None, (source_root, environment.get("PYTHONPATH"))))
        # SQLite sort/index temporary files share the filesystem included in preflight.
        environment["SQLITE_TMPDIR"] = str(versions)
        process = subprocess.Popen(
            [sys.executable, "-m", "helper_next.core.clinvar_update", "--database", str(target),
             "--operation", operation, "--lock-fd", str(lock.fileno())],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True, close_fds=True, pass_fds=(lock.fileno(),), env=environment,
        )
        def identify(receipt):
            if receipt.get("update", {}).get("operation_id") == operation:
                receipt["update"]["pid"] = process.pid
        # PID is informational; the inherited kernel lock is authoritative.
        try:
            checks.edit_state(target, identify)
        except OSError:
            pass
        threading.Thread(target=process.wait, daemon=True, name="helper-clinvar-reap").start()
        return dict(state["update"], pid=process.pid)
    except BaseException as exc:
        if "operation" in locals():
            def failed(state):
                value = state.get("update", {})
                if value.get("operation_id") == operation:
                    value.update(status="failed", phase="FAILED", error=str(exc), finished_at=checks._now())
            checks.edit_state(target, failed)
        raise
    finally:
        # The child keeps the same open-file-description lock until completion.
        lock.close()


def _filesystem(path):
    path = Path(path)
    while not path.exists():
        path = path.parent
    return path, path.stat().st_dev


def disk_preflight(target, download_directory):
    """Conservative free-space estimate, grouped by actual filesystem device."""
    with local.ClinVarLocal(target) as reader:
        manifest, current_size = reader.release(), reader.path.stat().st_size
    archive_sizes = {}
    for name in local.FILES:
        remote_size = None
        try:
            with local._request(local.BASE_URL + name, method="HEAD", timeout=15) as response:
                declared = response.headers.get("Content-Length")
                remote_size = int(declared) if declared is not None else None
        except (OSError, ValueError):
            pass  # Use a conservative fallback when HEAD/Content-Length is unavailable.
        known = manifest.get("sources", {}).get(name, {}).get("size_bytes") or 0
        archive_sizes[name] = max(remote_size or 0, known, current_size if not remote_size else 0)
    archives = sum(archive_sizes.values())
    database_estimate = max(current_size * 2, archives * 6)
    margin = max(256 * 1024 * 1024, current_size // 4)
    versions = target.parent / (target.name + ".snapshots")
    reservations = ((versions, database_estimate),
                    (Path(os.environ.get("SQLITE_TMPDIR", tempfile.gettempdir())), database_estimate),
                    (download_directory, archives))
    devices = {}
    for directory, size in reservations:
        existing, device = _filesystem(directory)
        entry = devices.setdefault(device, dict(path=str(existing), required_bytes=margin, free_bytes=shutil.disk_usage(existing).free))
        entry["required_bytes"] += size
    result = dict(current_bytes=current_size, archive_estimates=archive_sizes,
                  database_estimate_bytes=database_estimate, filesystems=list(devices.values()))
    insufficient = [entry for entry in devices.values() if entry["free_bytes"] < entry["required_bytes"]]
    if insufficient:
        entry = insufficient[0]
        raise local.ClinVarLocalError(
            "Insufficient disk space on {}: {:.1f} GiB free; at least {:.1f} GiB estimated for archives, staging, temporary files and margin. CURRENT/BACKUP are preserved.".format(
                entry["path"], entry["free_bytes"] / 2**30, entry["required_bytes"] / 2**30))
    return result


def _matches_installation(target, operation):
    with local.ClinVarLocal(target) as reader:
        manifest = reader.release()
        selected = {name: manifest["sources"][name]["md5"] for name in local.FILES}
        if selected == operation.get("checksums") and manifest["snapshot_id"] != operation.get("approved_current"):
            return manifest["snapshot_id"]
    return None


def _cleanup_downloads(path, operation):
    directory = operation.get("download_directory")
    if not directory:
        # A crash can occur between mkdir and recording the path. Downloads have
        # not started in that window, so remove only empty, operation-owned dirs.
        for candidate in path.parent.glob(".clinvar-update-" + operation["operation_id"] + "-*"):
            if candidate.is_dir() and not candidate.is_symlink():
                candidate.rmdir()
        return
    directory = Path(directory)
    prefix = ".clinvar-update-" + operation["operation_id"] + "-"
    if directory.parent != path.parent or not directory.name.startswith(prefix) or directory.is_symlink():
        raise local.ClinVarLocalError("Refusing to clean an unowned download directory")
    if directory.is_dir():
        deferred = local._cleanup_download_parts(directory)["deferred"]
        if deferred:
            raise local.ClinVarLocalError("Download partials are still in use")
        shutil.rmtree(str(directory))


def operation_status(database=None):
    """Reconcile crash windows using the operation lock and authoritative manifest."""
    target, path, lock_path = checks._paths(database)
    try:
        state = checks._load(path)
        operation = state.get("update") or {}
        if not isinstance(operation, dict):
            raise ValueError("Invalid installer receipt")
    except (OSError, ValueError, TypeError) as exc:
        return dict(status="failed", phase="FAILED", error=str(exc))
    if (operation.get("status") != "running" and not operation.get("recovery_pending")) or checks.lock_active(lock_path):
        return operation
    # Serialize recovery with any newly requested CHECK/UPDATE.
    with lock_path.open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return operation
        def reconcile(receipt):
            value = receipt.get("update", {})
            if value.get("status") != "running" and not value.get("recovery_pending"):
                return
            try:
                installed = _matches_installation(target, value)
                local.cleanup_snapshots(target)
                _cleanup_downloads(path, value)
                value["recovery_pending"] = False
                if installed:
                    value.update(status="completed", phase="COMPLETED", snapshot_id=installed,
                                 error=None, recovered=True, finished_at=checks._now())
                    receipt["last_successful_update"] = dict(operation_id=value["operation_id"], snapshot_id=installed,
                                                             completed_at=value["finished_at"])
                else:
                    value.update(status="failed", phase="FAILED", error="Installer interrupted; CURRENT/BACKUP preserved. Retry after checking.",
                                 finished_at=checks._now())
            except (OSError, ValueError, KeyError, local.ClinVarLocalError) as exc:
                value.update(status="failed", phase="FAILED", error="Interrupted installer; recovery requires attention: " + str(exc),
                             finished_at=checks._now(), recovery_pending=True)
        return checks.edit_state(target, reconcile).get("update", {})


def run_update(database, operation_id, lock_fd):
    """Child entry point. All downloads/builds remain in existing ClinVar functions."""
    target, path, _ = checks._paths(database)
    lock = os.fdopen(lock_fd, "rb")
    last_write, last_phase = 0, None
    def record(event, force=False):
        nonlocal last_write, last_phase
        phase = event.get("phase", "BUILDING")
        if phase == "indexing":
            phase = "BUILDING"
        now = time.monotonic()
        if not force and phase == last_phase and now - last_write < 1:
            return
        def change(state):
            operation = state.get("update", {})
            if operation.get("operation_id") != operation_id or operation.get("status") != "running":
                raise UpdateConflict("Installation approval is no longer active")
            operation.update(phase=phase, progress=event, progress_at=checks._now())
        checks.edit_state(target, change)
        last_write, last_phase = now, phase
    try:
        operation = checks._load(path)["update"]
        if operation.get("operation_id") != operation_id or operation.get("status") != "running":
            raise UpdateConflict("Installation approval is no longer active")
        versions = target.parent / (target.name + ".snapshots")
        versions.mkdir(parents=True, exist_ok=True)
        # All owned archives vanish on ordinary completion/failure. Crash recovery
        # uses the existing partial/staging cleanup (no foreign download directories).
        with tempfile.TemporaryDirectory(prefix=".clinvar-update-" + operation_id + "-", dir=str(path.parent)) as directory:
            checks.edit_state(target, lambda state: state["update"].update(download_directory=directory))
            def preflight():
                report = disk_preflight(target, Path(directory))
                record(dict(phase="CHECKING", disk=report), force=True)
            result = local.download_and_build(
                directory, target, expected_current=operation["approved_current"],
                expected_checksums=operation["checksums"], before_download=preflight, progress=record,
            )
            record(dict(phase="CLEANING"), force=True)
        def complete(state):
            value = state["update"]
            value.update(status="completed", phase="COMPLETED", snapshot_id=result["snapshot_id"],
                         finished_at=checks._now(), error=None, progress={})
            state["last_successful_update"] = dict(operation_id=operation_id, snapshot_id=result["snapshot_id"], completed_at=value["finished_at"])
        checks.edit_state(target, complete)
    except BaseException as exc:
        try:
            installed = _matches_installation(target, operation)
        except (OSError, ValueError, KeyError, local.ClinVarLocalError, UnboundLocalError):
            installed = None
        def failed(state):
            value = state.get("update", {})
            if value.get("operation_id") == operation_id:
                if installed:
                    value.update(status="completed", phase="COMPLETED", snapshot_id=installed,
                                 error=None, warning=str(exc), finished_at=checks._now(), recovery_pending=True)
                    state["last_successful_update"] = dict(operation_id=operation_id, snapshot_id=installed, completed_at=value["finished_at"])
                else:
                    value.update(status="failed", phase="FAILED", error=str(exc), finished_at=checks._now())
        checks.edit_state(target, failed)
    finally:
        lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--operation", required=True)
    parser.add_argument("--lock-fd", required=True, type=int)
    args = parser.parse_args()
    run_update(args.database, args.operation, args.lock_fd)


if __name__ == "__main__":
    main()
