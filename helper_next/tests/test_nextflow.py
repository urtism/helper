import csv
from pathlib import Path

import pytest

from helper_next.core.nextflow import (
    ValidationError,
    build_nextflow_run_config,
    manifest_rows,
    validate_nextflow_inputs,
    write_manifest,
)


def test_variant_callers_receive_panel_target_intervals():
    module = (Path(__file__).resolve().parents[2] / "workflows/nextflow/modules/variantcalling.nf").read_text()
    haplotype = module.split("process GATK_HAPLOTYPECALLER", 1)[1].split("process GATK_JOINT_GENOTYPING", 1)[0]
    joint = module.split("process GATK_JOINT_GENOTYPING", 1)[1].split("process GATK_MUTECT2", 1)[0]
    mutect2 = module.split("process GATK_MUTECT2", 1)[1].split("process DEEPVARIANT_CALLER", 1)[0]
    deepvariant = module.split("process DEEPVARIANT_CALLER", 1)[1].split("process FREEBAYES_CALLER", 1)[0]
    freebayes = module.split("process FREEBAYES_CALLER", 1)[1].split("process VARIANTCALLING_STEP_LOG", 1)[0]

    assert "resolved_callers.values().find { caller -> caller?.target_intervals }?.target_intervals" in module
    assert 'def target_arg = target_intervals ? "-L \\"${target_intervals}\\"" : \'\'' in haplotype
    assert "${target_arg}" in haplotype
    assert 'def target_arg = target_intervals ? "-L \\"${target_intervals}\\"" : \'\'' in joint
    assert "${target_arg}" in joint
    assert 'def target_arg = target_intervals ? "-L \\"${target_intervals}\\"" : \'\'' in mutect2
    assert "${target_arg}" in mutect2
    assert 'def regions_arg = target_intervals ? "--regions \\"${target_intervals}\\"" : \'\'' in deepvariant
    assert "${regions_arg}" in deepvariant
    assert 'def target_arg = target_intervals ? "-t \\"${target_intervals}\\"" : \'\'' in freebayes
    assert "${target_arg}" in freebayes


def test_variant_callers_run_in_parallel_and_keep_gatk_as_primary_output():
    module = (Path(__file__).resolve().parents[2] / "workflows/nextflow/modules/variantcalling.nf").read_text()

    assert "def configuredContainer(config)" in module
    assert "configuredContainer(deepvariant_cfg) ?: configuredContainer(deepvariant_resolved)" in module
    assert "configuredContainer(freebayes_cfg) ?: configuredContainer(freebayes_resolved)" in module
    assert "freebayes_resolved.container?.image" not in module
    assert "deepvariant_min_ram = deepvariant_cfg.minimum_ram ?: '8 GB'" in module
    assert "MemoryUnit.of(deepvariant_min_ram)" in module
    assert "path(input_bam), path(input_bai)" in module
    assert "path(input_bams), path(input_bais), val(use_bam_list)" in module
    assert "tuple(sample_id, role, sample_name, bam, bai)" in module
    assert 'grep -q "Failed to load index"' in module
    assert "if (gatk_tool) {" in module
    assert "if (deepvariant_tool) {" in module
    assert "if (freebayes_tool) {" in module
    assert "} else if (tool_upper.startsWith('FREEBAYES')) {" not in module
    assert "germline_statuses = gatk_statuses.mix(deepvariant_statuses).mix(freebayes_statuses)" in module
    assert "germline_vcfs = gatk_tool ? gatk_vcfs" in module
    assert "${sample_name}.GATK.variantcalling.status.tsv" in module
    assert "${sample_name}.DeepVariant.variantcalling.status.tsv" in module
    assert "${sample_name}.Freebayes.variantcalling.status.tsv" in module


def test_multi_caller_vcfs_are_merged_after_per_caller_filtering():
    root = Path(__file__).resolve().parents[2]
    variantcalling = (root / "workflows/nextflow/modules/variantcalling.nf").read_text()
    postprocessing = (root / "workflows/nextflow/modules/postprocessing.nf").read_text()
    main = (root / "workflows/nextflow/main.nf").read_text()

    assert "caller_vcfs = output_caller_vcfs" in variantcalling
    assert "'GATK', vcf" in variantcalling
    assert "'DEEPVARIANT', vcf" in variantcalling
    assert "'FREEBAYES', vcf" in variantcalling
    assert "postprocessing_input_variants = VARIANTCALLING.out.caller_vcfs" in main
    assert "process POSTPROCESS_CALLER_VCF" in postprocessing
    assert "process FINALIZE_POSTPROCESSING" in postprocessing
    assert "bcftools_path} norm -m -any" in postprocessing
    assert "bcftools_path} norm -d exact" in postprocessing
    assert "do_gatk_filter = do_filter && caller.toString().toUpperCase() == 'GATK'" in postprocessing
    assert "operations.contains('multi_vcf_merge')" in postprocessing
    assert "merge_consensus_vcfs.py" in postprocessing
    assert "variants = FINALIZE_POSTPROCESSING.out.variants" in postprocessing


def mixed_variant_samplesheet():
    sample_names = ["CHILD", "FATHER", "MOTHER", "CASE", "CONTROL", "SINGLE", "TUMOR", "NORMAL"]
    return {
        "schema_version": 2,
        "sample_list": sample_names,
        "sample_organization": "mixed",
        "analysis_groups": [
            {
                "analysis_id": "FAM-01",
                "analysis_type": "family",
                "members": [
                    {
                        "sample_name": "CHILD",
                        "relationship": "proband",
                        "sex": "female",
                        "father": "FATHER",
                        "mother": "MOTHER",
                        "affected": "affected",
                        "twin_group": "",
                    },
                    {
                        "sample_name": "FATHER",
                        "relationship": "father",
                        "sex": "male",
                        "father": "",
                        "mother": "",
                        "affected": "unaffected",
                        "twin_group": "",
                    },
                    {
                        "sample_name": "MOTHER",
                        "relationship": "mother",
                        "sex": "female",
                        "father": "",
                        "mother": "",
                        "affected": "unaffected",
                        "twin_group": "",
                    },
                ],
            },
            {
                "analysis_id": "CASE-CONTROL-01",
                "analysis_type": "case-control",
                "members": [
                    {
                        "sample_name": "CASE",
                        "relationship": "case",
                        "sex": "female",
                        "affected": "affected",
                        "control_relationship": "",
                    },
                    {
                        "sample_name": "CONTROL",
                        "relationship": "control",
                        "sex": "female",
                        "affected": "unaffected",
                        "control_relationship": "unrelated",
                    },
                ],
            },
            {
                "analysis_id": "SINGLE",
                "analysis_type": "only cases",
                "members": [{"sample_name": "SINGLE", "relationship": "proband"}],
            },
            {
                "analysis_id": "PAIR-01",
                "analysis_type": "tumor-normal",
                "members": [
                    {
                        "sample_name": "TUMOR",
                        "relationship": "tumor",
                        "individual_id": "PATIENT-01",
                        "sex": "male",
                        "specimen_type": "tumor tissue",
                        "tumor_purity": "65",
                    },
                    {
                        "sample_name": "NORMAL",
                        "relationship": "normal",
                        "individual_id": "PATIENT-01",
                        "sex": "male",
                        "specimen_type": "blood",
                        "tumor_purity": "",
                    },
                ],
            },
        ],
        "variantcalling": {
            sample_name: {"sample_name": sample_name, "bam": "/data/{}.bam".format(sample_name.lower())}
            for sample_name in sample_names
        },
    }


def gatk_variant_pipeline():
    return {
        "analysis": "Mixed",
        "reference_version": "hg19",
        "workflow": ["variantcalling"],
        "variantcalling": {
            "tools": ["GATK v.4.1"],
            "threads": "4",
            "ram": "12g",
            "filters": {},
            "GATK v.4.1": {"args": []},
        },
    }


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
            "analysis_id": "",
            "analysis_type": "",
            "relationship": "",
            "individual_id": "",
            "sex": "",
            "father": "",
            "mother": "",
            "affected": "",
            "control_relationship": "",
            "specimen_type": "",
            "tumor_purity": "",
            "twin_group": "",
            "fastq_r1": "",
            "fastq_r2": "",
            "fastq_i2": "",
            "bam": "/data/S1.bam",
            "merged_vcf": "",
            "variants_tsv": "",
        }
    ]


def test_manifest_rows_export_analysis_metadata_and_legacy_aliases():
    rows = manifest_rows(mixed_variant_samplesheet(), "variantcalling")

    child = next(row for row in rows if row["sample_name"] == "CHILD")
    tumor = next(row for row in rows if row["sample_name"] == "TUMOR")
    assert (child["sample_id"], child["role"]) == ("FAM-01", "proband")
    assert (child["analysis_id"], child["analysis_type"]) == ("FAM-01", "family")
    assert (child["father"], child["mother"]) == ("FATHER", "MOTHER")
    assert tumor["individual_id"] == "PATIENT-01"
    assert tumor["tumor_purity"] == "65"


def test_validate_and_build_run_config_for_mixed_analysis():
    samplesheet = mixed_variant_samplesheet()
    pipeline = gatk_variant_pipeline()
    tools = {"hg19": {"fasta": "/refs/hg19.fa"}, "GATK v.4.1": {"path": "gatk"}}

    assert validate_nextflow_inputs(samplesheet, pipeline, tools, entry_step="variantcalling") is True

    config = build_nextflow_run_config(samplesheet, pipeline, tools, entry_step="variantcalling")
    assert config["schema_version"] == 2
    assert config["calling_scope"] == "single-sample"
    assert config["gvcf_storage"] is True
    assert config["comparative_analysis"] is True
    assert "calling_group" not in config
    assert config["analysis_groups"] == samplesheet["analysis_groups"]


def test_validate_mixed_analysis_rejects_loaded_parent_outside_family():
    samplesheet = mixed_variant_samplesheet()
    samplesheet["analysis_groups"][0]["members"][0]["father"] = "SINGLE"
    tools = {"hg19": {"fasta": "/refs/hg19.fa"}, "GATK v.4.1": {"path": "gatk"}}

    with pytest.raises(ValidationError) as exc:
        validate_nextflow_inputs(samplesheet, gatk_variant_pipeline(), tools, entry_step="variantcalling")

    assert "father 'SINGLE' is loaded but assigned outside this family" in "\n".join(exc.value.errors)


def test_validate_mixed_analysis_allows_unsequenced_parent_id():
    samplesheet = mixed_variant_samplesheet()
    samplesheet["analysis_groups"][0]["members"][1]["father"] = "GRANDFATHER-NOT-LOADED"
    tools = {"hg19": {"fasta": "/refs/hg19.fa"}, "GATK v.4.1": {"path": "gatk"}}

    assert validate_nextflow_inputs(
        samplesheet,
        gatk_variant_pipeline(),
        tools,
        entry_step="variantcalling",
    ) is True


def test_validate_mixed_analysis_accepts_deepvariant_with_gatk4_for_tumor_normal():
    samplesheet = mixed_variant_samplesheet()
    pipeline = gatk_variant_pipeline()
    pipeline["variantcalling"]["tools"] = ["DeepVariant v.1.10.0"]
    tools = {
        "hg19": {"fasta": "/refs/hg19.fa"},
        "DeepVariant v.1.10.0": {"path": "run_deepvariant"},
        "GATK v.4.1": {"path": "gatk"},
    }

    assert validate_nextflow_inputs(samplesheet, pipeline, tools, entry_step="variantcalling") is True


def test_validate_mixed_analysis_rejects_missing_gatk4_for_tumor_normal():
    samplesheet = mixed_variant_samplesheet()
    pipeline = gatk_variant_pipeline()
    pipeline["variantcalling"]["tools"] = ["FreeBayes"]
    tools = {"hg19": {"fasta": "/refs/hg19.fa"}, "FreeBayes": {"path": "freebayes"}}

    with pytest.raises(ValidationError) as exc:
        validate_nextflow_inputs(samplesheet, pipeline, tools, entry_step="variantcalling")

    assert "pipeline.variantcalling: tumor-normal analysis requires a configured GATK 4 caller for Mutect2" in exc.value.errors


def test_validate_mixed_analysis_rejects_unusable_gatk4_for_tumor_normal():
    samplesheet = mixed_variant_samplesheet()
    pipeline = gatk_variant_pipeline()
    pipeline["variantcalling"]["tools"] = ["DeepVariant v.1.10.0"]
    tools = {
        "hg19": {"fasta": "/refs/hg19.fa"},
        "DeepVariant v.1.10.0": {"path": "run_deepvariant"},
        "GATK v.4.1": {},
    }

    with pytest.raises(ValidationError) as exc:
        validate_nextflow_inputs(samplesheet, pipeline, tools, entry_step="variantcalling")

    assert "pipeline.variantcalling: tumor-normal analysis requires a configured GATK 4 caller for Mutect2" in exc.value.errors


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


def test_validate_nextflow_inputs_accepts_configured_prealignment():
    samplesheet = {
        "sample_list": ["S1"],
        "sample_organization": "only cases",
        "prealignment": {
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
        "workflow": ["prealignment", "alignment"],
        "prealignment": {
            "workflow": ["fastq_QC"],
            "threads": "1",
            "ram": "1g",
            "fastq_QC": {"tool": "FASTQC v.0.11.8", "FASTQC v.0.11.8": {"args": []}},
        },
        "alignment": {
            "workflow": ["fastq_alignment"],
            "threads": "6",
            "ram": "8g",
            "fastq_alignment": {"tool": "BWA v.0.7.17"},
        },
    }
    tools = {
        "hg19": {"fasta": "/refs/hg19.fa"},
        "FASTQC v.0.11.8": {"path": "fastqc"},
        "BWA v.0.7.17": {"path": "bwa"},
    }

    assert validate_nextflow_inputs(samplesheet, pipeline, tools, entry_step="prealignment") is True


@pytest.mark.parametrize(
    "tool_name,tool_path",
    [
        ("CUTADAPT", "cutadapt"),
        ("SURECALLTRIMMER v.3.5.1.46", "/tools/SurecallTrimmer.jar"),
    ],
)
def test_validate_nextflow_inputs_accepts_supported_adapter_trimmers(tool_name, tool_path):
    samplesheet = {
        "sample_list": ["S1"],
        "sample_organization": "only cases",
        "prealignment": {
            "S1": {
                "case": {
                    "sample_name": "S1",
                    "fastq_R1": "/data/S1_R1.fastq.gz",
                    "fastq_R2": "/data/S1_R2.fastq.gz",
                }
            }
        },
    }
    pipeline = {
        "workflow": ["prealignment"],
        "prealignment": {
            "workflow": ["trim_adapters"],
            "threads": "2",
            "ram": "2g",
            "trim_adapters": {
                "tool": tool_name,
                "adapter1": "ADAPTER_R1",
                "adapter2": "ADAPTER_R2",
                tool_name: {"args": ["-hs"] if tool_name.startswith("SURECALL") else []},
            },
        },
    }

    assert validate_nextflow_inputs(
        samplesheet,
        pipeline,
        {tool_name: {"path": tool_path}},
        entry_step="prealignment",
    ) is True


def test_validate_nextflow_inputs_rejects_unsupported_adapter_trimmer():
    samplesheet = {
        "sample_list": ["S1"],
        "sample_organization": "only cases",
        "prealignment": {
            "S1": {
                "case": {
                    "sample_name": "S1",
                    "fastq_R1": "/data/S1_R1.fastq.gz",
                    "fastq_R2": "/data/S1_R2.fastq.gz",
                }
            }
        },
    }
    pipeline = {
        "workflow": ["prealignment"],
        "prealignment": {
            "workflow": ["trim_adapters"],
            "threads": "1",
            "ram": "1g",
            "trim_adapters": {"tool": "TRIMMOMATIC"},
        },
    }

    with pytest.raises(ValidationError) as exc:
        validate_nextflow_inputs(
            samplesheet,
            pipeline,
            {"TRIMMOMATIC": {"path": "trimmomatic"}},
            entry_step="prealignment",
        )

    assert "pipeline.prealignment.trim_adapters: unsupported trimming tool 'TRIMMOMATIC'" in exc.value.errors


def test_prealignment_module_routes_trimmed_reads_to_qc_and_alignment():
    root = Path(__file__).resolve().parents[2]
    module = (root / "workflows/nextflow/modules/prealignment.nf").read_text()
    main = (root / "workflows/nextflow/main.nf").read_text()

    assert "process TRIM_CUTADAPT" in module
    assert "process TRIM_SURECALL" in module
    assert "container { cutadapt_container ?: null }" in module
    assert "trim_tool_cfg.container.image" in module
    assert "FASTQ_QC(reads_ch" in module
    assert "reads = reads_ch" in module
    assert "alignment_samples = PREALIGNMENT.out.reads" in main
    assert "ALIGNMENT(alignment_samples" in main


def test_alignment_module_runs_selected_bam_qc_on_sorted_bams():
    module = (Path(__file__).resolve().parents[2] / "workflows/nextflow/modules/alignment.nf").read_text()

    assert "process BAM_QC" in module
    assert "bam_qc_enabled = enabled_operations.contains('bam_QC')" in module
    assert "BAM_QC(aligned_bams" in module
    assert 'publishDir "${params.outdir}/ALIGNMENT/bam_qc"' in module
    assert "alignment_statuses.mix(BAM_QC.out.statuses)" in module
    assert "process QUALIMAP_BAM_QC" in module
    assert "container { qualimap_container ?: null }" in module
    assert "QUALIMAP_BAM_QC(aligned_bams" in module
    assert "qualimap_path} bamqc" in module
    assert "--java-mem-size=${javaMemMb}M" in module
    assert "bam_qc_resolved_container_cfg instanceof Map" in module
    assert "bam_qc_resolved_container_cfg['image']" in module


def test_alignment_module_uses_explicit_bowtie2_reference_index():
    module = (Path(__file__).resolve().parents[2] / "workflows/nextflow/modules/alignment.nf").read_text()

    assert "reference_cfg.bowtie2_index" in module
    assert "container { bowtie2_container ?: null }" in module
    assert "tool_cfg.container_path ?: 'bowtie2'" in module
    assert "bowtie2_min_ram = tool_cfg.minimum_ram ?: '6 GB'" in module
    assert "MemoryUnit.of(bowtie2_min_ram)" in module
    assert "tuple val(row), path(fastq_r1), path(fastq_r2)" in module
    assert "tuple(row, file(row.fastq_r1), file(row.fastq_r2))" in module
    assert "ALIGN_BOWTIE2(bowtie2_fastq_samples, align_threads, align_ram, bowtie2_min_ram, bowtie2_path, bowtie2_container, extra_args, bowtie2_index, restart_token)" in module
    assert "ALIGN_BOWTIE2_FINALIZE(ALIGN_BOWTIE2.out.sams, align_threads, align_ram, samtools_path)" in module
    assert "aligned_bams = ALIGN_BOWTIE2_FINALIZE.out.bams" in module


def test_restart_token_is_applied_only_to_forced_step_roots():
    root = Path(__file__).resolve().parents[2]
    main = (root / "workflows/nextflow/main.nf").read_text()
    modules = {
        name: (root / "workflows/nextflow/modules" / f"{name}.nf").read_text()
        for name in ("prealignment", "alignment", "preprocessing", "variantcalling", "postprocessing", "annotation")
    }

    assert "forced_restart_steps" in main
    assert "variantcalling_restart_token = forced_restart_steps.contains('variantcalling')" in main
    assert "val restart_token" in modules["prealignment"]
    assert "val restart_token" in modules["alignment"]
    assert "INIT_PREPROCESSING_SAMPLE(ready_bams, restart_token)" in modules["preprocessing"]
    assert "GATK_HAPLOTYPECALLER" in modules["variantcalling"] and "calling_mode, restart_token)" in modules["variantcalling"]
    assert "POSTPROCESS_CALLER_VCF" in modules["postprocessing"] and "reference_fasta, restart_token)" in modules["postprocessing"]
    assert "ANNOTATE_VARIANTS" in modules["annotation"] and "transcripts_list, restart_token)" in modules["annotation"]


def test_restart_from_step_uses_published_upstream_results_without_running_upstream_modules():
    main = (Path(__file__).resolve().parents[2] / "workflows/nextflow/main.nf").read_text()

    assert "restart_from_step == 'alignment'" in main
    assert 'def trimmed_dir = "${params.outdir}/PREALIGNMENT/trimmed"' in main
    assert '${trimmed_dir}/${row.sample_name}.R1.trim.fastq.gz' in main
    assert "restart_from_step == 'preprocessing'" in main
    assert 'ALIGNMENT/${row.sample_name}.sort.bam' in main
    assert "restart_from_step == 'variantcalling'" in main
    assert 'PREPROCESSING/${row.sample_name}.preprocessed.bam' in main
    assert "restart_from_step == 'postprocessing'" in main
    assert 'fromPath("${params.outdir}/VARIANTCALLING/*.vcf"' in main
    assert "restart_from_step == 'annotation'" in main
    assert 'POSTPROCESSING/${row.sample_name}.postprocessed.vcf' in main


def test_postprocessing_uses_gatk_java_and_safely_logs_filter_expressions():
    module = (Path(__file__).resolve().parents[2] / "workflows/nextflow/modules/postprocessing.nf").read_text()

    assert "System.getenv('GATK_JAVA_HOME')" in module
    assert "System.getenv('GATK_JAVA_CMD')" in module
    assert 'export JAVA_HOME="${gatk_java_home}"' in module
    assert "<<HELPER_FILTER_COMMAND" in module
    assert 'optional: true, emit: variants' in module


def test_preprocessing_module_runs_selected_bam_qc_on_final_bams():
    module = (Path(__file__).resolve().parents[2] / "workflows/nextflow/modules/preprocessing.nf").read_text()

    assert "process PREPROCESSING_FASTQC_BAM_QC" in module
    assert "process PREPROCESSING_QUALIMAP_BAM_QC" in module
    assert "FINALIZE_PREPROCESSING.out.bams" in module
    assert "operations.contains('bam_QC')" in module
    assert "PREPROCESSING_QUALIMAP_BAM_QC(FINALIZE_PREPROCESSING.out.bams" in module
    assert "PREPROCESSING_FASTQC_BAM_QC(FINALIZE_PREPROCESSING.out.bams" in module
    assert 'publishDir "${params.outdir}/PREPROCESSING/bam_qc"' in module
    assert "preprocessing_statuses.mix(PREPROCESSING_QUALIMAP_BAM_QC.out.statuses)" in module
    assert "bam_qc_resolved_container_cfg instanceof Map" in module


def test_validate_nextflow_inputs_accepts_gatk3_preprocessing_databases():
    samplesheet = {
        "sample_list": ["S1"],
        "sample_organization": "only cases",
        "preprocessing": {"S1": {"case": {"sample_name": "S1", "bam": "/data/S1.bam"}}},
    }
    pipeline = {
        "analysis": "Germline",
        "reference_version": "hg19",
        "workflow": ["preprocessing"],
        "preprocessing": {
            "workflow": ["add_readgroups", "mark_pcr_dup", "indel_realignment", "BQ_recalibration"],
            "threads": "2",
            "ram": "8g",
            "add_readgroups": {"tool": "PICARD v.2.7.1"},
            "mark_pcr_dup": {"tool": "PICARD v.2.7.1"},
            "indel_realignment": {"tool": "GATK v.3.7", "GATK v.3.7": {"args": [], "mills": "mills"}},
            "BQ_recalibration": {
                "tool": "GATK v.3.7",
                "GATK v.3.7": {"args": [], "dbsnp": "dbsnp", "mills": "mills"},
            },
        },
    }
    tools = {
        "hg19": {"fasta": "/refs/hg19.fa"},
        "PICARD v.2.7.1": {"path": "/tools/picard.jar"},
        "GATK v.3.7": {"path": "/tools/GenomeAnalysisTK.jar"},
        "dbsnp": {"path": "/refs/dbsnp.vcf"},
        "mills": {"path": "/refs/mills.vcf"},
    }

    assert validate_nextflow_inputs(samplesheet, pipeline, tools, entry_step="preprocessing") is True


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


def test_validate_nextflow_inputs_accepts_gatk_variantcalling_from_bam():
    samplesheet = {
        "sample_list": ["S1"],
        "sample_organization": "only cases",
        "variantcalling": {"S1": {"case": {"sample_name": "S1", "bam": "/data/S1.bam"}}},
    }
    pipeline = {
        "analysis": "Germline",
        "reference_version": "hg19",
        "workflow": ["variantcalling"],
        "variantcalling": {
            "tools": ["GATK v.4.1"],
            "threads": "2",
            "ram": "8g",
            "filters": {},
            "GATK v.4.1": {"args": []},
            "samples_org": "single-sample",
        },
    }
    tools = {
        "hg19": {"fasta": "/refs/hg19.fa"},
        "GATK v.4.1": {"path": "gatk"},
    }

    assert validate_nextflow_inputs(samplesheet, pipeline, tools, entry_step="variantcalling") is True


def test_validate_nextflow_inputs_accepts_case_control_variantcalling_from_bam():
    samplesheet = {
        "sample_list": ["PAIR1"],
        "sample_organization": "case-control",
        "variantcalling": {
            "PAIR1": {
                "case": {"sample_name": "TUMOR", "bam": "/data/tumor.bam"},
                "control": {"sample_name": "NORMAL", "bam": "/data/normal.bam"},
            }
        },
    }
    pipeline = {
        "analysis": "Germline",
        "reference_version": "hg19",
        "workflow": ["variantcalling"],
        "variantcalling": {
            "tools": ["GATK v.4.1"],
            "threads": "2",
            "ram": "8g",
            "filters": {},
            "GATK v.4.1": {"args": []},
            "samples_org": "single-sample",
        },
    }
    tools = {"hg19": {"fasta": "/refs/hg19.fa"}, "GATK v.4.1": {"path": "gatk"}}

    assert validate_nextflow_inputs(samplesheet, pipeline, tools, entry_step="variantcalling") is True
    rows = manifest_rows(samplesheet, "variantcalling")
    assert [(row["sample_id"], row["role"], row["sample_name"]) for row in rows] == [
        ("PAIR1", "case", "TUMOR"),
        ("PAIR1", "control", "NORMAL"),
    ]


def test_validate_nextflow_inputs_accepts_trio_variantcalling_from_bam():
    samplesheet = {
        "sample_list": ["FAM1"],
        "sample_organization": "trio",
        "variantcalling": {
            "FAM1": {
                "case": {"sample_name": "CHILD", "bam": "/data/child.bam"},
                "parent1": {"sample_name": "MOTHER", "bam": "/data/mother.bam"},
                "parent2": {"sample_name": "FATHER", "bam": "/data/father.bam"},
            }
        },
    }
    pipeline = {
        "analysis": "Germline",
        "reference_version": "hg19",
        "workflow": ["variantcalling"],
        "variantcalling": {
            "tools": ["GATK v.4.1"],
            "threads": "2",
            "ram": "8g",
            "filters": {},
            "GATK v.4.1": {"args": []},
            "samples_org": "cohort",
        },
    }
    tools = {"hg19": {"fasta": "/refs/hg19.fa"}, "GATK v.4.1": {"path": "gatk"}}

    assert validate_nextflow_inputs(samplesheet, pipeline, tools, entry_step="variantcalling") is True
    rows = manifest_rows(samplesheet, "variantcalling")
    assert [(row["sample_id"], row["role"], row["sample_name"]) for row in rows] == [
        ("FAM1", "case", "CHILD"),
        ("FAM1", "parent1", "MOTHER"),
        ("FAM1", "parent2", "FATHER"),
    ]


def test_validate_nextflow_inputs_accepts_postprocessing_from_vcf():
    samplesheet = {
        "sample_list": ["S1"],
        "sample_organization": "only cases",
        "postprocessing": {"S1": {"case": {"sample_name": "S1", "gatk_vcf": "/data/S1.g.vcf"}}},
    }
    pipeline = {
        "analysis": "Germline",
        "reference_version": "hg19",
        "workflow": ["postprocessing"],
        "postprocessing": {
            "workflow": ["vcf_to_tsv"],
            "threads": "2",
            "ram": "2g",
            "vcf_to_tsv": {"tool": "", "args": {}},
        },
    }
    tools = {"hg19": {"fasta": "/refs/hg19.fa"}}

    assert validate_nextflow_inputs(samplesheet, pipeline, tools, entry_step="postprocessing") is True
    rows = manifest_rows(samplesheet, "postprocessing")
    assert rows[0]["merged_vcf"] == "/data/S1.g.vcf"


def test_validate_nextflow_inputs_accepts_annotation_from_vcf():
    samplesheet = {
        "sample_list": ["S1"],
        "sample_organization": "only cases",
        "annotation": {"S1": {"case": {"sample_name": "S1", "merged_vcf": "/data/S1.vcf"}}},
    }
    pipeline = {
        "analysis": "Germline",
        "reference_version": "hg19",
        "workflow": ["annotation"],
        "annotation": {
            "workflow": ["vep_annotation", "ann_vcf_to_tsv"],
            "threads": "2",
            "ram": "4g",
            "vep_annotation": {"tool": "VEP v.95", "VEP v.95": {"args": []}},
            "ann_vcf_to_tsv": {"tool": "", "args": {}},
        },
    }
    tools = {"hg19": {"fasta": "/refs/hg19.fa"}, "VEP v.95": {"path": "vep"}}

    assert validate_nextflow_inputs(samplesheet, pipeline, tools, entry_step="annotation") is True
    rows = manifest_rows(samplesheet, "annotation")
    assert rows[0]["merged_vcf"] == "/data/S1.vcf"


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
