import argparse
import os


if __name__ == '__main__':

	parser = argparse.ArgumentParser('crea i samplesheet dei bam dalle cartelle contenute in una directory')
	parser.add_argument('-f', '--folder', help="Folder che contiene le cartelle delle run")
	parser.add_argument('--out_path', help="Cartella in uscita dove vengono stampati i samplesheet")
	parser.add_argument('--file_type', help="Quale tipo di file inserire nel samplesheet , BAM, FASTQ")

	global opts
	opts = parser.parse_args()
	for root, dirs, files in os.walk(opts.folder):
		for run_id in dirs:
			dir = opts.folder + '/' + run_id
			samplesheet = open(opts.out_path + '/'+run_id+'.samplesheet','w')
			for file_name in os.listdir(dir):

				if file_name.endswith(".bam"):
					file = dir + '/' + file_name
					sample_id = file_name.split('.')[0]
					samplesheet.write(sample_id+'\t'+file+'\n')

			samplesheet.close()