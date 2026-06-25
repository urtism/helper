from helper_next.core.tool_resolver import resolve_pipeline_tools


def test_resolver_keeps_pipeline_intent_and_resolves_environment_paths():
    pipeline = {
        "workflow": ["alignment", "preprocessing", "variantcalling", "annotation"],
        "alignment": {
            "workflow": ["fastq_alignment"],
            "threads": "4",
            "ram": "8g",
            "fastq_alignment": {
                "tool": "BWA v.0.7.17",
                "BWA v.0.7.17": {"algorithm": "mem", "args": ["-M"]},
            },
        },
        "preprocessing": {
            "workflow": ["indel_realignment", "BQ_recalibration"],
            "threads": "2",
            "ram": "8g",
            "indel_realignment": {"tool": "GATK v.3.7", "GATK v.3.7": {"mills": "mills"}},
            "BQ_recalibration": {"tool": "GATK v.3.7", "GATK v.3.7": {"dbsnp": "dbsnp", "mills": "mills"}},
        },
        "variantcalling": {
            "tools": ["GATK v.4.1"],
            "threads": "2",
            "ram": "8g",
            "GATK v.4.1": {"args": ["--sample-ploidy", "2"]},
        },
        "annotation": {
            "workflow": ["vep_annotation"],
            "threads": "2",
            "ram": "4g",
            "vep_annotation": {
                "tool": "VEP v.95",
                "VEP v.95": {
                    "args": {
                        "args": ["--cache", "--offline"],
                        "features": ["--symbol"],
                        "af": ["--af"],
                        "assembly": "GRCh37",
                        "species": "homo_sapiens",
                        "plugins": {"list": ["GeneSplicer"], "GeneSplicer": {"files": "", "fields": "human"}},
                    }
                },
            },
        },
    }
    tools = {
        "BWA v.0.7.17": {"path": "/tools/bwa", "version": "0.7.17"},
        "SAMTOOLS": {"path": "/tools/samtools"},
        "GATK v.3.7": {"path": "/tools/GenomeAnalysisTK.jar"},
        "GATK v.4.1": {"path": "/tools/gatk"},
        "VEP v.95": {"path": "/tools/vep"},
        "GeneSplicer": {"path": "/plugins/genesplicer"},
        "dbsnp": {"path": "/refs/dbsnp.vcf"},
        "mills": {"path": "/refs/mills.vcf"},
    }
    panel = {"assets": {"target_bed": "/targets/panel.bed"}}

    resolved = resolve_pipeline_tools(pipeline, tools, panel)

    assert resolved["alignment"]["resolved"]["fastq_alignment"]["path"] == "/tools/bwa"
    assert resolved["alignment"]["resolved"]["fastq_alignment"]["resolved_args"] == "-M"
    assert resolved["preprocessing"]["resolved"]["databases"]["bqsr_dbsnp"]["path"] == "/refs/dbsnp.vcf"
    assert resolved["preprocessing"]["resolved"]["target_intervals"] == "/targets/panel.bed"
    assert resolved["variantcalling"]["resolved"]["caller"]["resolved_args"] == "--sample-ploidy 2"
    assert "--plugin GeneSplicer,/plugins/genesplicer,human" in resolved["annotation"]["resolved"]["vep_annotation"]["resolved_args"]
    assert resolved["resolved_tools"]["annotation"]["panel_assets"]["target_bed"] == "/targets/panel.bed"
