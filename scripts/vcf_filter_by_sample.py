import argparse


if __name__ == '__main__':

	parser = argparse.ArgumentParser('Sample Extraction from multisample VCF')

	parser.add_argument('-i','--vcf',help="input vcf file")
	parser.add_argument('-s','--samplename',help="sample to extract")
	parser.add_argument('-o','--out',help="output file")

	global opts

	opts = parser.parse_args()

	vcf = open(opts.vcf,'r')
	out = open(opts.out,'w')

	
	for line in vcf:

		line = line.rstrip()
		if line.startswith('##'):

			out.write(line +'\n')
		elif line.startswith('#CHROM'):
			header = line.split('\t')
			
			try:
				sample_header = '\t'.join(header[:9] + [opts.samplename])
				out.write(sample_header +'\n')
			except Exception as E:
				print('error:    ' + line)
				raise
		else:
			var = line.split('\t')[:9]
			try:
				sample = line.split('\t')[header.index(opts.samplename)]
				var = '\t'.join(var[:9] + [sample])
				if sample.startswith('0/0'):
					continue
				out.write(var +'\n')
			except Exception as E:
				print('error:    ' + line)
				raise
	vcf.close()
	out.close()	