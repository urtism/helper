from __future__ import unicode_literals

import csv
import json
from pathlib import Path

from helper_next.core.samplesheet import ANALYSIS_TYPES, ORGANIZATION_ROLES, STEP_COLUMNS


MANIFEST_COLUMNS = [
    "sample_id",
    "role",
    "sample_name",
    "analysis_id",
    "analysis_type",
    "relationship",
    "individual_id",
    "sex",
    "father",
    "mother",
    "affected",
    "control_relationship",
    "specimen_type",
    "tumor_purity",
    "twin_group",
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
    "annotation": ["workflow", "threads", "ram"],
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
    "postprocessing": ["merged_vcf"],
    "variant_annotation": [],
    "cnv_annotation": [],
    "annotation": ["merged_vcf"],
    "postannotation": [],
}

SUPPORTED_ALIGNMENT_TOOL_PREFIXES = ("BWA", "BOWTIE2", "NOVOALIGN")
SUPPORTED_TRIMMING_TOOL_PREFIXES = ("CUTADAPT", "SURECALLTRIMMER")


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
    if samplesheet.get("schema_version") == 2 or "analysis_groups" in samplesheet:
        return analysis_manifest_rows(samplesheet, step)

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
            rows.append(manifest_row(sample_id, role, sample_name, payload))

    return rows


def analysis_manifest_rows(samplesheet, step):
    step_data = samplesheet.get(step, {})
    rows = []
    for group in samplesheet.get("analysis_groups", []):
        analysis_id = group.get("analysis_id", "")
        analysis_type = group.get("analysis_type", "")
        for member in group.get("members", []):
            sample_name = member.get("sample_name", "")
            if not sample_name:
                continue
            row = manifest_row(analysis_id, member.get("relationship", ""), sample_name, step_data.get(sample_name, {}))
            row.update(
                {
                    "analysis_id": analysis_id,
                    "analysis_type": analysis_type,
                    "relationship": member.get("relationship", ""),
                    "individual_id": member.get("individual_id", ""),
                    "sex": member.get("sex", ""),
                    "father": member.get("father", ""),
                    "mother": member.get("mother", ""),
                    "affected": member.get("affected", ""),
                    "control_relationship": member.get("control_relationship", ""),
                    "specimen_type": member.get("specimen_type", ""),
                    "tumor_purity": member.get("tumor_purity", ""),
                    "twin_group": member.get("twin_group", ""),
                }
            )
            rows.append(row)
    return rows


def manifest_row(sample_id, role, sample_name, payload):
    return {
        "sample_id": sample_id,
        "role": role,
        "sample_name": sample_name,
        "analysis_id": sample_id,
        "analysis_type": "",
        "relationship": role,
        "individual_id": "",
        "sex": "",
        "father": "",
        "mother": "",
        "affected": "",
        "control_relationship": "",
        "specimen_type": "",
        "tumor_purity": "",
        "twin_group": "",
        "fastq_r1": payload.get("fastq_R1", ""),
        "fastq_r2": payload.get("fastq_R2", ""),
        "fastq_i2": payload.get("fastq_I2", ""),
        "bam": payload.get("bam", ""),
        "merged_vcf": payload.get(
            "merged_vcf",
            payload.get(
                "vcf",
                payload.get(
                    "gatk_vcf",
                    payload.get("freebayes_vcf", payload.get("varscan_vcf", payload.get("somatic_vcf", ""))),
                ),
            ),
        ),
        "variants_tsv": payload.get("variants_tsv", payload.get("tsv", "")),
    }


def validate_nextflow_inputs(samplesheet, pipeline_config, tools_config, entry_step=None, requested_workflow=None):
    errors = []
    _validate_samplesheet(samplesheet, entry_step, errors)
    workflow = _validate_pipeline(pipeline_config, requested_workflow, errors)
    _validate_analysis_workflow_compatibility(samplesheet, pipeline_config, tools_config, workflow, errors)
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

    analysis_schema = samplesheet.get("schema_version") == 2 or "analysis_groups" in samplesheet
    organization = samplesheet.get("sample_organization", "only cases")
    if analysis_schema:
        _validate_analysis_groups(samplesheet, errors)
    elif organization not in ORGANIZATION_ROLES:
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


def _validate_analysis_groups(samplesheet, errors):
    groups = samplesheet.get("analysis_groups")
    if not isinstance(groups, list) or not groups:
        errors.append("samplesheet.analysis_groups: expected a non-empty list")
        return

    raw_sample_list = samplesheet.get("sample_list", [])
    sample_list = raw_sample_list if isinstance(raw_sample_list, list) else []
    assigned_samples = []
    seen_group_ids = {}
    for index, group in enumerate(groups):
        path = "samplesheet.analysis_groups[{}]".format(index)
        if not isinstance(group, dict):
            errors.append("{}: expected a JSON object".format(path))
            continue
        analysis_id = group.get("analysis_id", "")
        analysis_type = group.get("analysis_type", "")
        members = group.get("members")
        if not analysis_id:
            errors.append("{}.analysis_id: required".format(path))
        elif analysis_id in seen_group_ids and seen_group_ids[analysis_id] != analysis_type:
            errors.append("{}.analysis_id: '{}' is already used by another analysis type".format(path, analysis_id))
        else:
            seen_group_ids[analysis_id] = analysis_type
        if analysis_type not in ANALYSIS_TYPES:
            errors.append("{}.analysis_type: unsupported value '{}'".format(path, analysis_type))
        if not isinstance(members, list) or not members:
            errors.append("{}.members: expected a non-empty list".format(path))
            continue

        valid_members = [member for member in members if isinstance(member, dict)]
        member_names = [member.get("sample_name", "") for member in valid_members]
        assigned_samples.extend(name for name in member_names if name)
        for member_index, member in enumerate(members):
            member_path = "{}.members[{}]".format(path, member_index)
            if not isinstance(member, dict):
                errors.append("{}: expected a JSON object".format(member_path))
                continue
            sample_name = member.get("sample_name", "")
            if not sample_name:
                errors.append("{}.sample_name: required".format(member_path))
            elif sample_name not in sample_list:
                errors.append("{}.sample_name: '{}' is not in sample_list".format(member_path, sample_name))

        if analysis_type == "only cases":
            if len(members) != 1:
                errors.append("{}.members: only-case analysis requires exactly one sample".format(path))
        elif analysis_type == "family":
            _validate_family_group(path, valid_members, member_names, sample_list, errors)
        elif analysis_type == "case-control":
            _validate_case_control_group(path, valid_members, errors)
        elif analysis_type == "tumor-normal":
            _validate_tumor_normal_group(path, valid_members, errors)

    duplicates = sorted({name for name in assigned_samples if assigned_samples.count(name) > 1})
    for sample_name in duplicates:
        errors.append("samplesheet.analysis_groups: sample '{}' is assigned more than once".format(sample_name))
    for sample_name in sample_list:
        if sample_name not in assigned_samples:
            errors.append("samplesheet.analysis_groups: sample '{}' is not assigned".format(sample_name))


def _validate_family_group(path, members, member_names, sample_list, errors):
    if sum(member.get("relationship") == "proband" for member in members) != 1:
        errors.append("{}.members: family requires exactly one proband".format(path))
    for member in members:
        sample_name = member.get("sample_name", "")
        if member.get("sex", "unknown") == "unknown":
            errors.append("{}.{}: sex is required".format(path, sample_name))
        if member.get("affected", "unknown") == "unknown":
            errors.append("{}.{}: affected status is required".format(path, sample_name))
        for parent_field in ("father", "mother"):
            parent = member.get(parent_field, "")
            if parent == sample_name and parent:
                errors.append("{}.{}: {} cannot reference the sample itself".format(path, sample_name, parent_field))
            elif parent and parent in sample_list and parent not in member_names:
                errors.append("{}.{}: {} '{}' is loaded but assigned outside this family".format(path, sample_name, parent_field, parent))
    twin_groups = {}
    for member in members:
        twin_group = member.get("twin_group", "")
        if twin_group:
            twin_groups.setdefault(twin_group, []).append(member.get("sample_name", ""))
    for twin_group, names in twin_groups.items():
        if len(names) < 2:
            errors.append("{}.twin_group.{}: requires at least two members".format(path, twin_group))


def _validate_case_control_group(path, members, errors):
    if len(members) != 2:
        errors.append("{}.members: case-control requires exactly two samples".format(path))
    if sum(member.get("relationship") == "case" for member in members) != 1:
        errors.append("{}.members: case-control requires exactly one case".format(path))
    if sum(member.get("relationship") == "control" for member in members) != 1:
        errors.append("{}.members: case-control requires exactly one control".format(path))
    for member in members:
        sample_name = member.get("sample_name", "")
        if member.get("sex", "unknown") == "unknown":
            errors.append("{}.{}: sex is required".format(path, sample_name))
        if member.get("affected", "unknown") == "unknown":
            errors.append("{}.{}: affected status is required".format(path, sample_name))
        if member.get("relationship") == "control" and not member.get("control_relationship"):
            errors.append("{}.{}: control relationship is required".format(path, sample_name))


def _validate_tumor_normal_group(path, members, errors):
    if len(members) != 2:
        errors.append("{}.members: tumor-normal requires exactly two samples".format(path))
    if sum(member.get("relationship") == "tumor" for member in members) != 1:
        errors.append("{}.members: tumor-normal requires exactly one tumor".format(path))
    if sum(member.get("relationship") == "normal" for member in members) != 1:
        errors.append("{}.members: tumor-normal requires exactly one normal".format(path))
    individual_ids = set()
    for member in members:
        sample_name = member.get("sample_name", "")
        individual_id = member.get("individual_id", "")
        if not individual_id:
            errors.append("{}.{}: individual_id is required".format(path, sample_name))
        else:
            individual_ids.add(individual_id)
        if member.get("sex", "unknown") == "unknown":
            errors.append("{}.{}: sex is required".format(path, sample_name))
        if member.get("specimen_type", "unknown") == "unknown":
            errors.append("{}.{}: specimen_type is required".format(path, sample_name))
        purity = member.get("tumor_purity", "")
        if purity not in (None, ""):
            try:
                numeric_purity = float(purity)
            except (TypeError, ValueError):
                errors.append("{}.{}: tumor_purity must be a number between 0 and 100".format(path, sample_name))
            else:
                if not 0 <= numeric_purity <= 100:
                    errors.append("{}.{}: tumor_purity must be between 0 and 100".format(path, sample_name))
    if len(individual_ids) > 1:
        errors.append("{}.members: tumor and normal must share the same individual_id".format(path))


def _validate_analysis_workflow_compatibility(samplesheet, pipeline_config, tools_config, workflow, errors):
    if not isinstance(samplesheet, dict) or not isinstance(pipeline_config, dict):
        return
    analysis_schema = samplesheet.get("schema_version") == 2 or "analysis_groups" in samplesheet
    if not analysis_schema or "variantcalling" not in workflow:
        return

    analysis_types = {
        group.get("analysis_type")
        for group in samplesheet.get("analysis_groups", [])
        if isinstance(group, dict)
    }
    configured_tools = tools_config.items() if isinstance(tools_config, dict) else []
    has_gatk4 = any(
        str(name).upper().startswith("GATK V.4")
        and isinstance(config, dict)
        and bool(config.get("path") or config.get("container"))
        for name, config in configured_tools
    )
    if "tumor-normal" in analysis_types and not has_gatk4:
        errors.append("pipeline.variantcalling: tumor-normal analysis requires a configured GATK 4 caller for Mutect2")


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
        if operation in ("vcf_filter", "vcf_to_tsv", "ann_vcf_to_tsv"):
            continue
        if operation_config and "tool" in operation_config and not operation_config.get("tool"):
            errors.append("pipeline.{}.{}: missing selected tool".format(step, operation))
        if step == "alignment" and operation == "fastq_alignment" and operation_config.get("tool"):
            tool_name = operation_config["tool"].upper()
            if not tool_name.startswith(SUPPORTED_ALIGNMENT_TOOL_PREFIXES):
                errors.append(
                    "pipeline.alignment.fastq_alignment: unsupported aligner '{}'".format(operation_config["tool"])
                )
        if step == "prealignment" and operation == "trim_adapters" and operation_config.get("tool"):
            tool_name = operation_config["tool"].upper()
            if not tool_name.startswith(SUPPORTED_TRIMMING_TOOL_PREFIXES):
                errors.append(
                    "pipeline.prealignment.trim_adapters: unsupported trimming tool '{}'".format(
                        operation_config["tool"]
                    )
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
        if step == "preprocessing":
            _validate_preprocessing_databases(step_config, tools_config, errors)


def _validate_preprocessing_databases(step_config, tools_config, errors):
    workflow = step_config.get("workflow", [])
    if "indel_realignment" in workflow:
        indel_cfg = step_config.get("indel_realignment", {})
        tool_name = indel_cfg.get("tool", "GATK v.3.7")
        tool_cfg = indel_cfg.get(tool_name, {}) if isinstance(indel_cfg.get(tool_name, {}), dict) else {}
        mills_key = tool_cfg.get("mills") or indel_cfg.get("mills") or "mills"
        if mills_key and not _tool_key_exists(tools_config, mills_key):
            errors.append("tools.{}: selected database is not configured".format(mills_key))
    if "BQ_recalibration" in workflow:
        bqsr_cfg = step_config.get("BQ_recalibration", {})
        tool_name = bqsr_cfg.get("tool", "GATK v.3.7")
        tool_cfg = bqsr_cfg.get(tool_name, {}) if isinstance(bqsr_cfg.get(tool_name, {}), dict) else {}
        dbsnp_key = tool_cfg.get("dbsnp") or bqsr_cfg.get("dbsnp") or "dbsnp"
        mills_key = tool_cfg.get("mills") or bqsr_cfg.get("mills") or "mills"
        for database_key in (dbsnp_key, mills_key):
            if database_key and not _tool_key_exists(tools_config, database_key):
                errors.append("tools.{}: selected database is not configured".format(database_key))


def _tool_key_exists(tools_config, key):
    aliases = {
        "DBSNP v.138": ["DBSNP v.138", "dbsnp", "DBSNP"],
        "MILLS": ["MILLS", "mills"],
    }
    candidates = aliases.get(key, [key])
    return any(candidate in tools_config or str(candidate).lower() in tools_config for candidate in candidates)


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


def build_nextflow_run_config(samplesheet, pipeline_config, tools_config, entry_step=None, requested_workflow=None, panel_design=None):
    step = infer_entry_step(samplesheet, entry_step)
    workflow = enabled_workflow(pipeline_config, requested_workflow)
    reference_version = pipeline_config.get("reference_version", "")
    reference = tools_config.get(reference_version, {})

    config = {
        "entry_step": step,
        "sample_organization": samplesheet.get("sample_organization", "only cases"),
        "analysis": pipeline_config.get("analysis", ""),
        "reference_version": reference_version,
        "reference_fasta": reference.get("fasta", ""),
        "workflow": workflow,
        "steps": step_summary(pipeline_config, workflow),
    }
    if samplesheet.get("schema_version") == 2 or "analysis_groups" in samplesheet:
        config["schema_version"] = 2
        config["calling_scope"] = "single-sample"
        config["gvcf_storage"] = True
        config["comparative_analysis"] = True
        config["analysis_groups"] = samplesheet.get("analysis_groups", [])
    if panel_design:
        config["panel_design"] = panel_design
    return config


def write_run_config(config, path):
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w") as handle:
        json.dump(config, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return output
