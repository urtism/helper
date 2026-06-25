import copy
import shlex

from helper_next.core.annotation import normalize_vep_annotation_config
from helper_next.core.tool_wrappers import build_invocation


def resolve_pipeline_tools(pipeline_config, tools_config, panel_design=None):
    resolved = copy.deepcopy(pipeline_config)
    resolved.setdefault("resolved_tools", {})
    panel_design = panel_design or {}

    for step in resolved.get("workflow", []):
        step_config = resolved.get(step)
        if not isinstance(step_config, dict):
            continue
        if step == "annotation":
            resolved[step] = normalize_vep_annotation_config(step_config, tools_config)
            step_config = resolved[step]
        reference_info = tool_entry(tools_config, resolved.get("reference_version", ""))
        step_config["resolved"] = resolve_step(step, step_config, tools_config, panel_design, reference_info)
        resolved["resolved_tools"][step] = step_config["resolved"]

    return resolved


def resolve_step(step, step_config, tools_config, panel_design, reference_info=None):
    reference_info = reference_info or {}
    if step == "alignment":
        return resolve_alignment(step_config, tools_config, panel_design, reference_info)
    if step == "preprocessing":
        return resolve_preprocessing(step_config, tools_config, panel_design, reference_info)
    if step == "variantcalling":
        return resolve_variantcalling(step_config, tools_config, panel_design, reference_info)
    if step == "postprocessing":
        return resolve_postprocessing(step_config, tools_config, panel_design, reference_info)
    if step == "annotation":
        return resolve_annotation(step_config, tools_config, panel_design, reference_info)
    return {}


def resolve_alignment(step_config, tools_config, panel_design=None, reference_info=None):
    fastq_cfg = step_config.get("fastq_alignment", {})
    tool_name = fastq_cfg.get("tool", "BWA v.0.7.17")
    tool_cfg = tool_entry(tools_config, tool_name)
    samtools_cfg = tool_entry(tools_config, "SAMTOOLS")
    return {
        "fastq_alignment": operation(
            "fastq_alignment",
            tool_name,
            tool_cfg,
            with_step_resources(fastq_cfg.get(tool_name, fastq_cfg), step_config),
            panel_design,
            reference_info,
            tools_config,
        ),
        "samtools": operation("samtools", "SAMTOOLS", samtools_cfg, {}, panel_design, reference_info, tools_config),
    }


def resolve_preprocessing(step_config, tools_config, panel_design, reference_info=None):
    add_cfg = step_config.get("add_readgroups", {})
    mark_cfg = step_config.get("mark_pcr_dup", {})
    indel_cfg = step_config.get("indel_realignment", {})
    bqsr_cfg = step_config.get("BQ_recalibration", {})
    picard_name = add_cfg.get("tool") or mark_cfg.get("tool") or "PICARD v.2.7.1"
    gatk3_name = indel_cfg.get("tool") or bqsr_cfg.get("tool") or "GATK v.3.7"

    indel_tool_cfg = indel_cfg.get(gatk3_name, {}) if isinstance(indel_cfg.get(gatk3_name, {}), dict) else {}
    bqsr_tool_cfg = bqsr_cfg.get(gatk3_name, {}) if isinstance(bqsr_cfg.get(gatk3_name, {}), dict) else {}
    indel_mills_key = indel_tool_cfg.get("mills") or indel_cfg.get("mills") or bqsr_tool_cfg.get("mills") or bqsr_cfg.get("mills") or "mills"
    bqsr_mills_key = bqsr_tool_cfg.get("mills") or bqsr_cfg.get("mills") or indel_mills_key
    bqsr_dbsnp_key = bqsr_tool_cfg.get("dbsnp") or bqsr_cfg.get("dbsnp") or "dbsnp"

    panel_assets = panel_design.get("assets", {}) if isinstance(panel_design, dict) else {}
    target_intervals = step_config.get("target_intervals") or step_config.get("target_list") or step_config.get("target_bed") or panel_assets.get("target_bed", "")

    picard_cfg = tool_entry(tools_config, picard_name)
    gatk3_cfg = tool_entry(tools_config, gatk3_name)
    samtools_cfg = tool_entry(tools_config, "SAMTOOLS")
    indel_operation_cfg = with_step_resources(indel_tool_cfg, step_config)
    indel_operation_cfg.update({"mills": indel_mills_key, "mills_path": database(indel_mills_key, tools_config).get("path", ""), "target_intervals": target_intervals})
    bqsr_operation_cfg = with_step_resources(bqsr_tool_cfg, step_config)
    bqsr_operation_cfg.update(
        {
            "mills": bqsr_mills_key,
            "mills_path": database(bqsr_mills_key, tools_config).get("path", ""),
            "dbsnp": bqsr_dbsnp_key,
            "dbsnp_path": database(bqsr_dbsnp_key, tools_config).get("path", ""),
            "target_intervals": target_intervals,
        }
    )
    resolved = {
        "picard": operation("picard", picard_name, picard_cfg, {}, panel_design, reference_info, tools_config),
        "samtools": operation("samtools", "SAMTOOLS", samtools_cfg, {}, panel_design, reference_info, tools_config),
        "gatk3": operation("gatk3", gatk3_name, gatk3_cfg, {}, panel_design, reference_info, tools_config),
        "databases": {
            "indel_mills": database(indel_mills_key, tools_config),
            "bqsr_mills": database(bqsr_mills_key, tools_config),
            "bqsr_dbsnp": database(bqsr_dbsnp_key, tools_config),
        },
        "target_intervals": target_intervals,
    }
    if "add_readgroups" in step_config.get("workflow", []) or add_cfg:
        resolved["add_readgroups"] = operation(
            "add_readgroups",
            picard_name,
            picard_cfg,
            with_step_resources(add_cfg.get(picard_name, add_cfg), step_config),
            panel_design,
            reference_info,
            tools_config,
        )
    if "mark_pcr_dup" in step_config.get("workflow", []) or mark_cfg:
        resolved["mark_pcr_dup"] = operation(
            "mark_pcr_dup",
            picard_name,
            picard_cfg,
            with_step_resources(mark_cfg.get(picard_name, mark_cfg), step_config),
            panel_design,
            reference_info,
            tools_config,
        )
    if "indel_realignment" in step_config.get("workflow", []) or indel_cfg:
        resolved["indel_realignment"] = operation("indel_realignment", gatk3_name, gatk3_cfg, indel_operation_cfg, panel_design, reference_info, tools_config)
    if "BQ_recalibration" in step_config.get("workflow", []) or bqsr_cfg:
        resolved["BQ_recalibration"] = operation("BQ_recalibration", gatk3_name, gatk3_cfg, bqsr_operation_cfg, panel_design, reference_info, tools_config)
    return resolved


def resolve_variantcalling(step_config, tools_config, panel_design=None, reference_info=None):
    tool_name = next((tool for tool in step_config.get("tools", []) if str(tool).upper().startswith("GATK")), "GATK v.4.3")
    operation_cfg = with_step_resources(step_config.get(tool_name, {}), step_config)
    panel_assets = panel_design.get("assets", {}) if isinstance(panel_design, dict) else {}
    if panel_assets.get("target_bed") and "target_intervals" not in operation_cfg:
        operation_cfg["target_intervals"] = panel_assets["target_bed"]
    return {
        "caller": operation("caller", tool_name, tool_entry(tools_config, tool_name), operation_cfg, panel_design, reference_info, tools_config),
    }


def resolve_postprocessing(step_config, tools_config, panel_design=None, reference_info=None):
    norm_cfg = step_config.get("vcf_norm", {})
    filter_cfg = step_config.get("vcf_filter", {})
    norm_name = norm_cfg.get("tool") or "BCFTOOLS"
    filter_name = filter_cfg.get("tool") or ""
    return {
        "vcf_norm": operation(
            "vcf_norm",
            norm_name,
            tool_entry(tools_config, norm_name),
            with_step_resources(norm_cfg.get(norm_name, norm_cfg), step_config),
            panel_design,
            reference_info,
            tools_config,
        )
        if norm_name
        else {},
        "vcf_filter": operation(
            "vcf_filter",
            filter_name,
            tool_entry(tools_config, filter_name),
            with_step_resources(filter_cfg.get(filter_name, filter_cfg), step_config),
            panel_design,
            reference_info,
            tools_config,
        )
        if filter_name
        else {},
    }


def resolve_annotation(step_config, tools_config, panel_design, reference_info=None):
    vep_cfg = step_config.get("vep_annotation", {})
    tool_name = vep_cfg.get("tool") or "VEP v.95"
    tool_specific = vep_cfg.get(tool_name, {}) if isinstance(vep_cfg.get(tool_name, {}), dict) else {}
    panel_assets = panel_design.get("assets", {}) if isinstance(panel_design, dict) else {}
    return {
        "vep_annotation": operation(
            "vep_annotation",
            tool_name,
            tool_entry(tools_config, tool_name),
            with_step_resources(tool_specific, step_config),
            panel_design,
            reference_info,
            tools_config,
        ),
        "panel_assets": panel_assets,
    }


def operation(operation_name, tool_name, tool_cfg, operation_cfg, panel_design=None, reference_info=None, tools_config=None):
    operation_cfg = operation_cfg if isinstance(operation_cfg, dict) else {}
    args = operation_cfg.get("args", [])
    resolved_args = operation_cfg.get("resolved_args") or shell_join(args if isinstance(args, list) else [])
    payload = {
        "tool": tool_name,
        "path": tool_cfg.get("path", tool_name),
        "version": tool_cfg.get("version", ""),
        "container": tool_cfg.get("container", ""),
        "args": args,
        "resolved_args": resolved_args,
    }
    invocation = build_invocation(operation_name, tool_name, operation_cfg, tool_cfg, panel_design, reference_info, tools_config)
    if invocation:
        payload["invocation"] = invocation.to_dict()
    return payload


def with_step_resources(operation_cfg, step_config):
    merged = dict(operation_cfg) if isinstance(operation_cfg, dict) else {}
    for key in ("threads", "ram"):
        if key not in merged and isinstance(step_config, dict) and step_config.get(key) not in (None, "", []):
            merged[key] = step_config[key]
    return merged


def database(key, tools_config):
    cfg = tool_entry(tools_config, key)
    return {"key": key, "path": cfg.get("path", ""), "version": cfg.get("version", "")}


def tool_entry(tools_config, key):
    if not key:
        return {}
    return tools_config.get(key) or tools_config.get(str(key).lower()) or {}


def shell_join(args):
    return " ".join(shlex.quote(str(item)) for item in args if str(item))
