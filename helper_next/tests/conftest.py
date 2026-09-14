import pytest


@pytest.fixture(autouse=True)
def isolate_analysis_history(monkeypatch, tmp_path):
    monkeypatch.setenv("HELPER_ANALYSIS_HISTORY_DB", str(tmp_path / "archive" / "history.sqlite3"))
    monkeypatch.setattr("helper_next.api.analysis.monitor_run", lambda *args: None)
