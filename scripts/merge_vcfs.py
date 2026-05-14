import re
import string
import argparse
import sys
import statistics
import os
import scipy.stats as stats
import numpy as np
import datetime
import math

def parse_headerINFO(vcf, h_header, tag):
	
	for line in vcf:
		line=line.rstrip()
		line_split=line.split(',')
		
		if line.startswith('##INFO'):
			if line.startswith('####INFO=<ID=Samples'):
				continue
			info_name = line_split[0].split('=')
			info_name[-1] = tag + '_' +info_name[-1]
			line_split[0] = '='.join(info_name)
			h_header[1] += [','.join(line_split)]

	return h_header

def parse_headerFORMAT(h_header):

	h_header[2] += ['##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">',
		'##FORMAT=<ID=DP,Number=1,Type=Integer,Description="Read depth calculated as rounded mean of DP from merged vcfs">',
		'##FORMAT=<ID=AD,Number=R,Type=Integer,Description="Number of observation for each allele">',
		'##FORMAT=<ID=RO,Number=1,Type=Integer,Description="Allelic depths for the ref allele calculated as rounded mean of RO from merged vcfs">',
		'##FORMAT=<ID=AO,Number=1,Type=Integer,Description="Allelic depths for the alt allele calculated as rounded mean of AO from merged vcfs">',
		'##FORMAT=<ID=AF,Number=A,Type=Float,Description="Allele fractions of alternate allele calculated using AO and RO">',
		'##FORMAT=<ID=QB,Number=1,Type=Integer,Description="Quality Base calculated as rounded mean of QB from merged vcfs">',
		'##FORMAT=<ID=MQ,Number=1,Type=Float,Description="Mapping Quality calculated as rounded mean of MQ from merged vcfs">',
		'##FORMAT=<ID=GQ,Number=1,Type=Integer,Description="Genotype Quality calculated as rounded mean of GQ from merged vcfs">',
		'##FORMAT=<ID=SB,Number=4,Type=Float,Description="Per-sample component statistics which comprise the Fishers Exact Test to detect strand bias.">',
		'##FORMAT=<ID=SOR,Number=1,Type=Float,Description="Symmetric Odds Ratio of 2x2 contingency table to detect strand bias">']
	return h_header

def calcola_GT(gt_arr):
	gt0 = 0
	gt1 = 0
	gt2 = 0
	for gt in gt_arr:
		if gt == '0/0':
			gt0 += 1
		elif gt == '0/1' or gt == '1/0' or gt == '0|1' or gt == '1|0':
			gt1 += 1
		elif gt == '1/1' or gt == '1|1':
			gt2 += 1

	if gt0 == 0 and gt1 ==0 and gt2 ==0:
		return '.'

	elif gt2 > gt1 and gt2 >= gt0:
		return '1/1'
	
	elif gt1 >= gt1 and gt1 >= gt0:
		if '0|1' in gt_arr:
			return '0|1'
		elif '1|0' in gt_arr:
			return '1|0'
		else:
			return '0/1'
	else:
		return '0/0'



def calcola_DP(dp_arr, stat):

	v=[]
	for dp in dp_arr:
		if dp != '' and dp is not '.':
			v=v+[int(dp)]
	if stat == 'mean':
		try:
			return int(np.ceil(statistics.mean(v)))
		except:
			return '.'
	elif stat == 'median':
		try:
			return int(statistics.median(v))
		except:
			return '.'

def calcola_AO(ao_arr, stat):
	v=[]
	for ao in ao_arr:
		if ao != '' and ao is not '.':
			v=v+[int(ao)]

	if stat == 'mean':
		try:
			return int(np.ceil(statistics.mean(v)))
		except:
			return '.'
	elif stat == 'median':
		try:
			return int(statistics.median(v))
		except:
			return '.'

def calcola_RO(ro_arr, stat):
	v=[]
	for ro in ro_arr:
		if ro != '' and ro is not '.' :
			v=v+[int(ro)]
	if stat == 'mean':
		try:
			return int(np.ceil(statistics.mean(v)))
		except:
			return '.'
	elif stat == 'median':
		try:
			return int(statistics.median(v))
		except:
			return '.'

def calcola_GQ(GQ_arr, stat):

	v=[]
	for gq in GQ_arr:
		if gq != '' and gq is not '.':
			v=v+[float(gq)]
	if stat == 'mean':
		try:
			return int(statistics.mean(v))
		except:
			return '.'
	elif stat == 'median':
		try:
			return int(statistics.median(v))
		except:
			return '.'	

def calcola_QB(QB_arr, stat):
	v=[]
	for bq in QB_arr:
		if bq != '' and bq is not '.':
			v=v+[float(bq)]
	if stat == 'mean':
		try:
			return int(statistics.mean(v))
		except:
			return '.'
	elif stat == 'median':
		try:
			return int(statistics.median(v))
		except:
			return '.'	

def calcola_MQ(MQ_arr, stat):

	v=[]
	for mq in MQ_arr:
		if mq != '' and mq is not '.':
			v=v+[float(mq)]
	if stat == 'mean':
		try:
			return round(statistics.mean(v),3)
		except:
			return '.'
	elif stat == 'median':
		try:
			return round(statistics.median(v),3)
		except:
			return '.'

def calcola_SB(SB_arr, stat):

	v=[]
	for strb in SB_arr:
		if strb != '' and strb is not '.':
			v=v+[float(strb)]
	if stat == 'mean':
		try:
			return round(statistics.mean(v),3)
		except:
			return '.'
	elif stat == 'median':
		try:
			return round(statistics.median(v),3)
		except:
			return '.'

def calcola_SOR(SOR_arr, stat):

	v=[]
	for sor in SOR_arr:
		if sor != '' and sor is not '.':
			v=v+[float(sor)]
	if stat == 'mean':	
		try:
			return round(statistics.mean(v),3)
		except:
			return '.'
	elif stat == 'median':
		try:
			return round(statistics.median(v),3)
		except:
			return '.'

def calcola_AC(AC_arr, stat):
	v=[]
	for ac in AC_arr:
		if ac != '' and ac is not '.':
			v=v+[int(ac)]
	if stat == 'mean':	
			try:
				AC_mean=int(statistics.mean(v))
			except:
				AC_mean='.'
	elif stat == 'median':
			try:
				return int(statistics.median(v))
			except:
				return '.'
	elif stat == 'max':		
			try:
				return max(v)
			except:
				return '.'
	elif stat == 'min':		
			try:
				return min(v)
			except:
				return '.'

def calcola_AN(AN_arr, stat):	
	v=[]
	for an in AN_arr:
		if an != '' and an is not '.':
			v=v+[int(an)]
	if stat == 'mean':	
		try:
			return int(statistics.mean(v))
		except:
			return '.'
	elif stat == 'median':
		try:
			return int(statistics.median(v))
		except:
			return '.'
	elif stat == 'max':
		try:
			return max(v)
		except:
			return '.'
	elif stat == 'min':		
		try:
			return min(v)
		except:
			return '.'


		

if __name__ == '__main__':

	parser = argparse.ArgumentParser('Sample Extraction from multisample VCF')

	parser = argparse.ArgumentParser('Merge vcfs from different Variant callers into a single vcf.\nSpecific VCaller fields will be reported as INFO field with the "VCallername_Namefield" format.\nMerged FORMAT infos will be reported in FORMAT field.')
	parser.add_argument('-g', '--gatk', help="GATK vcf",default=None)
	parser.add_argument('-f', '--freebayes', help="Freebayes vcf",default=None)
	parser.add_argument('-v', '--varscan', help="Varscan2 vcf",default=None)
	parser.add_argument('-o', '--out',help="Output vcf")
	global opts
	opts = parser.parse_args()


	gatk_header = []
	freebayes_header = []
	varscan_header = []
	header = []
	vars = {}
	
	newheder = [['##fileformat=VCFv4.2', '##source=merge_vcfs'], [], []]

	if opts.gatk != None:
		
		gatk = open(opts.gatk,'r')
		for line in gatk:

			line = line.rstrip()
			if line.startswith('##'):
				gatk_header += [line]
			elif line.startswith('#CHROM'):
				header = line
			else:
				chrom, pos, id, ref, alt, qual, filter, info, format, sample_format = line.split('\t')

				var_id = '\t'.join([chrom, pos, ref, alt])
				if var_id in vars.keys():
					vars[var_id]['gatk_qual'] = qual
					vars[var_id]['gatk_filter'] = filter
					vars[var_id]['gatk_info']= info
					vars[var_id]['gatk_format'] = format
					vars[var_id]['gatk_sample_format'] = sample_format
				else:				
					vars[var_id] = {'chrom': chrom,
						'pos': pos,
						'id':id,
						'ref':ref,
						'alt':alt,
						'gatk_qual':qual,
						'gatk_filter':filter,
						'gatk_info':info,
						'gatk_format':format,
						'gatk_sample_format':sample_format,
						'freebayes_qual':"'.'",
						'freebayes_filter':"'.'",
						'freebayes_info':"'.'",
						'freebayes_format':"'.'",
						'freebayes_sample_format':"'.'",
						'varscan_qual':"'.'",
						'varscan_filter':"'.'",
						'varscan_info':"'.'",
						'varscan_format':"'.'",
						'varscan_sample_format':"'.'"}
		
		newheder = parse_headerINFO(gatk_header, newheder, 'GATK')

	if opts.freebayes != None:
		freebayes = open(opts.freebayes,'r')
		for line in freebayes:
			line = line.rstrip()
			if line.startswith('##'):
				freebayes_header += [line]
			elif line.startswith('#CHROM'):
				header = line
			else:
				chrom, pos, id, ref, alt, qual, filter, info, format, sample_format = line.split('\t')

				var_id = '\t'.join([chrom, pos, ref, alt])
				if var_id in vars.keys():
					vars[var_id]['freebayes_qual'] = qual
					vars[var_id]['freebayes_filter'] = filter
					vars[var_id]['freebayes_info']= info
					vars[var_id]['freebayes_format'] = format
					vars[var_id]['freebayes_sample_format'] = sample_format
				else:
					vars[var_id] = {'chrom': chrom,
						'pos': pos,
						'id':id,
						'ref':ref,
						'alt':alt,
						'freebayes_qual':qual,
						'freebayes_filter':filter,
						'freebayes_info':info,
						'freebayes_format':format,
						'freebayes_sample_format':sample_format,
						'gatk_qual':"'.'",
						'gatk_filter':"'.'",
						'gatk_info':"'.'",
						'gatk_format':"'.'",
						'gatk_sample_format':"'.'",
						'varscan_qual':"'.'",
						'varscan_filter':"'.'",
						'varscan_info':"'.'",
						'varscan_format':"'.'",
						'varscan_sample_format':"'.'"}
		newheder = parse_headerINFO(freebayes_header, newheder, 'FREEB')

	if opts.varscan != None:
		varscan =  open(opts.varscan,'r')
		for line in varscan:
			line = line.rstrip()
			if line.startswith('##'):
				varscan_header += [line]
			elif line.startswith('#CHROM'):
				header = line
			else:
				chrom, pos, id, ref, alt, qual, filter, info, format, sample_format = line.split('\t')

				var_id = '\t'.join([chrom, pos, ref, alt])
				if var_id in vars.keys():
					vars[var_id]['varscan_qual'] = qual
					vars[var_id]['varscan_filter'] = filter
					vars[var_id]['varscan_info']= info
					vars[var_id]['varscan_format'] = format
					vars[var_id]['varscan_sample_format'] = sample_format
				else:
					vars[var_id] = {'chrom': chrom,
						'pos': pos,
						'id':id,
						'ref':ref,
						'alt':alt,
						'varscan_qual':qual,
						'varscan_filter':filter,
						'varscan_info':info,
						'varscan_format':format,
						'varscan_sample_format':sample_format,
						'gatk_qual':"'.'",
						'gatk_filter':"'.'",
						'gatk_info':"'.'",
						'gatk_format':"'.'",
						'gatk_sample_format':"'.'",
						'freebayes_qual':"'.'",
						'freebayes_filter':"'.'",
						'freebayes_info':"'.'",
						'freebayes_format':"'.'",
						'freebayes_sample_format':"'.'"}
		newheder = parse_headerINFO(varscan_header, newheder, 'VARSCAN')

	out = open(opts.out,'w')
#	print(newheder)
	newheder = parse_headerFORMAT(newheder)
	newheder[1] += ['##INFO=<ID=GATK_SAMPLE,Number=.,Type=String,Description="Sample-specific variant informations reported in GATK vcf">']
	newheder[1] += ['##INFO=<ID=GATK_FORMAT,Number=.,Type=String,Description="FORMAT reported in GATK vcf">']
	newheder[1] += ['##INFO=<ID=GATK_INFO,Number=.,Type=String,Description="When is . the variant was not found in GATK vcf">']
	
	newheder[1] += ['##INFO=<ID=FREEB_SAMPLE,Number=.,Type=String,Description="Sample-specific variant informations reported in Freebayes vcf">']
	newheder[1] += ['##INFO=<ID=FREEB_FORMAT,Number=.,Type=String,Description="FORMAT reported in Freebayes vcf">']
	newheder[1] += ['##INFO=<ID=FREEB_INFO,Number=.,Type=String,Description="When is . the variant was not found in Freebayes vcf">']
	
	newheder[1] += ['##INFO=<ID=VARSCAN_SAMPLE,Number=.,Type=String,Description="Sample-specific variant informations reported in Varscan vcf">']
	newheder[1] += ['##INFO=<ID=VARSCAN_FORMAT,Number=.,Type=String,Description="FORMAT reported in Varscan vcf">']
	newheder[1] += ['##INFO=<ID=VARSCAN_INFO,Number=.,Type=String,Description="When is . the variant was not found in Varscan vcf">']

	newheder[1] += ['##INFO=<ID=AC,Number=.,Type=String,Description="FORMAT reported in Varscan vcf">']
	newheder[1] += ['##INFO=<ID=AN,Number=.,Type=String,Description="When is . the variant was not found in Varscan vcf">']

	out.write('\n'.join(['\n'.join(newheder[0]), '\n'.join(newheder[1]), '\n'.join(newheder[2]+[header])]) +'\n')


	for var_id in vars.keys():
		chrom = vars[var_id]['chrom']
		pos = vars[var_id]['pos']
		id = vars[var_id]['id']
		ref = vars[var_id]['ref']
		alt = vars[var_id]['alt']

		qual = '.'

		INFO_gatk_qual = 'GATK_QUAL='+vars[var_id]['gatk_qual']
		INFO_freeb_qual = 'FREEB_QUAL='+vars[var_id]['freebayes_qual']	
		INFO_varscan_qual = 'VARSCAN_QUAL='+vars[var_id]['varscan_qual']

		INFO_gatk_filter = 'GATK_FILTER='+vars[var_id]['gatk_filter']
		INFO_freeb_filter = 'FREEB_FILTER='+vars[var_id]['freebayes_filter']	
		INFO_varscan_filter = 'VARSCAN_FILTER='+vars[var_id]['varscan_filter']

		INFO_gatk_info = ['GATK_' + tag for tag in vars[var_id]['gatk_info'].split(';')]		
		if INFO_gatk_info == ["GATK_'.'"]: INFO_gatk_info = ["GATK_INFO='.'"]
		
		INFO_freeb_info = ['FREEB_' + tag for tag in vars[var_id]['freebayes_info'].split(';')]
		if INFO_freeb_info == ["FREEB_'.'"] : INFO_freeb_info = ["FREEB_INFO='.'"]
		
		INFO_varscan_info = ['VARSCAN_' + tag for tag in vars[var_id]['varscan_info'].split(';')]
		if INFO_varscan_info == ["VARSCAN_'.'"] : INFO_varscan_info = ["VARSCAN_INFO='.'"]

		INFO_gatk_format = 'GATK_FORMAT='+vars[var_id]['gatk_format'] + ';GATK_SAMPLE=' + vars[var_id]['gatk_sample_format']
		INFO_freeb_format = 'FREEB_FORMAT='+vars[var_id]['freebayes_format'] + ';FREEB_SAMPLE=' + vars[var_id]['freebayes_sample_format']		
		INFO_varscan_format = 'VARSCAN_FORMAT='+vars[var_id]['varscan_format'] + ';VARSCAN_SAMPLE=' + vars[var_id]['varscan_sample_format']



		gatk_format_split = vars[var_id]['gatk_format'].split(':')
		freeb_format_split = vars[var_id]['freebayes_format'].split(':')
		varscan_format_split = vars[var_id]['varscan_format'].split(':')

		if opts.gatk != None and vars[var_id]['gatk_format'] != "'.'" \
			and vars[var_id]['gatk_sample_format'] != '.' \
			and not vars[var_id]['gatk_sample_format'].startswith('./.') \
			and not vars[var_id]['gatk_sample_format'].startswith('.'):
			try:
				gatk_gt = vars[var_id]['gatk_sample_format'].split(':')[vars[var_id]['gatk_format'].split(':').index('GT')]
				gatk_dp = float(vars[var_id]['gatk_sample_format'].split(':')[vars[var_id]['gatk_format'].split(':').index('DP')])
				gatk_ro = float(vars[var_id]['gatk_sample_format'].split(':')[vars[var_id]['gatk_format'].split(':').index('AD')].split(',')[0])
				gatk_ao = float(vars[var_id]['gatk_sample_format'].split(':')[vars[var_id]['gatk_format'].split(':').index('AD')].split(',')[1])
				try:
					gatk_rfow = float(vars[var_id]['gatk_sample_format'].split(':')[vars[var_id]['gatk_format'].split(':').index('F1R2')].split(',')[0])
					gatk_afow = float(vars[var_id]['gatk_sample_format'].split(':')[vars[var_id]['gatk_format'].split(':').index('F1R2')].split(',')[1])
					gatk_rrev = float(vars[var_id]['gatk_sample_format'].split(':')[vars[var_id]['gatk_format'].split(':').index('F2R1')].split(',')[1])
					gatk_arev = float(vars[var_id]['gatk_sample_format'].split(':')[vars[var_id]['gatk_format'].split(':').index('F2R1')].split(',')[1])
				except:
					gatk_rfow = 0.0
					gatk_afow = 0.0
					gatk_rrev = 0.0
					gatk_arev = 0.0
				try:
					gatk_GQ = float(vars[var_id]['gatk_sample_format'].split(':')[vars[var_id]['gatk_format'].split(':').index('GQ')])
				except: 
					gatk_GQ = '.'
				try:
					gatk_PL = vars[var_id]['gatk_sample_format'].split(':')[vars[var_id]['gatk_format'].split(':').index('PL')]
				except:
					gatk_PL = '.'

				gatk_MQ = '.'
				gatk_QB = '.'
				gatk_AC = '.'
				gatk_AN = '.'
				for info in vars[var_id]['gatk_info'].split(';'):
					if info.startswith('MQ='):
						gatk_MQ = float(info.split('=')[1])
					if info.startswith('QD='):
						gatk_QB = float(info.split('=')[1])
					if info.startswith("AC="):
						gatk_AC = int(info.split('=')[1])
					if info.startswith("AN="):
						gatk_AN = int(info.split('=')[1])

				try:
					if gatk_gt == '1/1':
						gatk_SB = '.'
					else:
						gatk_SB = -10*math.log10(stats.fisher_exact([[gatk_rfow, gatk_rrev], [gatk_afow, gatk_arev]])[1])
				except:
					gatk_SB= '.'

				try:
					symmetricalRatio  = ((gatk_rfow+1.0)*(gatk_arev+1.0))/((gatk_rrev+1.0)*(gatk_afow+1.0)) + ((gatk_rrev+1.0)*(gatk_afow+1.0))/((gatk_rfow+1.0)*(gatk_arev+1.0))
					refRatio = min(gatk_rfow + 1.0, gatk_rrev + 1.0) / max(gatk_rfow + 1.0, gatk_rrev + 1.0)
					altRatio = min(gatk_afow + 1.0, gatk_arev + 1.0) / max(gatk_afow + 1.0, gatk_arev + 1.0)
					gatk_SOR = math.log(symmetricalRatio) + math.log(refRatio) - math.log(altRatio)
					if gatk_gt == '1/1' or gatk_gt == '1|1':
						gatk_SOR='.'
				except:
					gatk_SOR='.'

			except Exception as e:
			
				print(var_id,vars[var_id])
				raise		
		else:
			gatk_gt = '.'
			gatk_dp = '.'
			gatk_ro = '.' 
			gatk_ao = '.'
			gatk_rfow = '.' 
			gatk_afow = '.'
			gatk_rrev = '.'
			gatk_arev = '.'
			gatk_GQ = '.'
			gatk_PL = '.'
			gatk_QB = '.'
			gatk_MQ = '.'
			gatk_SB= '.'
			gatk_SOR = '.'
			gatk_AC = '.'
			gatk_AN = '.'
 
		if opts.freebayes != None \
			and vars[var_id]['freebayes_format'] != "'.'" \
			and vars[var_id]['freebayes_sample_format'] != '.' \
			and not vars[var_id]['freebayes_sample_format'].startswith('./.') \
			and not vars[var_id]['freebayes_sample_format'].startswith('.'):

			freeb_gt = vars[var_id]['freebayes_sample_format'].split(':')[vars[var_id]['freebayes_format'].split(':').index('GT')]
			try:
				freeb_dp = float(vars[var_id]['freebayes_sample_format'].split(':')[vars[var_id]['freebayes_format'].split(':').index('DP')])
			except:
				print(var_id)
			freeb_ro = float(vars[var_id]['freebayes_sample_format'].split(':')[vars[var_id]['freebayes_format'].split(':').index('AD')].split(',')[0])
			freeb_ao = float(vars[var_id]['freebayes_sample_format'].split(':')[vars[var_id]['freebayes_format'].split(':').index('AD')].split(',')[1])
			freeb_GQ = float(vars[var_id]['freebayes_sample_format'].split(':')[vars[var_id]['freebayes_format'].split(':').index('GQ')])
			freeb_PL = vars[var_id]['freebayes_sample_format'].split(':')[vars[var_id]['freebayes_format'].split(':').index('DP')]

			freeb_afow = '.'
			freeb_arev = '.'
			freeb_rfow = '.'
			freeb_rrev = '.'
			freeb_MQ = '.'
			freeb_AC = '.'
			freeb_AN = '.'
			for info in vars[var_id]['freebayes_info'].split(';'):
				if info.startswith("SAF="):
					freeb_afow = float(info.split('=')[1]) + 1.0
				if info.startswith("SAR="):
					freeb_arev = float(info.split('=')[1]) + 1.0
				if info.startswith("SRF="):
					freeb_rfow = float(info.split('=')[1]) + 1.0
				if info.startswith("SRR="):
					freeb_rrev = float(info.split('=')[1]) + 1.0
				if info.startswith("MQM="):
					freeb_MQ = float(info.split('=')[1])
				if info.startswith("AC="):
					freeb_AC = int(info.split('=')[1])
				if info.startswith("AN="):
					freeb_AN = int(info.split('=')[1])

			freeb_QB=float(vars[var_id]['freebayes_sample_format'].split(':')[vars[var_id]['freebayes_format'].split(':').index('QA')])/(freeb_ao + 1)


			try:
				freeb_af = freeb_ao/(freeb_ro + freeb_ao)
			except:
				freeb_af = '.'
			try:
				if freeb_gt == '1/1':
					freeb_SB = 0
				else:
					freeb_SB = -10*math.log10(stats.fisher_exact([[freeb_rfow, freeb_rrev], [freeb_afow, freeb_arev]])[1])
			except:
				freeb_SB = '.'

			try:
				symmetricalRatio  = ((freeb_rfow)*(freeb_arev))/((freeb_rrev)*(freeb_afow)) + ((freeb_rrev)*(freeb_afow))/((freeb_rfow)*(freeb_arev))
				refRatio = min(freeb_rfow, freeb_rrev) / max(freeb_rfow, freeb_rrev)
				altRatio = min(freeb_afow, freeb_arev) / max(freeb_afow, freeb_arev)
				freeb_SOR = math.log(symmetricalRatio) + math.log(refRatio) - math.log(altRatio)
				if freeb_gt == '1/1' or freeb_gt == '1|1':
					freeb_SOR='.'
			except:
				freeb_SOR='.'
		else:
			freeb_gt = '.'
			freeb_dp = '.'
			freeb_ro = '.'
			freeb_ao = '.'
			freeb_rfow = '.'
			freeb_afow = '.'
			freeb_rrev = '.'
			freeb_arev = '.'
			freeb_GQ = '.' 
			freeb_PL = '.' 
			freeb_MQ = '.'
			freeb_QB = '.'
			freeb_SB= '.'
			freeb_SOR = '.'
			freeb_AC = '.'
			freeb_AN = '.'

		if opts.varscan != None and vars[var_id]['varscan_format'] != "'.'" \
			and vars[var_id]['varscan_sample_format'] != '.' \
			and not vars[var_id]['varscan_sample_format'].startswith('./.') \
			and not vars[var_id]['varscan_sample_format'].startswith('.'):
			varscan_gt = vars[var_id]['varscan_sample_format'].split(':')[vars[var_id]['varscan_format'].split(':').index('GT')]
			varscan_dp = float(vars[var_id]['varscan_sample_format'].split(':')[vars[var_id]['varscan_format'].split(':').index('SDP')])
			varscan_ro = float(vars[var_id]['varscan_sample_format'].split(':')[vars[var_id]['varscan_format'].split(':').index('RD')])
			varscan_ao = float(vars[var_id]['varscan_sample_format'].split(':')[vars[var_id]['varscan_format'].split(':').index('AD')])
			varscan_rfow = float(vars[var_id]['varscan_sample_format'].split(':')[vars[var_id]['varscan_format'].split(':').index('RDF')])
			varscan_afow = float(vars[var_id]['varscan_sample_format'].split(':')[vars[var_id]['varscan_format'].split(':').index('ADF')])
			varscan_rrev = float(vars[var_id]['varscan_sample_format'].split(':')[vars[var_id]['varscan_format'].split(':').index('RDR')])
			varscan_arev = float(vars[var_id]['varscan_sample_format'].split(':')[vars[var_id]['varscan_format'].split(':').index('ADR')])
			varscan_GQ = float(vars[var_id]['varscan_sample_format'].split(':')[vars[var_id]['varscan_format'].split(':').index('GQ')])
			varscan_PL = '.'
			varscan_MQ = '.'
			varscan_QB = float(vars[var_id]['varscan_sample_format'].split(':')[vars[var_id]['varscan_format'].split(':').index('ABQ')])

			varscan_WT = '.'
			varscan_HET = '.'
			varscan_HOM = '.'
			varscan_NC = '.'
			for info in vars[var_id]['varscan_info'].split(';'):
				if info.startswith("WT"):
					varscan_WT = info.split('=')[1]
				if info.startswith("HET"):
					varscan_HET = info.split('=')[1]
				if info.startswith("HOM"):
					varscan_HOM = info.split('=')[1]
				if info.startswith("NC"):
					varscan_NC = info.split('=')[1]
		
			varscan_AC=	int(varscan_HET)+2*int(varscan_HOM)
			varscan_AN=	2*(int(varscan_HET)+int(varscan_HOM)+int(varscan_WT))

			try:
				if varscan_gt == '1/1':
					varscan_SB = 0
				else:
					varscan_SB = -10*math.log10(stats.fisher_exact([[varscan_rfow, varscan_rrev], [varscan_afow, varscan_arev]])[1])
			except:
				varscan_SB= '.'

			try:
				symmetricalRatio  = ((varscan_rfow+1.0)*(varscan_arev+1.0))/((varscan_rrev+1.0)*(varscan_afow+1.0)) + ((varscan_rrev+1.0)*(varscan_afow+1.0))/((varscan_rfow+1.0)*(varscan_arev+1.0))
				refRatio = min(varscan_rfow + 1.0, varscan_rrev + 1.0) / max(varscan_rfow + 1.0, varscan_rrev + 1.0)
				altRatio = min(varscan_afow + 1.0, varscan_arev + 1.0) / max(varscan_afow + 1.0, varscan_arev + 1.0)
				varscan_SOR = math.log(symmetricalRatio) + math.log(refRatio) - math.log(altRatio)
			except:
				varscan_SOR='.'
		else:
			varscan_gt = '.'
			varscan_dp = '.'
			varscan_ro = '.'
			varscan_ao = '.'
			varscan_rfow = '.'
			varscan_afow = '.'
			varscan_rrev = '.'
			varscan_arev = '.'
			varscan_GQ = '.' 
			varscan_PL = '.' 
			varscan_MQ = '.'
			varscan_QB = '.'
			varscan_SB= '.'
			varscan_SOR = '.'
			varscan_AC = '.'
			varscan_AN = '.'

		
		GT = calcola_GT([gatk_gt, freeb_gt, varscan_gt])
		DP = calcola_DP([gatk_dp, freeb_dp, varscan_dp], 'median')
		AO = calcola_AO([gatk_ao, freeb_ao, varscan_ao], 'median')
		RO = calcola_RO([gatk_ro, freeb_ro, varscan_ro], 'median')
		AD = str(RO) + ',' + str(AO)
		GQ = calcola_GQ([gatk_GQ, freeb_GQ, varscan_GQ], 'median')
		QB = calcola_QB([gatk_QB, freeb_QB, varscan_QB], 'median')
		MQ = calcola_MQ([gatk_MQ, freeb_MQ, varscan_MQ], 'median')
		SB = calcola_SB([gatk_SB, freeb_SB, varscan_SB], 'median')
		SOR = calcola_SOR([gatk_SOR, freeb_SOR, varscan_SOR], 'median')
		AC = calcola_AC([gatk_AC, freeb_AC, varscan_AC], 'max')
		AN = calcola_AN([gatk_AN, freeb_AN, varscan_AN], 'max')

		try:
			AF = round(float(AO)/float(DP),3)
		except:
			AF = '.'
		
		INFO = ';'.join(['AC='+str(AC), 'AN='+str(AN)]  + INFO_gatk_info + [re.sub('\|','/',INFO_gatk_format)] + INFO_freeb_info + [re.sub('\|','/',INFO_freeb_format)] + INFO_varscan_info + [re.sub('\|','/',INFO_varscan_format)])
		QUAL = '.'
		FILTER = '.'
		FORMAT = 'GT:DP:AD:RO:AO:AF:QB:MQ:GQ:SB:SOR'
		SAMPLE = ':'.join([str(GT),str(DP),str(AD),str(RO),str(AO),str(AF),str(QB),str(MQ),str(GQ),str(SB),str(SOR)])

		if not SAMPLE.startswith('.'):
			out.write('\t'.join([chrom, pos, id, ref, alt, QUAL, FILTER, INFO, FORMAT, SAMPLE]) +'\n')
