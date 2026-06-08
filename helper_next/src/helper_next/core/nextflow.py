from __future__ import unicode_literals

import csv
import json
from pathlib import Path

from helper_next.core.samplesheet import ORGANIZATION_ROLES, STEP_COLUMNS


MANIFEST_COLUMNS = [
    "sample_id",
    "role",
    "sample_name",
    "fastq_r1",
    "fastq_r2",
    "fastq_i2",
    "bam",
    "merged_vcf",
    "variants_tsv",
]

ENTRY_STEPS = [
    "prealignment",
    "alignment",
    "preprocessing",
    "variantcalling",
    "cnvcalling",
    "postprocessing",
    "variant_annotation",
    "cnv_annotation",
    "annotation",
    "postannotation",
]

REFERENCE_STEPS = {
    "alignment",
    "preprocessing",
    "variantcalling",
    "cnvcalling",
    "variant_annotation",
    "cnv_annotation",
}

STEP_REQUIRED_FIELDS = {
    "prealignment": ["workflow", "threads", "ram"],
    "alignment": ["workflow", "threads", "ram"],
    "preprocessing": ["workflow", "threads", "ram"],
    "variantcalling": ["tools", "threads", "ram", "filters"],
    "cnvcalling": ["tools", "threads", "ram"],
    "postprocessing": ["workflow", "threads", "ram"],
    "variant_annotation": ["tool", "threads", "ram"],
    "cnv_annotation": ["tool", "threads", "ram"],
    "postannotation": ["workflow"],
}

ENTRY_STEP_REQUIRED_COLUMNS = {
    "prealignment": ["fastq_r1", "fastq_r2"],
    "alignment": ["fastq_r1", "fastq_r2"],
    "preprocessing": ["bam"],
    "variantcalling": ["bam"],
    "cnvcalling": ["bam"],
    "postprocessing": [],
    "variant_annotation": [],
    "cnv_annotation": [],
    "annotation": [],
    "postannotation": [],
}

SUPPORTED_ALIGNMENT_TOOL_PREFIXES = ("BWA", "BOWTIE2", "NOVOALIGN")


class ValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        ValueError.__init__(self, "\n".join(errors))


def load_json_file(path):
    with open(str(path)) as handle:
        return json.load(handle)


def infer_entry_step(samplesheet, requested_step=None):
    if requested_step:
        if requested_step not in ENTRY_STEPS and requested_step not in STEP_COLUMNS:
            raise ValueError("Unknown samplesheet step: {}".format(requested_step))
        if requested_step not in samplesheet:
            raise ValueError("Samplesheet does not contain step: {}".format(requested_step))
        return requested_step

    for step in ENTRY_STEPS:
        if step in samplesheet:
            return step
    raise ValueError("Samplesheet does not contain any supported entry step")


def manifest_rows(samplesheet, entry_step=None):
    step = infer_entry_step(samplesheet, entry_step)
    organization = samplesheet.get("sample_organization", "only cases")
    roles = ORGANIZATION_ROLES.get(organization, ORGANIZATION_ROLES["only cases"])
    step_data = samplesheet.get(step, {})
    rows = []

    for sample_id in samplesheet.get("sample_list", []):
        grouped = step_data.get(sample_id, {})
        for role in roles:
            payload = grouped.get(role, {})
            sample_name = payload.get("sample_name", "")
            if not sample_name:
                continue
            rows.append(
                {
                    "sample_id": sample_id,
                    "role": role,
                    "sample_name": sample_name,
                    "fastq_r1": payload.get("fastq_R1", ""),
                    "fastq_r2": payload.get("fastq_R2", ""),
                    "fastq_i2": payload.get("fastq_I2", ""),
                    "bam": payload.get("bam", ""),
                    "merged_vcf": payload.get("merged_vcf", payload.get("vcf", "")),
                    "variants_tsv": payload.get("variants_tsv", payload.get("tsv", "")),
                }
            )

    return rows


def validate_nextflow_inputs(samplesheet, pipeline_config, tools_config, entry_step=None, requested_workflow=None):
    errors = []
    _validate_samplesheet(samplesheet, entry_step, errors)
    workflow = _validate_pipeline(pipeline_config, requested_workflow, errors)
    _validate_tools_and_reference(pipeline_config, tools_config, workflow, errors)
    if errors:
        raise ValidationError(errors)
    return True


def _validate_samplesheet(samplesheet, entry_step, errors):
    if not isinstance(samplesheet, dict):
        errors.append("samplesheet: expected a JSON object")
        return

    sample_list = samplesheet.get("sample_list")
    if not isinstance(sample_list, list) or not sample_list:
        errors.append("samplesheet.sample_list: expected a non-empty list")

    organization = samplesheet.get("sample_organization", "only cases")
    if organization not in ORGANIZATION_ROLES:
        errors.append("samplesheet.sample_organization: unsupported value '{}'".format(organization))

    try:
        step = infer_entry_step(samplesheet, entry_step)
    except ValueError as exc:
        errors.append("samplesheet: {}".format(exc))
        return

    rows = manifest_rows(samplesheet, step)
    if not rows:
        errors.append("samplesheet.{}: no usable samples found".format(step))
        return

    required_columns = ENTRY_STEP_REQUIRED_COLUMNS.get(step, [])
    for row in rows:
        missing = [column for column in required_columns if not row.get(column)]
        if missing:
            errors.append(
                "samplesheet.{step}.{sample_id}.{role}: missing {fields}".format(
                    step=step,
                    sample_id=row.get("sample_id", ""),
                    role=row.get("role", ""),
                    fields=", ".join(missing),
                )
            )


def _validate_pipeline(pipeline_config, requested_workflow, errors):
    if not isinstance(pipeline_config, dict):
        errors.append("pipeline: expected a JSON object")
        return []

    workflow = pipeline_config.get("workflow")
    if not isinstance(workflow, list) or not workflow:
        errors.append("pipeline.workflow: expected a non-empty list")
        return []

    active_workflow = enabled_workflow(pipeline_config, requested_workflow)
    if requested_workflow and not active_workflow:
        errors.append("pipeline.workflow: requested workflow does not match configured steps")

    configured = set(workflow)
    if requested_workflow:
        for step in [item.strip() for item in requested_workflow.split(",") if item.strip()]:
            if step not in configured:
                errors.append("pipeline.workflow: requested step '{}' is not configured".format(step))

    for step in active_workflow:
        step_config = pipeline_config.get(step)
        if not isinstance(step_config, dict):
            errors.append("pipeline.{}: expected a JSON object".format(step))
            continue
        for field in STEP_REQUIRED_FIELDS.get(step, []):
            value = step_config.get(field)
            if value in (None, "", []):
                errors.append("pipeline.{}: missing required field '{}'".format(step, field))
        _validate_step_operations(step, step_config, errors)

    return active_workflow


def _validate_step_operations(step, step_config, errors):
    operations = step_config.get("workflow", [])
    if operations and not isinstance(operations, list):
        errors.append("pipeline.{}.workflow: expected a list".format(step))
        return

    tools = step_config.get("tools", [])
    if tools and not isinstance(tools, list):
        errors.append("pipeline.{}.tools: expected a list".format(step))

    for operation in operations:
        operation_config = step_config.get(operation, {})
        if operation_config and not isinstance(operation_config, dict):
            errors.append("pipeline.{}.{}: expected a JSON object".format(step, operation))
            continue
        if operation in ("vcf_to_tsv", "ann_vcf_to_tsv"):
            continue
        if operation_config and "tool" in operation_config and not operation_config.get("tool"):
            errors.append("pipeline.{}.{}: missing selected tool".format(step, operation))
        if step == "alignment" and operation == "fastq_alignment" and operation_config.get("tool"):
            tool_name = operation_config["tool"].upper()
            if not tool_name.startswith(SUPPORTED_ALIGNMENT_TOOL_PREFIXES):
                errors.append(
                    "pipeline.alignment.fastq_alignment: unsupported aligner '{}'".format(operation_config["tool"])
                )


def _validate_tools_and_reference(pipeline_config, tools_config, workflow, errors):
    if not isinstance(tools_config, dict):
        errors.append("tools: expected a JSON object")
        return

    reference_version = pipeline_config.get("reference_version", "")
    if any(step in REFERENCE_STEPS for step in workflow):
        if not reference_version:
            errors.append("pipeline.reference_version: required by enabled workflow")
        elif reference_version not in tools_config:
            errors.append("tools.{}: missing reference entry".format(reference_version))
        elif not isinstance(tools_config[reference_version], dict):
            errors.append("tools.{}: expected a JSON object".format(reference_version))
        elif not tools_config[reference_version].get("fasta"):
            errors.append("tools.{}.fasta: missing reference FASTA".format(reference_version))

    for step in workflow:
        step_config = pipeline_config.get(step, {})
        for tool_name in _selected_tools_for_step(step_config):
            if tool_name and tool_name not in tools_config:
                errors.append("tools.{}: selected tool is not configured".format(tool_name))
            elif tool_name and not isinstance(tools_config[tool_name], dict):
                errors.append("tools.{}: expected a JSON object".format(tool_name))
            elif tool_name and not tools_config[tool_name].get("path") and not tools_config[tool_name].get("container"):
                errors.append("tools.{}: missing path or container".format(tool_name))


def _selected_tools_for_step(step_config):
    tools = []
    if step_config.get("tool"):
        tools.append(step_config["tool"])
    if isinstance(step_config.get("tools"), list):
        tools.extend(step_config["tools"])
    for operation in step_config.get("workflow", []):
        operation_config = step_config.get(operation, {})
        if isinstance(operation_config, dict) and operation_config.get("tool"):
            tools.append(operation_config["tool"])
    return tools


def write_manifest(rows, path):
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in MANIFEST_COLUMNS})
    return output


def enabled_workflow(pipeline_config, requested_workflow=None):
    configured = pipeline_config.get("workflow", [])
    if not requested_workflow:
        return configured
    requested = [step.strip() for step in requested_workflow.split(",") if step.strip()]
    return [step for step in configured if step in requested]


def step_summary(pipeline_config, workflow):
    summary = []
    for step in workflow:
        step_config = pipeline_config.get(step, {})
        entry = {
            "step": step,
            "threads": step_config.get("threads", ""),
            "ram": step_config.get("ram", ""),
        }
        if "workflow" in step_config:
            entry["operations"] = step_config.get("workflow", [])
        if "tools" in step_config:
            entry["tools"] = step_config.get("tools", [])
        if "tool" in step_config:
            entry["tool"] = step_config.get("tool", "")
        summary.append(entry)
    return summary


def build_nextflow_run_config(samplesheet, pipeline_config, tools_config, entry_step=None, requested_workflow=None):
    step = infer_entry_step(samplesheet, entry_step)
    workflow = enabled_workflow(pipeline_config, requested_workflow)
    reference_version = pipeline_config.get("reference_version", "")
    reference = tools_config.get(reference_version, {})

    return {
        "entry_step": step,
        "sample_organization": samplesheet.get("sample_organization", "only cases"),
        "analysis": pipeline_config.get("analysis", ""),
        "reference_version": reference_version,
        "reference_fasta": reference.get("fasta", ""),
        "workflow": workflow,
        "steps": step_summary(pipeline_config, workflow),
    }


def write_run_config(config, path):
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w") as handle:
        json.dump(config, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return output
