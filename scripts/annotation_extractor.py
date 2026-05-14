import argparse
import re
import numpy

def estrai_annotazione():
    vcf = open(opts.vcf,'r')
    out = open(opts.out,'w')
    tsv = open(opts.tsv,'r')
    tags = open(opts.tag_list,'r')
    var_list = dict()
    tag_list=[]
    
    for var in tsv:
        var = var.rstrip()

        if var.startswith('CHROM'):
            header=var

        else:
            chrom = var.split('\t')[0]
            pos = var.split('\t')[1]
            id = var.split('\t')[2]
            ref = var.split('\t')[3]
            alt =  var.split('\t')[4]
            
            var_id = '\t'.join([chrom,pos,ref,alt])
            var_list[var_id] = var.split('\t')

    for tag in tags:
        tag=tag.rstrip()
        if tag.startswith('#'):
            continue
        else:
            tag_list+=[tag]

    tags.close()
    header_tot = header.split('\t') + tag_list
    out.write('\t'.join(header_tot)+'\n')

    for line in vcf:
        line = line.rstrip()

        if line.startswith('##INFO=<ID=ANN') or line.startswith('##INFO=<ID=CSQ'):
            start = line.find('Allele')
            end = line.find('">')
            header_ann = (line[start:end]).split('|')
            continue
        elif line.startswith('#'):
            continue
            
        else:
            chrom = line.split('\t')[0]
            pos = line.split('\t')[1]
            id = line.split('\t')[2]
            ref = line.split('\t')[3]
            alt =  line.split('\t')[4]
            var_id = '\t'.join([chrom,pos,ref,alt])
            
            if var_id in var_list.keys():
                info = (line.split('\t')[7]).split('=')[1]
                info_split = info.split('|')

                tags = var_list.get(var_id)
                
                for tag in tag_list:              
                    new_tag = info_split[header_ann.index(tag)]               
                    if new_tag == '':
                        new_tag = '.'
                    tags = tags + [new_tag]
                
                var_list[var_id] = tags
                out.write('\t'.join(var_list.get(var_id))+'\n')


def tags_extractor(tag_list):
    tag_l = open(tag_list,'r')
    tags = []
    for tag in tag_l:
        if not tag.startswith('#'):
            tags += [tag.rstrip()]
    tag_l.close()
    return tags

def transcr_extractor(transcr_list):
    transcr_l = open(transcr_list,'r')
    transcrs = []
    for transcr in transcr_l:
        if not transcr.startswith('#'):
            transcrs += [transcr.rstrip()]
    transcr_l.close()
    return transcrs

def calculateImpactValue(n):
    if n=='HIGH': return 3
    elif n=='MODERATE': return 2
    elif n=='MODIFIER': return 1
    else: return 0

def split_annotation(anninfo,header,transcrs):
    ann_array = [[],[],[]]
    for ann in anninfo.split(','):
        ann_split = ann.split('|')
        tr = ann_split[header.index('Feature')].split('.')[0]
        #print(ann_split[header.index('Feature')].split('.'))
        transcrs_mod = [trn.split('.')[0] for trn in transcrs]
        #print(tr)
        if tr in transcrs_mod:
            ann_array[0] = ann_split

        if ann_split[header.index('CANONICAL')]:
            ann_array[1] += [ann_split]      
        ann_array[2] += [ann_split]

    impact = 0
    for ann in ann_array[1]:
        ann_impact = calculateImpactValue(ann[header.index('IMPACT')])
        if ann_impact > impact:
            impact = ann_impact
            ann_array[1][0] = ann

    if ann_array[0] == []:
        if ann_array[1] == []:
            ann_array[0] = ann_array[2][0]
        else:
            ann_array[0] = ann_array[1][0]

    return ann_array
    
def tag_modifier(trs,tag,header):


        if tag == 'SIFT4G':
            try:
                SIFT4G_scores = trs[header.index('SIFT4G_score')].split('&')  
                while '.' in SIFT4G_scores: SIFT4G_scores.remove('.')
                argmax = numpy.argmin(SIFT4G_scores)
                SIFT4G_preds = trs[header.index('SIFT4G_pred')].split('&')
                while '.' in SIFT4G_preds: SIFT4G_preds.remove('.')   
                if SIFT4G_preds[argmax] == 'T':
                    SIFT4G_pred = 'tolerated'
                elif SIFT4G_preds[argmax] == 'D':
                    SIFT4G_pred = 'deleterious'
                else:
                    SIFT4G_pred = ''
                tag = SIFT4G_pred + '(' +SIFT4G_scores[argmax] + ')'
                if tag == '()': tag = '.'
            except Exception as e:
                tag = '.'

        elif tag == 'Polyphen2_HDIV':
            try:
                Polyphen2_HDIV_scores = trs[header.index('Polyphen2_HDIV_score')].split('&')  
                while '.' in Polyphen2_HDIV_scores: Polyphen2_HDIV_scores.remove('.')
                argmax = numpy.argmax(Polyphen2_HDIV_scores)
                Polyphen2_HDIV_preds = trs[header.index('Polyphen2_HDIV_pred')].split('&')
                while '.' in Polyphen2_HDIV_preds: Polyphen2_HDIV_preds.remove('.')   
                if Polyphen2_HDIV_preds[argmax] == 'P':
                    Polyphen2_HDIV_pred = 'possibly_damaging'
                elif Polyphen2_HDIV_preds[argmax] == 'D':
                    Polyphen2_HDIV_pred = 'probably_damaging'
                elif Polyphen2_HDIV_preds[argmax] == 'B':
                    Polyphen2_HDIV_pred = 'benign'
                else:
                    Polyphen2_HDIV_pred = ''
                tag = Polyphen2_HDIV_pred + '(' +Polyphen2_HDIV_scores[argmax] + ')'
                if tag == '()': tag = '.'
            except Exception as e:
                tag = '.'

        elif tag == 'Polyphen2_HVAR':
            try:
                Polyphen2_HVAR_scores = trs[header.index('Polyphen2_HVAR_score')].split('&')  
                while '.' in Polyphen2_HVAR_scores: Polyphen2_HVAR_scores.remove('.')
                argmax = numpy.argmax(Polyphen2_HVAR_scores)
                Polyphen2_HVAR_preds = trs[header.index('Polyphen2_HVAR_pred')].split('&')
                while '.' in Polyphen2_HVAR_preds: Polyphen2_HVAR_preds.remove('.')   
                if Polyphen2_HVAR_preds[argmax] == 'P':
                    Polyphen2_HVAR_pred = 'possibly_damaging'
                elif Polyphen2_HVAR_preds[argmax] == 'D':
                    Polyphen2_HVAR_pred = 'probably_damaging'
                elif Polyphen2_HVAR_preds[argmax] == 'B':
                    Polyphen2_HVAR_pred = 'benign'
                else:
                    Polyphen2_HVAR_pred = ''
                tag = Polyphen2_HVAR_pred + '(' +Polyphen2_HVAR_scores[argmax] + ')'
                if tag == '()': tag = '.'
            except Exception as e:
                tag = '.'

        elif tag == 'MaxEntScan':
            try:
               MaxEntScan_alt = float(trs[header.index('MaxEntScan_alt')])
               MaxEntScan_ref = float(trs[header.index('MaxEntScan_ref')])
               MaxEntScan_diff = float(trs[header.index('MaxEntScan_diff')])
               tag = str(round(MaxEntScan_diff / max(MaxEntScan_alt, MaxEntScan_ref),3)) + '(' + str(MaxEntScan_ref) + '|' + str(MaxEntScan_alt)+')' 
            except Exception as e:
                tag = '.'

        elif tag == 'LRT':
            try:
                LRT_pred = trs[header.index('LRT_pred')]
                if LRT_pred == 'D':
                    tag = 'Damaging'
                elif LRT_pred == 'N':
                    tag = 'Neutral'
                elif LRT_pred == 'U':
                    tag = 'Unknown'
                else:
                    tag = '.'
            except Exception as e:
                tag = '.'
        
        elif tag == 'MutationTaster':
            try:
                MutationTaster_scores = trs[header.index('MutationTaster_score')].split('&')  
                while '.' in MutationTaster_scores: MutationTaster_scores.remove('.')
                argmax = numpy.argmax(MutationTaster_scores)
                MutationTaster_preds = trs[header.index('MutationTaster_pred')].split('&')
                while '.' in MutationTaster_preds: MutationTaster_preds.remove('.')   
                if MutationTaster_preds[argmax] == 'A' or MutationTaster_preds[argmax] == 'D':
                    MutationTaster_pred = 'Disease Causing'
                elif MutationTaster_preds[argmax] == 'N' or MutationTaster_preds[argmax] == 'P':
                    MutationTaster_pred = 'Polymorphism'
                else:
                    MutationTaster_pred = ''
                tag = MutationTaster_pred + '(' +MutationTaster_scores[argmax] + ')'
                if tag == '()': tag = '.'
            except Exception as e:
                tag = '.'
        elif tag == 'MutationAssessor':
            try:
                MutationAssessor_scores = trs[header.index('MutationAssessor_score')].split('&')  
                while '.' in MutationAssessor_scores: MutationAssessor_scores.remove('.')
                argmax = numpy.argmax(MutationAssessor_scores)
                MutationAssessor_preds = trs[header.index('MutationAssessor_pred')].split('&')
                while '.' in MutationAssessor_preds: MutationAssessor_preds.remove('.')   
                if MutationAssessor_preds[argmax] == 'H':
                    MutationAssessor_pred = 'High'
                elif MutationAssessor_preds[argmax] == 'M':
                    MutationAssessor_pred = 'Medium'
                elif MutationAssessor_preds[argmax] == 'L' or MutationAssessor_preds[argmax] == 'N' :
                    MutationAssessor_pred = 'Low'
                else:
                    MutationAssessor_pred = ''
                tag = MutationAssessor_pred + '(' +MutationAssessor_scores[argmax] + ')'
                if tag == '()': tag = '.'
            except Exception as e:
                tag = '.'
        
        elif tag == 'FATHMM':
            try:
                FATHMM_scores = trs[header.index('FATHMM_score')].split('&')  
                while '.' in FATHMM_scores: FATHMM_scores.remove('.')
                argmax = numpy.argmax(FATHMM_scores)
                FATHMM_preds = trs[header.index('FATHMM_pred')].split('&')
                while '.' in FATHMM_preds: FATHMM_preds.remove('.')   
                if FATHMM_preds[argmax] == 'D':
                    FATHMM_pred = 'Damaging'
                elif FATHMM_preds[argmax] == 'T':
                    FATHMM_pred = 'Tolerated'
                else:
                    FATHMM_pred = ''
                tag = FATHMM_pred + '(' +FATHMM_scores[argmax] + ')'
                if tag == '()': tag = '.'
            except Exception as e:
                tag = '.'


        elif tag == 'FATHMM-XF':
            try:
                fathmm_XF_coding_scores = trs[header.index('fathmm-XF_coding_score')].split('&')
                while '.' in fathmm_XF_coding_scores: fathmm_XF_coding_scores.remove('.')
                argmax = numpy.argmax(fathmm_XF_coding_scores)
                fathmm_XF_coding_preds = trs[header.index('fathmm-XF_coding_pred')].split('&')
                while '.' in fathmm_XF_coding_preds: fathmm_XF_coding_preds.remove('.')   
                if fathmm_XF_coding_preds[argmax] == 'D':
                    fathmm_XF_coding_pred = 'Damaging'
                elif fathmm_XF_coding_preds[argmax] == 'N':
                    fathmm_XF_coding_pred = 'Tolerated'
                else:
                    fathmm_XF_coding_pred = ''
                tag = fathmm_XF_coding_pred + '(' +str(round(float(fathmm_XF_coding_scores[argmax]),3)) + ')'
                if tag == '()': tag = '.'
            except Exception as e:
                tag = '.'


        elif tag == 'PROVEAN':
            try:
                PROVEAN_scores = trs[header.index('PROVEAN_score')].split('&')
                while '.' in PROVEAN_scores: PROVEAN_scores.remove('.')
                argmax = numpy.argmin(PROVEAN_scores)
                PROVEAN_preds = trs[header.index('PROVEAN_pred')].split('&')
                while '.' in PROVEAN_preds: PROVEAN_preds.remove('.')   
                if PROVEAN_preds[argmax] == 'D':
                    PROVEAN_pred = 'Damaging'
                elif PROVEAN_preds[argmax] == 'N':
                    PROVEAN_pred = 'Neutral'
                else:
                    PROVEAN_pred = ''
                tag = PROVEAN_pred + '(' + PROVEAN_scores[argmax] + ')'
                if tag == '()': tag = '.'
            except Exception as e:
                tag = '.'


        elif tag == 'MetaSVM':
            try:
                MetaSVM_scores = trs[header.index('MetaSVM_score')].split('&')
                while '.' in MetaSVM_scores: MetaSVM_scores.remove('.')
                argmax = numpy.argmin(MetaSVM_scores)
                MetaSVM_preds = trs[header.index('MetaSVM_pred')].split('&')
                while '.' in MetaSVM_preds: MetaSVM_preds.remove('.')   
                if MetaSVM_preds[argmax] == 'D':
                    MetaSVM_pred = 'Damaging'
                elif MetaSVM_preds[argmax] == 'T':
                    MetaSVM_pred = 'Tolerated'
                else:
                    MetaSVM_pred = ''
                tag = MetaSVM_pred + '(' + MetaSVM_scores[argmax] + ')'
                if tag == '()': tag = '.'
            except Exception as e:
                tag = '.'


        elif tag == 'M-CAP':
            try:
                M_CAP_scores = trs[header.index('M-CAP_score')].split('&')
                while '.' in M_CAP_scores: M_CAP_scores.remove('.')
                argmax = numpy.argmin(M_CAP_scores)
                M_CAP_preds = trs[header.index('M-CAP_pred')].split('&')
                while '.' in M_CAP_preds: M_CAP_preds.remove('.')   
                if M_CAP_preds[argmax] == 'D':
                    M_CAP_pred = 'Damaging'
                elif M_CAP_preds[argmax] == 'T':
                    M_CAP_pred = 'Tolerated'
                else:
                    M_CAP_pred = ''
                tag = M_CAP_pred + '(' + M_CAP_scores[argmax] + ')'
                if tag == '()': tag = '.'
            except Exception as e:
                tag = '.'
        else:
            tag = '.'
        return tag



if __name__ == '__main__':
    parser = argparse.ArgumentParser('aggiunge le annotazioni fornite nel file -f (una per riga) al file di input -i in un formato tab delimited in output -o')
    
    parser.add_argument('-i','--vcf',help="file delle varianti annotate in formato vcf")
    parser.add_argument('-l','--tag_list',help="lista di annotation features da aggiungere: una per riga",default=None)
    parser.add_argument('-f','--tsv',help="file tab delimited a cui aggiungere le annotation features",default=None)
    parser.add_argument('-t','--trs_list',help="lista di trascritti su cui splittare le annotazioni",default=None)
    parser.add_argument('-o','--out',help="file di output")
    parser.add_argument('-O','--other_transcripts',help="file di output containing variants in other transcripts",default=None)
    parser.add_argument('-S', '--split', help="abilita lo split delle varianti per i trascritti contenuti in list", action='store_true')
    
    global opts
    
    opts = parser.parse_args()    
    vcf = open(opts.vcf,'r')
    out = open(opts.out,'w')
    tsv = open(opts.tsv,'r')

    if opts.other_transcripts:
        other = open(opts.other_transcripts,'w')

    tag_list = tags_extractor(opts.tag_list)

    if opts.trs_list != None and opts.trs_list != '' and opts.trs_list != 'None':
        transcrs = transcr_extractor(opts.trs_list)
    else:
        transcrs = []

    var_list = dict()
    
    for var in tsv:
        var = var.rstrip()

        if var.startswith('CHROM'):
            header=var

        else:
            chrom = var.split('\t')[0]
            pos = var.split('\t')[1]
            id = var.split('\t')[2]
            ref = var.split('\t')[3]
            alt =  var.split('\t')[4]
            
            var_id = '\t'.join([chrom,pos,ref,alt])
            var_list[var_id] = var.split('\t')

    for line in vcf:
        line = line.rstrip()


        if line.startswith('##INFO=<ID=ANN') or line.startswith('##INFO=<ID=CSQ'):
            start = line.find('Allele')
            end = line.find('">')
            header_ann = (line[start:end]).split('|')
            t_ann = []
            for t in tag_list:
                if t == 'AF': t = '1000G_AF'
                t_ann += [t]
            header_tot = header.split('\t') + t_ann
            out.write('\t'.join(header_tot)+'\n')
            try:
                other.write('\t'.join(header_tot)+'\n')
            except:
                continue
            continue
        elif line.startswith('#'):
            continue
        else:
            tags = []
            chrom = line.split('\t')[0]
            pos = line.split('\t')[1]
            id = line.split('\t')[2]
            ref = line.split('\t')[3]
            alt =  line.split('\t')[4]
            var_id = '\t'.join([chrom,pos,ref,alt])
            info = line.split('\t')[7]
            anninfo = ''

            for i in info.split(';'):
                if i.startswith('ANN=') or i.startswith('CSQ='):
                    anninfo = re.sub('ANN=','',i)

            if var_id in var_list.keys():

                if anninfo != '':
                    annotations = split_annotation(anninfo,header_ann,transcrs)
                    if opts.trs_list != None:
                        main_trs = annotations[0]
                        other_trs = annotations[1] + annotations[2]
                    else:
                        main_trs = annotations[0]
                        other_trs = annotations[1] + annotations[2]
                    
                    for tag in tag_list:
                        try:    
                            new_tag = main_trs[header_ann.index(tag)]
                        except:
                            new_tag = tag_modifier(main_trs,tag,header_ann)
                        #print(tag,new_tag)
                        if new_tag == '':
                            new_tag = '.'
                        tags = tags + [new_tag]
                
                    toprint = var_list[var_id] + tags
                    out.write('\t'.join(toprint)+'\n')

                    if opts.other_transcripts != None:
                        for trs in other_trs:
                            tags = []
                            for tag in tag_list:
                                new_tag = main_trs[header_ann.index(tag)]

                                if new_tag == '':
                                    new_tag = '.'
                                tags = tags + [new_tag]
                            
                            toprint = var_list[var_id] + tags
                            other.write('\t'.join(toprint)+'\n')
    vcf.close()     
    out.close()
    tsv.close()
