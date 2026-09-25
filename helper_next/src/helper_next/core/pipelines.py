import json
import os
import re
import tempfile
from pathlib import Path


PIPELINE_SUFFIX = ".pipeline"
PROTECTED_PIPELINES = {"default.pipeline"}
PIPELINE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

TOOL_CATEGORY_BY_OPERATION = {
    "index_bam": "indexBam",
    "short_variants": "variantcalling",
    "cnv_calling": "cnvcalling",
    "sv_calling": "svcalling",
    "methylation": "methylation",
    "vep_annotation": "variant_ann",
}

PIPELINE_CATALOG = [
    {
        "id": "prealignment",
        "label": "Pre-alignment",
        "operations": [
            {"id": "trim_adapters", "label": "Adapter trimming"},
            {"id": "fastq_QC", "label": "FASTQ quality control"},
        ],
    },
    {
        "id": "alignment",
        "label": "Alignment",
        "operations": [
            {"id": "fastq_alignment", "label": "FASTQ alignment"},
            {"id": "sam_to_bam", "label": "SAM to BAM conversion"},
            {"id": "sortSam", "label": "BAM sorting"},
            {"id": "index_bam", "label": "BAM indexing"},
            {"id": "bam_QC", "label": "BAM quality control"},
        ],
    },
    {
        "id": "preprocessing",
        "label": "Pre-processing",
        "operations": [
            {"id": "add_readgroups", "label": "Add read groups"},
            {"id": "mark_pcr_dup", "label": "Mark PCR duplicates"},
            {"id": "indel_realignment", "label": "Indel realignment"},
            {"id": "BQ_recalibration", "label": "Base-quality recalibration"},
            {"id": "bam_QC", "label": "BAM quality control"},
        ],
    },
    {
        "id": "variantcalling",
        "label": "Variant calling",
        "operations": [
            {"id": "short_variants", "label": "Short variants"},
            {"id": "cnv_calling", "label": "CNVs"},
            {"id": "sv_calling", "label": "SV"},
            {"id": "methylation", "label": "Methylation"},
        ],
    },
    {
        "id": "postprocessing",
        "label": "Post-processing",
        "operations": [
            {"id": "vcf_norm", "label": "VCF normalization"},
            {"id": "vcf_filter", "label": "VCF filtering"},
            {"id": "multi_vcf_merge", "label": "Multi-VCF consensus merge"},
            {"id": "vcf_to_tsv", "label": "VCF to TSV conversion"},
        ],
    },
    {
        "id": "annotation",
        "label": "Annotation",
        "operations": [
            {"id": "vep_annotation", "label": "VEP annotation"},
            {"id": "ann_vcf_to_tsv", "label": "Annotated VCF to TSV"},
        ],
    },
]

DEFAULT_STEP_CONFIGS = {
    "prealignment": {
        "workflow": ["fastq_QC"],
        "threads": "1",
        "ram": "1g",
        "trim_adapters": {
            "tool": "CUTADAPT",
            "adapter1": "CTGTCTCTTATACACATCT",
            "adapter2": "CTGTCTCTTATACACATCT",
            "CUTADAPT": {"args": []},
        },
        "fastq_QC": {"tool": ""},
    },
    "alignment": {"workflow": ["fastq_alignment"], "threads": "2", "ram": "1g", "fastq_alignment": {"tool": ""}},
    "preprocessing": {"workflow": ["add_readgroups", "mark_pcr_dup"], "threads": "2", "ram": "8g"},
    "variantcalling": {"workflow": ["short_variants"], "tools": [], "threads": "2", "ram": "8g", "filters": {}},
    "postprocessing": {"workflow": ["vcf_to_tsv"], "threads": "2", "ram": "2g"},
    "annotation": {"workflow": ["vep_annotation", "ann_vcf_to_tsv"], "threads": "2", "ram": "8g"},
}


class PipelineError(ValueError):
    pass


def pipeline_filename(name):
    candidate = str(name or "").strip()
    if candidate.endswith(PIPELINE_SUFFIX):
        candidate = candidate[:-len(PIPELINE_SUFFIX)]
    candidate = candidate.replace(" ", "_")
    if not PIPELINE_NAME.match(candidate) or candidate in (".", ".."):
        raise PipelineError("Pipeline name may contain only letters, numbers, dots, underscores, and hyphens")
    return candidate + PIPELINE_SUFFIX


def pipeline_path(pipelines_dir, name):
    filename = pipeline_filename(name)
    root = Path(pipelines_dir).resolve()
    path = (root / filename).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise PipelineError("Pipeline file must be inside the pipelines directory")
    return path


def list_pipelines(pipelines_dir):
    root = Path(pipelines_dir)
    if not root.exists():
        return []
    return [
        {"name": item.stem, "filename": item.name, "protected": item.name in PROTECTED_PIPELINES}
        for item in sorted(root.glob("*" + PIPELINE_SUFFIX), key=lambda value: value.name.lower())
        if item.is_file()
    ]


def pipeline_tool_catalog(tools_config):
    tools_config = tools_config if isinstance(tools_config, dict) else {}
    categories = tools_config.get("tools", {})
    categories = categories if isinstance(categories, dict) else {}
    catalog = {}
    for step in PIPELINE_CATALOG:
        for operation in step["operations"]:
            operation_id = operation["id"]
            category = TOOL_CATEGORY_BY_OPERATION.get(operation_id, operation_id)
            names = categories.get(category, [])
            if not isinstance(names, list):
                names = []
            catalog[operation_id] = [tool_summary(name, tools_config) for name in names]
    return catalog


def tool_summary(name, tools_config):
    config = tools_config.get(name, {})
    config = config if isinstance(config, dict) else {}
    container = config.get("container", "")
    if isinstance(container, dict):
        container = container.get("image", "")
    return {
        "name": name,
        "version": str(config.get("version", config.get("versione", ""))),
        "path": str(config.get("path", "")),
        "container": str(container or ""),
        "configured": bool(config.get("path") or container),
    }


def load_pipeline(pipelines_dir, name):
    path = pipeline_path(pipelines_dir, name)
    if not path.is_file():
        raise PipelineError("Pipeline not found: {}".format(path.name))
    try:
        with path.open() as handle:
            config = json.load(handle)
    except (OSError, ValueError) as exc:
        raise PipelineError("Could not read {}: {}".format(path.name, exc))
    if not isinstance(config, dict):
        raise PipelineError("Pipeline must contain a JSON object")
    return {"name": path.stem, "filename": path.name, "protected": path.name in PROTECTED_PIPELINES, "config": config}


def save_pipeline(pipelines_dir, name, config, overwrite=False):
    errors, warnings = validate_pipeline(config)
    if errors:
        raise PipelineError("\n".join(errors))
    path = pipeline_path(pipelines_dir, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise PipelineError("Pipeline already exists: {}".format(path.name))

    saved = json.loads(json.dumps(config))
    saved["id"] = path.stem
    handle = tempfile.NamedTemporaryFile(mode="w", dir=str(path.parent), prefix=".pipeline-", suffix=".tmp", delete=False)
    temporary_path = Path(handle.name)
    try:
        with handle:
            json.dump(saved, handle, indent=4)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary_path), str(path))
    except Exception:
        if temporary_path.exists():
            temporary_path.unlink()
        raise
    return {"name": path.stem, "filename": path.name, "protected": path.name in PROTECTED_PIPELINES, "config": saved, "warnings": warnings}


def delete_pipeline(pipelines_dir, name):
    path = pipeline_path(pipelines_dir, name)
    if path.name in PROTECTED_PIPELINES:
        raise PipelineError("The default pipeline cannot be deleted")
    if not path.is_file():
        raise PipelineError("Pipeline not found: {}".format(path.name))
    path.unlink()
    return path.name


def validate_pipeline(config):
    errors = []
    warnings = []
    if not isinstance(config, dict):
        return ["Pipeline must contain a JSON object"], warnings

    workflow = config.get("workflow")
    if not isinstance(workflow, list) or not workflow:
        errors.append("Select at least one pipeline step")
        workflow = []
    elif len(workflow) != len(set(workflow)):
        errors.append("Pipeline workflow contains duplicate steps")

    known_steps = [step["id"] for step in PIPELINE_CATALOG]
    unknown_steps = [step for step in workflow if step not in known_steps]
    if unknown_steps:
        warnings.append("Legacy or unsupported steps are preserved but not editable: {}".format(", ".join(unknown_steps)))

    for step in workflow:
        step_config = config.get(step)
        if not isinstance(step_config, dict):
            errors.append("Step '{}' requires a configuration object".format(step))
            continue
        operations = step_config.get("workflow")
        if operations is not None and not isinstance(operations, list):
            errors.append("Step '{}.workflow' must be a list".format(step))

    if not str(config.get("analysis", "")).strip():
        warnings.append("Analysis type is not set")
    if not str(config.get("reference_version", "")).strip():
        warnings.append("Reference genome is not set")
    return errors, warnings


def new_pipeline_config(template=None):
    if template is not None:
        if not isinstance(template, dict):
            raise PipelineError("Pipeline template must be a JSON object")
        return json.loads(json.dumps(template))
    return {
        "id": "new_pipeline",
        "design": "cohort",
        "analysis": "germline",
        "reference_version": "",
        "workflow": ["prealignment", "alignment", "preprocessing", "variantcalling", "postprocessing", "annotation"],
        **json.loads(json.dumps(DEFAULT_STEP_CONFIGS))
    }
