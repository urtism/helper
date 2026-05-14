import subprocess
import os
import functions2 as f
import datetime


### VCF processing ######
def header_fix(path,vcf,variantcaller,log):
	fix_vcf = '.'.join(vcf.split('.')[:-1] + ['hfix.vcf'])
	open_fix_vcf = open(fix_vcf,'w')
	args = ['python2',path+'/header_fix.py','-v',variantcaller,'-f',vcf]
	success = subprocess.call(args,stdout=open_fix_vcf,stderr=log)
	open_fix_vcf.close()
	if not success:
		return fix_vcf
	else:
		f.prRed('Error in Vcf fix. Check log file.')
		exit(1)


def Vcf_filter(path,vcf,log,workdir):
	vc = vcf.split('.')[:-1]
	out = ".".join(vc+['filter.vcf'])

	args = ['python', path+'/VCF_filter.py', '--vcf',vcf, '--out',out]

	#if format != '': args += ['--format', format]
	#print(' '.join(args))
	success = subprocess.call(args,stdout=log,stderr=log)
	#print(' '.join(args))
	if not success:
		print('- Vcf filtered')
		return out
	else:
		f.prRed('Error in Vcf filtration. Check log file.')
		exit(1)


def Filter_by_sample(path,vcf,sample_name,log,workdir):
	vc = vcf.split('.')[1]
	out = workdir + '/' + sample_name + '.'+ vc +'.vcf'

	args = ['python',path+'/vcf_filter_by_sample.py', '--vcf',vcf, '--samplename',sample_name, '--out',out]
	success = subprocess.call(args,stdout=log,stderr=log)
	print(args)
	if not success:
		print('- Split ' +sample_name)
		return out
	else:
		print(' '.join(args))
		f.prRed('Error in split Vcf by sample name. Check log file.')
		exit(1)

def filter_transcript(path,transcript_list,vcf,log,workdir):

	trs_vcf = workdir + '/' + '.'.join(vcf.split('/')[-1].split('.')[:-1] + ['trs.vcf'])

	args = ['python3', path+'/Transcript_selector.py', '-i', vcf, '-o', trs_vcf, '--trs_list', transcript_list]
	
	success = subprocess.call(args,stdout=log,stderr=log)
	if not success:
		print(" ".join(args))
		return trs_vcf
	else:
		f.prRed('Error in Transcripts selection. Check log file.')
		exit(1)

def Vcf_to_tsv(path,vcf,tag_file,format,info,sample_name,log,workdir):

	out = workdir + '/' + sample_name + '.tsv'

	args = ['python', path+'/vcf_to_tsv.py', '--vcf',vcf, '--out',out]

	if tag_file != '': args += ['--tag_file', tag_file]
	if format != '': args += ['--format', format]
	if info != '': args += ['--info', info]

	success = subprocess.call(args,stdout=log,stderr=log)
	#print(' '.join(args))
	if not success:
		print('- From vcf to tsv: ' +sample_name)
		return out
	else:
		f.prRed('Error in Vcf conversion to tsv format . Check log file.')
		exit(1)

def add_Annotation(path,name,vcf,tsv,tag_list,transcript_list,log,workdir):

	annotated_tsv = workdir + '/' + name + '.annotated.tsv'


	args = ['python',path+'/annotation_extractor.py','--vcf',vcf,'--tsv',tsv,'-o',annotated_tsv,'--tag_list',tag_list,'--trs_list',transcript_list]
	
	success = subprocess.call(args,stdout=log,stderr=log)

	if success:
		f.prRed('Error in tsv annotation. Check log file.')
		print(' '.join(args))
		exit(1)
	else:
		print('annotated: ' + annotated_tsv)

	return annotated_tsv

def merge_vcf(path,name,gatk,freebayes,varscan,log,workdir):

	merge_vcf = workdir + '/' + name + '.merge.vcf'
	args = ['python2',path +'/merge_vcf.py','-g',gatk,'-f',freebayes,'-o',merge_vcf]
	if varscan:
		args += ['-v',varscan]
	success = subprocess.call(args,stdout=log,stderr=log)

	if not success:
		return merge_vcf
	else:
		f.prRed('Error in Vcf merging. Check log file.')
		exit(1)

def merge_vcfs(path,name,gatk,freebayes,varscan,log,workdir):

	merged_vcf = workdir + '/' + name + '.merge.vcf'
	args = ['python',path  +'/merge_vcfs.py','-o',merged_vcf]

	if gatk != None:
		args += ['-g',gatk]
	if freebayes != None:
		args += ['-f',freebayes]
	if varscan != None:
		args += ['-v',varscan]

	#print(' '.join(args))
		
	success = subprocess.call(args,stdout=log,stderr=log)

	if not success:
		return merged_vcf
	else:
		f.prRed('Error in Vcf merging. Check log file.')
		exit(1)

def features_extractor(path,outpath,gatk,freebayes,varscan,merge,features_list,gvcf_path,design,log,workdir):
	start_time = datetime.datetime.now()
	args = ['python2',path+'/features_extractor.py','--listaFeatures',features_list,'--gvcf_path',gvcf_path,'-o',outpath]
	tsvfile = outpath+'/tsv.list'

	if merge:
		args += ['--merge',merge]
	if gatk:
		args += ['-g',gatk]
	if freebayes:
		args += ['-f',freebayes]
	if varscan:
		args += ['-v']

	# if design == "Amplicon":
	# 	args += ['-a']

	success = subprocess.call(args,stderr=log)
	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)

	if not success:
		#print("- Estraction: %d min, %d sec" % elapsed_time)
		return merge,tsvfile
	else:
		f.prRed('Error in features extraction. Check log file.')
		exit(1)


### REPORT #######


