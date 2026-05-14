#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Apr  29 10:29:33 2025

Alignmnet QC for single sample

@author: antonio
"""

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Oct 19 15:29:28 2024

@author: user
"""

import argparse
import os
import pysam
import math
import subprocess
import statistics
import re
from concurrent.futures import ProcessPoolExecutor, as_completed




def main():
    
    parser = argparse.ArgumentParser()
    parser.add_argument("bam_path",type=str,help="bam_path")
    parser.add_argument("out_path",type=str,help="output_path. Specify path to folder to store results in")
    parser.add_argument("bed_path",type=str,help="specify  path to bed file containing regions to target")
    parser.add_argument("-a","--annotated_bed",default=False,action="store_true",help="target bed file contains names of targeted regions")
    parser.add_argument("-q","--min_mq",type=int,default=1,help="Min mapping quality for reads to be included in the evaluation")
    parser.add_argument("-t","--threads",type=int,default=4,help="Max processes to be exectute at the same time")

    args = parser.parse_args()
    
    

    # --------------------------------------------------------------------------------------------------  SETUP
    
    bam_path = args.bam_path
    out_path = args.out_path
    bed_path = args.bed_path
    annotated_bed = args.annotated_bed
    min_mq = args.min_mq
    
    os.makedirs(out_path,exist_ok=True)
    
    
    
    
    
    
    # ---------------------------------------------------------------------------------- Sequencing QC
    
    quality_cutoffs = [10, 15, 20, 30]

    # Count total reads
    total_reads = sum(1 for _ in pysam.AlignmentFile(bam_path, "rb").fetch(until_eof=True))
    chunk_size = math.ceil(total_reads / args.threads)

    index_ranges = [(i * chunk_size, min((i + 1) * chunk_size, total_reads)) for i in range(args.threads)]

    total = 0
    counts_total = {q: 0 for q in quality_cutoffs}
    lengths_total = []

    with ProcessPoolExecutor() as executor:
        futures = [
            executor.submit(analyze_reads_chunk, bam_path, start, end, quality_cutoffs)
            for (start, end) in index_ranges
        ]

        for future in as_completed(futures):
            n, c, l = future.result()
            total += n
            for q in quality_cutoffs:
                counts_total[q] += c[q]
            lengths_total.extend(l)

    # Compute N50
    lengths_total.sort()
    total_bases = sum(lengths_total)
    cum = 0
    N50 = 0
    for l in lengths_total:
        cum += l
        if cum >= total_bases / 2:
            N50 = l
            break

    # Write results
    with open(args.out_path+"/sequencing_QC.tsv", "w") as f:
        header = ["total_reads", "N50"] + [f"%>Q{q}" for q in quality_cutoffs]
        row = [str(total), str(N50)] + [f"{(counts_total[q] / total * 100):.2f}" if total > 0 else "0.00" for q in quality_cutoffs]
        f.write("\t".join(header) + "\n")
        f.write("\t".join(row) + "\n")

    N_reads_total = total
    
    

    
    
    
    
    
    
    # ----------------------------------------------------------------------------- ALIGNMENT QC
    
    target = Target()
    region_infos = read_bed(bed_path,annotated_bed)
    
    with ProcessPoolExecutor(max_workers=args.threads) as executor:
        futures = [
            executor.submit(process_region, region_info, bam_path, out_path, min_mq)
            for region_info in region_infos
        ]

        for future in as_completed(futures):
            region = future.result()
            if region.len > 1:
                target.add_region(region)  # raise exception if occurred
    
    store_aggregate_data(target, out_path, N_reads_total)
    
    
    # ----------------------------------------------------------------------------
    
    
    
    


def analyze_reads_chunk(bam_path, start_idx, end_idx, quality_cutoffs):
    total = 0
    counts = {q: 0 for q in quality_cutoffs}
    lengths = []

    bamfile = pysam.AlignmentFile(bam_path, "rb")
    for i, read in enumerate(bamfile.fetch(until_eof=True)):
        if i < start_idx:
            continue
        if i >= end_idx:
            break

        if not read.query_qualities:
            continue
        total += 1
        lengths.append(read.query_length)

        p_error = [10**(-q/10) for q in read.query_qualities]
        phred = -10 * math.log10(sum(p_error) / len(p_error))

        for q in quality_cutoffs:
            if phred >= q:
                counts[q] += 1

    bamfile.close()
    return total, counts, lengths





def read_bed(bed_path,annotated_bed):
    
    region_infos = []
    
    with open(bed_path,'r') as file:
        for line in file:
            fields = line.split("\t")
            if annotated_bed:
                name = fields[3].strip()
            else:
                name = None
            chrm = fields[0]
            start = int(fields[1])+1 # stick to 1-based format of sam and vcf (bed start is 0-based)
            end = int(fields[2]) # bed end is 1-based
            
            region = {"chrm" : chrm, "start" : start, "end" : end, "name" : name}
            region_infos.append(region)
    
    return region_infos
                
            



def process_region(ri,bam_path,out_path,min_mq):
    
    region = Region(ri["chrm"],ri["start"],ri["end"],ri["name"])
        
    # - Retrive data
    command = ["samtools view",
        bam_path,
        region.get_coordinates(),
        "-F 1796 -q "+str(min_mq)]
    command = " ".join(command)
    aligned_reads = subprocess.check_output(command + " 2>/dev/null", shell=True).decode().strip()
    
    if aligned_reads == "": # no coverage
        return region
        
    aligned_reads = aligned_reads.split("\n")
    j = 0
    for read in aligned_reads:
        j += 1
        try:
            info = read.split("\t")
            id = info[0]
            chrm = info[2]
            start = int(info[3])
            alg_qual = info[4]
            cigar = info[5]
            sequence = info[9] 
            #base_qual = info[10]
            
            region.add_read(Read(id,chrm,start,alg_qual,cigar,sequence))
        except:
            print("BAD format of samtool output. Error in coverage.py/process_region()")
            print(f"region = {region.id}")
            print(f"read = {read}")
            print(f"total reads = {len(aligned_reads)}")
            print(f"j = {j}")
    return region




def store_aggregate_data(target,out_path,N_reads_total):

    with open(out_path+"/alignment_QC_data.tsv",'w') as file:
        
        file.write("\t".join(StoreFormat.fields_data))
        
        file.write("\n"+"\t".join(target.aggregate_data(N_reads_total)))
        for region in target.list_regions():
            file.write("\n"+"\t".join(region.aggregate_data(N_reads_total)))


        











class Target:
    def __init__(self):
        self.regions = {}
    
    def add_region(self,region):
        self.regions[region.id] = (region)

    def list_regions(self):
        return self.regions.values()



    def aggregate_data(self,n_tot_reads):

        # reads aligned on multiple region should be correctly handled by dictionary logic
        aligned_reads = {}
        for region in self.list_regions():
            for read in region.list_reads():
                aligned_reads[read.id] = read


        data = {}

        data[StoreFormat.region_id] = "target"

        total_len = 0
        for region in self.list_regions():
            total_len += region.len
        data[StoreFormat.region_len] = total_len

        total_covered = 0
        total_covered10 = 0
        total_covered20 = 0
        total_covered50 = 0
        total_covered100 = 0
        total_covered200 = 0
        for region in self.list_regions():
            total_covered += region.compute_covered_bases(1)
            total_covered10 += region.compute_covered_bases(10)
            total_covered20 += region.compute_covered_bases(20)
            total_covered50 += region.compute_covered_bases(50)
            total_covered100 += region.compute_covered_bases(100)
            total_covered200 += region.compute_covered_bases(200)

        data[StoreFormat.coverage] = total_covered / total_len
        data[StoreFormat.coverage10] = total_covered10 / total_len
        data[StoreFormat.coverage20] = total_covered20 / total_len
        data[StoreFormat.coverage50] = total_covered50 / total_len
        data[StoreFormat.coverage100] = total_covered100 / total_len
        data[StoreFormat.coverage200] = total_covered200 / total_len

        total_depths = []
        for region in self.list_regions():
            total_depths += region.list_depths()
        mean_depth = statistics.mean(total_depths)
        std_depth = statistics.stdev(total_depths)

        data[StoreFormat.mean_depth] = mean_depth
        data[StoreFormat.uniformity] = sum([1 for d in total_depths if d >= mean_depth - std_depth])/total_len

        data[StoreFormat.n_aligned_reads] = len(aligned_reads)
        data[StoreFormat.fraction_aligned_reads] = len(aligned_reads)/n_tot_reads
        [data[StoreFormat.mean_read_len],data[StoreFormat.N50],data[StoreFormat.mean_read_alg_qual]] = self.compute_reads_statistics(aligned_reads)

        return StoreFormat.format_aggregate_data(data)


    def compute_reads_statistics(self,aligned_reads):
        
        if len(aligned_reads) == 0: # no reads aligned
            return [float('nan'),float('nan'),float('nan')]
        
        lens = []
        alg_quals = []

        for read in aligned_reads.values():
            lens.append(read.len)
            alg_quals.append(read.alg_qual)

        lens.sort()
        total_len = sum(lens)
        mean_read_len = total_len/len(aligned_reads)

        mean_read_alg_qual = sum(alg_quals)/len(aligned_reads)

        half_total_len = total_len/2
        cum = 0
        N50 = 0
        for r in lens:
            cum += r
            if cum >= half_total_len:
                N50 = r
                break
        return [mean_read_len,N50,mean_read_alg_qual]










class Region:
    # start and and are in 1-based coordinates
    # the interval is semiopen, like in bed format.
    def __init__(self,chrm,start,end,name=None):
        self.chrm = chrm
        self.start = start
        self.end = end
        self.len = self.end-self.start
        self.aligned_reads = {}
        
        if not name is None:
            self.id = name
            self.name = name
        else:
            self.id = self.chrm+":"+str(self.start)+"-"+str(self.end)
            self.name = ""
        
        self.genomic_positions = {}
        for i in range(start,end):
            self.genomic_positions[i] = GenomicPosition(chrm,i)
    
    
    def add_read(self,read):
        self.aligned_reads[read.id] = read
        
        if read.start >= self.end:
            print("-----------   read starts out of region")
            print (f"read.start = {read.start}")
            print (f"self.start = {self.start}")
            print (f"self.end = {self.end}")
            exit(1)
        
        cigar = read.cigar
        read_idx = 0
        ref_idx = read.start
        
        while len(cigar) > 0 and ref_idx < self.end:
            [n,x,cigar] = self.consume(cigar)
            
            if x == "M" or x == "=" or x == "X":
                if not ref_idx + n < self.start:
                    for i in range(n):
                        if ref_idx + i >= self.start and ref_idx + i < self.end:
                            self.genomic_positions[ref_idx + i].add_read(read.alg_qual)
                read_idx += n
                ref_idx += n
            
            elif x == "D":
                if not ref_idx + n < self.start:
                    # b1 = ord(read.base_qual[read_idx]) - 33
                    # b2 = ord(read.base_qual[read_idx-1]) - 33
                    # bq = int((b1 + b2)/2)
                    # bq = chr(bq + 33)
                    for i in range(n):
                        if ref_idx + i >= self.start and ref_idx + i < self.end:
                            self.genomic_positions[ref_idx + i].add_read(read.alg_qual)
                ref_idx += n
            
            elif x == "I" or x == "S":
                read_idx += n
            
            elif x == "N":
                ref_idx += n
            
            elif x == "H" or x == "P":
                pass
            
    
    def locate(self,pos):
        if pos < self.start:
            return -1
        if pos >= self.end:
            return 1
        else:
            return 0
        
    def consume(self,cigar):
        match = re.match(r'(\d+)([a-zA-Z])', cigar)
        if match:
            number = int(match.group(1))  # Convert number to integer
            letter = match.group(2)
            remaining_string = cigar[len(match.group(0)):]  # Remove extracted part from the string
            return number, letter, remaining_string
        return None, None, cigar  # Return original string if no match
        
    def list_positions(self):
        return self.genomic_positions.values()
    def list_reads(self):
        return self.aligned_reads.values()
    
    def get_coordinates(self):
        return self.chrm+":"+str(self.start)+"-"+str(self.end-1)
    def get_id(self):
        return self.id


    def aggregate_data(self,n_tot_reads):
        data = {}

        data[StoreFormat.region_id] = self.id

        data[StoreFormat.region_len] = self.len

        data[StoreFormat.coverage] = self.compute_coverage(1)
        data[StoreFormat.coverage10] = self.compute_coverage(10)
        data[StoreFormat.coverage20] = self.compute_coverage(20)
        data[StoreFormat.coverage50] = self.compute_coverage(50)
        data[StoreFormat.coverage100] = self.compute_coverage(100)
        data[StoreFormat.coverage200] = self.compute_coverage(200)

        [data[StoreFormat.mean_depth],data[StoreFormat.uniformity]] = self.compute_depth_statistics()

        data[StoreFormat.n_aligned_reads] = len(self.aligned_reads)
        data[StoreFormat.fraction_aligned_reads] = len(self.aligned_reads)/n_tot_reads
        [data[StoreFormat.mean_read_len],data[StoreFormat.N50],data[StoreFormat.mean_read_alg_qual]] = self.compute_reads_statistics()

        return StoreFormat.format_aggregate_data(data)



    def compute_covered_bases(self,treshold):
        n = 0
        for pos in self.genomic_positions.values():
            if pos.depth >= treshold:
                n += 1
        return n

    def compute_coverage(self,treshold):
        return self.compute_covered_bases(treshold)/self.len

    def list_depths(self):
        depths = []
        for pos in self.genomic_positions.values():
            depths.append(pos.depth)
        return depths

    def compute_depth_statistics(self):
        
        depths = self.list_depths()

        mean_depth = statistics.mean(depths)
        std_depth = statistics.stdev(depths)
        uniform_bases = 0
        for pos in self.genomic_positions.values():
            if pos.depth >= mean_depth - std_depth:
                uniform_bases += 1
        uniformity = uniform_bases/self.len

        return [mean_depth,uniformity]


    def compute_reads_statistics(self):
        
        if len(self.aligned_reads) == 0: # no reads aligned
            return [float('nan'),float('nan'),float('nan')]
        
        lens = []
        alg_quals = []

        for read in self.list_reads():
            lens.append(read.len)
            alg_quals.append(read.alg_qual)
        
        lens.sort()
        total_len = sum(lens)
        mean_read_len = total_len/len(self.aligned_reads)

        mean_read_alg_qual = sum(alg_quals)/len(self.aligned_reads)

        half_total_len = total_len/2
        cum = 0
        N50 = 0
        for r in lens:
            cum += r
            if cum >= half_total_len:
                N50 = r
                break
        return [mean_read_len,N50,mean_read_alg_qual]







class GenomicPosition:
    def __init__(self,chrm,pos):
        self.chrm = chrm
        self.pos = pos
        self.depth = 0
        #self.base_qual = []
        self.alg_qual = []
    def get_coordinates(self):
        return self.chrm+":"+str(self.pos)+"-"+str(self.pos)
    
    def add_read(self,alg_qual):
        #self.base_qual.append(base_qual)
        self.alg_qual.append(int(alg_qual))
        self.depth += 1
    
    
    
class Read:
    def __init__(self,id,chrm,start,alg_qual,cigar,sequence):
        self.id = id
        self.chrm = chrm
        self.start = int(start)
        self.alg_qual = int(alg_qual)
        self.cigar = cigar
        self.sequence = sequence
        #self.base_qual = base_qual
        self.len = len(sequence)
        
        
        
class StoreFormat:
    fields_depth = ["CHROM","POS","depth","alg_qual","region"]
    fields_reads = ["id","CHROM","POS","alg_qual","CIGAR","sequence","len","region"]

    region_id = "region_id"
    region_len = "region_len"
    coverage = "coverage"
    coverage10 = "coverage10"
    coverage20 = "coverage20"
    coverage50 = "coverage50"
    coverage100 = "coverage100"
    coverage200 = "coverage200"
    mean_depth = "mean_depth"
    uniformity = "uniformity"
    n_aligned_reads = "n_aligned_reads"
    fraction_aligned_reads = "fraction_aligned_reads"
    mean_read_len = "mean_read_len"
    N50 = "N50"
    mean_read_alg_qual = "mean_read_alg_qual"

    fields_data = [
        region_id,
        region_len,
        coverage,
        coverage10,
        coverage20,
        coverage50,
        coverage100,
        coverage200,
        mean_depth,
        uniformity,
        n_aligned_reads,
        fraction_aligned_reads,
        mean_read_len,
        N50,
        mean_read_alg_qual
        ]

    def format_aggregate_data(data):
        format = [
            str(data[StoreFormat.region_id]),
            str(data[StoreFormat.region_len]),
            str(data[StoreFormat.coverage]),
            str(data[StoreFormat.coverage10]),
            str(data[StoreFormat.coverage20]),
            str(data[StoreFormat.coverage50]),
            str(data[StoreFormat.coverage100]),
            str(data[StoreFormat.coverage200]),
            str(data[StoreFormat.mean_depth]),
            str(data[StoreFormat.uniformity]),
            str(data[StoreFormat.n_aligned_reads]),
            str(data[StoreFormat.fraction_aligned_reads]),
            str(data[StoreFormat.mean_read_len]),
            str(data[StoreFormat.N50]),
            str(data[StoreFormat.mean_read_alg_qual])
            ]
        return format


main()