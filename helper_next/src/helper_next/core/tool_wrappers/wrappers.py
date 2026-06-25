from helper_next.core.annotation import build_vep_args
from helper_next.core.tool_wrappers.base import ToolInput, ToolOutput, ToolWrapper, config_args


class BwaAlignmentWrapper(ToolWrapper):
    default_operation = "fastq_alignment"

    def command_args(self, operation):
        algorithm = self.operation_config.get("algorithm", "mem")
        args = [algorithm, self.reference_fasta(), "{fastq_r1}", "{fastq_r2}"]
        threads = self.operation_config.get("threads", self.tool_config.get("threads"))
        if threads:
            args.extend(["-t", str(threads)])
        args.extend(config_args(self.operation_config))
        return args

    def inputs(self, operation):
        return [
            ToolInput("reference_fasta", self.reference_fasta()),
            ToolInput("fastq_r1", "{fastq_r1}"),
            ToolInput("fastq_r2", "{fastq_r2}", optional=True),
        ]

    def outputs(self, operation):
        return [ToolOutput("sam", "{sample_name}.sam")]


class Bowtie2AlignmentWrapper(ToolWrapper):
    default_operation = "fastq_alignment"

    def command_args(self, operation):
        args = ["-x", self.reference_info.get("bowtie2_index", self.reference_fasta()), "-1", "{fastq_r1}", "-2", "{fastq_r2}"]
        threads = self.operation_config.get("threads", self.tool_config.get("threads"))
        if threads:
            args.extend(["-p", str(threads)])
        args.extend(config_args(self.operation_config))
        return args

    def inputs(self, operation):
        return [
            ToolInput("reference_index", str(self.reference_info.get("bowtie2_index", self.reference_fasta()))),
            ToolInput("fastq_r1", "{fastq_r1}"),
            ToolInput("fastq_r2", "{fastq_r2}"),
        ]

    def outputs(self, operation):
        return [ToolOutput("sam", "{sample_name}.sam")]


class SamtoolsWrapper(ToolWrapper):
    def command_args(self, operation):
        subcommand = self.operation_config.get("subcommand") or self.operation_config.get("command") or "view"
        defaults = {
            "view": ["-bS", "{sam}"],
            "sort": ["-o", "{sample_name}.sort.bam", "{bam}"],
            "index": ["{bam}"],
        }
        return [subcommand] + defaults.get(subcommand, []) + config_args(self.operation_config)

    def inputs(self, operation):
        return [ToolInput("alignment", "{sam_or_bam}")]

    def outputs(self, operation):
        return [
            ToolOutput("bam", "{sample_name}.bam", optional=True),
            ToolOutput("bai", "{sample_name}.bam.bai", optional=True),
        ]


class PicardAddOrReplaceReadGroupsWrapper(ToolWrapper):
    default_operation = "add_readgroups"

    def command_args(self, operation):
        ram = self.operation_config.get("ram", self.tool_config.get("ram", "{ram}"))
        return [
            "java",
            "-Xmx{}".format(ram),
            "-jar",
            self.executable("PICARD"),
            "AddOrReplaceReadGroups",
            "I={bam}",
            "O={sample_name}.RG.bam",
            "RGID={sample_name}",
            "RGPL=ILLUMINA",
            "RGSM={sample_name}",
            "RGLB={panel_name}",
            "RGPU={run_id}",
            "VALIDATION_STRINGENCY=LENIENT",
        ] + config_args(self.operation_config)

    def inputs(self, operation):
        return [ToolInput("bam", "{bam}")]

    def outputs(self, operation):
        return [ToolOutput("bam", "{sample_name}.RG.bam")]


class PicardMarkDuplicatesWrapper(ToolWrapper):
    default_operation = "mark_pcr_dup"

    def command_args(self, operation):
        ram = self.operation_config.get("ram", self.tool_config.get("ram", "{ram}"))
        return [
            "java",
            "-Xmx{}".format(ram),
            "-jar",
            self.executable("PICARD"),
            "MarkDuplicates",
            "I={bam}",
            "O={sample_name}.Mark.bam",
            "METRICS_FILE={sample_name}.MarkMetrics.txt",
            "READ_NAME_REGEX=null",
            "ASSUME_SORTED=true",
            "VALIDATION_STRINGENCY=LENIENT",
        ] + config_args(self.operation_config)

    def inputs(self, operation):
        return [ToolInput("bam", "{bam}")]

    def outputs(self, operation):
        return [ToolOutput("bam", "{sample_name}.Mark.bam"), ToolOutput("metrics", "{sample_name}.MarkMetrics.txt")]


class Gatk3IndelRealignmentWrapper(ToolWrapper):
    default_operation = "indel_realignment"

    def command_args(self, operation):
        mills = self.operation_config.get("mills_path", self.operation_config.get("mills", "{mills}"))
        target = self.operation_config.get("target_intervals") or self.panel_assets().get("target_bed", "{target_bed}")
        ram = self.operation_config.get("ram", self.tool_config.get("ram", "{ram}"))
        return [
            "java",
            "-Xmx{}".format(ram),
            "-jar",
            self.executable("GATK"),
            "-T",
            "RealignerTargetCreator",
            "-R",
            self.reference_fasta(),
            "-I",
            "{bam}",
            "-o",
            "{sample_name}.IndelRealigner.intervals",
            "-known",
            str(mills),
            "-L",
            str(target),
            "&&",
            "java",
            "-Xmx{}".format(ram),
            "-jar",
            self.executable("GATK"),
            "-T",
            "IndelRealigner",
            "-R",
            self.reference_fasta(),
            "-I",
            "{bam}",
            "-targetIntervals",
            "{sample_name}.IndelRealigner.intervals",
            "-known",
            str(mills),
            "-o",
            "{sample_name}.IR.bam",
        ] + config_args(self.operation_config)

    def inputs(self, operation):
        return [
            ToolInput("bam", "{bam}"),
            ToolInput("reference_fasta", self.reference_fasta()),
            ToolInput("known_indels", str(self.operation_config.get("mills_path", self.operation_config.get("mills", "")))),
            ToolInput("target_intervals", str(self.operation_config.get("target_intervals") or self.panel_assets().get("target_bed", "")), optional=True),
        ]

    def outputs(self, operation):
        return [ToolOutput("bam", "{sample_name}.IR.bam"), ToolOutput("intervals", "{sample_name}.IndelRealigner.intervals")]


class Gatk3BqsrWrapper(ToolWrapper):
    default_operation = "BQ_recalibration"

    def command_args(self, operation):
        dbsnp = self.operation_config.get("dbsnp_path", self.operation_config.get("dbsnp", "{dbsnp}"))
        mills = self.operation_config.get("mills_path", self.operation_config.get("mills", "{mills}"))
        target = self.operation_config.get("target_intervals") or self.panel_assets().get("target_bed", "{target_bed}")
        ram = self.operation_config.get("ram", self.tool_config.get("ram", "{ram}"))
        return [
            "java",
            "-Xmx{}".format(ram),
            "-jar",
            self.executable("GATK"),
            "-T",
            "BaseRecalibrator",
            "-R",
            self.reference_fasta(),
            "-I",
            "{bam}",
            "-o",
            "{sample_name}.BQSR.table",
            "-knownSites",
            str(dbsnp),
            "-knownSites",
            str(mills),
            "-L",
            str(target),
            "&&",
            "java",
            "-Xmx{}".format(ram),
            "-jar",
            self.executable("GATK"),
            "-T",
            "PrintReads",
            "-R",
            self.reference_fasta(),
            "-I",
            "{bam}",
            "-BQSR",
            "{sample_name}.BQSR.table",
            "-L",
            str(target),
            "-o",
            "{sample_name}.BQSR.bam",
        ] + config_args(self.operation_config)

    def inputs(self, operation):
        return [
            ToolInput("bam", "{bam}"),
            ToolInput("reference_fasta", self.reference_fasta()),
            ToolInput("dbsnp", str(self.operation_config.get("dbsnp_path", self.operation_config.get("dbsnp", "")))),
            ToolInput("mills", str(self.operation_config.get("mills_path", self.operation_config.get("mills", "")))),
            ToolInput("target_intervals", str(self.operation_config.get("target_intervals") or self.panel_assets().get("target_bed", "")), optional=True),
        ]

    def outputs(self, operation):
        return [ToolOutput("bam", "{sample_name}.BQSR.bam"), ToolOutput("recal_table", "{sample_name}.BQSR.table")]


class Gatk4HaplotypeCallerWrapper(ToolWrapper):
    default_operation = "caller"

    def command_args(self, operation):
        target = self.operation_config.get("target_intervals") or self.panel_assets().get("target_bed")
        args = [
            "HaplotypeCaller",
            "-R",
            self.reference_fasta(),
            "-I",
            "{bam}",
            "-O",
            "{sample_name}.g.vcf",
            "-ERC",
            "GVCF",
            "--max-reads-per-alignment-start",
            "0",
            "--enable-all-annotations",
        ]
        if target:
            args.extend(["-L", str(target)])
        args.extend(config_args(self.operation_config))
        return args

    def inputs(self, operation):
        return [
            ToolInput("bam", "{bam}"),
            ToolInput("reference_fasta", self.reference_fasta()),
            ToolInput("target_intervals", str(self.operation_config.get("target_intervals") or self.panel_assets().get("target_bed", "")), optional=True),
        ]

    def outputs(self, operation):
        return [ToolOutput("gvcf", "{sample_name}.g.vcf")]


class BcftoolsNormWrapper(ToolWrapper):
    default_operation = "vcf_norm"

    def command_args(self, operation):
        args = ["norm", "-f", self.reference_fasta(), "-o", "{sample_name}.norm.vcf", "{vcf}"]
        args.extend(config_args(self.operation_config))
        return args

    def inputs(self, operation):
        return [ToolInput("vcf", "{vcf}"), ToolInput("reference_fasta", self.reference_fasta())]

    def outputs(self, operation):
        return [ToolOutput("vcf", "{sample_name}.norm.vcf")]


class GatkVariantFiltrationWrapper(ToolWrapper):
    default_operation = "vcf_filter"

    def command_args(self, operation):
        args = ["VariantFiltration", "-R", self.reference_fasta(), "-V", "{vcf}", "-O", "{sample_name}.filter.vcf"]
        args.extend(config_args(self.operation_config))
        return args

    def inputs(self, operation):
        return [ToolInput("vcf", "{vcf}"), ToolInput("reference_fasta", self.reference_fasta())]

    def outputs(self, operation):
        return [ToolOutput("vcf", "{sample_name}.filter.vcf")]


class VepAnnotationWrapper(ToolWrapper):
    default_operation = "vep_annotation"

    def command_args(self, operation):
        raw_args = self.operation_config.get("args", [])
        if isinstance(raw_args, dict):
            args = build_vep_args(raw_args, self.tools_config)
        else:
            args = config_args(self.operation_config)
        if self.reference_fasta() and "--fasta" not in args:
            args.extend(["--fasta", self.reference_fasta()])
        transcripts = self.panel_assets().get("transcripts_list")
        if transcripts and "--transcript_filter" not in args:
            args.extend(["--transcript_filter", str(transcripts)])
        return ["-i", "{vcf}", "-o", "{sample_name}.VEP.vcf"] + args

    def inputs(self, operation):
        return [
            ToolInput("vcf", "{vcf}"),
            ToolInput("reference_fasta", self.reference_fasta(), optional=True),
            ToolInput("transcripts_list", str(self.panel_assets().get("transcripts_list", "")), optional=True),
        ]

    def outputs(self, operation):
        return [ToolOutput("annotated_vcf", "{sample_name}.VEP.vcf")]

    def metadata(self, operation):
        metadata = super().metadata(operation)
        metadata["legacy_vep_args"] = True
        metadata["plugins_from_tools_cfg"] = True
        return metadata
