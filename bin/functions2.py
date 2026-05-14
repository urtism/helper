import argparse
import subprocess
import json
import os
import textwrap
import random as rm
import datetime
import pysam
import random as r
import regex as re
from contextlib import contextmanager

def prRed(prt): print("\033[91m {}\033[00m" .format(prt))
def prGreen(prt): print("\033[92m {}\033[00m" .format(prt))

@contextmanager
def working_directory(directory):
    owd = os.getcwd()
    try:
        os.chdir(directory)
        yield directory
    finally:
        os.chdir(owd)

def init_dirs(work_dir,opts):

	dirs = dict()
	dirs['work'] = work_dir
	dirs['storage'] = work_dir + '/STORAGE/'+opts.run_id
	dirs['out'] = work_dir + '/OUTPUT/'+opts.run_id
	dirs['log'] = work_dir + '/LOGS'
	dirs['delete'] = work_dir + '/DELETE'
	dirs['alignment'] = work_dir + '/ALIGNMENT'
	dirs['preprocess'] = work_dir + '/PREPROCESING'
	dirs['variantcalling'] = work_dir + '/VARIANTCALLING'
	dirs['gvcf'] = work_dir + '/VARIANTCALLING/GVCF'
	dirs['featsextract'] = work_dir + '/FEATURES_EXTRACTION'
	dirs['annotation'] = work_dir + '/ANNOTATION'
	dirs['CNV'] = work_dir + '/CNV'
	dirs['CNV_HDF5'] = dirs['CNV'] + '/HDF5'
	dirs['CNV_PLOIDY'] = dirs['CNV'] + '/PLOIDY'
	dirs['CNV_CALLS'] = dirs['CNV'] + '/CALLS'
	dirs['script'] = ('/'.join(os.path.dirname(os.path.abspath(__file__)).split('/')[:-1])) + '/scripts/'
	dirs['logo'] =('/'.join(os.path.dirname(os.path.abspath(__file__)).split('/')[:-1])) + '/logos'
	dirs['files'] = ('/'.join(os.path.dirname(os.path.abspath(__file__)).split('/')[:-1])) + '/files'

	
	return dirs

def makedirs(dirs):
	if type(dirs) is list: 
		for d in dirs:
			if not os.path.exists(d):
				os.makedirs(d)
	else:
		if not os.path.exists(dirs):
			os.makedirs(dirs)

def panel_check(panel,cfg):
	
	if panel == 'TrusightCardio':
		design = 'Enrichment'
		target_list = cfg['target']['TARGET_TRUSIGHTCARDIO_LIST']
		target_bed = cfg['target']['TARGET_TRUSIGHTCARDIO_BED']
		transcripts_list = cfg['files']['TRANSCR_TRUSIGHTCARDIO']
		cnv_target_list = cfg['CNV']['CNV_TARGET_TRUSIGHTCARDIO_LIST']
		cnv_target_bed = cfg['CNV']['CNV_TARGET_TRUSIGHTCARDIO_BED']
		cnv_ref_ploidy = cfg['CNV']['CNV_REF_TRUSIGHTCARDIO_PLOIDY']
		cnv_ref_calls = cfg['CNV']['CNV_REF_TRUSIGHTCARDIO_CALLS']

	elif panel == 'TrusightCancer':
		design = 'Enrichment'
		target_list = cfg['target']['TARGET_TRUSIGHTCANCER_LIST']
		target_bed = cfg['target']['TARGET_TRUSIGHTCANCER_BED']
		transcripts_list = cfg['files']['TRANSCR_TRUSIGHTCANCER']
		cnv_target_list = cfg['CNV']['CNV_TARGET_TRUSIGHTCANCER_LIST']
		cnv_target_bed = cfg['CNV']['CNV_TARGET_TRUSIGHTCANCER_BED']
		cnv_ref_ploidy = cfg['CNV']['CNV_REF_TRUSIGHTCANCER_PLOIDY']
		cnv_ref_calls = cfg['CNV']['CNV_REF_TRUSIGHTCANCER_CALLS']

	elif panel == 'TrusightOne':
		design = 'Enrichment'
		target_list = cfg['target']['TARGET_TRUSIGHTONE_LIST']
		target_bed = cfg['target']['TARGET_TRUSIGHTONE_BED']
		transcripts_list = cfg['files']['TRANSCR_TRUSIGHTONE']		
		cnv_target_list = cfg['CNV']['CNV_TARGET_TRUSIGHTONE_LIST']
		cnv_target_bed = cfg['CNV']['CNV_TRUSIGHTONE_BED']
		cnv_ref_ploidy = cfg['CNV']['CNV_REF_TRUSIGHTONE_PLOIDY']
		cnv_ref_calls = cfg['CNV']['CNV_REF_TRUSIGHTONE_CALLS']

	elif panel == 'BRCAMASTRDx':
		design = 'Amplicon'
		target_list = cfg['target']['TARGET_MULTIPLICOM_BRCA_LIST']
		target_bed = cfg['target']['TARGET_MULTIPLICOM_BRCA_BED']
		transcripts_list = cfg['files']['TRANSCR_BRCA']
		cnv_target_list = cfg['CNV']['CNV_TARGET_BRCA_LIST']
		cnv_target_bed = cfg['CNV']['CNV_BRCA_BED']
		cnv_ref_ploidy = cfg['CNV']['CNV_REF_BRCA_PLOIDY']
		cnv_ref_calls = cfg['CNV']['CNV_REF_BRCA_CALLS']

	elif panel == 'ALPORTMASTR':
		design = 'Amplicon'
		target_list = cfg['target']['TARGET_MULTIPLICOM_ALPORT_LIST']
		target_bed = cfg['target']['TARGET_MULTIPLICOM_ALPORT_BED']
		transcripts_list = cfg['files']['TRANSCR_ALPORT']
		cnv_target_list = cfg['CNV']['CNV_TARGET_ALPORT_LIST']
		cnv_target_bed = cfg['CNV']['CNV_ALPORT_BED']
		cnv_ref_ploidy = cfg['CNV']['CNV_REF_ALPORT_PLOIDY']
		cnv_ref_calls = cfg['CNV']['CNV_REF_ALPORT_CALLS']

	elif panel == 'HCS':
		design = 'Enrichment'
		target_list = cfg['target']['TARGET_HCS_LIST']
		target_bed = cfg['target']['TARGET_HCS_BED']
		transcripts_list = cfg['files']['TRANSCR_HCS']
		cnv_target_list = cfg['CNV']['CNV_TARGET_HCS_LIST']
		cnv_target_bed = cfg['CNV']['CNV_HCS_BED']
		cnv_ref_ploidy = cfg['CNV']['CNV_REF_HCS_PLOIDY']
		cnv_ref_calls = cfg['CNV']['CNV_REF_HCS_CALLS']

	elif panel == 'CustomsamplesheetQXT':
		design = 'Enrichment'
		target_list = cfg['target']['TARGET_SURESELECT_LIST']
		target_bed = cfg['target']['TARGET_SURESELECT_BED']
		transcripts_list = cfg['files']['TRANSCR_SURESELECT']
		cnv_target_list = cfg['CNV']['CNV_TARGET_SURESELECT_LIST']
		cnv_target_bed = cfg['CNV']['CNV_SURESELECT_BED']
		cnv_ref_ploidy = cfg['CNV']['CNV_REF_SURESELECT_PLOIDY']
		cnv_ref_calls = cfg['CNV']['CNV_REF_SURESELECT_CALLS']

	elif panel == 'CustomHPHS':
		design = 'Amplicon'
		target_list = cfg['target']['TARGET_HALOPLEX_LIST']
		target_bed = cfg['target']['TARGET_HALOPLEX_BED']
		transcripts_list = cfg['files']['TRANSCR_HALOPLEX']
		cnv_target_list = cfg['CNV']['CNV_TARGET_HALOPLEX_LIST']
		cnv_target_bed = cfg['CNV']['CNV_HALOPLEX_BED']
		cnv_ref_ploidy = cfg['CNV']['CNV_REF_HALOPLEX_PLOIDY']
		cnv_ref_calls = cfg['CNV']['CNV_REF_HALOPLEX_CALLS']

	elif panel == 'Custom':
		design = 'Enrichment'
		target_list = cfg['target']['TARGET_CUSTOM_LIST']
		target_bed = cfg['target']['TARGET_CUSTOM_BED']
		transcripts_list = cfg['files']['TRANSCR_CUSTOM']
		cnv_target_list = cfg['CNV']['CNV_TARGET_CUSTOM_LIST']
		cnv_target_bed = cfg['CNV']['CNV_CUSTOM_BED']
		cnv_ref_ploidy = cfg['CNV']['CNV_REF_CUSTOM_PLOIDY']
		cnv_ref_calls = cfg['CNV']['CNV_REF_CUSTOM_CALLS']

	return design,target_list,target_bed,transcripts_list,cnv_target_list,cnv_target_bed,cnv_ref_ploidy,cnv_ref_calls

def read_samplesheet(samplesheet, step):
	samples = dict()
	if step == 'prealignment' or step == 'alignment':
		for sampleID in samplesheet[step]:

			case_sample_name = samplesheet[step][sampleID]['case']['sample_name']
			case_fq_R1 = samplesheet[step][sampleID]['case']['fastq_R1']
			case_fq_R2 = samplesheet[step][sampleID]['case']['fastq_R2']
			case_fq_I2 = samplesheet[step][sampleID]['case']['fastq_I2']
			case = ['case', case_sample_name, case_fq_R1, case_fq_R2, case_fq_I2]
			samples[sampleID] = [case]

			if samplesheet['sample_organization'] == 'case-control':
				ctrl_sample_name = samplesheet[step][sampleID]['control']['sample_name']
				ctrl_fq_R1 = samplesheet[step][sampleID]['control']['fastq_R1']
				ctrl_fq_R2 = samplesheet[step][sampleID]['control']['fastq_R2']
				ctrl_fq_I2 = samplesheet[step][sampleID]['control']['fastq_I2']
				control = ['control', ctrl_sample_name, ctrl_fq_R1, ctrl_fq_R2, ctrl_fq_I2]
				samples[sampleID] += [control]

			if samplesheet['sample_organization'] == 'trio':
				parent1_sample_name = samplesheet[step][sampleID]['parent1']['sample_name']
				parent1_fq_R1 = samplesheet[step][sampleID]['parent1']['fastq_R1']
				parent1_fq_R2 = samplesheet[step][sampleID]['parent1']['fastq_R2']
				parent1_fq_I2 = samplesheet[step][sampleID]['parent1']['fastq_I2']

				parent2_sample_name = samplesheet[step][sampleID]['parent2']['sample_name']
				parent2_fq_R1 = samplesheet[step][sampleID]['parent2']['fastq_R1']
				parent2_fq_R2 = samplesheet[step][sampleID]['parent2']['fastq_R2']
				parent2_fq_I2 = samplesheet[step][sampleID]['parent2']['fastq_I2']

				parent1 = ['parent1', parent1_sample_name, parent1_fq_R1, parent1_fq_R2, parent1_fq_I2]
				parent2 = ['parent2', parent2_sample_name, parent2_fq_R1, parent2_fq_R2, parent2_fq_I2]
				samples[sampleID] += [parent1]
				samples[sampleID] += [parent2]
	
	elif step == 'preprocessing' or step == 'variantcalling' or step == 'cnvcalling' or step == 'variant/CNV calling':
		
		for sampleID in samplesheet[step]:
			
			case_sample_name = samplesheet[step][sampleID]['case']['sample_name']
			case_bam = samplesheet[step][sampleID]['case']['bam']
			case = ['case', case_sample_name, case_bam]
			samples[sampleID] = [case]

			if samplesheet['sample_organization'] == 'case-control':
				ctrl_sample_name = samplesheet[step][sampleID]['control']['sample_name']
				ctrl_bam = samplesheet[step][sampleID]['control']['bam']
				control = ['control', ctrl_sample_name , ctrl_bam]
				samples[sampleID] += [control]

			if samplesheet['sample_organization'] == 'trio':
				parent1_sample_name = samplesheet[step][sampleID]['parent1']['sample_name']
				parent1_bam = samplesheet[step][sampleID]['parent1']['bam']
				parent1 = ['parent1', parent1_sample_name , parent1_bam]

				parent2_sample_name = samplesheet[step][sampleID]['parent2']['sample_name']
				parent2_bam = samplesheet[step][sampleID]['parent2']['bam']
				parent2 = ['parent2', parent2_sample_name , parent2_bam]
				samples[sampleID] += [parent1]
				samples[sampleID] += [parent2]


	elif step == 'postprocessing':
		
		for sampleID in samplesheet[step]:
			try:
				case_sample_name = samplesheet[step][sampleID]['case']['sample_name']
				case_vcfs = samplesheet[step][sampleID]['case']['vcf']
				case_cnv = samplesheet[step][sampleID]['case']['cnv']
				case = ['case', case_sample_name, case_vcfs, case_cnv]
				samples[sampleID] = [case]


				if samplesheet['sample_organization'] == 'case-control':
					ctrl_sample_name = samplesheet[step][sampleID]['control']['sample_name']
					ctrl_vcfs = samplesheet[step][sampleID]['control']['vcf']
					control = ['control', ctrl_sample_name , ctrl_vcfs]
					samples[sampleID] += [control]

				if samplesheet['sample_organization'] == 'trio':
					parent1_sample_name = samplesheet[step][sampleID]['parent1']['sample_name']
					parent1_vcfs = samplesheet[step][sampleID]['parent1']['vcf']

					parent2_sample_name = samplesheet[step][sampleID]['parent2']['sample_name']
					parent2_vcfs = samplesheet[step][sampleID]['parent2']['vcf']
					parent1 = ['parent1', parent1_sample_name , parent1_vcfs]
					parent2 = ['parent2', parent2_sample_name , parent2_vcfs]
					samples[sampleID] += [parent1]
					samples[sampleID] += [parent2]
			except:
				continue

	elif step == 'variant_annotation':
		
		for sampleID in samplesheet[step]:
			
			case_sample_name = samplesheet[step][sampleID]['case']['sample_name']
			case_vcf = samplesheet[step][sampleID]['case']['vcf']
			case_tsv = samplesheet[step][sampleID]['case']['tsv']
			#case_cnv = samplesheet[step][sampleID]['case']['cnv']
			case = ['case', case_sample_name, case_vcf,case_tsv]
			samples[sampleID] = [case]

			if samplesheet['sample_organization'] == 'case-control':
				ctrl_sample_name = samplesheet[step][sampleID]['control']['sample_name']
				ctrl_vcf = samplesheet[step][sampleID]['control']['vcf']
				ctrl_tsv = samplesheet[step][sampleID]['control']['tsv']
				control = ['control', ctrl_sample_name , ctrl_vcf, ctrl_tsv]
				samples[sampleID] += [control]

			if samplesheet['sample_organization'] == 'trio':
				parent1_sample_name = samplesheet[step][sampleID]['parent1']['sample_name']
				parent1_vcf = samplesheet[step][sampleID]['parent1']['vcf']
				parent1_tsv = samplesheet[step][sampleID]['parent1']['tsv']

				parent2_sample_name = samplesheet[step][sampleID]['parent2']['sample_name']
				parent2_vcf = samplesheet[step][sampleID]['parent2']['vcf']
				parent2_tsv = samplesheet[step][sampleID]['parent2']['tsv']

				parent1 = ['parent1', parent1_sample_name , parent1_vcf, parent1_tsv]
				parent2 = ['parent2', parent2_sample_name , parent2_vcf, parent2_tsv]
				samples[sampleID] += [parent1]
				samples[sampleID] += [parent2]

				samples[sampleID] = [case, parent1, parent2]

	elif step == 'postannotation':
		
		for sampleID in samplesheet[step]:
			
			case_sample_name = samplesheet[step][sampleID]['case']['sample_name']
			case_vcf = samplesheet[step][sampleID]['case']['vcf']
			case_tsv = samplesheet[step][sampleID]['case']['tsv']
			#case_cnv = samplesheet[step][sampleID]['case']['cnv']
			case = ['case', case_sample_name, case_vcf, case_tsv]
			samples[sampleID] = [case]

			if samplesheet['sample_organization'] == 'case-control':
				ctrl_sample_name = samplesheet[step][sampleID]['control']['sample_name']
				ctrl_vcf = samplesheet[step][sampleID]['control']['vcf']
				ctrl_tsv = samplesheet[step][sampleID]['control']['tsv']
				control = ['control', ctrl_sample_name , ctrl_vcf, ctrl_tsv]
				samples[sampleID] += [control]

			if samplesheet['sample_organization'] == 'trio':
				parent1_sample_name = samplesheet[step][sampleID]['parent1']['sample_name']
				parent1_vcf = samplesheet[step][sampleID]['parent1']['vcf']
				parent1_tsv = samplesheet[step][sampleID]['parent1']['tsv']

				parent2_sample_name = samplesheet[step][sampleID]['parent2']['sample_name']
				parent2_vcf = samplesheet[step][sampleID]['parent2']['vcf']
				parent2_tsv = samplesheet[step][sampleID]['parent2']['tsv']
				parent1 = ['parent1', parent1_sample_name , parent1_vcf, parent1_tsv]
				parent2 = ['parent2', parent2_sample_name , parent2_vcf, parent2_tsv]
				samples[sampleID] += [parent1]
				samples[sampleID] += [parent2]
			
	return samples


def Delete(files):
	for f in files:
		if os.path.isfile(f): 
			status = subprocess.call("rm -rf" + f, shell=True)
		elif os.path.ispath(f):
			status = subprocess.call("rm -rf" + f, shell=True)

def Move(files,newdir):
	for f in files:
		if os.path.isfile(f): 
			status = subprocess.call("mv " + f + ' ' + newdir, shell=True)
		elif os.path.ispath(f):
			status = subprocess.call("mv " + f + ' ' + newdir, shell=True)

def Copy(files,newdir):
	for f in files:
		if os.path.isfile(f): 
			status = subprocess.call("cp " + f + ' ' + newdir, shell=True)
		else:
			print(f + ": error in coping file(s)")

def Conda(arg):
	print(arg)
	status = subprocess.call(['/bin/bash', '-i', '-c', "conda", arg],shell=True)
	print(status)


def Make_CNV_report(infofile, cnv_vcf_array, workdir, log):

	def checkX(X):
		allele0 = []
		allele1 = []
		allele2 = []
		allele3 = []
		cnv_arr = []
		for xcnv in X:
			sample_id, chrom, start, end, cn, cnlp, cnq = xcnv
			if cn == '1':
				allele1 += [[sample_id, chrom, start, end, cn, cnlp, cnq]]
			elif cn == '0':
				allele0 += [[sample_id, chrom, start, end, cn, cnlp, cnq]]
			elif cn == '2':
				allele2 += [[sample_id, chrom, start, end, cn, cnlp, cnq]]
			else:
				allele3 += [[sample_id, chrom, start, end, cn, cnlp, cnq]]

		if allele3 != []:
			cnv_arr += allele3
		if allele0 != []:
			cnv_arr += allele0
		if allele1 != [] and allele2 != []:
			if len(allele2) > len(allele1):
				cnv_arr += allele1
			else:
				cnv_arr += allele2
		return cnv_arr

	report = workdir + '/GATK.CNV.Report.tsv'
	repo = open(report,'w')
	repo.write('\t'.join(['SAMPLE_ID', 'CHROM', 'START', 'END', 'NUM_OF_COPIES', 'LIKELIHOODS', 'MIN_LIKELIHOOD' ,'GENE', 'EXON']) +'\n')
	
	for cnv_vcf in cnv_vcf_array:
		cnv = []
		X = []
		with open(cnv_vcf) as file:
			for line in file:
				if line.startswith('##'):
					continue
				elif line.startswith('#'):
					sample_id = line.split('\t')[-1].rstrip()
				else:
					chrom, pos, id, ref, alt, qual, filter, info, format, sample = line.rstrip().split('\t')
					start = id.split('_')[2]
					end = id.split('_')[3]
					gt, cn, cnlp, cnq = sample.split(':')

					if chrom == 'chrX' or chrom == 'X':
						X += [[sample_id, chrom, start, end, cn, cnlp, cnq]]
					elif gt != '0' or (gt == '0' and int(cnq)) < 10:	
						cnv += [[sample_id, chrom, start, end, cn, cnlp, cnq]]
			file.close()
		#print(sample_id, checkX(X))
		cnv += checkX(X)

		for rawcnv in cnv:
			gene = '-'
			exon = '-'
			sample_id, chrom, start, end, cn, cnlp, cnq = rawcnv
			if infofile != "":
				with open(infofile) as ifile:
					for iline in ifile:
						if line.startswith('Gene_name'):
							continue
						else:
							Gene_name, Gene_ID, Transcript_ID, RefSeq_ID, Strand, Chromosome, Exon_region_start, Exon_region_end, Exon_rank_in_transcript = iline.rstrip().split('\t')
							
							if Chromosome == chrom and int(Exon_region_start) - 100 <= int(start) and int(Exon_region_end) + 100  >= int(end):
								gene = Gene_name 
								exon = Exon_rank_in_transcript
			repo.write('\t'.join(rawcnv+[gene,exon]) +'\n')
	repo.close()

	return report