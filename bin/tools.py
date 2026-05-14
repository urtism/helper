import subprocess
import functions as f
import os
import datetime
###----------------------------------------------------------------------------------------------ALIGNMENT-------------------------------------------------------------------------------------


def Bwa_mem(path,threads,sample_name,fastq1,fastq2,reference,log,workdir):
	
	sam = workdir +'/'+sample_name+'.sam'
	sam_file=open(sam,'w+')

	for elem in [path,fastq1,fastq2,reference,workdir]:
		if os.path.isfile(elem) or os.path.isdir(elem):
			pass
		else: 
			print(elem)
	#print('- BWA mem')
	
	if fastq2 == None:
		args = [path,'mem',reference,fastq1,'-t',threads]
	else:
		args = [path,'mem',reference,fastq1,fastq2,'-t',threads]
	
	success = subprocess.call(args, stdout=sam_file,stderr=log)
	if not success:
		return sam
	else:
		f.prRed('Error in Alignment. Check log file.')
		exit(1)

def SamFormatConverter(path,ram,sam,log,workdir):

	bam= workdir + '/' + '.'.join(sam.split('/')[-1].split('.')[:-1])+'.bam'
	args = ['java','-Xmx'+ram,'-jar',path,'SamFormatConverter','I='+sam,'O='+bam]
	success = subprocess.call(args,stdout=log,stderr=log)
	if not success:
		return bam
	else:
		f.prRed('Error in Conversion. Check log file.')
		exit(1)

def SortSam(path,ram,bam,log,workdir):
	#print('- Bam sorting')
	sort = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1])+'.sort.bam'
	args = ['java','-Xmx'+ram,'-jar',path,'SortSam','I='+bam,'O='+sort,'SORT_ORDER=coordinate']
	success = subprocess.call(args,stdout=log,stderr=log)
	if not success:
		return sort
	else:
		f.prRed('Error in Sorting. Check log file.')
		exit(1)

def SureCallTrimmer(path,ram,fq1,fq2,tag,outdir,log,workdir):

	#print('- Adapters trimming'9
	args = ['java','-Xmx'+ram,'-jar',path,'-fq1',fq1,'-fq2',fq2,'-'+tag,'-out_loc',outdir]
	success = subprocess.call(args,stdout=log,stderr=log)

	fq1_name= fq1.split('/')[-1]
	fq2_name= fq2.split('/')[-1]

	for file in os.listdir(outdir):
		if fq1_name in file:
			trimmed_fq1 = outdir+'/'+file
		elif fq2_name in file:
			trimmed_fq2 = outdir+'/'+file

	if not success:
		return trimmed_fq1,trimmed_fq2
	else:
		f.prRed('Error in Trimming of adapters. Check log file.')
		exit(1)
	
def LocatIt(path,ram,bam,fqI2,log,workdir):
	#print("- Merging haloplex molecular barcodes")
	outbam = workdir +'/'+ '.'.join(sam.split('/')[-1].split('.')[:-1] + ['MCBmerged'] +['bam'])
	args = ['java','-Xmx'+ram,'-jar',path,'-U','-IB','-OB','-i','-o',outbam,bam,fqI2]
	success = subprocess.call(args,stdout=log,stderr=log)

	if not success:
		return outbam
	else:
		f.prRed('Error in merging molucular barcodes. Check log file.')
		exit(1)

###----------------------------------------------------------------------------------------------PREPROCESSING-------------------------------------------------------------------------------------

def AddOrReplaceReadGroups(path,ram,bam,sample_name,panel,run,log,workdir):
	#print("- Add/replace Read groups")
	outbam = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1] + ['RG'] +['bam'])
	print(outbam)
	args = ['java','-Xmx'+ram,'-jar',path,'AddOrReplaceReadGroups',
		'I='+bam,
		'O='+outbam,
		'RGID='+sample_name,
		'RGPL=ILLUMINA',
		'RGSM='+sample_name,
		'RGLB='+panel,
		"RGPU="+run,
		'VALIDATION_STRINGENCY=LENIENT']
	print(args)
	success = subprocess.call(args,stdout=log,stderr=log)

	if not success:
		return outbam
	else:
		f.prRed('Error in Adding or replacing Read groups. Check log file.')
		exit(1)

def BuildBamIndex(path,ram,bam,log):

	#print('- Bam indexing')
	bai= bam+'.bai'
	if os.path.exists(bai):
		status = subprocess.call("rm "+ bai , shell=True)
	args = ['java','-Xmx'+ram,'-jar',path,'BuildBamIndex','I='+bam,'O='+bai,'VALIDATION_STRINGENCY=LENIENT']
	success = subprocess.call(args,stdout=log,stderr=log)
	if not success:
		pass
	else:
		f.prRed('Error in Indexing. Check log file.')
		exit(1)


def MarkDuplicates(path,ram,bam,log,workdir):

	#print("- Marking duplicates")
	outbam = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1] + ['Mark'] +['bam'])
	metrics_file = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1] + ['MarkMetrics'] +['txt'])
	args = ['java','-Xmx'+ram,'-jar',path,'MarkDuplicates','I='+bam,'O='+outbam,'METRICS_FILE='+metrics_file,'READ_NAME_REGEX=null','ASSUME_SORTED=true','VALIDATION_STRINGENCY=LENIENT']
	success = subprocess.call(args,stdout=log,stderr=log)

	if not success:
		return outbam
	else:
		f.prRed('Error in Marking of duplicates. Check log file.')
		exit(1)

def IndelRealigner(path,ram,bam,reference,mills,target,log,workdir):

	#print("- Indel realignment")
	outbam = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1] + ['IR'] +['bam'])
	intervals = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1] + ['IndelRealigner'] +['intervals'])

	#args = [path,'RealignerTargetCreator','-R',reference,'-I', bam,'-o',intervals,'-known',mills,'-L',target]

	args = ['java','-Xmx'+ram,'-jar',path,'-T','RealignerTargetCreator','-R',reference,'-I', bam,'-o',intervals,'-known',mills,'-L',target]
	
	success = subprocess.call(args,stdout=log,stderr=log)
	if not success:
		pass
	else:
		f.prRed('Error in target creation for indel realignment. Check log file.')
		exit(1)

	args = ['java','-Xmx'+ram,'-jar',path,'-T','IndelRealigner','-R',reference,'-I', bam,'-targetIntervals',intervals,'-known',mills,'-o',outbam]
	success = subprocess.call(args,stdout=log,stderr=log)

	if not success:
		return outbam
	else:
		f.prRed('Error in indel realignment. Check log file.')
		exit(1)

def BaseRecalibrator(path,ram,bam,reference,dbsnp,mills,target,log,workdir):

	#print("- Base quality score recalibration")
	outbam = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1] + ['BQSR'] +['bam'])
	table = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1] + ['BQSR'] +['table'])
	args = ['java','-Xmx'+ram,'-jar',path,'-T','BaseRecalibrator','-R',reference,'-I', bam,'-o',table,'-knownSites',dbsnp,'-knownSites',mills,'-L',target]
	#args = [path,'BaseRecalibrator','-R',reference,'-I', bam,'-o',table,'-knownSites',dbsnp,'-knownSites',mills,'-L',target]
	success = subprocess.call(args,stdout=log,stderr=log)

	if not success:
		pass
	else:
		f.prRed('Error in table creation for Base quality score recalibration. Check log file.')
		exit(1)

	args = ['java','-Xmx'+ram,'-jar',path,'-T','PrintReads','-R',reference,'-I', bam,'-BQSR',table,'-L',target,'-o',outbam]
	success = subprocess.call(args,stdout=log,stderr=log)

	if not success:
		return outbam
	else:
		f.prRed('Error in base quality score recalibration. Check log file.')
		exit(1)



###----------------------------------------------------------------------------------------------VARIANTCALLING-------------------------------------------------------------------------------------

def mpileup(name,reference,gbam,sbam,bam_list,target,log,workdir):

	start_time = datetime.datetime.now()
	#print("- Mpileup")
	mpileup = workdir +'/'+name+'.mpileup'
	open_mpileup = open(mpileup,'w')

	args = ['samtools','mpileup','-B','-q 1','-d','50000','-L','50000','-f',reference]
	if sbam != None:
		args += [sbam]
	if gbam != None:
		args += [gbam]
	if bam_list != None:
		args += ['-b',bam_list]
	
	if target != None:
		args += ['-l',target]

	success = subprocess.call(args,stdout=open_mpileup,stderr=log)
	#success= 0
	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	open_mpileup.close()
	if not success:
		print("- Mpileup: %d min, %d sec" % elapsed_time)
		return mpileup
	else:
		f.prRed('Error in Mpileup. Check log file.')
		exit(1)


#:::::::::::::::::::::::::::::::::::::::::::::::::::::::::::     GATK     ::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::

def HaplotypeCaller(path,ram,bam,sample_name,reference,target,log,workdir):

	start_time = datetime.datetime.now()
	gvcf = workdir + '/'+ sample_name + '.g.vcf'
	
	version = check_version_gatk(path,log)
	if version.startswith('3'):
		args = ['java','-Xmx'+ram,'-jar',path,'-T','HaplotypeCaller','-R',reference,'-I', bam,'-o',gvcf,'-ERC','GVCF','--doNotRunPhysicalPhasing']
	elif version.startswith('4.1'):
		args = [path,'HaplotypeCaller','-R',reference,'-I', bam,'-O',gvcf,'-ERC','GVCF']
		args += ['--max-reads-per-alignment-start','0']
		args += ['--enable-all-annotations']
		#args += ['-G','AS_StandardAnnotation']

	if target != None:
		args += ['-L',target]

	#
	success = subprocess.call(args,stdout=log,stderr=log)
	#success = 0
	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	
	if not success:
		print("- HaplotypeCaller "  +sample_name + ": %d min, %d sec" % elapsed_time)
		return gvcf
	else:
		f.prRed('Error in gvcf generation: '+ sample_name+'. Check log file.')
		exit(1)

def GenotypeGVCFs(path,ram,gvcf,name,reference,target,log,workdir):

	start_time = datetime.datetime.now()

	version = check_version_gatk(path,log)
	#print('version',version)
	#print("- GenotypeGVCFs")
	vcf = workdir + '/' + name + '.GATK.vcf'
	if version.startswith('3'):
		args = ['java','-Xmx'+ram,'-jar',path,'-T','GenotypeGVCFs','-R',reference,'-V:VCF', gvcf,'-o',vcf]
	elif version.startswith('4.1'):
		args = [path,'GenotypeGVCFs','-R',reference,'-V', gvcf,'-O',vcf]
		#args += ['-G','AS_StandardAnnotation']
		args += ['--java-options','-Xmx'+ ram]
		#args += ['--enable-all-annotations']
		args += ['-A','StrandBiasBySample']
	if target != None:
		args += ['-L',target]

	success = subprocess.call(args,stdout=log,stderr=log)
	#success =0
	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	
	if not success:
		print("- GenotypeGVCFs: %d min, %d sec" % elapsed_time)
		return vcf
	else:
		f.prRed('Error in GenotypeGVCFs. Check log file.')
		exit(1)


def Mutect2(path,ram,gbam,sbam,gsample_name,ssample_name,reference,target,log,workdir):

	start_time = datetime.datetime.now()
	vcf = workdir + '/' + ssample_name + '.Mutect.vcf'
	filtered_vcf = workdir + '/' + ssample_name + '.Mutect.filter.vcf'

	version = check_version_gatk(path,log)
	
	if version.startswith('3'):
		if gbam == None:
			args = ['java','-Xmx'+ram,'-jar',path,'-T','MuTect2','-R',reference,
				'-I:tumor',sbam,'-o',vcf]
		else:
			args = ['java','-Xmx'+ram,'-jar',path,'-T','MuTect2','-R',reference,
				'-I:tumor',sbam, '-I:normal',gbam,'-o',vcf]

	if version.startswith('4.1'):
		if gbam == None:
			args = [path,'Mutect2','-R',reference,
				'-I',sbam,'-tumor',ssample_name,'--max-reads-per-alignment-start','0','-O',vcf]
		else:
			args = [path,'Mutect2','-R',reference,
				'-I',sbam, '-tumor',ssample_name, '-I',gbam,
				'-normal',gsample_name,'--max-reads-per-alignment-start','0','-O',vcf]

	if target != None:
		args += ['-L',target]

	#success = subprocess.call(args)
	success = subprocess.call(args,stdout=log,stderr=log)

	args = [path,'FilterMutectCalls','-R',reference,'-V',vcf,'-O',filtered_vcf]

	success = subprocess.call(args,stdout=log,stderr=log)

	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	
	if not success:
		print("- "+ ssample_name + ": %d min, %d sec" % elapsed_time)
		return filtered_vcf
	else:
		f.prRed('Error in Mutect2. Check log file.')
		exit(1)

def CombineGVCFs(path,ram,gvcf_array,sample_name,reference,target,log,workdir):

	start_time = datetime.datetime.now()
	gvcf_cohort = workdir + '/'+ sample_name + '.g.vcf'
	
	version = check_version_gatk(path,log)
	if version.startswith('3'):
		args = ['java','-Xmx'+ram,'-jar',path,'-T','CombineGVCFs','-R',reference,'-o',gvcf_cohort]
	elif version.startswith('4.1'):
		args = [path,'CombineGVCFs','-R',reference,'-O',gvcf_cohort]
		#args += ['-G','AS_StandardAnnotation']

		args += ['--enable-all-annotations']

	if target != None:
		args += ['-L',target]

	for gvcf in gvcf_array:
		args += ['-V',gvcf]

	success = subprocess.call(args,stdout=log,stderr=log)
	#success = 0
	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	
	if not success:
		#print("- CombineGVCFs "  +sample_name + ": %d min, %d sec" % elapsed_time)
		return gvcf_cohort
	else:
		f.prRed('Error in CombineGVCFs: '+ sample_name+'. Check log file.')
		exit(1)


def check_version_gatk(path,log):
	if path.endswith('.jar'):
		args = ['java','-jar',path,'--version']
	else:
		args = [path,'--version']
	success= subprocess.Popen(args,stdout=subprocess.PIPE,stderr=log)

	bversion = success.stdout.read()
	version = str(bversion, 'utf-8').split('\n')[0].split(' ')[-1]
	#print('\n\n\nVERSIONE:',version,'\n\n\n')
	
	if version.startswith('v'):
		version=version[1:]
	return version

#:::::::::::::::::::::::::::::::::::::::::::::::::::::::::::     FREEBAYES     :::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::

def FreeBayes(path,name,bam,bam_list,reference,target,log,workdir):

	start_time = datetime.datetime.now()
	#print("- FreeBayes"
	vcf = workdir + '/' + name + '.FreeBayes.vcf'
	if bam == None:
		args = [path,'-f',reference,'-L', bam_list,'-v',vcf,
			'--pooled-discrete','--pooled-continuous','--genotype-qualities','--report-genotype-likelihood-max','--allele-balance-priors-off']	

	else:
		args = [path,'-f',reference,'-b', bam,'-v',vcf,
			'--pooled-discrete','--pooled-continuous','--genotype-qualities','--report-genotype-likelihood-max','--allele-balance-priors-off']


	args += ['-m','1']
	#args += ['-q','0']
	#args += ['-R','0']
	#args += ['-Y','0']
	#args += ['-Q','1']
	args += ['-F','0.1']
	args += ['-C','5']

	if target != None:
		args += ['-t',target]

	success = subprocess.call(args,stdout=log,stderr=log)
	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	
	if not success:
		print("- FreeBayes: %d min, %d sec" % elapsed_time)
		return vcf
	else:
		f.prRed('Error in FreeBayes calling. Check log file.')
		exit(1)

#:::::::::::::::::::::::::::::::::::::::::::::::::::::::::::     VARSCAN     :::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::

def VarScan_mpileup2snp(path,ram,mpileup,sample_list,reference,target,log,workdir):

	start_time = datetime.datetime.now()
	#print("- VarScan mpileup2snp")
	vcf = workdir + '/' + '.'.join(mpileup.split('/')[-1].split('.')[:-1] + ['VarScan.snp.vcf'])
	open_vcf = open(vcf,'w')
	args = ['java','-Xmx'+ram,'-jar',path,'mpileup2snp',mpileup,'--vcf-sample-list',sample_list,'--output-vcf','1','--strand-filter 0']

	if target != None:
		args += ['-L',target]

	#if filters == '0':
	args += ['--min-coverage','1','--min-var-freq','0.01','--min-reads2','1','--min-avg-qual','0','--p-value','0.95']

	success = subprocess.call(args,stdout=open_vcf,stderr=log)
	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	open_vcf.close()
	
	if not success:
		print("- VarScan mpileup2snp: %d min, %d sec" % elapsed_time)
		return vcf
	else:
		f.prRed('Error in VarScan mpileup2snp. Check log file.')
		exit(1)

def VarScan_mpileup2indel(path,ram,mpileup,sample_list,reference,target,log,workdir):

	start_time = datetime.datetime.now()
	#print("- VarScan mpileup2indel")
	vcf = workdir + '/' + '.'.join(mpileup.split('/')[-1].split('.')[:-1] + ['VarScan.indel.vcf'])
	open_vcf = open(vcf,'w')
	args = ['java','-Xmx'+ram,'-jar',path,'mpileup2indel',mpileup,'--vcf-sample-list',sample_list,'--output-vcf','1','--strand-filter 0']

	if target != None:
		args += ['-L',target]

	#if filters == '0':
	args += ['--min-coverage','1','--min-var-freq','0.01','--min-reads2','1','--min-avg-qual','0','--p-value','0.95']

	success = subprocess.call(args,stdout=open_vcf,stderr=log)
	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	open_vcf.close()
	
	if not success:
		print("- VarScan mpileup2indel: %d min, %d sec" % elapsed_time)
		return vcf
	else:
		f.prRed('Error in VarScan mpileup2indel. Check log file.')
		exit(1)

def VarScan_somatic(path,ram,gpileup,spileup,reference,target,log,workdir):

	start_time = datetime.datetime.now()
	#print("- VarScan mpileup2indel")
	vcf = workdir + '/' + '.'.join(spileup.split('/')[-1].split('.')[:-1] + ['VarScan'])
	snp = vcf+'.snp.vcf'
	indel = vcf+'.indel.vcf'
	#args = ['java','-Xmx'+ram,'-jar',path,'somatic',gpileup,spileup,vcf,'--output-vcf','1','--strand-filter 0','--mpileup 1']
	args = ['java','-Xmx'+ram,'-jar',path,'somatic',spileup,vcf,'--output-vcf','1','--strand-filter', '0','--mpileup', '1']

	if target != None:
		args += ['-L',target]

	#if filters == '0':
		#args += ['--min-coverage','1','--min-var-freq','0.01','--min-reads2','1','--min-avg-qual','0','--p-value','0.95']

	success = subprocess.call(args,stdout=log,stderr=log)
	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	
	if not success:
		print("- VarScan mpileup2somatic: %d min, %d sec" % elapsed_time)
		return snp,indel
		#return vcf
	else:
		f.prRed('Error in VarScan mpileup2somatic. Check log file.')
		exit(1)

def Concat_VarScan_vcf(snp,indel,log):

	concat = '.'.join(snp.split('.')[:-2] + ['merge.vcf'])
	open_concat = open(concat,'w')
	sort = '.'.join(concat.split('.')[:-1] + ['sort.vcf'])
	open_sort = open(sort,'w')

	args = ['bgzip',snp]
	status = subprocess.call('bgzip -f '+snp, shell=True)
	status = subprocess.call('tabix -f '+snp+'.gz', shell=True)

	status = subprocess.call('bgzip -f '+indel, shell=True)
	status = subprocess.call('tabix -f '+indel+'.gz', shell=True)
	
	args = ['vcf-concat',snp+'.gz',indel+'.gz']
	success1 = subprocess.call(args,stdout=open_concat,stderr=log)

	args = ['vcf-sort','-c',concat]
	success2 = subprocess.call(args,stdout=open_sort,stderr=log)

	if success1 or success2:
		f.prRed('Error in VarScan concat. Check log file.')
		exit(1)
	else:
		return sort

#:::::::::::::::::::::::::::::::::::::::::::::::::::::::::::     VARDICT     ::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::


def Vardict(path,path_script,threads,gbam,sbam,gsample_name,ssample_name,reference,target,log,workdir):

	start_time = datetime.datetime.now()
	#print("- VarDict")	

	if sbam == None:
		vcf =  workdir + '/' + gsample_name + '.Vardict.vcf'
		open_vcf = open(vcf,'w')
		args = [path,'-G',reference,'-f','0.05','-N',gsample_name,'-b',sbam]
		if threads != "":
			args += ['-th',threads]
		if target != None:
			args += ['-z','1','-F','0','-c','1','-S','2','-E','3','-g','4',target]
		vardictprocs= subprocess.Popen(args,stdout=subprocess.PIPE,stderr=log)
		tsargs = [path_script+'/teststrandbias.R']
		tsprocs = subprocess.Popen(stargs,stdin=vardictprocs.stdout,stdout=subprocess.PIPE,stderr=log)
		v2vargs = [path_script+'/var2vcf_valid.pl','-f','0.05','-N',gsample_name]
		success = subprocess.call(v2vargs,stdin=tsprocs.stdout,stdout=open_vcf,stderr=log)

	else:
		vcf =  workdir + '/' + ssample_name + '.Vardict.vcf'
		open_vcf = open(vcf,'w')
		args = [path,'-G',reference,'-f','0.01','-N',ssample_name,'-b','"'+sbam+'|'+gbam+'"']
		if threads != "":
			args += ['-th',threads]
		if target != None:
			args += ['-z','1','-F','0','-c','1','-S','2','-E','3','-g','4',target]
		vardictprocs= subprocess.Popen(args,stdout=subprocess.PIPE,stderr=log)
		stargs = [path_script+'/testsomatic.R']
		tsprocs = subprocess.Popen(stargs,stdin=vardictprocs.stdout,stdout=subprocess.PIPE,stderr=log)
		v2vargs = [path_script+'/var2vcf_somatic.pl','-f', '0.01','-N',ssample_name+'|'+gsample_name]
		success = subprocess.call(v2vargs,stdin=tsprocs.stdout,stdout=open_vcf,stderr=log)


	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	open_vcf.close()

	if not success:
		print("- VarDict: %d min, %d sec" % elapsed_time)
		return vcf
	else:
		f.prRed('Error in VarDict. Check log file.')
		exit(1)


###------------------------------------------------------------------------------------------COPY NUMBER CALLING------------------------------------------------------------------------------------------


#:::::::::::::::::::::::::::::::::::::::::::::::::::::::::::     GATK     :::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::

def GATK_CollectReadCounts(path,ram,bam,sample_name,target_list,log,workdir):
	
	success = False
	version = check_version_gatk(path,log)
	hdf5 = workdir + '/' +sample_name +'.hdf5'
	if version.startswith('4.1'):
		args = [path, 'CollectReadCounts', '-I', bam, '-L', target_list, '--interval-merging-rule', 'OVERLAPPING_ONLY', '-O', hdf5]
		success = subprocess.call(args,stdout=log,stderr=log)
		subprocess.call(['/bin/bash', '-i', '-c', "conda deactivate"])
	if not success:
		#print("- Estraction: %d min, %d sec" % elapsed_time)
		return hdf5
	else:
		f.prRed('Error in CNV calling. Check log file.')
		exit(1)

def GATK_DetermineGermlineContigPloidy(path,ram,hdf5,sample_name,ploidy_model,log,workdir):

	success = False
	out_dir = workdir + '/' + sample_name
	version = check_version_gatk(path,log)
	if version.startswith('4.1'):
		

		args = ['/bin/bash', '-c', "source ~/miniconda2/bin/activate gatk", '&&']
		
		args = [path, 'DetermineGermlineContigPloidy','--output-prefix', sample_name, '--output', out_dir]
		
		if isinstance(hdf5, list):
			for sample_hdf5, sample, index in hdf5: 
				args += ['--input', sample_hdf5]
		else:
			args =+ ['--input', hdf5]

		if os.path.isdir(ploidy_model):
			args +=	['--model', ploidy_model]
		else:
			args +=	['--contig-ploidy-priors', ploidy_model]

		success = subprocess.call(args,stdout=log,stderr=log)

	if not success:
		#print("- Estraction: %d min, %d sec" % elapsed_time)
		return out_dir
	else:
		f.prRed('Error in CNV calling. Check log file.')
		exit(1)

def GATK_GermlineCNVCaller(path,ram,hdf5,sample_name,sample_ploidy,calls_model,log,workdir):

	success = False
	version = check_version_gatk(path,log)
	if version.startswith('4.1'):

		args = ['/bin/bash', '-c', "source ~/miniconda2/bin/activate gatk", '&&']
		args = [path, 'GermlineCNVCaller', '--contig-ploidy-calls', sample_ploidy + '/'+ sample_name + '-calls', '--output', workdir, '--output-prefix', sample_name]
		
		if isinstance(hdf5, list):
			for sample_hdf5, sample, index in hdf5: 
				args += ['--input', sample_hdf5]
		else:
			args =+ ['--input', hdf5]
		
		if calls_model == "":
			args += ['--run-mode', 'COHORT']
			args += ['--p-alt', '0.00001']
		else:
			args += ['--run-mode', 'CASE', '--model', calls_model]
			args += ['--p-alt', '0.001']
		#args += ['--annotated-intervals', '/media/jarvis/HD1/gatk_CNV_data/TRUSIGHCANCER/20191122/trusight_cancer_manifest_a.annotated.tsv']
	
		success = subprocess.call(args,stdout=log,stderr=log)

	calls = workdir + '/' + sample_name + '-calls'
	model = workdir + '/' + sample_name + '-model'

	if not success:
		#print("- Estraction: %d min, %d sec" % elapsed_time)
		return calls, model
	else:
		f.prRed('Error in CNV calling. Check log file.')
		exit(1)

def GATK_PostprocessGermlineCNVCalls(path,ram,sample_name,index,sample_calls,sample_ploidy,calls_model,log,workdir):


	intervals_vcf = workdir + '/' + sample_name + '.CNV.vcf'
	segments_vcf = workdir + '/' + sample_name + '.segments.CNV.vcf'

	name = sample_ploidy.split('/')[-1]
	if calls_model.split('-')[-1] == 'calls':
		calls_model = '-'.join(calls_model.split('-')[:-1] +['model'])

	success = False
	version = check_version_gatk(path,log)
	if version.startswith('4.1'):

		args = ['/bin/bash', '-c', "source ~/miniconda2/bin/activate gatk", '&&']
		args = [path, 'PostprocessGermlineCNVCalls', '--calls-shard-path', sample_calls, '--model-shard-path', calls_model, '--contig-ploidy-calls', sample_ploidy + '/'+ name + '-calls',
			'--autosomal-ref-copy-number', '2', '--output-genotyped-intervals', intervals_vcf, '--output-genotyped-segments', segments_vcf]

		if index is None:
			args += ['--sample-index', '0']
		else:
			args += ['--sample-index', str(index)]

		success = subprocess.call(args,stdout=log,stderr=log)

	if not success:
		print("-GATK: " + sample_name)
		return intervals_vcf, segments_vcf
	else:
		f.prRed('Error in CNV calling. Check log file.')
		exit(1)

#:::::::::::::::::::::::::::::::::::::::::::::::::::::::::::     DECON     :::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::

def Decon_ReadInBams(path,bam_list,sample_name,target_bed,reference,log,workdir):
	
	out = workdir + '/' + sample_name

	args = ['Rscript', './ReadInBams.R', '--bams', bam_list, '--bed', target_bed, '--fasta', reference, '--out', out]

	success = subprocess.call(args,stdout=log,stderr=log)
	rdata = out + '.RData'
	#success = False
	if not success:
		#print("- Estraction: %d min, %d sec" % elapsed_time)
		return rdata
	else:
		f.prRed('Error in DECON CNV calling. Check log file.')
		exit(1)

def Decon_IdentifyFailures(path,rdata,sample_name,reference,log,workdir):
	
	out = workdir + '/' + sample_name + '.IdentifyFailures'

	args = ['Rscript', './IdentifyFailures.R', '--Rdata', rdata, '--mincorr', '0.97', '--mincov', '50', '--custom', 'fALSE','--out', out]
	success = subprocess.call(args,stdout=log,stderr=log)

def Decon_makeCNVcalls(path,rdata,sample_name,reference,log,workdir):

	out = workdir + '/' + sample_name + '.DECON.CNV'
	
	args = ['Rscript', './makeCNVcalls.R', '--Rdata', rdata, '--transProb', '0.01', '--out', out]

	success = subprocess.call(args,stdout=log,stderr=log)
	calls = out + '_all.txt'
	#success = False
	if not success:
		#print("- Estraction: %d min, %d sec" % elapsed_time)
		return calls
	else:
		f.prRed('Error in DECON CNV calling. Check log file.')
		exit(1)

###------------------------------------------------------------------------------------------FILTERING------------------------------------------------------------------------------------------

def HardFilter(path,ram,vcf,sample_name,reference,target,log,workdir):

	start_time = datetime.datetime.now()
	vcf_filtered = workdir + '/' + '.'.join(vcf.split('/')[-1].split('.')[:-1] + ['FILTER.vcf'])

	version = check_version_gatk(path,log)
	if version.startswith('3'):
		args = ['java','-Xmx'+ram,'-jar',path,'-T','VariantFiltration','-V',vcf,'-R',reference,'-o',vcf_filtered]
	elif version.startswith('4.1'):
		args = [path,'VariantFiltration','-R',reference,'-V',vcf,'-O',vcf_filtered]

	if 'FreeBayes' in vcf:
		pass
		#args += ['--filter-name','Low-AD','--filter-expression',"AO < 20" ]
		#args += ['--filter-name','Low-MapQual','--filter-expression',"MQM < 40.0"]
	else:
		#args += ['--filter-name','Low-Qual','--filter-expression',"QD < 2.0"]
		#args += ['--filter-name','High-FS','--filter-expression',"FS > 60.0"]
		#args += ['--filter-name','High-SOR','--filter-expression',"SOR > 3.0"]
		#args += ['--filter-name','Low-MapQual','--filter-expression',"MQ < 40.0"]
		args += ['--filter-name','LOW-MQMQRS','--filter-expression',"MQRankSum < -2.5"]
		args += ['--filter-name','HIGH-RPOS','--filter-expression',"ReadPosRankSum < -8.0 || ReadPosRankSum > 8.0 "]

	success = subprocess.call(args,stdout=log,stderr=log)
	#success = 0
	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	
	if not success:
		#print("- CombineGVCFs "  +sample_name + ": %d min, %d sec" % elapsed_time)
		return vcf_filtered
	else:
		f.prRed('Error in HardFiltering: '+ sample_name+'. Check log file.')
		exit(1)
###------------------------------------------------------------------------------------------FEATURES EXTRACTION--------------------------------------------------------------------------------

def merge_vcf(path,name,gatk,freebayes,varscan,log,workdir):

	merge_vcf = workdir + '/' + name + '.merge.vcf'
	args = ['python2',path,'-g',gatk,'-f',freebayes,'-o',merge_vcf]
	if varscan:
		args += ['-v',varscan]
	success = subprocess.call(args,stdout=log,stderr=log)

	if not success:
		return merge_vcf
	else:
		f.prRed('Error in Vcf merging. Check log file.')
		exit(1)

def merge_vcfs(path,name,gatk,freebayes,varscan,log,workdir):

	merge_vcf = workdir + '/' + name + '.merge.vcf'
	args = ['python',path,'-o',merge_vcf]

	if gatk != None:
		args += ['-g',gatk]
	if freebayes != None:
		args += ['-f',freebayes]
	if varscan != None:
		args += ['-v',varscan]
		
	success = subprocess.call(args,stdout=log,stderr=log)

	if not success:
		return merge_vcf
	else:
		f.prRed('Error in Vcf merging. Check log file.')
		exit(1)
		
def features_extractor(path,outpath,gatk,freebayes,varscan,merge,features_list,gvcf_path,design,log,workdir):
	start_time = datetime.datetime.now()
	args = ['python2',path,'--listaFeatures',features_list,'--gvcf_path',gvcf_path,'-o',outpath]
	tsvfile = outpath+'/tsv.list'

	if merge != None:
		args += ['--merge',merge]
	if gatk != None:
		args += ['-g',gatk]
	if freebayes != None:
		args += ['-f',freebayes]
	if varscan != None:
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


def features_extractor_somatic(path,outpath,mutect,vardict,varscan,gname,sname,features_list,design,log,workdir):
	start_time = datetime.datetime.now()
	args = ['python2',path,'--listaFeatures',features_list,'-o',outpath]
	tsvfile = outpath+'.tsv'
	vcffile = outpath+'.vcf'

	args += ['-g',mutect,'-f',vardict,'-v',varscan]

	args += ['-n',gname,'-t',sname]

	if design == "Amplicon":
		args += ['-a']

	success = subprocess.call(args,stdout=log,stderr=log)
	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)

	if not success:
		#print("- Estraction: %d min, %d sec" % elapsed_time)
		return tsvfile,vcffile
	else:
		f.prRed('Error in features extraction. Check log file.')
		exit(1)

def features_extractor_somatic_MUTECT2(path,outpath,mutect,sname,features_list,design,log,workdir):
	start_time = datetime.datetime.now()
	args = ['python2',path,'--listaFeatures',features_list,'-o',outpath]
	tsvfile = outpath+'.tsv'
	vcffile = outpath+'.vcf'

	args += ['-g',mutect]

	args += ['-t',sname]

	if design == "Amplicon":
		args += ['-a']

	success = subprocess.call(args,stdout=log,stderr=log)
	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)

	if not success:
		#print("- Estraction: %d min, %d sec" % elapsed_time)
		return tsvfile,mutect
	else:
		f.prRed('Error in features extraction. Check log file.')
		exit(1)

def iEVA(path,vcf,reference,bam_list,log,workdir):

	ieva_vcf = workdir + '/' + '.'.join(vcf.split('/')[-1].split('.')[:-1] + ['iEVA.vcf'])
	
	args = ['python2',path,'--input',vcf,'--reference',reference,'--list',bam_list,'--outfile',ieva_vcf]

	args+=["--SimpleRepeat","--SimpleRepeatLength","--PseudoNucleotidesComposition","--RepeatMasker",
		"--gcContent","--VariantClass","--StrandBiasReads","--UnMappedReads","--MappingQualityZero",
		"--NotPrimaryAlignment","--SupplementaryAlignment","--NotPairedReads","--NotProperPairedReads",
		"--AlignmentScore","--NumberTotalDupReads","--NumberReadDupRef","--NumberReadDupAlt","--DuplicateReference",
		"--DuplicateAlternate","--DeltaDuplicate","--iEvaDepth","--iAlleleDepth","--ReadRef","--ReadAlt",
		"--MeanRefQscore","--MeanAltQscore","--TotalDPUnfilter","--NumberClippedReadsRef","--NumberClippedReadsAlt",
		"--ClippedReadsRef","--ClippedReadsAlt"]

	success = subprocess.call(args,stdout=log,stderr=log)

	if not success:
		return ieva_vcf
	else:
		f.prRed('Error in iEVA annotation. Check log file.')
		exit(1)

def VariantAnnotator(path,vcf,reference,bam,target,log,workdir):

	start_time = datetime.datetime.now()
	
	out_vcf = workdir + '/' + '.'.join(vcf.split('/')[-1].split('.')[:-1] + ['VA.vcf'])
	
	version = check_version_gatk(path,log)
	if version.startswith('3'):
		args = ['java','-Xmx'+ram,'-jar',path,'-T','VariantAnnotator','-R',reference,'-o',out_vcf]
	elif version.startswith('4.1'):
		args = [path,'VariantAnnotator','-R',reference,'-O',out_vcf]
		args += ['-V', vcf, '-I', bam]
		#args += ['-G','AS_StandardAnnotation']
		#args += ['--enable-all-annotations']
		#args += ['-G','StandardAnnotation']
		#args += ['-A', 'TandemRepeat']

	if target != None:
		args += ['-L',target]
	print(' '.join(args))
	success = subprocess.call(args,stdout=log,stderr=log)
	#success = 0
	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	
	if not success:
		#print("- CombineGVCFs "  +sample_name + ": %d min, %d sec" % elapsed_time)
		return out_vcf
	else:
		f.prRed('Error in VariantAnnotator: '+ vcf+'. Check log file.')
		exit(1)


def SelectVariants(path,vcf,reference,sample_name,log,workdir):

	start_time = datetime.datetime.now()
	out_vcf = workdir + '/' + sample_name+ '.GATK.vcf'
	
	version = check_version_gatk(path,log)
	if version.startswith('3'):
		args = ['java','-Xmx'+ram,'-jar',path,'-T','SelectVariants','-R',reference,'-o',out_vcf]
	elif version.startswith('4.1'):
		args = [path,'SelectVariants','-R',reference,'-O',out_vcf,'--keep-original-ac']
		args += ['-V', vcf]
		args += ['--sample-name',sample_name]

	success = subprocess.call(args,stdout=log,stderr=log)
	#success = 0
	elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	
	if not success:
		#print("- CombineGVCFs "  +sample_name + ": %d min, %d sec" % elapsed_time)
		return out_vcf
	else:
		f.prRed('Error in SelectVariants: '+ vcf +'. Check log file.')
		exit(1)

###----------------------------------------------------------------------------------------------ANNOTATION-------------------------------------------------------------------------------------

def Vep(path,fork,name,reference,transcript_list,vep_af,vep_plugins,vcf,log,workdir):
	vep_vcf = workdir + '/' + name + '.VEP.vcf'
	
	args = [path,'-i',vcf,'-o',vep_vcf,'--species','homo_sapiens','--assembly','GRCh37','--force_overwrite','--no_stats',
		'--cache','--offline','--fasta',reference,'--merged',
		'--sift','b','--polyphen','b','--numbers','--vcf_info_field','ANN',
		'--hgvs','--transcript_version','--symbol','--canonical',
		'--check_existing','--vcf','--fork',fork,'--use_given_ref']

	if vep_af != "":
		for v in vep_af.split(','):
			args += [v]
	if vep_plugins['list'] != '':	
		args += add_vep_plugins(vep_plugins)	

	if transcript_list == None:
		args += ['--pick']
	if transcript_list == "most_severe":
		args += ['--most_severe']
	

	#print(' '.join(args))
	success = subprocess.call(args,stdout=log,stderr=log)

	if not success:
		print("- VEP: " + name)
		return vep_vcf
	else:
		f.prRed('Error in VEP annotation. Check log file.' + log)
		exit(1)

def add_vep_plugins(vep_plugins):
	args = []
	plugins = vep_plugins['list'].split(',')
	for plugin in plugins:
		pl_args = plugin
		if vep_plugins[plugin]['path'] != "":
			pl_args += ',' + vep_plugins[plugin]['path']
		if vep_plugins[plugin]['files'] != "":
			pl_args += ',' + vep_plugins[plugin]['files']
		if vep_plugins[plugin]['fields'] != "":	
			pl_args += ',' + vep_plugins[plugin]['fields']

		args += ['--plugin',pl_args]
	return args


def add_Annotation(path,name,vcf,tsv,tag_list,transcript_list,log,workdir):

	annotated_tsv = workdir + '/' + name + '.tsv'
	
	args = ['python2',path,'--vcf',vcf,'--tsv',tsv,'-o',annotated_tsv,'--tag_list',tag_list,'--trs_list',transcript_list]
	success = subprocess.call(args,stdout=log,stderr=log)

	if success:
		f.prRed('Error in tsv annotation. Check log file.')
		exit(1)
	return annotated_tsv

#:::::::::::::::::::::::::::::::::::::::::::::::::::::::::::     TOOLS     :::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::

def header_fix(path,vcf,variantcaller,log):
	fix_vcf = '.'.join(vcf.split('.')[:-1] + ['hfix.vcf'])
	open_fix_vcf = open(fix_vcf,'w')
	args = ['python2',path,'-v',variantcaller,'-f',vcf]
	success = subprocess.call(args,stdout=open_fix_vcf,stderr=log)
	open_fix_vcf.close()
	if not success:
		return fix_vcf
	else:
		f.prRed('Error in Vcf fix. Check log file.')
		exit(1)

def vcf_norm(path,vcf,reference,log):
	norm_vcf = '.'.join(vcf.split('.')[:-1] + ['norm.vcf'])
	args = [path,'norm','-D','-m','-both','-f',reference,vcf,'-o',norm_vcf]
	success = subprocess.call(args,stdout=log,stderr=log)
	
	if not success:
		return norm_vcf
	else:
		f.prRed('Error in Vcf normalization. Check log file.')
		exit(1)


def LeftAlignAndTrimVariants(path,vcf,reference,log):
	norm_vcf = '.'.join(vcf.split('.')[:-1] + ['norm.vcf'])
	args = [path,'LeftAlignAndTrimVariants','-R',reference,'-V',vcf,'-O',norm_vcf,'--split-multi-allelics']
	success = subprocess.call(args,stdout=log,stderr=log)
	if not success:
		return norm_vcf
	else:
		f.prRed('Error in Vcf LeftAlignAndTrimVariants normalization. Check log file.')
		exit(1)

def Index_vcf(path,vcf,log):
	args = [path,'IndexFeatureFile','-F',vcf]
	success = subprocess.call(args,stdout=log,stderr=log)
	if not success:
		pass
	else:
		f.prRed('Error in Index Vcf. Check log file.')
		exit(1)

def Sort_vcf(path,vcf,log,workdir):
	sorted_vcf = '.'.join(vcf.split('.')[:-1] + ['sort.vcf'])
	open_sorted_vcf = open(sorted_vcf,'w')
	args = ['vcf-sort',vcf]
	success = subprocess.call(args,stdout=open_sorted_vcf,stderr=log)

	open_sorted_vcf.close()

	args = ['bgzip',sorted_vcf,'-f','>',sorted_vcf+'.gz']
	success = subprocess.call(args,stdout=log,stderr=log)

	args = ['tabix','-p','vcf',sorted_vcf+'.gz']
	success = subprocess.call(args,stdout=log,stderr=log)

	if not success:
		return sorted_vcf+'.gz'
	else:
		f.prRed('Error in Vcf Sorting. Check log file.')
		exit(1)


def Split_by_sample(path,vcf,sample_name,log,workdir):

	out = workdir + '/' + sample_name +'.vcf'

	args = ['python',path,'--vcf',vcf, '--samplename',sample_name, '--out',out]
	success = subprocess.call(args,stdout=log,stderr=log)
	if not success:
		return out
	else:
		f.prRed('Error in split Vcf by sample name. Check log file.')
		exit(1)



def Make_CNV_report(infofile, cnv_vcf_array, log, workdir):

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
			with open(infofile) as ifile:
				for iline in ifile:
					if line.startswith('Gene_name'):
						continue
					else:
						Gene_name, Gene_ID, Transcript_ID, RefSeq_ID, Strand, Chromosome, Exon_region_start, Exon_region_end, Exon_rank_in_transcript = iline.rstrip().split('\t')
						
						if Chromosome == chrom and int(Exon_region_start) - 100 <= int(start) and int(Exon_region_end) + 100  >= int(end):
							gene = Gene_name 
							exon = Exon_rank_in_transcript
			ifile.close()
			repo.write('\t'.join(rawcnv+[gene,exon]) +'\n')
	repo.close()

	return report


