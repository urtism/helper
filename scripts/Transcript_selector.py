import argparse
import re
import numpy

def transcr_extractor(transcr_list):
    transcr_l = open(transcr_list,'r')
    transcrs = []
    for transcr in transcr_l: 
        if not transcr.startswith('#'):
            transcrs += [transcr.rstrip()]
    transcr_l.close()
    return transcrs

def split_annotation(anninfo,header,transcrs):
    
    for ann in anninfo.split(','):
        ann_split = ann.split('|')
        try:
            tr = ann_split[header.index('Feature')].split('.')[0]
            gene = ann_split[header.index('SYMBOL')].split('.')[0]
        except:
            continue
        if tr in transcrs:
            return ann
        else:
            continue

    for ann in anninfo.split(','):
        ann_split = ann.split('|')
        try:
            canonical = ann_split[header.index('CANONICAL')].split('.')[0]
            if canonical == 'YES':
                return ann
        except:
            continue
    return None

if __name__ == '__main__':
    parser = argparse.ArgumentParser('Estrare i trascritti contenuti nella lista filtrando tutti gli altri. Prende in input un vcf annotato e restituisce in output un vcf annotato filtrato.')
    
    parser.add_argument('-i','--vcf',help="file delle varianti annotate in formato vcf")
    parser.add_argument('-t','--trs_list',help="lista di trascritti da mantenere")
    parser.add_argument('-o','--out',help="file di output")
    
    global opts
    
    opts = parser.parse_args()
    
    vcf = open(opts.vcf,'r')
    out = open(opts.out,'w')

    transcrs = transcr_extractor(opts.trs_list)

    for line in vcf:
        line = line.rstrip()

        if line.startswith('##INFO=<ID=ANN') or line.startswith('##INFO=<ID=CSQ'):
            start = line.find('Allele')
            end = line.find('">')
            header_ann = (line[start:end]).split('|')
            out.write(line+'\n')
        elif line.startswith('#'):
            out.write(line+'\n')
        else:
            chrom = line.split('\t')[0]
            pos = line.split('\t')[1]
            id = line.split('\t')[2]
            ref = line.split('\t')[3]
            alt =  line.split('\t')[4]
            var_id = '\t'.join([chrom,pos,ref,alt])
            info = line.split('\t')[7].split(';')
            anninfo = re.sub('ANN=','',info[-1])
            if anninfo != '' and info[-1] != '.':
                info[-1] = split_annotation(anninfo,header_ann,transcrs)
            else:
                info[-1] = None

            if info[-1] is not None:
                info[-1] = 'ANN='+ info[-1] 
                toprint = [chrom, pos, id, ref, alt, line.split('\t')[5], line.split('\t')[6], ';'.join(info)] + line.split('\t')[8:]
                out.write('\t'.join(toprint)+'\n')
    vcf.close()     
    out.close()