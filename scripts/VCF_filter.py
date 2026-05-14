import argparse


def filter_extract(tags, format, sample):

	formatspl = format.split(':')
	GT,DP,AD,RO,AO,AF,QB,MQ,GQ,SB,SOR = sample.split(':')
	
	filters = []

	if GT in ['./.', '0/0']:
		filters += ['GT-WT']
	else:
		try:
			if float(DP) < 20.0:
				filters += ['LOW-DP']
		except:
			filters += ['LOW-DP']

		try:
			if float(AO) < 10.0:
				filters += ['LOW-AD']
		except:
			filters += ['LOW-AD']

		try: 	
			if float(AF) < 0.30:
				filters += ['LOW-FREQ']
		except:
			filters += ['LOW-FREQ']

		try:
			if float(MQ) < 40.0:
				filters += ['LOW-MAPQUAL']
		except:
			filters += ['LOW-MAPQUAL']

		try:	
			if float(QB) < 15.0:
				filters += ['LOW-BASEQUAL']
		except:
			filters += ['LOW-BASEQUAL']

		try:
			if float(SB) > 60.0:
				filters += ['HIGH-FS']
		except:
			filters += ['HIGH-FS']

		try:
			if SOR != '.' and float(SOR) > 3.0:
				filters += ['HIGH-SOR']
		except:
			filters += ['HIGH-SOR']

	if filters == []:
		filters = ['PASS']	

	#print('GT ',GT,'DP ', DP, 'AD ',AD ,'RO ',RO ,'AO ',AO ,'AF ',AF ,'QB ',QB,'MQ ',MQ,'GQ ',GQ, 'SB ',SB,'SOR ',SOR, filters)
	return filters	

if __name__ == '__main__':

	parser = argparse.ArgumentParser('VCF filtering using FORMAT information')
	parser.add_argument('--vcf', help="vcf")
	parser.add_argument('--format', help="Comma separated FORMAT fields to report", default='GT,DP,RO,AO,AF,QB,MQ,GQ,SB,SOR')
	parser.add_argument('-o', '--out',help="Output file")
	parser.add_argument('--DP',help="Coverage threshold", default=20.0)
	parser.add_argument('--AD',help="Allele depth threshold", default=10.0)
	parser.add_argument('--AF',help="Allele frequency threshold", default=0.30)
	parser.add_argument('--MQ',help="Mapping quality threshold", default=40.0)
	parser.add_argument('--QB',help="Base quality thresold", default=15.0)
	parser.add_argument('--SB',help="Strand Bias thresold", default=60.0)
	parser.add_argument('--SOR',help="SOR thresold", default=3.0)
	
	global opts
	global sample_name

	opts = parser.parse_args()

	header = []
	vars = {}

	vcf = open(opts.vcf,'r')

	format_tags = opts.format.split(',')

	out = open(opts.out,'w')

	
	filter_header = ['##FILTER=<ID=GT-WT,Description=>"Genotype: wildtype (0/0) or unknown (./.)".>',
	'##FILTER=<ID=LOW-DP,Description=>"Coverage depth < '+ str(int(opts.DP)) + '".>',
	'##FILTER=<ID=LOW-AD,Description=>"Allele depth < '+ str(int(opts.AD)) + '".>',
	'##FILTER=<ID=LOW-FREQ,Description=>"Allele frequency < '+ str(opts.AF) + '".>',
	'##FILTER=<ID=LOW-MAPQUAL,Description=>"Mapping quality < '+ str(opts.MQ) + '".>',
	'##FILTER=<ID=LOW-BASEQUAL,Description=>"Mapping quality < '+ str(opts.QB) + '".>',
	'##FILTER=<ID=HIGH-FS,Description=>"Base quality < '+ str(opts.QB) + '".>',
	'##FILTER=<ID=HIGH-SB,Description=>"Strand Bias > '+ str(opts.SB) + '".>',
	'##FILTER=<ID=HIGH-SOR,Description=>"SOR > '+ str(opts.SOR) + '".>',
	'##FILTER=<ID=PASS,Description=>"Passing filters".>']


	for line in vcf:
		line = line.rstrip()
		if line.startswith('##'):
			out.write(line + '\n')
		elif line.startswith('#CHROM'):
			for f in filter_header: out.write(f + '\n')
			out.write(line + '\n')
			sample_name = line.split('\t')[-1]
		else:
			chrom, pos, id, ref, alt, qual, filter, info, format, sample_format = line.split('\t')
			try:
				outfilter = ';'.join(filter_extract(format_tags, format, sample_format))
			except Exception as e:
				print(e, line)
				continue
			
			outvar = [chrom, pos, id, ref, alt, qual, outfilter, info, format, sample_format]
			out.write('\t'.join(outvar) + '\n')	

