import json
import os
import re
import signal
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
    mode: str = ""
    aligner: str = "BWA v.0.7.17"
    workdir: str = "/tmp/helper_next_analysis"
    pipeline_path: str = ""
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


class StopRunRequest(BaseModel):
    run_dir: str


SUPPORTED_ALIGNERS = ["BWA v.0.7.17", "BOWTIE2", "NOVOALIGN"]
SUPPORTED_EXECUTION_PROFILES = ["local", "slurm"]
TAIL_BYTES = 24000
JAVA_CANDIDATES = [
    Path("/usr/lib/jvm/java-21-openjdk-amd64"),
    Path("/usr/lib/jvm/openjdk-21"),
    Path("/usr/lib/jvm/java-17-openjdk-amd64"),
]
GATK_JAVA_CANDIDATES = [
    Path("/usr/lib/jvm/java-8-openjdk-amd64"),
    Path("/usr/lib/jvm/java-1.8.0-openjdk-amd64"),
    Path("/usr/lib/jvm/java-11-openjdk-amd64"),
    Path("/usr/lib/jvm/java-1.11.0-openjdk-amd64"),
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


@router.post("/validate-run")
def validate_run(payload: FakeRunRequest):
    validation = validate_analysis_payload(payload)
    return {
        "status": "ok",
        "run_id": validation["run_id"],
        "entry_step": validation["entry_step"],
        "workflow": validation["workflow"],
        "checked_files": validation["checked_files"],
        "workdir": validation["workdir"],
        "message": "Analysis setup is valid",
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
    requested_workflow = clean_requested_workflow(payload.requested_workflow, entry_step)
    pipeline_config = resolve_pipeline_config(
        payload.pipeline_path,
        paths.pipelines,
        payload.aligner,
        entry_step,
        requested_steps,
        requested_workflow,
        requested_preprocessing_workflow,
        requested_postprocessing_workflow,
        requested_annotation_workflow,
        tools_config,
    )
    pipeline_config = resolve_pipeline_tools(pipeline_config, tools_config, panel_design)
    validate_workflow_availability(entry_step, requested_workflow)
    nextflow_profile = container_aware_execution_profile(execution_profile, pipeline_config)

    try:
        validate_nextflow_inputs(samplesheet, pipeline_config, tools_config, entry_step=entry_step, requested_workflow=requested_workflow)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.errors)

    rows = manifest_rows(samplesheet, entry_step)
    run_dir = Path(payload.workdir).expanduser() / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    nextflow_work_dir = run_dir / "work"
    resume_run = nextflow_work_dir.exists() and any(nextflow_work_dir.iterdir())
    nextflow_work_dir.mkdir(parents=True, exist_ok=True)

    samplesheet_path = run_dir / "input.samplesheet.json"
    pipeline_path = run_dir / "alignment.pipeline.json"
    manifest_path = run_dir / "manifest.tsv"
    run_config_path = run_dir / "run_config.json"
    nextflow_log = run_dir / "nextflow.log"
    nextflow_trace = run_dir / "nextflow.trace.tsv"
    command_path = run_dir / "nextflow.command.txt"
    pid_path = run_dir / "nextflow.pid"
    previous_session_ids = nextflow_session_ids(nextflow_log)
    existing_pid = read_pid(pid_path)
    if existing_pid and is_pid_running(existing_pid):
        raise HTTPException(status_code=409, detail="Run is already running with PID {}".format(existing_pid))

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
        nextflow_profile,
    ]
    if resume_run:
        cmd.append("-resume")
    if payload.queue.strip():
        cmd.extend(["--queue", payload.queue.strip()])

    env = nextflow_environment()
    launch_dir = nextflow_launch_dir(run_dir, command_path, paths.root, previous_session_ids)
    if resume_run:
        remove_stale_nextflow_locks(launch_dir, previous_session_ids)
    command_path.write_text(
        "CWD={}\nJAVA_HOME={}\nJAVA_CMD={}\n{}\n".format(
            launch_dir,
            env.get("JAVA_HOME", ""),
            env.get("JAVA_CMD", ""),
            " ".join(cmd),
        )
    )
    with nextflow_log.open("w") as log_handle:
        process = subprocess.Popen(
            cmd,
            cwd=str(launch_dir),
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
        "pipeline_path": payload.pipeline_path,
        "set_workdir_default": payload.set_workdir_default,
        "keep_intermediates": payload.keep_intermediates,
        "execution_profile": execution_profile,
        "nextflow_profile": nextflow_profile,
        "queue": payload.queue.strip(),
        "resume": resume_run,
        "pid": process.pid,
        "run_dir": str(run_dir),
        "work_dir": str(nextflow_work_dir),
        "launch_dir": str(launch_dir),
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


@router.get("/pipeline-config")
def pipeline_config(path: str):
    paths = get_project_paths()
    pipeline_path = resolve_pipeline_path(path, paths.pipelines)
    config = normalize_pipeline_for_nextflow(load_json(pipeline_path))
    return {"path": str(pipeline_path), "name": pipeline_path.name, "config": config}


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


@router.post("/stop-run")
def stop_run(payload: StopRunRequest):
    run_path = Path(payload.run_dir).expanduser()
    if not run_path.exists() or not run_path.is_dir():
        raise HTTPException(status_code=404, detail="Run directory not found")

    pid_path = run_path / "nextflow.pid"
    pid = read_pid(pid_path)
    if not pid:
        raise HTTPException(status_code=400, detail="Run PID not found")
    if not is_pid_running(pid):
        return {"status": "not_running", "pid": pid, "run_dir": str(run_path), "message": "Analysis is not running"}

    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return {"status": "not_running", "pid": pid, "run_dir": str(run_path), "message": "Analysis is not running"}
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied while stopping analysis")
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return {"status": "not_running", "pid": pid, "run_dir": str(run_path), "message": "Analysis is not running"}
        except PermissionError:
            raise HTTPException(status_code=403, detail="Permission denied while stopping analysis")

    stop_marker = run_path / "analysis.stop.requested"
    try:
        stop_marker.write_text("pid={}\nrequested=SIGTERM\n".format(pid))
    except OSError:
        pass
    return {"status": "stopping", "pid": pid, "run_dir": str(run_path), "message": "Stop requested"}


def clean_run_id(run_id):
    value = "".join(char if char.isalnum() or char in ("-", "_", ".") else "_" for char in run_id.strip())
    return value or "helper_test_run"


def clean_execution_profile(profile):
    value = (profile or "local").strip().lower()
    if value not in SUPPORTED_EXECUTION_PROFILES:
        raise HTTPException(status_code=400, detail="Unsupported execution profile: {}".format(profile))
    return value


def nextflow_launch_dir(run_dir, command_path, project_root, session_ids):
    recorded = recorded_nextflow_launch_dir(command_path)
    if recorded:
        return recorded
    if session_ids and any(nextflow_lock_path(project_root, session_id).exists() for session_id in session_ids):
        return project_root
    return run_dir


def recorded_nextflow_launch_dir(command_path):
    if not command_path.is_file():
        return None
    try:
        for line in command_path.read_text(errors="replace").splitlines():
            if line.startswith("CWD="):
                value = line.removeprefix("CWD=").strip()
                if value:
                    return Path(value).expanduser()
    except OSError:
        return None
    return None


def nextflow_session_ids(log_path):
    if not log_path.is_file():
        return []
    try:
        text = log_path.read_text(errors="replace")
    except OSError:
        return []
    patterns = [
        r"Session UUID:\s*([0-9a-fA-F-]{36})",
        r"session with ID\s+([0-9a-fA-F-]{36})",
        r"\.nextflow/cache/([0-9a-fA-F-]{36})/db/LOCK",
    ]
    session_ids = []
    seen = set()
    for pattern in patterns:
        for match in re.findall(pattern, text):
            session_id = match.lower()
            if session_id not in seen:
                seen.add(session_id)
                session_ids.append(session_id)
    return session_ids


def remove_stale_nextflow_locks(launch_dir, session_ids):
    for session_id in session_ids:
        lock_path = nextflow_lock_path(launch_dir, session_id)
        try:
            if lock_path.is_file():
                lock_path.unlink()
        except OSError:
            pass


def nextflow_lock_path(launch_dir, session_id):
    return Path(launch_dir) / ".nextflow" / "cache" / session_id / "db" / "LOCK"


def validate_analysis_payload(payload):
    errors = []
    mode = (payload.mode or "real_alignment").strip()
    run_id = clean_run_id(payload.run_id)
    if not payload.run_id.strip():
        errors.append("Run ID is required")
    if not payload.samplesheet_content.strip():
        errors.append("Samplesheet content is required")
    if not payload.gene_panel_design.strip():
        errors.append("Gene panel/design is required")
    if not payload.pipeline_path.strip():
        errors.append("Pipeline config is required")

    execution_profile = ""
    try:
        execution_profile = clean_execution_profile(payload.execution_profile)
    except HTTPException as exc:
        append_detail(errors, exc.detail)

    loaded = None
    samplesheet = None
    entry_step = ""
    if payload.samplesheet_content.strip():
        try:
            loaded = load_samplesheet_text(payload.samplesheet_content)
            samplesheet = loaded["samplesheet"]
            entry_step = loaded["step"]
        except Exception as exc:
            errors.append("Samplesheet is not valid: {}".format(exc))

    if samplesheet is not None:
        try:
            validate_samplesheet_file_access(samplesheet, entry_step)
        except ValidationError as exc:
            errors.extend(exc.errors)

    try:
        validate_workdir_path(payload.workdir)
    except HTTPException as exc:
        append_detail(errors, exc.detail)

    workflow = ""
    checked_files = 0
    if samplesheet is not None:
        try:
            checked_files = len(sample_file_paths(samplesheet, entry_step))
            if mode == "fake_alignment":
                if entry_step not in ("prealignment", "alignment"):
                    errors.append("Fake alignment requires a FASTQ samplesheet")
                pipeline_config = fake_alignment_pipeline(payload.aligner)
                tools_config = fake_tools_config(payload.aligner)
                workflow = "alignment"
            else:
                if shutil.which("nextflow") is None:
                    errors.append("Nextflow is not installed or not available in PATH")
                if entry_step not in ("prealignment", "alignment", "preprocessing", "variantcalling", "postprocessing", "annotation"):
                    errors.append("Real Nextflow run requires a FASTQ, BAM, or VCF samplesheet")
                paths = get_project_paths()
                tools_path = resolve_tools_path(payload.tools_path, paths.configs)
                tools_config = load_json(tools_path)
                panel_design = resolve_panel_design(payload.gene_panel_design, paths.configs)
                requested_steps = [step for step in payload.requested_workflow if step]
                requested_preprocessing_workflow = clean_requested_preprocessing_workflow(payload.requested_preprocessing_workflow)
                requested_postprocessing_workflow = clean_requested_postprocessing_workflow(payload.requested_postprocessing_workflow)
                requested_annotation_workflow = clean_requested_annotation_workflow(payload.requested_annotation_workflow)
                workflow = clean_requested_workflow(payload.requested_workflow, entry_step)
                pipeline_config = resolve_pipeline_config(
                    payload.pipeline_path,
                    paths.pipelines,
                    payload.aligner,
                    entry_step,
                    requested_steps,
                    workflow,
                    requested_preprocessing_workflow,
                    requested_postprocessing_workflow,
                    requested_annotation_workflow,
                    tools_config,
                )
                pipeline_config = resolve_pipeline_tools(pipeline_config, tools_config, panel_design)
                validate_workflow_availability(entry_step, workflow)
                container_aware_execution_profile(execution_profile, pipeline_config)
            validate_nextflow_inputs(samplesheet, pipeline_config, tools_config, entry_step=entry_step, requested_workflow=workflow)
        except ValidationError as exc:
            errors.extend(exc.errors)
        except HTTPException as exc:
            append_detail(errors, exc.detail)
        except Exception as exc:
            errors.append(str(exc))

    if errors:
        raise HTTPException(status_code=400, detail=errors)

    return {
        "run_id": run_id,
        "entry_step": entry_step,
        "workflow": workflow,
        "checked_files": checked_files,
        "workdir": str(Path(payload.workdir).expanduser()),
    }


def append_detail(errors, detail):
    if isinstance(detail, list):
        errors.extend(str(item) for item in detail)
    else:
        errors.append(str(detail))


def validate_samplesheet_file_access(samplesheet, entry_step):
    errors = []
    for path in sample_file_paths(samplesheet, entry_step):
        candidate = Path(path).expanduser()
        if not candidate.exists():
            errors.append("samplesheet file not found: {}".format(path))
        elif not candidate.is_file():
            errors.append("samplesheet path is not a file: {}".format(path))
        elif not os.access(str(candidate), os.R_OK):
            errors.append("samplesheet file is not readable: {}".format(path))
    if errors:
        raise ValidationError(errors)


def sample_file_paths(samplesheet, entry_step):
    rows = manifest_rows(samplesheet, entry_step)
    file_columns = [
        "fastq_r1",
        "fastq_r2",
        "fastq_i2",
        "bam",
        "merged_vcf",
        "variants_tsv",
    ]
    paths = []
    seen = set()
    for row in rows:
        for column in file_columns:
            value = str(row.get(column) or "").strip()
            if value and value not in seen:
                seen.add(value)
                paths.append(value)
    return paths


def validate_workdir_path(workdir):
    selected = (workdir or "").strip()
    if not selected:
        raise HTTPException(status_code=400, detail="Working directory is required")
    candidate = Path(selected).expanduser()
    target = candidate if candidate.exists() else candidate.parent
    if candidate.exists() and not candidate.is_dir():
        raise HTTPException(status_code=400, detail="Working directory is not a directory: {}".format(selected))
    if not target.exists():
        raise HTTPException(status_code=400, detail="Working directory parent does not exist: {}".format(target))
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Working directory parent is not a directory: {}".format(target))
    if not os.access(str(target), os.W_OK | os.X_OK):
        raise HTTPException(status_code=400, detail="Working directory is not writable: {}".format(target))


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


def resolve_pipeline_path(selected_path, pipelines_dir):
    selected = (selected_path or "").strip()
    if not selected:
        raise HTTPException(status_code=400, detail="Pipeline file is required")

    candidate = Path(selected).expanduser()
    if not candidate.is_absolute():
        candidate = pipelines_dir / selected
    candidate = candidate.resolve()
    pipelines_root = pipelines_dir.resolve()

    try:
        candidate.relative_to(pipelines_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Pipeline file must be inside {}".format(pipelines_root))
    if not candidate.is_file():
        raise HTTPException(status_code=400, detail="Pipeline file not found: {}".format(selected))
    return candidate


def container_aware_execution_profile(execution_profile, pipeline_config):
    engines = workflow_container_engines(pipeline_config)
    profiles = [part.strip() for part in execution_profile.split(",") if part.strip()]
    if "docker" in engines and "docker" not in profiles:
        profiles.append("docker")
    if ("apptainer" in engines or "singularity" in engines) and "apptainer" not in profiles:
        profiles.append("apptainer")
    return ",".join(profiles)


def workflow_container_engines(pipeline_config):
    engines = set()
    resolved_tools = pipeline_config.get("resolved_tools", {})
    if not isinstance(resolved_tools, dict):
        return engines
    for step_tools in resolved_tools.values():
        if not isinstance(step_tools, dict):
            continue
        collect_container_engines(step_tools, engines)
    return engines


def collect_container_engines(value, engines):
    if isinstance(value, dict):
        container = value.get("container")
        if isinstance(container, dict):
            engine = str(container.get("engine") or "").strip().lower()
            image = str(container.get("image") or "").strip()
            if engine:
                engines.add(engine)
            elif image:
                engines.add("docker")
        elif isinstance(container, str) and container.strip():
            engines.add("docker")
        for nested in value.values():
            collect_container_engines(nested, engines)
    elif isinstance(value, list):
        for item in value:
            collect_container_engines(item, engines)


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


def resolve_pipeline_config(
    selected_pipeline,
    pipelines_dir,
    aligner,
    entry_step,
    requested_steps,
    requested_workflow,
    preprocessing_workflow,
    postprocessing_workflow,
    annotation_workflow,
    tools_config=None,
):
    if selected_pipeline:
        pipeline = normalize_pipeline_for_nextflow(load_json(resolve_pipeline_path(selected_pipeline, pipelines_dir)))
    else:
        selected = [step.strip() for step in requested_workflow.split(",") if step.strip()]
        pipeline = real_alignment_pipeline(
            aligner,
            include_prealignment=entry_step == "prealignment" or "prealignment" in selected,
            include_alignment=entry_step in ("prealignment", "alignment") or "alignment" in selected,
            include_variantcalling=entry_step == "variantcalling" or "variantcalling" in requested_steps,
            include_postprocessing=entry_step == "postprocessing" or "postprocessing" in requested_steps,
            include_annotation=entry_step == "annotation" or "annotation" in requested_steps,
            preprocessing_workflow=preprocessing_workflow,
            postprocessing_workflow=postprocessing_workflow,
            annotation_workflow=annotation_workflow,
        )

    selected_steps = [step.strip() for step in requested_workflow.split(",") if step.strip()]
    pipeline["workflow"] = [step for step in selected_steps if step in supported_nextflow_steps()]
    reconcile_variantcalling_tools_with_tools_config(pipeline, tools_config or {})
    reconcile_preprocessing_databases_with_tools_config(pipeline, tools_config or {})
    if "variantcalling" in pipeline["workflow"] and not pipeline.get("variantcalling", {}).get("tools"):
        pipeline["workflow"] = [step for step in pipeline["workflow"] if step != "variantcalling"]
    if "preprocessing" in pipeline.get("workflow", []) and isinstance(pipeline.get("preprocessing"), dict):
        pipeline["preprocessing"]["workflow"] = preprocessing_workflow
    if "postprocessing" in pipeline.get("workflow", []) and isinstance(pipeline.get("postprocessing"), dict):
        pipeline["postprocessing"]["workflow"] = postprocessing_workflow
    if "annotation" in pipeline.get("workflow", []) and isinstance(pipeline.get("annotation"), dict):
        pipeline["annotation"]["workflow"] = annotation_workflow
    return pipeline


def reconcile_variantcalling_tools_with_tools_config(pipeline, tools_config):
    variantcalling = pipeline.get("variantcalling")
    if not isinstance(variantcalling, dict):
        return
    tools = variantcalling.get("tools", [])
    if not isinstance(tools, list):
        tools = []
    configured = [tool for tool in tools if tool in tools_config]
    if configured:
        variantcalling["tools"] = configured[:1]
        return
    configured_callers = [
        tool
        for tool in tools_config
        if str(tool).upper().startswith("GATK V.4")
        or str(tool).upper().startswith("DEEPVARIANT")
        or str(tool).upper().startswith("FREEBAYES")
    ]
    if configured_callers and "variantcalling" in pipeline.get("workflow", []):
        fallback = sorted(configured_callers)[0]
        variantcalling["tools"] = [fallback]
        variantcalling.setdefault(fallback, {"args": []})


def reconcile_preprocessing_databases_with_tools_config(pipeline, tools_config):
    preprocessing = pipeline.get("preprocessing")
    if not isinstance(preprocessing, dict):
        return
    aliases = {
        "DBSNP v.138": ["DBSNP v.138", "dbsnp", "DBSNP"],
        "MILLS": ["MILLS", "mills"],
    }
    for operation, fields in {
        "indel_realignment": ["mills"],
        "BQ_recalibration": ["dbsnp", "mills"],
    }.items():
        operation_cfg = preprocessing.get(operation)
        if not isinstance(operation_cfg, dict):
            continue
        tool_name = operation_cfg.get("tool", "")
        tool_cfg = operation_cfg.get(tool_name, {}) if isinstance(operation_cfg.get(tool_name, {}), dict) else {}
        for field in fields:
            value = tool_cfg.get(field) or operation_cfg.get(field)
            replacement = first_configured_alias(value, aliases, tools_config)
            if not replacement:
                continue
            if value and value != replacement:
                if isinstance(tool_cfg, dict) and field in tool_cfg:
                    tool_cfg[field] = replacement
                elif field in operation_cfg:
                    operation_cfg[field] = replacement
            elif not value:
                if isinstance(tool_cfg, dict):
                    tool_cfg[field] = replacement
                else:
                    operation_cfg[field] = replacement


def first_configured_alias(value, aliases, tools_config):
    candidates = aliases.get(value, [value]) if value else []
    for candidate in candidates:
        if candidate in tools_config:
            return candidate
    lower_candidates = [str(candidate).lower() for candidate in candidates]
    for candidate in lower_candidates:
        if candidate in tools_config:
            return candidate
    return ""


def normalize_pipeline_for_nextflow(pipeline):
    normalized = json.loads(json.dumps(pipeline)) if isinstance(pipeline, dict) else {}
    workflow = normalized.get("workflow", [])
    if not isinstance(workflow, list):
        workflow = []

    mapped = []
    for step in workflow:
        mapped_step = "annotation" if step == "variant_annotation" else step
        if mapped_step in supported_nextflow_steps() and mapped_step not in mapped:
            mapped.append(mapped_step)
    normalized["workflow"] = mapped

    if "annotation" not in normalized and isinstance(normalized.get("variant_annotation"), dict):
        variant_annotation = normalized["variant_annotation"]
        tool_name = variant_annotation.get("tool") or "VEP v.95"
        tool_specific = variant_annotation.get(tool_name, {}) if isinstance(variant_annotation.get(tool_name, {}), dict) else {}
        normalized["annotation"] = {
            "workflow": ["vep_annotation", "ann_vcf_to_tsv"],
            "threads": variant_annotation.get("threads", "2"),
            "ram": variant_annotation.get("ram", "8g"),
            "vep_annotation": {
                "tool": tool_name,
                tool_name: tool_specific,
            },
            "ann_vcf_to_tsv": {"tool": "", "args": {"tags_file": "", "format_tags": "", "info_tags": ""}},
        }
    normalize_supported_variantcalling(normalized)
    normalize_supported_workflows(normalized)
    normalize_step_defaults(normalized)
    return normalized


def normalize_supported_variantcalling(pipeline):
    variantcalling = pipeline.get("variantcalling")
    if not isinstance(variantcalling, dict):
        return
    tools = variantcalling.get("tools", [])
    if not isinstance(tools, list):
        tools = []
    gatk_tools = [tool for tool in tools if str(tool).upper().startswith("GATK")]
    deepvariant_tools = [tool for tool in tools if str(tool).upper().startswith("DEEPVARIANT")]
    freebayes_tools = [tool for tool in tools if str(tool).upper().startswith("FREEBAYES")]
    supported_tools = gatk_tools or deepvariant_tools or freebayes_tools
    if supported_tools:
        selected = supported_tools[0]
        variantcalling["tools"] = [selected]
        if not variantcalling.get("ram"):
            variantcalling["ram"] = "8g"
        if not variantcalling.get("threads"):
            variantcalling["threads"] = "2"
        variantcalling.setdefault("filters", {})
        return
    variantcalling["tools"] = []
    if "variantcalling" in pipeline.get("workflow", []):
        pipeline["workflow"] = [step for step in pipeline["workflow"] if step != "variantcalling"]


def normalize_supported_workflows(pipeline):
    supported_operations = {
        "prealignment": {"fastq_QC"},
        "alignment": {"fastq_alignment", "sam_to_bam", "sortSam", "sort_bam", "index_bam", "bam_QC"},
        "preprocessing": {"add_readgroups", "mark_pcr_dup", "indel_realignment", "BQ_recalibration"},
        "postprocessing": {"vcf_norm", "vcf_filter", "vcf_to_tsv"},
        "annotation": {"vep_annotation", "ann_vcf_to_tsv"},
    }
    for step, allowed in supported_operations.items():
        step_config = pipeline.get(step)
        if not isinstance(step_config, dict):
            continue
        workflow = step_config.get("workflow", [])
        if isinstance(workflow, list):
            step_config["workflow"] = [operation for operation in workflow if operation in allowed]
            if step == "prealignment" and not step_config["workflow"] and isinstance(step_config.get("fastq_QC"), dict):
                step_config["workflow"] = ["fastq_QC"]


def normalize_step_defaults(pipeline):
    defaults = {
        "prealignment": {"workflow": ["fastq_QC"], "threads": "1", "ram": "1g"},
        "alignment": {"workflow": ["fastq_alignment"], "threads": "2", "ram": "1g"},
        "preprocessing": {"workflow": ["add_readgroups", "mark_pcr_dup"], "threads": "2", "ram": "8g"},
        "variantcalling": {"threads": "2", "ram": "8g", "filters": {}},
        "postprocessing": {"workflow": ["vcf_to_tsv"], "threads": "2", "ram": "2g"},
        "annotation": {"workflow": ["vep_annotation", "ann_vcf_to_tsv"], "threads": "2", "ram": "8g"},
    }
    for step in pipeline.get("workflow", []):
        step_config = pipeline.get(step)
        if not isinstance(step_config, dict):
            continue
        for field, value in defaults.get(step, {}).items():
            if step_config.get(field) in (None, "", []):
                step_config[field] = json.loads(json.dumps(value))


def supported_nextflow_steps():
    return ["prealignment", "alignment", "preprocessing", "variantcalling", "postprocessing", "annotation"]


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
    gatk_java_home = compatible_gatk_java_home()
    if gatk_java_home:
        env["GATK_JAVA_HOME"] = str(gatk_java_home)
        env["GATK_JAVA_CMD"] = str(gatk_java_home / "bin" / "java")
    return env


def compatible_java_home():
    for path in JAVA_CANDIDATES:
        if (path / "bin" / "java").exists():
            return path
    return None


def compatible_gatk_java_home():
    for path in GATK_JAVA_CANDIDATES:
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
            "ram": "8g",
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
