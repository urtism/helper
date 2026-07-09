from helper_next.core.tool_wrappers.generic import build_catalog_invocation
from helper_next.core.tool_wrappers.wrappers import (
    BcftoolsNormWrapper,
    Bowtie2AlignmentWrapper,
    BwaAlignmentWrapper,
    DeepVariantWrapper,
    FreeBayesWrapper,
    Gatk3BqsrWrapper,
    Gatk3IndelRealignmentWrapper,
    Gatk4HaplotypeCallerWrapper,
    GatkVariantFiltrationWrapper,
    PicardAddOrReplaceReadGroupsWrapper,
    PicardMarkDuplicatesWrapper,
    SamtoolsWrapper,
    VepAnnotationWrapper,
)


def wrapper_for(operation_name, tool_name):
    tool_upper = str(tool_name or "").upper()
    operation = str(operation_name or "")
    operation_lower = operation.lower()

    if operation == "fastq_alignment" and tool_upper.startswith("BWA"):
        return BwaAlignmentWrapper
    if operation == "fastq_alignment" and tool_upper.startswith("BOWTIE2"):
        return Bowtie2AlignmentWrapper
    if tool_upper.startswith("SAMTOOLS"):
        return SamtoolsWrapper
    if operation == "add_readgroups" and tool_upper.startswith("PICARD"):
        return PicardAddOrReplaceReadGroupsWrapper
    if operation == "mark_pcr_dup" and tool_upper.startswith("PICARD"):
        return PicardMarkDuplicatesWrapper
    if operation == "indel_realignment" and tool_upper.startswith("GATK"):
        return Gatk3IndelRealignmentWrapper
    if operation == "BQ_recalibration" and tool_upper.startswith("GATK"):
        return Gatk3BqsrWrapper
    if operation in ("caller", "variant_calling") and tool_upper.startswith("GATK"):
        return Gatk4HaplotypeCallerWrapper
    if operation in ("caller", "variant_calling") and tool_upper.startswith("DEEPVARIANT"):
        return DeepVariantWrapper
    if operation in ("caller", "variant_calling") and tool_upper.startswith("FREEBAYES"):
        return FreeBayesWrapper
    if operation == "vcf_norm" and tool_upper.startswith("BCFTOOLS"):
        return BcftoolsNormWrapper
    if operation == "vcf_filter" and tool_upper.startswith("GATK"):
        return GatkVariantFiltrationWrapper
    if operation_lower in ("vep_annotation", "vep", "vcf_annotation") and tool_upper.startswith("VEP"):
        return VepAnnotationWrapper
    return None


def build_invocation(operation_name, tool_name, operation_config, tool_config, panel_design=None, reference_info=None, tools_config=None):
    wrapper_class = wrapper_for(operation_name, tool_name)
    if wrapper_class is None:
        return build_catalog_invocation(operation_name, tool_name, operation_config, tool_config, panel_design, reference_info, tools_config)
    wrapper = wrapper_class(operation_config, tool_config, panel_design, reference_info, tools_config)
    return wrapper.build(tool_name, operation_name)
