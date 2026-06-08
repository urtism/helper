import pytest
from fastapi import HTTPException

from helper_next.api.analysis import FakeRunRequest, real_run, run_status, test_run as run_fake_analysis


def test_fake_analysis_writes_manifest_outputs_and_logs(tmp_path):
    samplesheet = """
    {
      "sample_list": ["S1"],
      "sample_organization": "only cases",
      "alignment": {
        "S1": {
          "case": {
            "sample_name": "S1",
            "fastq_R1": "/data/S1_R1.fastq.gz",
            "fastq_R2": "/data/S1_R2.fastq.gz",
            "fastq_I2": ""
          }
        }
      }
    }
    """

    result = run_fake_analysis(
        FakeRunRequest(
            run_id="run 1",
            samplesheet_content=samplesheet,
            aligner="BOWTIE2",
            workdir=str(tmp_path),
        )
    )

    assert result["status"] == "completed"
    assert result["run_id"] == "run_1"
    assert result["manifest"].endswith("manifest.tsv")
    assert result["outputs"][0]["bam"].endswith("S1.sort.bam")
    assert result["logs"]["step"].endswith("alignment.step.log")

    status = run_status(result["run_dir"])
    assert status["status"] == "completed"
    assert status["workflow_matrix"][0]["counts"]["completed"] == 1
    assert "alignment: total=1 running=0 completed=1 failed=0 planned=0" in status["content"]["workflow_matrix"]
    assert status["content"]["workflow_plan"].startswith("order\tstep\tstatus")
    assert "ALIGNMENT:FAKE_ALIGN" in status["content"]["nextflow_trace"]


def test_real_analysis_reports_missing_nextflow(monkeypatch, tmp_path):
    monkeypatch.setattr("helper_next.api.analysis.shutil.which", lambda name: None)

    with pytest.raises(HTTPException) as exc:
        real_run(
            FakeRunRequest(
                run_id="real_run",
                samplesheet_content="S1\t/data/S1_R1.fastq.gz\t/data/S1_R2.fastq.gz\n",
                aligner="BWA v.0.7.17",
                workdir=str(tmp_path),
            )
        )

    assert exc.value.status_code == 400
    assert "Nextflow is not installed" in exc.value.detail


def test_run_status_stays_running_when_samples_are_unfinished(monkeypatch, tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "manifest.tsv").write_text(
        "sample_id\trole\tsample_name\tfastq_r1\tfastq_r2\tfastq_i2\tbam\tmerged_vcf\tvariants_tsv\n"
        "S1\tcase\tS1\t/data/S1_R1.fastq.gz\t/data/S1_R2.fastq.gz\t\t\t\t\n"
    )
    (run_dir / "nextflow.log").write_text("Completed at: fake\n")
    (run_dir / "nextflow.pid").write_text("12345\n")
    monkeypatch.setattr("helper_next.api.analysis.is_pid_running", lambda pid: True)

    status = run_status(str(run_dir))

    assert status["status"] == "running"
    assert status["workflow_matrix"][0]["counts"]["running"] == 1


def test_real_analysis_passes_slurm_profile(monkeypatch, tmp_path):
    samplesheet = """
    {
      "sample_list": ["S1"],
      "sample_organization": "only cases",
      "alignment": {
        "S1": {
          "case": {
            "sample_name": "S1",
            "fastq_R1": "/data/S1_R1.fastq.gz",
            "fastq_R2": "/data/S1_R2.fastq.gz",
            "fastq_I2": ""
          }
        }
      }
    }
    """

    class FakeProcess:
        pid = 12345

    monkeypatch.setattr("helper_next.api.analysis.shutil.which", lambda name: "/usr/bin/nextflow")
    monkeypatch.setattr(
        "helper_next.api.analysis.load_json",
        lambda path: {
            "hg19": {"fasta": "/refs/hg19.fa"},
            "BWA v.0.7.17": {"path": "bwa"},
            "PICARD v.2.7.1": {"path": "/tools/picard.jar"},
            "SAMTOOLS": {"path": "samtools"},
        },
    )
    monkeypatch.setattr("helper_next.api.analysis.subprocess.Popen", lambda *args, **kwargs: FakeProcess())

    result = real_run(
        FakeRunRequest(
            run_id="slurm_run",
            samplesheet_content=samplesheet,
            aligner="BWA v.0.7.17",
            workdir=str(tmp_path),
            execution_profile="slurm",
            queue="short",
        )
    )

    assert result["execution_profile"] == "slurm"
    assert result["queue"] == "short"
    assert "-profile slurm" in result["command"]
    assert "--queue short" in result["command"]
