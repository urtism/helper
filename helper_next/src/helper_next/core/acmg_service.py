"""Own an optional local ACMG subprocess; keep the engine's Python separate."""

import json
import logging
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import time
from urllib.parse import urlsplit

from helper_next.core.acmg_client import ACMGClient, EngineError
from helper_next.core.project import find_repo_root


logger = logging.getLogger(__name__)


class ACMGService:
    def __init__(self):
        self.process = None
        self.profile_directory = None

    def _environment(self, host, port):
        env = dict(os.environ, ACMG_HOST=host, ACMG_PORT=str(port))
        configured = os.environ.get("HELPER_ACMG_CONFIG")
        if configured:
            config_path = Path(configured).expanduser()
        else:
            try:
                config_path = find_repo_root(Path(__file__).resolve().parent) / "configs" / "acmg_engine.json"
            except RuntimeError:
                return env
            if not config_path.is_file():
                return env
        config = json.loads(config_path.read_text())
        if not isinstance(config, dict):
            raise ValueError("ACMG launcher configuration must be an object")
        if "enable_research_interpretation" in config:
            enabled = config["enable_research_interpretation"]
            if not isinstance(enabled, bool):
                raise ValueError("ACMG enable_research_interpretation must be a boolean")
            env.setdefault("ACMG_ENABLE_RESEARCH_INTERPRETATION", str(enabled).lower())
        if "ACMG_PROFILES_DIR" in env:
            return env
        files = config.get("profile_files", [])
        if not isinstance(files, list) or any(not isinstance(p, str) or not p for p in files):
            raise ValueError("ACMG profile_files must be a list of file paths")
        if files:
            self.profile_directory = tempfile.TemporaryDirectory(prefix="helper-acmg-profiles-")
            for index, source in enumerate(files):
                path = Path(source).expanduser()
                if not path.is_absolute():
                    path = config_path.parent / path
                target = Path(self.profile_directory.name) / "{:03d}-{}.json".format(index, path.stem)
                shutil.copyfile(str(path), str(target))
            env["ACMG_PROFILES_DIR"] = self.profile_directory.name
            logger.info("Loading %s explicitly configured ACMG research profiles", len(files))
        return env

    def _command(self):
        configured = os.environ.get("HELPER_ACMG_COMMAND")
        if configured:
            return shlex.split(configured)
        directory = os.environ.get("HELPER_ACMG_ENGINE_DIR")
        if directory:
            directory = Path(directory).expanduser()
        else:
            try:
                directory = find_repo_root(Path(__file__).resolve().parent).parent / "acmg-engine"
            except RuntimeError:
                directory = None
        if directory is not None:
            executable = directory / ".venv" / "bin" / "acmg-engine"
            if executable.is_file() and os.access(str(executable), os.X_OK):
                return [str(executable)]
        executable = shutil.which("acmg-engine")
        return [executable] if executable else None

    def start(self):
        if self.process is not None:
            return
        if os.environ.get("HELPER_ACMG_AUTOSTART", "1").lower() in ("0", "false", "no", "off"):
            return
        try:
            client = ACMGClient()
            url = urlsplit(client.url)
            if (url.scheme != "http" or url.hostname not in ("127.0.0.1", "localhost", "::1")
                    or url.path not in ("", "/")):
                return
            port = url.port or 80
            client.timeout = 0.5
            try:
                health = client.call("/health")
            except EngineError as exc:
                # Only a refused connection justifies starting another process.
                if (exc.details or {}).get("reason") != "CONNECTION_REFUSED":
                    logger.warning("ACMG auto-start skipped: %s", exc)
                    return
            else:
                if health.get("service") == "acmg-engine" and health.get("status") == "ok":
                    logger.info("Reusing ACMG Engine at %s", client.url)
                else:
                    logger.warning("ACMG auto-start skipped: another service responds at %s", client.url)
                return

            command = self._command()
            if not command:
                logger.warning(
                    "ACMG Engine is not installed: install it in acmg-engine/.venv "
                    "or set HELPER_ACMG_COMMAND to its executable. HELPER will continue without ACMG."
                )
                return
            env = self._environment(url.hostname, port)
            self.process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError("ACMG Engine exited with code {}".format(self.process.returncode))
                try:
                    health = client.call("/health")
                except EngineError:
                    pass
                else:
                    if health.get("service") == "acmg-engine" and health.get("status") == "ok":
                        logger.info("Started ACMG Engine at %s (pid %s)", client.url, self.process.pid)
                        return
                time.sleep(0.1)
            raise RuntimeError("ACMG Engine did not become ready within 10 seconds")
        except (EngineError, OSError, ValueError, RuntimeError) as exc:
            logger.warning("ACMG auto-start failed: %s. HELPER will continue without ACMG.", exc)
            self.stop()

    def stop(self):
        process = self.process
        self.process = None
        try:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                else:
                    process.wait()
        finally:
            if self.profile_directory is not None:
                self.profile_directory.cleanup()
                self.profile_directory = None
