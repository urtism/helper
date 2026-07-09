import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from helper_next.api.analysis import (
    FakeRunRequest,
    nextflow_environment,
    normalize_pipeline_for_nextflow,
    real_run,
    resolve_pipeline_config,
    resolve_tools_path,
    run_status,
    StopRunRequest,
    stop_run,
    test_run as run_fake_analysis,
    validate_run,
)
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


def test_stop_analysis_sends_sigterm_to_process_group(monkeypatch, tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "nextflow.pid").write_text("12345\n")
    killed = []

    monkeypatch.setattr("helper_next.api.analysis.is_pid_running", lambda pid: True)
    monkeypatch.setattr("helper_next.api.analysis.os.killpg", lambda pid, sig: killed.append((pid, sig)))

    result = stop_run(StopRunRequest(run_dir=str(run_dir)))

    assert result["status"] == "stopping"
    assert result["pid"] == 12345
    assert killed == [(12345, 15)]
    assert (run_dir / "analysis.stop.requested").exists()


def test_validate_analysis_rejects_missing_samplesheet_file(tmp_path):
    samplesheet = """
    {
      "sample_list": ["S1"],
      "sample_organization": "only cases",
      "prealignment": {
        "S1": {
          "case": {
            "sample_name": "S1",
            "fastq_R1": "/missing/S1_R1.fastq.gz",
            "fastq_R2": "/missing/S1_R2.fastq.gz",
            "fastq_I2": ""
          }
        }
      }
    }
    """

    with pytest.raises(HTTPException) as exc:
        validate_run(
            FakeRunRequest(
                run_id="queued",
                mode="fake_alignment",
                samplesheet_content=samplesheet,
                workdir=str(tmp_path),
                gene_panel_design="panel",
                pipeline_path="pipeline",
            )
        )

    assert exc.value.status_code == 400
    assert "samplesheet file not found: /missing/S1_R1.fastq.gz" in exc.value.detail


def test_validate_analysis_accepts_reachable_samplesheet_files(tmp_path):
    r1 = tmp_path / "S1_R1.fastq.gz"
    r2 = tmp_path / "S1_R2.fastq.gz"
    r1.write_text("")
    r2.write_text("")
    samplesheet = """
    {{
      "sample_list": ["S1"],
      "sample_organization": "only cases",
      "prealignment": {{
        "S1": {{
          "case": {{
            "sample_name": "S1",
            "fastq_R1": "{r1}",
            "fastq_R2": "{r2}",
            "fastq_I2": ""
          }}
        }}
      }}
    }}
    """.format(r1=r1, r2=r2)

    result = validate_run(
        FakeRunRequest(
            run_id="queued",
            mode="fake_alignment",
            samplesheet_content=samplesheet,
            workdir=str(tmp_path),
            gene_panel_design="panel",
            pipeline_path="pipeline",
        )
    )

    assert result["status"] == "ok"
    assert result["checked_files"] == 2
    assert result["entry_step"] == "prealignment"


def test_validate_analysis_requires_panel_and_pipeline(tmp_path):
    with pytest.raises(HTTPException) as exc:
        validate_run(
            FakeRunRequest(
                run_id="queued",
                mode="fake_alignment",
                samplesheet_content="S1\t/missing/S1_R1.fastq.gz\t/missing/S1_R2.fastq.gz\n",
                workdir=str(tmp_path),
            )
        )

    assert "Gene panel/design is required" in exc.value.detail
    assert "Pipeline config is required" in exc.value.detail


def test_nextflow_environment_exports_separate_gatk_java(monkeypatch, tmp_path):
    nextflow_java = tmp_path / "java-21"
    gatk_java = tmp_path / "java-8"
    (nextflow_java / "bin").mkdir(parents=True)
    (gatk_java / "bin").mkdir(parents=True)
    (nextflow_java / "bin" / "java").write_text("")
    (gatk_java / "bin" / "java").write_text("")
    monkeypatch.setattr("helper_next.api.analysis.compatible_java_home", lambda: nextflow_java)
    monkeypatch.setattr("helper_next.api.analysis.compatible_gatk_java_home", lambda: gatk_java)

    env = nextflow_environment()

    assert env["JAVA_HOME"] == str(nextflow_java)
    assert env["GATK_JAVA_HOME"] == str(gatk_java)
    assert env["GATK_JAVA_CMD"] == str(gatk_java / "bin" / "java")


def test_normalize_pipeline_maps_legacy_variant_annotation_to_annotation():
    pipeline = {
        "workflow": ["prealignment", "variant_annotation", "cnvcalling"],
        "variant_annotation": {
            "tool": "VEP v.95",
            "threads": "3",
            "ram": "5g",
            "VEP v.95": {"args": {"args": ["--cache"]}},
        },
    }

    normalized = normalize_pipeline_for_nextflow(pipeline)

    assert normalized["workflow"] == ["prealignment", "annotation"]
    assert normalized["annotation"]["workflow"] == ["vep_annotation", "ann_vcf_to_tsv"]
    assert normalized["annotation"]["vep_annotation"]["tool"] == "VEP v.95"
    assert normalized["annotation"]["vep_annotation"]["VEP v.95"]["args"]["args"] == ["--cache"]


def test_normalize_pipeline_keeps_only_supported_gatk_variantcaller():
    pipeline = {
        "workflow": ["variantcalling"],
        "variantcalling": {
            "tools": ["FREEBAYES v.1.1", "GATK v.4.3", "VARSCAN2"],
            "threads": "2",
            "ram": "4g",
            "filters": {},
            "GATK v.4.3": {"args": []},
        },
    }

    normalized = normalize_pipeline_for_nextflow(pipeline)

    assert normalized["workflow"] == ["variantcalling"]
    assert normalized["variantcalling"]["tools"] == ["GATK v.4.3"]


def test_normalize_pipeline_keeps_supported_deepvariant_caller():
    pipeline = {
        "workflow": ["variantcalling"],
        "variantcalling": {
            "tools": ["FREEBAYES v.1.1", "DeepVariant v.1.10.0"],
            "threads": "4",
            "ram": "16g",
            "filters": {},
            "DeepVariant v.1.10.0": {"args": ["--vcf_stats_report=true"], "model_type": "WES"},
        },
    }

    normalized = normalize_pipeline_for_nextflow(pipeline)

    assert normalized["workflow"] == ["variantcalling"]
    assert normalized["variantcalling"]["tools"] == ["DeepVariant v.1.10.0"]


def test_normalize_pipeline_keeps_supported_freebayes_caller():
    pipeline = {
        "workflow": ["variantcalling"],
        "variantcalling": {
            "tools": ["FREEBAYES v.1.1"],
            "threads": "4",
            "ram": "8g",
            "filters": {},
            "FREEBAYES v.1.1": {"args": ["--use-best-n-alleles", "4"]},
        },
    }

    normalized = normalize_pipeline_for_nextflow(pipeline)

    assert normalized["workflow"] == ["variantcalling"]
    assert normalized["variantcalling"]["tools"] == ["FREEBAYES v.1.1"]


def test_normalize_pipeline_drops_variantcalling_when_no_supported_caller():
    pipeline = {
        "workflow": ["variantcalling", "postprocessing"],
        "variantcalling": {"tools": ["VARSCAN2"], "threads": "2", "ram": "4g", "filters": {}},
        "postprocessing": {"workflow": ["vcf_to_tsv"], "threads": "1", "ram": "1g"},
    }

    normalized = normalize_pipeline_for_nextflow(pipeline)

    assert normalized["workflow"] == ["postprocessing"]
    assert normalized["variantcalling"]["tools"] == []


def test_normalize_legacy_pipeline_fills_supported_step_defaults():
    pipeline = {
        "workflow": ["prealignment", "variantcalling"],
        "prealignment": {
            "workflow": ["trim_adapters"],
            "threads": "1",
            "ram": "1g",
            "fastq_QC": {"tool": "FASTQC v.0.11.8", "FASTQC v.0.11.8": {"args": []}},
        },
        "variantcalling": {
            "tools": ["GATK v.4.3"],
            "threads": "2",
            "ram": "",
            "filters": {},
            "GATK v.4.3": {"args": []},
        },
    }

    normalized = normalize_pipeline_for_nextflow(pipeline)

    assert normalized["prealignment"]["workflow"] == ["fastq_QC"]
    assert normalized["variantcalling"]["ram"] == "8g"


def test_resolve_pipeline_config_reconciles_legacy_database_names(tmp_path):
    pipelines = tmp_path / "pipelines"
    pipelines.mkdir()
    pipeline_path = pipelines / "legacy.pipeline"
    pipeline_path.write_text(
        json.dumps(
            {
                "workflow": ["preprocessing"],
                "reference_version": "hg19",
                "preprocessing": {
                    "workflow": ["BQ_recalibration"],
                    "threads": "2",
                    "ram": "4g",
                    "BQ_recalibration": {
                        "tool": "GATK v.3.7",
                        "GATK v.3.7": {"args": [], "dbsnp": "DBSNP v.138", "mills": "MILLS"},
                    },
                },
            }
        )
    )

    resolved = resolve_pipeline_config(
        "legacy.pipeline",
        pipelines,
        "BWA v.0.7.17",
        "preprocessing",
        ["preprocessing"],
        "preprocessing",
        ["BQ_recalibration"],
        [],
        [],
        {"dbsnp": {"path": "dbsnp.vcf"}, "mills": {"path": "mills.vcf"}},
    )

    tool_cfg = resolved["preprocessing"]["BQ_recalibration"]["GATK v.3.7"]
    assert tool_cfg["dbsnp"] == "dbsnp"
    assert tool_cfg["mills"] == "mills"


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
    assert "-resume" not in result["command"].split()
    assert popen_calls[0]["args"][0][0] == "/usr/bin/nextflow"
    assert popen_calls[0]["kwargs"]["cwd"] == str(tmp_path / "default_slice")


def test_real_analysis_resumes_existing_run_workdir(monkeypatch, tmp_path):
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

    run_dir = tmp_path / "resume_me"
    cached_task = run_dir / "work" / "aa" / "cached-task"
    cached_task.mkdir(parents=True)
    (cached_task / ".exitcode").write_text("0\n")

    popen_calls = []

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

    def fake_popen(*args, **kwargs):
        popen_calls.append({"args": args, "kwargs": kwargs})
        return FakeProcess()

    monkeypatch.setattr("helper_next.api.analysis.subprocess.Popen", fake_popen)

    result = real_run(
        FakeRunRequest(
            run_id="resume_me",
            samplesheet_content=samplesheet,
            workdir=str(tmp_path),
        )
    )

    assert result["resume"] is True
    assert "-resume" in result["command"].split()
    assert "-resume" in popen_calls[0]["args"][0]
    assert popen_calls[0]["kwargs"]["cwd"] == str(run_dir)
    assert "CWD={}".format(run_dir) in Path(result["command_file"]).read_text()
    assert "-resume" in Path(result["command_file"]).read_text().split()


def test_real_analysis_rejects_run_when_existing_pid_is_running(monkeypatch, tmp_path):
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

    run_dir = tmp_path / "already_running"
    run_dir.mkdir()
    (run_dir / "nextflow.pid").write_text("12345\n")

    monkeypatch.setattr("helper_next.api.analysis.shutil.which", lambda name: "/usr/bin/nextflow")
    monkeypatch.setattr("helper_next.api.analysis.is_pid_running", lambda pid: pid == 12345)
    monkeypatch.setattr(
        "helper_next.api.analysis.load_json",
        lambda path: {
            "hg19": {"fasta": "/refs/hg19.fa"},
            "BWA v.0.7.17": {"path": "bwa"},
            "PICARD v.2.7.1": {"path": "/tools/picard.jar"},
            "SAMTOOLS": {"path": "samtools"},
        },
    )

    with pytest.raises(HTTPException) as exc:
        real_run(
            FakeRunRequest(
                run_id="already_running",
                samplesheet_content=samplesheet,
                workdir=str(tmp_path),
            )
        )

    assert exc.value.status_code == 409
    assert "already running" in exc.value.detail


def test_real_analysis_reuses_previous_repo_cache_and_clears_stale_lock(monkeypatch, tmp_path):
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

    root = tmp_path / "repo"
    configs = root / "configs"
    pipelines = configs / "pipelines"
    configs.mkdir(parents=True)
    pipelines.mkdir(parents=True)
    run_dir = tmp_path / "resume_from_old_cache"
    cached_task = run_dir / "work" / "aa" / "cached-task"
    cached_task.mkdir(parents=True)
    (cached_task / ".exitcode").write_text("0\n")
    session_id = "0313fc95-27f3-4d5c-89ad-6f4230b641c5"
    (run_dir / "nextflow.log").write_text("Session UUID: {}\n".format(session_id))
    lock_path = root / ".nextflow" / "cache" / session_id / "db" / "LOCK"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text("")
    popen_calls = []

    monkeypatch.setattr("helper_next.api.analysis.shutil.which", lambda name: "/usr/bin/nextflow")
    monkeypatch.setattr(
        "helper_next.api.analysis.get_project_paths",
        lambda: ProjectPaths(root=root, configs=configs, pipelines=pipelines, files=root / "files", scripts=root / "scripts"),
    )
    monkeypatch.setattr(
        "helper_next.api.analysis.load_json",
        lambda path: {
            "hg19": {"fasta": "/refs/hg19.fa"},
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
            run_id="resume_from_old_cache",
            samplesheet_content=samplesheet,
            workdir=str(tmp_path),
        )
    )

    assert result["resume"] is True
    assert result["launch_dir"] == str(root)
    assert popen_calls[0]["kwargs"]["cwd"] == str(root)
    assert not lock_path.exists()


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


def test_real_analysis_enables_docker_profile_for_containerized_gatk3(monkeypatch, tmp_path):
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
            "GATK v.3.7": {
                "path": "/usr/GenomeAnalysisTK.jar",
                "container": {"engine": "docker", "image": "broadinstitute/gatk3:3.8-1"},
            },
            "SAMTOOLS": {"path": "samtools"},
            "dbsnp": {"path": "/refs/dbsnp.vcf"},
            "mills": {"path": "/refs/mills.vcf"},
        },
    )
    monkeypatch.setattr("helper_next.api.analysis.subprocess.Popen", lambda *args, **kwargs: FakeProcess())

    result = real_run(
        FakeRunRequest(
            run_id="preprocessing_gatk3_container",
            samplesheet_content=samplesheet,
            workdir=str(tmp_path),
            requested_preprocessing_workflow=["indel_realignment"],
        )
    )

    assert result["execution_profile"] == "local"
    assert result["nextflow_profile"] == "local,docker"
    assert "-profile local,docker" in result["command"]


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


def test_real_analysis_uses_selected_pipeline_file(monkeypatch, tmp_path):
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
    root = tmp_path / "repo"
    configs = root / "configs"
    pipelines = configs / "pipelines"
    tools_dir = configs / "tools_cfg"
    pipelines.mkdir(parents=True)
    tools_dir.mkdir(parents=True)
    (tools_dir / "tools.cfg").write_text(
        json.dumps(
            {
                "hg19": {"fasta": "/refs/hg19.fa"},
                "GATK v.4.1": {"path": "/custom/gatk"},
            }
        )
    )
    (pipelines / "custom.pipeline").write_text(
        json.dumps(
            {
                "analysis": "Custom",
                "reference_version": "hg19",
                "workflow": ["variantcalling"],
                "variantcalling": {
                    "tools": ["GATK v.4.1"],
                    "threads": "7",
                    "ram": "9g",
                    "filters": {},
                    "GATK v.4.1": {"args": ["--sample-ploidy", "2"]},
                },
            }
        )
    )

    class FakeProcess:
        pid = 12345

    monkeypatch.setattr("helper_next.api.analysis.shutil.which", lambda name: "/usr/bin/nextflow")
    monkeypatch.setattr(
        "helper_next.api.analysis.get_project_paths",
        lambda: ProjectPaths(root=root, configs=configs, pipelines=pipelines, files=root / "files", scripts=root / "scripts"),
    )
    monkeypatch.setattr("helper_next.api.analysis.subprocess.Popen", lambda *args, **kwargs: FakeProcess())

    result = real_run(
        FakeRunRequest(
            run_id="selected_pipeline",
            samplesheet_content=samplesheet,
            workdir=str(tmp_path),
            pipeline_path="custom.pipeline",
            requested_workflow=["variantcalling"],
        )
    )

    with open(Path(result["run_dir"]) / "alignment.pipeline.json") as handle:
        pipeline_config = json.load(handle)

    assert result["pipeline_path"] == "custom.pipeline"
    assert pipeline_config["analysis"] == "Custom"
    assert pipeline_config["variantcalling"]["threads"] == "7"
    assert pipeline_config["variantcalling"]["resolved"]["caller"]["path"] == "/custom/gatk"
    assert pipeline_config["variantcalling"]["resolved"]["caller"]["resolved_args"] == "--sample-ploidy 2"


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


def test_real_analysis_enables_docker_profile_for_containerized_vep(monkeypatch, tmp_path):
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
            "VEP v.95": {
                "path": "vep",
                "cache_dir": "/home/jarvis/.vep",
                "container": {"engine": "docker", "image": "ensemblorg/ensembl-vep:latest"},
            },
            "GeneSplicer": {"path": "/GeneSplicer/GeneSplicer/sources/genesplicer"},
            "MaxEntScan": {"path": "/MaxEntScan/fordownload"},
            "SpliceRegion": {"path": ""},
            "dbNSFP": {"path": "/dbSNFP/dbNSFP4.0/dbNSFP4.0a_hg19.gz"},
        },
    )
    monkeypatch.setattr("helper_next.api.analysis.subprocess.Popen", lambda *args, **kwargs: FakeProcess())

    result = real_run(
        FakeRunRequest(
            run_id="annotation_container",
            samplesheet_content=samplesheet,
            workdir=str(tmp_path),
            requested_annotation_workflow=["vep_annotation"],
        )
    )

    with open(Path(result["run_dir"]) / "alignment.pipeline.json") as handle:
        pipeline_config = json.load(handle)

    assert result["nextflow_profile"] == "local,docker"
    assert "-profile local,docker" in result["command"]
    assert pipeline_config["resolved_tools"]["annotation"]["vep_annotation"]["container"]["image"] == "ensemblorg/ensembl-vep:latest"


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
