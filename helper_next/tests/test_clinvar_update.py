"""CACHE-06B: offline approval, scheduling, disk checks and detached installation."""
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import threading
import time
from types import SimpleNamespace

import httpx
import pytest

from helper_next.api.app import create_app
from helper_next.core import data_source_checks as checks, clinvar_update as workflow
from helper_variants import clinvar_local as local, query
from test_clinvar_integration import install, at, component
from test_clinvar_local import inputs, summary, submission
from test_variant_query import query_store


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("HELPER_DATA_SOURCES_STATE_DIR", str(tmp_path / "state"))
    def no_network(*args, **kwargs):
        pytest.fail("Tests use local fixture URLs only")
    monkeypatch.setattr(socket, "create_connection", no_network)


def wait_for(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.02)
    pytest.fail("Timed out waiting for ClinVar operation")


def api(method, path, payload=None, **kwargs):
    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://127.0.0.1") as client:
            return await asyncio.wait_for(client.request(method, "/api/data-sources/clinvar" + path, json=payload, **kwargs), 5)
    return asyncio.run(request())


def refresh():
    checks.start_clinvar_check()
    with local.ClinVarLocal() as reader:
        snapshot = reader.release()["snapshot_id"]
    return wait_for(lambda: (lambda value: value if value["status"] != "running" else None)(checks.check_status(snapshot_id=snapshot)))


def remote_fixture(tmp_path, monkeypatch, backup=False):
    target, original = install(tmp_path, monkeypatch)
    if backup:
        paths = inputs(tmp_path / "sources", submissions=[submission(SCV="SCV000000099")])
        original = local.build_database(*paths, database=target)
    remote = tmp_path / "remote"
    remote.mkdir()
    inputs(remote, variants=[summary(ClinicalSignificance="Benign")], submissions=[submission(ClinicalSignificance="Benign")])
    for name in local.FILES:
        (remote / (name + ".md5")).write_text(hashlib.md5((remote / name).read_bytes()).hexdigest() + "  " + name)
    monkeypatch.setattr(local, "BASE_URL", remote.as_uri() + "/")
    checked = refresh()
    assert checked["status"] == "complete" and checked["update_available"] is True
    return target, original, remote, checked


def launch_fixture_worker(monkeypatch, remote, *, pause=None, low_disk=False):
    """Launch the real detached worker, replacing only remote URLs with file fixtures."""
    actual = subprocess.Popen
    marker, release = remote / "entered", remote / "continue"
    script = "from pathlib import Path\nimport time\nfrom types import SimpleNamespace\n"
    script += "from helper_variants import clinvar_local as local\nfrom helper_next.core import clinvar_update as worker\n"
    script += "local.BASE_URL = " + repr(remote.as_uri() + "/") + "\n"
    script += "worker.shutil.disk_usage = lambda p: SimpleNamespace(free=" + ("0" if low_disk else "2**50") + ")\n"
    script += "original_download = local.download_sources\n"
    script += "def download(*args, **kwargs):\n    Path(" + repr(str(remote / "downloaded")) + ").touch()\n    return original_download(*args, **kwargs)\n"
    script += "local.download_sources = download\n"
    if pause:
        method = "_select_roles" if pause == "published" else "download_sources"
        script += "original = local." + method + "\n"
        script += "def paused(*args, **kwargs):\n"
        if pause == "published":
            script += "    result = original(*args, **kwargs)\n"
        script += "    Path(" + repr(str(marker)) + ").touch()\n"
        script += "    while not Path(" + repr(str(release)) + ").exists(): time.sleep(.02)\n"
        script += "    return " + ("result" if pause == "published" else "original(*args, **kwargs)") + "\n"
        script += "local." + method + " = paused\n"
    script += "worker.main()\n"
    launched = []
    def start(args, **kwargs):
        assert kwargs["start_new_session"] is True and kwargs["pass_fds"]
        child = actual([args[0], "-c", script] + args[3:], **kwargs)
        launched.append(child)
        return child
    monkeypatch.setattr(workflow.subprocess, "Popen", start)
    return marker, release, launched


def selection(checked, confirmed=True):
    return dict(snapshot_id=checked["snapshot_id"], update_id=checked["update_id"], confirmed=confirmed)


def finished(target):
    return wait_for(lambda: (lambda state: state if state.get("status") in ("completed", "failed") else None)(workflow.operation_status(target)))


def role_bytes(target):
    return [(path.name, path.read_bytes()) for path in sorted((target.parent / (target.name + ".snapshots")).glob("*.sqlite3"))]


def test_weekly_due_boundary_and_automatic_check_never_downloads(tmp_path, monkeypatch):
    target, _, _, checked = remote_fixture(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)
    assert checks.check_due(dict(status="complete", last_checked=(now - timedelta(days=7)).isoformat()), now)
    assert not checks.check_due(dict(status="complete", last_checked=(now - timedelta(days=7) + timedelta(seconds=1)).isoformat()), now)
    assert checks.check_due(dict(status="error", last_checked="bad"), now)
    def forbidden(*args, **kwargs):
        pytest.fail("Automatic CHECK must never download full datasets")
    monkeypatch.setattr(local, "download_sources", forbidden)
    assert checks.check_if_due(target) is None
    checks.edit_state(target, lambda state: state.update(last_checked=(now - timedelta(days=8)).isoformat()))
    assert checks.check_if_due(target)["status"] == "running"
    wait_for(lambda: checks.check_status(target, checked["snapshot_id"])["status"] == "complete")
    assert checks.check_if_due(target) is None


def test_only_one_periodic_leader_and_startup_is_nonblocking(tmp_path, monkeypatch):
    calls = []
    entered, release = threading.Event(), threading.Event()
    def tick():
        calls.append(True)
        entered.set()
        release.wait(3)
    monkeypatch.setattr(checks, "check_if_due", tick)
    async def exercise():
        first, second = create_app(), create_app()
        start = time.monotonic()
        await first.router.startup()
        await second.router.startup()
        assert time.monotonic() - start < .5
        try:
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(.01)
            assert entered.is_set() and len(calls) == 1
        finally:
            release.set()
            await first.router.shutdown()
            await second.router.shutdown()
    asyncio.run(exercise())
    _, path, _ = checks._paths()
    assert not checks.lock_active(path.with_suffix(".scheduler.lock"))


def test_postpone_is_persistent_checksum_specific_and_does_not_disable_update(tmp_path, monkeypatch):
    target, _, remote, checked = remote_fixture(tmp_path, monkeypatch)
    before = role_bytes(target)
    response = api("POST", "/postpone", selection(checked, confirmed=False))
    assert response.status_code == 200
    value = response.json()
    assert datetime.fromisoformat(value["remind_after"]) - datetime.fromisoformat(value["postponed_at"]) == timedelta(days=7)
    for _ in range(2):  # New app objects, same persisted administrative receipt.
        row = api("GET", "").json()
        assert row["postpone"]["silenced"] and not row["notification"]
        assert row["can_update"] and row["update_available"]
    assert role_bytes(target) == before
    assert not (remote / "downloaded").exists()
    checks.edit_state(target, lambda state: state["postpone"].update(remind_after="2000-01-01T00:00:00+00:00"))
    assert api("GET", "").json()["notification"]
    checks.edit_state(target, lambda state: state.update(postpone=value))
    # An additional upstream file revision supersedes only the notice suppression.
    inputs(remote, submissions=[submission(SCV="SCV000000555")])
    for name in local.FILES:
        (remote / (name + ".md5")).write_text(hashlib.md5((remote / name).read_bytes()).hexdigest() + "  " + name)
    refresh()
    row = api("GET", "").json()
    assert row["notification"] and not row["postpone"]["silenced"]
    assert row["postpone"]["update_id"] == checked["update_id"]


def test_confirmation_and_stale_selection_are_rejected_before_launch(tmp_path, monkeypatch):
    target, _, _, checked = remote_fixture(tmp_path, monkeypatch)
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid approval must never launch a worker")
    monkeypatch.setattr(workflow.subprocess, "Popen", forbidden)
    assert api("POST", "/update", selection(checked, False)).status_code == 409
    invalid = dict(selection(checked), update_id="different-files")
    assert api("POST", "/update", invalid).status_code == 409
    paths = inputs(tmp_path / "sources", submissions=[submission(SCV="SCV000000123")])
    local.build_database(*paths, database=target)
    assert api("POST", "/update", selection(checked)).status_code == 409


def test_detached_update_nonblocking_reader_pinning_and_duplicate_exclusion(tmp_path, monkeypatch):
    target, old, remote, checked = remote_fixture(tmp_path, monkeypatch)
    marker, release, launched = launch_fixture_worker(monkeypatch, remote, pause="download")
    reader = local.ClinVarLocal(target)
    started = time.monotonic()
    response = api("POST", "/update", selection(checked))
    assert response.status_code == 202 and time.monotonic() - started < 2
    try:
        wait_for(marker.exists)
        assert len(launched) == 1 and response.json()["pid"] != os.getpid()
        row = api("GET", "").json()
        assert row["update"]["status"] == "running" and not row["can_update"]
        assert api("POST", "/update", selection(checked)).status_code == 409
        assert api("POST", "/postpone", selection(checked)).status_code == 409
        assert api("POST", "/check").status_code == 400
        assert api("GET", "/update/status").json()["operation_id"] == response.json()["operation_id"]
    finally:
        release.touch()
    try:
        result = finished(target)
        assert result["phase"] == "COMPLETED", result
        assert reader.release()["snapshot_id"] == old["snapshot_id"]
        assert reader.aggregate(2)[0]["classification"] == "Pathogenic"
        with local.ClinVarLocal(target) as current:
            assert current.aggregate(2)[0]["classification"] == "Benign"
        state = local.installation_status(target)
        assert state["backup"]["snapshot_id"] == old["snapshot_id"]
        assert len(role_bytes(target)) == 2
        assert not list(checks._paths(target)[1].parent.glob(".clinvar-update-*"))
        row = api("GET", "").json()
        assert row["last_successful_update"]["snapshot_id"] == result["snapshot_id"]
        assert row["update_available"] is None and not row["can_update"]
    finally:
        reader.close()


@pytest.mark.parametrize("failure", ["remote_changed", "checksum", "gzip", "space"])
def test_failed_update_preserves_both_roles_and_cleans_temporary_files(tmp_path, monkeypatch, failure):
    target, _, remote, checked = remote_fixture(tmp_path, monkeypatch, backup=True)
    if failure == "remote_changed":
        (remote / (local.FILES[0] + ".md5")).write_text("0" * 32 + "  " + local.FILES[0])
    if failure in ("checksum", "gzip"):
        (remote / local.FILES[0]).write_bytes(b"not a gzip export")
        if failure == "gzip":
            (remote / (local.FILES[0] + ".md5")).write_text(hashlib.md5(b"not a gzip export").hexdigest() + "  " + local.FILES[0])
            checked = refresh()
    before = role_bytes(target)
    launch_fixture_worker(monkeypatch, remote, low_disk=failure == "space")
    assert api("POST", "/update", selection(checked)).status_code == 202
    result = finished(target)
    assert result["phase"] == "FAILED" and result["error"]
    assert role_bytes(target) == before
    assert not list(checks._paths(target)[1].parent.glob(".clinvar-update-*"))
    assert not list(target.parent.glob("*.snapshots/.clinvar-build-*"))
    if failure in ("remote_changed", "space"):
        assert not (remote / "downloaded").exists()


def test_active_backup_blocks_publication_and_retry_keeps_two_snapshots(tmp_path, monkeypatch):
    target, _, remote, checked = remote_fixture(tmp_path, monkeypatch, backup=True)
    state = local.installation_status(target)
    before = role_bytes(target)
    launch_fixture_worker(monkeypatch, remote)
    with local.ClinVarLocal(state["backup"]["path"]):
        assert api("POST", "/update", selection(checked)).status_code == 202
        result = finished(target)
        assert result["phase"] == "FAILED" and "active readers" in result["error"]
        assert role_bytes(target) == before
    assert api("POST", "/update", selection(checked)).status_code == 202
    assert finished(target)["phase"] == "COMPLETED"
    assert len(role_bytes(target)) == 2


@pytest.mark.parametrize("pause", ["download", "published"])
def test_killed_worker_reconciles_manifest_and_existing_cleanup(tmp_path, monkeypatch, pause):
    target, old, remote, checked = remote_fixture(tmp_path, monkeypatch, backup=True)
    marker, _, launched = launch_fixture_worker(monkeypatch, remote, pause=pause)
    assert api("POST", "/update", selection(checked)).status_code == 202
    wait_for(marker.exists)
    os.kill(launched[0].pid, signal.SIGKILL)
    launched[0].wait(timeout=5)
    result = workflow.operation_status(target)
    assert result["status"] == ("completed" if pause == "published" else "failed"), result
    assert len(role_bytes(target)) == 2
    assert not list(checks._paths(target)[1].parent.glob(".clinvar-update-*"))
    current = local.installation_status(target)["manifest"]["snapshot_id"]
    assert (current != old["snapshot_id"]) == (pause == "published")


def test_disk_preflight_groups_real_filesystems_and_unknown_sizes(tmp_path, monkeypatch):
    target, _, remote, _ = remote_fixture(tmp_path, monkeypatch)
    class Head:
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *args): pass
    requests = []
    def head(url, method=None, timeout=None):
        requests.append((method, timeout))
        return Head()
    monkeypatch.setattr(local, "_request", head)
    monkeypatch.setattr(workflow.shutil, "disk_usage", lambda path: SimpleNamespace(free=2**50))
    monkeypatch.setenv("SQLITE_TMPDIR", str(target.parent))
    report = workflow.disk_preflight(target, remote)
    assert len(report["filesystems"]) == 1
    assert report["database_estimate_bytes"] >= report["current_bytes"] * 2
    assert all(size >= report["current_bytes"] for size in report["archive_estimates"].values())
    assert requests == [("HEAD", 15), ("HEAD", 15)]
    monkeypatch.setattr(workflow.shutil, "disk_usage", lambda path: SimpleNamespace(free=1))
    with pytest.raises(local.ClinVarLocalError, match="Insufficient disk space"):
        workflow.disk_preflight(target, remote)


def test_builder_exposes_real_phases_and_counters_without_global_percentage(tmp_path, monkeypatch):
    target, old, remote, checked = remote_fixture(tmp_path, monkeypatch)
    downloads = tmp_path / "download"
    events = []
    result = local.download_and_build(downloads, target, expected_current=old["snapshot_id"],
        expected_checksums={name: value["remote_md5"] for name, value in checked["files"].items()}, progress=events.append)
    assert result["snapshot_id"] != old["snapshot_id"]
    phases = {event.get("phase") for event in events}
    assert {"CHECKING", "DOWNLOADING", "VALIDATING_DOWNLOAD", "BUILDING", "VALIDATING_DATABASE", "PUBLISHING", "CLEANING"} <= phases
    assert any(event.get("bytes", 0) > 0 for event in events)
    assert any(event.get("variant_summary_rows", 0) > 0 for event in events)
    assert all("percent" not in event for event in events)


def test_supervised_snapshot_invalidates_priority_cache_without_rule_changes(tmp_path, monkeypatch):
    target, _, remote, _ = remote_fixture(tmp_path, monkeypatch)
    install(tmp_path, monkeypatch, variants=[at()])
    inputs(remote, variants=[at(ClinicalSignificance="Benign")])
    for name in local.FILES:
        (remote / (name + ".md5")).write_text(hashlib.md5((remote / name).read_bytes()).hexdigest() + "  " + name)
    checked = refresh()
    path, sample, _ = query_store(tmp_path)
    first = query.list_variants(path, sample)
    assert first["items"][0]["position"] == 5
    assert component(first["items"][0])["score"] == 20
    launch_fixture_worker(monkeypatch, remote)
    assert api("POST", "/update", selection(checked)).status_code == 202
    assert finished(target)["phase"] == "COMPLETED"
    second = query.list_variants(path, sample)
    assert second["clinvar_snapshot_id"] != first["clinvar_snapshot_id"]
    assert second["items"][-1]["position"] == 5
    assert component(second["items"][-1])["score"] == -20
    assert len([item for item in second["items"][-1]["priority"]["components"] if item["key"] == "clinvar"]) == 1


def test_launch_failure_records_error_and_releases_lock(tmp_path, monkeypatch):
    target, _, _, checked = remote_fixture(tmp_path, monkeypatch)
    before = role_bytes(target)
    def unavailable(*args, **kwargs):
        raise OSError("Could not start installer process")
    monkeypatch.setattr(workflow.subprocess, "Popen", unavailable)
    response = api("POST", "/update", selection(checked))
    assert response.status_code == 400
    result = workflow.operation_status(target)
    assert result["phase"] == "FAILED" and "start installer" in result["error"]
    assert not checks.lock_active(checks._paths(target)[2])
    assert role_bytes(target) == before


def test_administrative_receipt_corruption_does_not_hide_installed_database(tmp_path, monkeypatch):
    target, _, _, _ = remote_fixture(tmp_path, monkeypatch)
    checks._paths(target)[1].write_text("incomplete json")
    response = api("GET", "")
    assert response.status_code == 200
    row = response.json()
    assert row["installed"] and row["status"] == "installed"
    assert row["check"]["status"] == "error" and row["update"]["phase"] == "FAILED"
    assert row["update_available"] is None and not row["can_update"]


def test_current_is_rechecked_at_atomic_publication(tmp_path, monkeypatch):
    target, old, remote, checked = remote_fixture(tmp_path, monkeypatch, backup=True)
    current, backup, _ = local._roles(target)
    before = role_bytes(target)
    def progress(event):
        if event.get("phase") == "PUBLISHING":
            with local._publication_lock(target.parent):
                local._select_roles(target, backup, current)
    with pytest.raises(local.ClinVarLocalError, match="CURRENT changed before publication"):
        local.download_and_build(tmp_path / "downloads", target, expected_current=old["snapshot_id"],
            expected_checksums={name: value["remote_md5"] for name, value in checked["files"].items()}, progress=progress)
    assert role_bytes(target) == before
    assert target.resolve() == backup


def test_disk_preflight_accounts_for_distinct_download_and_staging_filesystems(tmp_path, monkeypatch):
    target, _, remote, _ = remote_fixture(tmp_path, monkeypatch)
    monkeypatch.setenv("SQLITE_TMPDIR", str(target.parent))
    original = workflow._filesystem
    def separate(path):
        existing, _ = original(path)
        return existing, 1 if Path(path) == remote else 2
    monkeypatch.setattr(workflow, "_filesystem", separate)
    monkeypatch.setattr(workflow.shutil, "disk_usage", lambda path: SimpleNamespace(free=2**50))
    report = workflow.disk_preflight(target, remote)
    assert len(report["filesystems"]) == 2
    archive_bytes = sum(report["archive_estimates"].values())
    assert all(item["required_bytes"] > 0 for item in report["filesystems"])
    assert sum(item["required_bytes"] for item in report["filesystems"]) > archive_bytes + 2 * report["database_estimate_bytes"]


def test_existing_builder_lock_disables_update_and_refuses_launch(tmp_path, monkeypatch):
    target, _, _, checked = remote_fixture(tmp_path, monkeypatch)
    def forbidden(*args, **kwargs):
        pytest.fail("An existing CLI builder must prevent worker launch")
    monkeypatch.setattr(workflow.subprocess, "Popen", forbidden)
    with local._publication_lock(target.parent / (target.name + ".snapshots"), blocking=False):
        row = api("GET", "").json()
        assert row["installed"] and row["details"]["builder_busy"]
        assert not row["can_update"]
        assert api("POST", "/update", selection(checked)).status_code == 409
