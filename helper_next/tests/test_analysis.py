import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from helper_next.api.analysis import FakeRunRequest, real_run, resolve_tools_path, run_status, test_run as run_fake_analysis
from helper_next.core.project import ProjectPaths


def test_fake_analysis_writes_manifest_outputs_and_logs(tmp_path):
    samplesheet = """
    {
      "sample_list": ["S1"],
      "sample_organization": "only cases",
      "prealignment": {
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


def test_resolve_tools_path_accepts_relative_config_path(tmp_path):
    configs = tmp_path / "configs"
    tools_dir = configs / "tools_cfg"
    tools_dir.mkdir(parents=True)
    tools_file = tools_dir / "tools.cfg"
    tools_file.write_text("{}")

    assert resolve_tools_path("tools_cfg/tools.cfg", configs) == tools_file.resolve()
    assert resolve_tools_path("", configs) == tools_file


def test_resolve_tools_path_rejects_paths_outside_configs(tmp_path):
    configs = tmp_path / "configs"
    configs.mkdir()
    outside = tmp_path / "outside.cfg"
    outside.write_text("{}")

    with pytest.raises(HTTPException):
        resolve_tools_path(str(outside), configs)


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


def test_run_status_reads_prealignment_status(tmp_path):
    run_dir = tmp_path / "run"
    sample_log_dir = run_dir / "results" / "LOGS" / "PREALIGNMENT" / "samples"
    sample_log_dir.mkdir(parents=True)
    (run_dir / "manifest.tsv").write_text(
        "sample_id\trole\tsample_name\tfastq_r1\tfastq_r2\tfastq_i2\tbam\tmerged_vcf\tvariants_tsv\n"
        "S1\tcase\tS1\t/data/S1_R1.fastq.gz\t/data/S1_R2.fastq.gz\t\t\t\t\n"
    )
    (run_dir / "run_config.json").write_text('{"workflow": ["prealignment"]}\n')
    (sample_log_dir / "S1.prealignment.status.tsv").write_text(
        "step\ttool\tsample_id\trole\tsample_name\tstatus\texit_code\tstarted\tcompleted\n"
        "prealignment\tFASTQC\tS1\tcase\tS1\tcompleted\t0\tfake\tfake\n"
    )

    status = run_status(str(run_dir))

    assert status["status"] == "completed"
    assert status["workflow_matrix"][0]["step"] == "prealignment"
    assert status["workflow_matrix"][0]["counts"]["completed"] == 1


def test_run_status_reads_variantcalling_status(tmp_path):
    run_dir = tmp_path / "run"
    sample_log_dir = run_dir / "results" / "LOGS" / "VARIANTCALLING" / "samples"
    sample_log_dir.mkdir(parents=True)
    (run_dir / "manifest.tsv").write_text(
        "sample_id\trole\tsample_name\tfastq_r1\tfastq_r2\tfastq_i2\tbam\tmerged_vcf\tvariants_tsv\n"
        "S1\tcase\tS1\t\t\t\t/data/S1.bam\t\t\n"
    )
    (run_dir / "run_config.json").write_text('{"workflow": ["variantcalling"]}\n')
    (sample_log_dir / "S1.variantcalling.status.tsv").write_text(
        "step\ttool\tsample_id\trole\tsample_name\tstatus\texit_code\tstarted\tcompleted\n"
        "variantcalling\tGATK_HAPLOTYPECALLER\tS1\tcase\tS1\tcompleted\t0\tfake\tfake\n"
    )

    status = run_status(str(run_dir))

    assert status["status"] == "completed"
    assert status["workflow_matrix"][0]["step"] == "variantcalling"
    assert status["workflow_matrix"][0]["counts"]["completed"] == 1


def test_run_status_reads_annotation_status(tmp_path):
    run_dir = tmp_path / "run"
    sample_log_dir = run_dir / "results" / "LOGS" / "ANNOTATION" / "samples"
    sample_log_dir.mkdir(parents=True)
    (run_dir / "manifest.tsv").write_text(
        "sample_id\trole\tsample_name\tfastq_r1\tfastq_r2\tfastq_i2\tbam\tmerged_vcf\tvariants_tsv\n"
        "S1\tcase\tS1\t\t\t\t\t/data/S1.vcf\t\n"
    )
    (run_dir / "run_config.json").write_text('{"workflow": ["annotation"]}\n')
    (sample_log_dir / "S1.annotation.status.tsv").write_text(
        "step\ttool\tsample_id\trole\tsample_name\tstatus\texit_code\tstarted\tcompleted\n"
        "annotation\tVARIANT_ANNOTATION\tS1\tcase\tS1\tcompleted\t0\tfake\tfake\n"
    )

    status = run_status(str(run_dir))

    assert status["status"] == "completed"
    assert status["workflow_matrix"][0]["step"] == "annotation"
    assert status["workflow_matrix"][0]["counts"]["completed"] == 1


def test_real_analysis_passes_slurm_profile(monkeypatch, tmp_path):
    samplesheet = """
    {
      "sample_list": ["S1"],
      "sample_organization": "only cases",
      "prealignment": {
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

    popen_calls = []

    monkeypatch.setattr("helper_next.api.analysis.shutil.which", lambda name: "/usr/bin/nextflow")
    monkeypatch.setattr("helper_next.api.analysis.compatible_java_home", lambda: tmp_path / "java-21")
    monkeypatch.setattr(
        "helper_next.api.analysis.load_json",
        lambda path: {
            "hg19": {"fasta": "/refs/hg19.fa"},
            "FASTQC v.0.11.8": {"path": "fastqc"},
            "BWA v.0.7.17": {"path": "bwa"},
            "PICARD v.2.7.1": {"path": "/tools/picard.jar"},
            "SAMTOOLS": {"path": "samtools"},
        },
    )

    def fake_popen(*args, **kwargs):
        popen_calls.append({"args": args, "kwargs": kwargs})
        return FakeProcess()

    monkeypatch.setattr("helper_next.api.analysis.subprocess.Popen", fake_popen)

    result = real_run(
        FakeRunRequest(
            run_id="slurm_run",
            samplesheet_content=samplesheet,
            aligner="BWA v.0.7.17",
            workdir=str(tmp_path),
            execution_profile="slurm",
            queue="short",
            requested_workflow=["prealignment", "alignment"],
        )
    )

    assert result["execution_profile"] == "slurm"
    assert result["queue"] == "short"
    assert "-profile slurm" in result["command"]
    assert "--queue short" in result["command"]
    assert popen_calls[0]["kwargs"]["env"]["JAVA_HOME"] == str(tmp_path / "java-21")
    assert popen_calls[0]["kwargs"]["env"]["JAVA_CMD"] == str(tmp_path / "java-21" / "bin" / "java")
    assert "JAVA_HOME={}".format(tmp_path / "java-21") in open(result["command_file"]).read()
    with open(result["run_config"]) as handle:
        run_config = json.load(handle)
    assert run_config["workflow"] == ["prealignment", "alignment"]


def test_real_analysis_snapshots_selected_panel_design(monkeypatch, tmp_path):
    samplesheet = """
    {
      "sample_list": ["S1"],
      "sample_organization": "only cases",
      "preprocessing": {
        "S1": {
          "case": {
            "sample_name": "S1",
            "bam": "/data/S1.bam"
          }
        }
      }
    }
    """

    configs = tmp_path / "configs"
    configs.mkdir()
    (configs / "experiment_list.cfg").write_text(
        """
        {
          "list": ["Panel A"],
          "Panel A": {
            "panel_name": "Panel A",
            "panel_technology": "Capture Enrichment",
            "target_bed": "/targets/panel_a.bed"
          }
        }
        """
    )

    class FakeProcess:
        pid = 12345

    monkeypatch.setattr(
        "helper_next.api.analysis.get_project_paths",
        lambda: ProjectPaths(
            root=tmp_path,
            configs=configs,
            pipelines=configs / "pipelines",
            files=tmp_path / "files",
            scripts=tmp_path / "scripts",
        ),
    )
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
            run_id="panel_snapshot",
            samplesheet_content=samplesheet,
            workdir=str(tmp_path / "runs"),
            gene_panel_design="Panel A",
        )
    )

    with open(result["run_config"]) as handle:
        run_config = json.load(handle)

    assert result["panel_design"]["source_name"] == "Panel A"
    assert run_config["panel_design"]["assets"]["target_bed"] == "/targets/panel_a.bed"
    assert run_config["panel_design"]["validation"]["target_bed_present"] is True


def test_real_analysis_default_prealignment_run_uses_full_stable_slice(monkeypatch, tmp_path):
    samplesheet = """
    {
      "sample_list": ["S1"],
      "sample_organization": "only cases",
      "prealignment": {
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

    popen_calls = []

    monkeypatch.setattr("helper_next.api.analysis.shutil.which", lambda name: "/usr/bin/nextflow")
    monkeypatch.setattr(
        "helper_next.api.analysis.load_json",
        lambda path: {
            "hg19": {"fasta": "/refs/hg19.fa"},
            "FASTQC v.0.11.8": {"path": "fastqc"},
            "BWA v.0.7.17": {"path": "bwa"},
            "PICARD v.2.7.1": {"path": "/tools/picard.jar"},
            "SAMTOOLS": {"path": "samtools"},
        },
    )

    def fake_popen(*args, **kwargs):
        popen_calls.append({"args": args, "kwargs": kwargs})
        return FakeProcess()

    monkeypatch.setattr("helper_next.api.analysis.subprocess.Popen", fake_popen)

    result = real_run(
        FakeRunRequest(
            run_id="default_slice",
            samplesheet_content=samplesheet,
            workdir=str(tmp_path),
        )
    )

    with open(result["run_config"]) as handle:
        run_config = json.load(handle)
    with open(Path(result["run_dir"]) / "alignment.pipeline.json") as handle:
        pipeline_config = json.load(handle)

    assert result["status"] == "submitted"
    assert run_config["workflow"] == ["prealignment", "alignment", "preprocessing"]
    assert pipeline_config["workflow"] == ["prealignment", "alignment", "preprocessing"]
    assert "--keep_intermediates false" in result["command"]
    assert popen_calls[0]["args"][0][0] == "/usr/bin/nextflow"


def test_real_analysis_passes_selected_preprocessing_substeps(monkeypatch, tmp_path):
    samplesheet = """
    {
      "sample_list": ["S1"],
      "sample_organization": "only cases",
      "preprocessing": {
        "S1": {
          "case": {
            "sample_name": "S1",
            "bam": "/data/S1.bam"
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
            "GATK v.3.7": {"path": "/tools/GenomeAnalysisTK.jar"},
            "SAMTOOLS": {"path": "samtools"},
            "dbsnp": {"path": "/refs/dbsnp.vcf"},
            "mills": {"path": "/refs/mills.vcf"},
        },
    )
    monkeypatch.setattr("helper_next.api.analysis.subprocess.Popen", lambda *args, **kwargs: FakeProcess())

    result = real_run(
        FakeRunRequest(
            run_id="preprocessing_gatk3",
            samplesheet_content=samplesheet,
            workdir=str(tmp_path),
            requested_preprocessing_workflow=["add_readgroups", "mark_pcr_dup", "indel_realignment", "BQ_recalibration"],
        )
    )

    with open(Path(result["run_dir"]) / "alignment.pipeline.json") as handle:
        pipeline_config = json.load(handle)
    with open(result["run_config"]) as handle:
        run_config = json.load(handle)

    assert pipeline_config["preprocessing"]["workflow"] == [
        "add_readgroups",
        "mark_pcr_dup",
        "indel_realignment",
        "BQ_recalibration",
    ]
    assert run_config["steps"][0]["operations"] == pipeline_config["preprocessing"]["workflow"]


def test_real_analysis_can_submit_variantcalling_from_bam(monkeypatch, tmp_path):
    samplesheet = """
    {
      "sample_list": ["S1"],
      "sample_organization": "only cases",
      "variantcalling": {
        "S1": {
          "case": {
            "sample_name": "S1",
            "bam": "/data/S1.bam"
          }
        }
      }
    }
    """

    class FakeProcess:
        pid = 12345

    popen_calls = []

    monkeypatch.setattr("helper_next.api.analysis.shutil.which", lambda name: "/usr/bin/nextflow")
    monkeypatch.setattr(
        "helper_next.api.analysis.load_json",
        lambda path: {
            "hg19": {"fasta": "/refs/hg19.fa"},
            "BWA v.0.7.17": {"path": "bwa"},
            "PICARD v.2.7.1": {"path": "/tools/picard.jar"},
            "GATK v.4.1": {"path": "gatk"},
            "SAMTOOLS": {"path": "samtools"},
        },
    )

    def fake_popen(*args, **kwargs):
        popen_calls.append({"args": args, "kwargs": kwargs})
        return FakeProcess()

    monkeypatch.setattr("helper_next.api.analysis.subprocess.Popen", fake_popen)

    result = real_run(
        FakeRunRequest(
            run_id="variant_run",
            samplesheet_content=samplesheet,
            workdir=str(tmp_path),
        )
    )

    with open(result["run_config"]) as handle:
        run_config = json.load(handle)
    with open(Path(result["run_dir"]) / "alignment.pipeline.json") as handle:
        pipeline_config = json.load(handle)

    assert result["status"] == "submitted"
    assert run_config["workflow"] == ["variantcalling"]
    assert pipeline_config["variantcalling"]["tools"] == ["GATK v.4.1"]
    assert popen_calls[0]["args"][0][0] == "/usr/bin/nextflow"


def test_real_analysis_can_submit_postprocessing_from_vcf(monkeypatch, tmp_path):
    samplesheet = """
    {
      "sample_list": ["S1"],
      "sample_organization": "only cases",
      "postprocessing": {
        "S1": {
          "case": {
            "sample_name": "S1",
            "gatk_vcf": "/data/S1.g.vcf"
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
            "BCFTOOLS": {"path": "bcftools"},
        },
    )
    monkeypatch.setattr("helper_next.api.analysis.subprocess.Popen", lambda *args, **kwargs: FakeProcess())

    result = real_run(
        FakeRunRequest(
            run_id="postprocessing_run",
            samplesheet_content=samplesheet,
            workdir=str(tmp_path),
            requested_postprocessing_workflow=["vcf_norm", "vcf_to_tsv"],
        )
    )

    with open(result["run_config"]) as handle:
        run_config = json.load(handle)
    with open(Path(result["run_dir"]) / "alignment.pipeline.json") as handle:
        pipeline_config = json.load(handle)

    assert run_config["workflow"] == ["postprocessing"]
    assert pipeline_config["postprocessing"]["workflow"] == ["vcf_norm", "vcf_to_tsv"]


def test_real_analysis_can_submit_annotation_from_vcf(monkeypatch, tmp_path):
    samplesheet = """
    {
      "sample_list": ["S1"],
      "sample_organization": "only cases",
      "annotation": {
        "S1": {
          "case": {
            "sample_name": "S1",
            "merged_vcf": "/data/S1.vcf"
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
            "VEP v.95": {"path": "vep"},
            "GeneSplicer": {"path": "/tools/genesplicer"},
            "MaxEntScan": {"path": "/tools/maxentscan"},
            "SpliceRegion": {"path": ""},
            "dbNSFP": {"path": "/db/dbNSFP.gz"},
        },
    )
    monkeypatch.setattr("helper_next.api.analysis.subprocess.Popen", lambda *args, **kwargs: FakeProcess())

    result = real_run(
        FakeRunRequest(
            run_id="annotation_run",
            samplesheet_content=samplesheet,
            workdir=str(tmp_path),
            requested_annotation_workflow=["vep_annotation", "ann_vcf_to_tsv"],
        )
    )

    with open(result["run_config"]) as handle:
        run_config = json.load(handle)
    with open(Path(result["run_dir"]) / "alignment.pipeline.json") as handle:
        pipeline_config = json.load(handle)

    assert run_config["workflow"] == ["annotation"]
    assert pipeline_config["annotation"]["workflow"] == ["vep_annotation", "ann_vcf_to_tsv"]
    assert pipeline_config["annotation"]["vep_annotation"]["tool"] == "VEP v.95"
    assert pipeline_config["resolved_tools"]["annotation"]["vep_annotation"]["path"] == "vep"
    resolved_args = pipeline_config["annotation"]["vep_annotation"]["VEP v.95"]["resolved_args"]
    assert "--cache --offline" in resolved_args
    assert "--assembly GRCh37 --species homo_sapiens" in resolved_args
    assert "--plugin GeneSplicer,/tools/genesplicer" in resolved_args
    assert "--plugin dbNSFP,/db/dbNSFP.gz" in resolved_args


def test_real_analysis_rejects_prealignment_to_preprocessing_without_alignment(monkeypatch, tmp_path):
    samplesheet = """
    {
      "sample_list": ["S1"],
      "sample_organization": "only cases",
      "prealignment": {
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

    monkeypatch.setattr("helper_next.api.analysis.shutil.which", lambda name: "/usr/bin/nextflow")
    monkeypatch.setattr(
        "helper_next.api.analysis.load_json",
        lambda path: {
            "hg19": {"fasta": "/refs/hg19.fa"},
            "FASTQC v.0.11.8": {"path": "fastqc"},
            "BWA v.0.7.17": {"path": "bwa"},
            "PICARD v.2.7.1": {"path": "/tools/picard.jar"},
            "SAMTOOLS": {"path": "samtools"},
        },
    )

    with pytest.raises(HTTPException) as exc:
        real_run(
            FakeRunRequest(
                run_id="bad_workflow",
                samplesheet_content=samplesheet,
                workdir=str(tmp_path),
                requested_workflow=["prealignment", "preprocessing"],
            )
        )

    assert exc.value.status_code == 400
    assert "preprocessing requires bam input" in exc.value.detail


def test_nextflow_demo_script_documents_real_stable_slice():
    script = Path(__file__).resolve().parents[2] / "scripts" / "run_nextflow_demo.sh"

    text = script.read_text()

    assert script.exists()
    assert "prealignment,alignment,preprocessing" in text
    assert "GATK v.4.1" in text
    assert "picard-wrapper" in text
    assert "nextflow run" in text
