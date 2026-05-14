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
	dirs['preprocessing'] = work_dir + '/PREPROCESSING'
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
	for d in dirs:
		if not os.path.exists(d):
			os.makedirs(d)

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

	elif panel == 'CustomSSQXT':
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

def ReadSampleSheet(samplesheet,analysis,panel,step):
	ssheet = dict()
	if step == 'Alignment':
		with open(samplesheet,'r') as ss:
			for line in ss:
				line=line.rstrip()
				if panel == 'CustomHPHS':
					if analysis == 'Germline' or analysis == 'Somatic':
						sample_name = line.split('\t')[0]
						fq1 = line.split('\t')[1]
						fq2 = line.split('\t')[2]
						fqI2 = line.split('\t')[3]
						ssheet[sample_name] = [[sample_name,fq1,fq2,fqI2]]

					elif analysis == 'Somatic_Case_Control':
						gsample_name = line.split('\t')[0]
						gfq1 = line.split('\t')[1]
						gfq2 = line.split('\t')[2]
						gfqI2 = line.split('\t')[3]
						ssample_name = line.split('\t')[4]
						sfq1 = line.split('\t')[5]
						sfq2 = line.split('\t')[6]
						sfqI2 = line.split('\t')[7]
						ssheet[ssample_name] = [[gsample_name,gfq1,gfq2,gfqI2],[ssample_name,sfq1,sfq2,sfqI2]]
				else:
					if analysis == 'Germline' or analysis == 'Somatic':
						sample_name = line.split('\t')[0]
						fq1 = line.split('\t')[1]
						fq2 = line.split('\t')[2]
						ssheet[sample_name] = [[sample_name,fq1,fq2]]

					elif analysis == 'Somatic_Case_Control':
						gsample_name = line.split('\t')[0]
						gfq1 = line.split('\t')[1]
						gfq2 = line.split('\t')[2]
						ssample_name = line.split('\t')[3]
						sfq1 = line.split('\t')[4]
						sfq2 = line.split('\t')[5]
						ssheet[ssample_name] = [[gsample_name,gfq1,gfq2],[ssample_name,sfq1,sfq2]]
	
	elif step == 'Preprocessing':
		with open(samplesheet,'r') as ss:
			for line in ss:
				line=line.rstrip()
				if analysis == 'Germline' or analysis == 'Somatic':
					sample_name = line.split('\t')[0]
					bam = line.split('\t')[1]
					ssheet[sample_name] = [[sample_name,bam]]

				elif analysis == 'Somatic_Case_Control':
					gsample_name = line.split('\t')[0]
					gbam = line.split('\t')[1]
					ssample_name = line.split('\t')[2]
					sbam = line.split('\t')[3]
					ssheet[ssample_name] = [[gsample_name,gbam],[ssample_name,sbam]]

	elif step == 'VariantCalling':
		with open(samplesheet,'r') as ss:
			for line in ss:
				line=line.rstrip()
				if analysis == 'Germline' or analysis == 'Somatic':
					sample_name = line.split('\t')[0]
					bam = line.split('\t')[1]
					ssheet[sample_name] = [[sample_name,bam]]

				elif analysis == 'Somatic_Case_Control':
					gsample_name = line.split('\t')[0]
					gbam = line.split('\t')[1]
					ssample_name = line.split('\t')[2]
					sbam = line.split('\t')[3]
					ssheet[ssample_name] = [[gsample_name,gbam],[ssample_name,sbam]]

	elif step == 'Featuresextraction':
		with open(samplesheet,'r') as ss:
			for line in ss:
				line=line.rstrip()
				if analysis == 'Germline':
					sample_name = line.split('\t')[0]
					try:
						vcf_gatk = line.split('\t')[1]
						vcf_freebayes = line.split('\t')[2]
						vcf_varscan = line.split('\t')[3]
						ssheet[sample_name] = [[sample_name,vcf_gatk,vcf_freebayes,vcf_varscan]]
					except:
						vcf_merge = line.split('\t')[1]
						ssheet[sample_name] = [[sample_name,vcf_merge]]
				elif analysis == 'Somatic_Case_Control':
					gsample_name = line.split('\t')[0]
					ssample_name = line.split('\t')[1]
					mutect_vcf,vardict_vcf,varscan_vcf = line.split('\t')[2:]
					ssheet[ssample_name] = [[gsample_name,ssample_name,mutect_vcf,vardict_vcf,varscan_vcf]]
				elif analysis == 'Somatic':
					ssample_name = line.split('\t')[0]
					mutect_vcf = line.split('\t')[1]
					ssheet[ssample_name] = [[ssample_name,mutect_vcf]]

	elif step == 'Annotation':
		with open(samplesheet,'r') as ss:
			for line in ss:
				line=line.rstrip()
				if analysis == 'Germline':
					name = line.split('\t')[0]
					vcf = line.split('\t')[1]
					samples = line.split('\t')[2]
					ssheet[name] = [[name,vcf,samples]]
					#ssheet[name] = [[name,vcf]]
				elif analysis == 'Somatic_Case_Control' or analysis == 'Somatic':
					name = line.split('\t')[0]
					vcf = line.split('\t')[1]
					tsv = line.split('\t')[2]
					ssheet[name] = [[name,vcf,tsv]]

	elif step == 'CNV':
		with open(samplesheet,'r') as ss:
			for line in ss:
				line=line.rstrip()
				if analysis == 'Germline':
					sample_name = line.split('\t')[0]
					bam = line.split('\t')[1]
					ssheet[sample_name] = [[sample_name,bam]]
					#ssheet[name] = [[name,vcf]]
				elif analysis == 'Somatic_Case_Control' or analysis == 'Somatic':
					gsample_name = line.split('\t')[0]
					gbam = line.split('\t')[1]
					ssample_name = line.split('\t')[2]
					sbam = line.split('\t')[3]
					ssheet[ssample_name] = [[gsample_name,gbam],[ssample_name,sbam]]
			
	return ssheet


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