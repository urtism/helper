import subprocess
import os
import tools2 as t
import scripts
import datetime
import functions2 as f
import json


############ PRE-ALIGNMENT AND FASTQ PROCESSING ############

def trim_adapters():
	path = tools_info[tool]['path']
	path = tools_info[tool]['path']
	if tool.upper().startswith('AGENT'):
		tag = ''
		agent = t.AGeNT()
		agent.init_tool(path, threads, ram, args)
		return agent.Trimmer(fq1, fq2, tag, log, workdir)

	if tool.upper().startswith('CUTADAPT'):
		pass
	if tool.upper().startswith('TRIMMOMATIC'):
		pass
	if tool.upper().startswith('FASTP'):
		pass

def filter_fastq_by_qual():
	path = tools_info[tool]['path']
	path = tools_info[tool]['path']
	if tool.upper().startswith('CUTADAPT'):
		pass
	if tool.upper().startswith('TRIMMOMATIC'):
		pass
	if tool.upper().startswith('FASTP'):
		pass

def filter_fastq_by_reads_len():
	path = tools_info[tool]['path']
	if tool.upper().startswith('CUTADAPT'):
		pass
	if tool.upper().startswith('TRIMMOMATIC'):
		pass
	if tool.upper().startswith('FASTP'):
		pass

def fastq_QC(tool, args, threads, ram, sample_name, fastq1, fastq2, workdir, log, reference_fasta, panel_info, tools_info):
	path = tools_info[tool]['path']
	if tool.upper().startswith('FASTQC'):
		fastqc = t.Fastqc()
		fastqc.init_tool(path, threads, ram, args)
		return fastqc.fastqc_diagnosis(sample_name, fastq1, fastq2, log, workdir)

############ ALIGNMENT AND SAM PROCESSING ############

def fastq_alignment(tool, algorithm, args, threads, ram, sample_name, fastq1, fastq2, workdir, log, reference_fasta, panel_info, tools_info):	
	path = tools_info[tool]['path']
	version = tools_info[tool]['version']

	if tool.upper().startswith('BWA'):
		bwa = t.Bwa()
		bwa.init_tool(path, threads, ram, args)
		return bwa.align_fastq(algorithm, sample_name, fastq1, fastq2, reference_fasta, log, workdir)

	elif tool.upper() == 'BOWTIE2':
		print('bowtie2')

	elif tool.upper() == 'NOVOALIGN':
		print('Novoalign')

def parallel_fastq_alignment(tool, algorithm, args, threads, ram, fastq_list, workdir, log, reference_fasta, panel_info, tools_info):	
	path = tools_info[tool]['path']
	version = tools_info[tool]['version']
	print(fastq_list)

	if tool.upper().startswith('BWA'):
		bwa = t.Bwa()
		bwa.init_tool(path, threads, ram, args)
		#return bwa.align_fastq(algorithm, sample_name, fastq1, fastq2, reference_fasta, log, workdir)
		return bwa.parallel_align_fastq(algorithm, fastq_list, reference_fasta, log, workdir)

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

def indexBam(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_info, tools_info):
	path = tools_info[tool]['path']
	if tool.upper().startswith('PICARD'):
		picard = t.Picard()
		picard.init_tool(path, threads, ram, args)
		picard.BuildBamIndex(bam, log, workdir)

def bam_QC(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_info, tools_info):
	path = tools_info[tool]['path']
	if tool.upper().startswith('FASTQC'):
		fastqc = t.Fastqc()
		fastqc.init_tool(path, threads, ram, args)
		return fastqc.bam_diagnosis(sample_name, bam, log, workdir)

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

def mark_pcr_dup(tool, args, threads, ram, bam, sample_name, runID, workdir, log, panel_info, tools_info):
	path = tools_info[tool]['path']
	panel = panel_info['panel_name']
	if tool.upper().startswith('PICARD'):
		picard = t.Picard()
		picard.init_tool(path, threads, ram, args)
		return picard.MarkDuplicates(sample_name, bam, log, workdir)

def indel_realignment(tool, args, threads, ram, bam, sample_name, mills, runID, reference_fasta, workdir, log, panel_info, tools_info):
	path = tools_info[tool]['path']
	panel = panel_info['panel_name']
	target_list = panel_info['target_list']
	if tool.upper().startswith('GATK'):
		if tools_info[tool]['version'].startswith('3'):
			gatk = t.GATKv3()
			gatk.init_tool(path, threads, ram, args)
			return gatk.IndelRealigner(bam, mills, target_list, reference_fasta, log, workdir)

def BQ_recalibration(tool, args, mills, dbsnp, threads, ram, bam, sample_name, runID, reference_fasta, workdir, log, panel_info, tools_info):
	path = tools_info[tool]['path']
	panel = panel_info['panel_name']
	target_list = panel_info['target_list']
	if tool.upper().startswith('GATK'):
		if tools_info[tool]['version'].startswith('3'):
			gatk = t.GATKv3()
			gatk.init_tool(path, threads, ram, args)
			return gatk.BaseRecalibrator(bam, dbsnp, mills, target_list, reference_fasta, log, workdir)

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

	if tool.upper().startswith('GATK'):
		if version.startswith('3'):
			gatk = t.GATKv3()
		if version.startswith('4'):
			gatk = t.GATKv4()
		gatk.init_tool(path, threads, ram, args)
		return gatk.HaplotypeCaller(bam, sample_name, filters, target_list, reference_fasta, log, workdir)

	if tool.upper().startswith('FREEBAYES'):
		freebayes = t.Freebayes()
		freebayes.init_tool(path, threads, ram, args)
		return freebayes.variant_calling(bam, sample_name, filters, reference_fasta, workdir, log, panel_configuration, tools_configuration)

	if tool.upper().startswith('VARSCAN'):
		varscan = t.Varscan()
		varscan.init_tool(path, threads, ram, args)
		return varscan.variant_calling(bam, sample_name, filters, reference_fasta, workdir, log, panel_configuration, tools_configuration)

def genotype_germline_cohort(tool, args, filters, threads, ram, bam_array, runID, reference_fasta, workdir, log, panel_info, tools_info):

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

		new_args = args + ['-ERC','GVCF']
		gatk.init_tool(path, threads, ram, new_args)
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
		varscan.init_tool(path, threads, ram, args)
		return varscan.variant_calling(bam_array, runID, filters, target_bed, reference_fasta, log, workdir), []


def vcf_QC():
	pass


############ CNV-CALLING #############
def CNV_calling(tool, tool_args, filters, threads, ram, bam_array, runID, reference_fasta, workdir, log, panel_info, tools_info):
	
	path = tools_info[tool]['path']
	version = tools_info[tool]['version']
	panel = panel_info['panel_name']
	args = tool_args['args']

	cnv_target_list = panel_info['cnv_target_list']
	cnv_target_bed = panel_info['cnv_target_bed']
	cnv_GATK_ploidy_model = panel_info['cnv_GATK_ploidy_model']
	cnv_GATK_calls_model = panel_info['cnv_GATK_calls_model']
	CONVADING_controls_dir = panel_info['CoNVaDING_controls_dir']
	CNVkit_reference = panel_info['CNVkit_reference']
	samples_dict = {}
	
	if cnv_GATK_ploidy_model == "":
		cnv_GATK_ploidy_model = '/home/jarvis/git/Powercall2/files/Prior.ploidy'

	if tool.upper().startswith('GATK'):

		if version.startswith('4'):
			gatk = t.GATKv4()
			gatk.init_tool(path, threads, ram, args)
			#dir_cnv = workdir +'/CNV_HDF5'
			print(bam_array)
			new_args = args + ['-ERC','GVCF']
			sample_index = 0
			hdf5_array = []
			for sample_name, bam in bam_array:

				if bam != '':
					hdf5 = gatk.CollectReadCounts(bam, sample_name, cnv_target_list, log, workdir)
					hdf5_array += [[hdf5, sample_name, sample_index]]
					sample_index += 1

		sample_ploidy = gatk.DetermineGermlineContigPloidy(hdf5_array, runID, cnv_GATK_ploidy_model, log, workdir)
		sample_calls, sample_model = gatk.GermlineCNVCaller(hdf5_array, runID, sample_ploidy, cnv_calls_model, log, workdir)

		if cnv_GATK_calls_model == "":
			cnv_GATK_calls_model = sample_model

		for hdf5, sample_name, sample_index in hdf5_array:
			cnv_vcf, segments_vcf = gatk.PostprocessGermlineCNVCalls(sample_name, sample_index, sample_calls, sample_ploidy, cnv_GATK_calls_model, log, workdir)
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
			print(bam)
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
	path = tools_info[tool]['path']
	version = tools_info[tool]['version']
	
	if tool.upper().startswith('GATK'):
		if version.startswith('3'):
			gatk = t.GATKv3()
		if version.startswith('4'):
			gatk = t.GATKv4()
		gatk.init_tool(path, threads, ram, args)
		return gatk.VariantFiltration(vcf, reference_fasta, log, workdir)

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
	path = scripts_path

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
	path = scripts_path
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

def variant_annotation(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_info, tools_info):

	path = tools_info[tool]['path']
	version = tools_info[tool]['version']
	#plugins = tools_info[tool]['plugins']
	panel = panel_info['panel_name']
	target_list = panel_info['target_list']
	target_bed = panel_info['target_bed']
	#print(vcf, args)

	if tool.upper().startswith('VEP'):
		vep = t.VEP()
		vep.init_tool(path, threads, ram, args['args'])
		plugins = args['plugins']
		identifiers = args['features']
		assembly = args['assembly']
		species = args['species']
		af = args['af']
		
		vcf = vep.vcf_annotation(vcf, reference_fasta, assembly, species, identifiers, af, plugins, tools_info, log, workdir)	
	return vcf

def filter_by_transcripts(tool, args, threads, ram, gatk_vcf, freeb_vcf, varscan_vcf, workdir, log, panel_info, tools_info):
	path = scripts_path
	return scripts.merge_vcfs(path,sample_name,gatk_vcf,freeb_vcf,varscan_vcf,log,workdir)

############ VCF TO TSV ############

def vcf_to_tsv(tool, args, threads, ram, vcf, sample_name, reference_fasta, workdir, log, panel_info, tools_info):
	path = scripts_path
	tags_file = args['tags_file']
	format = args['format_tags']
	info = args['info_tags']

	return scripts.Vcf_to_tsv(path,vcf,tags_file,format,info,sample_name,log,workdir)

def report_annotation(tool, args, filter, vcf, tsv, sample_name, reference_fasta, workdir, log, panel_info, tools_info):
	path = scripts_path
	tag_list = args['tags_file']
	if filter:
		transcript_list = panel_info['transcripts_list']
	else:
		transcript_list = None
	return scripts.add_Annotation(path,sample_name,vcf,tsv,tag_list,transcript_list,log,workdir)

#########################################################################################################################
def read_pipeline_configuration():
	pass
	#return reference, workflow, alignment, preprocessing

def read_panel_configuration():
	pass
	#return reference, workflow, alignment, preprocessing

def read_tools_configuration():
	pass
	#return reference, workflow, alignment, preprocessing

def pipeline_builder(samplesheet, confirmed_workflow, pipeline_configuration, panel_configuration, tools_configuration, runID):

	reference_version = pipeline_configuration['reference_version']
	reference_fasta = tools_configuration[reference_version]['fasta']
	workflow_pipe = pipeline_configuration['workflow']

	workflow = [value for value in workflow_pipe if value in confirmed_workflow]

	print(workflow)
	if 'pre-alignment' in workflow_pipe and 'pre-alignment' in confirmed_workflow:
		samplesheet = pre_alignment(samplesheet, pipeline_configuration['prealignment'], reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID)

	if 'alignment' in workflow_pipe and 'alignment' in confirmed_workflow:
		samplesheet = alignment(samplesheet, pipeline_configuration['alignment'], reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID)

	if 'preprocessing' in workflow_pipe and 'preprocessing' in confirmed_workflow:
		samplesheet = preprocessing(samplesheet, pipeline_configuration['preprocessing'], reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID)

	if 'variantcalling' in workflow_pipe and 'variantcalling' in confirmed_workflow:
		if pipeline_configuration['analysis'] == 'germline':
			samplesheet = variantcalling_germline(samplesheet, pipeline_configuration['variantcalling'], reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID)
		elif pipeline_configuration['analysis'] == 'somatic':
			samplesheet = variantcalling_somatic(samplesheet, pipeline_configuration['variantcalling'], reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID)

	if 'postprocessing' in workflow_pipe and 'postprocessing' in confirmed_workflow:
		samplesheet = postprocessing(samplesheet, pipeline_configuration['postprocessing'], reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID)

	if 'cnvcalling' in workflow_pipe and 'cnvcalling' in confirmed_workflow:
		samplesheet = cnvcalling(samplesheet, pipeline_configuration['cnvcalling'], reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID)

	if 'annotation' in workflow_pipe and 'annotation' in confirmed_workflow:
		samplesheet = annotation(samplesheet, pipeline_configuration['annotation'], reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID)

	if 'postannotation' in workflow_pipe and 'postannotation' in confirmed_workflow:
		samplesheet = postannotation(samplesheet, pipeline_configuration['postannotation'], reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID)

def pre_alignment(samplesheet, prealignment_info, reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID):
	
	alignment_start_time = datetime.datetime.now()
	
	#f.makedirs([dirs['alignment']])
	#log = open(dirs['log'] + '/Alignment.log','w+')
	workdir = '/home/jarvis/PROVA'

	log = open(workdir + '/pre-alignment.log','w+')
	samples = f.read_samplesheet(samplesheet, 'pre-alignment')

	#workflow = alignment_pipe['workflow']
	samplesheet['alignment'] = {}

	threads = prealignment_info['threads']
	ram = prealignment_info['ram']
	workflow = prealignment_info['workflow']

	for sampleID in samples.keys():
		case, control, parent1, parent2 = samples[sampleID]
		samplesheet['alignment'][sampleID] = {}

		for sample in samples[sampleID]:
			sample_type, sample_name, fastqR1, fastqR2 , fastqI1, fastqI2 = sample
			samplesheet['alignment'][sampleID][sample_type] = {}
			
			if 'fastq_QC' in workflow:
				tool = alignment_info['fastq_QC']['tool']
				args = alignment_info['fastq_QC']['args']
				fastq_QC(tool, args, threads, ram, sample_name, fastqR1, fastqR2, workdir, log, reference_fasta, panel_configuration, tools_configuration)


			samplesheet['preprocessing'][sampleID][sample_type] = {'sample_name':sample_name, 'fastqR1':fastqR1, 'fastqR2':fastqR2, 'fastqI1':fastqI1, 'fastqI2':fastqI2}



def alignment(samplesheet, alignment_info, reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID):
	alignment_start_time = datetime.datetime.now()
	print(alignment_start_time)
	
	#f.makedirs([dirs['alignment']])
	#log = open(dirs['log'] + '/Alignment.log','w+')
	workdir = '/home/jarvis/'+runID
	f.makedirs([workdir])

	log = open(workdir + '/alignment.log','w+')
	samples = f.read_samplesheet(samplesheet, 'alignment')

	#workflow = alignment_pipe['workflow']
	samplesheet['preprocessing'] = {}

	threads = alignment_info['threads']
	ram = alignment_info['ram']
	workflow = alignment_info['workflow']

	start_time = datetime.datetime.now()
	sam = []
	for sampleID in samples.keys():
		case, control, parent1, parent2 = samples[sampleID]
		samplesheet['preprocessing'][sampleID] = {}

		for sample in samples[sampleID]:

			sample_type, sample_name, fastqR1, fastqR2, fastqI1, fastqI2 = sample
			bam = ''
			samplesheet['preprocessing'][sampleID][sample_type] = {} 

			if fastqR1 != '' and fastqR2 != '':

				tool = alignment_info['fastq_alignment']['tool']
				algorithm = alignment_info['fastq_alignment']['algorithm']
				args = alignment_info['fastq_alignment']['args']
				sam += [fastq_alignment(tool, algorithm, args, threads, ram, sample_name, fastqR1, fastqR2, workdir, log, reference_fasta, panel_configuration, tools_configuration)]
	
	for s in sam:
		s.wait()
	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	print("-align_fastq: %d min, %d sec" % elapsed_time)
				
	# 			tool = alignment_info['sam_to_bam']['tool']
	# 			args = alignment_info['sam_to_bam']['args']
	# 			bam = sam_to_bam(tool, args, threads, ram, sample_name, sam, workdir, log, reference_fasta, panel_configuration, tools_configuration)
				
	# 			tool = alignment_info['sortSam']['tool']
	# 			args = alignment_info['sortSam']['args']
	# 			bam = sortSam(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_configuration, tools_configuration)

	# 			tool = alignment_info['sortSam']['tool']
	# 			args = alignment_info['sortSam']['args']
	# 			indexBam(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_configuration, tools_configuration)

	# 			if 'merge_UMI' in workflow:
	# 				pass

	# 			if 'bam_QC' in workflow:
	# 				tool = alignment_info['bam_QC']['tool']
	# 				args = alignment_info['bam_QC']['args']
	# 				bam_QC(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_configuration, tools_configuration)

	# 		samplesheet['preprocessing'][sampleID][sample_type] = {'sample_name':sample_name, 'bam':bam}

	# with open('result.json', 'w') as ss:
	# 	json.dump(samplesheet, ss, indent=4)

	# log.close()

	# fastq_list = []
	# start_time = datetime.datetime.now()

	for sampleID in samples.keys():
		case, control, parent1, parent2 = samples[sampleID]
		samplesheet['preprocessing'][sampleID] = {}

		for sample in samples[sampleID]:

			sample_type, sample_name, fastqR1, fastqR2, fastqI1, fastqI2 = sample
			bam = ''
			if fastqR1 != '' and fastqR2 != '':
				fastq_list += [[sample_name, fastqR1, fastqR2]]
				samplesheet['preprocessing'][sampleID][sample_type] = {} 


	tool = alignment_info['fastq_alignment']['tool']
	algorithm = alignment_info['fastq_alignment']['algorithm']
	args = alignment_info['fastq_alignment']['args']
	sam = parallel_fastq_alignment(tool, algorithm, args, threads, ram, fastq_list, workdir, log, reference_fasta, panel_configuration, tools_configuration)
				
	# elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	# print("-parallel_align_fastq: %d min, %d sec" % elapsed_time)

	# with open('result.json', 'w') as ss:
	# 	json.dump(samplesheet, ss, indent=4)

	# log.close()
	# return samplesheet



#def preprocessing(panel, workflow, target_list, sample_name, bam, dirs, cfg, opts, log, workdir, runID):
def	preprocessing(samplesheet, preprocessing_info, reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID):

	preprocessing_start_time = datetime.datetime.now()
	
	#f.makedirs([dirs['preprocessing']])
	#log = open(dirs['log'] + '/preprocessing.log','w+')
	workdir = '/home/jarvis/PROVA'

	log = open(workdir + '/preprocessing.log','w+')
	samples = f.read_samplesheet(samplesheet, 'preprocessing')

	samplesheet['variantcalling'] = {}

	#workflow = alignment_pipe['workflow']

	threads = preprocessing_info['threads']
	ram = preprocessing_info['ram']
	workflow = preprocessing_info['workflow']
	try:
		mills = tools_configuration[preprocessing_info['BQ_recalibration']['mills']]['path']
	except:
		mills = ''
	try:
		dbsnp = tools_configuration[preprocessing_info['BQ_recalibration']['dbsnp']]['path']
	except:
		dbsnp = ''

#	#print('Sample: ' + sample_name)
	start_time = datetime.datetime.now()
	for sampleID in samples.keys():
		case, control, parent1, parent2 = samples[sampleID]
		samplesheet['variantcalling'][sampleID] = {}

		for sample in samples[sampleID]:

			sample_type, sample_name, bam = sample
			samplesheet['variantcalling'][sampleID][sample_type] = {}

			if bam != '':

				if 'add_readgroups' in workflow:
					tool = preprocessing_info['add_readgroups']['tool']
					args = preprocessing_info['add_readgroups']['args']
					bam = add_readgroups(tool, args, threads, ram, bam, sample_name, runID, workdir, log, panel_configuration, tools_configuration)
					indexBam(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_configuration, tools_configuration)
		#			f.Move([bam,bam+'.bai'],dirs['delete'])

				if 'filter_bam' in workflow:
					tool = preprocessing_info['filter_bam']['tool']
					args = preprocessing_info['filter_bam']['args']
					bam = filter_bam()
					indexBam(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_configuration, tools_configuration)
				
				if 'mark_pcr_dup' in workflow:
					tool = preprocessing_info['mark_pcr_dup']['tool']
					args = preprocessing_info['mark_pcr_dup']['args']
					bam = mark_pcr_dup(tool, args, threads, ram, bam, sample_name, runID, workdir, log, panel_configuration, tools_configuration)
					indexBam(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_configuration, tools_configuration)

				if 'indel_realignment' in workflow:
					tool = preprocessing_info['indel_realignment']['tool']
					args = preprocessing_info['indel_realignment']['args']
					bam = indel_realignment(tool, args, threads, ram, bam, sample_name, mills, runID, reference_fasta, workdir, log, panel_configuration, tools_configuration)
					indexBam(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_configuration, tools_configuration)

				if 'BQ_recalibration' in workflow:
					tool = preprocessing_info['BQ_recalibration']['tool']
					args = preprocessing_info['BQ_recalibration']['args']
					bam = BQ_recalibration(tool, args, mills, dbsnp, threads, ram, bam, sample_name, runID, reference_fasta, workdir, log, panel_configuration, tools_configuration)
					indexBam(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_configuration, tools_configuration)

			samplesheet['variantcalling'][sampleID][sample_type] = {'sample_name':sample_name, 'bam':bam}

	with open('result.json', 'w') as ss:
		json.dump(samplesheet, ss, indent=4)

	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	#print('Sample: '+sample_name+ ' -> Done in: %d min, %d sec' % elapsed_time)
	#f.Delete([sam,bam])
	return samplesheet

#def preprocessing(panel, workflow, target_list, sample_name, bam, dirs, cfg, opts, log, workdir, runID):
# def	preprocessing(samplesheet, preprocessing_info, reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID):

#	preprocessing_start_time = datetime.datetime.now()
	
#	#f.makedirs([dirs['preprocessing']])
#	#log = open(dirs['log'] + '/preprocessing.log','w+')
#	workdir = '/home/jarvis/PROVA'

#	log = open(workdir + '/preprocessing.log','w+')
#	samples = f.read_samplesheet(samplesheet, 'preprocessing')

#	samplesheet['variantcalling'] = {}

#	#workflow = alignment_pipe['workflow']

#	threads = preprocessing_info['threads']
#	ram = preprocessing_info['ram']
#	workflow = preprocessing_info['workflow']
#	try:
#		mills = tools_configuration[preprocessing_info['BQ_recalibration']['mills']]['path']
#	except:
#		mills = ''
#	try:
#		dbsnp = tools_configuration[preprocessing_info['BQ_recalibration']['dbsnp']]['path']
#	except:
#		dbsnp = ''

# #	#print('Sample: ' + sample_name)
# 	start_time = datetime.datetime.now()
#	for sampleID in samples.keys():
#		case, control, parent1, parent2 = samples[sampleID]
#		samplesheet['variantcalling'][sampleID] = {}

#		for sample in samples[sampleID]:

#			sample_type, sample_name, bam = sample
#			samplesheet['variantcalling'][sampleID][sample_type] = {}

#			if bam != '':

#				if 'add_readgroups' in workflow:
#					tool = preprocessing_info['add_readgroups']['tool']
#					args = preprocessing_info['add_readgroups']['args']
#					bam = add_readgroups(tool, args, threads, ram, bam, sample_name, runID, workdir, log, panel_configuration, tools_configuration)
#					indexBam(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_configuration, tools_configuration)
#		#			f.Move([bam,bam+'.bai'],dirs['delete'])

#				if 'filter_bam' in workflow:
#					tool = preprocessing_info['filter_bam']['tool']
#					args = preprocessing_info['filter_bam']['args']
#					bam = filter_bam()
#					indexBam(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_configuration, tools_configuration)
				
#				if 'mark_pcr_dup' in workflow:
#					tool = preprocessing_info['mark_pcr_dup']['tool']
#					args = preprocessing_info['mark_pcr_dup']['args']
#					bam = mark_pcr_dup(tool, args, threads, ram, bam, sample_name, runID, workdir, log, panel_configuration, tools_configuration)
#					indexBam(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_configuration, tools_configuration)

#				if 'indel_realignment' in workflow:
#					tool = preprocessing_info['indel_realignment']['tool']
#					args = preprocessing_info['indel_realignment']['args']
#					bam = indel_realignment(tool, args, threads, ram, bam, sample_name, mills, runID, reference_fasta, workdir, log, panel_configuration, tools_configuration)
#					indexBam(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_configuration, tools_configuration)

#				if 'BQ_recalibration' in workflow:
#					tool = preprocessing_info['BQ_recalibration']['tool']
#					args = preprocessing_info['BQ_recalibration']['args']
#					bam = BQ_recalibration(tool, args, mills, dbsnp, threads, ram, bam, sample_name, runID, reference_fasta, workdir, log, panel_configuration, tools_configuration)
#					indexBam(tool, args, threads, ram, sample_name, bam, workdir, log, reference_fasta, panel_configuration, tools_configuration)

#			samplesheet['variantcalling'][sampleID][sample_type] = {'sample_name':sample_name, 'bam':bam}

#	with open('result.json', 'w') as ss:
#		json.dump(samplesheet, ss, indent=4)

#	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
# 	#print('Sample: '+sample_name+ ' -> Done in: %d min, %d sec' % elapsed_time)
# 	#f.Delete([sam,bam])
#	return samplesheet

def	variantcalling_germline(samplesheet, variantcalling_info, reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID):

	preprocessing_start_time = datetime.datetime.now()
	
	#f.makedirs([dirs['preprocessing']])
	#log = open(dirs['log'] + '/preprocessing.log','w+')
	workdir = '/home/jarvis/PROVA'

	log = open(workdir + '/variantcalling.log','w+')
	samples = f.read_samplesheet(samplesheet, 'variantcalling')
	samplesheet['postprocessing'] = {}

	#workflow = alignment_pipe['workflow']

	threads = variantcalling_info['threads']
	ram = variantcalling_info['ram']
	workflow = variantcalling_info['workflow']
	#print(variantcalling_info)
	filters = variantcalling_info['filters']
	
	start_time = datetime.datetime.now()

	if pipeline_configuration['design'] == 'single-sample':

		for tool in workflow:
			for sampleID in samples.keys():
				samplesheet['postprocessing'][sampleID] = {}
				args = variantcalling_info[tool]['args']
				
				for sample in samples[sampleID]:
					sample_type, sample_name, bam = sample
					samplesheet['postprocessing'][sampleID][sample_type] = {'sample_name':sample_name, 'vcfs':{}}
					gvcf = ""
					if bam != '':
						vcf = genotype_germline_single_samples(tool, args, filters, threads, ram, bam, sample_name, runID, reference_fasta, workdir, log, panel_configuration, tools_configuration)

					samplesheet['postprocessing'][sampleID][sample_type][tool] = vcf


	elif pipeline_configuration['design'] == 'cohort':

		bam_array = []
		samplesheet['postprocessing']['cohort-vcf-files'] = {}

		for sampleID in samples.keys():
				samplesheet['postprocessing'][sampleID] = {}
				for sample in samples[sampleID]:
					sample_type, sample_name, bam = sample
					samplesheet['postprocessing'][sampleID][sample_type] = {'sample_name':sample_name, 'vcfs':{}}

					for tool in workflow:	
						args = variantcalling_info[tool]['args']
						for sampleID in samples.keys():
							for sample in samples[sampleID]:
								sample_type, sample_name, bam = sample
								if bam != '' and bam not in bam_array:
									bam_array += [bam]
						vcf, gvcf_array = genotype_germline_cohort(tool, args, filters, threads, ram, bam_array, runID, reference_fasta, workdir, log, panel_configuration, tools_configuration)
						samplesheet['postprocessing']['cohort-vcf-files'][tool] = vcf
		
			# for sampleID in samples.keys():
			# 	for sample in samples[sampleID]:
			# 		sample_type, sample_name, vcfs = sample
			# 		if sample_name != '':
			# 			svcf = vcf_split_by_sample(None, None, None, None, vcf, sample_name, workdir, log, panel_configuration, tools_configuration)
			# 			samplesheet['postprocessing'][sampleID][sample_type]['vcfs'][tool] = svcf

		print(samplesheet['postprocessing'][sampleID])

	elif pipeline_configuration['design'] == 'case-control':
		
		bam_array = []
		samplesheet['postprocessing']['case-control-vcf-files'] = {}

		for sampleID in samples.keys():
				samplesheet['postprocessing'][sampleID] = {}
				for sample in samples[sampleID]:
					sample_type, sample_name, bam = sample
					samplesheet['postprocessing'][sampleID][sample_type] = {'sample_name':sample_name, 'vcfs':{}}

		for tool in workflow:	
			args = variantcalling_info[tool]['args']
			for sampleID in samples.keys():
				for sample in samples[sampleID]:
					sample_type, sample_name, bam = sample
					if bam != '' and bam not in bam_array:
						bam_array += [bam]
			vcf, gvcf_array = genotype_germline_cohort(tool, args, filters, threads, ram, bam_array, runID, reference_fasta, workdir, log, panel_configuration, tools_configuration)
			samplesheet['postprocessing']['cohort-vcf-files'][tool] = vcf

	elif pipeline_configuration['design'] == 'trio':
		pass
	
	#samplesheet['variantcalling'][sampleID][sample_type] = {'sample_name':sample_name, 'bam':bam}

	with open('result.json', 'w') as ss:
		json.dump(samplesheet, ss, indent=4)

	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	#print('Sample: '+sample_name+ ' -> Done in: %d min, %d sec' % elapsed_time)
	#f.Delete([sam,bam])
	return samplesheet

def	cnvcalling(samplesheet, cnvcalling_info, reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID):

	start_time = datetime.datetime.now()
	
	#f.makedirs([dirs['preprocessing']])
	#log = open(dirs['log'] + '/preprocessing.log','w+')
	workdir = '/home/jarvis/PROVA/CNV'

	log = open(workdir + '/cnvcalling.log','w+')
	samples = f.read_samplesheet(samplesheet, 'cnvcalling')
	#samplesheet['cnvcalling'] = {}

	#workflow = alignment_pipe['workflow']

	threads = cnvcalling_info['threads']
	ram = cnvcalling_info['ram']
	workflow = cnvcalling_info['workflow']
	#print(variantcalling_info)
	
	start_time = datetime.datetime.now()

	bam_array =[]
	for tool in workflow:
		for sampleID in samples.keys():
			#samplesheet['postprocessing'][sampleID] = {}
			tool_args = cnvcalling_info[tool]
			try:
				algorithm = cnvcalling_info[tool]['algorithm']
			except:
				algorithm = ''
			for sample in samples[sampleID]:
				sample_type, sample_name, bam = sample
				if bam != '':
					bam_array += [[sample_name, bam]]
		vcf = CNV_calling(tool, tool_args, threads, ram, bam, bam_array, runID, reference_fasta, workdir, log, panel_configuration, tools_configuration)

				#samplesheet['postprocessing'][sampleID][sample_type][tool] = vcf
	
	#samplesheet['variantcalling'][sampleID][sample_type] = {'sample_name':sample_name, 'bam':bam}

	#with open('result.json', 'w') as ss:
		#json.dump(samplesheet, ss, indent=4)

	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	#print('Sample: '+sample_name+ ' -> Done in: %d min, %d sec' % elapsed_time)
	#f.Delete([sam,bam])
	return samplesheet

def postprocessing(samplesheet, postprocessing_info, reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID):
	print('postprocessing')
	postprocessing = datetime.datetime.now()
	
	#f.makedirs([dirs['preprocessing']])
	#log = open(dirs['log'] + '/preprocessing.log','w+')
	workdir = '/home/jarvis/PROVA'

	log = open(workdir + '/postprocessing.log','w+')
	samples = f.read_samplesheet(samplesheet, 'postprocessing')

	samplesheet['annotation'] = {}

	#workflow = alignment_pipe['workflow']
	threads = postprocessing_info['threads']
	ram = postprocessing_info['ram']
	workflow = postprocessing_info['workflow']
	start_time = datetime.datetime.now()

	if pipeline_configuration['design'] == 'single-sample':

		for sampleID in samples.keys():
			samplesheet['annotation'][sampleID] = {}
			args = postprocessing_info[tool]['args']			
			for sample in samples[sampleID]:
				sample_type, sample_name, vcfs = sample
				samplesheet['annotation'][sampleID][sample_type] = {'sample_name':sample_name, 'vcfs':{}}
				for vcaller in vcfs:
					vcf = sample[vcaller]
					if 'vcf_norm' in workflow:
						tool = postprocessing_info['vcf_norm']['tool']
						args = postprocessing_info['vcf_norm']['args']
						vcf = vcf_norm(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)

					if 'vcf_filter' in workflow:
						tool = postprocessing_info['vcf_filter']['tool']
						args = postprocessing_info['vcf_filter']['args']
						vcf = vcf_filter(tool, args, threads, ram, vcf, sample_name, runID, workdir, log, panel_configuration, tools_configuration)

					if 'hard_filter' in workflow:
						tool = postprocessing_info['hard_filter']['tool']
						args = postprocessing_info['hard_filter']['args']
						vcf = hard_filter(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)

					samplesheet['annotation'][sampleID][sample_type][vcaller] = vcf

				if 'vcf_merge' in workflow:
					tool = postprocessing_info['vcf_merge']['tool']
					args = postprocessing_info['vcf_merge']['args']
					vcf = vcf_merge(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)
					samplesheet['annotation'][sampleID][sample_type]['merged'] = vcf

				if 'vcf_to_tsv' in workflow:
					tool = postprocessing_info['vcf_to_tsv']['tool']
					args = postprocessing_info['vcf_to_tsv']['args']
					tsv = vcf_to_tsv(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)
					samplesheet['annotation'][sampleID][sample_type]['merged'] = vcf
					samplesheet['annotation'][sampleID][sample_type]['tsv'] = tsv


	elif pipeline_configuration['design'] == 'cohort':

		vcfs = samplesheet['postprocessing']['cohort-vcf-files']
		samplesheet['annotation']['cohort-vcf-files'] = {}
		for vcaller in vcfs.keys():
			if 'vcf_split' in workflow:		
				for sampleID in samples.keys():
					for sample in samples[sampleID]:
						vcf = samplesheet['postprocessing']['cohort-vcf-files'][vcaller]
						sample_type, sample_name, vcfs = sample
						if sample_name != '':
							tool = postprocessing_info['vcf_split']['tool']
							args = postprocessing_info['vcf_split']['args']
							vcf = vcf_split_by_sample(tool, args, threads, ram, vcf, sample_name, workdir, log, panel_configuration, tools_configuration)
							
							tool = postprocessing_info['vcf_norm']['tool']
							args = postprocessing_info['vcf_norm']['args']
							vcf = vcf_norm(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)
							samplesheet['postprocessing'][sampleID][sample_type]['vcfs'][vcaller] = vcf


		if 'vcf_merge' in workflow:
			for sampleID in samples.keys():
				for sample in samples[sampleID]:
					sample_type, sample_name, vcfs = sample
					if sample_name != '':
						tool = postprocessing_info['vcf_merge']['tool']
						args = postprocessing_info['vcf_merge']['args']
						vcf = vcf_merge(tool, args, threads, ram, sample_name, vcfs, workdir, log, panel_configuration, tools_configuration)
						samplesheet['postprocessing'][sampleID][sample_type]['vcfs']['merged'] = vcf

					
		for sampleID in samples.keys():
			samplesheet['annotation'][sampleID] = {}
			for sample in samples[sampleID]:
				vcf_arr = []
				sample_type, sample_name, vcfs = sample
				samplesheet['annotation'][sampleID][sample_type] = {'sample_name':'', 'vcf':'', 'tsv':''}
				if 'merged' in samplesheet['postprocessing'][sampleID][sample_type]['vcfs'].keys():
					vcf = samplesheet['postprocessing'][sampleID][sample_type]['vcfs']['merged']

					if 'vcf_filter' in workflow:
						tool = postprocessing_info['vcf_filter']['tool']
						args = postprocessing_info['vcf_filter']['args']
						vcf = vcf_filter(tool, args, threads, ram, vcf, sample_name, runID, workdir, log, panel_configuration, tools_configuration)
					
					if 'hard_filter' in workflow:
						tool = postprocessing_info['hard_filter']['tool']
						args = postprocessing_info['hard_filter']['args']
						vcf = hard_filter(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)
					
					samplesheet['annotation'][sampleID][sample_type]['sample_name'] = sample_name
					samplesheet['annotation'][sampleID][sample_type]['vcf'] = vcf

					if 'vcf_to_tsv' in workflow:
						tool = postprocessing_info['vcf_to_tsv']['tool']
						args = postprocessing_info['vcf_to_tsv']['args']
						tsv = vcf_to_tsv(tool, args, threads, ram, vcf, sample_name, reference_fasta, workdir, log, panel_configuration, tools_configuration)
						samplesheet['annotation'][sampleID][sample_type]['tsv'] = tsv

		# for sampleID in samples.keys():
		# 	samplesheet['annotation'][sampleID] = {}
			
		# 	for sample in samples[sampleID]:
		# 		sample_type, sample_name, bam = sample
		# 		samplesheet['annotation'][sampleID][sample_type] = {'sample_name':sample_name, 'vcfs':{}}
				#samplesheet['annotation'][sampleID][sample_type][tool] = vcf


	elif pipeline_configuration['design'] == 'case-control':

		pass

	elif pipeline_configuration['design'] == 'trio':
		pass

	with open('result.json', 'w') as ss:
		json.dump(samplesheet, ss, indent=4)

	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	#print('Sample: '+sample_name+ ' -> Done in: %d min, %d sec' % elapsed_time)
	#f.Delete([sam,bam])
	return samplesheet

	##finire annotation

def annotation(samplesheet, annotation_info, reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID):
	print('Variant annotation')
	postprocessing = datetime.datetime.now()
	
	#f.makedirs([dirs['preprocessing']])
	#log = open(dirs['log'] + '/preprocessing.log','w+')
	workdir = '/home/jarvis/PROVA'

	log = open(workdir + '/annotation.log','w+')
	samples = f.read_samplesheet(samplesheet, 'annotation')

	samplesheet['post_annotation'] = {}

	#workflow = alignment_pipe['workflow']
	threads = annotation_info['threads']
	ram = annotation_info['ram']
	workflow = annotation_info['workflow']
#	#print('Sample: ' + sample_name)
	start_time = datetime.datetime.now()

	if pipeline_configuration['design'] == 'single-sample':

		for tool in workflow:
			for sampleID in samples.keys():
				#samplesheet['postprocessing'][sampleID] = {}
				args = annotation_info[tool]['args']			
				for sample in samples[sampleID]:
					sample_type, sample_name, vcfs = sample
					for vcaller in vcfs:
						vcf = sample[vcaller]
						if 'vcf_norm' in workflow:
							tool = postprocessing_info['vcf_norm']['tool']
							args = postprocessing_info['vcf_norm']['args']
							vcf = vcf_norm(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)

						if 'vcf_filter' in workflow:
							tool = postprocessing_info['vcf_filter']['tool']
							args = postprocessing_info['vcf_filter']['args']
							vcf = vcf_filter(tool, args, threads, ram, vcf, sample_name, runID, workdir, log, panel_configuration, tools_configuration)

						if 'hard_filter' in workflow:
							tool = postprocessing_info['hard_filter']['tool']
							args = postprocessing_info['hard_filter']['args']
							vcf = hard_filter(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)
						
						if 'vcf_split' in workflow:
							tool = postprocessing_info['vcf_split']['tool']
							args = postprocessing_info['vcf_split']['args']
							vcf = vcf_split(tool, args, threads, ram, vcf, sample_name, runID, workdir, log, panel_configuration, tools_configuration)

						if 'vcf_merge' in workflow:
							tool = postprocessing_info['vcf_merge']['tool']
							args = postprocessing_info['vcf_merge']['args']
							vcf = vcf_merge(tool, args, threads, ram, vcf, reference_fasta, workdir, log, panel_configuration, tools_configuration)


	elif pipeline_configuration['design'] == 'cohort':

		vcf = samplesheet['annotation']['cohort-vcf-files']
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
	
						

	elif pipeline_configuration['design'] == 'case-control':
		pass

	elif pipeline_configuration['design'] == 'trio':
		pass

	with open('result.json', 'w') as ss:
		json.dump(samplesheet, ss, indent=4)

	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	#print('Sample: '+sample_name+ ' -> Done in: %d min, %d sec' % elapsed_time)
	#f.Delete([sam,bam])
	return samplesheet


def postannotation(samplesheet, postannotation_info, reference_fasta, pipeline_configuration, panel_configuration, tools_configuration, runID):
	print('Post-Annotation')
	
	#f.makedirs([dirs['preprocessing']])
	#log = open(dirs['log'] + '/preprocessing.log','w+')
	workdir = '/home/jarvis/PROVA'

	log = open(workdir + '/postannotation.log','w+')
	samples = f.read_samplesheet(samplesheet, 'postannotation')

		#workflow = alignment_pipe['workflow']
	
	workflow = postannotation_info['workflow']
#	#print('Sample: ' + sample_name)
	start_time = datetime.datetime.now()

	if pipeline_configuration['design'] == 'single-sample':

		for tool in workflow:
			for sampleID in samples.keys():
				#samplesheet['postprocessing'][sampleID] = {}
				args = postannotation_info[tool]['args']			
				for sample in samples[sampleID]:
					sample_type, sample_name, vcfs = sample
					for vcaller in vcfs:
						vcf = sample[vcaller]


	elif pipeline_configuration['design'] == 'cohort':

		vcf = samplesheet['annotation']['cohort-vcf-files']
		for tool in workflow:			
			tool_run_info = postannotation_info[tool]
			args = tool_run_info['args']
			tool = postannotation_info[tool]	
			for sampleID in samples.keys():					
				for sample in samples[sampleID]:
					sample_type, sample_name, vcf, tsv = sample
					if vcf != '' and tsv != '':	
						if 'filter_transcript' in workflow:
							args = postannotation_info['filter_transcript']['args']
							filter = 'filter'
						else:
							filter = None
						tsv = report_annotation(tool, args, filter, vcf, tsv, sample_name, reference_fasta, workdir, log, panel_configuration, tools_configuration)

	elif pipeline_configuration['design'] == 'case-control':
		pass

	elif pipeline_configuration['design'] == 'trio':
		pass

	#with open('result.json', 'w') as ss:
	#	json.dump(samplesheet, ss, indent=4)

	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	#print('Sample: '+sample_name+ ' -> Done in: %d min, %d sec' % elapsed_time)
	#f.Delete([sam,bam])
	return samplesheet

if __name__ == '__main__':

	global maindir
	maindir = os.path.dirname(os.path.realpath(__file__))
	global scripts_path
	scripts_path = maindir+'/scripts/'

	#status = subprocess.call("conda init bash", shell=True)
	#status = subprocess.call("conda activate", shell=True)
	#print(status)
	#status = subprocess.call("conda activate GATK", shell=True)
	 #print(status)
	#exit()
	runID = 'prova_pipeline2'
	samplesheet = '/home/jarvis/result.json'
	#samplesheet = '/home/jarvis/Scrivania/TEST/pipeline/prova_pipeline.ss'
	confirmed_workflow = ['alignment']
	#scripts_path = 'maindir/scripts/'
	#confirmed_workflow = ['annotation','postannotation']
	pipeline_configuration = json.loads((open('/home/jarvis/git/Powercall2/configs/pipeline.PROVA.CFG').read()).encode('utf8'))
	panel_configuration = json.loads((open('/home/jarvis/git/Powercall2/configs/panel.cfg').read()).encode('utf8'))['TrusightCardio']
	tools_configuration = json.loads((open('/home/jarvis/git/Powercall2/configs/Tools.cfg.json').read()).encode('utf8'))
	samplesheet = json.loads((open(samplesheet).read()).encode('utf8'))
	pipeline_builder(samplesheet, confirmed_workflow, pipeline_configuration, panel_configuration, tools_configuration, runID)





