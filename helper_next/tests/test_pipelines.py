import json
import shlex
from pathlib import Path

import pytest

from helper_next.api.analysis import normalize_pipeline_for_nextflow
from helper_next.core.pipelines import (
    PIPELINE_CATALOG,
    PipelineError,
    delete_pipeline,
    list_pipelines,
    load_pipeline,
    new_pipeline_config,
    pipeline_filename,
    pipeline_tool_catalog,
    save_pipeline,
    validate_pipeline,
)
from helper_next.core.tool_resolver import resolve_pipeline_tools


def valid_pipeline():
    return {
        "id": "Example",
        "analysis": "germline",
        "design": "cohort",
        "reference_version": "hg19",
        "workflow": ["alignment"],
        "alignment": {
            "workflow": ["fastq_alignment"],
            "threads": "2",
            "ram": "2g",
            "fastq_alignment": {"tool": "BWA v.0.7.17"},
        },
    }


def test_pipeline_name_is_normalized_and_confined():
    assert pipeline_filename("My pipeline") == "My_pipeline.pipeline"
    assert pipeline_filename("example.pipeline") == "example.pipeline"
    with pytest.raises(PipelineError):
        pipeline_filename("../outside")
    with pytest.raises(PipelineError):
        pipeline_filename("bad/name")


def test_pipeline_round_trip_uses_atomic_save_and_does_not_mutate_input(tmp_path):
    pipelines = tmp_path / "pipelines"
    config = valid_pipeline()

    saved = save_pipeline(pipelines, "My pipeline", config)

    assert saved["filename"] == "My_pipeline.pipeline"
    assert config["id"] == "Example"
    assert load_pipeline(pipelines, "My_pipeline")["config"]["id"] == "My_pipeline"
    assert list_pipelines(pipelines) == [
        {"name": "My_pipeline", "filename": "My_pipeline.pipeline", "protected": False}
    ]
    assert not list(pipelines.glob(".pipeline-*.tmp"))


def test_existing_pipeline_requires_explicit_overwrite(tmp_path):
    save_pipeline(tmp_path, "example", valid_pipeline())
    with pytest.raises(PipelineError, match="already exists"):
        save_pipeline(tmp_path, "example", valid_pipeline())

    changed = valid_pipeline()
    changed["analysis"] = "somatic"
    save_pipeline(tmp_path, "example", changed, overwrite=True)
    assert load_pipeline(tmp_path, "example")["config"]["analysis"] == "somatic"


def test_default_pipeline_is_protected_from_deletion(tmp_path):
    (tmp_path / "default.pipeline").write_text(json.dumps(valid_pipeline()))
    with pytest.raises(PipelineError, match="cannot be deleted"):
        delete_pipeline(tmp_path, "default")


def test_delete_pipeline_removes_only_selected_file(tmp_path):
    save_pipeline(tmp_path, "one", valid_pipeline())
    save_pipeline(tmp_path, "two", valid_pipeline())

    assert delete_pipeline(tmp_path, "one") == "one.pipeline"
    assert not (tmp_path / "one.pipeline").exists()
    assert (tmp_path / "two.pipeline").exists()


def test_validation_reports_errors_and_preserves_legacy_steps_as_warnings():
    config = valid_pipeline()
    config["workflow"].append("postannotation")
    config["postannotation"] = {"workflow": []}
    errors, warnings = validate_pipeline(config)
    assert errors == []
    assert "postannotation" in warnings[0]

    config["workflow"] = []
    errors, _ = validate_pipeline(config)
    assert errors == ["Select at least one pipeline step"]


def test_new_pipeline_template_is_deep_copied():
    source = valid_pipeline()
    draft = new_pipeline_config(source)
    draft["alignment"]["threads"] = "12"
    assert source["alignment"]["threads"] == "2"

    blank = new_pipeline_config()
    assert blank["workflow"]
    assert blank["analysis"] == "germline"
    assert blank["prealignment"]["trim_adapters"]["tool"] == "CUTADAPT"


def test_pipeline_catalog_exposes_adapter_trimming_before_fastq_qc():
    prealignment = next(step for step in PIPELINE_CATALOG if step["id"] == "prealignment")
    assert [operation["id"] for operation in prealignment["operations"]] == ["trim_adapters", "fastq_QC"]


def test_pipeline_catalog_exposes_bam_qc_as_last_preprocessing_operation():
    preprocessing = next(step for step in PIPELINE_CATALOG if step["id"] == "preprocessing")

    assert preprocessing["operations"][-1] == {"id": "bam_QC", "label": "BAM quality control"}


def test_pipeline_catalog_exposes_multi_vcf_merge_after_filtering():
    postprocessing = next(step for step in PIPELINE_CATALOG if step["id"] == "postprocessing")

    operation_ids = [operation["id"] for operation in postprocessing["operations"]]
    assert operation_ids.index("multi_vcf_merge") == operation_ids.index("vcf_filter") + 1


def test_variant_calling_catalog_exposes_all_variant_classes():
    variantcalling = next(step for step in PIPELINE_CATALOG if step["id"] == "variantcalling")
    assert [operation["id"] for operation in variantcalling["operations"]] == [
        "short_variants",
        "cnv_calling",
        "sv_calling",
        "methylation",
    ]
    assert new_pipeline_config()["variantcalling"]["workflow"] == ["short_variants"]


def test_tool_catalog_maps_pipeline_operations_to_tools_config_categories():
    tools = {
        "tools": {
            "trim_adapters": ["CUTADAPT", "MISSING"],
            "variantcalling": ["GATK v.4.3"],
            "cnvcalling": ["CNVKIT"],
        },
        "CUTADAPT": {"path": "cutadapt", "version": "4.9"},
        "GATK v.4.3": {"container": {"image": "gatk:4.3"}},
    }

    catalog = pipeline_tool_catalog(tools)

    assert catalog["trim_adapters"][0] == {
        "name": "CUTADAPT",
        "version": "4.9",
        "path": "cutadapt",
        "container": "",
        "configured": True,
    }
    assert catalog["trim_adapters"][1]["configured"] is False
    assert catalog["short_variants"][0]["container"] == "gatk:4.3"
    assert catalog["cnv_calling"][0]["name"] == "CNVKIT"
    assert catalog["sv_calling"] == []


def test_tool_choices_and_parameters_survive_pipeline_round_trip(tmp_path):
    config = new_pipeline_config()
    config["reference_version"] = "hg19"
    config["prealignment"]["workflow"] = ["trim_adapters", "fastq_QC"]
    config["prealignment"]["trim_adapters"]["CUTADAPT"]["args"] = ["--minimum-length", "75"]
    config["variantcalling"]["workflow"] = ["short_variants", "cnv_calling", "methylation"]
    config["variantcalling"]["tools"] = ["GATK v.4.3", "FREEBAYES v.1.1"]
    config["variantcalling"]["GATK v.4.3"] = {"args": ["--dont-use-soft-clipped-bases"]}
    config["cnvcalling"] = {"tools": ["CNVKIT"], "threads": "4", "ram": "12g", "CNVKIT": {"args": ["--method", "hybrid"]}}
    config["methylation"] = {"tools": ["CustomMethyl"], "threads": "2", "ram": "4g", "CustomMethyl": {"args": ["--preset", "cpg"]}}

    save_pipeline(tmp_path, "configured", config)
    loaded = load_pipeline(tmp_path, "configured")["config"]

    assert loaded["prealignment"]["trim_adapters"]["CUTADAPT"]["args"] == ["--minimum-length", "75"]
    assert loaded["variantcalling"]["tools"] == ["GATK v.4.3", "FREEBAYES v.1.1"]
    assert loaded["cnvcalling"]["CNVKIT"]["args"] == ["--method", "hybrid"]
    assert loaded["methylation"]["CustomMethyl"]["args"] == ["--preset", "cpg"]


def test_legacy_annotation_presets_resolve_with_matching_vep_cache_and_container():
    repository = Path(__file__).resolve().parents[2]
    tools = json.loads((repository / "configs/tools_cfg/tools.cfg").read_text())

    for path in sorted((repository / "configs/pipelines").glob("*.pipeline")):
        original = json.loads(path.read_text())
        pipeline = normalize_pipeline_for_nextflow(original)
        if "annotation" not in pipeline["workflow"]:
            continue

        resolved = resolve_pipeline_tools(pipeline, tools)
        vep = resolved["annotation"]["vep_annotation"]
        tool_name = vep["tool"]
        args = shlex.split(vep[tool_name]["resolved_args"])
        version = tools[tool_name]["version"]
        assembly = "GRCh38" if pipeline["reference_version"] == "hg38" else "GRCh37"

        assert tools[tool_name]["container"]["image"].startswith(f"ensemblorg/ensembl-vep:release_{version}.")
        assert args[args.index("--cache_version") + 1] == version
        assert args[args.index("--assembly") + 1] == assembly
        assert args.count("--cache") == args.count("--offline") == args.count("--merged") == 1
        assert args.count("--vcf_info_field") == 1
        assert args[args.index("--vcf_info_field") + 1] == "ANN"
        assert "--af_esp" not in args
        assert "--plugin" not in args
        legacy = original["variant_annotation"]
        legacy_args = legacy[legacy["tool"]]["args"]
        if isinstance(legacy_args, dict):
            legacy_args = legacy_args["args"]
        for flag in legacy_args:
            if str(flag).startswith("--") and flag not in {"--af_esp", "--force_overwrite"}:
                assert flag in args, (path.name, flag)
