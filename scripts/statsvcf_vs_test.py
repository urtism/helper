import argparse

def main():
	parser = argparse.ArgumentParser('aggiunge le annotazioni fornite nel file -f (una per riga) al file di input -i in un formato tab delimited in output -o')

	parser.add_argument('-i','--vcf',help="file vcf delle varianti presenti nel campione")
	parser.add_argument('-v','--test_vcf',help="file vcf delle varianti da valutare trovate dai variant caller")
	parser.add_argument('-s','--samplename',help="neme del campione presente nel vcf test")
	parser.add_argument('-o','--out',help="file di outout con le statistiche")

	global opts

	opts = parser.parse_args()

	vcf = open(opts.vcf,'r')
	varvcf = dict()
	stats = dict()
	stats['TP'] = 0
	stats['FP'] = 0
	stats['TN'] = 0
	stats['FN'] = 0

	toprint = []
	for line in vcf:
		line=line.strip()
		if line.startswith('#'):
			continue
		else:
			chr,pos,id,ref,alt,qual,filter,info,format,sample = line.split('\t')
			varid = '\t'.join([chr,pos,ref.upper(),alt.upper()])
			gt = sample.split(':')[format.split(':').index('GT')]
			if gt == '1/0':
				gt = '0/1'
			varvcf[varid] = gt

	vcf.close()
	vcf = open(opts.test_vcf,'r')

	for line in vcf:
		line=line.strip()
		if line.startswith('##'):
			continue
		if line.startswith('#CHROM'):
			sampleindex = line.split('\t').index(opts.samplename)
		else:
			if [chr,pos,id,ref,alt,qual,filter,info,format] == line.split('\t')[:9]:
				continue
			else:
				chr,pos,id,ref,alt,qual,filter,info,format = line.split('\t')[:9]
				sample = line.split('\t')[sampleindex]
				gt = sample.split(':')[format.split(':').index('GT')]
				if gt == '1/0':
					gt = '0/1'
				varid = '\t'.join([chr,pos,ref.upper(),alt.upper()])
				if varid in varvcf.keys():
					if gt == varvcf[varid]:
						stats['TP'] += 1
					else:
						stats['FN'] += 1
						toprint += [varid+'\t'+varvcf[varid]]
					del varvcf[varid]
				elif gt == '0/1' or gt == '1/1':
					stats['FP'] += 1

	vcf.close()

	for varid in varvcf.keys():
		toprint += [varid+'\t0/0']
		stats['FN'] += 1

	out = open(opts.out,'w')

	out.write('\t'.join(['SAMPLE','TP','FP','TN','FN'])+'\n')
	out.write('\t'.join([opts.samplename,str(stats['TP']),str(stats['FP']),str(stats['TN']),str(stats['FN'])])+'\n')
	for v in toprint:
		out.write(v+'\n')

main()
