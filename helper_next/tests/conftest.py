import pytest


@pytest.fixture(autouse=True)
def isolate_analysis_history(monkeypatch, tmp_path):
    monkeypatch.setenv("HELPER_ANALYSIS_HISTORY_DB", str(tmp_path / "archive" / "history.sqlite3"))
    monkeypatch.setenv("HELPER_IMPORTED_RUNS_DIR", str(tmp_path / "imported_variant_runs"))
    monkeypatch.setenv("HELPER_GENE_PHENOTYPE_DB", str(tmp_path / "knowledge" / "gene_phenotype.sqlite3"))
    monkeypatch.setenv(
        "HELPER_GNOMAD_FREQUENCY_CACHE", str(tmp_path / "knowledge" / "gnomad_frequency.sqlite3")
    )
    monkeypatch.setattr("helper_next.api.analysis.monitor_run", lambda *args: None)
