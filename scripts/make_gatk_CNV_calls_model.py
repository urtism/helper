import argparse
import subprocess
import os
import datetime
import random
#from ruffus import *

def prRed(prt): print("\033[91m {}\033[00m" .format(prt))
def prGreen(prt): print("\033[92m {}\033[00m" .format(prt))

def makedirs(dirs):
	for d in dirs:
		if not os.path.exists(d):
			os.makedirs(d)

def Copy(files,newdir):
	for f in files:
		if os.path.isfile(f): 
			status = subprocess.call("cp " + f + ' ' + newdir, shell=True)
		else:
			print(files + ": error in coping file(s)")

def GATK_CollectReadCounts(path,bam,sample_name,target_list,log,workdir):
	
	success = False
	hdf5 = workdir + '/' +sample_name +'.hdf5'
	if not os.path.isfile(hdf5):
		args = [path, 'CollectReadCounts', '-I', bam, '-L', target_list, '--interval-merging-rule', 'OVERLAPPING_ONLY', '-O', hdf5]
		success = subprocess.call(args,stdout=log,stderr=log)
	#success = False
	if not success:
		return hdf5
	else:
		prRed('Error in CNV calling. Check log file.')
		exit(1)

def GATK_DetermineGermlineContigPloidy(path,hdf5,sample_name,ploidy_model,log,workdir):

	success = False
	out_dir = workdir + '/' + sample_name
	args = [path, 'DetermineGermlineContigPloidy','--output-prefix', sample_name, '--contig-ploidy-priors', ploidy_model, '--output', out_dir]

	print(args)
	
	if isinstance(hdf5, list):
		for sample_hdf5 in hdf5: 
			args += ['--input', sample_hdf5]
	else:
		args =+ ['--input', hdf5]

	success = subprocess.call(args,stdout=log,stderr=log)
	#success = False
	if not success:
		return out_dir
	else:
		prRed('Error in CNV calling. Check log file.')
		exit(1)


def GATK_GermlineCNVCaller(path,hdf5,sample_name,sample_ploidy,log,workdir):

	success = False
	args = [path, 'GermlineCNVCaller', '--run-mode', 'COHORT', '--contig-ploidy-calls', sample_ploidy + '/'+ sample_name + '-calls',
		 '--output', workdir, '--output-prefix', sample_name]
	
	if isinstance(hdf5, list):
		for sample_hdf5 in hdf5: 
			args += ['--input', sample_hdf5]
	else:
		args =+ ['--input', hdf5]

	success = subprocess.call(args,stdout=log,stderr=log)

	calls = workdir + '/' + sample_name + '-calls'
	model = workdir + '/' + sample_name + '-model'
	#success = False
	if not success:
		return calls, model
	else:
		prRed('Error in CNV calling. Check log file.')
		exit(1)


if __name__ == '__main__':

	parser = argparse.ArgumentParser('this script generates PLOIDY model for the gatk cnv caller')
	parser.add_argument('-t', '--target', help="target list file")
	parser.add_argument('-l', '--bam_list', help="List of bam")
	parser.add_argument('--hdf5_list', help="List of hdf5 files")
	parser.add_argument('-s', '--sample_list', help="List of sample to use in ploidy calls. it will be used to filter the bam list")
	parser.add_argument('-o','--out', help="Output path")
	parser.add_argument('--name', help="Output name")
	parser.add_argument('-n','--nsamples', help="number of samples to use in PLOIDY modelling")
	parser.add_argument('-p','--ploidy_model', help="Previous ploidy model")
	
	start_time = datetime.datetime.now()
	success = subprocess.call('clear')
	
	global opts
	opts = parser.parse_args()
	HDF5_dir = opts.out + '/HDF5'
	ploidy_dir = opts.out + '/PLOIDY'
	calls_dir = opts.out + '/CALLS'
	makedirs([opts.out,HDF5_dir,ploidy_dir,calls_dir])

	path = '/home/jarvis/NGS_TOOLS/GATK/gatk-4.3.0.0/gatk'
	log = open(opts.out + '/ploidy.log','w+')
	hdf5_array = []
	name = opts.name
	ploidy_model = opts.ploidy_model
	bam_list = []
	
	if opts.bam_list != None:
		bam_list = [a.rstrip() for a in open(opts.bam_list ,'r').readlines()]

	if opts.sample_list != None:
		new_bam_list = []
		sample_list = [a.rstrip() for a in open(opts.sample_list,'r').readlines()]
		if opts.nsamples != None:
			try:
				sample_list = random.sample(sample_list, int(opts.nsamples))
			except Exception as e:
				print(e)

		for bam in bam_list:
			sample_name = bam.split('/')[-1].split('.')[0]
			if sample_name in sample_list:
				new_bam_list += [bam]

		bam_list = new_bam_list
	print('ploidy calculated using ' + str(len(bam_list)) + ' samples')
	
	if opts.hdf5_list is None:
		for bam in bam_list:
			if os.path.isfile(bam):
				sample_name = bam.split('/')[-1].split('.')[0]
				hdf5 = GATK_CollectReadCounts(path,bam,sample_name,opts.target,log,HDF5_dir)
				hdf5_array += [hdf5]
			else:
				print(bam + " doesn't exist")
	else:
		hdf5_array = [a.rstrip() for a in open(opts.hdf5_list,'r').readlines()]

	#print(hdf5_array)

	ploidy = GATK_DetermineGermlineContigPloidy(path,hdf5_array,name,ploidy_model,log,ploidy_dir)
	calls, model = GATK_GermlineCNVCaller(path,hdf5_array,name,ploidy,log,calls_dir)

	Copy([opts.target,opts.sample_list,opts.bam_list],opts.out)
