import json
import ast
from pathlib import Path

from helper_next.core.tool_resolver import resolve_pipeline_tools
from helper_next.core.tool_wrappers import (
    BwaAlignmentWrapper,
    ContainerSpec,
    CutadaptTrimmingWrapper,
    PicardMarkDuplicatesWrapper,
    QualimapBamQcWrapper,
    SurecallTrimmingWrapper,
    VepAnnotationWrapper,
    operation_spec,
    build_invocation,
)
from helper_next.core.tool_wrappers.catalog import SCRIPT_OPERATIONS


def test_bwa_wrapper_builds_serializable_invocation_from_pipeline_and_tools_cfg():
    wrapper = BwaAlignmentWrapper(
        {"algorithm": "mem", "args": ["-M"], "threads": "8"},
        {"path": "/tools/bwa", "version": "0.7.17"},
        reference_info={"fasta": "/refs/hg19.fa"},
    )

    invocation = wrapper.build("BWA v.0.7.17", "fastq_alignment")
    payload = invocation.to_dict()

    assert payload["tool"] == "BWA v.0.7.17"
    assert payload["executable"] == "/tools/bwa"
    assert payload["version"] == "0.7.17"
    assert payload["command_args"][:4] == ["mem", "/refs/hg19.fa", "{fastq_r1}", "{fastq_r2}"]
    assert "-M" in payload["command_args"]
    assert payload["inputs"][0]["path"] == "/refs/hg19.fa"
    assert json.loads(invocation.to_json())["executable"] == "/tools/bwa"


def test_cutadapt_wrapper_adds_default_adapters_and_preserves_extra_args():
    invocation = CutadaptTrimmingWrapper(
        {"adapter1": "AD1", "adapter2": "AD2", "args": ["--minimum-length", "75"]},
        {"path": "cutadapt", "version": "1.13"},
    ).build("CUTADAPT", "trim_adapters")

    assert invocation.executable == "cutadapt"
    assert invocation.command_args[:4] == ["-a", "AD1", "-A", "AD2"]
    assert ["--minimum-length", "75"] == invocation.command_args[4:6]
    assert invocation.outputs[0].path == "{sample_name}.R1.trim.fastq.gz"


def test_cutadapt_wrapper_does_not_duplicate_custom_adapter_arguments():
    invocation = CutadaptTrimmingWrapper(
        {"adapter1": "DEFAULT", "adapter2": "DEFAULT", "args": ["-g", "CUSTOM"]},
        {"path": "cutadapt"},
    ).build("CUTADAPT", "trim_adapters")

    assert invocation.command_args[:2] == ["-g", "CUSTOM"]
    assert "DEFAULT" not in invocation.command_args


def test_surecall_wrapper_builds_java_jar_invocation_with_tool_ram():
    invocation = SurecallTrimmingWrapper(
        {"args": ["-hs"]},
        {"path": "/tools/SurecallTrimmer.jar", "ram": "32g", "version": "3.5.1.46"},
    ).build("SURECALLTRIMMER v.3.5.1.46", "trim_adapters")

    assert invocation.executable == "java"
    assert invocation.command_args[:3] == ["-Xmx32g", "-jar", "/tools/SurecallTrimmer.jar"]
    assert "-fq1" in invocation.command_args
    assert "-fq2" in invocation.command_args
    assert invocation.command_args[-1] == "-hs"


def test_container_spec_is_populated_from_tool_cfg():
    spec = ContainerSpec.from_tool_config(
        {
            "container": {
                "engine": "apptainer",
                "image": "/containers/bwa.sif",
                "bind_mounts": ["/refs:/refs"],
                "workdir": "/work",
                "env": {"LC_ALL": "C"},
                "extra_args": ["--cleanenv"],
            }
        }
    )

    assert spec.engine == "apptainer"
    assert spec.image == "/containers/bwa.sif"
    assert spec.bind_mounts == ["/refs:/refs"]
    assert spec.env["LC_ALL"] == "C"


def test_picard_mark_duplicates_wrapper_declares_outputs_without_subprocess():
    wrapper = PicardMarkDuplicatesWrapper({"args": ["REMOVE_DUPLICATES=false"]}, {"path": "/tools/picard.jar", "ram": "8g"})

    invocation = wrapper.build("PICARD v.2.7.1", "mark_pcr_dup").to_dict()

    assert invocation["executable"] == "/tools/picard.jar"
    assert "MarkDuplicates" in invocation["command_args"]
    assert "REMOVE_DUPLICATES=false" in invocation["command_args"]
    assert {output["name"] for output in invocation["outputs"]} == {"bam", "metrics"}
    assert "subprocess" not in " ".join(invocation["command_args"])


def test_qualimap_bam_qc_wrapper_declares_container_ready_invocation():
    invocation = QualimapBamQcWrapper(
        {"threads": "6", "args": ["-gff", "/panel/targets.bed", "-os"]},
        {
            "path": "qualimap",
            "version": "2.3",
            "container": {"engine": "docker", "image": "staphb/qualimap:latest"},
        },
        panel_design={"assets": {"target_bed": "/panel/automatic.bed"}},
    ).build("QUALIMAP v.2.3", "bam_QC").to_dict()

    assert invocation["command_args"][:5] == ["bamqc", "-bam", "{bam}", "-nt", "6"]
    assert ["-outdir", "{sample_name}.qualimap"] == invocation["command_args"][5:7]
    assert invocation["command_args"][-3:] == ["-gff", "/panel/targets.bed", "-os"]
    assert invocation["command_args"].count("-gff") == 1
    assert invocation["container"]["image"] == "staphb/qualimap:latest"
    assert invocation["outputs"][0]["kind"] == "directory"


def test_resolver_embeds_selected_qualimap_bam_qc_invocation():
    pipeline = {
        "workflow": ["alignment"],
        "reference_version": "hg19",
        "alignment": {
            "workflow": ["fastq_alignment", "bam_QC"],
            "threads": "4",
            "ram": "6g",
            "fastq_alignment": {"tool": "BWA v.0.7.17"},
            "bam_QC": {
                "tool": "QUALIMAP v.2.3",
                "QUALIMAP v.2.3": {"args": ["-nr", "2000"]},
            },
        },
    }
    tools = {
        "hg19": {"fasta": "/refs/hg19.fa"},
        "BWA v.0.7.17": {"path": "bwa"},
        "SAMTOOLS": {"path": "samtools"},
        "QUALIMAP v.2.3": {
            "path": "qualimap",
            "container": {"engine": "docker", "image": "staphb/qualimap:latest"},
        },
    }

    panel = {"assets": {"target_bed": "/targets/analysis-panel.bed"}}
    resolved = resolve_pipeline_tools(pipeline, tools, panel)["alignment"]["resolved"]["bam_QC"]

    assert resolved["resolved_args"] == "-nr 2000 -gff /targets/analysis-panel.bed"
    assert resolved["container"]["image"] == "staphb/qualimap:latest"
    assert resolved["invocation"]["resources"] == {"threads": "4", "ram": "6g"}
    assert resolved["invocation"]["command_args"][:5] == ["bamqc", "-bam", "{bam}", "-nt", "4"]
    assert resolved["invocation"]["inputs"][2]["path"] == "/targets/analysis-panel.bed"


def test_resolver_parses_each_qualimap_setting_row_as_one_option():
    pipeline = {
        "workflow": ["alignment"],
        "reference_version": "hg19",
        "alignment": {
            "workflow": ["fastq_alignment", "bam_QC"],
            "threads": "2",
            "ram": "4g",
            "fastq_alignment": {"tool": "BWA v.0.7.17"},
            "bam_QC": {
                "tool": "QUALIMAP v.2.3",
                "QUALIMAP v.2.3": {"args": ["-os", "-ip", "-cl 1000"]},
            },
        },
    }
    tools = {
        "hg19": {"fasta": "/refs/hg19.fa"},
        "BWA v.0.7.17": {"path": "bwa"},
        "SAMTOOLS": {"path": "samtools"},
        "QUALIMAP v.2.3": {"path": "qualimap"},
    }

    resolved = resolve_pipeline_tools(pipeline, tools)["alignment"]["resolved"]["bam_QC"]

    assert resolved["args"] == ["-os", "-ip", "-cl", "1000"]
    assert resolved["resolved_args"] == "-os -ip -cl 1000"


def test_resolver_embeds_qualimap_after_preprocessing_with_analysis_bed():
    pipeline = {
        "workflow": ["preprocessing"],
        "reference_version": "hg19",
        "preprocessing": {
            "workflow": ["mark_pcr_dup", "bam_QC"],
            "threads": "6",
            "ram": "8g",
            "mark_pcr_dup": {"tool": "PICARD v.2.7.1"},
            "bam_QC": {"tool": "QUALIMAP v.2.3", "QUALIMAP v.2.3": {"args": ["-os"]}},
        },
    }
    tools = {
        "hg19": {"fasta": "/refs/hg19.fa"},
        "SAMTOOLS": {"path": "samtools"},
        "PICARD v.2.7.1": {"path": "/tools/picard.jar"},
        "GATK v.3.7": {"path": "/tools/gatk3.jar"},
        "QUALIMAP v.2.3": {
            "path": "qualimap",
            "container": {"engine": "docker", "image": "staphb/qualimap:latest"},
        },
    }
    panel = {"assets": {"target_bed": "/targets/analysis-panel.bed"}}

    resolved = resolve_pipeline_tools(pipeline, tools, panel)["preprocessing"]["resolved"]["bam_QC"]

    assert resolved["resolved_args"] == "-os -gff /targets/analysis-panel.bed"
    assert resolved["invocation"]["metadata"]["operation"] == "bam_QC"
    assert resolved["invocation"]["container"]["image"] == "staphb/qualimap:latest"


def test_vep_wrapper_reuses_legacy_args_and_tools_cfg_plugin_paths():
    wrapper = VepAnnotationWrapper(
        {
            "args": {
                "args": ["--cache", "--offline"],
                "features": ["--symbol"],
                "af": ["--af"],
                "assembly": "GRCh37",
                "species": "homo_sapiens",
                "plugins": {"list": ["GeneSplicer"], "GeneSplicer": {"fields": "human"}},
            }
        },
        {"path": "/tools/vep", "version": "95"},
        panel_design={"assets": {"transcripts_list": "/panels/transcripts.txt"}},
        reference_info={"fasta": "/refs/hg19.fa"},
        tools_config={"GeneSplicer": {"path": "/plugins/genesplicer"}},
    )

    invocation = wrapper.build("VEP v.95", "vep_annotation").to_dict()

    assert invocation["executable"] == "/tools/vep"
    assert "--plugin" in invocation["command_args"]
    assert "GeneSplicer,/plugins/genesplicer,human" in invocation["command_args"]
    assert ["--assembly", "GRCh37"] == invocation["command_args"][invocation["command_args"].index("--assembly") : invocation["command_args"].index("--assembly") + 2]
    assert "/panels/transcripts.txt" in invocation["command_args"]


def test_containerized_vep_wrapper_uses_container_executable_and_normalized_args():
    invocation = VepAnnotationWrapper(
        {"args": ["--cache", "--cache_version 116", "--assembly GRCh37"]},
        {"version": "116", "container": {"engine": "docker", "image": "ensemblorg/ensembl-vep:release_116.0"}},
    ).build("VEP v.116", "vep_annotation")

    assert invocation.executable == "vep"
    assert invocation.command_args[-5:] == ["--cache", "--cache_version", "116", "--assembly", "GRCh37"]


def test_registry_covers_initial_ngs_wrappers():
    cases = [
        ("fastq_alignment", "BWA v.0.7.17"),
        ("fastq_alignment", "BOWTIE2 v.2.3.5.1"),
        ("bam_QC", "QUALIMAP v.2.3"),
        ("samtools", "SAMTOOLS"),
        ("add_readgroups", "PICARD v.2.7.1"),
        ("mark_pcr_dup", "PICARD v.2.7.1"),
        ("indel_realignment", "GATK v.3.7"),
        ("BQ_recalibration", "GATK v.3.7"),
        ("caller", "GATK v.4.1"),
        ("vcf_norm", "BCFTOOLS"),
        ("vcf_filter", "GATK v.4.1"),
        ("vep_annotation", "VEP v.95"),
    ]

    for operation, tool_name in cases:
        invocation = build_invocation(
            operation,
            tool_name,
            {"args": ["--flag"]},
            {"path": "/tools/{}".format(tool_name.split()[0].lower())},
            {"assets": {"target_bed": "/panel/targets.bed"}},
            {"fasta": "/refs/ref.fa"},
            {},
        )
        assert invocation is not None, (operation, tool_name)
        assert invocation.executable.startswith("/tools/")


def test_resolver_embeds_wrapper_invocations_while_preserving_legacy_fields():
    pipeline = {
        "workflow": ["alignment", "preprocessing", "variantcalling", "postprocessing", "annotation"],
        "reference_version": "hg19",
        "alignment": {
            "workflow": ["fastq_alignment"],
            "fastq_alignment": {"tool": "BWA v.0.7.17", "BWA v.0.7.17": {"args": ["-M"]}},
        },
        "preprocessing": {
            "workflow": ["add_readgroups", "mark_pcr_dup", "indel_realignment", "BQ_recalibration"],
            "add_readgroups": {"tool": "PICARD v.2.7.1"},
            "mark_pcr_dup": {"tool": "PICARD v.2.7.1", "PICARD v.2.7.1": {"args": ["REMOVE_DUPLICATES=false"]}},
            "indel_realignment": {"tool": "GATK v.3.7", "GATK v.3.7": {"mills": "mills"}},
            "BQ_recalibration": {"tool": "GATK v.3.7", "GATK v.3.7": {"dbsnp": "dbsnp", "mills": "mills"}},
        },
        "variantcalling": {"tools": ["GATK v.4.1"], "GATK v.4.1": {"args": ["--sample-ploidy", "2"]}},
        "postprocessing": {
            "workflow": ["vcf_norm", "vcf_filter"],
            "vcf_norm": {"tool": "BCFTOOLS", "BCFTOOLS": {"args": ["-m", "-any"]}},
            "vcf_filter": {"tool": "GATK v.4.1", "GATK v.4.1": {"args": ["--filter-name", "QD2"]}},
        },
        "annotation": {
            "workflow": ["vep_annotation"],
            "vep_annotation": {
                "tool": "VEP v.95",
                "VEP v.95": {"args": {"args": ["--cache"], "plugins": {"list": ["dbNSFP"]}}},
            },
        },
    }
    tools = {
        "hg19": {"fasta": "/refs/hg19.fa"},
        "BWA v.0.7.17": {"path": "/tools/bwa", "container": {"engine": "docker", "image": "bwa:0.7.17"}},
        "SAMTOOLS": {"path": "/tools/samtools"},
        "PICARD v.2.7.1": {"path": "/tools/picard.jar"},
        "GATK v.3.7": {"path": "/tools/GenomeAnalysisTK.jar"},
        "GATK v.4.1": {"path": "/tools/gatk"},
        "BCFTOOLS": {"path": "/tools/bcftools"},
        "VEP v.95": {"path": "/tools/vep"},
        "dbsnp": {"path": "/refs/dbsnp.vcf"},
        "mills": {"path": "/refs/mills.vcf"},
        "dbNSFP": {"path": "/db/dbNSFP.gz"},
    }
    panel = {"assets": {"target_bed": "/panels/targets.bed", "transcripts_list": "/panels/transcripts.txt"}}

    resolved = resolve_pipeline_tools(pipeline, tools, panel)

    alignment = resolved["alignment"]["resolved"]["fastq_alignment"]
    assert alignment["path"] == "/tools/bwa"
    assert alignment["resolved_args"] == "-M"
    assert alignment["invocation"]["container"]["image"] == "bwa:0.7.17"
    assert alignment["invocation"]["inputs"][0]["path"] == "/refs/hg19.fa"
    assert resolved["preprocessing"]["resolved"]["indel_realignment"]["invocation"]["inputs"][2]["path"] == "/refs/mills.vcf"
    assert resolved["preprocessing"]["resolved"]["BQ_recalibration"]["invocation"]["inputs"][2]["path"] == "/refs/dbsnp.vcf"
    assert resolved["variantcalling"]["resolved"]["caller"]["invocation"]["inputs"][2]["path"] == "/panels/targets.bed"
    assert "/panels/transcripts.txt" in resolved["annotation"]["resolved"]["vep_annotation"]["invocation"]["command_args"]


def test_catalog_covers_legacy_tool_functions_and_methods():
    root = Path(__file__).resolve().parents[2]
    ignored = {
        "__init__",
        "init_tool",
        "checksubstring",
        "check_version_gatk",
        "add_vep_plugins",
        "SelectVariants",
        "VariantAnnotator",
        "VariantFiltration",
        "MuTect2",
    }
    missing = []

    for relative in ("bin/tools.py", "bin/tools2.py", "bin/parallel_tools.py"):
        tree = ast.parse((root / relative).read_text(errors="ignore"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name not in ignored:
                if node.name == "main":
                    continue
                if not (operation_spec(node.name) or build_invocation(node.name, node.name, {}, {"path": node.name})):
                    missing.append("{}:{}".format(relative, node.name))
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if not isinstance(item, ast.FunctionDef) or item.name in ignored:
                        continue
                    qualified = "{}.{}".format(node.name, item.name)
                    if not (operation_spec(qualified) or operation_spec(item.name) or build_invocation(item.name, node.name, {}, {"path": node.name})):
                        missing.append("{}:{}".format(relative, qualified))

    assert missing == []


def test_catalog_covers_helper_scripts_and_builds_script_invocations():
    root = Path(__file__).resolve().parents[2]
    script_files = sorted(path.name for path in (root / "scripts").glob("*.py"))
    catalog_scripts = sorted(SCRIPT_OPERATIONS.values())

    assert script_files == catalog_scripts

    invocation = build_invocation(
        "vcf_to_tsv",
        "vcf_to_tsv",
        {"params": {"vcf": "{vcf}", "out": "{sample_name}.tsv"}},
        {"scripts_dir": "scripts"},
    ).to_dict()

    assert invocation["executable"] == "python"
    assert invocation["command_args"][:2] == ["scripts/vcf_to_tsv.py", "--vcf"]
    assert "--out" in invocation["command_args"]
    assert invocation["metadata"]["script"] == "vcf_to_tsv.py"
