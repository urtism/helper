import json

import pytest

from helper_next.core.tools import (
    ToolsError,
    load_tools,
    normalize_tools,
    pipeline_dependencies,
    save_tools,
    tools_path,
    validate_tools,
)


def example_config():
    return {
        "tools": {"list": ["BWA"], "fastq_alignment": ["BWA"]},
        "databases": {"list": ["dbsnp"]},
        "refGenomes_list": ["hg19"],
        "BWA": {"path": "bwa", "version": "0.7", "tags": "fastq_alignment"},
        "dbsnp": {"path": "/missing/dbsnp.vcf", "tags": "database"},
        "hg19": {"fasta": "/missing/hg19.fa", "dict": "/missing/hg19.dict", "tags": "reference"},
    }


def write_tools(configs, payload=None):
    path = configs / "tools_cfg" / "tools.cfg"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload or example_config()))
    return path


def test_legacy_lists_are_normalized_without_losing_entries():
    config = normalize_tools({"tools_list": ["BWA", "BWA"], "databases_list": ["dbsnp"]})

    assert config["tools"]["list"] == ["BWA"]
    assert config["databases"]["list"] == ["dbsnp"]
    assert config["refGenomes_list"] == []
    assert "tools_list" not in config


def test_tools_path_is_confined_and_requires_a_tool_config_name(tmp_path):
    assert tools_path(tmp_path, "tools_cfg/tools.cfg") == (tmp_path / "tools_cfg" / "tools.cfg").resolve()
    with pytest.raises(ToolsError, match="inside"):
        tools_path(tmp_path, "../tools.cfg")
    with pytest.raises(ToolsError, match="name contains"):
        tools_path(tmp_path, "settings.cfg")


def test_validation_reports_missing_entries_and_paths_as_audit_results(tmp_path):
    config = example_config()
    config["tools"]["fastq_alignment"].append("MISSING")
    del config["BWA"]

    errors, warnings = validate_tools(config, tmp_path)

    assert "Tool 'BWA' has no configuration object" in errors
    assert "Tool category 'fastq_alignment' references unknown tool 'MISSING'" in warnings
    assert any("FASTA path does not exist" in warning for warning in warnings)


def test_reference_test_checks_fasta_and_required_sidecars(tmp_path):
    from helper_next.core.tools import test_resource as check_resource

    fasta = tmp_path / "hg19.fa"
    fasta.write_text(">chr1\nA\n")
    result = check_resource("reference", "hg19", {"fasta": str(fasta)})
    assert result["ok"] is False
    assert [check["label"] for check in result["checks"]] == ["FASTA", "FASTA index", "Sequence dictionary"]

    (tmp_path / "hg19.fa.fai").write_text("chr1\t1\t6\t1\t2\n")
    (tmp_path / "hg19.dict").write_text("@HD\tVN:1.6\n")
    assert check_resource("reference", "hg19", {"fasta": str(fasta)})["ok"] is True


def test_pipeline_dependencies_find_resource_values_and_keys(tmp_path):
    pipelines = tmp_path / "pipelines"
    pipelines.mkdir()
    (pipelines / "one.pipeline").write_text(json.dumps({"reference_version": "hg19", "alignment": {"tool": "BWA"}}))

    dependencies = pipeline_dependencies(example_config(), pipelines)

    assert dependencies["BWA"] == ["one.pipeline"]
    assert dependencies["hg19"] == ["one.pipeline"]
    assert dependencies["dbsnp"] == []


def test_save_is_atomic_creates_backup_and_checks_revision(tmp_path):
    configs = tmp_path / "configs"
    pipelines = configs / "pipelines"
    pipelines.mkdir(parents=True)
    path = write_tools(configs)
    path.chmod(0o640)
    loaded = load_tools(configs, pipelines)
    changed = loaded["config"]
    changed["BWA"]["version"] = "0.8"

    saved = save_tools(configs, pipelines, loaded["filename"], changed, loaded["revision"])

    assert saved["config"]["BWA"]["version"] == "0.8"
    assert path.stat().st_mode & 0o777 == 0o640
    assert json.loads((path.with_name("tools.cfg.bak")).read_text())["BWA"]["version"] == "0.7"
    assert not list(path.parent.glob(".tools-*.tmp"))
    with pytest.raises(ToolsError, match="changed on disk"):
        save_tools(configs, pipelines, loaded["filename"], changed, loaded["revision"])


def test_save_blocks_removing_a_resource_used_by_a_pipeline(tmp_path):
    configs = tmp_path / "configs"
    pipelines = configs / "pipelines"
    pipelines.mkdir(parents=True)
    write_tools(configs)
    (pipelines / "used.pipeline").write_text(json.dumps({"alignment": {"tool": "BWA"}}))
    loaded = load_tools(configs, pipelines)
    changed = loaded["config"]
    changed["tools"]["list"].remove("BWA")
    changed["tools"]["fastq_alignment"].remove("BWA")
    del changed["BWA"]

    with pytest.raises(ToolsError, match="used by used.pipeline"):
        save_tools(configs, pipelines, loaded["filename"], changed, loaded["revision"])
