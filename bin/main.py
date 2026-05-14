import argparse
import subprocess
import json
import os
import textwrap
import random as rm
import datetime
import pysam
import random as r
import regex as re
import time

#import pipeline as pipeline
#import functions as f


if __name__ == '__main__':


	print('a')
	time.sleep(3)

	subprocess.call('bash',shell=True)

	# parser = argparse.ArgumentParser('Helper v.1:')
	# parser.add_argument('-v', '--version', action='version', version='Powercall v3.2.0')

	# parser.add_argument('-c', '--cfg', help="Configuration file in json format")
	# parser.add_argument('-s', '--samplesheet', help="Samplesheet that contains filepaths and samples associated", required=True)
	# parser.add_argument('-d', '--design', help="Design of the NGS experiment [Enrichment,Amplicon].",choices=['Enrichment','Amplicon'])
	# parser.add_argument('-p', '--panel', help="The name of the used for the analysis")
	# parser.add_argument('-a', '--analysis', help="Type of analysis [Germline (Multisample), GermlineSS (Singlesample), SomaticCC (Case-Control), Somatic (only Case)].", choices=['Germline', 'GermlineSS','SomaticCC','Somatic'], default='Germline')
	# parser.add_argument('-id','--run_id', help="Run id [YYYYMMDD_Run_NRUN_PANEL}", required=True)
	# parser.add_argument('-w', '--workdir', help="Working Directory. Use this option if you want to work in a precise directory. Default: '/home/run_id'", default=None)
	# parser.add_argument('--workflow', help="String that indicates which steps the analysis must do: A-> Alignment, R-> AddOrReplaceReadGroups, M-> MarkDuplicates, I-> IndelRealigner, B-> BaseRecalibrator, V-> Variant Calling, F-> Features Extraction, E-> Annotation. Es: --start AMIBVFE indicates all steps (like --start ALL), --start MIBV starts from MarkDuplicates and ends to Variant Calling. Default: ALL ", default='ALL')
	# parser.add_argument('-BP', '--GATKBestPractices', help="GATK Best practices workflow", action='store_true')

	# start_time = datetime.datetime.now()
	# success = subprocess.call('clear')
	
	# global opts
	# opts = parser.parse_args()

	# dirs=dict()
	
	# if opts.cfg != None:
	# 	cfg = json.loads((open(opts.cfg).read()).encode('utf8'))
	# else:
	# 	cfg = json.loads((open('/'.join(os.path.dirname(os.path.abspath(__file__)).split('/')[:-1]) + '/configs/Powercall.default.cfg.json').read()).encode('utf8'))
	
	# if opts.workdir != None:
	# 	work_dir = opts.workdir
	# else:
	# 	work_dir = opts.run_id

	# dirs = f.init_dirs(work_dir,opts)
	# f.makedirs([work_dir, work_dir+'/STORAGE', work_dir+'/OUTPUT', dirs['storage'], dirs['out'], dirs['delete'], dirs['log'], ])

	# design,target_list,target_bed,transcripts_list,cnv_target_list,cnv_target_bed,cnv_ref_ploidy,cnv_ref_calls = f.panel_check(opts.panel,cfg)

	# if opts.design != None:
	# 	design = opts.design

	# workflow = opts.workflow
	# if workflow == 'ALL':
	# 	workflow = 'ARMIBVFEC'

	# if design == 'Amplicon':
	# 	workflow=re.sub('MIB','',workflow)
	# 	workflow=re.sub('M','',workflow)

	# if opts.GATKBestPractices:
	# 	workflow=re.sub('I','',workflow)

	# if opts.analysis == 'Germline':
	# 	pipeline.Pipeline_Germline_Multisample(workflow,opts.samplesheet,design,opts.panel,dirs,cfg,opts,target_list,target_bed,transcripts_list,cnv_target_list,cnv_target_bed,cnv_ref_ploidy,cnv_ref_calls)

	# if opts.analysis == 'GermlineSS':
	# 	pipeline.Pipeline_Germline_Singlesample(workflow,opts.samplesheet,design,opts.panel,dirs,cfg,opts,target_list,target_bed,transcripts_list,cnv_target_list,cnv_target_bed,cnv_ref_ploidy,cnv_ref_calls)

	# elif opts.analysis == 'SomaticCC':
	# 	pipeline.Pipeline_Somatic_Case_Control(workflow,opts.samplesheet,design,opts.panel,dirs,cfg,opts,target_list,target_bed,transcripts_list,cnv_target_list,cnv_target_bed,cnv_ref_ploidy,cnv_ref_calls)

	# elif opts.analysis == 'Somatic':
	# 	pipeline.Pipeline_Somatic(workflow,opts.samplesheet,design,opts.panel,dirs,cfg,opts,target_list,target_bed,transcripts_list,cnv_target_list,cnv_target_bed,cnv_ref_ploidy,cnv_ref_calls)

	# elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
	# print("\nTime elapsed: %d min, %d sec" % elapsed_time)
