import subprocess
import argparse
import os
import tools2 as t
import parallel_tools as p
import scripts
import datetime
import functions2 as f
import json


############ prealignment AND FASTQ PROCESSING ############

def trim_adapters(tool, args, threads, ram, ad1, ad2, fastq1, fastq2, workdir, log, reference_fasta, panel_info, tools_info):
	path = tools_info[tool]['path']

	if tool.upper().startswith('AGENT') or tool.upper().startswith('SURECALLTRIMMER'):
		agent = t.AGeNT()
		agent.init_tool(path, threads, ram, args)
		return agent.Trimmer(fastq1, fastq2, log, workdir)

	if tool.upper().startswith('CUTADAPT'):
		cutad = t.Cutadapt()
		cutad.init_tool(path, threads, ram, args)
		return cutad.Trim_Adapters(fastq1, fastq2, ad1, ad2, log, workdir)

def parallel_trim_adapters(tool, args, threads, ram, ad1, ad2, fastq_list, workdir, log, reference_fasta, panel_info, tools_info):
	path = tools_info[tool]['path']

	if tool.upper().startswith('AGENT'):
		agent = p.AGeNT()
		agent.init_tool(path, threads, ram, args)
		return agent.Trimmer(fastq1, fastq2, log, workdir)

	if tool.upper().startswith('CUTADAPT'):
		cutad = p.Cutadapt()
		cutad.init_tool(path, threads, ram, args)
		return cutad.Trim_Adapters(fastq_list, ad1, ad2, log, workdir)

	if tool.upper().startswith('TRIMMOMATIC'):
		pass

def filter_fastq_by_qual(tool, args, threads, ram, qual, fastq1, fastq2, workdir, log, reference_fasta, panel_info, tools_info):
	path = tools_info[tool]['path']

	if tool.upper().startswith('CUTADAPT'):
		cutad = t.Cutadapt()
		cutad.init_tool(path, threads, ram, args)
		return cutad.Fastq_fiter_Qual(fastq1, fastq2, qual, log, workdir)

def parallel_filter_fastq_by_qual(tool, args, threads, ram, qual, fastq_list, workdir, log, reference_fasta, panel_info, tools_info):
	path = tools_info[tool]['path']

	if tool.upper().startswith('CUTADAPT'):
		cutad = p.Cutadapt()
		cutad.init_tool(path, threads, ram, args)
		return cutad.Fastq_fiter_Qual(fastq_list, qual, log, workdir)

def filter_fastq_by_len(tool, args, threads, ram, maxlen, minlen, fastq1, fastq2, workdir, log, reference_fasta, panel_info, tools_info):
	path = tools_info[tool]['path']
	path = tools_info[tool]['path']
	if tool.upper().startswith('CUTADAPT'):		
		cutad = t.Cutadapt()
		cutad.init_tool(path, threads, ram, args)
		return cutad.Fastq_fiter_Len(fastq1, fastq2, maxlen, minlen, log, workdir)

def parallel_filter_fastq_by_len(tool, args, threads, ram, maxlen, minlen, fastq_list, workdir, log, reference_fasta, panel_info, tools_info):
	path = tools_info[tool]['path']
	path = tools_info[tool]['path']
	if tool.upper().startswith('CUTADAPT'):		
		cutad = p.Cutadapt()
		cutad.init_tool(path, threads, ram, args)
		return cutad.Fastq_fiter_Len(fastq_list, maxlen, minlen, log, workdir)

def fastq_QC(tool, args, threads, ram, sample_name, fastq1, fastq2, workdir, log, reference_fasta, panel_info, tools_info):
	path = tools_info[tool]['path']
	if tool.upper().startswith('FASTQC'):
		fastqc = t.Fastqc()
		fastqc.init_tool(path, threads, ram, args)
		return fastqc.fastq_diagnosis(sample_name, fastq1, fastq2, log, workdir)

def parallel_fastq_QC(tool, args, threads, ram, fastq_list, workdir, log, reference_fasta, panel_info, tools_info):
	path = tools_info[tool]['path']
	if tool.upper().startswith('FASTQC'):
		fastqc = p.Fastqc()
		fastqc.init_tool(path, threads, ram, args)
		return fastqc.fastq_diagnosis(fastq_list, log, workdir)

############ ALIGNMENT AND SAM PROCESSING ############

def fastq_alignment(tool, algorithm, args, threads, ram, sample_name, fastq1, fastq2, workdir, log, reference_fasta, panel_info, tools_info):	
	path = tools_info[tool]['path']
	version = tools_info[tool]['version']

	if tool.upper().startswith('BWA'):
		bwa = t.Bwa()
		bwa.init_tool(path, threads, ram, args)
		return bwa.align_fastq(algorithm, sample_name, fastq1, fastq2, reference_fasta, log, workdir)

	elif tool.upper() == 'BOWTIE2':
		bowtie2 = t.Bowtie2()
		bowtie2.init_tool(path, threads, ram, args)
		return bowtie2.align_fastq(sample_name, fastq1, fastq2, reference_fasta, log, workdir)
		print('bowtie2')

	elif tool.upper() == 'NOVOALIGN':
		print('Novoalign')
		nalign = t.Novoalign()
		nalign.init_tool(path, threads, ram, args)
		return nalign.align_fastq(algorithm, sample_name, fastq1, fastq2, reference_fasta, log, workdir)

def parallel_fastq_alignment(tool, algorithm, args, threads, ram, fastq_list, workdir, log, reference_fasta, panel_info, tools_info):	
	path = tools_info[tool]['path']
	version = tools_info[tool]['version']
	#print(fastq_list)

	if tool.upper().startswith('BWA'):
		bwa = p.Bwa()
		bwa.init_tool(path, threads, ram, args)
		#return bwa.align_fastq(algorithm, sample_name, fastq1, fastq2, reference_fasta, log, workdir)
		return bwa.align_fastq(algorithm, fastq_list, reference_fasta, log, workdir)

	elif tool.upper() == 'BOWTIE2':
		bowtie2 = p.Bowtie2()
		bowtie2.init_tool(path, threads, ram, args)
		return bowtie2.align_fastq(fastq_list, reference_fasta, log, workdir)
		print('bowtie2')

def parallel_sam_to_bam(tool, args, threads, ram, sample_name, sam_list, workdir, log, reference_fasta, panel_info, tools_info):
	path = tools_info[tool]['path']
	version = tools_info[tool]['version']

	if tool.upper().startswith('PICARD'):
		picard = p.Picard()
		picard.init_tool(path, threads, ram, args)
		return picard.SamFormatConverter(sample_name, sam_list, log, workdir)

def sam_to_bam(tool, args, threads, ram, sample_name, sam, workdir, log, reference_fasta, panel_info, tools_info):
	path = tools_info[tool]['path']
	version = tools_info[tool]['version']

	if tool.upper().startswith('PICARD'):
		picard = t.Picard()
		picard.init_tool(path, threads, ram, args)
		return picard.SamFormatConverter(sample_name, sam, log, workdir)

def sortSam(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_info, tools_info):
	path = tools_info[tool]['path']
	version = tools_info[tool]['version']

	if tool.upper().startswith('PICARD'):
		picard = t.Picard()
		picard.init_tool(path, threads, ram, args)
		return picard.SortSam(sample_name, bam, log, workdir)

def parallel_sortSam(tool, args, threads, ram, sample_name, bam_list, workdir, log, reference_fasta, panel_info, tools_info):
	path = tools_info[tool]['path']
	version = tools_info[tool]['version']

	if tool.upper().startswith('PICARD'):
		picard = p.Picard()
		picard.init_tool(path, threads, ram, args)
		return picard.SortSam(sample_name, bam_list, log, workdir)

def indexBam(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_info, tools_info):
	path = tools_info[tool]['path']
	if tool.upper().startswith('PICARD'):
		picard = t.Picard()
		picard.init_tool(path, threads, ram, args)
		picard.BuildBamIndex(bam, log, workdir)

def parallel_indexBam(tool, args, threads, ram, bam_list, workdir, log, reference_fasta, panel_info, tools_info):
	path = tools_info[tool]['path']
	if tool.upper().startswith('PICARD'):
		picard = p.Picard()
		picard.init_tool(path, threads, ram, args)
		picard.BuildBamIndex(bam_list, log, workdir)

def bam_QC(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_info, tools_info):
	path = tools_info[tool]['path']
	if tool.upper().startswith('FASTQC'):
		fastqc = t.Fastqc()
		fastqc.init_tool(path, threads, ram, args)
		return fastqc.bam_diagnosis(sample_name, bam, log, workdir)

def parallel_bam_QC(tool, args, threads, ram, bam_list, workdir, log, reference_fasta, panel_info, tools_info):
	path = tools_info[tool]['path']
	if tool.upper().startswith('FASTQC'):
		fastqc = p.Fastqc()
		fastqc.init_tool(path, threads, ram, args)
		return fastqc.bam_diagnosis(bam_list, log, workdir)

def merge_UMI(tool, args, threads, ram, sample_name, sam, fastqI2, workdir, log, reference_fasta, panel_info, tools_info):
	path = tools_info[tool]['path']
	if tool.upper().startswith('AGENT'):
		agent = t.AGeNT()
		agent.init_tool(path, threads, ram, args)
		return agent.LocatIt(sam, fastqI2, log, workdir)

	#bam = tools.LocatIt(cfg['tools']['LOCATIT']['path'],cfg['tools']['LOCATIT']['ram'],bam,fqI2,log,workdir)


############ PRE-PROCESSING ############

def filter_bam():
	pass

def add_readgroups(tool, args, threads, ram, bam, sample_name, runID, workdir, log, panel_info, tools_info):
	path = tools_info[tool]['path']
	panel = panel_info['panel_name']
	if tool.upper().startswith('PICARD'):
		picard = t.Picard()
		picard.init_tool(path, threads, ram, args)
		return picard.AddOrReplaceReadGroups(sample_name, bam, panel, runID, log, workdir)

def parallel_add_readgroups(tool, args, threads, ram, bam_list, runID, workdir, log, panel_info, tools_info):
	path = tools_info[tool]['path']
	panel = panel_info['panel_name']
	if tool.upper().startswith('PICARD'):
		picard = p.Picard()
		picard.init_tool(path, threads, ram, args)
		return picard.AddOrReplaceReadGroups(bam_list, panel, runID, log, workdir)

def mark_pcr_dup(tool, args, threads, ram, bam, sample_name, runID, workdir, log, panel_info, tools_info):
	path = tools_info[tool]['path']
	panel = panel_info['panel_name']
	if tool.upper().startswith('PICARD'):
		picard = t.Picard()
		picard.init_tool(path, threads, ram, args)
		return picard.MarkDuplicates(sample_name, bam, log, workdir)

def parallel_mark_pcr_dup(tool, args, threads, ram, bam_list, runID, workdir, log, panel_info, tools_info):
	path = tools_info[tool]['path']
	panel = panel_info['panel_name']
	if tool.upper().startswith('PICARD'):
		picard = p.Picard()
		picard.init_tool(path, threads, ram, args)
		return picard.MarkDuplicates(bam_list, log, workdir)

def indel_realignment(tool, args, threads, ram, bam, sample_name, mills, runID, reference_fasta, workdir, log, panel_info, tools_info):
	path = tools_info[tool]['path']
	panel = panel_info['panel_name']
	target_list = panel_info['target_list']
	if tool.upper().startswith('GATK'):
		if tools_info[tool]['version'].startswith('3'):
			gatk = t.GATKv3()
			gatk.init_tool(path, threads, ram, args)
			return gatk.IndelRealigner(bam, mills, target_list, reference_fasta, log, workdir)

def parallel_indel_realignment(tool, args, threads, ram, bam_list, mills, runID, reference_fasta, workdir, log, panel_info, tools_info):
	path = tools_info[tool]['path']
	panel = panel_info['panel_name']
	target_list = panel_info['target_list']
	if tool.upper().startswith('GATK'):
		if tools_info[tool]['version'].startswith('3'):
			gatk = p.GATKv3()
			gatk.init_tool(path, threads, ram, args)
			return gatk.IndelRealigner(bam_list, mills, target_list, reference_fasta, log, workdir)

def BQ_recalibration(tool, args, mills, dbsnp, threads, ram, bam, sample_name, runID, reference_fasta, workdir, log, panel_info, tools_info):
	path = tools_info[tool]['path']
	panel = panel_info['panel_name']
	target_list = panel_info['target_list']
	target_bed = panel_info['target_bed']
	if tool.upper().startswith('GATK'):
		if tools_info[tool]['version'].startswith('3'):
			gatk = t.GATKv3()
			gatk.init_tool(path, threads, ram, args)
			return gatk.BaseRecalibrator(bam, dbsnp, mills, target_list, reference_fasta, log, workdir)
		if tools_info[tool]['version'].startswith('4'):
			gatk = t.GATKv4()
			gatk.init_tool(path, threads, ram, args)
			return gatk.BaseRecalibrator(bam, dbsnp, mills, target_bed, reference_fasta, log, workdir)

def parallel_BQ_recalibration(tool, args, mills, dbsnp, threads, ram, bam_list, runID, reference_fasta, workdir, log, panel_info, tools_info):
	path = tools_info[tool]['path']
	panel = panel_info['panel_name']
	target_list = panel_info['target_list']
	if tool.upper().startswith('GATK'):
		if tools_info[tool]['version'].startswith('3'):
			gatk = p.GATKv3()
			gatk.init_tool(path, threads, ram, args)
			return gatk.BaseRecalibrator(bam_list, dbsnp, mills, target_list, reference_fasta, log, workdir)

############ VARIANT CALLING ############

def gvcf_caller():
	path = tools_info[tool]['path']
	version = tools_info[tool]['version']
	panel = panel_info['panel_name']
	target_list = panel_info['target_list']

	if variant_caller.upper().startswith('GATK'):	
		if version.startswith('3'):
			gatk = t.GATKv3()
		if version.startswith('4'):
			gatk = t.GATKv4()
		gatk.init_tool(path, threads, ram, args)
		return gatk.HaplotypeCaller(varcaller, threads, ram, bam, sample_name, reference_fasta, workdir, log, target_list, tools_configuration)

def genotype_germline_single_samples(tool, args, filters, threads, ram, bam, sample_name, runID, reference_fasta, workdir, log, panel_info, tools_info):

	path = tools_info[tool]['path']
	version = tools_info[tool]['version']
	panel = panel_info['panel_name']
	target_list = panel_info['target_list']
	target_bed = panel_info['target_bed']

	if tool.upper().startswith('GATK'):
		if version.startswith('3'):
			gatk = t.GATKv3()
		if version.startswith('4'):
			gatk = t.GATKv4()
		gatk.init_tool(path, threads, ram, args)
		gvcf = gatk.HaplotypeCaller(bam, sample_name, filters, target_list, reference_fasta, log, workdir)
		return gatk.GenotypeGVCFs(gvcf, sample_name, filters, target_list, reference_fasta, log, workdir)

	if tool.upper().startswith('FREEBAYES'):
		freebayes = t.Freebayes()
		freebayes.init_tool(path, threads, ram, args)
		return freebayes.variant_calling(bam, sample_name, filters, target_bed, reference_fasta, log, workdir)

	if tool.upper().startswith('VARSCAN'):
		varscan = t.Varscan()
		samtools = t.Samtools()
		samtools.init_tool(tools_info['SAMTOOLS']['path'], threads, ram, args)
		mpileup = samtools.mpileup(sample_name, [bam], filters, target_bed, reference_fasta, log, workdir)
		varscan.init_tool(path, threads, ram, args)
		return varscan.variant_calling(mpileup,[sample_name], filters, target_bed, reference_fasta, log, workdir)

def parallel_genotype_germline_single_samples(tool, args, filters, threads, ram, bam_list, runID, reference_fasta, workdir, log, panel_info, tools_info):

	path = tools_info[tool]['path']
	version = tools_info[tool]['version']
	panel = panel_info['panel_name']
	target_list = panel_info['target_list']
	target_bed = panel_info['target_bed']

	if tool.upper().startswith('GATK'):
		if version.startswith('3'):
			gatk = p.GATKv3()
		if version.startswith('4'):
			gatk = p.GATKv4()
		gatk.init_tool(path, threads, ram, args)
		gvcf_list =  gatk.HaplotypeCaller(bam_list, filters, target_list, reference_fasta, log, workdir)
		return gatk.GenotypeGVCFs(gvcf_list, runID, filters, target_list, reference_fasta, log, workdir)

	if tool.upper().startswith('FREEBAYES'):
		freebayes = p.Freebayes()
		freebayes.init_tool(path, threads, ram, args)
		return freebayes.variant_calling(bam_list, filters, target_bed, reference_fasta, log, workdir)

	if tool.upper().startswith('VARSCAN'):
		varscan = p.Varscan()
		samtools = p.Samtools()
		samtools.init_tool(tools_info['SAMTOOLS']['path'], threads, ram, args)
		mpileup_list = samtools.mpileup(bam_list, filters, target_bed, reference_fasta, log, workdir)
		varscan.init_tool(path, threads, ram, args)
		return varscan.variant_calling(mpileup_list, filters, target_bed, reference_fasta, log, workdir)

def genotype_germline_cohort(tool, args, filters, threads, ram, samplename_array, bam_array, runID, reference_fasta, workdir, log, panel_info, tools_info):
	print('-genotype_germline_cohort')

	path = tools_info[tool]['path']
	version = tools_info[tool]['version']
	panel = panel_info['panel_name']
	target_list = panel_info['target_list']
	target_bed = panel_info['target_bed']
	
	samples_dict = {}
	#print(tool, args, filters, threads, ram, samplename_array, bam_array, runID, reference_fasta)

	if tool.upper().startswith('GATK'):
		if version.startswith('3'):
			gatk = t.GATKv3()
		if version.startswith('4'):
			gatk = t.GATKv4()

		#new_args = args + ['-ERC','GVCF']
		gatk.init_tool(path, threads, ram, args)
		gvcf_array = []
		for bam in bam_array:
			
			sample_name = bam.split('/')[-1].split('.')[0]
			gvcf = gatk.HaplotypeCaller(bam, sample_name, filters, target_bed, reference_fasta, log, workdir)
			gvcf_array += [gvcf]
		gatk.init_tool(path, threads, ram, args)
		gvcf = gatk.CombineGVCFs(gvcf_array, runID, target_bed, reference_fasta, log, workdir)
		return gatk.GenotypeGVCFs(gvcf, runID, filters, target_bed, reference_fasta, log, workdir), gvcf_array

	if tool.upper().startswith('FREEBAYES'):
		freebayes = t.Freebayes()
		freebayes.init_tool(path, threads, ram, args)
		return freebayes.variant_calling(bam_array, runID, filters, target_bed, reference_fasta, log, workdir), []

	if tool.upper().startswith('VARSCAN'):
		varscan = t.Varscan()
		samtools = t.Samtools()
		samtools.init_tool(tools_info['SAMTOOLS']['path'], threads, ram, args)
		mpileup_list = samtools.mpileup(runID, bam_array, filters, target_bed, reference_fasta, log, workdir)
		varscan.init_tool(path, threads, ram, args)
		return varscan.variant_calling(mpileup_list, samplename_array, filters, target_bed, reference_fasta, log, workdir), []

def genotype_germline_trio(tool, args, filters, threads, ram, samplename_array, bam_array, runID, reference_fasta, workdir, log, panel_info, tools_info):
	print('-genotype_germline_trio')

	path = tools_info[tool]['path']
	version = tools_info[tool]['version']
	panel = panel_info['panel_name']
	target_list = panel_info['target_list']
	target_bed = panel_info['target_bed']
	
	samples_dict = {}

	if tool.upper().startswith('GATK'):
		if version.startswith('3'):
			gatk = t.GATKv3()
		if version.startswith('4'):
			gatk = t.GATKv4()

		#new_args = args + ['-ERC','GVCF']
		gatk.init_tool(path, threads, ram, args)
		gvcf_array = []
		for bam in bam_array:
			sample_name = bam.split('/')[-1].split('.')[0]
			gvcf = gatk.HaplotypeCaller(bam, sample_name, filters, target_list, reference_fasta, log, workdir)
			gvcf_array += [gvcf]
		gatk.init_tool(path, threads, ram, args)
		gvcf = gatk.CombineGVCFs(gvcf_array, runID, target_list, reference_fasta, log, workdir)
		return gatk.GenotypeGVCFs(gvcf, runID, filters, target_list, reference_fasta, log, workdir), gvcf_array

	if tool.upper().startswith('FREEBAYES'):
		freebayes = t.Freebayes()
		freebayes.init_tool(path, threads, ram, args)
		return freebayes.variant_calling(bam_array, runID, filters, target_bed, reference_fasta, log, workdir), []

	if tool.upper().startswith('VARSCAN'):
		varscan = t.Varscan()
		samtools = t.Samtools()
		samtools.init_tool(tools_info['SAMTOOLS']['path'], threads, ram, args)
		mpileup_list = samtools.mpileup(runID, bam_array, filters, target_bed, reference_fasta, log, workdir)
		varscan.init_tool(path, threads, ram, args)
		return varscan.variant_calling(mpileup_list, samplename_array, filters, target_bed, reference_fasta, log, workdir), []


def genotype_somatic_single_samples(tool, args, filters, threads, ram, bam, sample_name, reference_fasta, workdir, log, panel_info, tools_info):
	#print('-genotype_somatic_single_samples')

	path = tools_info[tool]['path']
	version = tools_info[tool]['version']
	panel = panel_info['panel_name']
	target_list = panel_info['target_list']
	target_bed = panel_info['target_bed']
	
	samples_dict = {}

	if tool.upper().startswith('GATK'):
		if version.startswith('3'):
			gatk = t.GATKv3()
		if version.startswith('4'):
			gatk = t.GATKv4()

		gatk.init_tool(path, threads, ram, args)
		vcf = gatk.Mutect2(bam, sample_name, '', '', filters, target_list, reference_fasta, log, workdir)
		gatk.init_tool(path, threads, ram, args)
		#gvcf = gatk.CombineGVCFs(gvcf_array, runID, target_list, reference_fasta, log, workdir)
		return vcf

def genotype_somatic_case_control(tool, args, filters, threads, ram, case_bam, case_name, ctrl_bam, ctrl_name, reference_fasta, workdir, log, panel_info, tools_info):
	print('-genotype_somatic_case_control')

	path = tools_info[tool]['path']
	version = tools_info[tool]['version']
	panel = panel_info['panel_name']
	target_list = panel_info['target_list']
	target_bed = panel_info['target_bed']
	
	samples_dict = {}

	if tool.upper().startswith('GATK'):
		if version.startswith('3'):
			gatk = t.GATKv3()
		if version.startswith('4'):
			gatk = t.GATKv4()

		gatk.init_tool(path, threads, ram, args)
		vcf = gatk.Mutect2(case_bam, case_name, control_bam, control_name, filters, target_list, reference_fasta, log, workdir)
		gatk.init_tool(path, threads, ram, args)
		#gvcf = gatk.CombineGVCFs(gvcf_array, runID, target_list, reference_fasta, log, workdir)
		return vcf

def vcf_QC():
	pass

############ CNV-CALLING #############

def CNV_calling(tool, tool_args, filters, threads, ram, bam_array, runID, reference_fasta, workdir, log, panel_info, tools_info):
	
	path = tools_info[tool]['path']
	version = tools_info[tool]['version']
	panel = panel_info['panel_name']
	args = tool_args['args']

	cnv_target_list = panel_info['cnv_target_list']
	#cnv_target_bed = panel_info['cnv_target_bed']
	cnv_GATK_ploidy_model = panel_info['cnv_ploidy_model']
	cnv_GATK_calls_model = panel_info['cnv_calls_model']

	try:
		CONVADING_controls_dir = panel_info['CoNVaDING_controls_dir']
	except:
		CONVADING_controls_dir = ''
	try:	
		CNVkit_reference = panel_info['CNVkit_reference']
	except:
		CNVkit_reference = ''
	samples_dict = {}
	
	if cnv_GATK_ploidy_model == "":
		cnv_GATK_ploidy_model = FILES_DIR + '/Prior.ploidy'

	if tool.upper().startswith('GATK'):

		if version.startswith('4'):
			gatk = t.GATKv4()
			gatk.init_tool(path, threads, ram, args)
			#dir_cnv = workdir +'/CNV_HDF5'
			new_args = args + ['-ERC','GVCF']
			sample_index = 0
			hdf5_array = []
			cnv_list = []
			for sample_name, bam in bam_array:

				if bam != '':
					print('-CollectReadCounts: '+sample_name)
					hdf5 = gatk.CollectReadCounts(bam, sample_name, cnv_target_list, log, workdir)
					hdf5_array += [[hdf5, sample_name, sample_index]]
					sample_index += 1
		print('-DetermineGermlineContigPloidy')
		sample_ploidy = gatk.DetermineGermlineContigPloidy(hdf5_array, runID, cnv_GATK_ploidy_model, log, workdir)
		print('-GermlineCNVCaller')
		sample_calls, sample_model = gatk.GermlineCNVCaller(hdf5_array, runID, sample_ploidy, cnv_GATK_calls_model, log, workdir)

		if cnv_GATK_calls_model == "":
			cnv_GATK_calls_model = sample_model

		for hdf5, sample_name, sample_index in hdf5_array:
			print('-PostprocessGermlineCNVCalls: '+sample_name)
			cnv_vcf, segments_vcf, copy_ratios_vcf = gatk.PostprocessGermlineCNVCalls(sample_name, sample_index, sample_calls, sample_ploidy, cnv_GATK_calls_model, log, workdir)
			cnv_list += [cnv_vcf]
		return report_CNV(cnv_list, workdir, log, panel_configuration, tools_configuration)
			#cnv_vcf_array += [cnv_vcf]
			#f.Copy([cnv_vcf, segments_vcf],dirs['storage'])
			#f.Copy([cnv_vcf, segments_vcf],dirs['out'])
		
		# CNV_report = tools.Make_CNV_report(dirs['files'] +'/'+panel +'_exons_info.txt', cnv_vcf_array, cnv_log, dirs['CNV'])
		# f.Copy([GATK_CNV_report],dirs['out'])
		# f.Copy([GATK_CNV_report],dirs['storage'])

	if tool.upper().startswith('DECON'):
		decon = t.DECON()
		decon.init_tool(path, threads, ram, args)
		bam_list = workdir+'/deconbams.list'
		bam_l = open(bam_list,'w+')

		for sample_name, bam in bam_array:
			bam_l.write(bam+'\n')
		bam_l.close()
		with f.working_directory(path):			
			rdata = decon.ReadInBams(bam_list, runID, cnv_target_bed, reference_fasta, log, workdir)
			decon.IdentifyFailures(rdata, runID, reference_fasta, log, workdir)
			calls = decon.makeCNVcalls(rdata, runID, reference_fasta, log, workdir)

	if tool.upper().startswith('CONVADING'):
		convading = t.CoNVaDING()
		convading.init_tool(path, threads, ram, args)
		tmp = workdir +"/tmp_convading"
		tmp_bam = tmp + "/bam"
		tmp_coverage =  tmp + "/coverage"
		tmp_coverage_norm =  tmp + "/coverage_norm"
		tmp_result =  tmp + "/calls"

		f.makedirs([tmp, tmp_bam, tmp_coverage, tmp_coverage_norm, tmp_result])
		
		for sample_name, bam in bam_array:
			bai= bam+'.bai'
			f.Copy([bam],tmp_bam +"/"+sample_name + '.bam')
			f.Copy([bai],tmp_bam +"/"+sample_name + '.bai')

		controls_dir = convading.StartWithBam(tmp_bam, cnv_target_bed, CONVADING_controls_dir, log, tmp_coverage)
		s = convading.StartWithMatchScore(tmp_coverage, cnv_target_bed, controls_dir, log, tmp_coverage_norm)
		s = convading.StartWithBestScore(tmp_coverage_norm, cnv_target_bed, controls_dir, log, tmp_result)

	if tool.upper().startswith('CNVKIT'):
		cnvkit = t.CNVkit()
		cnvkit.init_tool(path, threads, ram, args)
		tmp = workdir +"/tmp_cnvkit"
		tmp_cnn =  tmp + "/cnn"
		tmp_cnr =  tmp + "/cnr"
		tmp_cns =  tmp + "/cns"
		tmp_call =  tmp + "/call"

		algorithm = tool_args['algorithm']
		threshold = tool_args['threshold']

		f.makedirs([tmp, tmp_cnn, tmp_cnr, tmp_cns, tmp_call])

		cnv_antitarget_bed = cnvkit.antitarget(cnv_target_bed, log, tmp)
		
		for sample_name, bam in bam_array:
			
			target_cnn = cnvkit.coverage(bam, cnv_target_bed, 'targetcoverage', log, tmp_cnn)
			antitarget_cnn = cnvkit.coverage(bam, cnv_antitarget_bed, 'antitargetcoverage', log, tmp_cnn)
			cnr = cnvkit.fix(target_cnn, antitarget_cnn, CNVkit_reference, log, tmp_cnr)
			cns = cnvkit.segment(cnr, algorithm, threshold, log, tmp_cns)
			call = cnvkit.call(cns, log, tmp_call)

	return True

############ POST-PROCESSING ############

def vcf_filter(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_info, tools_info):
	
	if tool.upper().startswith('GATK'):
		path = tools_info[tool]['path']
		version = tools_info[tool]['version']
		if version.startswith('3'):
			gatk = t.GATKv3()
		if version.startswith('4'):
			gatk = t.GATKv4()
		gatk.init_tool(path, threads, ram, args)
		return gatk.VariantFiltration(vcf, reference_fasta, log, workdir)

	else:
		path = SCRIPTS_DIR
		return scripts.Vcf_filter(path,vcf,log,workdir)

def hard_filter(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_info, tools_info):
	path = tools_info[tool]['path']
	version = tools_info[tool]['version']
	
	if tool.upper().startswith('GATK'):
		if version.startswith('3'):
			gatk = t.GATKv3()
		if version.startswith('4'):
			gatk = t.GATKv4()
		gatk.init_tool(path, threads, ram, args)
		return gatk.HardFilter(vcf, reference_fasta, log, workdir)

def vcf_merge(tool, args, threads, ram, sample_name, vcfs, workdir, log, panel_info, tools_info):
	path = SCRIPTS_DIR

	gatk_vcf = None
	freeb_vcf = None
	varscan_vcf = None

	for vc in vcfs.keys():
		if vc.upper().startswith('GATK'):
			gatk_vcf = vcfs[vc]
		if vc.upper().startswith('FREEB'):
			freeb_vcf = vcfs[vc]
		if vc.upper().startswith('VARSCAN'):
			varscan_vcf = vcfs[vc]

	return scripts.merge_vcfs(path,sample_name,gatk_vcf,freeb_vcf,varscan_vcf,log,workdir)

def vcf_split_by_sample(tool, args, threads, ram, vcf, sample_name, workdir, log, panel_info, tools_info):
	path = SCRIPTS_DIR
	return scripts.Filter_by_sample(path,vcf,sample_name,log,workdir)

def vcf_norm(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_info, tools_info):
	path = tools_info[tool]['path']
	version = tools_info[tool]['version']
	
	if tool.upper().startswith('GATK'):
		if version.startswith('3'):
			gatk = t.GATKv3()
		if version.startswith('4'):
			gatk = t.GATKv4()
		gatk.init_tool(path, threads, ram, args)
		return gatk.LeftAlignAndTrimVariants(vcf, reference_fasta, log, workdir)

	if tool.upper().startswith('BCFTOOLS'):
		bcftools = t.BCFTOOLS()
		bcftools.init_tool(path, threads, ram, args)
		return bcftools.norm(vcf, reference_fasta, log, workdir)


############ VARIANT ANNOTATION ############

def vcf_annotation(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_info, tools_info):

	path = tools_info[tool]['path']
	version = tools_info[tool]['version']
	#plugins = tools_info[tool]['plugins']
	panel = panel_info['panel_name']
	target_list = panel_info['target_list']
	target_bed = panel_info['target_bed']
	#print(vcf, args)

	if tool.upper().startswith('VEP'):
		vep = t.VEP()

		#print(args)
		vep.init_tool(path, threads, ram, args['args'])
		plugins = args['plugins']
		assembly = args['assembly']
		species = args['species']
		
		vcf = vep.vcf_annotation(vcf, reference_fasta, assembly, species, plugins, tools_info, log, workdir)	
	return vcf

########### VARIANT POSTANNOTATION #######
def filter_by_transcripts(args, vcf, workdir, log, panel_info, tools_info):
	transcript_list = panel_info['transcripts_list']
	path = SCRIPTS_DIR
	if transcript_list != '':
		return scripts.filter_transcript(path,transcript_list,vcf,log,workdir)
	else:
		return vcf

############ VCF TO TSV ############

def vcf_to_tsv(tool, args, threads, ram, vcf, sample_name, reference_fasta, workdir, log, panel_info, tools_info):
	path = SCRIPTS_DIR
	tags_file = args['tags_file']
	format = args['format_tags']
	info = args['info_tags']

	return scripts.Vcf_to_tsv(path,vcf,tags_file,format,info,sample_name,log,workdir)

def report_annotation(tool, args, filter, vcf, tsv, sample_name, reference_fasta, workdir, log, panel_info, tools_info):
	path = SCRIPTS_DIR
	tag_list = args['tags_file']
	if filter:
		transcript_list = panel_info['transcripts_list']
	else:
		transcript_list = ''
	return scripts.add_Annotation(path,sample_name,vcf,tsv,tag_list,transcript_list,log,workdir)

def report_CNV(vcf_list, workdir, log, panel_info, tools_info):
	path = SCRIPTS_DIR
	infofile = panel_info['cnv_exons_info']
	return f.Make_CNV_report(infofile,vcf_list,workdir,log)

#########################################################################################################################

def pre_alignment(samplesheet, prealignment_info, reference_fasta, panel_configuration, tools_configuration, runID):
	
	prealignment_start_time = datetime.datetime.now()
	print('\nPRE-ALIGNMENT:')

	f.makedirs([dirs['PREALIGN_DIR']])

	samples = f.read_samplesheet(samplesheet, 'prealignment')
	#workflow = alignment_pipe['workflow']
	samplesheet['alignment'] = {}

	threads = prealignment_info['threads']
	ram = prealignment_info['ram']
	workflow = prealignment_info['workflow']
	logdir = dirs['LOGS_DIR'] + '/PREALIGNMENT'
	f.makedirs([logdir])

	for sampleID in samples.keys():
		samplesheet['alignment'][sampleID] = {}

		for sample in samples[sampleID]:
			sample_type, sample_name, fastqR1, fastqR2, fastqI2 = sample
			samplesheet['alignment'][sampleID][sample_type] = {}

			if fastqR1 != '' and fastqR2 != '':
				log = open(logdir + '/' + sample_name + '.log','w+')

				if 'trim_adapters' in workflow:

					workdir = '/'.join([dirs['PREALIGN_DIR'], 'TRIM_ADAPTERS'])
					f.makedirs([workdir])

					tool = prealignment_info['trim_adapters']['tool']
					args = prealignment_info['trim_adapters'][tool]['args']
					adapter1 = prealignment_info['trim_adapters']['adapter1']
					adapter2 = prealignment_info['trim_adapters']['adapter2']
					fastqR1,fastqR2 = trim_adapters(tool, args, threads, ram, adapter1, adapter2, fastqR1, fastqR2, workdir, log, reference_fasta, panel_configuration, tools_configuration)

				if 'filter_fastq_by_qual' in workflow:
					workdir = '/'.join([dirs['PREALIGN_DIR'], 'FILTER_FASTQ'])
					f.makedirs([workdir])
					tool = prealignment_info['filter_fastq_by_qual']['tool']
					qual = prealignment_info['filter_fastq_by_qual']['quality']
					args = prealignment_info['filter_fastq_by_qual'][tool]['args']
					fastqR1,fastqR2 = filter_fastq_by_qual(tool, args, threads, ram, qual, fastqR1, fastqR2, workdir, log, reference_fasta, panel_configuration, tools_configuration)

				if 'filter_fastq_by_len' in workflow:
					workdir = '/'.join([dirs['PREALIGN_DIR'], 'FILTER_FASTQ'])
					f.makedirs([workdir])
					tool = prealignment_info['filter_fastq_by_len']['tool']
					args = prealignment_info['filter_fastq_by_len'][tool]['args']				
					maxlen = prealignment_info['filter_fastq_by_len']['maxlen']
					minlen = prealignment_info['filter_fastq_by_len']['minlen']
					fastqR1,fastqR2 = filter_fastq_by_len(tool, args, threads, ram, maxlen, minlen, fastqR1, fastqR2, workdir, log, reference_fasta, panel_configuration, tools_configuration)
				
				if 'fastq_QC' in workflow:
					workdir = '/'.join([dirs['PREALIGN_DIR'], 'FASTQ_QC'])
					f.makedirs([workdir])
					tool = prealignment_info['fastq_QC']['tool']
					args = prealignment_info['fastq_QC'][tool]['args']
					fastq_QC(tool, args, threads, ram, sample_name, fastqR1, fastqR2, workdir, log, reference_fasta, panel_configuration, tools_configuration)


			samplesheet['alignment'][sampleID][sample_type] = {'sample_name':sample_name, 'fastq_R1':fastqR1, 'fastq_R2':fastqR2, 'fastq_I2':fastqI2}

	with open(opts.samplesheet, 'w') as ss:
		json.dump(samplesheet, ss, indent=4)

	log.close()
	return samplesheet

def p_pre_alignment(samplesheet, prealignment_info, reference_fasta, panel_configuration, tools_configuration, runID):
	
	print('\nPRE-ALIGNMENT:')
	prealignment_start_time = datetime.datetime.now()

	
	f.makedirs([dirs['PREALIGN_DIR']])

	log = open(dirs['LOGS_DIR'] + '/prealignment.log','w+')
	samples = f.read_samplesheet(samplesheet, 'prealignment')
	fastq_list = []
	#workflow = alignment_pipe['workflow']
	samplesheet['alignment'] = {}

	threads = prealignment_info['threads']
	ram = prealignment_info['ram']
	workflow = prealignment_info['workflow']
	workdir = dirs['PREALIGN_DIR']	
	logdir = dirs['LOGS_DIR'] + '/PREALIGNMENT'
	f.makedirs([logdir])
	logs_list = []

	for sampleID in samples.keys():
		samplesheet['alignment'][sampleID] = {}

		for sample in samples[sampleID]:
			sample_type, sample_name, fastqR1, fastqR2, fastqI2 = sample
			samplesheet['alignment'][sampleID][sample_type] = {}

			if fastqR1 != '' and fastqR2 != '':
				logs_list += [workdir +'/'+sample_name+'.log']
				fastq_list += [[sample_name, fastqR1, fastqR2]]
	
	if 'trim_adapters' in workflow:
		#workdir = '/'.join([dirs['PREALIGN_DIR'], 'TRIM_ADAPTERS'])
		#f.makedirs([workdir])

		tool = prealignment_info['trim_adapters']['tool']
		args = prealignment_info['trim_adapters'][tool]['args']
		adapter1 = prealignment_info['trim_adapters']['adapter1']
		adapter2 = prealignment_info['trim_adapters']['adapter2']
		fastq_list = parallel_trim_adapters(tool, args, threads, ram, adapter1, adapter2, fastq_list, workdir, log, reference_fasta, panel_configuration, tools_configuration)

	if 'filter_fastq_by_qual' in workflow:
		#workdir = '/'.join([dirs['PREALIGN_DIR'], 'FILTER_FASTQ'])
		#f.makedirs([workdir])
		tool = prealignment_info['filter_fastq_by_qual']['tool']
		qual = prealignment_info['filter_fastq_by_qual']['quality']
		args = prealignment_info['filter_fastq_by_qual'][tool]['args']
		fastq_list = parallel_filter_fastq_by_qual(tool, args, threads, ram, qual, fastq_list, workdir, log, reference_fasta, panel_configuration, tools_configuration)

	if 'filter_fastq_by_len' in workflow:
		#workdir = '/'.join([dirs['PREALIGN_DIR'], 'FILTER_FASTQ'])
		#f.makedirs([workdir])
		tool = prealignment_info['filter_fastq_by_len']['tool']
		args = prealignment_info['filter_fastq_by_len'][tool]['args']				
		maxlen = prealignment_info['filter_fastq_by_len']['maxlen']
		minlen = prealignment_info['filter_fastq_by_len']['minlen']
		fastq_list = parallel_filter_fastq_by_len(tool, args, threads, ram, maxlen, minlen, fastq_list, workdir, log, reference_fasta, panel_configuration, tools_configuration)
	
	if 'fastq_QC' in workflow:
		#workdir = '/'.join([dirs['PREALIGN_DIR'], 'FASTQ_QC'])
		#f.makedirs([workdir])
		tool = prealignment_info['fastq_QC']['tool']
		args = prealignment_info['fastq_QC'][tool]['args']
		parallel_fastq_QC(tool, args, threads, ram, fastq_list, workdir, log, reference_fasta, panel_configuration, tools_configuration)

	### Manage LOG files ###
	log.close() 
	for logfile in logs_list:
		f.Move([logfile],logdir)
	#########################

	for sampleID in samples.keys():
		for sample in samples[sampleID]:
			sample_type, sample_name, fastqR1, fastqR2, fastqI2 = sample
			for sample_n, fq1, fq2 in fastq_list:
				if sample_n == sample_name:
					samplesheet['alignment'][sampleID][sample_type] = {'sample_name':sample_name, 'fastq_R1':fq1, 'fastq_R2':fq2, 'fastq_I2':fastqI2}

	with open(opts.samplesheet, 'w') as ss:
		json.dump(samplesheet, ss, indent=4)

	log.close()
	return samplesheet

def alignment(samplesheet, alignment_info, reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID):
	
	print('\nALIGNMENT:')
	alignment_start_time = datetime.datetime.now()
	#f.makedirs([dirs['alignment']])
	#log = open(dirs['log'] + '/Alignment.log','w+')
	f.makedirs([dirs['ALIGN_DIR']])
	
	workdir = dirs['ALIGN_DIR']

	alignment_log = open(dirs['LOGS_DIR'] + '/alignment.log','w+')
	samples = f.read_samplesheet(samplesheet, 'alignment')

	#workflow = alignment_pipe['workflow']
	samplesheet['preprocessing'] = {}

	threads = alignment_info['threads']
	ram = alignment_info['ram']
	workflow = alignment_info['workflow']
	logdir = dirs['LOGS_DIR'] + '/ALIGNMENT'
	f.makedirs([logdir])

	for sampleID in samples.keys():
		samplesheet['preprocessing'][sampleID] = {}

		for sample in samples[sampleID]:

			sample_type, sample_name, fastqR1, fastqR2, fastqI2 = sample
			bam = ''
			samplesheet['preprocessing'][sampleID][sample_type] = {} 

			if fastqR1 != '' and fastqR2 != '':
				
				log = open(logdir + '/' + sample_name + '.log','w+')

				tool = alignment_info['fastq_alignment']['tool']
				args = alignment_info['fastq_alignment'][tool]['args']
				try:
					algorithm = alignment_info['fastq_alignment'][tool]['algorithm']
				except:
					algorithm = ''
				
				sam = fastq_alignment(tool, algorithm, args, threads, ram, sample_name, fastqR1, fastqR2, workdir, log, reference_fasta, panel_configuration, tools_configuration)
				
				tool = alignment_info['sam_to_bam']['tool']
				args = alignment_info['sam_to_bam'][tool]['args']
				bam = sam_to_bam(tool, args, threads, ram, sample_name, sam, workdir, log, reference_fasta, panel_configuration, tools_configuration)
				
				tool = alignment_info['sortSam']['tool']
				args = alignment_info['sortSam'][tool]['args']
				bam = sortSam(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_configuration, tools_configuration)

				tool = alignment_info['sortSam']['tool']
				args = alignment_info['sortSam'][tool]['args']
				indexBam(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_configuration, tools_configuration)

				if 'merge_UMI' in workflow:
					pass

				if 'bam_QC' in workflow:
					tool = alignment_info['bam_QC']['tool']
					args = alignment_info['bam_QC'][tool]['args']
					workdir = '/'.join([dirs['ALIGN_DIR'], 'BAM_QC'])
					bam_QC(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_configuration, tools_configuration)

			samplesheet['preprocessing'][sampleID][sample_type] = {'sample_name':sample_name, 'bam':bam}

	with open(opts.samplesheet, 'w') as ss:
		json.dump(samplesheet, ss, indent=4)

	elapsed_time = divmod((datetime.datetime.now() - alignment_start_time).total_seconds(),60)
	print("-align_fastq: %d min, %d sec" % elapsed_time)
	log.close()
	return samplesheet

def p_alignment(samplesheet, alignment_info, reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID):
	
	print('\nALIGNMENT:')
	alignment_start_time = datetime.datetime.now()
	
	#f.makedirs([dirs['alignment']])
	#log = open(dirs['log'] + '/Alignment.log','w+')
	f.makedirs([dirs['ALIGN_DIR']])
	
	workdir = dirs['ALIGN_DIR']
	logdir = dirs['LOGS_DIR'] + '/ALIGNMENT'
	f.makedirs([logdir])

	alignment_log = dirs['LOGS_DIR'] + '/alignment.log'
	log = open(alignment_log,'w+')
	
	samples = f.read_samplesheet(samplesheet, 'alignment')

	#workflow = alignment_pipe['workflow']
	samplesheet['preprocessing'] = {}

	threads = alignment_info['threads']
	ram = alignment_info['ram']
	workflow = alignment_info['workflow']
	
	fastq_list = []
	logs_list = []

	for sampleID in samples.keys():
		samplesheet['preprocessing'][sampleID] = {}

		for sample in samples[sampleID]:

			sample_type, sample_name, fastqR1, fastqR2, fastqI2 = sample
			bam = ''
			if fastqR1 != '' and fastqR2 != '':
				logs_list += [workdir +'/'+sample_name+'.log']
				fastq_list += [[sample_name, fastqR1, fastqR2]]
				samplesheet['preprocessing'][sampleID][sample_type] = {} 


	tool = alignment_info['fastq_alignment']['tool']
	try:
		algorithm = alignment_info['fastq_alignment'][tool]['algorithm']
	except:
		algorithm = ''
	args = alignment_info['fastq_alignment'][tool]['args']
	sam_list = parallel_fastq_alignment(tool, algorithm, args, threads, ram, fastq_list, workdir, log, reference_fasta, panel_configuration, tools_configuration)

	tool = alignment_info['sam_to_bam']['tool']
	args = alignment_info['sam_to_bam'][tool]['args']
	bam_list = parallel_sam_to_bam(tool, args, threads, ram, sample_name, sam_list, workdir, log, reference_fasta, panel_configuration, tools_configuration)

	tool = alignment_info['sortSam']['tool']
	args = alignment_info['sortSam'][tool]['args']
	bam_list = parallel_sortSam(tool, args, threads, ram, sample_name, bam_list, workdir, log, reference_fasta, panel_configuration, tools_configuration)

	tool = alignment_info['sortSam']['tool']
	args = alignment_info['sortSam'][tool]['args']
	parallel_indexBam(tool, args, threads, ram, bam_list, workdir, log, reference_fasta, panel_configuration, tools_configuration)

	### Manage LOG files ###
	log.close() 
	for logfile in logs_list:
		f.Move([logfile],logdir)
	#########################	

	elapsed_time = divmod((datetime.datetime.now() - alignment_start_time).total_seconds(),60)
	
	### UPDATE SAMPLESHEET ###
	for sampleID in samples.keys():
		for sample in samples[sampleID]:
			sample_type, sample_name, fastqR1, fastqR2, fastqI2 = sample
			for sample_n, bam in bam_list:
				if sample_n == sample_name:
					samplesheet['preprocessing'][sampleID][sample_type] = {'sample_name':sample_name, 'bam':bam}

	with open(opts.samplesheet, 'w') as ss:
			json.dump(samplesheet, ss, indent=4)
	###########################

	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	#f.Delete([sam,bam])
	return samplesheet

def	p_preprocessing(samplesheet, preprocessing_info, reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID):

	print('\nPRE-PROCESSING:')
	preprocessing_start_time = datetime.datetime.now()
	
	f.makedirs([dirs['PREPROC_DIR']])
	workdir = dirs['PREPROC_DIR']
	logdir = dirs['LOGS_DIR'] + '/PREPROCESSING'
	f.makedirs([logdir])

	preprocs_log = dirs['LOGS_DIR'] + '/preprocessing.log'
	log = open(preprocs_log,'w+')

	samplesheet['variantcalling'] = {}
	samples = f.read_samplesheet(samplesheet, 'preprocessing')

	threads = preprocessing_info['threads']
	ram = preprocessing_info['ram']
	workflow = preprocessing_info['workflow']

	logs_list = []
	try:
		mills = tools_configuration['mills']['path']
	except:
		mills = ''
	try:
		dbsnp = tools_configuration['dbsnp']['path']
	except:
		dbsnp = ''
	bam_list = []
	
	for sampleID in samples.keys():
		samplesheet['variantcalling'][sampleID] = {}

		for sample in samples[sampleID]:
			sample_type, sample_name, bam = sample		
			samplesheet['variantcalling'][sampleID][sample_type] = {}
			if bam != '':
				logs_list += [workdir +'/'+sample_name+'.log']
				bam_list += [[sample_name,bam]]

	if 'add_readgroups' in workflow:
		tool = preprocessing_info['add_readgroups']['tool']
		args = preprocessing_info['add_readgroups'][tool]['args']
		bam_list = parallel_add_readgroups(tool, args, threads, ram, bam_list, runID, workdir, log, panel_configuration, tools_configuration)
		parallel_indexBam(tool, args, threads, ram, bam_list, workdir, log, reference_fasta, panel_configuration, tools_configuration)

	if 'filter_bam' in workflow:
		tool = preprocessing_info['filter_bam']['tool']
		args = preprocessing_info['filter_bam'][tool]['args']
		bam_list = parallel_filter_bam()
		parallel_indexBam(tool, args, threads, ram, bam_list, workdir, log, reference_fasta, panel_configuration, tools_configuration)
	
	if 'mark_pcr_dup' in workflow:
		tool = preprocessing_info['mark_pcr_dup']['tool']
		args = preprocessing_info['mark_pcr_dup'][tool]['args']
		bam_list = parallel_mark_pcr_dup(tool, args, threads, ram, bam_list, runID, workdir, log, panel_configuration, tools_configuration)
		parallel_indexBam(tool, args, threads, ram, bam_list, workdir, log, reference_fasta, panel_configuration, tools_configuration)

	if 'indel_realignment' in workflow:
		tool = preprocessing_info['indel_realignment']['tool']
		args = preprocessing_info['indel_realignment'][tool]['args']
		bam_list = parallel_indel_realignment(tool, args, threads, ram, bam_list, mills, runID, reference_fasta, workdir, log, panel_configuration, tools_configuration)
		parallel_indexBam(tool, args, threads, ram, bam_list, workdir, log, reference_fasta, panel_configuration, tools_configuration)

	if 'BQ_recalibration' in workflow:
		tool = preprocessing_info['BQ_recalibration']['tool']
		args = preprocessing_info['BQ_recalibration'][tool]['args']
		bam_list = parallel_BQ_recalibration(tool, args, mills, dbsnp, threads, ram, bam_list, runID, reference_fasta, workdir, log, panel_configuration, tools_configuration)
		parallel_indexBam(tool, args, threads, ram, bam_list, workdir, log, reference_fasta, panel_configuration, tools_configuration)

	### Manage LOG files ###
	log.close() 
	for logfile in logs_list:
		f.Move([logfile],logdir)
	#########################	

	### UPDATE SAMPLESHEET ###
	for sampleID in samples.keys():
		for sample in samples[sampleID]:
			sample_type, sample_name, bam = sample
			for sample_n, bam in bam_list:
				if sample_n == sample_name:
					samplesheet['variantcalling'][sampleID][sample_type] = {'sample_name':sample_name, 'bam':bam}

	with open(opts.samplesheet, 'w') as ss:
		json.dump(samplesheet, ss, indent=4)
	##########################

	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	#print('Sample: '+sample_name+ ' -> Done in: %d min, %d sec' % elapsed_time)
	#f.Delete([sam,bam])
	return samplesheet

def	preprocessing(samplesheet, preprocessing_info, reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID):

	preprocessing_start_time = datetime.datetime.now()
	print('\nPRE-PROCESSING:')

	f.makedirs([dirs['PREPROC_DIR']])
	workdir = dirs['PREPROC_DIR']
	logdir = dirs['LOGS_DIR'] + '/PREPROCESSING'
	f.makedirs([logdir])

	log = open(workdir + '/preprocessing.log','w+')
	samples = f.read_samplesheet(samplesheet, 'preprocessing')

	samplesheet['variantcalling'] = {}
	#workflow = alignment_pipe['workflow']

	threads = preprocessing_info['threads']
	ram = preprocessing_info['ram']
	workflow = preprocessing_info['workflow']


	#workflow = workflow[0]
	try:
		mills = tools_configuration['mills']['path']
	except:
		mills = ''
	try:
		dbsnp = tools_configuration['dbsnp']['path']
	except:
		dbsnp = ''

	preprocessing_start_time = datetime.datetime.now()
	
	f.makedirs([dirs['PREPROC_DIR']])
	workdir = dirs['PREPROC_DIR']

	#log = open(workdir + '/preprocessing.log','w+')
	samples = f.read_samplesheet(samplesheet, 'preprocessing')
	logdir = dirs['LOGS_DIR'] + '/ALIGNMENT'
	f.makedirs([logdir])

	samplesheet['variantcalling'] = {}

	start_time = datetime.datetime.now()
	for sampleID in samples.keys():
		samplesheet['variantcalling'][sampleID] = {}

		for sample in samples[sampleID]:
			sample_type, sample_name, bam = sample
			samplesheet['variantcalling'][sampleID][sample_type] = {}
			log = open(logdir + '/' + sample_name + '.log','w+')

			if bam != '':
				log = open(logdir + '/' + sample_name + '.log','w+')

				if 'add_readgroups' in workflow:
					tool = preprocessing_info['add_readgroups']['tool']
					args = preprocessing_info['add_readgroups'][tool]['args']
					bam = add_readgroups(tool, args, threads, ram, bam, sample_name, runID, workdir, log, panel_configuration, tools_configuration)
					indexBam(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_configuration, tools_configuration)

				if 'filter_bam' in workflow:
					tool = preprocessing_info['filter_bam']['tool']
					args = preprocessing_info['filter_bam'][tool]['args']
					bam = filter_bam()
					indexBam(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_configuration, tools_configuration)
				
				if 'mark_pcr_dup' in workflow:
					tool = preprocessing_info['mark_pcr_dup']['tool']
					args = preprocessing_info['mark_pcr_dup'][tool]['args']
					bam = mark_pcr_dup(tool, args, threads, ram, bam, sample_name, runID, workdir, log, panel_configuration, tools_configuration)
					indexBam(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_configuration, tools_configuration)

				if 'indel_realignment' in workflow:
					tool = preprocessing_info['indel_realignment']['tool']
					args = preprocessing_info['indel_realignment'][tool]['args']
					#bam = indel_realignment(tool, args, threads, ram, bam, sample_name, mills, runID, reference_fasta, workdir, log, panel_configuration, tools_configuration)
					#indexBam(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_configuration, tools_configuration)

				if 'BQ_recalibration' in workflow:
					tool = preprocessing_info['BQ_recalibration']['tool']
					args = preprocessing_info['BQ_recalibration'][tool]['args']
					bam = BQ_recalibration(tool, args, mills, dbsnp, threads, ram, bam, sample_name, runID, reference_fasta, workdir, log, panel_configuration, tools_configuration)
					indexBam(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_configuration, tools_configuration)

			samplesheet['variantcalling'][sampleID][sample_type] = {'sample_name':sample_name, 'bam':bam}

	with open(opts.samplesheet, 'w') as ss:
		json.dump(samplesheet, ss, indent=4)

	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	#print('Sample: '+sample_name+ ' -> Done in: %d min, %d sec' % elapsed_time)
	#f.Delete([sam,bam])
	return samplesheet

def	variantcalling(samplesheet, variantcalling_info, reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID):

	preprocessing_start_time = datetime.datetime.now()
	
	print('\nSNV & InDels CALLING:')
	preprocessing_start_time = datetime.datetime.now()
	
	f.makedirs([dirs['VCALL_DIR']])
	workdir = dirs['VCALL_DIR']

	log = open(workdir + '/variantcalling.log','w+')
	samples = f.read_samplesheet(samplesheet, 'variantcalling')
	samplesheet['postprocessing'] = {}

	#workflow = alignment_pipe['workflow']

	threads = variantcalling_info['threads']
	ram = variantcalling_info['ram']
	tools = variantcalling_info['tools']
	#print(variantcalling_info)
	filters = variantcalling_info['filters']
	
	start_time = datetime.datetime.now()

	if variantcalling_info['samples_org'] == 'single-sample':
		for sampleID in samples.keys():
			samplesheet['postprocessing'][sampleID] = {}
			for sample in samples[sampleID]:
				sample_type, sample_name, bam = sample
				samplesheet['postprocessing'][sampleID][sample_type] = {'sample_name':sample_name, 'vcf':{}, 'cnv':''}
		
		for tool in tools:
			bam_list =[]
			for sampleID in samples.keys():
				args = variantcalling_info[tool]['args']
				for sample in samples[sampleID]:
					sample_type, sample_name, bam = sample
					bam_list += [[sample_name,bam]]
					gvcf = ""
					if bam != '':
						if not opts.parallel:
							vcf = genotype_germline_single_samples(tool, args, filters, threads, ram, bam, sample_name, runID, reference_fasta, workdir, log, panel_configuration, tools_configuration)
							samplesheet['postprocessing'][sampleID][sample_type]['vcf'][tool] = vcf

			if opts.parallel:
				vcf_list = parallel_genotype_germline_single_samples(tool, args, filters, threads, ram, bam_list, runID, reference_fasta, workdir, log, panel_configuration, tools_configuration)
							
				for sampleID in samples.keys():
					for sample in samples[sampleID]:
						sample_type, sample_name, bam = sample
						for sample_n, vcf in vcf_list:
							if sample_n == sample_name:
								samplesheet['postprocessing'][sampleID][sample_type]['vcf'][tool] = vcf

	elif variantcalling_info['samples_org'] == 'cohort':


		bam_array = []
		sample_name_array = []
		samplesheet['postprocessing']['cohort-vcf-files'] = {}

		for sampleID in samples.keys():
				samplesheet['postprocessing'][sampleID] = {}
				for sample in samples[sampleID]:
					sample_type, sample_name, bam = sample
					samplesheet['postprocessing'][sampleID][sample_type] = {'sample_name':sample_name, 'vcf':{}, 'cnv':''}

		for tool in tools:	
			args = variantcalling_info[tool]['args']
			for sampleID in samples.keys():
				for sample in samples[sampleID]:
					sample_type, sample_name, bam = sample
					if bam != '' and bam not in bam_array:
						bam_array += [bam]
						sample_name_array += [sample_name]
			
			vcf, gvcf_array = genotype_germline_cohort(tool, args, filters, threads, ram, sample_name_array, bam_array, runID, reference_fasta, workdir, log, panel_configuration, tools_configuration)
			samplesheet['postprocessing']['cohort-vcf-files'][tool] = vcf

			for sampleID in samples.keys():
				for sample in samples[sampleID]:
					sample_type, sample_name, vcfs = sample
					if sample_name != '':
						
						svcf = vcf_split_by_sample(None, None, None, None, vcf, sample_name, workdir, log, panel_configuration, tools_configuration)
						#print(samplesheet['postprocessing'])
						samplesheet['postprocessing'][sampleID][sample_type]['vcf'][tool] = svcf

	elif variantcalling_info['samples_org'] == 'trio':

		#samplesheet['postprocessing']['vcf-files'] = {}

		for sampleID in samples.keys():
				samplesheet['postprocessing'][sampleID] = {'vcf-files':{}}
				for sample in samples[sampleID]:
					sample_type, sample_name, bam = sample
					samplesheet['postprocessing'][sampleID][sample_type] = {'sample_name':sample_name}

		for tool in tools:
			bam_list = []
			samplename_list = []
			args = variantcalling_info[tool]['args']
			for sampleID in samples.keys():
				trio_bam_array = []
				samplename_array = []
				for sample in samples[sampleID]:
					sample_type, sample_name, bam = sample
					if bam != '' and bam not in bam_list:
						trio_bam_array += [bam]
						samplename_array += [sample_name]
				vcf, gvcf_array = genotype_germline_trio(tool, args, filters, threads, ram, samplename_array, trio_bam_array, sampleID, reference_fasta, workdir, log, panel_configuration, tools_configuration)
				samplesheet['postprocessing'][sampleID]['vcf-files'][tool] = vcf
										
	elif variantcalling_info['samples_org'] == 'case-control':
		# not implemented yet #########################################################
		print("This version of HELPER doesn't implement germline variant calling in case-control mode")
		# bam_array = []
		# samplesheet['postprocessing']['vcf-files'] = {}

		# for sampleID in samples.keys():
		# 		samplesheet['postprocessing'][sampleID] = {}
		# 		for sample in samples[sampleID]:
		# 			sample_type, sample_name, bam = sample
		# 			samplesheet['postprocessing'][sampleID][sample_type] = {'sample_name':sample_name}

		# for tool in tools:	
		# 	args = variantcalling_info[tool]['args']
		# 	for sampleID in samples.keys():
		# 		for sample in samples[sampleID]:
		# 			sample_type, sample_name, bam = sample
		# 			if bam != '' and bam not in bam_array:
		# 				bam_array += [bam]
		# 	vcf, gvcf_array = genotype_germline_cohort(tool, args, filters, threads, ram, bam_array, runID, reference_fasta, workdir, log, panel_configuration, tools_configuration)
		# 	samplesheet['postprocessing'][sampleID]['vcf-files'][tool] = vcf
		################################################################################

	with open(opts.samplesheet, 'w') as ss:
		json.dump(samplesheet, ss, indent=4)

	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	print('SNV & InDels calling-> Done in: %d min, %d sec' % elapsed_time)
	#f.Delete([sam,bam])
	return samplesheet

def variantcalling_somatic(samplesheet, variantcalling_info, reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID):

	preprocessing_start_time = datetime.datetime.now()
	
	print('\nSNV & InDels SOMATIC CALLING:')
	preprocessing_start_time = datetime.datetime.now()
	
	f.makedirs([dirs['VCALL_DIR']])
	workdir = dirs['VCALL_DIR']

	log = open(workdir + '/variantcalling.log','w+')
	samples = f.read_samplesheet(samplesheet, 'variantcalling')
	samplesheet['postprocessing'] = {}

	#workflow = alignment_pipe['workflow']

	threads = variantcalling_info['threads']
	ram = variantcalling_info['ram']
	tools = variantcalling_info['tools']
	#print(variantcalling_info)
	filters = variantcalling_info['filters']
	
	start_time = datetime.datetime.now()
	
	if variantcalling_info['samples_org'] == 'single-sample':
		for sampleID in samples.keys():
			samplesheet['postprocessing'][sampleID] = {}
			for sample in samples[sampleID]:
				sample_type, sample_name, bam = sample
				samplesheet['postprocessing'][sampleID][sample_type] = {'sample_name':sample_name, 'vcf':{}, 'cnv':''}
		
		for tool in tools:
			bam_list =[]
			for sampleID in samples.keys():
				args = variantcalling_info[tool]['args']
				for sample in samples[sampleID]:
					sample_type, sample_name, bam = sample
					if bam != '':
						if not opts.parallel:
							vcf = genotype_somatic_single_samples(tool, args, filters, threads, ram, bam, sample_name, reference_fasta, workdir, log, panel_configuration, tools_configuration)
							samplesheet['postprocessing'][sampleID][sample_type]['vcf'][tool] = vcf

			if opts.parallel:
				vcf_list = parallel_genotype_somatic_single_samples(tool, args, filters, threads, ram, bam_list, runID, reference_fasta, workdir, log, panel_configuration, tools_configuration)
							
				for sampleID in samples.keys():
					for sample in samples[sampleID]:
						sample_type, sample_name, bam = sample
						for sample_n, vcf in vcf_list:
							if sample_n == sample_name:
								samplesheet['postprocessing'][sampleID][sample_type]['vcf'][tool] = vcf

								
	elif variantcalling_info['samples_org'] == 'case-control':
		# not implemented yet #########################################################
		print("This version of HELPER doesn't implement germline variant calling in case-control mode")

		for sampleID in samples.keys():
			samplesheet['postprocessing'][sampleID] = {}
			for sample in samples[sampleID]:
				sample_type, sample_name, bam = sample
				samplesheet['postprocessing'][sampleID][sample_type] = {'sample_name':sample_name, 'vcf':{}}

		for tool in tools:
			bam_list =[]
			for sampleID in samples.keys():
				args = variantcalling_info[tool]['args']
				case_bam = samples[sampleID]["case"]["bam"]
				case_name = samples[sampleID]["case"]["sample_name"]
				ctrl_bam = samples[sampleID]["control"]["bam"]
				ctrl_name = samples[sampleID]["control"]["sample_name"]

				if ctrl_bam != '':
					vcf = genotype_somatic_case_control(tool, args, filters, threads, ram, case_bam, case_name, ctrl_bam, ctrl_name, reference_fasta, workdir, log, panel_configuration, tools_configuration)
					samplesheet['postprocessing'][sampleID][sample_type]['vcf'][tool] = vcf

		# bam_array = []
		# samplesheet['postprocessing']['vcf-files'] = {}

		# for sampleID in samples.keys():
		# 		samplesheet['postprocessing'][sampleID] = {}
		# 		for sample in samples[sampleID]:
		# 			sample_type, sample_name, bam = sample
		# 			samplesheet['postprocessing'][sampleID][sample_type] = {'sample_name':sample_name}

		# for tool in tools:	
		# 	args = variantcalling_info[tool]['args']
		# 	for sampleID in samples.keys():
		# 		for sample in samples[sampleID]:
		# 			sample_type, sample_name, bam = sample
		# 			if bam != '' and bam not in bam_array:
		# 				bam_array += [bam]
		# 	vcf, gvcf_array = genotype_germline_cohort(tool, args, filters, threads, ram, bam_array, runID, reference_fasta, workdir, log, panel_configuration, tools_configuration)
		# 	samplesheet['postprocessing'][sampleID]['vcf-files'][tool] = vcf
		################################################################################

	with open(opts.samplesheet, 'w') as ss:
		json.dump(samplesheet, ss, indent=4)

	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	print('SNV & InDels calling-> Done in: %d min, %d sec' % elapsed_time)
	#f.Delete([sam,bam])
	return samplesheet


def	cnvcalling(samplesheet, cnvcalling_info, reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID):

		
	print('\nCNV CALLING:')
	
	f.makedirs([dirs['CNVCALL_DIR']])
	workdir = dirs['CNVCALL_DIR']

	start_time = datetime.datetime.now()
	
	
	log = open(workdir + '/cnvcalling.log','w+')
	samples = f.read_samplesheet(samplesheet, 'variantcalling')
	#samplesheet['cnvcalling'] = {}

	#workflow = alignment_pipe['workflow']
	threads = cnvcalling_info['threads']
	ram = cnvcalling_info['ram']
	workflow = cnvcalling_info['tools']
	#print(variantcalling_info)
	
	start_time = datetime.datetime.now()

	if 'postprocessing' not in samplesheet.keys():
		samplesheet['postprocessing'] = {}
	for sampleID in samples.keys():
		for sample in samples[sampleID]:
			sample_type, sample_name, bam = sample
			if sampleID in samplesheet['postprocessing'].keys():
				samplesheet['postprocessing'][sampleID][sample_type]['cnv']= ''
			else:
				samplesheet['postprocessing'][sampleID] = {}
				samplesheet['postprocessing'][sampleID][sample_type] = {'sample_name':sampleID, 'vcf':{}, 'cnv':''}

	bam_array =[]
	for tool in workflow:

		for sampleID in samples.keys():
			tool_args = cnvcalling_info[tool]
			try:
				algorithm = cnvcalling_info[tool]['algorithm']
			except:
				algorithm = ''
			for sample in samples[sampleID]:
				sample_type, sample_name, bam = sample
				if bam != '':
					bam_array += [[sample_name, bam]]
		vcf = CNV_calling(tool, tool_args, '', threads, ram, bam_array, runID, reference_fasta, workdir, log, panel_configuration, tools_configuration)
		samplesheet['postprocessing'][sampleID][sample_type]['cnv'] = vcf

				#samplesheet['postprocessing'][sampleID][sample_type][tool] = vcf
	
	#samplesheet['variantcalling'][sampleID][sample_type] = {'sample_name':sample_name, 'bam':bam}

	with open(opts.samplesheet, 'w') as ss:
		json.dump(samplesheet, ss, indent=4)

	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	#print('Sample: '+sample_name+ ' -> Done in: %d min, %d sec' % elapsed_time)
	#f.Delete([sam,bam])
	return samplesheet

def postprocessing(samplesheet, postprocessing_info, reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID):
	
	print('\nPOST-PROCESSING:')
	postprocessing_start_time = datetime.datetime.now()
	
	f.makedirs([dirs['POSTPROC_DIR']])
	workdir = dirs['POSTPROC_DIR']
	logdir = dirs['LOGS_DIR'] + '/POSTPROCESSING'
	f.makedirs([logdir])

	log = open(workdir + '/postprocessing.log','w+')
	samples = f.read_samplesheet(samplesheet, 'postprocessing')
	samplesheet['variant_annotation'] = {}

	threads = postprocessing_info['threads']
	ram = postprocessing_info['ram']
	workflow = postprocessing_info['workflow']

	if samplesheet['sample_organization'] == 'only cases':

		for sampleID in samples.keys():
			samplesheet['variant_annotation'][sampleID] = {}
			temp_vcfs={}
			cnv_list = []
			vcf = ''		
			for sample in samples[sampleID]:
				sample_type, sample_name, vcfs, cnv = sample
				log = open(logdir + '/' + sample_name + '.log','w+')
				samplesheet['variant_annotation'][sampleID][sample_type] = {'sample_name':sample_name, 'vcf':"", 'tsv':""}

				for vcaller in vcfs.keys():
					
					vcf = vcfs[vcaller]
					if 'vcf_norm' in workflow:
						tool = postprocessing_info['vcf_norm']['tool']
						args = postprocessing_info['vcf_norm'][tool]['args']
						vcf = vcf_norm(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)
						temp_vcfs[vcaller]=vcf

				if len(temp_vcfs.keys())>0:
					vcf = vcf_merge(None, None, threads, ram, sample_name, temp_vcfs, workdir, log, panel_configuration, tools_configuration)
					samplesheet['variant_annotation'][sampleID][sample_type]['vcf'] = vcf
					samplesheet['variant_annotation'][sampleID][sample_type]['cnv'] = samplesheet['postprocessing'][sampleID][sample_type]['cnv']

				if 'vcf_filter' in workflow :
					tool = postprocessing_info['vcf_filter']['tool']
					try:
						args = postprocessing_info['vcf_filter'][tool]['args']
					except:
						args = []
					if vcf != '':
						vcf = vcf_filter(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)
					samplesheet['variant_annotation'][sampleID][sample_type]['vcf'] = vcf

				if 'vcf_to_tsv' in workflow:
					tool = postprocessing_info['vcf_to_tsv']['tool']
					args = postprocessing_info['vcf_to_tsv']['args']
					tsv = ''
					if vcf != '':
						tsv = vcf_to_tsv(tool, args, threads, ram, vcf, sample_name, reference_fasta, workdir, log, panel_configuration, tools_configuration)
					cnv_list += [cnv]
					samplesheet['variant_annotation'][sampleID][sample_type]['vcf'] = vcf
					samplesheet['variant_annotation'][sampleID][sample_type]['tsv'] = tsv
		# if cnv_list != []:
		# 	cnv = report_CNV(cnv_list, workdir, log, panel_configuration, tools_configuration)

	elif samplesheet['sample_organization'] == 'case-control':

		for sampleID in samples.keys():
			samplesheet['variant_annotation'][sampleID] = {}
			temp_vcfs={}		
			for sample in samples[sampleID]:
				sample_type, sample_name, vcfs = sample
				log = open(logdir + '/' + sample_name + '.log','w+')
				samplesheet['variant_annotation'][sampleID][sample_type] = {'sample_name':sample_name, 'vcf':{}}
				for vcaller in vcfs.keys():
					vcf = vcfs[vcaller]
					if 'vcf_norm' in workflow:
						tool = postprocessing_info['vcf_norm']['tool']
						args = postprocessing_info['vcf_norm'][tool]['args']
						vcf = vcf_norm(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)
						temp_vcfs[vcaller]=vcf

				vcf = vcf_merge(None, None, threads, ram, sample_name, temp_vcfs, workdir, log, panel_configuration, tools_configuration)
				samplesheet['variant_annotation'][sampleID][sample_type]['vcf']['merged'] = vcf

				if 'vcf_filter' not in workflow:
					tool = postprocessing_info['vcf_filter']['tool']
					args = postprocessing_info['vcf_filter'][tool]['args']
					vcf = vcf_filter(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)
					samplesheet['variant_annotation'][sampleID][sample_type]['vcf']['merged'] = vcf

				if 'vcf_to_tsv' in workflow:
					tool = postprocessing_info['vcf_to_tsv']['tool']
					args = postprocessing_info['vcf_to_tsv']['args']
					tsv = vcf_to_tsv(tool, args, threads, ram, vcf, sample_name, reference_fasta, workdir, log, panel_configuration, tools_configuration)
					samplesheet['variant_annotation'][sampleID][sample_type]['vcf']['merged'] = vcf
					samplesheet['variant_annotation'][sampleID][sample_type]['tsv'] = tsv

	elif samplesheet['sample_organization'] == 'trio':
		
		for sampleID in samples.keys():
			samplesheet['variant_annotation'][sampleID] = {}
			temp_vcfs={}		
			for sample in samples[sampleID]:
				sample_type, sample_name, vcfs = sample
				log = open(logdir + '/' + sample_name + '.log','w+')
				samplesheet['variant_annotation'][sampleID][sample_type] = {'sample_name':sample_name, 'vcf':{}}
				for vcaller in vcfs.keys():
					vcf = vcfs[vcaller]
					if 'vcf_norm' in workflow:
						tool = postprocessing_info['vcf_norm']['tool']
						args = postprocessing_info['vcf_norm'][tool]['args']
						vcf = vcf_norm(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)
						temp_vcfs[vcaller]=vcf

				vcf = vcf_merge(None, None, threads, ram, sample_name, temp_vcfs, workdir, log, panel_configuration, tools_configuration)
				samplesheet['variant_annotation'][sampleID][sample_type]['vcf']['merged'] = vcf

				if 'vcf_filter' in workflow:
					tool = postprocessing_info['vcf_filter']['tool']
					args = postprocessing_info['vcf_filter'][tool]['args']
					vcf = vcf_filter(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)
					samplesheet['variant_annotation'][sampleID][sample_type]['vcf']['merged'] = vcf

				if 'vcf_to_tsv' in workflow:
					tool = postprocessing_info['vcf_to_tsv']['tool']
					args = postprocessing_info['vcf_to_tsv']['args']
					tsv = vcf_to_tsv(tool, args, threads, ram, vcf, sample_name, reference_fasta, workdir, log, panel_configuration, tools_configuration)
					samplesheet['variant_annotation'][sampleID][sample_type]['vcf']['merged'] = vcf
					samplesheet['variant_annotation'][sampleID][sample_type]['tsv'] = tsv

	with open(opts.samplesheet, 'w') as ss:
		json.dump(samplesheet, ss, indent=4)

	elapsed_time = divmod((datetime.datetime.now() - postprocessing_start_time).total_seconds(),60)
	print('Post processing-> Done in: %d min, %d sec' % elapsed_time)
	#f.Delete([sam,bam])
	return samplesheet

def p_postprocessing(samplesheet, postprocessing_info, reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID):
	
	print('Postprocessing')
	postprocessing_start_time = datetime.datetime.now()
	
	f.makedirs([dirs['POSTPROC_DIR']])
	workdir = dirs['POSTPROC_DIR']

	log = open(workdir + '/postprocessing.log','w+')
	samples = f.read_samplesheet(samplesheet, 'postprocessing')
	samplesheet['variant_annotation'] = {}

	threads = postprocessing_info['threads']
	ram = postprocessing_info['ram']
	workflow = postprocessing_info['workflow']

	if samplesheet['sample_organization'] == 'only cases':
		vcf_list = []
		for sampleID in samples.keys():
			samplesheet['variant_annotation'][sampleID] = {}
			temp_vcfs={}		
			for sample in samples[sampleID]:
				sample_type, sample_name, vcfs, cnv = sample
				samplesheet['variant_annotation'][sampleID][sample_type] = {'sample_name':sample_name, 'vcf':"", 'tsv':""}
				for vcaller in vcfs.keys():
					vcf = vcfs[vcaller]
					if 'vcf_norm' in workflow:
						tool = postprocessing_info['vcf_norm']['tool']
						args = postprocessing_info['vcf_norm'][tool]['args']
						vcf = vcf_norm(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)
						temp_vcfs[vcaller]=vcf

				vcf = vcf_merge(None, None, threads, ram, sample_name, temp_vcfs, workdir, log, panel_configuration, tools_configuration)
				samplesheet['variant_annotation'][sampleID][sample_type]['vcf'] = vcf

				if 'vcf_filter' in workflow:
					tool = postprocessing_info['vcf_filter']['tool']
					args = postprocessing_info['vcf_filter'][tool]['args']
					vcf = vcf_filter(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)
					samplesheet['variant_annotation'][sampleID][sample_type]['vcf'] = vcf

				if 'vcf_to_tsv' in workflow:
					tool = postprocessing_info['vcf_to_tsv']['tool']
					args = postprocessing_info['vcf_to_tsv']['args']
					tsv = vcf_to_tsv(tool, args, threads, ram, vcf, sample_name, reference_fasta, workdir, log, panel_configuration, tools_configuration)
					vcf_list+=[cnv]
					samplesheet['variant_annotation'][sampleID][sample_type]['vcf'] = vcf
					samplesheet['variant_annotation'][sampleID][sample_type]['tsv'] = tsv
		if vcf_list != []:
			cnv = report_CNV(vcf_list, workdir, log, panel_info, tools_info)

	elif samplesheet['sample_organization'] == 'case-control':

		for sampleID in samples.keys():
			samplesheet['variant_annotation'][sampleID] = {}
			temp_vcfs={}		
			for sample in samples[sampleID]:
				sample_type, sample_name, vcfs, cnv = sample
				samplesheet['variant_annotation'][sampleID][sample_type] = {'sample_name':sample_name, 'vcf':{}}
				for vcaller in vcfs.keys():
					vcf = vcfs[vcaller]
					if 'vcf_norm' in workflow:
						tool = postprocessing_info['vcf_norm']['tool']
						args = postprocessing_info['vcf_norm'][tool]['args']
						vcf = vcf_norm(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)
						temp_vcfs[vcaller]=vcf

				vcf = vcf_merge(None, None, threads, ram, sample_name, temp_vcfs, workdir, log, panel_configuration, tools_configuration)
				samplesheet['variant_annotation'][sampleID][sample_type]['vcf']['merged'] = vcf

				if 'vcf_filter' in workflow:
					tool = postprocessing_info['vcf_filter']['tool']
					args = postprocessing_info['vcf_filter'][tool]['args']
					vcf = vcf_filter(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)
					samplesheet['variant_annotation'][sampleID][sample_type]['vcf']['merged'] = vcf

				if 'vcf_to_tsv' in workflow:
					tool = postprocessing_info['vcf_to_tsv']['tool']
					args = postprocessing_info['vcf_to_tsv']['args']
					tsv = vcf_to_tsv(tool, args, threads, ram, vcf, sample_name, reference_fasta, workdir, log, panel_configuration, tools_configuration)
					cnv_list += [cnv]
					samplesheet['variant_annotation'][sampleID][sample_type]['vcf']['merged'] = vcf
					samplesheet['variant_annotation'][sampleID][sample_type]['tsv'] = tsv

	elif samplesheet['sample_organization'] == 'trio':
		
		for sampleID in samples.keys():
			samplesheet['variant_annotation'][sampleID] = {}
			temp_vcfs={}		
			for sample in samples[sampleID]:
				sample_type, sample_name, vcfs = sample
				samplesheet['variant_annotation'][sampleID][sample_type] = {'sample_name':sample_name, 'vcf':{}}
				for vcaller in vcfs.keys():
					vcf = vcfs[vcaller]
					if 'vcf_norm' in workflow:
						tool = postprocessing_info['vcf_norm']['tool']
						args = postprocessing_info['vcf_norm'][tool]['args']
						vcf = vcf_norm(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)
						temp_vcfs[vcaller]=vcf

				vcf = vcf_merge(None, None, threads, ram, sample_name, temp_vcfs, workdir, log, panel_configuration, tools_configuration)
				samplesheet['variant_annotation'][sampleID][sample_type]['vcf']['merged'] = vcf

				if 'vcf_filter' in workflow:
					tool = postprocessing_info['vcf_filter']['tool']
					args = postprocessing_info['vcf_filter'][tool]['args']
					vcf = vcf_filter(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)
					samplesheet['variant_annotation'][sampleID][sample_type]['vcf']['merged'] = vcf

				if 'vcf_to_tsv' in workflow:
					tool = postprocessing_info['vcf_to_tsv']['tool']
					args = postprocessing_info['vcf_to_tsv']['args']
					tsv = vcf_to_tsv(tool, args, threads, ram, vcf, sample_name, reference_fasta, workdir, log, panel_configuration, tools_configuration)
					samplesheet['variant_annotation'][sampleID][sample_type]['vcf']['merged'] = vcf
					samplesheet['variant_annotation'][sampleID][sample_type]['tsv'] = tsv

	with open(opts.samplesheet, 'w') as ss:
		json.dump(samplesheet, ss, indent=4)

	elapsed_time = divmod((datetime.datetime.now() - postprocessing_start_time).total_seconds(),60)
	print('Post processing-> Done in: %d min, %d sec' % elapsed_time)
	#f.Delete([sam,bam])
	return samplesheet

def variant_annotation(samplesheet, annotation_info, reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID):
	print('Variant annotation')
	annotation_time = datetime.datetime.now()
	
	f.makedirs([dirs['ANNOTATION_DIR']])
	workdir = dirs['ANNOTATION_DIR']
	logdir = dirs['LOGS_DIR'] + '/ANNOTATION'
	f.makedirs([logdir])

	log = open(workdir + '/variant_annotation.log','w+')
	samples = f.read_samplesheet(samplesheet, 'variant_annotation')
	samplesheet['postannotation'] = {}

	#workflow = alignment_pipe['workflow']
	threads = annotation_info['threads']
	ram = annotation_info['ram']
	tool = annotation_info['tool']

	start_time = datetime.datetime.now()

	if samplesheet['sample_organization'] == 'only cases':
		for sampleID in samples.keys():
			samplesheet['postannotation'][sampleID] = {}
			args = annotation_info[tool]['args']			
			for sample in samples[sampleID]:
				sample_type, sample_name, vcf, tsv = sample
				log = open(logdir + '/' + sample_name + '.log','w+')
				samplesheet['postannotation'][sampleID][sample_type] = {'sample_name':'', 'vcf':'', 'tsv':''}
				if vcf != '':
					vcf = vcf_annotation(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)
					samplesheet['postannotation'][sampleID][sample_type]['sample_name'] = sample_name
					samplesheet['postannotation'][sampleID][sample_type]['tsv'] = tsv
					samplesheet['postannotation'][sampleID][sample_type]['vcf'] = vcf

	elif samplesheet['sample_organization'] == 'cohort':

		vcf = samplesheet['variant_annotation']['cohort-vcf-files']
		for tool in workflow:
			
			tool_run_info = annotation_info[tool]		
			for sampleID in samples.keys():
				samplesheet['postannotation'][sampleID] = {}					
				for sample in samples[sampleID]:
					sample_type, sample_name, vcf, tsv = sample	
					log = open(logdir + '/' + sample_name + '.log','w+')				
					samplesheet['postannotation'][sampleID][sample_type] = {'sample_name':'', 'vcf':'', 'tsv':''}

					args = annotation_info[tool]['args']
					if vcf != '':
						vcf = variant_annotation(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)
						samplesheet['postannotation'][sampleID][sample_type]['sample_name'] = sample_name
						samplesheet['postannotation'][sampleID][sample_type]['tsv'] = tsv
						samplesheet['postannotation'][sampleID][sample_type]['vcf'] = vcf

	elif samplesheet['sample_organization'] == 'trio':
		pass

	elif samplesheet['sample_organization'] == 'case-control':
		pass

	with open(opts.samplesheet, 'w') as ss:
		json.dump(samplesheet, ss, indent=4)

	elapsed_time = divmod((datetime.datetime.now() - annotation_time).total_seconds(),60)
	#print('Sample: '+sample_name+ ' -> Done in: %d min, %d sec' % elapsed_time)
	#f.Delete([sam,bam])
	return samplesheet

def p_variant_annotation(samplesheet, annotation_info, reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID):
	print('Variant annotation')
	annotation_time = datetime.datetime.now()
	
	f.makedirs([dirs['ANNOTATION_DIR']])
	workdir = dirs['ANNOTATION_DIR']

	log = open(workdir + '/variant_annotation.log','w+')
	samples = f.read_samplesheet(samplesheet, 'variant_annotation')
	samplesheet['postannotation'] = {}

	#workflow = alignment_pipe['workflow']
	threads = annotation_info['threads']
	ram = annotation_info['ram']
	tool = annotation_info['tool']

	start_time = datetime.datetime.now()

	if samplesheet['sample_organization'] == 'only cases':
		for sampleID in samples.keys():
			samplesheet['postannotation'][sampleID] = {}
			args = annotation_info[tool]['args']			
			for sample in samples[sampleID]:
				sample_type, sample_name, vcf, tsv = sample
				samplesheet['postannotation'][sampleID][sample_type] = {'sample_name':'', 'vcf':'', 'tsv':''}
				if vcf != '':
					vcf = vcf_annotation(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)
					samplesheet['postannotation'][sampleID][sample_type]['sample_name'] = sample_name
					samplesheet['postannotation'][sampleID][sample_type]['tsv'] = tsv
					samplesheet['postannotation'][sampleID][sample_type]['vcf'] = vcf

	elif samplesheet['sample_organization'] == 'cohort':

		vcf = samplesheet['variant_annotation']['cohort-vcf-files']
		for tool in workflow:
			
			tool_run_info = annotation_info[tool]		
			for sampleID in samples.keys():
				samplesheet['postannotation'][sampleID] = {}					
				for sample in samples[sampleID]:
					sample_type, sample_name, vcf, tsv = sample					
					samplesheet['postannotation'][sampleID][sample_type] = {'sample_name':'', 'vcf':'', 'tsv':''}

					args = annotation_info[tool]['args']
					if vcf != '':
						vcf = variant_annotation(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)
						samplesheet['postannotation'][sampleID][sample_type]['sample_name'] = sample_name
						samplesheet['postannotation'][sampleID][sample_type]['tsv'] = tsv
						samplesheet['postannotation'][sampleID][sample_type]['vcf'] = vcf

	elif samplesheet['sample_organization'] == 'trio':
		pass

	elif samplesheet['sample_organization'] == 'case-control':
		pass

	with open(opts.samplesheet, 'w') as ss:
		json.dump(samplesheet, ss, indent=4)

	elapsed_time = divmod((datetime.datetime.now() - annotation_time).total_seconds(),60)
	#print('Sample: '+sample_name+ ' -> Done in: %d min, %d sec' % elapsed_time)
	#f.Delete([sam,bam])
	return samplesheet

def postannotation(samplesheet, postannotation_info, reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID):
	print('Post-Annotation')
	post_annotation_time = datetime.datetime.now()
	
	f.makedirs([dirs['POSTANN_DIR']])
	workdir = dirs['POSTANN_DIR']
	logdir = dirs['LOGS_DIR'] + '/POSTANNOTATION'
	f.makedirs([logdir])

	workflow = postannotation_info['workflow']
	#threads = postannotation_info['threads']
	#ram = postannotation_info['ram']

	print(workflow)
	log = open(workdir + '/postannotation.log','w+')
	samples = f.read_samplesheet(samplesheet, 'postannotation')

	if samplesheet['sample_organization'] == 'only cases':

		for step in workflow:
			for sampleID in samples.keys():
				tool = postannotation_info[step]['tool']
				args = postannotation_info[step]['args']		
				for sample in samples[sampleID]:
					sample_type, sample_name, vcf, tsv= sample
					log = open(logdir + '/' + sample_name + '.log','w+')
					if vcf != '' and tsv != '':
						if 'filter_by_trs_list' in workflow:
							args = postannotation_info['filter_by_trs_list']['args']
							vcf = filter_by_transcripts(args,vcf,workdir,log,panel_configuration, tools_configuration)
							filter = None
						else:
							filter = None
						tsv = report_annotation(tool, args, filter, vcf, tsv, sample_name, reference_fasta, workdir, log, panel_configuration, tools_configuration)


	elif samplesheet['sample_organization'] == 'case-control':
		
		for step in workflow:
			for sampleID in samples.keys():
				tool = postannotation_info[step]['tool']
				args = postannotation_info[step]['args']		
				for sample in samples[sampleID]:
					sample_type, sample_name, vcf, tsv = sample
					log = open(logdir + '/' + sample_name + '.log','w+')
					if vcf != '' and tsv != '':
						if 'filter_by_trs_list' in workflow:
							args = postannotation_info['filter_by_trs_list']['args']
							filter = 'filter'
						else:
							filter = None
						tsv = report_annotation(tool, args, filter, vcf, tsv, sample_name, reference_fasta, workdir, log, panel_configuration, tools_configuration)

	elif samplesheet['sample_organization'] == 'trio':
		
		for step in workflow:
			for sampleID in samples.keys():
				tool = postannotation_info[step]['tool']
				args = postannotation_info[step]['args']		
				for sample in samples[sampleID]:
					sample_type, sample_name, vcf, tsv = sample
					log = open(logdir + '/' + sample_name + '.log','w+')
					if vcf != '' and tsv != '':
						if 'filter_by_trs_list' in workflow:
							args = postannotation_info['filter_by_trs_list']['args']
							filter = 'filter'
						else:
							filter = None
						tsv = report_annotation(tool, args, filter, vcf, tsv, sample_name, reference_fasta, workdir, log, panel_configuration, tools_configuration)

	#with open('result.json', 'w') as ss:
	#	json.dump(samplesheet, ss, indent=4)

	elapsed_time = divmod((datetime.datetime.now() - post_annotation_time).total_seconds(),60)
	#print('Sample: '+sample_name+ ' -> Done in: %d min, %d sec' % elapsed_time)
	#f.Delete([sam,bam])
	return samplesheet

if __name__ == '__main__':

	parser = argparse.ArgumentParser()
	parser.add_argument('-v', '--version', action='version', version='Helper v.1')

	parser.add_argument('--tools_cfg', help="Tools configuration file")
	parser.add_argument('--samplesheet', help="Samplesheet that contains filepaths, samples and samples organization", required=True)
	parser.add_argument('--panel', help="The name of the used for the analysis", required=True)
	parser.add_argument('--pipeline', help="Pipeline configuration file", required=True)
	parser.add_argument('--run_id', help="Run id}", required=True)
	parser.add_argument('--workdir', help="Working Directory. A new folder will be created and named with the run_id", required=True)
	parser.add_argument('--workflow', help="pipeline steps confirmed")
	parser.add_argument('--parallel', help="Enable parallel analysis", action='store_true')
	parser.add_argument('--del_temp', help="Delete temp files", action='store_true')

	start_time = datetime.datetime.now()
	#success = subprocess.call('clear')
	
	global opts
	global MAINDIR
	global SCRIPTS_DIR
	global CFG_DIR
	global dirs
	global SAMPLESHEET
	opts = parser.parse_args()

	print('\n\n')

	print('Analysis Id: ' + opts.run_id )
	print('Experiment: ' + opts.panel )
	print('Pipeline: ' + opts.pipeline )
	print('Sample sheet: ' + opts.samplesheet)
	print('Working Directory: ' + opts.workdir)
	print('Parallel analysis: ' + str(opts.parallel))
	print('Delete temp files: ' + str(opts.del_temp))


	MAINDIR = os.path.dirname(os.path.realpath(__file__))
	SCRIPTS_DIR = '/'.join(MAINDIR.split('/')[:-1]+['/scripts/'])
	CFG_DIR = '/'.join(MAINDIR.split('/')[:-1]+['/configs/'])
	FILES_DIR = '/'.join(MAINDIR.split('/')[:-1]+['/files/'])

	runID = opts.run_id
	if opts.tools_cfg:
		confirmed_workflow = opts.workflow.split(',')
	else:
		confirmed_workflow = ['prealignment','alignment','preprocessing','variantcalling','cnvcalling','postprocessing','variant_annotation','postannotation']
	pipeline_configuration = json.loads((open(opts.pipeline).read()).encode('utf8'))
	panel_configuration = json.loads((open(CFG_DIR + 'experiment_list.cfg').read()).encode('utf8'))[opts.panel]
	if not opts.tools_cfg:
		tools_configuration = json.loads((open(CFG_DIR + 'tools_cfg/tools.cfg').read()).encode('utf8'))
	else:
		tools_configuration = json.loads((open(opts.tools_cfg).read()).encode('utf8'))
	samplesheet = json.loads((open(opts.samplesheet).read()).encode('utf8'))

	dirs = dict()

	WORKDIR = opts.workdir
	dirs['PREALIGN_DIR'] = '/'.join([WORKDIR, 'PREALIGNMENT'])
	dirs['ALIGN_DIR'] = '/'.join([WORKDIR, 'ALIGNMENT'])
	dirs['PREPROC_DIR'] = '/'.join([WORKDIR, 'PREPROCESSING'])
	dirs['VCALL_DIR'] = '/'.join([WORKDIR, 'VARIANTCALLING'])
	dirs['CNVCALL_DIR'] = '/'.join([WORKDIR, 'CNVCALLING'])
	dirs['POSTPROC_DIR'] = '/'.join([WORKDIR, 'POSTPROCESSING'])
	dirs['ANNOTATION_DIR'] = '/'.join([WORKDIR, 'ANNOTATION'])
	dirs['POSTANN_DIR'] = '/'.join([WORKDIR, 'POSTANNOTATION'])
	dirs['TMP_DIR'] = '/'.join([WORKDIR, 'TEMP'])
	dirs['LOGS_DIR'] = '/'.join([WORKDIR, 'LOGS'])
	dirs['OUT_DIR'] = '/'.join([WORKDIR, 'OUTPUT'])
	dirs['STORAGE_DIR'] = '/'.join([WORKDIR, 'STORAGE'])

	#print( WORKDIR)

	f.makedirs([dirs['LOGS_DIR'],dirs['OUT_DIR'],dirs['OUT_DIR']+"/"+runID,dirs['STORAGE_DIR'],dirs['STORAGE_DIR']+"/"+runID])

	design = samplesheet['sample_organization']
	analysis = pipeline_configuration['analysis']
	workflow_pipeline = pipeline_configuration['workflow']
	reference_version = pipeline_configuration['reference_version']
	reference_fasta = tools_configuration[reference_version]['fasta']

	workflow = [step for step in workflow_pipeline if step in confirmed_workflow]
	#print(workflow)

	if 'prealignment' in workflow:
		if opts.parallel:
			samplesheet = p_pre_alignment(samplesheet,
				pipeline_configuration['prealignment'],
				reference_fasta,
				panel_configuration,
				tools_configuration,
				runID)
		else:
			samplesheet = pre_alignment(samplesheet,
				pipeline_configuration['prealignment'],
				reference_fasta,
				panel_configuration,
				tools_configuration,
				runID)

	if 'alignment' in workflow:
		if opts.parallel:
			samplesheet = p_alignment(samplesheet,
				pipeline_configuration['alignment'],
				reference_fasta,
				pipeline_configuration,
				panel_configuration,
				tools_configuration,
				runID)
		else:
			samplesheet = alignment(samplesheet,
				pipeline_configuration['alignment'],
				reference_fasta,
				pipeline_configuration,
				panel_configuration,
				tools_configuration,
				runID)

	if 'preprocessing' in workflow:
		if opts.parallel:
			samplesheet = p_preprocessing(samplesheet, 
				pipeline_configuration['preprocessing'], 
				reference_fasta, 
				pipeline_configuration, 
				panel_configuration, 
				tools_configuration, 
				runID)
		else:
			samplesheet = preprocessing(samplesheet, 
				pipeline_configuration['preprocessing'], 
				reference_fasta, 
				pipeline_configuration, 
				panel_configuration, 
				tools_configuration, 
				runID)

	if 'variantcalling' in workflow:
		if pipeline_configuration['analysis'].upper() == 'GERMLINE':
			samplesheet = variantcalling(samplesheet, pipeline_configuration['variantcalling'], reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID)
		elif pipeline_configuration['analysis'].upper() == 'SOMATIC':
			samplesheet = variantcalling_somatic(samplesheet, pipeline_configuration['variantcalling'], reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID)

	if 'cnvcalling' in workflow:
		samplesheet = cnvcalling(samplesheet, pipeline_configuration['cnvcalling'], reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID)

	if 'postprocessing' in workflow:
		samplesheet = postprocessing(samplesheet, pipeline_configuration['postprocessing'], reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID)
	
	if 'variant_annotation' in workflow:
		samplesheet = variant_annotation(samplesheet, pipeline_configuration['variant_annotation'], reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID)
	
	if 'cnv_annotation' in workflow:
		samplesheet = cnv_annotation(samplesheet, pipeline_configuration['cnv_annotation'], reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID)

	if 'postannotation' in workflow:
		samplesheet = postannotation(samplesheet, pipeline_configuration['postannotation'], reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID)

	print('\nAnalysis: ' + runID + ' --> Complete!')


