"""Local process ownership and startup failures, independent of scientific rules."""

import asyncio
import json
from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest

from helper_next.core import acmg_service
from helper_next.core.acmg_client import EngineError


HEALTH = {"service": "acmg-engine", "status": "ok"}


def unavailable(reason="CONNECTION_REFUSED"):
    return EngineError("ENGINE_UNAVAILABLE", reason, 503, {"reason": reason})


@pytest.fixture
def service(monkeypatch, tmp_path):
    monkeypatch.setenv("HELPER_ACMG_AUTOSTART", "1")
    monkeypatch.setenv("ACMG_ENGINE_URL", "http://127.0.0.1:8012")
    monkeypatch.setenv("HELPER_ACMG_COMMAND", '"/engine venv/bin/acmg-engine"')
    monkeypatch.delenv("ACMG_PROFILES_DIR", raising=False)
    config = tmp_path / "engine.json"
    config.write_text("{}")
    monkeypatch.setenv("HELPER_ACMG_CONFIG", str(config))
    client = Mock()
    client.url = "http://127.0.0.1:8012"
    monkeypatch.setattr(acmg_service, "ACMGClient", lambda: client)
    process = Mock(pid=1234)
    process.poll.return_value = None
    launch = Mock(return_value=process)
    monkeypatch.setattr(acmg_service.subprocess, "Popen", launch)
    return acmg_service.ACMGService(), client, process, launch


def test_starts_local_engine_with_configured_port_and_stops_owned_process(service, monkeypatch):
    manager, client, process, launch = service
    monkeypatch.setenv("ACMG_PROFILES_DIR", "/chosen/profiles")
    monkeypatch.delenv("ACMG_ENABLE_RESEARCH_INTERPRETATION", raising=False)
    client.call.side_effect = [unavailable(), unavailable(), HEALTH]
    monkeypatch.setattr(acmg_service.time, "sleep", lambda seconds: None)
    manager.start()
    assert launch.call_args.args == (["/engine venv/bin/acmg-engine"],)
    env = launch.call_args.kwargs["env"]
    assert env["ACMG_HOST"] == "127.0.0.1"
    assert env["ACMG_PORT"] == "8012"
    assert env["ACMG_PROFILES_DIR"] == "/chosen/profiles"
    assert "ACMG_ENABLE_RESEARCH_INTERPRETATION" not in env
    manager.start()  # Repeated startup must not create another process.
    launch.assert_called_once()
    manager.stop()
    process.terminate.assert_called_once()
    process.wait.assert_called_once_with(timeout=5)
    manager.stop()
    process.terminate.assert_called_once()


@pytest.mark.parametrize("health", [HEALTH, {"service": "other", "status": "ok"}])
def test_existing_service_is_never_started_or_stopped(service, health):
    manager, client, process, launch = service
    client.call.return_value = health
    manager.start()
    manager.stop()
    launch.assert_not_called()
    process.terminate.assert_not_called()


@pytest.mark.parametrize("url", ["http://remote:8000", "https://localhost:8000", "http://127.0.0.1:8000/prefix"])
def test_remote_or_proxied_engine_is_not_managed(service, url):
    manager, client, _, launch = service
    client.url = url
    manager.start()
    client.call.assert_not_called()
    launch.assert_not_called()


def test_autostart_can_be_disabled(service, monkeypatch):
    manager, client, _, launch = service
    monkeypatch.setenv("HELPER_ACMG_AUTOSTART", "0")
    manager.start()
    client.call.assert_not_called()
    launch.assert_not_called()


@pytest.mark.parametrize("reason", ["TIMEOUT", "HOST_NOT_FOUND", "CONNECTION_FAILED"])
def test_only_refused_connection_triggers_start(service, reason):
    manager, client, _, launch = service
    client.call.side_effect = unavailable(reason)
    manager.start()
    launch.assert_not_called()


def test_missing_installation_keeps_helper_available(service, monkeypatch, caplog):
    manager, client, _, launch = service
    client.call.side_effect = unavailable()
    monkeypatch.setattr(manager, "_command", lambda: None)
    manager.start()
    launch.assert_not_called()
    assert "HELPER_ACMG_COMMAND" in caplog.text


def test_launch_failure_keeps_helper_available(service, caplog):
    manager, client, _, launch = service
    client.call.side_effect = unavailable()
    launch.side_effect = FileNotFoundError("missing executable")
    manager.start()
    assert manager.process is None
    assert "missing executable" in caplog.text


def test_failed_child_is_reaped(service, caplog):
    manager, client, process, _ = service
    client.call.side_effect = unavailable()
    process.poll.return_value = 1
    process.returncode = 1
    manager.start()
    assert manager.process is None
    process.wait.assert_called_once()
    process.terminate.assert_not_called()
    assert "exited with code 1" in caplog.text


def test_readiness_timeout_terminates_child(service, monkeypatch, caplog):
    manager, client, process, _ = service
    client.call.side_effect = unavailable()
    monkeypatch.setattr(acmg_service.time, "monotonic", Mock(side_effect=[0, 11]))
    manager.start()
    process.terminate.assert_called_once()
    assert manager.process is None
    assert "did not become ready" in caplog.text


def test_shutdown_kills_unresponsive_owned_child(service):
    manager, _, process, _ = service
    manager.process = process
    process.wait.side_effect = [subprocess.TimeoutExpired("engine", 5), 0]
    manager.stop()
    process.kill.assert_called_once()
    assert manager.process is None


def test_sibling_environment_discovery(monkeypatch, tmp_path):
    helper = tmp_path / "Helper"
    helper.mkdir()
    executable = tmp_path / "acmg-engine" / ".venv" / "bin" / "acmg-engine"
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o755)
    monkeypatch.delenv("HELPER_ACMG_COMMAND", raising=False)
    monkeypatch.delenv("HELPER_ACMG_ENGINE_DIR", raising=False)
    monkeypatch.setattr(acmg_service, "find_repo_root", lambda start: helper)
    assert acmg_service.ACMGService()._command() == [str(executable)]


def test_lifecycle_hooks_manage_service(monkeypatch):
    from helper_next.api.app import create_app

    manager = Mock()
    monkeypatch.setattr("helper_next.api.app.ACMGService", lambda: manager)
    app = create_app()
    asyncio.run(app.router.startup())
    manager.start.assert_called_once()
    asyncio.run(app.router.shutdown())
    manager.stop.assert_called_once()


def test_configured_profile_snapshots_preserve_bytes_and_are_cleaned(service, monkeypatch, tmp_path):
    manager, client, process, launch = service
    source = tmp_path / "profile.json"
    original = b'{"profile_id":"explicit-profile", "version":"1"}\n'
    source.write_bytes(original)
    config = tmp_path / "engine.json"
    config.write_text(json.dumps({"profile_files": [source.name]}))
    client.call.side_effect = [unavailable(), HEALTH]
    monkeypatch.delenv("ACMG_ENABLE_RESEARCH_INTERPRETATION", raising=False)
    manager.start()
    env = launch.call_args.kwargs["env"]
    directory = Path(env["ACMG_PROFILES_DIR"])
    assert [p.read_bytes() for p in directory.glob("*.json")] == [original]
    assert "ACMG_ENABLE_RESEARCH_INTERPRETATION" not in env
    manager.stop()
    assert not directory.exists()
    assert source.read_bytes() == original
    process.terminate.assert_called_once()


def test_profiles_environment_overrides_launcher_config(service, monkeypatch, tmp_path):
    manager, _, _, _ = service
    monkeypatch.setenv("ACMG_PROFILES_DIR", "/explicit/profiles")
    monkeypatch.delenv("ACMG_ENABLE_RESEARCH_INTERPRETATION", raising=False)
    (tmp_path / "engine.json").write_text(json.dumps({"enable_research_interpretation": True}))
    env = manager._environment("127.0.0.1", 8000)
    assert env["ACMG_PROFILES_DIR"] == "/explicit/profiles"
    assert env["ACMG_ENABLE_RESEARCH_INTERPRETATION"] == "true"
    assert manager.profile_directory is None


@pytest.mark.parametrize("content", ['[]', '{"profile_files": "directory"}', '{"profile_files": [null]}', '{broken', '{"enable_research_interpretation": "false"}'])
def test_invalid_profile_configuration_keeps_helper_available(service, tmp_path, content, caplog):
    manager, client, _, launch = service
    (tmp_path / "engine.json").write_text(content)
    client.call.side_effect = unavailable()
    manager.start()
    launch.assert_not_called()
    assert manager.profile_directory is None
    assert "ACMG auto-start failed" in caplog.text


def test_missing_profile_source_cleans_temporary_directory(service, tmp_path, caplog):
    manager, client, _, launch = service
    (tmp_path / "engine.json").write_text(json.dumps({"profile_files": ["missing.json"]}))
    client.call.side_effect = unavailable()
    manager.start()
    launch.assert_not_called()
    assert manager.profile_directory is None
    assert "missing.json" in caplog.text


def test_repository_profile_config_is_found_without_working_directory(service, monkeypatch, tmp_path):
    manager, _, _, _ = service
    root = tmp_path / "Helper"
    config_dir = root / "configs"
    config_dir.mkdir(parents=True)
    source = tmp_path / "selected.json"
    source.write_text("{}")
    (config_dir / "acmg_engine.json").write_text(json.dumps({"profile_files": [str(source)]}))
    monkeypatch.delenv("HELPER_ACMG_CONFIG")
    monkeypatch.setattr(acmg_service, "find_repo_root", lambda start: root)
    monkeypatch.chdir(tmp_path)
    try:
        env = manager._environment("127.0.0.1", 8000)
        assert len(list(Path(env["ACMG_PROFILES_DIR"]).glob("*.json"))) == 1
    finally:
        manager.stop()


@pytest.mark.parametrize("enabled", [True, False])
def test_research_execution_uses_explicit_boolean_config(service, monkeypatch, tmp_path, enabled):
    manager, _, _, _ = service
    monkeypatch.delenv("ACMG_ENABLE_RESEARCH_INTERPRETATION", raising=False)
    (tmp_path / "engine.json").write_text(json.dumps({"enable_research_interpretation": enabled}))
    env = manager._environment("127.0.0.1", 8000)
    assert env["ACMG_ENABLE_RESEARCH_INTERPRETATION"] == str(enabled).lower()


def test_explicit_environment_can_disable_research_despite_config(service, monkeypatch, tmp_path):
    manager, _, _, _ = service
    monkeypatch.setenv("ACMG_ENABLE_RESEARCH_INTERPRETATION", "false")
    (tmp_path / "engine.json").write_text(json.dumps({"enable_research_interpretation": True}))
    env = manager._environment("127.0.0.1", 8000)
    assert env["ACMG_ENABLE_RESEARCH_INTERPRETATION"] == "false"
