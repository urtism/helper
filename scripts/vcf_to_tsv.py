import argparse


def format_extract(tags, format, sample):

	formatspl = format.split(':')
	samplespl = sample.split(':')
	report = []
	report_tags = []
	for tag in tags:
		try:
			report += [samplespl[formatspl.index(tag)]]
		except Exception as E:
			print(E) 
			report += ['.']
	if 'FT' in formatspl:
		ft = samplespl[formatspl.index('FT')]
	else:
		ft = ''

	return report,ft

def info_extract(tags, info):

	infospl = info.split(';')
	infos = {}
	for i in infospl:
		try:
			infos[i.split('=')[0]] = i.split('=')[-1]
		except Exception as E:
			print(E)

	report = []
	report_tags = []
	for tag in tags:
		if tag in infos.keys():
			report += [infos[tag]]
		
		elif tag.split(':')[0] == 'GATK_FORMAT':

			try:
				formatTagindex = infos['GATK_FORMAT'].split(':').index(tag.split(':')[-1])
				report += [infos['GATK_'+sample_name].split(':')[formatTagindex]]
			except Exception as E:
				#print(E)
				report += ['.']
			
		elif tag.split(':')[0] == 'FREEB_FORMAT':
			try:
				formatTagindex = infos['FREEB_FORMAT'].split(':').index(tag.split(':')[-1])
				report += [infos['FREEB_'+sample_name].split(':')[formatTagindex]]
			except Exception as E:
				#print(E)
				report +=  ['.']

		elif tag.split(':')[0] == 'VARSCAN_FORMAT':
			try:
				formatTagindex = infos['FREEB_FORMAT'].split(':').index(tag.split(':')[-1])
				report += [infos['FREEB_'+sample_name].split(':')[formatTagindex]]
			except Exception as E:
				#print(E)
				report += ['.']
		else:
			report += ['.']

	return report

def readtag_file(file):
	tag_file = open(file, 'r')

	format_tags = []
	info_tags = []
	ann_tags = []

	for line in tag_file:
		line = line.rstrip()

		field, tag = line.split('\t')
		if field.upper() == 'FORMAT':
			format_tags += [tag]

		elif field.upper() == 'INFO':
			info_tags += [tag]

	return format_tags, info_tags

if __name__ == '__main__':

	parser = argparse.ArgumentParser('Report VCF variants in TSV or Excell format')

	parser.add_argument('--vcf', help="vcf")
	parser.add_argument('--format', help="Comma separated FORMAT fields to report", default='GT,DP,RO,AO,AF,QB,MQ,GQ,SB,SOR')
	parser.add_argument('--info', help="Comma separated INFO fields to report", default='AC,AN')
	parser.add_argument('--tag_file', help="file containing a list of fields to report. \
		The list must have the TAG_NAME and the FILD_NAME (tab separated) format (e.g. FORMAT 	DP, INFO	AC, ANN	HGVSc). \
		Each row must contains just one field. Using --tag_file excludes --format and --info input.", default= None)
	parser.add_argument('-o', '--out',help="Output file")
	
	global opts
	global sample_name

	opts = parser.parse_args()

	header = []
	vars = {}

	vcf = open(opts.vcf,'r')

	if opts.tag_file:
		format_tags, info_tags= readtag_file(opts.tag_file)
	else:
		format_tags = opts.format.split(',')
		info_tags = opts.info.split(',')


	out = open(opts.out,'w')
	out.write('\t'.join(['CHROM', 'POS', 'ID', 'REF', 'ALT', 'FILTER'] + format_tags + info_tags) +'\n')


	for line in vcf:
		line = line.rstrip()
		if line.startswith('##'):
			continue
		elif line.startswith('#CHROM'):
			header = line
			sample_name = header.split('\t')[-1]
		else:
			chrom, pos, id, ref, alt, qual, filter, info, format, sample_format = line.split('\t')
			outformat, ft = format_extract(format_tags, format, sample_format)
			if ft != '':
				if filter =='PASS':
					filter = ft
				else:
					filter += ';'+ft
			outvar = [chrom, pos, sample_name, ref, alt, filter]
			outinfo = info_extract(info_tags, info)
			if outformat != []:
				outvar += outformat
			if outinfo != []:
				outvar += outinfo


			out.write('\t'.join(outvar) + '\n')	

