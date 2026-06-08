import csv

import pytest

from helper_next.core.nextflow import (
    ValidationError,
    build_nextflow_run_config,
    manifest_rows,
    validate_nextflow_inputs,
    write_manifest,
)


def test_manifest_rows_preserve_trio_roles():
    samplesheet = {
        "sample_list": ["FAM1"],
        "sample_organization": "trio",
        "alignment": {
            "FAM1": {
                "case": {
                    "sample_name": "CHILD",
                    "fastq_R1": "/data/child_R1.fastq.gz",
                    "fastq_R2": "/data/child_R2.fastq.gz",
                    "fastq_I2": "",
                },
                "parent1": {
                    "sample_name": "MOTHER",
                    "fastq_R1": "/data/mother_R1.fastq.gz",
                    "fastq_R2": "/data/mother_R2.fastq.gz",
                    "fastq_I2": "",
                },
                "parent2": {
                    "sample_name": "FATHER",
                    "fastq_R1": "/data/father_R1.fastq.gz",
                    "fastq_R2": "/data/father_R2.fastq.gz",
                    "fastq_I2": "",
                },
            }
        },
    }

    rows = manifest_rows(samplesheet)

    assert [row["role"] for row in rows] == ["case", "parent1", "parent2"]
    assert rows[0]["sample_id"] == "FAM1"
    assert rows[0]["sample_name"] == "CHILD"
    assert rows[1]["fastq_r1"] == "/data/mother_R1.fastq.gz"


def test_write_manifest_outputs_tsv_with_stable_columns(tmp_path):
    out = tmp_path / "manifest.tsv"
    rows = [
        {
            "sample_id": "S1",
            "role": "case",
            "sample_name": "S1",
            "bam": "/data/S1.bam",
        }
    ]

    write_manifest(rows, out)

    with out.open() as handle:
        parsed = list(csv.DictReader(handle, delimiter="\t"))

    assert parsed == [
        {
            "sample_id": "S1",
            "role": "case",
            "sample_name": "S1",
            "fastq_r1": "",
            "fastq_r2": "",
            "fastq_i2": "",
            "bam": "/data/S1.bam",
            "merged_vcf": "",
            "variants_tsv": "",
        }
    ]


def test_build_nextflow_run_config_keeps_json_workflow_and_resources():
    samplesheet = {
        "sample_list": ["S1"],
        "sample_organization": "only cases",
        "variantcalling": {"S1": {"case": {"sample_name": "S1", "bam": "/data/S1.bam"}}},
    }
    pipeline = {
        "analysis": "Germline",
        "reference_version": "hg19",
        "workflow": ["alignment", "variantcalling", "postprocessing"],
        "alignment": {"workflow": ["fastq_alignment"], "threads": "6", "ram": "8g"},
        "variantcalling": {"tools": ["GATK v.4.1"], "threads": "4", "ram": "12g"},
    }
    tools = {"hg19": {"fasta": "/refs/hg19.fa"}}

    config = build_nextflow_run_config(samplesheet, pipeline, tools, requested_workflow="variantcalling")

    assert config["entry_step"] == "variantcalling"
    assert config["reference_fasta"] == "/refs/hg19.fa"
    assert config["workflow"] == ["variantcalling"]
    assert config["steps"] == [{"step": "variantcalling", "threads": "4", "ram": "12g", "tools": ["GATK v.4.1"]}]


def test_validate_nextflow_inputs_accepts_configured_alignment():
    samplesheet = {
        "sample_list": ["S1"],
        "sample_organization": "only cases",
        "alignment": {
            "S1": {
                "case": {
                    "sample_name": "S1",
                    "fastq_R1": "/data/S1_R1.fastq.gz",
                    "fastq_R2": "/data/S1_R2.fastq.gz",
                    "fastq_I2": "",
                }
            }
        },
    }
    pipeline = {
        "analysis": "Germline",
        "reference_version": "hg19",
        "workflow": ["alignment"],
        "alignment": {
            "workflow": ["fastq_alignment"],
            "threads": "6",
            "ram": "8g",
            "fastq_alignment": {"tool": "BWA v.0.7.17"},
        },
    }
    tools = {
        "hg19": {"fasta": "/refs/hg19.fa"},
        "BWA v.0.7.17": {"path": "bwa"},
    }

    assert validate_nextflow_inputs(samplesheet, pipeline, tools) is True


@pytest.mark.parametrize(
    "tool_name,tool_path",
    [
        ("BWA v.0.7.17", "bwa"),
        ("BOWTIE2", "bowtie2"),
        ("NOVOALIGN", "novoalign"),
    ],
)
def test_validate_nextflow_inputs_accepts_supported_aligners(tool_name, tool_path):
    samplesheet = {
        "sample_list": ["S1"],
        "sample_organization": "only cases",
        "alignment": {
            "S1": {
                "case": {
                    "sample_name": "S1",
                    "fastq_R1": "/data/S1_R1.fastq.gz",
                    "fastq_R2": "/data/S1_R2.fastq.gz",
                    "fastq_I2": "",
                }
            }
        },
    }
    pipeline = {
        "analysis": "Germline",
        "reference_version": "hg19",
        "workflow": ["alignment"],
        "alignment": {
            "workflow": ["fastq_alignment"],
            "threads": "6",
            "ram": "8g",
            "fastq_alignment": {"tool": tool_name, tool_name: {"args": []}},
        },
    }
    tools = {
        "hg19": {"fasta": "/refs/hg19.fa"},
        tool_name: {"path": tool_path},
    }

    assert validate_nextflow_inputs(samplesheet, pipeline, tools) is True


def test_validate_nextflow_inputs_reports_unsupported_aligner():
    samplesheet = {
        "sample_list": ["S1"],
        "sample_organization": "only cases",
        "alignment": {
            "S1": {
                "case": {
                    "sample_name": "S1",
                    "fastq_R1": "/data/S1_R1.fastq.gz",
                    "fastq_R2": "/data/S1_R2.fastq.gz",
                    "fastq_I2": "",
                }
            }
        },
    }
    pipeline = {
        "analysis": "Germline",
        "reference_version": "hg19",
        "workflow": ["alignment"],
        "alignment": {
            "workflow": ["fastq_alignment"],
            "threads": "6",
            "ram": "8g",
            "fastq_alignment": {"tool": "MINIMAP2", "MINIMAP2": {"args": []}},
        },
    }
    tools = {
        "hg19": {"fasta": "/refs/hg19.fa"},
        "MINIMAP2": {"path": "minimap2"},
    }

    with pytest.raises(ValidationError) as exc:
        validate_nextflow_inputs(samplesheet, pipeline, tools)

    assert "pipeline.alignment.fastq_alignment: unsupported aligner 'MINIMAP2'" in exc.value.errors


def test_validate_nextflow_inputs_reports_missing_tool():
    samplesheet = {
        "sample_list": ["S1"],
        "sample_organization": "only cases",
        "variantcalling": {"S1": {"case": {"sample_name": "S1", "bam": "/data/S1.bam"}}},
    }
    pipeline = {
        "analysis": "Germline",
        "reference_version": "hg19",
        "workflow": ["variantcalling"],
        "variantcalling": {"tools": ["GATK v.4.1"], "threads": "4", "ram": "12g", "filters": {}},
    }
    tools = {"hg19": {"fasta": "/refs/hg19.fa"}}

    with pytest.raises(ValidationError) as exc:
        validate_nextflow_inputs(samplesheet, pipeline, tools)

    assert "tools.GATK v.4.1: selected tool is not configured" in exc.value.errors


def test_validate_nextflow_inputs_reports_missing_entry_files():
    samplesheet = {
        "sample_list": ["S1"],
        "sample_organization": "only cases",
        "alignment": {
            "S1": {
                "case": {
                    "sample_name": "S1",
                    "fastq_R1": "/data/S1_R1.fastq.gz",
                    "fastq_R2": "",
                    "fastq_I2": "",
                }
            }
        },
    }
    pipeline = {
        "analysis": "Germline",
        "reference_version": "hg19",
        "workflow": ["alignment"],
        "alignment": {
            "workflow": ["fastq_alignment"],
            "threads": "6",
            "ram": "8g",
            "fastq_alignment": {"tool": "BWA v.0.7.17"},
        },
    }
    tools = {
        "hg19": {"fasta": "/refs/hg19.fa"},
        "BWA v.0.7.17": {"path": "bwa"},
    }

    with pytest.raises(ValidationError) as exc:
        validate_nextflow_inputs(samplesheet, pipeline, tools)

    assert "samplesheet.alignment.S1.case: missing fastq_r2" in exc.value.errors


def test_validate_nextflow_inputs_accepts_variant_annotation_entry_step():
    samplesheet = {
        "sample_list": ["S1"],
        "sample_organization": "only cases",
        "variant_annotation": {
            "S1": {
                "case": {
                    "sample_name": "S1",
                    "vcf": "/data/S1.vcf",
                    "tsv": "/data/S1.tsv",
                }
            }
        },
    }
    pipeline = {
        "analysis": "Germline",
        "reference_version": "hg19",
        "workflow": ["variant_annotation"],
        "variant_annotation": {"tool": "VEP v.95", "threads": "2", "ram": "4g"},
    }
    tools = {
        "hg19": {"fasta": "/refs/hg19.fa"},
        "VEP v.95": {"path": "vep"},
    }

    assert validate_nextflow_inputs(samplesheet, pipeline, tools, entry_step="variant_annotation") is True
