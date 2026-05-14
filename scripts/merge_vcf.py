import re
import string
import argparse
import sys
import statistics
import scipy.stats as stats

def parse_header(vcf,i):
	h_filter=''
	h_info=''
	h_format=''
	var_format='.'

	if i==1:
		add='G'
	elif i==2:
		add='F'
	elif i==3:
		add='V'

	for line in vcf:
		line=line.rstrip()
		line_split=line.split(',')


		if line.startswith('##FILTER'):
			line_split[0]=line_split[0]+'_'+ add
			h_filter=h_filter+','.join(line_split) + '\n'
		
		elif line.startswith('##INFO'):
			line_split[0]=line_split[0]+'_'+ add
			h_info=h_info+','.join(line_split) + '\n'

		elif line.startswith('##FORMAT'):
			line_split[0]=line_split[0]+'_'+ add
			h_format=h_format+','.join(line_split) + '\n'


	return h_filter,h_info,h_format

def samples(vcf):
	sample_list=''
	for line in vcf:
		line=line.rstrip()
		line_split=line.split('\t')
		
		if line.startswith('#CHROM'):
			sample_list=line_split[9:]
	return sample_list

def estrai_varianti(varianti,vcf,i,sample_list):
	if vcf == None:
		pass
	else:
		for line in vcf:
			line=line.rstrip()
			line_split=line.split('\t')
			if line.startswith('##'):
				continue
			elif line.startswith('#CHROM'):
				h_sample_list=line_split[9:]
			else:
				var='\t'.join(line_split[0:5])
				qual=line_split[5]
				filter=modifica_filter(line_split[6],i)
				info=modifica_info(line_split[7],i)
				format=modifica_format(line_split[8],i) 
				format_samples=riordina_samples(line_split[9:],sample_list,h_sample_list)
				

				if var in varianti.keys():
					line_var=varianti.get(var)
				else:
					if opts.varscan != None:
						line_var=[['.','.','.','.','.'],['.','.','.','.','.'],['.','.','.','.','.']]
					else:
						line_var=[['.','.','.','.','.'],['.','.','.','.','.']]
					
				(line_var[i-1])[0]=qual
				(line_var[i-1])[1]=filter
				(line_var[i-1])[2]=info
				(line_var[i-1])[3]=format
				(line_var[i-1])[4]=format_samples
				varianti[var]=line_var


def riordina_samples(format_list,sample_list,h_sample_list):
	new_format_list=[]
	for sample in sample_list:
		i=h_sample_list.index(sample)
		new_format_list+=[format_list[i]]
	return new_format_list

def modifica_filter(filter,i):
	if i==1:
		add='G'
	elif i==2:
		add='F'
	elif i==3:
		add='V'
	if filter != '.':
		filter_split=filter.split(';')
		filter=';'.join(a+'_'+add for a in filter_split)
	return filter

def modifica_info(info,i):
	if i==1:
		add='G'
	elif i==2:
		add='F'
	elif i==3:
		add='V'
	info_split=info.split(';')
	for el in info_split:
		el_split=el.split('=')
		info_split[info_split.index(el)]=el_split[0]+'_'+add+'='+el_split[1]

	info=';'.join(info_split)
	return info

def modifica_format(format,i):
	if i==1:
		add='G'
	elif i==2:
		add='F'
	elif i==3:
		add='V'
	format_split=format.split(':')
	format=':'.join(a+'_'+add for a in format_split)
	return format

def fix_format_values(line_var,s_list,i,format):
	format_sample=[]
	null_format='./.'
	if (line_var[i])[-1]=='.':
		for a in format.split(':')[1:]:
			null_format=null_format + ':.'
		for s in s_list:
			format_sample=format_sample + [null_format]
	else:
		for form in (line_var[i])[-1]:
			null_format='./.'
			if form.startswith('.') or form.startswith('./.'):
				for a in format.split(':')[1:]:
					null_format=null_format + ':.'
				format_sample = format_sample + [null_format]
			else:
				format_sample =	format_sample + [form]

	return format_sample


def main():
	
	parser = argparse.ArgumentParser('Parse 3 VCF output from Variant callers to output a VCF whith merged h_info. Output is to --out.')
	parser.add_argument('-g', '--gatk', help="GATK vcf output file name")
	parser.add_argument('-f', '--freebayes', help="Freebayes vcf output file name")
	parser.add_argument('-v', '--varscan', help="Varscan vcf output file name", default=None)
	parser.add_argument('-o', '--out', help="file name in output. It returns file_name.vcf ")
	
	global opts 
	opts = parser.parse_args()

	gatk=open(opts.gatk,'r').readlines()
	freebayes=open(opts.freebayes,'r').readlines()
	try:
		varscan=open(opts.varscan,'r').readlines()
	except:
		varscan = None
	out_vcf=open(opts.out,'w')
	varianti = dict()
	HEADER='##fileformat=VCFv4.2\n'

	h_filter_gatk,h_info_gatk,h_format_gatk=parse_header(gatk,1)
	h_filter_freebayes,h_info_freebayes,h_format_freebayes=parse_header(freebayes,2)
	
	if opts.varscan != None:
		h_filter_varscan,h_info_varscan,h_format_varscan=parse_header(varscan,3)
		sample_list_varscan=samples(varscan)

	sample_list_gatk=samples(gatk)
	sample_list_freebayes=samples(freebayes)

	estrai_varianti(varianti,gatk,1,sample_list_gatk)
	estrai_varianti(varianti,freebayes,2,sample_list_gatk)
	estrai_varianti(varianti,varscan,3,sample_list_gatk)

	HEADER = HEADER + h_filter_gatk+h_filter_freebayes
	if opts.varscan != None:
		HEADER += h_filter_varscan
	
	HEADER += h_info_gatk+h_info_freebayes
	if opts.varscan != None:
		HEADER += h_info_varscan

	HEADER += h_format_gatk+h_format_freebayes
	if opts.varscan != None:
		HEADER += h_format_varscan

	HEADER += '#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t'+'\t'.join(sample_list_gatk)
	out_vcf.write(HEADER+'\n')
	
	for var in varianti.keys():
		line_var=varianti.get(var)
		try:
			qual=','.join([(line_var[0])[0],(line_var[1])[0],(line_var[2])[0]])
			filter=','.join([(line_var[0])[1],(line_var[1])[1],(line_var[2])[1]])
			info=','.join([(line_var[0])[2],(line_var[1])[2],(line_var[2])[2]])
			format_varscan = (line_var[2])[-2]
			if format_varscan == '.':
				format_varscan = 'GT_V:GQ_V:SDP_V:DP_V:RD_V:AD_V:FREQ_V:PVAL_V:RBQ_V:ABQ_V:RDF_V:RDR_V:ADF_V:ADR_V'
		except:
			qual=','.join([(line_var[0])[0],(line_var[1])[0]])
			filter=','.join([(line_var[0])[1],(line_var[1])[1]])
			info=','.join([(line_var[0])[2],(line_var[1])[2]])

		#format=':'.join([format_gatk,format_freebayes,format_varscan])

		format_gatk, format_freebayes = [(line_var[0])[-2],(line_var[1])[-2]]


		if format_gatk == '.':
			format_gatk = 'GT_G:AD_G:AF_G:DP_G:F1R2_G:F2R1_G:GQ_G:PL_G'
		if format_freebayes == '.':
			format_freebayes = 'GT_F:GQ_F:DP_F:AD_F:RO_F:QR_F:AO_F:QA_F:GL_F'
		
		try:
			format=':'.join([format_gatk,format_freebayes,format_varscan])
		except:
			format=':'.join([format_gatk,format_freebayes])

		(line_var[0])[-1]=fix_format_values(line_var,sample_list_gatk,0,format_gatk)
		(line_var[1])[-1]=fix_format_values(line_var,sample_list_gatk,1,format_freebayes)
		try:
			(line_var[2])[-1]=fix_format_values(line_var,sample_list_gatk,2,format_varscan)
		except:
			pass

		format_sample=[]
		for sample in sample_list_gatk:
			i=sample_list_gatk.index(sample)
			try:
				format_sample+=[':'.join([((line_var[0])[-1])[i],((line_var[1])[-1])[i],((line_var[2])[-1])[i]])]
			except:
				format_sample+=[':'.join([((line_var[0])[-1])[i],((line_var[1])[-1])[i]])]
		
		format_samples='\t'.join(format_sample)

		out_vcf.write('\t'.join([var,qual,filter,info,format,format_samples])+'\n')
	
main()
