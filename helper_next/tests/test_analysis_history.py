import shutil
from pathlib import Path

import pytest
from fastapi import HTTPException

from helper_next.api import analysis
from helper_next.core import analysis_history as history


def archived_run(tmp_path):
    work = tmp_path / "workdir" / "run1"
    work.mkdir(parents=True)
    return history.create({
        "run_id": "run1", "run_dir": str(work), "launch_dir": str(work),
        "status": "completed", "workflow": ["alignment"], "samples": [{"sample_name": "S1"}],
        "request": {"run_id": "run1", "workdir": str(work.parent),
                    "samplesheet_content": "S1\t/input/R1.fastq.gz\t/input/R2.fastq.gz\n"},
        "pipeline_config": {"version": "original"}, "tools_config": {"tool": "original"},
        "panel_design": {"name": "original"},
    })


def test_history_survives_workdir_deletion_and_does_not_read_it(tmp_path, monkeypatch):
    record = archived_run(tmp_path)
    shutil.rmtree(record["run_dir"])
    monkeypatch.setattr(analysis, "run_status", lambda *args: pytest.fail("History must not read workdir"))
    assert analysis.analysis_history()["runs"][0]["samples"] == [{"sample_name": "S1"}]
    assert analysis.analysis_history_detail(record["id"])["pipeline_config"] == {"version": "original"}


def test_reanalysis_uses_snapshot_without_original_workdir(tmp_path, monkeypatch):
    record = archived_run(tmp_path)
    shutil.rmtree(record["run_dir"])
    calls = []
    monkeypatch.setattr(analysis, "launch_run", lambda request, **kwargs: calls.append((request, kwargs)) or {})
    analysis.replay_analysis(record["id"], analysis.HistoryReplayRequest())
    request, kwargs = calls[0]
    assert request.run_id != record["run_id"]
    assert request.samplesheet_content == record["request"]["samplesheet_content"]
    assert kwargs["snapshot"]["tools_config"] == record["tools_config"]
    assert kwargs["parent_id"] == record["id"]
    assert len(history.list_runs()) == 1


def test_resume_requires_cache_and_reanalysis_rejects_existing_destination(tmp_path):
    record = archived_run(tmp_path)
    for payload in (analysis.HistoryReplayRequest(mode="resume"), analysis.HistoryReplayRequest(run_id="run1")):
        with pytest.raises(HTTPException) as error:
            analysis.replay_analysis(record["id"], payload)
        assert error.value.status_code == 409


def test_final_status_and_sample_progress_are_persisted(tmp_path, monkeypatch):
    record = archived_run(tmp_path)
    matrix = [{"step": "alignment", "samples": [{"sample_name": "S1", "status": "completed"}]}]
    monkeypatch.setattr(analysis, "run_status", lambda path: {"status": "completed", "workflow_matrix": matrix})
    analysis.capture_history_status(record["id"], 0)
    shutil.rmtree(record["run_dir"])
    saved = history.get(record["id"])
    assert saved["status"] == "completed"
    assert saved["exit_code"] == 0
    assert saved["finished_at"]
    assert saved["last_status"]["workflow_matrix"] == matrix


def test_separate_attempts_have_unique_ids_and_atomic_updates(tmp_path):
    first = archived_run(tmp_path)
    second = history.create(dict(first, parent_id=first["id"]))
    history.update(second["id"], status="failed")
    assert first["id"] != second["id"]
    assert history.get(first["id"])["status"] == "completed"
    assert history.get(second["id"])["status"] == "failed"


def test_delete_history_record_keeps_run_files_and_reparents_children(tmp_path):
    original = archived_run(tmp_path)
    child = history.create(dict(original, parent_id=original["id"], run_id="run2"))
    run_dir = original["run_dir"]

    result = analysis.delete_analysis_history(original["id"])

    assert result["status"] == "deleted"
    assert result["run_files_deleted"] is False
    assert history.get(original["id"]) is None
    assert history.get(child["id"])["parent_id"] is None
    assert Path(run_dir).is_dir()


def test_delete_history_rejects_active_analysis(tmp_path):
    record = archived_run(tmp_path)
    history.update(record["id"], status="running")

    with pytest.raises(HTTPException) as error:
        analysis.delete_analysis_history(record["id"])

    assert error.value.status_code == 409
    assert history.get(record["id"]) is not None
