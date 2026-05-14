
import argparse
import scipy.stats as stats
import numpy as np

class Variantcaller():
	GT = '.'
	RO = '.'
	AO = '.'
	DP = '.'
	AF = '.'
	GQ = '.'
	PGT = '.'
	PID = '.'
	PID ='.'
	FStBias = '.'
	StOR = '.'
	STR = '0'
	PON = '.'
	CONTQ = '.'
	ECNT = '.'
	GERMQ = '.'
	MBQ_ref, MBQ_alt  = '.', '.'
	MFRL_ref, MFRL_alt = '.', '.'
	MMQ_ref, MMQ_alt = '.', '.'
	MPOS = '.'
	POPAF = '.'
	PON = '1'
	RPA_ref, RPA_alt = '.', '.'
	RU = '.'
	STR = '0'
	SEQQ = '.'
	STRANDQ = '.'
	STRQ = '.'
	tumor_lod = '.'

def get_info_gatk(info,format,tumor,normal):
	'''estrae le informazioni dal vcf di mutect'''
	mutect = Variantcaller()

	mutect.GT = tumor[format.index('GT')]
	if mutect.GT == '0|1' or mutect.GT == '1|0':
		mutect.GT = '0/1'
	if len(mutect.GT.split('/')) > 2 :
		mutect.GT = '0/1'

	[mutect.RO, mutect.AO] = [int(a) for a in tumor[format.index('AD')].split(',')]
	mutect.DP = mutect.AO + mutect.RO
	mutect.AF = round(float(mutect.AO)/ float(mutect.DP),4)

	try:
		mutect.GQ=float(tumor[format.index('GQ')])
	except:
		mutect.GQ='.'
	try:
		mutect.PGT=tumor[format.index('PGT')]
	except:
		mutect.PGT='.'
	try:
		mutect.PID=tumor[format.index('PID')]
	except:
		mutect.PID='.'

	try:
		mutect.RO_f, mutect.RO_r, mutect.AO_f, mutect.AO_r = tumor[format.index('SB')].split(',')
	except:
		print(tumor)

	R = (float(mutect.RO_f)+1) * (float(mutect.AO_r)+1) / (float(mutect.RO_r)+1) * (float(mutect.AO_f)+1)
	SymmetricRatio = R + 1/R
	RefRatio = min((float(mutect.RO_f)+1),(float(mutect.RO_r)+1)) / max((float(mutect.RO_f)+1),(float(mutect.RO_r)+1))
	AltRatio = min((float(mutect.AO_f)+1),(float(mutect.AO_r)+1)) / max((float(mutect.AO_f)+1),(float(mutect.AO_r)+1))
	mutect.StOR = np.log(SymmetricRatio) + np.log(RefRatio) - np.log(AltRatio)

	mutect.DP_r = float(mutect.RO_r) + float(mutect.AO_r)
	mutect.DP_f = float(mutect.RO_f) + float(mutect.AO_f)

	if opts.amplicon:
		if min(mutect.DP_r,mutect.DP_f)/(mutect.DP_r+mutect.DP_f) >= 0.05:
			mutect.FStBias=1-stats.fisher_exact([[mutect.RO_f, mutect.RO_r], [mutect.AO_f, mutect.AO_r]])[1]
		else:
			mutect.FStBias='1.0'
	else:
		if min(mutect.DP_r,mutect.DP_f)/(mutect.DP_r+mutect.DP_f) > 0:
			mutect.FStBias=1-stats.fisher_exact([[mutect.RO_f, mutect.RO_r], [mutect.AO_f, mutect.AO_r]])[1]
		else:
			mutect.FStBias='1.0'
		
	for ind in info:
		if ind.startswith("CONTQ="):
			mutect.CONTQ = ind.split('=')[1]
		if ind.startswith("ECNT="):
			mutect.ECNT = ind.split('=')[1]
		if ind.startswith("GERMQ="):
			mutect.GERMQ = ind.split('=')[1]
		if ind.startswith("MBQ="):
			mutect.MBQ_ref, mutect.MBQ_alt = ind.split('=')[1].split(',')
		if ind.startswith("MFRL="):
			mutect.MFRL_ref, mutect.MFRL_alt = ind.split('=')[1].split(',')
		if ind.startswith("MMQ="):
			mutect.MMQ_ref, mutect.MMQ_alt = ind.split('=')[1].split(',')
		if ind.startswith("MPOS="):
			mutect.MPOS = ind.split('=')[1]
		if ind.startswith("POPAF="):
			mutect.POPAF = ind.split('=')[1]
		if ind.startswith("PON"):
			mutect.PON = '1'
		if ind.startswith("RPA="):
			mutect.RPA_ref, mutect.RPA_alt = ind.split('=')[1].split(',')
		if ind.startswith("RU="):
			mutect.RU = ind.split('=')[1]
		if ind == "STR":
			mutect.STR = '1'
		if ind.startswith("SEQQ="):
			mutect.SEQQ = float(ind.split('=')[1])
		if ind.startswith("STRANDQ="):
			mutect.STRANDQ = float(ind.split('=')[1])
		if ind.startswith("STRQ="):
			mutect.STRQ = float(ind.split('=')[1])
		if ind.startswith("TLOD="):
			mutect.tumor_lod = float(ind.split('=')[1])

	return mutect


def print_vcf(varianti):
	varianti_vcf=open(opts.out+ '.vcf','w')
	varianti_vcf.write('##fileformat=VCFv4.2\n'+'#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLES\n')
	for variante in varianti.keys():
		var_vcf=variante.split('\t')[0]+'\t'+variante.split('\t')[1]+'\t.\t'+variante.split('\t')[2]+'\t'+variante.split('\t')[3]+'\t.\t.\t.\t.\t.'
		varianti_vcf.write(var_vcf+ '\n')
	varianti_vcf.close()

def read_features_set(file_listafeatures):
	lista_features = open(file_listafeatures,'r')
	header = []
	features_set = []

	for line in lista_features:
		line = line.rstrip().split('\t')[0]
		if line.startswith('#'):
			continue
		else:
			header += [line]
			features_set += ['features.'+line]

	lista_features.close()
	return features_set, header

def print_var(features,features_variante,outfile):
	
	features_eval = [str(eval(feat)) for feat in features_variante]

	var = features.chr + '\t' + features.pos + '\t' + opts.tumor + '\t' + features.ref + '\t' + features.alt + '\t' + features.filter + '\t' + '\t'.join(features_eval)
	
	outfile.write(var + '\n')
	

def read(vcf_file,sample_name,features_variante,outfile):
	'''legge il vcf e splitta le varie sezioni'''
	with open(vcf_file) as vcf:
		for line in vcf:
			line = line.rstrip()
			if line.startswith('##'):
				continue
			elif line.startswith('#CHROM'):
				header = line.split("\t")
			else:
				chrom, pos, id, ref, alt, qual, filter, info, format = line.split("\t")[:9]
				info = info.split(";")
				format = format.split(":")

				sample = line.split("\t")[header.index(sample_name)].split(":")
				
				
				if sample[0].startswith('.'):
					continue
				else:
					features = get_info_gatk(info,format,sample)
					features.chr = chrom
					features.pos = pos
					features.ref = ref
					features.alt = alt
					features.qual = qual
					features.filter = filter
					print_var(features,features_variante,outfile)
		vcf.close()

if __name__ == '__main__':

	parser = argparse.ArgumentParser('Parse VCF output from Variant callers to output a variant_dataset.tsv.')
	parser.add_argument('-g', '--gatk', help="gatk vcf output file name")
	#parser.add_argument('-d', '--vardict', help="Vardict vcf output file name")
	#parser.add_argument('-v', '--varscan', help="Varscan vcf output file name")
	#parser.add_argument('-f', '--freebayes', help="Freebayes vcf output file name")
	parser.add_argument('-s','--sample', help="Sample name")
	parser.add_argument('-a','--amplicon', help="Amplicon design", action='store_true')
	parser.add_argument('-o', '--out', help="file name in output. It returns file_name.features.tsv and file_name.vcf ")
	parser.add_argument('-l', '--listaFeatures', help="Features list to extract")

	global opts 
	opts = parser.parse_args()

	#callers = [opts.mutect,opts.varscan,opts.vardict,opts.freebayes]
	outfile = outfile = open(opts.out+ '.tsv','w')

	features_set, header = read_features_set(opts.listaFeatures)

	outfile.write('CHROM\tPOS\tID\tREF\tALT\tFILTER\t' + '\t'.join(header) + '\n')

	read(opts.mutect,opts.sample,features_set,outfile)
