import json
import os
import shutil
import subprocess
import csv
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from helper_next.core.nextflow import (
    ValidationError,
    build_nextflow_run_config,
    manifest_rows,
    validate_nextflow_inputs,
    write_manifest,
    write_run_config,
)
from helper_next.core.panels import PanelDesignError, get_panel_design
from helper_next.core.project import get_project_paths
from helper_next.core.tool_resolver import resolve_pipeline_tools
from helper_next.core.samplesheet import load_samplesheet_text


router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class FakeRunRequest(BaseModel):
    run_id: str
    samplesheet_content: str
    aligner: str = "BWA v.0.7.17"
    workdir: str = "/tmp/helper_next_analysis"
    gene_panel_design: str = ""
    tools_path: str = ""
    set_workdir_default: bool = False
    keep_intermediates: bool = False
    execution_profile: str = "local"
    queue: str = ""
    requested_workflow: List[str] = []
    requested_preprocessing_workflow: List[str] = []
    requested_postprocessing_workflow: List[str] = []
    requested_annotation_workflow: List[str] = []


SUPPORTED_ALIGNERS = ["BWA v.0.7.17", "BOWTIE2", "NOVOALIGN"]
SUPPORTED_EXECUTION_PROFILES = ["local", "slurm"]
TAIL_BYTES = 24000
JAVA_CANDIDATES = [
    Path("/usr/lib/jvm/java-21-openjdk-amd64"),
    Path("/usr/lib/jvm/openjdk-21"),
    Path("/usr/lib/jvm/java-17-openjdk-amd64"),
]


@router.post("/test-run")
def test_run(payload: FakeRunRequest):
    run_id = clean_run_id(payload.run_id)
    if not payload.samplesheet_content.strip():
        raise HTTPException(status_code=400, detail="Samplesheet content is required")
    if payload.aligner not in SUPPORTED_ALIGNERS:
        raise HTTPException(status_code=400, detail="Unsupported aligner: {}".format(payload.aligner))
    execution_profile = clean_execution_profile(payload.execution_profile)

    loaded = load_samplesheet_text(payload.samplesheet_content)
    samplesheet = loaded["samplesheet"]
    entry_step = loaded["step"]
    if entry_step not in ("prealignment", "alignment"):
        raise HTTPException(status_code=400, detail="Fake alignment requires a FASTQ samplesheet")
    pipeline_config = fake_alignment_pipeline(payload.aligner)
    tools_config = fake_tools_config(payload.aligner)

    try:
        validate_nextflow_inputs(samplesheet, pipeline_config, tools_config, entry_step=entry_step)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.errors)

    run_dir = Path(payload.workdir).expanduser() / run_id
    manifest_path = run_dir / "manifest.tsv"
    run_config_path = run_dir / "run_config.json"
    results = simulate_alignment_run(
        run_dir,
        run_id,
        payload.aligner,
        manifest_rows(samplesheet, entry_step),
        keep_intermediates=payload.keep_intermediates,
    )

    write_manifest(results["manifest_rows"], manifest_path)
    write_run_config(
        build_nextflow_run_config(samplesheet, pipeline_config, tools_config, entry_step=entry_step, requested_workflow="alignment"),
        run_config_path,
    )

    return {
        "status": "completed",
        "mode": "fake",
        "run_id": run_id,
        "aligner": payload.aligner,
        "gene_panel_design": payload.gene_panel_design.strip(),
        "tools_path": payload.tools_path.strip(),
        "set_workdir_default": payload.set_workdir_default,
        "keep_intermediates": payload.keep_intermediates,
        "execution_profile": execution_profile,
        "run_dir": str(run_dir),
        "manifest": str(manifest_path),
        "run_config": str(run_config_path),
        "nextflow_trace": results["nextflow_trace"],
        "workflow_plan": results["logs"]["workflow_plan"],
        "outputs": results["outputs"],
        "logs": results["logs"],
        "message": "Fake alignment workflow completed",
    }


@router.post("/real-run")
def real_run(payload: FakeRunRequest):
    run_id = clean_run_id(payload.run_id)
    if not payload.samplesheet_content.strip():
        raise HTTPException(status_code=400, detail="Samplesheet content is required")
    if payload.aligner not in SUPPORTED_ALIGNERS:
        raise HTTPException(status_code=400, detail="Unsupported aligner: {}".format(payload.aligner))
    execution_profile = clean_execution_profile(payload.execution_profile)

    nextflow_path = shutil.which("nextflow")
    if not nextflow_path:
        raise HTTPException(status_code=400, detail="Nextflow is not installed or not available in PATH")

    loaded = load_samplesheet_text(payload.samplesheet_content)
    samplesheet = loaded["samplesheet"]
    entry_step = loaded["step"]
    if entry_step not in ("prealignment", "alignment", "preprocessing", "variantcalling", "postprocessing", "annotation"):
        raise HTTPException(status_code=400, detail="Real Nextflow run requires a FASTQ, BAM, or VCF samplesheet")

    paths = get_project_paths()
    tools_path = resolve_tools_path(payload.tools_path, paths.configs)
    tools_config = load_json(tools_path)
    panel_design = resolve_panel_design(payload.gene_panel_design, paths.configs)
    requested_steps = [step for step in payload.requested_workflow if step]
    requested_preprocessing_workflow = clean_requested_preprocessing_workflow(payload.requested_preprocessing_workflow)
    requested_postprocessing_workflow = clean_requested_postprocessing_workflow(payload.requested_postprocessing_workflow)
    requested_annotation_workflow = clean_requested_annotation_workflow(payload.requested_annotation_workflow)
    pipeline_config = real_alignment_pipeline(
        payload.aligner,
        include_prealignment=entry_step == "prealignment",
        include_alignment=entry_step in ("prealignment", "alignment"),
        include_variantcalling=entry_step == "variantcalling" or "variantcalling" in requested_steps,
        include_postprocessing=entry_step == "postprocessing" or "postprocessing" in requested_steps,
        include_annotation=entry_step == "annotation" or "annotation" in requested_steps,
        preprocessing_workflow=requested_preprocessing_workflow,
        postprocessing_workflow=requested_postprocessing_workflow,
        annotation_workflow=requested_annotation_workflow,
    )
    pipeline_config = resolve_pipeline_tools(pipeline_config, tools_config, panel_design)
    requested_workflow = clean_requested_workflow(payload.requested_workflow, entry_step)
    validate_workflow_availability(entry_step, requested_workflow)

    try:
        validate_nextflow_inputs(samplesheet, pipeline_config, tools_config, entry_step=entry_step, requested_workflow=requested_workflow)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.errors)

    rows = manifest_rows(samplesheet, entry_step)
    run_dir = Path(payload.workdir).expanduser() / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    nextflow_work_dir = run_dir / "work"
    nextflow_work_dir.mkdir(parents=True, exist_ok=True)

    samplesheet_path = run_dir / "input.samplesheet.json"
    pipeline_path = run_dir / "alignment.pipeline.json"
    manifest_path = run_dir / "manifest.tsv"
    run_config_path = run_dir / "run_config.json"
    nextflow_log = run_dir / "nextflow.log"
    nextflow_trace = run_dir / "nextflow.trace.tsv"
    command_path = run_dir / "nextflow.command.txt"
    pid_path = run_dir / "nextflow.pid"

    write_json(samplesheet, samplesheet_path)
    write_json(pipeline_config, pipeline_path)
    write_manifest(rows, manifest_path)
    write_run_config(
        build_nextflow_run_config(
            samplesheet,
            pipeline_config,
            tools_config,
            entry_step=entry_step,
            requested_workflow=requested_workflow,
            panel_design=panel_design,
        ),
        run_config_path,
    )

    cmd = [
        nextflow_path,
        "run",
        str(paths.root / "workflows" / "nextflow" / "main.nf"),
        "-work-dir",
        str(nextflow_work_dir),
        "-c",
        str(paths.root / "workflows" / "nextflow" / "nextflow.config"),
        "-with-trace",
        str(nextflow_trace),
        "--manifest",
        str(manifest_path),
        "--pipeline",
        str(pipeline_path),
        "--tools",
        str(tools_path),
        "--run_config",
        str(run_config_path),
        "--outdir",
        str(run_dir / "results"),
        "--keep_intermediates",
        "true" if payload.keep_intermediates else "false",
        "-profile",
        execution_profile,
    ]
    if payload.queue.strip():
        cmd.extend(["--queue", payload.queue.strip()])

    env = nextflow_environment()
    command_path.write_text(
        "JAVA_HOME={}\nJAVA_CMD={}\n{}\n".format(
            env.get("JAVA_HOME", ""),
            env.get("JAVA_CMD", ""),
            " ".join(cmd),
        )
    )
    with nextflow_log.open("w") as log_handle:
        process = subprocess.Popen(
            cmd,
            cwd=str(paths.root),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
    pid_path.write_text(str(process.pid) + "\n")

    return {
        "status": "submitted",
        "mode": "real",
        "run_id": run_id,
        "aligner": payload.aligner,
        "gene_panel_design": payload.gene_panel_design.strip(),
        "panel_design": panel_design,
        "tools_path": str(tools_path),
        "set_workdir_default": payload.set_workdir_default,
        "keep_intermediates": payload.keep_intermediates,
        "execution_profile": execution_profile,
        "queue": payload.queue.strip(),
        "pid": process.pid,
        "run_dir": str(run_dir),
        "work_dir": str(nextflow_work_dir),
        "manifest": str(manifest_path),
        "run_config": str(run_config_path),
        "nextflow_log": str(nextflow_log),
        "nextflow_trace": str(nextflow_trace),
        "workflow_plan": str(run_dir / "results" / "LOGS" / "workflow.plan.tsv"),
        "command_file": str(command_path),
        "pid_file": str(pid_path),
        "command": " ".join(cmd),
        "message": "Real Nextflow workflow submitted",
    }


@router.get("/run-status")
def run_status(run_dir: str):
    run_path = Path(run_dir).expanduser()
    if not run_path.exists() or not run_path.is_dir():
        raise HTTPException(status_code=404, detail="Run directory not found")

    nextflow_log = run_path / "nextflow.log"
    nextflow_trace = run_path / "nextflow.trace.tsv"
    workflow_plan = run_path / "results" / "LOGS" / "workflow.plan.tsv"
    prealignment_step_log = run_path / "results" / "LOGS" / "PREALIGNMENT" / "prealignment.step.log"
    alignment_step_log = run_path / "results" / "LOGS" / "ALIGNMENT" / "alignment.step.log"
    preprocessing_step_log = run_path / "results" / "LOGS" / "PREPROCESSING" / "preprocessing.step.log"
    variantcalling_step_log = run_path / "results" / "LOGS" / "VARIANTCALLING" / "variantcalling.step.log"
    postprocessing_step_log = run_path / "results" / "LOGS" / "POSTPROCESSING" / "postprocessing.step.log"
    annotation_step_log = run_path / "results" / "LOGS" / "ANNOTATION" / "annotation.step.log"
    pid_path = run_path / "nextflow.pid"

    pid = read_pid(pid_path)
    log_text = tail_text(nextflow_log)
    trace_text = tail_text(nextflow_trace)
    plan_text = tail_text(workflow_plan)
    prealignment_summary = tail_text(prealignment_step_log)
    alignment_summary = tail_text(alignment_step_log)
    preprocessing_summary = tail_text(preprocessing_step_log)
    variantcalling_summary = tail_text(variantcalling_step_log)
    postprocessing_summary = tail_text(postprocessing_step_log)
    annotation_summary = tail_text(annotation_step_log)
    process_running = is_pid_running(pid)
    base_status = infer_run_status(pid, log_text, trace_text)
    workflow_matrix = build_workflow_matrix(run_path, process_running)
    status = reconcile_run_status(base_status, workflow_matrix, process_running)

    return {
        "status": status,
        "pid": pid,
        "running": status == "running",
        "run_dir": str(run_path),
        "files": {
            "nextflow_log": str(nextflow_log),
            "nextflow_trace": str(nextflow_trace),
            "workflow_plan": str(workflow_plan),
            "prealignment_step_log": str(prealignment_step_log),
            "alignment_step_log": str(alignment_step_log),
            "preprocessing_step_log": str(preprocessing_step_log),
            "variantcalling_step_log": str(variantcalling_step_log),
            "postprocessing_step_log": str(postprocessing_step_log),
            "annotation_step_log": str(annotation_step_log),
        },
        "content": {
            "workflow_matrix": workflow_matrix_text(workflow_matrix),
            "nextflow_log": log_text,
            "nextflow_trace": trace_text,
            "workflow_plan": plan_text,
            "prealignment_step_log": prealignment_summary,
            "alignment_step_log": alignment_summary,
            "preprocessing_step_log": preprocessing_summary,
            "variantcalling_step_log": variantcalling_summary,
            "postprocessing_step_log": postprocessing_summary,
            "annotation_step_log": annotation_summary,
        },
        "workflow_matrix": workflow_matrix,
    }


def clean_run_id(run_id):
    value = "".join(char if char.isalnum() or char in ("-", "_", ".") else "_" for char in run_id.strip())
    return value or "helper_test_run"


def clean_execution_profile(profile):
    value = (profile or "local").strip().lower()
    if value not in SUPPORTED_EXECUTION_PROFILES:
        raise HTTPException(status_code=400, detail="Unsupported execution profile: {}".format(profile))
    return value


def resolve_tools_path(selected_path, configs_dir):
    default_path = configs_dir / "tools_cfg" / "tools.cfg"
    selected = (selected_path or "").strip()
    if not selected:
        return default_path

    candidate = Path(selected).expanduser()
    if not candidate.is_absolute():
        candidate = configs_dir / selected
    candidate = candidate.resolve()
    configs_root = configs_dir.resolve()

    try:
        candidate.relative_to(configs_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Tools file must be inside {}".format(configs_root))
    if not candidate.is_file():
        raise HTTPException(status_code=400, detail="Tools file not found: {}".format(selected))
    return candidate


def resolve_panel_design(selected_design, configs_dir):
    selected = (selected_design or "").strip()
    if not selected:
        return None
    try:
        return get_panel_design(configs_dir, selected)
    except PanelDesignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def clean_requested_workflow(requested_workflow, entry_step):
    defaults = {
        "prealignment": ["prealignment", "alignment", "preprocessing"],
        "alignment": ["alignment", "preprocessing"],
        "preprocessing": ["preprocessing"],
        "variantcalling": ["variantcalling"],
        "postprocessing": ["postprocessing"],
        "annotation": ["annotation"],
    }
    allowed = ["prealignment", "alignment", "preprocessing", "variantcalling", "postprocessing", "annotation"]
    selected = [step for step in requested_workflow if step in allowed]
    if not selected:
        selected = defaults.get(entry_step, ["alignment", "preprocessing"])
    return ",".join(selected)


def clean_requested_preprocessing_workflow(requested_workflow):
    allowed = ["filter_bam", "merge_UMI", "add_readgroups", "mark_pcr_dup", "indel_realignment", "BQ_recalibration"]
    implemented = {"add_readgroups", "mark_pcr_dup", "indel_realignment", "BQ_recalibration"}
    selected = [step for step in requested_workflow if step in allowed and step in implemented]
    return selected or ["add_readgroups", "mark_pcr_dup"]


def clean_requested_postprocessing_workflow(requested_workflow):
    allowed = ["vcf_norm", "vcf_filter", "vcf_to_tsv"]
    selected = [step for step in requested_workflow if step in allowed]
    return selected or ["vcf_to_tsv"]


def clean_requested_annotation_workflow(requested_workflow):
    allowed = ["vep_annotation", "ann_vcf_to_tsv"]
    selected = [step for step in requested_workflow if step in allowed]
    return selected or ["vep_annotation", "ann_vcf_to_tsv"]


def validate_workflow_availability(entry_step, requested_workflow):
    selected = [step.strip() for step in requested_workflow.split(",") if step.strip()]
    available = {
        "prealignment": {"fastq"},
        "alignment": {"fastq"},
        "preprocessing": {"bam"},
        "variantcalling": {"bam"},
        "postprocessing": {"vcf"},
        "annotation": {"vcf"},
    }.get(entry_step, set())
    step_inputs = {
        "prealignment": {"fastq"},
        "alignment": {"fastq"},
        "preprocessing": {"bam"},
        "variantcalling": {"bam"},
        "postprocessing": {"vcf"},
        "annotation": {"vcf"},
    }
    step_outputs = {
        "prealignment": {"fastq"},
        "alignment": {"bam"},
        "preprocessing": {"bam"},
        "variantcalling": {"vcf"},
        "postprocessing": {"vcf", "tsv"},
        "annotation": {"vcf", "tsv"},
    }

    for step in ["prealignment", "alignment", "preprocessing", "variantcalling", "postprocessing", "annotation"]:
        if step not in selected:
            continue
        required = step_inputs[step]
        if not (required & available):
            raise HTTPException(
                status_code=400,
                detail="{} requires {} input from the samplesheet or a previous selected step".format(
                    step,
                    "/".join(sorted(required)),
                ),
            )
        available.update(step_outputs[step])


def read_pid(path):
    if not path.exists():
        return None
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def is_pid_running(pid):
    if not pid:
        return False
    proc_status = Path("/proc") / str(pid) / "status"
    if proc_status.exists():
        try:
            for line in proc_status.read_text().splitlines():
                if line.startswith("State:") and "\tZ" in line:
                    return False
        except OSError:
            pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def nextflow_environment():
    env = os.environ.copy()
    java_home = compatible_java_home()
    if java_home:
        env["JAVA_HOME"] = str(java_home)
        env["JAVA_CMD"] = str(java_home / "bin" / "java")
        env["PATH"] = "{}{}{}".format(java_home / "bin", os.pathsep, env.get("PATH", ""))
    else:
        env.pop("JAVA_HOME", None)
        env.pop("JAVA_CMD", None)
    return env


def compatible_java_home():
    for path in JAVA_CANDIDATES:
        if (path / "bin" / "java").exists():
            return path
    return None


def infer_run_status(pid, log_text, trace_text):
    if "ERROR ~" in log_text or "\tFAILED\t" in trace_text or "\tABORTED\t" in trace_text:
        return "failed"
    if is_pid_running(pid):
        return "running"
    if "Completed at:" in log_text:
        return "completed"
    if log_text or trace_text:
        return "finished"
    return "created"


def reconcile_run_status(base_status, workflow_matrix, process_running=False):
    counts = {"total": 0, "running": 0, "completed": 0, "failed": 0, "planned": 0}
    for step in workflow_matrix:
        step_counts = step.get("counts", {})
        for key in counts:
            counts[key] += step_counts.get(key, 0)

    if counts["running"] > 0:
        return "running"
    if process_running and counts["planned"] > 0:
        return "running"
    if counts["failed"] > 0 and counts["running"] == 0:
        return "failed"
    if counts["total"] > 0 and counts["completed"] == counts["total"]:
        return "completed"
    return base_status


def tail_text(path, limit=TAIL_BYTES):
    if not path.exists():
        return ""
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > limit:
                handle.seek(size - limit)
            data = handle.read()
    except OSError:
        return ""
    text = data.decode("utf-8", errors="replace")
    if size > limit:
        first_newline = text.find("\n")
        if first_newline >= 0:
            text = text[first_newline + 1 :]
        text = "[tail: last {} bytes]\n{}".format(limit, text)
    return text


def build_workflow_matrix(run_path, is_running):
    samples = read_manifest_samples(run_path / "manifest.tsv")
    workflow = read_run_workflow(run_path / "run_config.json") or ["alignment"]
    matrix = []
    previous_complete = True

    for step in workflow:
        if step not in ("prealignment", "alignment", "preprocessing", "variantcalling", "postprocessing", "annotation"):
            continue
        statuses = read_step_statuses(run_path / "results" / "LOGS" / step.upper() / "samples", step)
        step_active = is_running and previous_complete
        sample_rows = []

        for sample in samples:
            key = (sample["sample_id"], sample["role"], sample["sample_name"])
            status = statuses.get(key, {})
            state = status.get("status")
            if not state:
                state = "running" if step_active else "planned"
            sample_rows.append(
                {
                    "sample_id": sample["sample_id"],
                    "role": sample["role"],
                    "sample_name": sample["sample_name"],
                    "status": state,
                    "exit_code": status.get("exit_code", ""),
                    "started": status.get("started", ""),
                    "completed": status.get("completed", ""),
                }
            )

        counts = {
            "planned": sum(1 for row in sample_rows if row["status"] == "planned"),
            "running": sum(1 for row in sample_rows if row["status"] == "running"),
            "completed": sum(1 for row in sample_rows if row["status"] == "completed"),
            "failed": sum(1 for row in sample_rows if row["status"] == "failed"),
            "total": len(sample_rows),
        }
        matrix.append({"step": step, "counts": counts, "samples": sample_rows})
        previous_complete = counts["total"] > 0 and counts["completed"] == counts["total"]

    return matrix


def read_manifest_samples(path):
    if not path.exists():
        return []
    try:
        with path.open() as handle:
            return [
                {
                    "sample_id": row.get("sample_id", ""),
                    "role": row.get("role", ""),
                    "sample_name": row.get("sample_name", ""),
                    "merged_vcf": row.get("merged_vcf", ""),
                }
                for row in csv.DictReader(handle, delimiter="\t")
            ]
    except OSError:
        return []


def read_run_workflow(path):
    if not path.exists():
        return []
    try:
        with path.open() as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    workflow = data.get("workflow", [])
    return workflow if isinstance(workflow, list) else []


def read_step_statuses(sample_log_dir, step):
    statuses = {}
    if not sample_log_dir.exists():
        return statuses
    for path in sorted(sample_log_dir.glob("*.{}.status.tsv".format(step))):
        try:
            with path.open() as handle:
                rows = list(csv.DictReader(handle, delimiter="\t"))
        except OSError:
            continue
        for row in rows:
            key = (row.get("sample_id", ""), row.get("role", ""), row.get("sample_name", ""))
            statuses[key] = row
    return statuses


def workflow_matrix_text(matrix):
    if not matrix:
        return "[waiting for manifest]"
    lines = []
    for step in matrix:
        counts = step["counts"]
        lines.append(
            "{step}: total={total} running={running} completed={completed} failed={failed} planned={planned}".format(
                step=step["step"],
                **counts,
            )
        )
        for sample in step["samples"]:
            details = "{sample_id}\t{role}\t{sample_name}\t{status}".format(**sample)
            if sample.get("exit_code"):
                details += "\texit={}".format(sample["exit_code"])
            lines.append("  " + details)
    return "\n".join(lines)


def fake_alignment_pipeline(aligner):
    tool_config = {"args": []}
    if aligner.upper().startswith("BWA"):
        tool_config["algorithm"] = "mem"
    return {
        "id": "fake_alignment",
        "analysis": "Test",
        "reference_version": "fake_reference",
        "workflow": ["alignment"],
        "alignment": {
            "workflow": ["fastq_alignment"],
            "threads": "2",
            "ram": "1g",
            "fastq_alignment": {
                "tool": aligner,
                aligner: tool_config,
            },
        },
    }


def real_alignment_pipeline(
    aligner,
    include_prealignment=False,
    include_alignment=True,
    include_variantcalling=False,
    include_postprocessing=False,
    include_annotation=False,
    preprocessing_workflow=None,
    postprocessing_workflow=None,
    annotation_workflow=None,
):
    pipeline = fake_alignment_pipeline(aligner)
    pipeline["id"] = "real_alignment"
    pipeline["analysis"] = "Germline"
    pipeline["reference_version"] = "hg19"
    pipeline["workflow"] = []
    if include_prealignment:
        pipeline["workflow"].append("prealignment")
        pipeline["prealignment"] = {
            "workflow": ["fastq_QC"],
            "threads": "1",
            "ram": "1g",
            "fastq_QC": {
                "tool": "FASTQC v.0.11.8",
                "FASTQC v.0.11.8": {"args": []},
            },
        }
    if include_alignment:
        pipeline["workflow"].append("alignment")
    pipeline["workflow"].append("preprocessing")
    preprocessing_workflow = preprocessing_workflow or ["add_readgroups", "mark_pcr_dup"]
    pipeline["preprocessing"] = {
        "workflow": preprocessing_workflow,
        "threads": "2",
        "ram": "8g",
        "add_readgroups": {
            "tool": "PICARD v.2.7.1",
            "PICARD v.2.7.1": {"args": []},
        },
        "mark_pcr_dup": {
            "tool": "PICARD v.2.7.1",
            "PICARD v.2.7.1": {"args": []},
        },
        "indel_realignment": {
            "tool": "GATK v.3.7",
            "GATK v.3.7": {"args": [], "mills": "mills"},
        },
        "BQ_recalibration": {
            "tool": "GATK v.3.7",
            "GATK v.3.7": {"args": [], "dbsnp": "dbsnp", "mills": "mills"},
        },
    }
    if include_variantcalling:
        pipeline["workflow"].append("variantcalling")
        pipeline["variantcalling"] = {
            "tools": ["GATK v.4.1"],
            "threads": "2",
            "ram": "8g",
            "filters": {
                "min_base_quality_score": "",
                "min_alt_coverage": "",
                "min_alt_freq": "",
                "min_mapping_quality_score": "",
            },
            "GATK v.4.1": {"args": []},
            "samples_org": "single-sample",
        }
    if include_postprocessing:
        postprocessing_workflow = postprocessing_workflow or ["vcf_to_tsv"]
        pipeline["workflow"].append("postprocessing")
        pipeline["postprocessing"] = {
            "workflow": postprocessing_workflow,
            "threads": "2",
            "ram": "2g",
            "vcf_norm": {"tool": "BCFTOOLS", "BCFTOOLS": {"args": []}},
            "vcf_filter": {"tool": "", "GATK v.4.1": {"args": []}},
            "vcf_to_tsv": {"tool": "", "args": {"tags_file": "", "format_tags": "", "info_tags": ""}},
        }
    if include_annotation:
        annotation_workflow = annotation_workflow or ["vep_annotation", "ann_vcf_to_tsv"]
        pipeline["workflow"].append("annotation")
        pipeline["annotation"] = {
            "workflow": annotation_workflow,
            "threads": "2",
            "ram": "4g",
            "vep_annotation": {
                "tool": "VEP v.95",
                "VEP v.95": {
                    "args": default_vep_args(),
                },
            },
            "ann_vcf_to_tsv": {"tool": "", "args": {"tags_file": "", "format_tags": "", "info_tags": ""}},
        }
    return pipeline


def default_vep_args():
    return {
        "args": [
            "--vcf_info_field",
            "ANN",
            "--force_overwrite",
            "--no_stats",
            "--cache",
            "--offline",
            "--merged",
            "--use_given_ref",
            "--canonical",
        ],
        "features": [
            "--sift",
            "b",
            "--polyphen",
            "b",
            "--numbers",
            "--hgvs",
            "--transcript_version",
            "--symbol",
            "--check_existing",
        ],
        "af": ["--af", "--max_af", "--af_1kg", "--af_esp", "--af_gnomad"],
        "assembly": "GRCh37",
        "species": "homo_sapiens",
        "plugins": {
            "list": ["GeneSplicer", "MaxEntScan", "SpliceRegion", "dbNSFP"],
            "GeneSplicer": {"files": "", "fields": "/home/jarvis/.vep/Plugins/GeneSplicer/GeneSplicer/human"},
            "MaxEntScan": {"files": "", "fields": "/home/jarvis/.vep/Plugins/GeneSplicer/GeneSplicer/human"},
            "SpliceRegion": {"files": "", "fields": ""},
            "dbNSFP": {"files": "", "fields": ""},
        },
    }


def fake_tools_config(aligner):
    return {
        "fake_reference": {
            "fasta": "/tmp/helper_next_fake_reference.fa",
            "version": "fake",
            "tags": "reference",
        },
        aligner: {
            "path": aligner.lower().replace(" ", "_"),
            "version": "fake",
            "tags": "fastq_alignment",
        },
        "SAMTOOLS": {
            "path": "samtools",
            "version": "fake",
            "tags": "",
        },
    }


def load_json(path):
    with open(str(path)) as handle:
        return json.load(handle)


def write_json(data, path):
    with Path(path).open("w") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def simulate_alignment_run(run_dir, run_id, aligner, rows, keep_intermediates=False):
    alignment_dir = run_dir / "results" / "ALIGNMENT"
    intermediates_dir = alignment_dir / "intermediates"
    sample_log_dir = run_dir / "results" / "LOGS" / "ALIGNMENT" / "samples"
    step_log_dir = run_dir / "results" / "LOGS" / "ALIGNMENT"
    root_log_dir = run_dir / "results" / "LOGS"
    alignment_dir.mkdir(parents=True, exist_ok=True)
    if keep_intermediates:
        intermediates_dir.mkdir(parents=True, exist_ok=True)
    sample_log_dir.mkdir(parents=True, exist_ok=True)
    step_log_dir.mkdir(parents=True, exist_ok=True)

    outputs = []
    sample_logs = []

    for row in rows:
        sample_name = row["sample_name"]
        bam = alignment_dir / "{}.sort.bam".format(sample_name)
        bai = alignment_dir / "{}.sort.bam.bai".format(sample_name)
        sample_log = sample_log_dir / "{}.alignment.log".format(sample_name)
        sample_status = sample_log_dir / "{}.alignment.status.tsv".format(sample_name)
        intermediate_sam = intermediates_dir / "{}.sam".format(sample_name)
        intermediate_bam = intermediates_dir / "{}.unsorted.bam".format(sample_name)

        bam.write_text("fake BAM placeholder for {} {}\n".format(run_id, sample_name))
        bai.write_text("fake BAI placeholder for {} {}\n".format(run_id, sample_name))
        if keep_intermediates:
            intermediate_sam.write_text("fake SAM placeholder for {} {}\n".format(run_id, sample_name))
            intermediate_bam.write_text("fake unsorted BAM placeholder for {} {}\n".format(run_id, sample_name))
        sample_log.write_text(sample_log_text(run_id, aligner, row, bam, bai, keep_intermediates))
        sample_status.write_text(
            "step\ttool\tsample_id\trole\tsample_name\tstatus\texit_code\tstarted\tcompleted\n"
            "alignment\t{tool}\t{sample_id}\t{role}\t{sample_name}\tcompleted\t0\tfake\tfake\n".format(
                tool=aligner,
                sample_id=row.get("sample_id", ""),
                role=row.get("role", ""),
                sample_name=sample_name,
            )
        )

        outputs.append({"sample_name": sample_name, "bam": str(bam), "bai": str(bai)})
        if keep_intermediates:
            outputs[-1]["sam"] = str(intermediate_sam)
            outputs[-1]["unsorted_bam"] = str(intermediate_bam)
        sample_logs.append(sample_log)

    step_log = step_log_dir / "alignment.step.log"
    workflow_plan = root_log_dir / "workflow.plan.tsv"
    nextflow_trace = run_dir / "nextflow.trace.tsv"
    with step_log.open("w") as handle:
        handle.write("step=alignment\n")
        handle.write("mode=fake\n")
        handle.write("run_id={}\n".format(run_id))
        handle.write("keep_intermediates={}\n".format(str(keep_intermediates).lower()))
        handle.write("sample_log_count={}\n\n".format(len(sample_logs)))
        for sample_log in sample_logs:
            handle.write("===== {} =====\n".format(sample_log.name))
            handle.write(sample_log.read_text())
            handle.write("\n")

    with workflow_plan.open("w") as handle:
        handle.write("order\tstep\tstatus\toutput_dir\tlog_dir\n")
        handle.write("1\talignment\tplanned\t{}\t{}\n".format(alignment_dir, step_log_dir))

    with nextflow_trace.open("w") as handle:
        handle.write("task_id\tprocess\ttag\tstatus\texit\n")
        for index, row in enumerate(rows, start=1):
            handle.write("{}\tALIGNMENT:FAKE_ALIGN\t{}\tCOMPLETED\t0\n".format(index, row["sample_name"]))

    return {
        "manifest_rows": rows,
        "outputs": outputs,
        "logs": {
            "step": str(step_log),
            "workflow_plan": str(workflow_plan),
            "samples": [str(path) for path in sample_logs],
        },
        "nextflow_trace": str(nextflow_trace),
    }


def sample_log_text(run_id, aligner, row, bam, bai, keep_intermediates=False):
    command = fake_command(aligner, row)
    return "\n".join(
        [
            "step=alignment",
            "mode=fake",
            "run_id={}".format(run_id),
            "tool={}".format(aligner),
            "sample_id={}".format(row.get("sample_id", "")),
            "role={}".format(row.get("role", "")),
            "sample_name={}".format(row.get("sample_name", "")),
            "fastq_r1={}".format(row.get("fastq_r1", "")),
            "fastq_r2={}".format(row.get("fastq_r2", "")),
            "keep_intermediates={}".format(str(keep_intermediates).lower()),
            "command={}".format(command),
            "output_bam={}".format(bam),
            "output_bai={}".format(bai),
            "completed=true",
            "",
        ]
    )


def fake_command(aligner, row):
    if aligner.upper().startswith("BOWTIE2"):
        return "bowtie2 -x fake_reference -1 {fastq_r1} -2 {fastq_r2} | samtools sort".format(**row)
    if aligner.upper().startswith("NOVOALIGN"):
        return "novoalign -d fake_reference -f {fastq_r1} {fastq_r2} | samtools sort".format(**row)
    return "bwa mem fake_reference {fastq_r1} {fastq_r2} | samtools sort".format(**row)
