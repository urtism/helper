
ifile = '/home/jarvis/git/Helper/target/CONN_EXT_V1/CONN_EXT.3362101_Covered.bed'

ofile = '/home/jarvis/git/Helper/target/CONN_EXT_V1/CONN_EXT_ext100.3362101.bed'
outfile = open(ofile,'w')

with open(ifile,'r') as infile:
	for line in infile:
		chr,start,stop,gene = line.rstrip().split('\t')
		nstart = str(int(start)-100)
		nstop = str(int(stop)+100)
		nline = '\t'.join([chr,nstart,nstop,gene])
		outfile.writelines(nline+'\n')
outfile.close()

