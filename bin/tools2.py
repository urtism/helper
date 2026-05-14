import subprocess
import os
import functions2 as f
import datetime

class Tool(object):
	"""docstring for Tool"""
	def __init__(self):
		super(Tool, self).__init__()
		
	def init_tool(self, path, threads, ram, args):
		self.args = args
		self.path = path
		self.threads = threads
		self.ram = ram

class Fastqc(Tool):
	def __init__(self):
		super(Tool, self).__init__()

	def fastq_diagnosis(self, sample, fastq1, fastq2, log, workdir):
		
		outdir = workdir + '/' + sample
		f.makedirs(outdir)
		
		args = ['perl', self.path, fastq1, '-o', outdir]

		if fastq2 != '': args += [fastq2]		
		if self.threads != '': args += ['-t', self.threads]
		if self.args != '': args += self.args
		
		#success = subprocess.call(args)

		success = subprocess.call(args, stdout=log, stderr=log)
		if not success:
			return outdir
		else:
			f.prRed('Error in Alignment. Check log file.')
			exit(1)

	def parallel_fastq_diagnosis(self, fastq_list, log, workdir):
		
		start_time = datetime.datetime.now()
		cmds_list = []
		log_list = []
		for sample, fastq1, fastq2 in fastq_list:
			args = []
			
			outdir = workdir + '/' + sample
			f.makedirs(outdir)
			samplelog = workdir +'/'+sample+'.log'
			log_list += [samplelog]
			write_log = open(samplelog,'a+')	
			args = ['perl', self.path, fastq1, '-o', outdir]

			if fastq2 != '': args += [fastq2]		
			if self.threads != '': args += ['-t', self.threads]
			if self.args != '': args += self.args
			
			write_log.write('\n')
			cmds_list +=  [[args, write_log]]

		procs_list = [subprocess.Popen(cmd, stdout=log_file, stderr=log_file) for cmd, log_file in cmds_list]
		for proc in procs_list:
			proc.wait()
		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		print("-parallel Fastq QC: %d min, %d sec" % elapsed_time)
		
	def bam_diagnosis(self, sample, bam, log, workdir):
		
		outdir = workdir + '/' + sample
		f.makedirs(outdir)
		
		args = ['perl', self.path, bam, '-o', outdir]
	
		if self.threads != '': args += ['-t', self.threads]
		if self.args != '': args += self.args
		
		success = subprocess.call(args, stdout=log, stderr=log)

		#success = subprocess.call(args, stdout=log, stderr=log)
		if not success:
			return outdir
		else:
			f.prRed('Error in Alignment. Check log file.')
			exit(1)

	def parallel_bam_diagnosis(self, bam_list, log, workdir):
		
		start_time = datetime.datetime.now()
		cmds_list = []
		log_list = []
		for sample, bam in bam_list:
			args = []
			outdir = workdir + '/' + sample
			f.makedirs(outdir)
			samplelog = workdir +'/'+sample+'.log'
			log_list += [samplelog]
			write_log = open(samplelog,'a+')
		
			args = ['perl', self.path, bam, '-o', outdir]
	
			if self.threads != '': args += ['-t', self.threads]
			if self.args != '': args += self.args

			write_log.write('\n')
			cmds_list +=  [[args, write_log]]
		
		procs_list = [subprocess.Popen(cmd, stdout=log_file, stderr=log_file) for cmd, log_file in cmds_list]
		for proc in procs_list:
			proc.wait()
		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		print("-parallel BAM QC: %d min, %d sec" % elapsed_time)

	def sam_diagnosis(self, sample, sam, log, workdir):
		
		outdir = workdir + '/' + sample
		f.makedirs(outdir)
		
		args = ['perl', self.path, sam, '-o', outdir]
	
		if self.threads != '': args += ['-t', self.threads]
		if self.args != '': args += self.args
		
		success = subprocess.call(args)

		#success = subprocess.call(args, stdout=log, stderr=log)
		if not success:
			return outdir
		else:
			f.prRed('Error in Alignment. Check log file.')
			exit(1)

class Bwa(Tool):
	"""docstring for Bwa"""
	def __init__(self):
		super(Tool, self).__init__()

	def align_fastq(self, algorithm, sample, fastq1, fastq2, reference, log, workdir):

		sam = workdir +'/'+sample+'.sam'
		write_sam = open(sam,'w+')
		args = [self.path]
		
		if algorithm != '': args += [algorithm]
		args += [reference, fastq1]
		if fastq2 != '': args += [fastq2]		
		if self.threads != '': args += ['-t', self.threads]
		if self.args != []: args += self.args

		success = subprocess.call(args, stdout=write_sam, stderr=log)
		#return success
		if not success:
			return sam
		else:
			print(' '.join(args))
			f.prRed('Error in Alignment. Check log file.')
			exit(1)

	def parallel_align_fastq(self, algorithm, fastq_list, reference, log, workdir):
		start_time = datetime.datetime.now()
		cmds_list = []
		sam_list = []
		log_list = []
		for sample, fastq1, fastq2 in fastq_list:
			args = []
			
			sam = workdir +'/'+sample+'.sam'
			write_sam = open(sam,'w+')
			samplelog = workdir +'/'+sample+'.log'
			log_list += [samplelog]
			write_log = open(samplelog,'a+')
			sam_list += [[sample,sam]]
			write_log.write('\n')

			args = [self.path]
			if algorithm != '': args += [algorithm]
			args += [reference, fastq1]
			if fastq2 != '': args += [fastq2]		
			if self.threads != '': args += ['-t', self.threads]
			if self.args != []: args += self.args

			cmds_list +=  [[args, write_sam, write_log]]
		procs_list = [subprocess.Popen(cmd, stdout=sam_file, stderr=log_file) for cmd, sam_file, log_file in cmds_list]
		for proc in procs_list:
			proc.wait()

		for cmd, sam_file, log_file in cmds_list:
			pass

		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		print("-parallel_align_fastq: %d min, %d sec" % elapsed_time)
		return sam_list
		# if not success:
		# 	print(sam_list)
		# 	return sam_list

		# else:
		# 	f.prRed('Error in Alignment. Check log file.')
		# 	exit(1)

class Bowtie2(Tool):
	"""docstring for Bowtie2"""
	def __init__(self):
		super(Tool, self).__init__()

	def	align_fastq(self, sample, fastq1, fastq2, reference, log, workdir):

		sam = workdir +'/'+sample+'.sam'
		reference_index = '.'.join(reference.split('.')[:-1])
		args = ['perl',self.path]
		
		args += ['-x',reference_index, '-1', fastq1]
		if fastq2 != '': args += ['-2',fastq2]		
		if self.threads != '': args += ['--threads', self.threads]
		if self.args != []: args += self.args
		args += ['-S',sam]
		success = subprocess.call(args, stdout=log, stderr=log)
		#return success
		if not success:
			return sam
		else:
			print(' '.join(args))
			f.prRed('Error in Alignment. Check log file.')
			exit(1)
		
class Novoalign(Tool):
	"""docstring for Novoalign"""
	def __init__(self):
		super(Tool, self).__init__()

class Cutadapt(Tool):
	"""docstring for Cutadapt"""
	def __init__(self):
		super(Tool, self).__init__()

	def checksubstring(self,sub, list):
			for s in list:
				if sub in s:
					return True
			return False
	
	def Trim_Adapters(self, fastq1, fastq2, adapter1, adapter2, log, workdir):

		args = [self.path]
		outfastq1 =  workdir +'/'+ '.'.join([fastq1.split('/')[-1].split('.')[0]] + ['trim'] + fastq1.split('/')[-1].split('.')[1:])
		outfastq2 = ''
		outfiles = ['-o',outfastq1]
		if fastq2 != '':
			outfastq2 =  workdir +'/'+ '.'.join([fastq2.split('/')[-1].split('.')[0]] + ['trim'] + fastq2.split('/')[-1].split('.')[1:])
			outfiles += ['-p',outfastq2]

		
		if self.args != '': 
			if '-g' in self.args or self.checksubstring('--front=', self.args) \
				or '-b' in self.args or self.checksubstring('--anywhere=', self.args) \
				or'-a' in self.args or self.checksubstring('--adapter=', self.args):
					args += self.args
			else:
				args += ['-a', adapter1]
				if adapter2 != '':
					args += ['-A', adapter2]
		else:
			args += ['-a', adapter1]
			if adapter2 != '':
				args += ['-A', adapter2]

		args += outfiles
		args += [fastq1]
		if fastq2 != '':
			args += [fastq2]

		success = subprocess.call(args,stdout=log,stderr=log)
		if not success:
			return outfastq1,outfastq2
		else:
			f.prRed('Error in Trimming of adapters. Check log file.')
			print(' '.join(args))
			exit(1)


	def parallel_Trim_Adapters(self, fastq_list, adapter1, adapter2, log, workdir):

		start_time = datetime.datetime.now()
		cmds_list = []
		trimmed_list = []
		log_list = []
		for sample, fastq1, fastq2 in fastq_list:
			args = []
			samplelog = workdir +'/'+sample+'.log'
			log_list += [samplelog]
			write_log = open(samplelog,'a+')
			
			outfastq1 =  workdir +'/'+ '.'.join([fastq1.split('/')[-1].split('.')[0]] + ['trim'] + fastq1.split('/')[-1].split('.')[1:])
			outfiles = ['-o',outfastq1]
			outfastq2 = ''
			
			if fastq2 != '':
				outfastq2 =  workdir +'/'+ '.'.join([fastq2.split('/')[-1].split('.')[0]] + ['trim'] + fastq2.split('/')[-1].split('.')[1:])
				outfiles += ['-p',outfastq2]
			args = [self.path]
			if self.args != '': 
				if '-g' in self.args or self.checksubstring('--front=', self.args) \
				or '-b' in self.args or self.checksubstring('--anywhere=', self.args) \
				or'-a' in self.args or self.checksubstring('--adapter=', self.args):
					args += self.args
				else:
					args += ['-a', adapter1]
					if adapter2 != '':
						args += ['-A', adapter2]
			else:
				args += ['-a', adapter1]
				if adapter2 != '':
					args += ['-A', adapter2]

			args += outfiles
			args += [fastq1]
			if fastq2 != '':
				args += [fastq2]

			trimmed_list += [[sample, outfastq1, outfastq2]]
			write_log.write('\n')
			cmds_list +=  [[args, write_log]]

		procs_list = [subprocess.Popen(cmd, stdout=log_file, stderr=log_file) for cmd, log_file in cmds_list]
		for proc in procs_list:
			proc.wait()

		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		print("-parallel_Trim_Adapters: %d min, %d sec" % elapsed_time)
		return trimmed_list


	def Fastq_fiter_Qual(self, fastq1, fastq2, qual, log, workdir):
		args = [self.path]

		outfastq1 =  workdir +'/'+ '.'.join([fastq1.split('/')[-1].split('.')[0]] + ['qual'] + fastq1.split('/')[-1].split('.')[1:])
		outfastq2 = ''
		outfiles = ['-o',outfastq1]
		if fastq2 != '':
			outfastq2 =  workdir +'/'+ '.'.join([fastq2.split('/')[-1].split('.')[0]] + ['qual'] + fastq2.split('/')[-1].split('.')[1:])
			outfiles += ['-p',outfastq2]

		if qual != '':
			args += ['-q', qual]
		args += outfiles
		args += [fastq1]
		if fastq2 != '':
			args += [fastq2]

		success = subprocess.call(args,stdout=log,stderr=log)

		if not success:
			return outfastq1,outfastq2
		else:
			f.prRed('Error in fastq filtering. Check log file.')
			exit(1)


	def parallel_Fastq_fiter_Qual(self, fastq_list, qual, log, workdir):
		
		start_time = datetime.datetime.now()
		cmds_list = []
		trimmed_list = []
		log_list = []
		for sample, fastq1, fastq2 in fastq_list:
			args = []
			samplelog = workdir +'/'+sample+'.log'
			log_list += [samplelog]
			write_log = open(samplelog,'a+')


			outfastq1 =  workdir +'/'+ '.'.join([fastq1.split('/')[-1].split('.')[0]] + ['qual'] + fastq1.split('/')[-1].split('.')[1:])
			outfastq2 = ''
			outfiles = ['-o',outfastq1]
			if fastq2 != '':
				outfastq2 =  workdir +'/'+ '.'.join([fastq2.split('/')[-1].split('.')[0]] + ['qual'] + fastq2.split('/')[-1].split('.')[1:])
				outfiles += ['-p',outfastq2]

			
			args = [self.path]
			if qual != '':
				args += ['-q', qual]
			args += outfiles
			args += [fastq1]
			if fastq2 != '':
				args += [fastq2]

			trimmed_list += [[sample, outfastq1, outfastq2]]
			write_log.write('\n')
			cmds_list +=  [[args, write_log]]

			procs_list = [subprocess.Popen(cmd, stdout=log_file, stderr=log_file) for cmd, log_file in cmds_list]
		for proc in procs_list:
			proc.wait()

		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		print("-parallel_Fastq_fiter_Qual: %d min, %d sec" % elapsed_time)
		return trimmed_list
	
	def Fastq_fiter_Len(self, fastq1, fastq2, maxlen, minlen, log, workdir):
		args = [self.path]

		outfastq1 =  workdir +'/'+ '.'.join([fastq1.split('/')[-1].split('.')[0]] + ['len'] + fastq1.split('/')[-1].split('.')[1:])
		outfastq2 = ''
		outfiles = ['-o',outfastq1]
		if fastq2 != '':
			outfastq2 =  workdir +'/'+ '.'.join([fastq2.split('/')[-1].split('.')[0]] + ['len'] + fastq2.split('/')[-1].split('.')[1:])
			outfiles += ['-p',outfastq2]

		if maxlen != '':
			args += ['-M', maxlen]

		if minlen != '':
			args += ['-m', minlen]
		if self.args != '': args += self.args

		args += outfiles
		args += [fastq1]
		if fastq2 != '':
			args += [fastq2]
		success = subprocess.call(args,stdout=log,stderr=log)

		if not success:
			return outfastq1,outfastq2
		else:
			f.prRed('Error in fastq filtering. Check log file.')
			exit(1)

	def parallel_Fastq_fiter_Len(self, fastq_list, maxlen, minlen, log, workdir):
		
		start_time = datetime.datetime.now()
		cmds_list = []
		trimmed_list = []
		log_list = []
		for sample, fastq1, fastq2 in fastq_list:
			args = []
			samplelog = workdir +'/'+sample+'.log'
			log_list += [samplelog]
			write_log = open(samplelog,'a+')
			
			outfastq1 =  workdir +'/'+ '.'.join([fastq1.split('/')[-1].split('.')[0]] + ['len'] + fastq1.split('/')[-1].split('.')[1:])
			outfastq2 = ''
			outfiles = ['-o',outfastq1]
			if fastq2 != '':
				outfastq2 =  workdir +'/'+ '.'.join([fastq2.split('/')[-1].split('.')[0]] + ['len'] + fastq2.split('/')[-1].split('.')[1:])
				outfiles += ['-p',outfastq2]

			args = [self.path]
			if maxlen != '':
				args += ['-M', maxlen]

			if minlen != '':
				args += ['-m', minlen]
			if self.args != '': args += self.args

			args += outfiles
			args += [fastq1]
			if fastq2 != '':
				args += [fastq2]
			trimmed_list += [[sample, outfastq1, outfastq2]]
			write_log.write('\n')
			cmds_list +=  [[args, write_log]]

			procs_list = [subprocess.Popen(cmd, stdout=log_file, stderr=log_file) for cmd, log_file in cmds_list]
		for proc in procs_list:
			proc.wait()

		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		print("-parallel_Fastq_fiter_Len: %d min, %d sec" % elapsed_time)
		return trimmed_list

class AGeNT(Tool):
	"""docstring for Novoalign"""
	def __init__(self):
		super(Tool, self).__init__()
	
	def LocatIt(self, sam, fqI2, target_bed,log, workdir):
		#print("- Merging haloplex molecular barcodes")
		bam = workdir +'/'+ '.'.join(sam.split('/')[-1].split('.')[:-1] + ['UMI'] + sam.split('/')[-1].split('.')[-1])
		args = ['java']

		if os.path.isdir(self.path):
			for subdir, dirs, files in os.walk(rootdir):
				for file in files:
					if 'LOCATIT' in file.upper():
						path = rootdir + '/' + file
		else:
			path = self.path

		if self.ram != '': args += ['-Xmx'+self.ram]
		args += ['-jar', path]		
		if target_bed != None: args += ['-b', target_bed]
		
		args += ['-U','-i']
		if self.args != '': args += self.args
		if sam.endswith('.bam'): args+= ['-IB','-OB']
		if sam.endswith('.sam'): args+= ['-IS','-OS']

		args += ['-o', bam, sam, fqI2]
		
		success = subprocess.call(args,stdout=log,stderr=log)

		if not success:
			return bam
		else:
			f.prRed('Error in merging molucular barcodes. Check log file.')
			exit(1)

	def Trimmer(self, fq1, fq2, log, workdir):

		trimmed_fq1 = workdir +'/'+ '.'.join(fq1.split('/')[-1].split('.')[:-1] + ['trm','fastq'])
		trimmed_fq2 = workdir +'/'+ '.'.join(fq2.split('/')[-1].split('.')[:-1] + ['trm','fastq'])
		mbc = ''

		if os.path.isdir(self.path):
			for subdir, dirs, files in os.walk(self.path):
				for file in files:
					if 'TRIMMER' in file.upper():
						path = self.path + '/' + file
		else:
			path = self.path

		args = ['java']
		if self.ram != '': args += ['-Xmx'+self.ram]
		args += ['-jar',self.path]		
		args += ['-fq1',fq1,'-fq2',fq2]
		args += ['-out_loc', workdir]
		if self.args != []: args += self.args

		success = subprocess.call(args,stdout=log,stderr=log)

		for file in os.listdir(workdir):
			if file.startswith(fq1.split('/')[-1]):
				trimmed_fq1 = workdir +'/'+file
			if file.startswith(fq2.split('/')[-1]):
				trimmed_fq2 = workdir +'/'+file

		if not success:
			return trimmed_fq1, trimmed_fq2
		else:
			f.prRed('Error in Trimming of adapters. Check log file.')
			exit(1)

class Picard(Tool):
	"""docstring for Picard"""
	def __init__(self):
		super(Tool, self).__init__()

	def SamFormatConverter(self, sample_name, sam, log, workdir):
		bam= workdir +'/'+ sample_name + '.bam'
		
		args = ['java']
		if self.ram != '': args += ['-Xmx'+self.ram]
		args += ['-jar',self.path]		
		args += ['SamFormatConverter', 'I='+sam, 'O='+bam]
		if self.args != []: args += self.args
		success = subprocess.call(args, stdout=log, stderr=log)
		if not success:
			return bam
		else:
			f.prRed('Error in Sam to Bam converter. Check log file.')
			exit(1)


	def parallel_SamFormatConverter(self, sample_name, sam_list, log, workdir):
		
		start_time = datetime.datetime.now()
		cmds_list = []
		bam_list = []
		log_list = []
		for sample, sam in sam_list:
			args = []
			
			bam = workdir +'/'+sample+'.bam'
			samplelog = workdir +'/'+sample+'.log'
			log_list += [samplelog]
			write_log = open(samplelog,'a+')
			bam_list += [[sample,bam]]
			write_log.write('\n')

			args = ['java']
			if self.ram != '': args += ['-Xmx'+ self.ram]
			args += ['-jar', self.path, 'SamFormatConverter', 'I='+sam, 'O='+bam]
			if self.args != []: args += self.args
			cmds_list +=  [[args, write_log]]
		

		procs_list = [subprocess.Popen(cmd, stdout=log_file, stderr=log_file) for cmd, log_file in cmds_list]
		for proc in procs_list:
			proc.wait()

		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		print("-parallel_SamFormatConverter: %d min, %d sec" % elapsed_time)
		return bam_list


	def SortSam(self, sample_name, bam, log, workdir):
		sort = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1])+'.sort.bam'

		args = ['java']
		if self.ram != '': args += ['-Xmx'+ self.ram]
		args += [ '-jar', self.path, 'SortSam', 'I='+bam, 'O='+sort]
		if self.args != []: args += self.args

		#print(args)

		success = subprocess.call(args, stdout=log, stderr=log)
		if not success:
			return sort
		else:
			f.prRed('Error in Bam Sorting. Check log file.')
			exit(1)

	def parallel_SortSam(self, sample_name, bam_list, log, workdir):
		start_time = datetime.datetime.now()
		cmds_list = []
		sort_list = []
		log_list = []
		for sample, bam in bam_list:
			sort = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1])+'.sort.bam'
			samplelog = workdir +'/'+sample+'.log'
			log_list += [samplelog]
			write_log = open(samplelog,'a+')
			sort_list += [[sample,sort]]
			write_log.write('\n')


			args = ['java']
			if self.ram != '': args += ['-Xmx'+ self.ram]
			args += [ '-jar', self.path, 'SortSam', 'I='+bam, 'O='+sort]
			if self.args != []: args += self.args

			cmds_list +=  [[args, write_log]]

		procs_list = [subprocess.Popen(cmd, stdout=log_file, stderr=log_file) for cmd, log_file in cmds_list]
		for proc in procs_list:
			proc.wait()

		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		print("-parallel_SortSam: %d min, %d sec" % elapsed_time)
		return sort_list

	def BuildBamIndex(self, bam, log, workdir):
		bai = bam +'.bai'
		if os.path.exists(bai):
			status = subprocess.call("rm " + bai , shell=True)
		
		args = ['java']
		if self.ram != '': args += ['-Xmx'+ self.ram]
		args += ['-jar', self.path, 'BuildBamIndex', 'I='+bam, 'O='+bai, 'VALIDATION_STRINGENCY=LENIENT']

		success = subprocess.call(args, stdout=log, stderr=log)
		if not success:
			pass
		else:
			f.prRed('Error in Bam Indexing. Check log file.')
			exit(1)

	def parallel_BuildBamIndex(self, bam_list, log, workdir):
		start_time = datetime.datetime.now()
		cmds_list = []
		bai_list = []
		log_list = []
		for sample, bam in bam_list:
			bai = bam +'.bai'
			samplelog = workdir +'/'+sample+'.log'
			log_list += [samplelog]
			write_log = open(samplelog,'a+')
			bai_list += [[sample,bai]]
			write_log.write('\n')
			#if os.path.exists(bai):
				#status = subprocess.call("rm " + bai , shell=True)
			
			args = ['java']
			if self.ram != '': args += ['-Xmx'+ self.ram]
			args += ['-jar', self.path, 'BuildBamIndex', 'I='+bam, 'O='+bai, 'VALIDATION_STRINGENCY=LENIENT']
			cmds_list +=  [[args, write_log]]

		procs_list = [subprocess.Popen(cmd, stdout=log_file, stderr=log_file) for cmd, log_file in cmds_list]

		for proc in procs_list:
			proc.wait()

		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		print("-parallel_BuildBamIndex: %d min, %d sec" % elapsed_time)
		#return bam_list

	def MarkDuplicates(self, sample_name, bam, log, workdir):
		outbam = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1] + ['Mark'] +['bam'])
		metrics_file = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1] + ['MarkMetrics'] +['txt'])
		
		args = ['java']
		if self.ram != '': args += ['-Xmx'+ self.ram]
		args += ['-jar', self.path, 'MarkDuplicates', 'I='+bam, 'O='+outbam, 'METRICS_FILE='+metrics_file]
		args += ['READ_NAME_REGEX=null','ASSUME_SORTED=true','VALIDATION_STRINGENCY=LENIENT']
		if self.args != []: args += self.args

		success = subprocess.call(args, stdout=log, stderr=log)
		if not success:
			return outbam
		else:
			f.prRed('Error in Marking of duplicates. Check log file.')
			exit(1)

	def parallel_MarkDuplicates(self, bam_list, log, workdir):

		start_time = datetime.datetime.now()
		cmds_list = []
		log_list = []
		out_list= []
		for sample, bam in bam_list:
			args = []
			samplelog = workdir +'/'+sample+'.log'
			log_list += [samplelog]
			write_log = open(samplelog,'a+')

			outbam = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1] + ['Mark'] +['bam'])
			metrics_file = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1] + ['MarkMetrics'] +['txt'])
			out_list += [[sample, outbam]]
		
			args = ['java']
			if self.ram != '': args += ['-Xmx'+ self.ram]
			args += ['-jar', self.path, 'MarkDuplicates', 'I='+bam, 'O='+outbam, 'METRICS_FILE='+metrics_file]
			args += ['READ_NAME_REGEX=null','ASSUME_SORTED=true','VALIDATION_STRINGENCY=LENIENT']
			if self.args != []: args += self.args

			write_log.write('\n')
			cmds_list +=  [[args, write_log]]
		
		procs_list = [subprocess.Popen(cmd, stdout=log_file, stderr=log_file) for cmd, log_file in cmds_list]
		for proc in procs_list:
			proc.wait()
		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		print("-parallel MarkDuplicates: %d min, %d sec" % elapsed_time)
		return out_list

	def AddOrReplaceReadGroups(self, sample_name, bam, panel_name, runID, log, workdir):
		outbam = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1] + ['RG'] +['bam'])
		args = ['java']
		if self.ram != '': args += ['-Xmx'+ self.ram]
		args += ['-jar', self.path, 'AddOrReplaceReadGroups',
			'I='+bam,
			'O='+outbam,
			'RGID='+sample_name,
			'RGPL=ILLUMINA',
			'RGSM='+sample_name,
			'RGLB='+panel_name,
			"RGPU="+runID,
			'VALIDATION_STRINGENCY=LENIENT']
		success = subprocess.call(args, stdout=log, stderr=log)

		if not success:
			return outbam
		else:
			f.prRed('Error in Adding or replacing Read groups. Check log file.')
			exit(1)

	def parallel_AddOrReplaceReadGroups(self, bam_list, panel_name, runID, log, workdir):
		
		start_time = datetime.datetime.now()
		cmds_list = []
		log_list = []
		out_list= []
		for sample, bam in bam_list:
			args = []
			samplelog = workdir +'/'+sample+'.log'
			log_list += [samplelog]
			write_log = open(samplelog,'a+')

			outbam = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1] + ['RG'] +['bam'])
			out_list += [[sample, outbam]]
			args = ['java']
			if self.ram != '': args += ['-Xmx'+ self.ram]
			args += ['-jar', self.path, 'AddOrReplaceReadGroups',
				'I='+bam,
				'O='+outbam,
				'RGID='+sample,
				'RGPL=ILLUMINA',
				'RGSM='+sample,
				'RGLB='+panel_name,
				"RGPU="+runID,
				'VALIDATION_STRINGENCY=LENIENT']

			write_log.write('\n')
			cmds_list +=  [[args, write_log]]
		
		procs_list = [subprocess.Popen(cmd, stdout=log_file, stderr=log_file) for cmd, log_file in cmds_list]
		for proc in procs_list:
			proc.wait()
		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		print("-parallel AddOrReplaceReadGroups: %d min, %d sec" % elapsed_time)
		return out_list
		
class GATK(Tool):
	"""docstring for GATK"""
	def __init__(self):
		super(Tool, self).__init__()
		self.tool_name = 'GATK'

class GATKv3(GATK):
	"""docstring for GATKv3"""
	def __init__(self):
		super(GATK, self).__init__()
		self.tool_name = 'GATKv3'

	def IndexFeatureFile(self, file, log, workdir):
		start_time = datetime.datetime.now()
		
		args = ['java']
		if self.ram != '': args += ['-Xmx' + self.ram]
		args += ['-jar', self.path, '-T','IndexFeatureFile', '-F', file]

		success = subprocess.call(args,stdout=log,stderr=log)

		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		
		if not success:
			#print("-Index created: " + vcf)
			pass
		else:
			f.prRed('Error in file indexing: Check log file.')
			exit(1)

	def IndelRealigner(self, bam, mills, target_list, reference_fasta, log, workdir):
		#print("- Indel realignment")
		outbam = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1] + ['IR'] +['bam'])
		intervals = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1] + ['IndelRealigner'] +['intervals'])

		args = ['java']
		if self.ram != '': args += ['-Xmx'+ self.ram]
		args += ['-jar',self.path,'-T','RealignerTargetCreator',
			'-R',reference_fasta,
			'-I', bam,
			'-o', intervals,
			'-L', target_list]
		if mills != '': args += ['-known', mills]
		if self.args != []: args += self.args
		success = subprocess.call(args, stdout=log, stderr=log)
		
		if success:
			f.prRed('Error in target creation for indel realignment. Check log file.')
			print(" ".join(args))
			exit(1)

		args = ['java']
		if self.ram != '': args += ['-Xmx'+ self.ram]
		args += ['-jar',self.path,'-T','IndelRealigner',
			'-R', reference_fasta,
			'-I', bam,
			'-targetIntervals', intervals,
			'-o', outbam]

		if mills != '': args += ['-known', mills]
		if self.args != []: args += self.args
		success = subprocess.call(args, stdout=log, stderr=log)

		if not success:
			return outbam
		else:
			
			f.prRed('Error in indel realignment. Check log file.')
			exit(1)

	def parallel_IndelRealigner(self, bam_list, mills, target_list, reference_fasta, log, workdir):

		start_time = datetime.datetime.now()
		cmds_list = []
		outbam_list = []
		int_list = []
		log_list = []
		for sample, bam in bam_list:
			args = []
			outbam = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1] + ['IR'] +['bam'])
			intervals = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1] + ['IndelRealigner'] +['intervals'])

			samplelog = workdir +'/'+sample+'.log'
			log_list += [samplelog]
			write_log = open(samplelog,'a+')
			int_list += [[sample,outbam,intervals,write_log]]
			write_log.write('\n')
		#print("- Indel realignment")
		
			args = ['java']
			if self.ram != '': args += ['-Xmx'+ self.ram]
			args += ['-jar',self.path,'-T','RealignerTargetCreator',
				'-R',reference_fasta,
				'-I', bam,
				'-o', intervals,
				'-L', target_list]
			if mills != '': args += ['-known', mills]
			if self.args != []: args += self.args

			cmds_list +=  [[args, write_log]]
		
		procs_list = [subprocess.Popen(cmd, stdout=log_file, stderr=log_file) for cmd, log_file in cmds_list]
		for proc in procs_list:
			proc.wait()

		cmds_list = []
		
		for sample,outbam,intervals,write_log in int_list:

			outbam_list += [[sample,outbam]]
			args = ['java']
			if self.ram != '': args += ['-Xmx'+ self.ram]
			args += ['-jar',self.path,'-T','IndelRealigner',
				'-R', reference_fasta,
				'-I', bam,
				'-targetIntervals', intervals,
				'-o', outbam]

			if mills != '': args += ['-known', mills]
			if self.args != []: args += self.args
			cmds_list +=  [[args, write_log]]
		
		procs_list = [subprocess.Popen(cmd, stdout=log_file, stderr=log_file) for cmd, log_file in cmds_list]
		for proc in procs_list:
			proc.wait()

		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		print("-parallel_IndelRealigner: %d min, %d sec" % elapsed_time)
		return outbam_list
		

	def BaseRecalibrator(self, bam, dbsnp, mills, target_list, reference_fasta, log, workdir):
		print("- Base quality score recalibration")
		outbam = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1] + ['BQSR'] +['bam'])
		table = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1] + ['BQSR'] +['table'])
		
		args = ['java']
		if self.ram != '': args += ['-Xmx'+ self.ram]
		args += ['-jar',self.path,'-T','BaseRecalibrator',
			'-R', reference_fasta,
			'-I', bam,
			'-L', target_list,
			'-o', table]
		if dbsnp != '': args += ['-knownSites', dbsnp]
		if mills != '': args += ['-knownSites', mills]
		if self.args != []: args += self.args
		success = subprocess.call(args, stdout=log, stderr=log)

		if success:
			f.prRed('Error in table creation for Base quality score recalibration. Check log file.')
			exit(1)

		args = ['java']
		if self.ram != '': args += ['-Xmx'+ self.ram]
		args += ['-jar',self.path,'-T','PrintReads',
			'-R', reference_fasta,
			'-I', bam,
			'-BQSR', table,
			'-L', target_list,
			'-o',outbam]
		if self.args != []: args += self.args
		success = subprocess.call(args, stdout=log, stderr=log)

		if not success:
			return outbam
		else:
			f.prRed('Error in base quality score recalibration. Check log file.')
			exit(1)

	def parallel_BaseRecalibrator(self, bam_list, dbsnp, mills, target_list, reference_fasta, log, workdir):
		#print("- Base quality score recalibration")
		start_time = datetime.datetime.now()
		cmds_list = []
		outbam_list = []
		int_list = []
		log_list = []

		for sample, bam in bam_list:
			args = []
			
			outbam = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1] + ['BQSR'] +['bam'])
			table = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1] + ['BQSR'] +['table'])

			samplelog = workdir +'/'+sample+'.log'
			log_list += [samplelog]
			write_log = open(samplelog,'a+')
			int_list += [[sample,outbam,table,write_log]]
			write_log.write('\n')

			args = ['java']
			if self.ram != '': args += ['-Xmx'+ self.ram]
			args += ['-jar',self.path,'-T','BaseRecalibrator',
				'-R', reference_fasta,
				'-I', bam,
				'-L', target_list,
				'-o', table]
			if dbsnp != '': args += ['-knownSites', dbsnp]
			if mills != '': args += ['-knownSites', mills]
			if self.args != []: args += self.args
			cmds_list +=  [[args, write_log]]
		
		procs_list = [subprocess.Popen(cmd, stdout=log_file, stderr=log_file) for cmd, log_file in cmds_list]
		for proc in procs_list:
			proc.wait()

		cmds_list = []
		
		for sample,outbam,table,write_log in int_list:

			outbam_list += [[sample,outbam]]

			args = ['java']
			if self.ram != '': args += ['-Xmx'+ self.ram]
			args += ['-jar',self.path,'-T','PrintReads',
				'-R', reference_fasta,
				'-I', bam,
				'-BQSR', table,
				'-L', target_list,
				'-o',outbam]

			if self.args != []: args += self.args
			cmds_list +=  [[args, write_log]]
		
		procs_list = [subprocess.Popen(cmd, stdout=log_file, stderr=log_file) for cmd, log_file in cmds_list]
		for proc in procs_list:
			proc.wait()

		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		print("-parallel_BaseRecalibrator: %d min, %d sec" % elapsed_time)
		return outbam_list

	def HaplotypeCaller(self, bam, sample_name, filters, target_list, reference_fasta, log, workdir):

		#start_time = datetime.datetime.now()

		gvcf = workdir + '/'+ sample_name + '.g.vcf'

		args = ['java']
		if self.ram != '': args += ['-Xmx'+ self.ram]
		args += ['-jar',self.path, '-T','HaplotypeCaller',
			'-R', reference_fasta,
			'-I', bam,
			'-o', gvcf,
			'-ERC','GVCF']

		if target_list != "":
			args += ['-L',target_list]

		if filters["min_base_quality_score"] != "" : args += ['--min-base-quality-score', filters["min_base_quality_score"]]
		if filters["min_alt_coverage"] != "" : args += ['--min_alt_coverage', filters["min_alt_coverage"]]
		if filters["min_alt_freq"] != "" : args += ['--min_alt_freq', filters["min_alt_freq"]]
		if filters["min_mapping_quality_score"] != "": args += ['--min_mapping_quality_score', filters["min_mapping_quality_score"]]

		if self.args != []: args += self.args
		success = subprocess.call(args, stdout=log, stderr=log)	
		#success = 0
		#elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		
		if not success:
			#print("- HaplotypeCaller "  +sample_name + ": %d min, %d sec" % elapsed_time)
			return gvcf
		else:
			f.prRed('Error in gvcf generation: '+ sample_name+'. Check log file.')
			exit(1)

	def parallel_HaplotypeCaller(self, bam_list, filters, target_list, reference_fasta, log, workdir):

		#start_time = datetime.datetime.now()
		start_time = datetime.datetime.now()
		cmds_list = []
		outbam_list = []
		gvcf_list = []
		log_list = []

		for sample, bam in bam_list:
			args = []

			samplelog = workdir +'/'+sample+'.log'
			log_list += [samplelog]
			write_log = open(samplelog,'a+')
			write_log.write('\n')

			vcf = workdir + '/'+ sample_name + '.' + self.tool_name + '.g.vcf'

			gvcf_list += [[sample,vcf]]
			
			args = ['java']
			if self.ram != '': args += ['-Xmx'+ self.ram]
			args += ['-jar',self.path, '-T','HaplotypeCaller',
				'-R', reference_fasta,
				'-I', bam,
				'-o', vcf,
				'-ERC','GVCF']

			if target_list != "":
				args += ['-L',target_list]

			if filters["min_base_quality_score"] != "" : args += ['--min-base-quality-score', filters["min_base_quality_score"]]
			if filters["min_alt_coverage"] != "" : args += ['--min_alt_coverage', filters["min_alt_coverage"]]
			if filters["min_alt_freq"] != "" : args += ['--min_alt_freq', filters["min_alt_freq"]]
			if filters["min_mapping_quality_score"] != "": args += ['--min_mapping_quality_score', filters["min_mapping_quality_score"]]

			if self.args != []: args += self.args
			cmds_list +=  [[args, write_log]]
		
		procs_list = [subprocess.Popen(cmd, stdout=log_file, stderr=log_file) for cmd, log_file in cmds_list]
		for proc in procs_list:
			proc.wait()

		return gvcf_list
		
	def GenotypeGVCFs(self, gvcf, sample_name, filters, target_list, reference_fasta, log, workdir):

		args = ['java']
		if self.ram != '': args += ['-Xmx'+ self.ram]
		args += ['-jar',self.path, '-T','GenotypeGVCFs',
			'-R', reference_fasta,
			'-V:VCF', gvcf,
			'-o', vcf]
			
		if target_list != "": args += ['-L', target_list]
		if self.threads != "": args += ['--native-pair-hmm-threads',self.threads]
		if self.ram != "": args += ['--java-options','-Xmx'+ ram]
		if self.args != []: args += self.args

		success = subprocess.call(args, stdout=log, stderr=log)
		#success =0
		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		
		if not success:
			print("- GenotypeGVCFs: %d min, %d sec" % elapsed_time)
			return vcf
		else:
			f.prRed('Error in GenotypeGVCFs. Check log file.')
			exit(1)

	def parallel_GenotypeGVCFs(self, gvcf_list, run_id, filters, target_list, reference_fasta, log, workdir):
		
		start_time = datetime.datetime.now()
		cmds_list = []
		outbam_list = []
		vcf_list = []
		log_list = []


		for sample, gvcf in gvcf_list:
			args = []
			vcf = workdir + '/' + sample + '.' + self.tool_name + '.vcf'

			samplelog = workdir +'/'+sample+'.log'
			log_list += [samplelog]
			write_log = open(samplelog,'a+')
			write_log.write('\n')

			vcf_list += [[sample,vcf]]
		
			args = ['java']
			if self.ram != '': args += ['-Xmx'+ self.ram]
			args += ['-jar',self.path, '-T','GenotypeGVCFs',
				'-R', reference_fasta,
				'-V:VCF', gvcf,
				'-o', vcf]

			if target_list != "": args += ['-L', target_list]
			if self.args != []: args += self.args
			cmds_list +=  [[args, write_log]]
		
		procs_list = [subprocess.Popen(cmd, stdout=log_file, stderr=log_file) for cmd, log_file in cmds_list]
		for proc in procs_list:
			proc.wait()

		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		print("-GenotypeGVCFs: %d min, %d sec" % elapsed_time)

		return vcf_list

	def MuTect2():
		#start_time = datetime.datetime.now()
		vcf = workdir + '/' + sample_name + '.Mutect.vcf'
		filtered_vcf = workdir + '/' + ssample_name + '.Mutect.filter.vcf'

		args = ['java']
		if self.ram != '': args += ['-Xmx'+ self.ram]
		args += ['-jar',self.path, '-T','MuTect2',
			'-R', reference_fasta,
			'-o', vcf,
			'-I:tumor', case_bam]

		if control_bam != "": args += ['-I:normal', control_bam]

		if target_list != "": args += ['-L', target_list]
		if self.threads != "": args += ['--native-pair-hmm-threads',self.threads]
		if self.ram != "": args += ['--java-options','-Xmx'+ ram]
		if self.args != []: args += self.args

		#success = subprocess.call(args)
		success = subprocess.call(args,stdout=log,stderr=log)

		args = [path,'FilterMutectCalls','-R',reference_fasta,'-V',vcf,'-O',filtered_vcf]

		success = subprocess.call(args,stdout=log,stderr=log)

		#elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		
		if not success:
			#print("- "+ ssample_name + ": %d min, %d sec" % elapsed_time)
			return filtered_vcf
		else:
			f.prRed('Error in Mutect2. Check log file.')
			exit(1)

	def CombineGVCFs(self, gvcf_array, sample_name, filters, target_list, reference_fasta, log, workdir):
		
		gvcf_cohort = workdir + '/'+ sample_name + '.g.vcf'
		
		args = ['java']
		if self.ram != '': args += ['-Xmx'+ self.ram]
		args += ['-jar',self.path, '-T','CombineGVCFs',
			'-R', reference_fasta,
			'-o', gvcf_cohort]
		
		#args += ['--enable-all-annotations']

		if target_list != "": args += ['-L', target_list]
		if self.threads != "": args += ['--native-pair-hmm-threads',self.threads]
		if self.ram != "": args += ['--java-options','-Xmx'+ ram]
		if self.args != []: args += self.args

		for gvcf in gvcf_array:
			args += ['-V',gvcf]

		success = subprocess.call(args,stdout=log,stderr=log)
		#success = 0
		#elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		
		if not success:
			#print("- CombineGVCFs "  +sample_name + ": %d min, %d sec" % elapsed_time)
			return gvcf_cohort
		else:
			f.prRed('Error in CombineGVCFs: '+ sample_name+'. Check log file.')
			exit(1)

	def SelectVariants():
		pass

	def VariantAnnotator():
		pass

	def VariantFiltration():
		pass

	def HardFilter(self, vcf, reference, target, log, workdir):

		start_time = datetime.datetime.now()
		vcf_filtered = workdir + '/' + '.'.join(vcf.split('/')[-1].split('.')[:-1] + ['hardfilter.vcf'])
		args = ['java']
		if self.ram != '': args += ['-Xmx'+ self.ram]
		args += ['-jar',path,'-T','VariantFiltration','-V',vcf,'-R',reference,'-o',vcf_filtered]

		args += ['--filter-name','Low-Qual','--filter-expression',"QD < 2.0"]
		args += ['--filter-name','High-FS','--filter-expression',"FS > 60.0"]
		args += ['--filter-name','High-SOR','--filter-expression',"SOR > 3.0"]
		args += ['--filter-name','Low-MapQual','--filter-expression',"MQ < 40.0"]
		args += ['--filter-name','LOW-MQMQRS','--filter-expression',"MQRankSum < -2.5"]
		args += ['--filter-name','HIGH-RPOS','--filter-expression',"ReadPosRankSum < -8.0 || ReadPosRankSum > 8.0 "]
		#args += ['--filter-name','HIGH-COV','--filter-expression',"DP > 2"]

		success = subprocess.call(args,stdout=log,stderr=log)
		#success = 0
		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		
		if not success:
			#print("- CombineGVCFs "  +sample_name + ": %d min, %d sec" % elapsed_time)
			return vcf_filtered
		else:
			f.prRed('Error in HardFiltering. Check log file.')
			exit(1)

class GATKv4(GATK):
	"""docstring for GATKv4"""
	def __init__(self):
		super(GATK, self).__init__()
		self.tool_name = 'GATKv4'

	def IndexFeatureFile(self, file, log, workdir):
		start_time = datetime.datetime.now()	
		#version = check_version_gatk(path,log)
		# if version.startswith('3'):
		# 	args = ['java','-Xmx'+ram,'-jar',path,'-T','IndexFeatureFile','-F', vcf]

		# elif version.startswith('4.1'):
		args = [self.path,'IndexFeatureFile','-F', file]

		
		success = subprocess.call(args,stdout=log,stderr=log)

		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		
		if not success:
			print("-Index created: " + vcf)
			pass
		else:
			f.prRed('Error in file indexing: Check log file.')
			exit(1)

	def BaseRecalibrator(self, bam, dbsnp, mills, target_list, reference_fasta, log, workdir):
		print("- Base quality score recalibration")
		outbam = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1] + ['BQSR'] +['bam'])
		table = workdir +'/'+ '.'.join(bam.split('/')[-1].split('.')[:-1] + ['BQSR'] +['table'])
		
		args = [self.path,'BaseRecalibrator',
			'-R', reference_fasta,
			'-I', bam,
			'-L', target_list,
			'-O', table]
		if dbsnp != '': args += ['--known-sites', dbsnp]
		if mills != '': args += ['--known-sites', mills]
		if self.args != []: args += self.args
		success = subprocess.call(args, stdout=log, stderr=log)

		if success:
			print(' '.join(args))
			f.prRed('Error in table creation for Base quality score recalibration. Check log file.')
			exit(1)

		args = [self.path,'ApplyBQSR',
			'-R', reference_fasta,
			'-I', bam,
			'--bqsr-recal-file', table,
			'-L', target_list,
			'-O',outbam]
		if self.args != []: args += self.args
		success = subprocess.call(args, stdout=log, stderr=log)

		if not success:
			return outbam
		else:
			print(' '.join(args))
			f.prRed('Error in base quality score recalibration. Check log file.')
			exit(1)

	def HaplotypeCaller(self, bam, sample_name, filters, target_list, reference_fasta, log, workdir):

		#start_time = datetime.datetime.now()
		gvcf = workdir + '/'+ sample_name + '.' + self.tool_name + '.g.vcf'
		
		args = [self.path, 'HaplotypeCaller',
			'-R', reference_fasta,
			'-I', bam,
			'-O', gvcf,
			'-bamout', workdir + '/'+ sample_name + '.' + self.tool_name + '.realign.bam',
			'-ERC','GVCF']

		if target_list != "": args += ['-L',target_list]
		if self.threads != "": args += ['--native-pair-hmm-threads',self.threads]
		if self.ram != "": args += ['--java-options','-Xmx'+ self.ram]
		

		if self.args != []: args += self.args
		success = subprocess.call(args, stdout=log, stderr=log)
		
		if not success:
			#print("- HaplotypeCaller "  +sample_name + ": %d min, %d sec" % elapsed_time)
			return gvcf
		else:
			f.prRed('Error in gvcf generation: '+ sample_name+'. Check log file.')
			exit(1)

	def parallel_HaplotypeCaller(self, bam_list, filters, target_list, reference_fasta, log, workdir):

		start_time = datetime.datetime.now()
		cmds_list = []
		outbam_list = []
		gvcf_list = []
		log_list = []

		for sample, bam in bam_list:
			args = []

			samplelog = workdir +'/'+sample+'.log'
			log_list += [samplelog]
			write_log = open(samplelog,'a+')
			write_log.write('\n')

			gvcf = workdir + '/'+ sample + '.g.vcf'		
			args = [self.path, 'HaplotypeCaller',
				'-R', reference_fasta,
				'-I', bam,
				'-O', gvcf,
				'-ERC','GVCF']

			if target_list != "": args += ['-L',target_list]
			if self.threads != "": args += ['--native-pair-hmm-threads',self.threads]
			if self.ram != "": args += ['--java-options','-Xmx'+ self.ram]
			if filters["min_base_quality_score"] != "" : args += ['--min-base-quality-score', filters["min_base_quality_score"]]
			if filters["min_alt_coverage"] != "" : args += ['--min-alt-coverage', filters["min_alt_coverage"]]
			if filters["min_mapping_quality_score"] != "" : args += ['--min-mapping-quality-score', filters["min_mapping_quality_score"]]
			if filters["min_alt_freq"] != "" : args += ['--min-alt-freq', filters["min_alt_freq"]]
			if self.args != []: args += self.args
			cmds_list +=  [[args, write_log]]
		
		procs_list = [subprocess.Popen(cmd, stdout=log_file, stderr=log_file) for cmd, log_file in cmds_list]
		for proc in procs_list:
			proc.wait()
		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		print("-HaplotypeCaller: %d min, %d sec" % elapsed_time)

		return gvcf_list

	def GenotypeGVCFs(self, gvcf, sample_name, filters, target_list, reference_fasta, log, workdir):
		#start_time = datetime.datetime.now()
		vcf = workdir + '/' + sample_name + '.' + self.tool_name + '.vcf'
		args = [self.path,'GenotypeGVCFs',
			'-R', reference_fasta,
			'-V', gvcf,
			'-O', vcf]
		args += ['-A','StrandBiasBySample']

		if target_list != "": args += ['-L', target_list]
		if self.ram != "": args += ['--java-options','-Xmx'+ self.ram]
		if self.args != []: args += self.args
		if filters["min_base_quality_score"] != "" : args += ['--min-base-quality-score', filters["min_base_quality_score"]]
		if filters["min_alt_freq"] != "" : args += ['--min_alt_freq', filters["min_alt_freq"]]
		if filters["min_mapping_quality_score"] != "": args += ['--min_mapping_quality_score', filters["min_mapping_quality_score"]]

		success = subprocess.call(args, stdout=log, stderr=log)
		#success =0
		#elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		
		if not success:
			#print("- GenotypeGVCFs: %d min, %d sec" % elapsed_time)
			return vcf
		else:
			f.prRed('Error in GenotypeGVCFs. Check log file.')
			exit(1)

	def parallel_GenotypeGVCFs(self, gvcf_list, runID, filters, target_list, reference_fasta, log, workdir):
		start_time = datetime.datetime.now()
		cmds_list = []
		outbam_list = []
		vcf_list = []
		log_list = []

		for sample, gvcf in gvcf_list:
			args = []
			vcf = workdir + '/' + sample + '.' + self.tool_name + '.vcf'

			samplelog = workdir +'/'+sample+'.log'
			log_list += [samplelog]
			write_log = open(samplelog,'a+')
			write_log.write('\n')

			vcf_list += [[sample,vcf]]
		
			args = [self.path,'GenotypeGVCFs',
			'-R', reference_fasta,
			'-V', gvcf,
			'-O', vcf]
			args += ['-A','StrandBiasBySample']
			if target_list != "": args += ['-L', target_list]
			if self.ram != "": args += ['--java-options','-Xmx'+ self.ram]
			if self.args != []: args += self.args
			cmds_list +=  [[args, write_log]]
		
		procs_list = [subprocess.Popen(cmd, stdout=log_file, stderr=log_file) for cmd, log_file in cmds_list]
		for proc in procs_list:
			proc.wait()

		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
			
		return vcf_list

	def Mutect2(self, case_bam, case_name, control_bam, control_name, filters, target_list, reference_fasta, log, workdir):
		
		#start_time = datetime.datetime.now()
		vcf = workdir + '/' + case_name + '.' + self.tool_name + '.vcf'
		filtered_vcf = workdir + '/' + case_name + '.' + self.tool_name + '.filter.vcf'

		args = [self.path,'Mutect2','-R',reference_fasta,
			'-I', case_bam, '-tumor',case_name,
			'-O', vcf]

		if control_bam != "": args += ['-I', control_bam, '-normal', control_name]
		if target_list != "": args += ['-L', target_list]
		if self.threads != "": args += ['--native-pair-hmm-threads',self.threads]
		if self.ram != "": args += ['--java-options','-Xmx'+ self.ram]
		if self.args != []: args += self.args

		#success = subprocess.call(args)
		success = subprocess.call(args,stdout=log,stderr=log)

		args = [self.path,'FilterMutectCalls','-R',reference_fasta,'-V',vcf,'-O',filtered_vcf]

		success = subprocess.call(args,stdout=log,stderr=log)

		#elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		
		if not success:
			#print("- "+ case_name + ' '+ control_name + ": %d min, %d sec" % elapsed_time)
			return filtered_vcf
		else:
			f.prRed('Error in Mutect2. Check log file.')
			exit(1)

	def CombineGVCFs(self, gvcf_array, sample_name, target_list, reference_fasta, log, workdir):

		gvcf_cohort = workdir + '/'+ sample_name + '.' + self.tool_name + '.g.vcf'	
		args = [self.path,'CombineGVCFs',
			'-R', reference_fasta,
			'-O', gvcf_cohort]
		
		args += ['--enable-all-annotations']
		if target_list != "": args += ['-L', target_list]

		for gvcf in gvcf_array:
			args += ['-V', gvcf]

		if self.ram != "": args += ['--java-options','-Xmx'+ self.ram]
		if self.args != []: args += self.args

		success = subprocess.call(args, stdout=log, stderr=log)
		#success = 0
		#elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		
		if not success:
			#print("- CombineGVCFs "  +sample_name + ": %d min, %d sec" % elapsed_time)
			return gvcf_cohort
		else:
			f.prRed('Error in CombineGVCFs: '+ sample_name+'. Check log file.')
			exit(1)

	def LeftAlignAndTrimVariants(self, vcf, reference_fasta, log, workdir):
		
		norm_vcf = '.'.join(vcf.split('.')[:-1] + ['norm.vcf'])
		args = [self.path,'LeftAlignAndTrimVariants',
			'-R', reference_fasta,
			'-V', vcf,
			'-O', norm_vcf,
			'--split-multi-allelics']
		success = subprocess.call(args,stdout=log,stderr=log)
		
		if not success:
			return norm_vcf
		else:
			f.prRed('Error in Vcf LeftAlignAndTrimVariants normalization. Check log file.')
			exit(1)

	def SelectVariants():
		pass

	def VariantAnnotator():
		pass

	def VariantFiltration(self, vcf, reference_fasta, log, workdir):
		
		vcf_filtered = workdir + '/' + '.'.join(vcf.split('/')[-1].split('.')[:-1] + ['filter.vcf'])
		
		args = [self.path,'VariantFiltration','-R',reference_fasta,'-V',vcf,'-O',vcf_filtered]

		args += ['--filter-name','Low-AD','--filter-expression',"AD < 20"]
		args += ['--filter-name','Low-AF','--filter-expression',"AF < 0.15"]
		args += ['--filter-name','Low-Qual','--filter-expression',"QD < 2.0"]
		args += ['--filter-name','High-FS','--filter-expression',"FS > 60.0"]
		args += ['--filter-name','High-SOR','--filter-expression',"SOR > 3.0"]
		args += ['--filter-name','Low-MapQual','--filter-expression',"MQ < 40.0"]
		args += ['--filter-name','LOW-MQRSum','--filter-expression',"MQRankSum < -2.5"]
		args += ['--filter-name','HIGH-RPOS','--filter-expression',"ReadPosRankSum < -8.0 || ReadPosRankSum > 8.0 "]

		success = subprocess.call(args,stdout=log,stderr=log)
		
		if not success:
			return vcf_filtered
		else:
			f.prRed('Error in HardFiltering. Check log file.')
			exit(1)

	def HardFilter(self, vcf, reference_fasta, log, workdir):

		vcf_filtered = workdir + '/' + '.'.join(vcf.split('/')[-1].split('.')[:-1] + ['hardfilter.vcf'])
		
		args = [self.path,'VariantFiltration','-R',reference_fasta,'-V',vcf,'-O',vcf_filtered]

		args += ['--filter-name','Low-Qual','--filter-expression',"QD < 2.0"]
		args += ['--filter-name','High-FS','--filter-expression',"FS > 60.0"]
		args += ['--filter-name','High-SOR','--filter-expression',"SOR > 3.0"]
		args += ['--filter-name','Low-MapQual','--filter-expression',"MQ < 40.0"]
		args += ['--filter-name','LOW-MQRSum','--filter-expression',"MQRankSum < -2.5"]
		args += ['--filter-name','HIGH-RPOS','--filter-expression',"ReadPosRankSum < -8.0 || ReadPosRankSum > 8.0 "]

		success = subprocess.call(args,stdout=log,stderr=log)
		#success = 0
		
		if not success:
			return vcf_filtered
		else:
			f.prRed('Error in HardFiltering. Check log file.')
			exit(1)

	def CollectReadCounts(self, bam, sample_name, target_list, log, workdir):

		hdf5 = workdir + '/' +sample_name +'.hdf5'
		
		args = [self.path, 'CollectReadCounts', '-I', bam, '-L', target_list, '--interval-merging-rule', 'OVERLAPPING_ONLY', '-O', hdf5]

		if self.ram != "": args += ['--java-options','-Xmx'+ self.ram]
		if self.args != []: args += self.args


		success = subprocess.call(args, stdout=log, stderr=log)

		if not success:
			#print("- Estraction: %d min, %d sec" % elapsed_time)
			return hdf5
		else:
			f.prRed('Error in CNV calling. Check log file.')
			exit(1)

	def DetermineGermlineContigPloidy(self, hdf5_list, sample_name, ploidy_model, log, workdir):

		out_dir = workdir + '/' + sample_name

		args = [self.path, 'DetermineGermlineContigPloidy','--output-prefix', sample_name, '--output', out_dir]

		if len(hdf5_list) > 1:
			for sample_hdf5, sample, index in hdf5_list: 
				args += ['--input', sample_hdf5]
		else:
			args += ['--input', hdf5_list[0][0]]

		if os.path.isdir(ploidy_model):
			args +=	['--model', ploidy_model]
		else:
			args +=	['--contig-ploidy-priors', ploidy_model]

		if self.ram != "": args += ['--java-options','-Xmx'+ self.ram]
		if self.args != []: args += self.args

		try:
			success = subprocess.call(args, stdout=log, stderr=log)
		except:
			print(args)
		if not success:
			#print("- Estraction: %d min, %d sec" % elapsed_time)
			return out_dir
		else:
			f.prRed('Error in CNV calling. Check log file.')
			exit(1)

	def GermlineCNVCaller(self, hdf5_list, sample_name, sample_ploidy, calls_model, log, workdir):

		args = [self.path, 'GermlineCNVCaller', '--contig-ploidy-calls', sample_ploidy + '/'+ sample_name + '-calls', '--output', workdir, '--output-prefix', sample_name]
		
		if len(hdf5_list) > 1:
			for sample_hdf5, sample, index in hdf5_list: 
				args += ['--input', sample_hdf5]
		else:
			args += ['--input', hdf5_list[0][0]]
		
		if calls_model == "" or  calls_model == "cohort":
			args += ['--run-mode', 'COHORT']
			args += ['--p-alt', '0.00001']
		else:
			args += ['--run-mode', 'CASE', '--model', calls_model]
			args += ['--p-alt', '0.01']
		#args += ['--annotated-intervals', '/media/jarvis/HD1/gatk_CNV_data/TRUSIGHCANCER/20191122/trusight_cancer_manifest_a.annotated.tsv']
	
		success = subprocess.call(args, stdout=log, stderr=log)

		calls = workdir + '/' + sample_name + '-calls'
		model = workdir + '/' + sample_name + '-model'

		if not success:
			#print("- Estraction: %d min, %d sec" % elapsed_time)
			return calls, model
		else:
			print(''.join(args))
			f.prRed('Error in CNV calling. Check log file.')
			exit(1)

	def PostprocessGermlineCNVCalls(self, sample_name, index, sample_calls, sample_ploidy, calls_model, log, workdir):

		intervals_vcf = workdir + '/' + sample_name + '.CNV.vcf'
		segments_vcf = workdir + '/' + sample_name + '.segments.CNV.vcf'
		copy_ratios_vcf = workdir + '/' + sample_name + '.denoised_copy_ratios.CNV.vcf'

		name = sample_ploidy.split('/')[-1]
		if calls_model.split('-')[-1] == 'calls':
			calls_model = '-'.join(calls_model.split('-')[:-1] +['model'])

		args = [self.path, 'PostprocessGermlineCNVCalls', 
			'--calls-shard-path', sample_calls, 
			'--model-shard-path', calls_model, 
			'--contig-ploidy-calls', sample_ploidy + '/'+ name + '-calls',
			'--autosomal-ref-copy-number', '2', 
			'--output-genotyped-intervals', intervals_vcf, 
			'--output-genotyped-segments', segments_vcf,
			'--output-denoised-copy-ratios', copy_ratios_vcf
			]

		if index is None:
			args += ['--sample-index', '0']
		else:
			args += ['--sample-index', str(index)]

		success = subprocess.call(args,stdout=log,stderr=log)

		if not success:
			print("-GATK: " + sample_name)
			return intervals_vcf, segments_vcf, copy_ratios_vcf
		else:
			f.prRed('Error in CNV calling. Check log file.')
			exit(1)

class Freebayes(Tool):
	"""docstring for GATK"""
	def __init__(self):
		super(Tool, self).__init__()
		self.tool_name = 'Freebayes'

	def variant_calling(self, bam, sample_name, filters, target_bed, reference_fasta, log, workdir):

		#start_time = datetime.datetime.now()
		#print("- FreeBayes"
		vcf = workdir + '/'+ sample_name + '.' + self.tool_name + '.vcf'	
		bam_list = workdir +  '/bam.list'

		print("- FreeBayes")
		args = [self.path,
			'-f', reference_fasta,
			'-v', vcf,
			'--pooled-discrete', '--pooled-continuous', 
			'--genotype-qualities', 
			'--report-genotype-likelihood-max', 
			'--allele-balance-priors-off']	

		if isinstance(bam,list):
			with open(bam_list,'w') as bamlist:
				bamlist.write('\n'.join(bam))
			args += ['-L', bam_list]
		else:
			args += ['-b', bam]

		if filters["min_base_quality_score"] != "" : args += ['--min-base-quality', filters["min_base_quality_score"]]
		if filters["min_alt_coverage"] != "" : args += ['--min-alternate-count', filters["min_alt_coverage"]]
		if filters["min_alt_freq"] != "" : args += ['--min-alternate-fraction', filters["min_alt_freq"]]
		if filters["min_mapping_quality_score"] != "": args += ['--min-mapping-quality', filters["min_mapping_quality_score"]]

		if target_bed != "": args += ['-t', target_bed]

		success = subprocess.call(args,stdout=log,stderr=log)
		#elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		
		if not success:
			#print("- FreeBayes: %d min, %d sec" % elapsed_time)
			return vcf
		else:
			print(' '.join(args))
			f.prRed('Error in FreeBayes calling. Check log file.')
			exit(1)


	def parallel_variant_calling(self, bam_list, filters, target_bed, reference_fasta, log, workdir):

		start_time = datetime.datetime.now()
		cmds_list = []
		outbam_list = []
		vcf_list = []
		log_list = []

		for sample, bam in bam_list:
			args = []

			samplelog = workdir +'/'+sample+'.log'
			log_list += [samplelog]
			write_log = open(samplelog,'a+')
			write_log.write('\n')

			vcf = workdir + '/'+ sample + '.' + self.tool_name + '.vcf'	
			
			vcf_list += [[sample,vcf]]
			
			args = [self.path,
				'-f', reference_fasta,
				'-v', vcf,
				'--pooled-discrete', '--pooled-continuous', 
				'--genotype-qualities', 
				'--report-genotype-likelihood-max', 
				'--allele-balance-priors-off']
			
			args += ['-b', bam]

			if filters["min_base_quality_score"] != "" : args += ['--min-base-quality', filters["min_base_quality_score"]]
			if filters["min_alt_coverage"] != "" : args += ['--min-alternate-count', filters["min_alt_coverage"]]
			if filters["min_alt_freq"] != "" : args += ['--min-alternate-fraction', filters["min_alt_freq"]]
			if filters["min_mapping_quality_score"] != "": args += ['--min-mapping-quality', filters["min_mapping_quality_score"]]
		
			if target_bed != "": args += ['-t', target_bed]
			if self.args != []: args += self.args
			cmds_list +=  [[args, write_log]]
		
		procs_list = [subprocess.Popen(cmd, stdout=log_file, stderr=log_file) for cmd, log_file in cmds_list]
		for proc in procs_list:
			proc.wait()

		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		print("-FreeBayes: %d min, %d sec" % elapsed_time)	
		return vcf_list

class Varscan(Tool):
	def __init__(self):
		super(Tool, self).__init__()
		self.tool_name = 'Varscan'

	def variant_calling(self, mpileup, sample_name, filters, target_bed, reference_fasta, log, workdir):

		start_time = datetime.datetime.now()

		sample_list = workdir +'/sample.list'
		with open(sample_list,'w+') as s:
			s.write('\n'.join(sample_name))
		vcf = workdir + '/' + '.'.join(mpileup.split('/')[-1].split('.')[:-1] + ['VarScan.vcf'])
		open_vcf = open(vcf,'w')
		args = ['java','-Xmx'+self.ram,'-jar',self.path,
			'mpileup2cns',mpileup,
			'--output-vcf','1',
			'--strand-filter 0',
			'--vcf-sample-list',sample_list,
			'--variants']

		if target_bed != None:
			args += ['-L',target_bed]

		#if filters == '0':
		if filters["min_base_quality_score"] != "" : args += ['--min-avg-qual', filters["min_base_quality_score"]]
		if filters["min_alt_coverage"] != "" : args += ['-min-reads2', filters["min_alt_coverage"]]
		if filters["min_alt_freq"] != "" : args += ['--min-var-freq', filters["min_alt_freq"]]

		success = subprocess.call(args,stdout=open_vcf,stderr=log)
		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		open_vcf.close()
		
		if not success:
			print("- VarScan: %d min, %d sec" % elapsed_time)
			return vcf
		else:
			f.prRed('Error in VarScan. Check log file.')
			exit(1)

class Samtools(Tool):
	
	def __init__(self):
		super(Tool, self).__init__()
		self.tool_name = 'Samtools'
	
	def mpileup(self, sample_name, bam_list, filters, target_bed, reference_fasta, log, workdir):

		start_time = datetime.datetime.now()
		mpileup = workdir +'/'+sample_name+'.mpileup'
		open_mpileup = open(mpileup,'w')

		args = ['samtools','mpileup','-B','-q 1','-d','50000','-L','50000','-f',reference_fasta]
	
		bam_list_file =  workdir +  '/bam.list'
		with open(bam_list_file,'w') as bamlist:
			if isinstance(bam_list,list):
				bamlist.write('\n'.join(bam_list))
			else:
				bamlist.write(bam_list)
		args += ['-b',bam_list_file]
		
		if target_bed != None:
			args += ['-l',target_bed]

		success = subprocess.call(args,stdout=open_mpileup,stderr=log)
		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		open_mpileup.close()
		if not success:
			print("- Mpileup: %d min, %d sec" % elapsed_time)
			return mpileup
		else:
			f.prRed('Error in Mpileup. Check log file.')
			exit(1)

class Vardict(Tool):

	def __init__(self):
		super(Tool, self).__init__()
		self.tool_name = 'Vardict'
	
	def vc_germline(self,path,path_script,threads,gbam,sbam,gsample_name,ssample_name,reference,target,log,workdir):

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

		def vc_somatic(self,path,path_script,threads,gbam,sbam,gsample_name,ssample_name,reference,target,log,workdir):

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
			

class VEP(Tool):
	"""docstring for VEP"""
	def __init__(self):
		super(Tool, self).__init__()
		self.tool_name = 'VEP'

	def add_vep_plugins(self, plugins, tools_info):
		

		args = []
		args_dir_plugin = []
		args_plugin= []

		for plugin in plugins['list']:
			pl_args = plugin
			pl_dir = []
			pl_files = []
			pl_fields = []
			path = tools_info[plugin]['path']
			files = plugins[plugin]['files']
			fields = plugins[plugin]['fields']			
			try:
				if tools_info[plugin]['local'] == "True":
					if path != "":
						args_dir_plugin += ['-v', path+':/'+plugin]

					if files != "":
						for file in files.split(','):
							if '=' in file:
								parts=file.split('=')
								parts[-1] = '/'+plugin+'/'+ parts[-1]
								pl_files += ['='.join(parts)]
							else:
								pl_files += ['/'+plugin+'/'+ file]

					if fields != "":	
						pl_fields += [fields]
					
					args_plugin += ['--plugin', ','.join([plugin]+pl_files+pl_fields)]		
				else:
					if path != "":
						pl_dir = ['./Plugins/'+ path]
					if files != "":
						for file in files.split(','):
							if '=' in file:
								parts=file.split('=')
								parts[-1] = './Plugins'+'/'+ parts[-1]
								pl_files += ['='.join(parts)]
							else:
								pl_files += ['./Plugins/'+ file]
					if fields != "":	
						pl_fields += [fields]
					args_plugin += ['--plugin', ','.join([plugin]+pl_dir+pl_files+pl_fields)]
			except Exception as e:
				if path != "":
					pl_dir = ['./Plugins/'+ path]
				if files != "":
					for file in files.split(','):
						if '=' in file:
							parts=file.split('=')
							parts[-1] = './Plugins'+'/'+ parts[-1]
							pl_files += ['='.join(parts)]
						else:
							pl_files += ['./Plugins/'+ file]
				if fields != "":	
					pl_fields += [fields]

				args_plugin += ['--plugin', ','.join([plugin]+pl_dir+pl_files+pl_fields)]
			
			#print(' '.join(args_plugin))

		return args_dir_plugin, args_plugin

	def vcf_annotation(self, vcf, reference_fasta, assembly, species, plugins, tools_info, log, workdir):
		print('-----------------vep')
		
		vep_vcf_name = '.'.join(vcf.split('/')[-1].split('.')[:-1] + ['VEP.vcf'])
		inputdir = '/'.join(vcf.split('/')[:-1])
		vcf_name = vcf.split('/')[-1]
		fastadir = '/'.join(reference_fasta.split('/')[:-1])
		fasta_name = reference_fasta.split('/')[-1]
	
		#args = [self.path,'-i',vcf,'-o',vep_vcf,'--fasta',reference_fasta, '--vcf']

		args = ['docker', 'run', '-it', '--rm', '-u', '1000:1000']
		args_dir = ['-v', self.path + ':/data',
			'-v', workdir + ':/output_dir',
			'-v', inputdir + ':/input_dir',
			'-v', fastadir + ':/fasta_dir']
			
		args_vep = ['ensemblorg/ensembl-vep', 'vep',
			'--dir_cache', '/data/',
			'--dir_plugins', '/data/Plugins',
			'--quiet',
			'-i', '/input_dir/'+vcf_name,
			'-o','/output_dir/'+vep_vcf_name,
			'-warning_file','STDERR',
			'--fasta','/fasta_dir/'+ fasta_name, '--vcf']

		if self.threads != '': args_vep += ['--fork', self.threads]
		if self.args != []: args_vep += self.args
		
		if assembly != "" : args_vep += ['--assembly',assembly]
		else: args_vep += ['--assembly', 'GRCh37']
		
		if species != "" : args_vep += ['--species',species] 
		else: args_vep += ['--species', 'homo_sapiens']

		if plugins['list'] != []:

			args_dir_plugin, args_plugin = self.add_vep_plugins(plugins, tools_info)
			args_dir += args_dir_plugin
			args_vep += args_plugin

		args += args_dir +args_vep

		print(args)

		print('\n'+' '.join(args))
		
		success = subprocess.call(args,stdout=log,stderr=log)
		#success = 1
		if not success:
			print("- VEP annotation: " + '.'.join(vcf.split('/')[-1].split('.')[:-1]))
			return workdir + '/' + vep_vcf_name
		else:
			f.prRed('Error in VEP annotation. Check log file.')
			exit(1)

class BCFTOOLS(Tool):
	"""docstring for ClassName"""
	def __init__(self):
		super(Tool, self).__init__()
		self.tool_name = 'BCFTOOLS'

	def norm(self, vcf, reference_fasta, log, workdir):

		norm_vcf = '.'.join(vcf.split('.')[:-1] + ['norm.vcf'])

		args = [self.path,'norm',
			'-m', '-both', vcf,
			'-f', reference_fasta,
			'-o', norm_vcf]
		
		success = subprocess.call(args, stdout=log, stderr=log)
		
		if not success:
			return norm_vcf
		else:
			f.prRed('Error in Vcf normalization. Check log file.')
			exit(1)

class DECON(Tool):
	"""docstring for ClassName"""
	def __init__(self):
		super(Tool, self).__init__()
		self.tool_name = 'DECON'

	def ReadInBams(self, bam_list, sample_name, target_bed, reference, log, workdir):
		
		out = workdir + '/' + sample_name

		args = ['Rscript', 'ReadInBams.R', '--bams', bam_list, '--bed', target_bed, '--fasta', reference, '--out', out]

		success = subprocess.call(args, stdout=log, stderr=log)
		rdata = out + '.RData'
		#success = False
		if not success:
			#print("- Estraction: %d min, %d sec" % elapsed_time)
			return rdata
		else:
			f.prRed('Error in DECON CNV calling. Check log file.')
			exit(1)

	def IdentifyFailures(self, rdata, sample_name, reference, log, workdir):

		out = workdir + '/' + sample_name + '.IdentifyFailures'

		args = ['Rscript', 'IdentifyFailures.R', '--Rdata', rdata, '--mincorr', '0.97', '--mincov', '50', '--custom', 'fALSE','--out', out]
		success = subprocess.call(args,stdout=log,stderr=log)


	def makeCNVcalls(self, rdata, sample_name, reference, log, workdir):

		out = workdir + '/' + sample_name + '.DECON.CNV'
	
		args = ['Rscript', self.path +'/makeCNVcalls.R', '--Rdata', rdata, "--plot", "None", '--out', out]

		if self.args != []: args += self.args

		success = subprocess.call(args,stdout=log,stderr=log)
		calls = out + '_all.txt'
		#success = False
		if not success:
			#print("- Estraction: %d min, %d sec" % elapsed_time)
			return calls
		else:
			f.prRed('Error in DECON CNV calling. Check log file.')
			exit(1)

class CoNVaDING(Tool):
	def __init__(self):
		super(Tool, self).__init__()
		self.tool_name = 'CoNVaDING'

	def StartWithBam(self, inputdir, target_bed, controls_dir, log, outdir):

		print('StartWithBam')

		args = ['perl', self.path, '-mode', 'StartWithBam',
			'-inputDir', inputdir,
			'-bed', target_bed,
			'-outputDir', outdir]
			#'--rmdup']
		
		if controls_dir == '':
			controls_dir = inputdir
			args += ['-useSampleAsControl']
		
		args += ['-controlsDir', controls_dir]

		success = subprocess.call(args, stdout=log, stderr=log)

		if not success:
			return controls_dir
		else:
			f.prRed('Error in CoNVaDING StartWithBam. Check log file.')
			exit(1)

	def StartWithMatchScore(self, inputdir, target_bed, controls_dir, log, outdir):
		print('StartWithMatchScore')

		args = ['perl', self.path, '-mode', 'StartWithMatchScore',
			'-inputDir', inputdir,
			'-outputDir', outdir]
		
		args += ['-controlsDir', controls_dir]

		controlSamples = 0
		
		for file in os.listdir(controls_dir):
			if 'normalized.coverage.txt' in file:
				controlSamples += 1
		
		args += ['-controlSamples', str(controlSamples)]




		success = subprocess.call(args, stdout=log, stderr=log)

		if not success:
			return success
		else:
			f.prRed('Error in CoNVaDING StartWithMatchScore. Check log file.')
			exit(1)

	def StartWithBestScore(self, inputdir, target_bed, controls_dir, log, outdir):
		print('StartWithBestScore')

		args = ['perl', self.path, '-mode', 'StartWithBestScore',
			'-inputDir', inputdir,
			'-outputDir', outdir,
			'-controlsDir', controls_dir]

		if self.args != []: args += self.args

		success = subprocess.call(args, stdout=log, stderr=log)

		if not success:
			return success
		else:
			f.prRed('Error in CoNVaDING StartWithBestScore. Check log file.')
			exit(1)

class CNVkit(Tool):
	def __init__(self):
		super(Tool, self).__init__()
		self.tool_name = 'CNVkit'

	def coverage(self, bam, target_bed, tag, log, outdir):

		cnn = outdir + '/' + '.'.join(bam.split('/')[-1].split('.')[:-1] + [tag, 'cnn'])
		
		args = [self.path, 'coverage', bam, target_bed, '-o', cnn]

		if self.args != []: args += self.args

		success = subprocess.call(args, stdout=log, stderr=log)

		if not success:
			return cnn
		else:
			f.prRed('Error in CNVkit coverage. Check log file.')
			exit(1)

	def fix(self, target_cnn, antitarget_cnn, cnn_reference, log, outdir):
		cnr = outdir + '/' + '.'.join(target_cnn.split('/')[-1].split('.')[:-2] + ['cnr'])

		args = [self.path, 'fix', target_cnn, antitarget_cnn, cnn_reference, '-o', cnr, '--no-gc']

		if self.args != []: args += self.args

		success = subprocess.call(args, stdout=log, stderr=log)

		if not success:
			return cnr
		else:
			f.prRed('Error in CNVkit fix. Check log file.')
			exit(1)
	
	def segment(self, cnr, algorithm, threshold, log, outdir):

		cns = outdir + '/' + '.'.join(cnr.split('/')[-1].split('.')[:-1] + ['cns'])

		args = [self.path, 'segment', cnr, '-o', cns]

		if self.args != []: args += self.args
		if algorithm != '': args += ['-m', algorithm]
		if threshold != '': args += ['-t', threshold]

		success = subprocess.call(args, stdout=log, stderr=log)

		if not success:
			return cns
		else:
			f.prRed('Error in CNVkit segment. Check log file.')
			exit(1)

	def antitarget(self, target_bed, log, outdir):

		antitarget = outdir + '/CNVkit.antitarget.bed'

		args = [self.path, 'antitarget', target_bed, '-o', antitarget]

		if self.args != []: args += self.args

		success = subprocess.call(args, stdout=log, stderr=log)

		if not success:
			return antitarget
		else:
			f.prRed('Error in CNVkit antitarget. Check log file.')
			exit(1)

	def call(self, cns, log, outdir):

		call = outdir + '/' + '.'.join(cns.split('/')[-1].split('.')[:-1] + ['call.cns'])


		args = [self.path, 'call', cns, '-o', call, '-m', 'threshold']

		if self.args != []: args += self.args


		success = subprocess.call(args, stdout=log, stderr=log)

		if not success:
			return call
		else:
			f.prRed('Error in CNVkit call. Check log file.')
			exit(1)