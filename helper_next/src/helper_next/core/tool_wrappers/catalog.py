from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class OperationSpec:
    operation: str
    tool_family: str = ""
    command_args: List[str] = field(default_factory=list)
    inputs: Dict[str, str] = field(default_factory=dict)
    outputs: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, str] = field(default_factory=dict)


SCRIPT_NAMES = [
    "QCtool.py",
    "Transcript_selector.py",
    "VCF_filter.py",
    "add_AC.py",
    "add_AC_AN_from_VCF_to_TSV.py",
    "addtoTarget.py",
    "annotation_extractor.py",
    "annotation_extractor_Somatic.py",
    "check_vcf_uppercase.py",
    "eVAI_adapter.py",
    "features_extraction_germline_iEVA.py",
    "features_extractor.py",
    "features_extractor_GATK.py",
    "features_extractor_ieva.py",
    "features_extractor_somatic.py",
    "features_extractor_somatic_MUTECT2.py",
    "header_fix.py",
    "make_gatk_CNV_calls_model.py",
    "merge_vcf.py",
    "merge_vcfs.py",
    "samplesheet_writer.py",
    "statsvcf_vs_test.py",
    "vcf_filter_by_sample.py",
    "vcf_to_tsv.py",
]


SCRIPT_OPERATIONS = {Path(name).stem: name for name in SCRIPT_NAMES}


LEGACY_OPERATION_SPECS: Dict[str, OperationSpec] = {
    "fastq_diagnosis": OperationSpec("fastq_diagnosis", "FASTQC", ["{fastq}", "-o", "{outdir}"], {"fastq": "{fastq}"}, {"report_dir": "{sample_name}_fastqc"}),
    "bam_diagnosis": OperationSpec("bam_diagnosis", "FASTQC", ["{bam}", "-o", "{outdir}"], {"bam": "{bam}"}, {"report_dir": "{sample_name}_fastqc"}),
    "sam_diagnosis": OperationSpec("sam_diagnosis", "FASTQC", ["{sam}", "-o", "{outdir}"], {"sam": "{sam}"}, {"report_dir": "{sample_name}_fastqc"}),
    "align_fastq": OperationSpec("align_fastq", "BWA", ["mem", "{reference_fasta}", "{fastq_r1}", "{fastq_r2}", "-t", "{threads}"], {"reference_fasta": "{reference_fasta}", "fastq_r1": "{fastq_r1}", "fastq_r2": "{fastq_r2}"}, {"sam": "{sample_name}.sam"}),
    "parallel_align_fastq": OperationSpec("parallel_align_fastq", "BWA", ["mem", "{reference_fasta}", "{fastq_r1}", "{fastq_r2}", "-t", "{threads}"], {"fastq_list": "{fastq_list}", "reference_fasta": "{reference_fasta}"}, {"sam_list": "{sample_name}.sam"}),
    "bowtie2_align_fastq": OperationSpec("bowtie2_align_fastq", "BOWTIE2", ["-x", "{reference_index}", "-1", "{fastq_r1}", "-2", "{fastq_r2}", "-p", "{threads}"], {"reference_index": "{reference_index}", "fastq_r1": "{fastq_r1}", "fastq_r2": "{fastq_r2}"}, {"sam": "{sample_name}.sam"}),
    "trim_adapters": OperationSpec("trim_adapters", "CUTADAPT", ["-a", "{adapter1}", "-A", "{adapter2}", "-o", "{r1_trimmed}", "-p", "{r2_trimmed}", "{fastq_r1}", "{fastq_r2}"], {"fastq_r1": "{fastq_r1}", "fastq_r2": "{fastq_r2}"}, {"fastq_r1": "{sample_name}.R1.trim.fastq.gz", "fastq_r2": "{sample_name}.R2.trim.fastq.gz"}),
    "fastq_fiter_qual": OperationSpec("fastq_fiter_qual", "CUTADAPT", ["-q", "{quality}", "-o", "{r1_filtered}", "-p", "{r2_filtered}", "{fastq_r1}", "{fastq_r2}"], {"fastq_r1": "{fastq_r1}", "fastq_r2": "{fastq_r2}"}, {"fastq_r1": "{sample_name}.R1.qual.fastq.gz", "fastq_r2": "{sample_name}.R2.qual.fastq.gz"}),
    "fastq_fiter_len": OperationSpec("fastq_fiter_len", "CUTADAPT", ["-m", "{minlen}", "-M", "{maxlen}", "-o", "{r1_filtered}", "-p", "{r2_filtered}", "{fastq_r1}", "{fastq_r2}"], {"fastq_r1": "{fastq_r1}", "fastq_r2": "{fastq_r2}"}, {"fastq_r1": "{sample_name}.R1.len.fastq.gz", "fastq_r2": "{sample_name}.R2.len.fastq.gz"}),
    "locatit": OperationSpec("locatit", "AGENT", ["LocatIt", "-i", "{bam}", "-o", "{sample_name}.MCBmerged.bam", "{fastq_i2}"], {"bam": "{bam}", "fastq_i2": "{fastq_i2}", "target_bed": "{target_bed}"}, {"bam": "{sample_name}.MCBmerged.bam"}),
    "trimmer": OperationSpec("trimmer", "AGENT", ["Trimmer", "-fq1", "{fastq_r1}", "-fq2", "{fastq_r2}", "-out_loc", "{outdir}"], {"fastq_r1": "{fastq_r1}", "fastq_r2": "{fastq_r2}"}, {"fastq_r1": "{sample_name}.R1.trim.fastq.gz", "fastq_r2": "{sample_name}.R2.trim.fastq.gz"}),
    "samformatconverter": OperationSpec("samformatconverter", "PICARD", ["SamFormatConverter", "I={sam}", "O={sample_name}.bam"], {"sam": "{sam}"}, {"bam": "{sample_name}.bam"}),
    "sortsam": OperationSpec("sortsam", "PICARD", ["SortSam", "I={bam}", "O={sample_name}.sort.bam", "SORT_ORDER=coordinate"], {"bam": "{bam}"}, {"bam": "{sample_name}.sort.bam"}),
    "buildbamindex": OperationSpec("buildbamindex", "PICARD", ["BuildBamIndex", "I={bam}", "O={bam}.bai", "VALIDATION_STRINGENCY=LENIENT"], {"bam": "{bam}"}, {"bai": "{bam}.bai"}),
    "markduplicates": OperationSpec("markduplicates", "PICARD", ["MarkDuplicates", "I={bam}", "O={sample_name}.Mark.bam", "METRICS_FILE={sample_name}.MarkMetrics.txt", "READ_NAME_REGEX=null", "ASSUME_SORTED=true", "VALIDATION_STRINGENCY=LENIENT"], {"bam": "{bam}"}, {"bam": "{sample_name}.Mark.bam", "metrics": "{sample_name}.MarkMetrics.txt"}),
    "addorreplacereadgroups": OperationSpec("addorreplacereadgroups", "PICARD", ["AddOrReplaceReadGroups", "I={bam}", "O={sample_name}.RG.bam", "RGID={sample_name}", "RGPL=ILLUMINA", "RGSM={sample_name}", "RGLB={panel_name}", "RGPU={run_id}", "VALIDATION_STRINGENCY=LENIENT"], {"bam": "{bam}"}, {"bam": "{sample_name}.RG.bam"}),
    "indexfeaturefile": OperationSpec("indexfeaturefile", "GATK", ["IndexFeatureFile", "-F", "{file}"], {"file": "{file}"}, {"index": "{file}.idx"}),
    "indelrealigner": OperationSpec("indelrealigner", "GATK", ["-T", "RealignerTargetCreator", "-R", "{reference_fasta}", "-I", "{bam}", "-o", "{sample_name}.intervals", "-known", "{mills}", "-L", "{target_bed}", "&&", "-T", "IndelRealigner", "-R", "{reference_fasta}", "-I", "{bam}", "-targetIntervals", "{sample_name}.intervals", "-known", "{mills}", "-o", "{sample_name}.IR.bam"], {"bam": "{bam}", "reference_fasta": "{reference_fasta}", "mills": "{mills}", "target_bed": "{target_bed}"}, {"bam": "{sample_name}.IR.bam", "intervals": "{sample_name}.intervals"}),
    "baserecalibrator": OperationSpec("baserecalibrator", "GATK", ["BaseRecalibrator", "-R", "{reference_fasta}", "-I", "{bam}", "-O", "{sample_name}.BQSR.table", "--known-sites", "{dbsnp}", "--known-sites", "{mills}", "-L", "{target_bed}", "&&", "ApplyBQSR", "-R", "{reference_fasta}", "-I", "{bam}", "--bqsr-recal-file", "{sample_name}.BQSR.table", "-O", "{sample_name}.BQSR.bam"], {"bam": "{bam}", "reference_fasta": "{reference_fasta}", "dbsnp": "{dbsnp}", "mills": "{mills}", "target_bed": "{target_bed}"}, {"bam": "{sample_name}.BQSR.bam", "recal_table": "{sample_name}.BQSR.table"}),
    "haplotypecaller": OperationSpec("haplotypecaller", "GATK", ["HaplotypeCaller", "-R", "{reference_fasta}", "-I", "{bam}", "-O", "{sample_name}.g.vcf", "-ERC", "GVCF", "-L", "{target_bed}"], {"bam": "{bam}", "reference_fasta": "{reference_fasta}", "target_bed": "{target_bed}"}, {"gvcf": "{sample_name}.g.vcf"}),
    "genotypegvcfs": OperationSpec("genotypegvcfs", "GATK", ["GenotypeGVCFs", "-R", "{reference_fasta}", "-V", "{gvcf}", "-O", "{sample_name}.GATK.vcf", "-L", "{target_bed}"], {"gvcf": "{gvcf}", "reference_fasta": "{reference_fasta}"}, {"vcf": "{sample_name}.GATK.vcf"}),
    "mutect2": OperationSpec("mutect2", "GATK", ["Mutect2", "-R", "{reference_fasta}", "-I", "{case_bam}", "-tumor", "{case_name}", "-I", "{control_bam}", "-normal", "{control_name}", "-O", "{sample_name}.Mutect.vcf", "&&", "FilterMutectCalls", "-R", "{reference_fasta}", "-V", "{sample_name}.Mutect.vcf", "-O", "{sample_name}.Mutect.filter.vcf"], {"case_bam": "{case_bam}", "control_bam": "{control_bam}", "reference_fasta": "{reference_fasta}"}, {"vcf": "{sample_name}.Mutect.filter.vcf"}),
    "combinegvcfs": OperationSpec("combinegvcfs", "GATK", ["CombineGVCFs", "-R", "{reference_fasta}", "-O", "{sample_name}.g.vcf", "-V", "{gvcf_array}", "-L", "{target_bed}"], {"gvcf_array": "{gvcf_array}", "reference_fasta": "{reference_fasta}"}, {"gvcf": "{sample_name}.g.vcf"}),
    "leftalignandtrimvariants": OperationSpec("leftalignandtrimvariants", "GATK", ["LeftAlignAndTrimVariants", "-R", "{reference_fasta}", "-V", "{vcf}", "-O", "{sample_name}.norm.vcf", "--split-multi-allelics"], {"vcf": "{vcf}", "reference_fasta": "{reference_fasta}"}, {"vcf": "{sample_name}.norm.vcf"}),
    "variantfiltration": OperationSpec("variantfiltration", "GATK", ["VariantFiltration", "-R", "{reference_fasta}", "-V", "{vcf}", "-O", "{sample_name}.filter.vcf"], {"vcf": "{vcf}", "reference_fasta": "{reference_fasta}"}, {"vcf": "{sample_name}.filter.vcf"}),
    "hardfilter": OperationSpec("hardfilter", "GATK", ["VariantFiltration", "-R", "{reference_fasta}", "-V", "{vcf}", "-O", "{sample_name}.filter.vcf"], {"vcf": "{vcf}", "reference_fasta": "{reference_fasta}"}, {"vcf": "{sample_name}.filter.vcf"}),
    "selectvariants": OperationSpec("selectvariants", "GATK", ["SelectVariants", "-R", "{reference_fasta}", "-V", "{vcf}", "-O", "{sample_name}.GATK.vcf", "--sample-name", "{sample_name}"], {"vcf": "{vcf}", "reference_fasta": "{reference_fasta}"}, {"vcf": "{sample_name}.GATK.vcf"}),
    "variantannotator": OperationSpec("variantannotator", "GATK", ["VariantAnnotator", "-R", "{reference_fasta}", "-V", "{vcf}", "-I", "{bam}", "-O", "{sample_name}.annotated.vcf", "-L", "{target_bed}"], {"vcf": "{vcf}", "bam": "{bam}", "reference_fasta": "{reference_fasta}"}, {"vcf": "{sample_name}.annotated.vcf"}),
    "collectreadcounts": OperationSpec("collectreadcounts", "GATK", ["CollectReadCounts", "-I", "{bam}", "-L", "{target_bed}", "--interval-merging-rule", "OVERLAPPING_ONLY", "-O", "{sample_name}.hdf5"], {"bam": "{bam}", "target_bed": "{target_bed}"}, {"hdf5": "{sample_name}.hdf5"}),
    "determinegermlinecontigploidy": OperationSpec("determinegermlinecontigploidy", "GATK", ["DetermineGermlineContigPloidy", "--input", "{hdf5_list}", "--contig-ploidy-priors", "{ploidy_model}", "--output-prefix", "{sample_name}", "--output", "{outdir}"], {"hdf5_list": "{hdf5_list}", "ploidy_model": "{ploidy_model}"}, {"ploidy_calls": "{sample_name}-calls"}),
    "germlinecnvcaller": OperationSpec("germlinecnvcaller", "GATK", ["GermlineCNVCaller", "--input", "{hdf5_list}", "--contig-ploidy-calls", "{sample_ploidy}", "--model", "{calls_model}", "--output", "{outdir}", "--output-prefix", "{sample_name}"], {"hdf5_list": "{hdf5_list}", "sample_ploidy": "{sample_ploidy}"}, {"calls": "{sample_name}-calls"}),
    "postprocessgermlinecnvcalls": OperationSpec("postprocessgermlinecnvcalls", "GATK", ["PostprocessGermlineCNVCalls", "--calls-shard-path", "{sample_calls}", "--contig-ploidy-calls", "{sample_ploidy}", "--model-shard-path", "{calls_model}", "--sample-index", "{index}", "--output-genotyped-intervals", "{sample_name}.intervals.vcf", "--output-genotyped-segments", "{sample_name}.segments.vcf"], {"sample_calls": "{sample_calls}", "sample_ploidy": "{sample_ploidy}"}, {"intervals_vcf": "{sample_name}.intervals.vcf", "segments_vcf": "{sample_name}.segments.vcf"}),
    "freebayes": OperationSpec("freebayes", "FREEBAYES", ["-f", "{reference_fasta}", "-t", "{target_bed}", "-v", "{sample_name}.freebayes.vcf", "{bam}"], {"bam": "{bam}", "reference_fasta": "{reference_fasta}", "target_bed": "{target_bed}"}, {"vcf": "{sample_name}.freebayes.vcf"}),
    "variant_calling": OperationSpec("variant_calling", "FREEBAYES", ["-f", "{reference_fasta}", "-t", "{target_bed}", "-v", "{sample_name}.freebayes.vcf", "{bam}"], {"bam": "{bam}", "reference_fasta": "{reference_fasta}", "target_bed": "{target_bed}"}, {"vcf": "{sample_name}.freebayes.vcf"}),
    "mpileup": OperationSpec("mpileup", "SAMTOOLS", ["mpileup", "-B", "-q", "1", "-d", "50000", "-L", "50000", "-f", "{reference_fasta}", "-l", "{target_bed}", "-b", "{bam_list}"], {"bam_list": "{bam_list}", "reference_fasta": "{reference_fasta}"}, {"mpileup": "{sample_name}.mpileup"}),
    "varscan_mpileup2snp": OperationSpec("varscan_mpileup2snp", "VARSCAN", ["mpileup2snp", "{mpileup}", "--output-vcf", "1"], {"mpileup": "{mpileup}"}, {"vcf": "{sample_name}.snp.vcf"}),
    "varscan_mpileup2indel": OperationSpec("varscan_mpileup2indel", "VARSCAN", ["mpileup2indel", "{mpileup}", "--output-vcf", "1"], {"mpileup": "{mpileup}"}, {"vcf": "{sample_name}.indel.vcf"}),
    "varscan_somatic": OperationSpec("varscan_somatic", "VARSCAN", ["somatic", "{normal_mpileup}", "{tumor_mpileup}", "{sample_name}", "--output-vcf", "1"], {"normal_mpileup": "{normal_mpileup}", "tumor_mpileup": "{tumor_mpileup}"}, {"snp_vcf": "{sample_name}.snp.vcf", "indel_vcf": "{sample_name}.indel.vcf"}),
    "vardict": OperationSpec("vardict", "VARDICT", ["-G", "{reference_fasta}", "-f", "{allele_frequency}", "-N", "{sample_name}", "-b", "{bam}", "{target_bed}"], {"bam": "{bam}", "reference_fasta": "{reference_fasta}", "target_bed": "{target_bed}"}, {"vcf": "{sample_name}.vardict.vcf"}),
    "vc_germline": OperationSpec("vc_germline", "VARDICT", ["-G", "{reference_fasta}", "-f", "0.05", "-N", "{sample_name}", "-b", "{bam}", "{target_bed}"], {"bam": "{bam}", "reference_fasta": "{reference_fasta}", "target_bed": "{target_bed}"}, {"vcf": "{sample_name}.vardict.vcf"}),
    "bcftools_norm": OperationSpec("bcftools_norm", "BCFTOOLS", ["norm", "-D", "-m", "-both", "-f", "{reference_fasta}", "{vcf}", "-o", "{sample_name}.norm.vcf"], {"vcf": "{vcf}", "reference_fasta": "{reference_fasta}"}, {"vcf": "{sample_name}.norm.vcf"}),
    "norm": OperationSpec("norm", "BCFTOOLS", ["norm", "-D", "-m", "-both", "-f", "{reference_fasta}", "{vcf}", "-o", "{sample_name}.norm.vcf"], {"vcf": "{vcf}", "reference_fasta": "{reference_fasta}"}, {"vcf": "{sample_name}.norm.vcf"}),
    "readinbams": OperationSpec("readinbams", "DECON", ["ReadInBams.R", "--bams", "{bam_list}", "--bed", "{target_bed}", "--fasta", "{reference_fasta}", "--out", "{sample_name}.RData"], {"bam_list": "{bam_list}", "target_bed": "{target_bed}", "reference_fasta": "{reference_fasta}"}, {"rdata": "{sample_name}.RData"}),
    "identifyfailures": OperationSpec("identifyfailures", "DECON", ["IdentifyFailures.R", "--Rdata", "{rdata}", "--mincorr", "0.97", "--mincov", "50", "--custom", "fALSE", "--out", "{sample_name}.failures.txt"], {"rdata": "{rdata}"}, {"failures": "{sample_name}.failures.txt"}),
    "makecnvcalls": OperationSpec("makecnvcalls", "DECON", ["makeCNVcalls.R", "--Rdata", "{rdata}", "--transProb", "0.01", "--out", "{sample_name}.cnv.txt"], {"rdata": "{rdata}"}, {"cnv": "{sample_name}.cnv.txt"}),
    "startwithbam": OperationSpec("startwithbam", "CONVADING", ["-mode", "StartWithBam", "-inputDir", "{inputdir}", "-outputDir", "{outdir}", "-controlsDir", "{controls_dir}", "-bed", "{target_bed}"], {"inputdir": "{inputdir}", "target_bed": "{target_bed}", "controls_dir": "{controls_dir}"}, {"coverage_dir": "{outdir}"}),
    "startwithmatchscore": OperationSpec("startwithmatchscore", "CONVADING", ["-mode", "StartWithMatchScore", "-inputDir", "{inputdir}", "-outputDir", "{outdir}", "-controlsDir", "{controls_dir}", "-bed", "{target_bed}"], {"inputdir": "{inputdir}", "target_bed": "{target_bed}", "controls_dir": "{controls_dir}"}, {"normalized_dir": "{outdir}"}),
    "startwithbestscore": OperationSpec("startwithbestscore", "CONVADING", ["-mode", "StartWithBestScore", "-inputDir", "{inputdir}", "-outputDir", "{outdir}", "-controlsDir", "{controls_dir}", "-bed", "{target_bed}"], {"inputdir": "{inputdir}", "target_bed": "{target_bed}", "controls_dir": "{controls_dir}"}, {"calls_dir": "{outdir}"}),
    "coverage": OperationSpec("coverage", "CNVKIT", ["coverage", "{bam}", "{target_bed}", "-o", "{sample_name}.{tag}.cnn"], {"bam": "{bam}", "target_bed": "{target_bed}"}, {"cnn": "{sample_name}.{tag}.cnn"}),
    "fix": OperationSpec("fix", "CNVKIT", ["fix", "{target_cnn}", "{antitarget_cnn}", "{cnn_reference}", "-o", "{sample_name}.cnr", "--no-gc"], {"target_cnn": "{target_cnn}", "antitarget_cnn": "{antitarget_cnn}", "cnn_reference": "{cnn_reference}"}, {"cnr": "{sample_name}.cnr"}),
    "segment": OperationSpec("segment", "CNVKIT", ["segment", "{cnr}", "-o", "{sample_name}.cns"], {"cnr": "{cnr}"}, {"cns": "{sample_name}.cns"}),
    "antitarget": OperationSpec("antitarget", "CNVKIT", ["antitarget", "{target_bed}", "-o", "{sample_name}.antitarget.bed"], {"target_bed": "{target_bed}"}, {"bed": "{sample_name}.antitarget.bed"}),
    "call": OperationSpec("call", "CNVKIT", ["call", "{cns}", "-o", "{sample_name}.call.cns", "-m", "threshold"], {"cns": "{cns}"}, {"calls": "{sample_name}.call.cns"}),
    "ieva": OperationSpec("ieva", "IEVA", ["--input", "{vcf}", "--reference", "{reference_fasta}", "--list", "{bam_list}", "--outfile", "{sample_name}.iEVA.vcf"], {"vcf": "{vcf}", "reference_fasta": "{reference_fasta}", "bam_list": "{bam_list}"}, {"vcf": "{sample_name}.iEVA.vcf"}),
    "sort_vcf": OperationSpec("sort_vcf", "VCFTOOLS", ["vcf-sort", "{vcf}", "&&", "bgzip", "-f", "{sample_name}.sort.vcf", "&&", "tabix", "-p", "vcf", "{sample_name}.sort.vcf.gz"], {"vcf": "{vcf}"}, {"vcf_gz": "{sample_name}.sort.vcf.gz", "tbi": "{sample_name}.sort.vcf.gz.tbi"}),
    "make_cnv_report": OperationSpec("make_cnv_report", "HELPER_INTERNAL", ["Make_CNV_report", "--infofile", "{infofile}", "--cnv-vcfs", "{cnv_vcf_array}", "--out", "{sample_name}.CNV.Report.tsv"], {"infofile": "{infofile}", "cnv_vcf_array": "{cnv_vcf_array}"}, {"report": "{sample_name}.CNV.Report.tsv"}),
}


ALIASES = {
    "Bwa_mem": "align_fastq",
    "FreeBayes": "freebayes",
    "Concat_VarScan_vcf": "merge_vcf",
    "GATK_CollectReadCounts": "collectreadcounts",
    "GATK_DetermineGermlineContigPloidy": "determinegermlinecontigploidy",
    "GATK_GermlineCNVCaller": "germlinecnvcaller",
    "GATK_PostprocessGermlineCNVCalls": "postprocessgermlinecnvcalls",
    "Decon_ReadInBams": "readinbams",
    "Decon_IdentifyFailures": "identifyfailures",
    "Decon_makeCNVcalls": "makecnvcalls",
    "vcf_norm": "bcftools_norm",
    "Index_vcf": "indexfeaturefile",
    "Split_by_sample": "vcf_filter_by_sample",
    "add_Annotation": "annotation_extractor",
    "iEVA": "ieva",
    "Sort_vcf": "sort_vcf",
    "Make_CNV_report": "make_cnv_report",
    "SureCallTrimmer": "trimmer",
    "LocatIt": "locatit",
    "SamFormatConverter": "samformatconverter",
    "SortSam": "sortsam",
    "BuildBamIndex": "buildbamindex",
    "MarkDuplicates": "markduplicates",
    "AddOrReplaceReadGroups": "addorreplacereadgroups",
    "IndelRealigner": "indelrealigner",
    "BaseRecalibrator": "baserecalibrator",
    "HaplotypeCaller": "haplotypecaller",
    "GenotypeGVCFs": "genotypegvcfs",
    "Mutect2": "mutect2",
    "CombineGVCFs": "combinegvcfs",
    "HardFilter": "hardfilter",
    "VariantAnnotator": "variantannotator",
    "SelectVariants": "selectvariants",
    "VariantFiltration": "variantfiltration",
    "LeftAlignAndTrimVariants": "leftalignandtrimvariants",
    "Freebayes.variant_calling": "variant_calling",
    "Varscan.variant_calling": "varscan_mpileup2snp",
    "BCFTOOLS.norm": "norm",
    "DECON.ReadInBams": "readinbams",
    "DECON.IdentifyFailures": "identifyfailures",
    "DECON.makeCNVcalls": "makecnvcalls",
    "CoNVaDING.StartWithBam": "startwithbam",
    "CoNVaDING.StartWithMatchScore": "startwithmatchscore",
    "CoNVaDING.StartWithBestScore": "startwithbestscore",
    "CNVkit.coverage": "coverage",
    "CNVkit.fix": "fix",
    "CNVkit.segment": "segment",
    "CNVkit.antitarget": "antitarget",
    "CNVkit.call": "call",
    "parallel_fastq_diagnosis": "fastq_diagnosis",
    "parallel_bam_diagnosis": "bam_diagnosis",
    "parallel_align_fastq": "parallel_align_fastq",
    "parallel_Trim_Adapters": "trim_adapters",
    "parallel_Fastq_fiter_Qual": "fastq_fiter_qual",
    "parallel_Fastq_fiter_Len": "fastq_fiter_len",
    "parallel_SamFormatConverter": "samformatconverter",
    "parallel_SortSam": "sortsam",
    "parallel_BuildBamIndex": "buildbamindex",
    "parallel_MarkDuplicates": "markduplicates",
    "parallel_AddOrReplaceReadGroups": "addorreplacereadgroups",
    "parallel_IndelRealigner": "indelrealigner",
    "parallel_BaseRecalibrator": "baserecalibrator",
    "parallel_HaplotypeCaller": "haplotypecaller",
    "parallel_GenotypeGVCFs": "genotypegvcfs",
    "parallel_variant_calling": "variant_calling",
}


def normalize_operation_name(operation: str) -> str:
    if operation in ALIASES:
        return ALIASES[operation]
    text = str(operation or "")
    if text in SCRIPT_OPERATIONS:
        return text
    return text.replace(" ", "_").replace("-", "_").lower()


def operation_spec(operation: str) -> Optional[OperationSpec]:
    normalized = normalize_operation_name(operation)
    if normalized in LEGACY_OPERATION_SPECS:
        return LEGACY_OPERATION_SPECS[normalized]
    if normalized in SCRIPT_OPERATIONS:
        script = SCRIPT_OPERATIONS[normalized]
        return OperationSpec(
            normalized,
            "HELPER_SCRIPT",
            [script],
            metadata={"script": script, "interpreter": "python"},
        )
    return None


def all_catalog_operations() -> List[str]:
    return sorted(set(LEGACY_OPERATION_SPECS) | set(SCRIPT_OPERATIONS))
