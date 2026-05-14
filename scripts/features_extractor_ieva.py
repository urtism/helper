import re
import string
import argparse
import sys
import statistics
import os
import scipy.stats as stats
import numpy as np
import datetime

''' //////////// CLASSI ////////////'''

class Caller():
	GT=''
	AO=''
	RO=''
	AO_f=''
	AO_r=''
	DP_f=''
	DP_r=''
	DP=''
	QB=''
	GQ=''
	Call='0'
	AF=''
	STRBIAS='.'
	FILTER='.'
	AC=''
	AN=''
	STRBIAS_TOT=''
	RF=''

class iEVA():

	SimpleRepeat=''
	SimpleRepeatLength=''
	SimpleRepeatUnit=''
	PseudoNucleotidesComposition=''
	RepeatMasker=''
	gcContent=''
	VariantClass=''

	#bam extraction

	StrandBiasReads=''
	UnMappedReads=''
	MeanMappingQuality=''
	MappingQualityZero=''
	NotPrimaryAlignment=''
	SupplementaryAlignment=''
	NotPairedReads=''
	NotProperPairedReads=''
	AlignmentScore=''
	TotalDupReads=''
	
	#Genotype extraction

	NumberReadDupRef=''
	NumberReadDupAlt=''
	DuplicateReference=''
	DuplicateAlternate=''
	DeltaDuplicate=''
	iEvaDepth=''
	iAlleleDepthiEVA=''
	ReadRef=''
	ReadAlt=''
	MeanRefQscore=''
	MeanAltQscore=''
	RefMeanMappingQuality=''
	AltMeanMappingQuality=''
	TotalDPUnfilter=''
	NumberClippedReadsRef=''
	NumberClippedReadsAlt=''
	ClippedReadsRef=''
	ClippedReadsAlt=''

class Freebayes(Caller):
	
	#PROVENIENTI DALLE INFO
	AO_f_TOT=''
	AO_r_TOT=''
	RO_f_TOT=''
	RO_r_TOT=''
	DP_f_TOT=''
	DP_r_TOT=''
	AB=''
	ABP=''
	AN=''
	AF_TOT=''
	AO_TOT=''
	CIGAR=''
	DP_TOT=''
	DPB_TOT=''
	DPRA_TOT=''
	END_TOT=''
	EPP_TOT=''
	EPPR_TOT=''
	GTI_TOT=''
	LEN=''
	MEANALT=''
	MIN=''
	MQ_A=''
	MQ_R=''
	NS=''
	NUMALT=''
	ODDS=''
	PAIRED=''
	PAIREDR=''
	PAO=''
	PQA=''
	PQR=''
	PRO=''
	QA=''
	QR=''
	RO_TOT=''
	RPL=''
	RPP=''
	RPPR=''
	RPR=''
	RUN=''
	SAP=''
	SRP=''

	#PROVENIENTI DAL FORMAT
	lod=''
	A_QB=''
	R_QB=''

class GATK(Caller):
	#PROVENIENTI DAL FORMAT
	sQD=''
	#PROVENIENTI DALLE INFO
	AF_TOT=''
	BaseQRankSum=''
	ClippingRankSum=''
	DP_TOT=''
	DS=''
	END=''
	ExcessHet=''
	FS=''
	HaplotypeScore=''
	InbreedingCoeff=''
	MLEAC=''
	MLEAF=''
	MQ=''
	MQRankSum=''
	QD=''
	RAW_MQ=''
	ReadPosRankSum='.'
	SOR=''

class Varscan(Caller):

	SDP=''

	ADP=''
	WT=''
	HET=''
	HOM=''
	NC=''

class Features():

	GT_Varscan='.'
	GT_Freebayes='.'
	GT_GATK='.'

	AO_mean='.'
	RO_mean='.'
	AO_median='.'
	RO_median='.'

	DP_mean='.'
	DP_median='.'

	RF_Varscan='.'
	RF_Freebayes='.'
	RF_GATK='.'

	QB_GATK='.'
	QB_Varscan='.'
	QB_Freebayes='.'
	MBQ_mean='.'
	MBQ_median='.'
	
	AF_GATK='0'
	AF_Varscan='0'
	AF_Freebayes='0'
	AF_mean='.'
	AF_median='.'
	
	CallGATK='0'
	CallVarscan='0'
	CallFreebayes='0'
	
	STRBIAS_GATK='.'
	STRBIAS_Varscan='.'
	STRBIAS_Freebayes='.'
	
	STRBIAS_mean='.'
	STRBIAS_median= '.'

	STRBIAS_TOT_GATK='.'
	STRBIAS_TOT_Varscan='.'
	STRBIAS_TOT_Freebayes='.'
	STRBIAS_TOT_mean='.'
	STRBIAS_TOT_median= '.'
	
	FILTER_GATK='.'
	FILTER_Varscan='.'
	FILTER_Freebayes='.'
	FILTER='.'
	
	AC_GATK='.'
	AC_Varscan='.'
	AC_Freebayes='.'
	AC_mean='.'
	AC_median='.'
	AC ='.'

	AN_GATK='.'
	AN_Varscan='.'
	AN_Freebayes='.'
	AN='.'

	#features solo di GATK
	sQD_GATK='.'
	AF_TOT_GATK='.'
	BaseQRankSum_GATK='.'
	ClippingRankSum_GATK='.'
	DP_TOT_GATK='.'
	DS_GATK='.'
	END_GATK='.'
	ExcessHet_GATK='.'
	FS_GATK='.'
	HaplotypeScore_GATK='.'
	InbreedingCoeff_GATK='.'
	MLEAC_GATK='.'
	MLEAF_GATK='.'
	MQ_GATK='.'
	MQRankSum_GATK='.'
	QD_GATK='.'
	RAW_MQ_GATK='.'
	ReadPosRankSum_GATK='.'
	SOR_GATK='.'

	#features solo di Freebayes
	lod_Freebayes='.'
	AO_f_TOT_Freebayes='.'
	AO_r_TOT_Freebayes='.'
	RO_f_TOT_Freebayes='.'
	RO_r_TOT_Freebayes='.'
	DP_f_TOT_Freebayes='.'
	DP_r_TOT_Freebayes='.'
	AB_Freebayes='.'
	ABP_Freebayes='.'
	AF_TOT_Freebayes='.'
	AO_TOT_Freebayes='.'
	CIGAR_Freebayes='.'
	DP_TOT_Freebayes='.'
	DPB_TOT_Freebayes='.'
	DPRA_TOT_Freebayes='.'
	END_TOT_Freebayes='.'
	EPP_TOT_Freebayes='.'
	EPPR_TOT_Freebayes='.'
	GTI_TOT_Freebayes='.'
	LEN_Freebayes='.'
	MEANALT_Freebayes='.'
	MIN_Freebayes='.'
	MQ_A_Freebayes='.'
	MQ_R_Freebayes='.'
	NS_Freebayes='.'
	NUMALT_Freebayes='.'
	ODDS_Freebayes='.'
	PAIRED_Freebayes='.'
	PAIREDR_Freebayes='.'
	PAO_Freebayes='.'
	PQA_Freebayes='.'
	PQR_Freebayes='.'
	PRO_Freebayes='.'
	QA_Freebayes='.'
	QR_Freebayes='.'
	RO_TOT_Freebayes='.'
	RPL_Freebayes='.'
	RPP_Freebayes='.'
	RPPR_Freebayes='.'
	RPR_Freebayes='.'
	RUN_Freebayes='.'
	SAP_Freebayes='.'
	SRP_Freebayes='.'

	A_QB_Freebayes='.'
	R_QB_Freebayes='.'

	#features solo di Varscan
	SDP_Varscan=''

	#features di iEVA
	#Reference extraction arguments
	SimpleRepeat_iEVA='.'
	SimpleRepeatLength_iEVA='.'
	SimpleRepeatUnit_iEVA='.'
	PseudoNucleotidesComposition_iEVA='.'
	RepeatMasker_iEVA='.'
	gcContent_iEVA='.'
	VariantClass_iEVA='.'

	#bam extraction

	StrandBiasReads_iEVA='.'
	UnMappedReads_iEVA='.'
	MeanMappingQuality_iEVA='.'
	MappingQualityZero_iEVA='.'
	NotPrimaryAlignment_iEVA='.'
	SupplementaryAlignment_iEVA='.'
	NotPairedReads_iEVA='.'
	NotProperPairedReads_iEVA='.'
	AlignmentScore_iEVA='.'
	TotalDupReads_iEVA='.'
	
	#Genotype extraction

	NumberReadDupRef_iEVA='.'
	NumberReadDupAlt_iEVA='.'
	DuplicateReference_iEVA='.'
	DuplicateAlternate_iEVA='.'
	DeltaDuplicate_iEVA='.'
	iEvaDepth_iEVA='.'
	iAlleleDepth_iEVA='.'
	ReadRef_iEVA='.'
	ReadAlt_iEVA='.'
	MeanRefQscore_iEVA='.'
	MeanAltQscore_iEVA='.'
	RefMeanMappingQuality_iEVA='.'
	AltMeanMappingQuality_iEVA='.'
	TotalDPUnfilter_iEVA='.'
	NumberClippedReadsRef_iEVA='.'
	NumberClippedReadsAlt_iEVA='.'
	ClippedReadsRef_iEVA='.'
	ClippedReadsAlt_iEVA='.'


''' //////////// FUNZIONI ////////////'''

def get_info_iEVA(chrom,pos,ref,alt,filter,info,format,sample,ieva):

	if "SBR" in format:
		ieva.StrandBiasReads=sample[format.index("SBR")]
	if "UnMap" in format:
		ieva.UnMappedReads=sample[format.index("UnMap")]
	if "MQ0" in format:
		ieva.MappingQualityZero=sample[format.index("MQ0")]
	if "MMQ" in format:
		ieva.MeanMappingQuality=sample[format.index("MMQ")]
	if "NPA" in format:
		ieva.NotPrimaryAlignment=sample[format.index("NPA")]
	if "SA" in format:
		ieva.SupplementaryAlignment=sample[format.index("SA")]
	if "NP" in format:
		ieva.NotPairedReads=sample[format.index("NP")]
	if "NPP" in format:
		ieva.NotProperPairedReads=sample[format.index("NPP")]
	if "AS" in format:
		ieva.AlignmentScore=sample[format.index("AS")]
	if "TDR" in format:
		ieva.TotalDupReads=sample[format.index("TDR")]

	if "iNDR" in format:
		ieva.NumberReadDupRef=sample[format.index("iNDR")]
	if "iNDA" in format:
		ieva.NumberReadDupAlt=sample[format.index("iNDA")]
	if "iDR" in format:
		ieva.DuplicateReference=sample[format.index("iDR")]
	if "iDA" in format:
		ieva.DuplicateAlternate=sample[format.index("iDA")]
	if "iDDup" in format:
		ieva.DeltaDuplicate=sample[format.index("iDDup")]
	if "iDP" in format:
		ieva.iEvaDepth=sample[format.index("iDP")]
	if "iAD" in format:
		ieva.iAlleleDepth=sample[format.index("iAD")]
	if "iRR" in format:
		ieva.ReadRef=sample[format.index("iRR")]
	if "iRA" in format:
		ieva.ReadAlt=sample[format.index("iRA")]
	if "iQR" in format:
		ieva.MeanRefQscore=sample[format.index("iQR")]
	if "iQA" in format:
		ieva.MeanAltQscore=sample[format.index("iQA")]

	if "TDP" in format:
		ieva.TotalDPUnfilter=sample[format.index("TDP")]
	if "iRMQ" in format:
		ieva.RefMeanMappingQuality=sample[format.index("iRMQ")]
	if "iAMQ" in format:
		ieva.AltMeanMappingQuality=sample[format.index("iAMQ")]
	if "iNCR" in format:
		ieva.NumberClippedReadsRef=sample[format.index("NCR")]
	if "iNCA" in format:
		ieva.NumberClippedReadsAlt=sample[format.index("NCA")]
	if "iCR" in format:
		ieva.ClippedReadsRef=sample[format.index("CR")]
	if "iCA" in format:
		ieva.ClippedReadsAlt=sample[format.index("CA")]

	for el in info:
		if el.startswith('SRL='):
			ieva.SimpleRepeatLength=el.split('=')[1]
		elif el.startswith('SRU='):
			ieva.SimpleRepeatUnit=el.split('=')[1]
		elif el.startswith('SR='):
			ieva.SimpleRepeat=el.split('=')[1]
		elif el.startswith('PNC='):
			ieva.PseudoNucleotidesComposition=el.split('=')[1]
		elif el.startswith('RM='):
			ieva.RepeatMasker=el.split('=')[1]
		elif el.startswith('GC='):
			ieva.gcContent=el.split('=')[1]
		elif el.startswith('VC='):
			ieva.VariantClass=el.split('=')[1]

def get_info_Freebayes(chrom,pos,ref,alt,filter,info,format,sample,freebayes):
	'''estrae le informazioni dal vcf di freebayes'''
	
	freebayes.GT=sample[format.index('GT')]
	if freebayes.GT=='.' :
		freebayes.GT='./.'
	if freebayes.GT=='./.':
		pass
	else:
		freebayes.GQ=sample[format.index('GQ')]
		freebayes.AO=float(sample[format.index('AO')])
		freebayes.RO=float(sample[format.index('RO')])
		#freebayes.DP=freebayes.AO+freebayes.RO
		freebayes.DP=float(sample[format.index('DP')])

		try:
			freebayes.RF=(freebayes.AO+freebayes.RO)/freebayes.DP
		except:
			freebayes.RF='.'

		for ind in info:
			if ind.startswith("SAF="):
				freebayes.AO_f_TOT=float(ind.split('=')[1])
			if ind.startswith("SAR="):
				freebayes.AO_r_TOT=float(ind.split('=')[1])
			if ind.startswith("SRF="):
				freebayes.RO_f_TOT=float(ind.split('=')[1])
			if ind.startswith("SRR="):
				freebayes.RO_r_TOT=float(ind.split('=')[1])
			if ind.startswith("AC="):
				freebayes.AC=ind.split('=')[1]
			if ind.startswith("AB="):
				freebayes.AB=float(ind.split('=')[1])
			if ind.startswith("ABP="):
				freebayes.ABP=float(ind.split('=')[1])
			if ind.startswith("AN="):
				freebayes.AN=ind.split('=')[1]
			if ind.startswith("AF="):
				freebayes.AF_TOT=float(ind.split('=')[1])
			if ind.startswith("AO="):
				freebayes.AO_TOT=float(ind.split('=')[1])
			if ind.startswith("DP="):
				freebayes.DP_TOT=float(ind.split('=')[1])
			if ind.startswith("DPB="):
				freebayes.DPB_TOT=float(ind.split('=')[1])
			if ind.startswith("DPRA="):
				freebayes.DPRA_TOT=float(ind.split('=')[1])
			if ind.startswith("END="):
				freebayes.END_TOT=float(ind.split('=')[1])
			if ind.startswith("EPP="):
				freebayes.EPP_TOT=float(ind.split('=')[1])
			if ind.startswith("EPPR="):
				freebayes.EPPR_TOT=float(ind.split('=')[1])
			if ind.startswith("GTI="):
				freebayes.GTI_TOT=float(ind.split('=')[1])
			if ind.startswith("LEN="):
				freebayes.LEN=float(ind.split('=')[1])
			if ind.startswith("MEANALT="):
				freebayes.MEANALT=float(ind.split('=')[1])
			if ind.startswith("MIN="):
				freebayes.MIN=float(ind.split('=')[1])
			if ind.startswith("MQM="):
				freebayes.MQ_A=float(ind.split('=')[1])
			if ind.startswith("MQMR="):
				freebayes.MQ_R=float(ind.split('=')[1])
			if ind.startswith("NS="):
				freebayes.NS=float(ind.split('=')[1])
			if ind.startswith("NUMALT="):
				freebayes.NUMALT=float(ind.split('=')[1])
			if ind.startswith("ODDS="):
				freebayes.ODDS=float(ind.split('=')[1])
			if ind.startswith("PAIRED="):
				freebayes.PAIRED=float(ind.split('=')[1])
			if ind.startswith("PAIREDR="):
				freebayes.PAIREDR=float(ind.split('=')[1])
			if ind.startswith("PAO="):
				freebayes.PAO=float(ind.split('=')[1])
			if ind.startswith("PQA="):
				freebayes.PQA=float(ind.split('=')[1])
			if ind.startswith("PQR="):
				freebayes.PQR=float(ind.split('=')[1])
			if ind.startswith("PRO="):
				freebayes.PRO=float(ind.split('=')[1])
			if ind.startswith("QA="):
				freebayes.QA=float(ind.split('=')[1])
			if ind.startswith("QR="):
				freebayes.QR=float(ind.split('=')[1])
			if ind.startswith("RO="):
				freebayes.RO_TOT=float(ind.split('=')[1])
			if ind.startswith("RPL="):
				freebayes.RPL=float(ind.split('=')[1])
			if ind.startswith("RPP="):
				freebayes.RPP=float(ind.split('=')[1])
			if ind.startswith("RPPR="):
				freebayes.RPPR=float(ind.split('=')[1])
			if ind.startswith("RPR="):
				freebayes.RPR=float(ind.split('=')[1])
			if ind.startswith("RUN="):
				freebayes.RUN=float(ind.split('=')[1])
			if ind.startswith("SAP="):
				freebayes.SAP=float(ind.split('=')[1])
			if ind.startswith("SRP="):
				freebayes.SRP=float(ind.split('=')[1])


		freebayes.DP_f_TOT=float(freebayes.AO_f_TOT)+float(freebayes.RO_f_TOT)
		freebayes.DP_r_TOT=float(freebayes.AO_r_TOT)+float(freebayes.RO_r_TOT)

		try:
			freebayes.A_QB=float(sample[format.index('QA')])/freebayes.AO
		except:
			freebayes.A_QB='.'
		try:	
			freebayes.R_QB=float(sample[format.index('QR')])/freebayes.RO
		except:
			freebayes.R_QB='.'
		try:	
			freebayes.QB=float(sample[format.index('QA')])/freebayes.AO
		except:
			freebayes.QB='.'


		try:
			gls = [float(x) for x in sample[format.index("GL")].split(",")]
			freebayes.lod = max(gls[i] - gls[0] for i in range(1, len(gls)))
		except:
			freebayes.lod = -1.0
		
		try:
			freebayes.AF = freebayes.AO/freebayes.DP
		except:
			freebayes.AF = '.'

		try:
			freebayes.FS = -10*math.log10(stats.fisher_exact([[freebayes.RO_f_TOT, freebayes.RO_r_TOT], [freebayes.AO_f_TOT, freebayes.AO_r_TOT]])[1])
		except:
			freebayes.FS = '.'

		symmetricalRatio  = ((freebayes.RO_f_TOT+1.0)*(freebayes.AO_r_TOT+1.0))/((freebayes.RO_r_TOT+1.0)*(freebayes.AO_f_TOT+1.0)) + ((freebayes.RO_r_TOT+1.0)*(freebayes.AO_f_TOT+1.0))/((freebayes.RO_f_TOT+1.0)*(freebayes.AO_r_TOT+1.0))
 		refRatio = min(freebayes.RO_f_TOT + 1.0, freebayes.RO_r_TOT + 1.0) / max(freebayes.RO_f_TOT + 1.0, freebayes.RO_r_TOT + 1.0)
 		altRatio = min(freebayes.AO_f_TOT + 1.0, freebayes.AO_r_TOT + 1.0) / max(freebayes.AO_f_TOT + 1.0, freebayes.AO_r_TOT + 1.0)
		try:
			freebayes.SOR = math.log(symmetricalRatio) + math.log(refRatio) – math.log(altRatio)
		except:
			freebayes.SOR='.'

		freebayes.FILTER=filter	
		freebayes.Call=1
	return freebayes

def get_info_GATK(chrom,pos,ref,alt,filter,info,format,sample,GATK):
	'''estrae le informazioni dal vcf di GATK'''
	
	GATK.GT=sample[format.index('GT')]

	if GATK.GT=='./.':
		pass
	else:
		GATK.AO=float((sample[format.index('AD')]).split(',')[1])
		GATK.RO=float((sample[format.index('AD')]).split(',')[0])
		try:
			GATK.DP=float(sample[format.index('DP')])
		except:
			GATK.DP=0.0
			pass
		try:
			GATK.RF=(GATK.AO+GATK.RO)/GATK.DP
		except:
			GATK.RF='.'
		try:
			GATK.AF=GATK.AO/GATK.DP
		except:
			GATK.AF='.'
		GATK.STR='0'
		try:
			GATK.AO_r=float((sample[format.index('SB')]).split(',')[3])
			GATK.AO_f=float((sample[format.index('SB')]).split(',')[2])
			GATK.RO_r=float((sample[format.index('SB')]).split(',')[1])
			GATK.RO_f=float((sample[format.index('SB')]).split(',')[0])

			GATK.DP_r=GATK.AO_r+GATK.RO_r
			GATK.DP_f=GATK.AO_f+GATK.RO_f
		except:
			GATK.AO_r='.'
			GATK.AO_f='.'
			GATK.RO_r='.'
			GATK.RO_f='.'
			GATK.DP_r='.'
			GATK.DP_f='.'

		GATK.QB=sample[format.index('SQD')]

		for ind in info:
			if ind.startswith("AC="):
				GATK.AC=ind.split('=')[1]
			if ind.startswith("AF="):
				GATK.AF_TOT=ind.split('=')[1]
			if ind.startswith("AN="):
				GATK.AN=ind.split('=')[1]
			if ind.startswith("BaseQRankSum="):
				GATK.BaseQRankSum=ind.split('=')[1]
			if ind.startswith("ClippingRankSum="):
				GATK.ClippingRankSum=ind.split('=')[1]
			if ind.startswith("DP="):
				GATK.DP_TOT=ind.split('=')[1]
			if ind.startswith("DS="):
				GATK.DS=ind.split('=')[1]
			if ind.startswith("END="):
				GATK.END=ind.split('=')[1]
			if ind.startswith("ExcessHet="):
				GATK.ExcessHet=ind.split('=')[1]
			if ind.startswith("FS="):
				GATK.FS=ind.split('=')[1]
			if ind.startswith("HaplotypeScore="):
				GATK.HaplotypeScore=ind.split('=')[1]
			if ind.startswith("InbreedingCoeff="):
				GATK.InbreedingCoeff=ind.split('=')[1]
			if ind.startswith("MLEAC="):
				GATK.MLEAC=ind.split('=')[1]
			if ind.startswith("MLEAF="):
				GATK.MLEAF=ind.split('=')[1]
			if ind.startswith("MQ="):
				GATK.MQ=ind.split('=')[1]
			if ind.startswith("MQRankSum="):
				GATK.MQRankSum=ind.split('=')[1]
			if ind.startswith("QD="):
				GATK.QD=ind.split('=')[1]
			if ind.startswith("RAW_MQ="):
				GATK.RAW_MQ=ind.split('=')[1]
			if ind.startswith("ReadPosRankSum="):
				GATK.ReadPosRankSum=ind.split('=')[1]
			if ind.startswith("SOR="):
				GATK.SOR=ind.split('=')[1]

		try:
			GATK.STRBIAS = -10*math.log10(stats.fisher_exact([[GATK.RO_f, GATK.RO_r], [GATK.AO_f, GATK.AO_r]])[1])
		except:
			GATK.STRBIAS= '.'

		symmetricalRatio  = ((GATK.RO_f+1.0)*(GATK.AO_r+1.0))/((GATK.RO_r+1.0)*(GATK.AO_f+1.0)) + ((GATK.RO_r+1.0)*(GATK.AO_f+1.0))/((GATK.RO_f+1.0)*(GATK.AO_r+1.0))
 		refRatio = min(GATK.RO_f + 1.0, GATK.RO_r + 1.0) / max(GATK.RO_f + 1.0, GATK.RO_r + 1.0)
 		altRatio = min(GATK.AO_f + 1.0, GATK.AO_r + 1.0) / max(GATK.AO_f + 1.0, GATK.AO_r + 1.0)

		try:
			GATK.STROR = math.log(symmetricalRatio) + math.log(refRatio) – math.log(altRatio)
		except:
			GATK.STROR='.'

		try:
			GATK.GQ=float(sample[format.index('GQ')])
		except:
			GATK.GQ='.'
		
		GATK.FILTER=filter
		GATK.Call=1
	return GATK
	
def get_info_Varscan(chrom,pos,ref,alt,filter,info,format,sample,varscan):
	'''estrae le informazioni dal vcf di varscan'''
	
	varscan.GT=sample[format.index('GT')]
	if varscan.GT== './.':
		pass
	else:
		varscan.AO=float(sample[format.index('AD')])
		varscan.RO=float(sample[format.index('RD')])
		varscan.DP=float(sample[format.index('DP')])
		varscan.SDP=float(sample[format.index('SDP')])

		varscan.RF=(varscan.RO + varscan.AO)/varscan.SDP
	
	 	for ind in info:
	 		if ind.startswith("ADP"):
				varscan.ADP=ind.split('=')[1]
			if ind.startswith("WT"):
				varscan.WT=ind.split('=')[1]
			if ind.startswith("HET"):
				varscan.HET=ind.split('=')[1]
			if ind.startswith("HOM"):
				varscan.HOM=ind.split('=')[1]
			if ind.startswith("NC"):
				varscan.NC=ind.split('=')[1]
		
		varscan.AC=	int(varscan.HET)+2*int(varscan.HOM)
		varscan.AN=	2*(int(varscan.HET)+int(varscan.HOM)+int(varscan.WT))
					
		varscan.RO_f=float(sample[format.index('RDF')])
		varscan.RO_r=float(sample[format.index('RDR')])
		varscan.AO_f=float(sample[format.index('ADF')])
		varscan.AO_r=float(sample[format.index('ADR')])
		varscan.DP_f=varscan.RO_f + varscan.AO_f
		varscan.DP_r=varscan.RO_r + varscan.AO_r
		varscan.Call=1
		varscan.QB_R=float(sample[format.index('RBQ')])
		varscan.QB_A=float(sample[format.index('ABQ')])
		try:
			varscan.QB=varscan.QB_A
		except:
			varscan.QB='.'
		Varscan.GQ=float(sample[format.index('GQ')])
		
		try:
			varscan.AF=float(varscan.AO/(varscan.DP))
		except:
			varscan.AF='.'

		try:
			varscan.STRBIAS = -10*math.log10(stats.fisher_exact([[varscan.RO_f, varscan.RO_r], [varscan.AO_f, varscan.AO_r]])[1])
		except:
			varscan.STRBIAS= '.'

		symmetricalRatio  = ((varscan.RO_f+1.0)*(varscan.AO_r+1.0))/((varscan.RO_r+1.0)*(varscan.AO_f+1.0)) + ((varscan.RO_r+1.0)*(varscan.AO_f+1.0))/((varscan.RO_f+1.0)*(varscan.AO_r+1.0))
 		refRatio = min(varscan.RO_f + 1.0, varscan.RO_r + 1.0) / max(varscan.RO_f + 1.0, varscan.RO_r + 1.0)
 		altRatio = min(varscan.AO_f + 1.0, varscan.AO_r + 1.0) / max(varscan.AO_f + 1.0, varscan.AO_r + 1.0)

		try:
			varscan.SOR = math.log(symmetricalRatio) + math.log(refRatio) – math.log(altRatio)
		except:
			varscan.SOR='.'

		varscan.FILTER=filter
		varscan.Call=1
	return varscan

def set_features(variants):
	'''setta i valori delle features in base alle info estratte dai vcf'''
	for var in variants.keys():
		features=Features()
		varc_array=variants[var]

		features.RF_Freebayes=varc_array['F'].RF
		features.lod_Freebayes=varc_array['F'].lod			
		features.GT_Freebayes=varc_array['F'].GT
		features.AO_Freebayes=varc_array['F'].AO
		features.RO_Freebayes=varc_array['F'].RO
		features.AO_f_Freebayes=varc_array['F'].AO_f
		features.AO_r_Freebayes=varc_array['F'].AO_r
		features.DP_f_Freebayes=varc_array['F'].DP_f
		features.DP_r_Freebayes=varc_array['F'].DP_r
		features.DP_Freebayes=varc_array['F'].DP
		features.QB_Freebayes=varc_array['F'].QB
		features.GQ_Freebayes=varc_array['F'].GQ
		features.CallFreebayes=varc_array['F'].Call
		features.AF_Freebayes=varc_array['F'].AF
		features.STRBIAS_Freebayes=varc_array['F'].STRBIAS
		features.FILTER_Freebayes=','.join(varc_array['F'].FILTER)
		features.AC_Freebayes=varc_array['F'].AC
		features.AN_Freebayes=varc_array['F'].AN	
		features.STRBIAS_TOT_Freebayes=varc_array['F'].STRBIAS_TOT
		features.STROR_Freebayes=varc_array['F'].STROR

		features.AO_f_TOT_Freebayes=varc_array['F'].AO_f_TOT
		features.AO_r_TOT_Freebayes=varc_array['F'].AO_r_TOT
		features.RO_f_TOT_Freebayes=varc_array['F'].RO_f_TOT
		features.RO_r_TOT_Freebayes=varc_array['F'].RO_r_TOT
		features.DP_f_TOT_Freebayes=varc_array['F'].DP_f_TOT
		features.DP_r_TOT_Freebayes=varc_array['F'].DP_r_TOT
		features.AB_Freebayes=varc_array['F'].AB
		features.ABP_Freebayes=varc_array['F'].ABP
		features.AF_TOT_Freebayes=varc_array['F'].AF_TOT
		features.AO_TOT_Freebayes=varc_array['F'].AO_TOT
		features.CIGAR_Freebayes=varc_array['F'].CIGAR
		features.DP_TOT_Freebayes=varc_array['F'].DP_TOT
		features.DPB_TOT_Freebayes=varc_array['F'].DPB_TOT
		features.DPRA_TOT_Freebayes=varc_array['F'].DPRA_TOT
		features.END_TOT_Freebayes=varc_array['F'].END_TOT
		features.EPP_TOT_Freebayes=varc_array['F'].EPP_TOT
		features.EPPR_TOT_Freebayes=varc_array['F'].EPPR_TOT
		features.GTI_TOT_Freebayes=varc_array['F'].GTI_TOT
		features.LEN_Freebayes=varc_array['F'].LEN
		features.MEANALT_Freebayes=varc_array['F'].MEANALT
		features.MIN_Freebayes=varc_array['F'].MIN
		features.MQ_A_Freebayes=varc_array['F'].MQ_A
		features.MQ_R_Freebayes=varc_array['F'].MQ_R
		features.NS_Freebayes=varc_array['F'].NS
		features.NUMALT_Freebayes=varc_array['F'].NUMALT
		features.ODDS_Freebayes=varc_array['F'].ODDS
		features.PAIRED_Freebayes=varc_array['F'].PAIRED
		features.PAIREDR_Freebayes=varc_array['F'].PAIREDR
		features.PAO_Freebayes=varc_array['F'].PAO
		features.PQA_Freebayes=varc_array['F'].PQA
		features.PQR_Freebayes=varc_array['F'].PQR
		features.PRO_Freebayes=varc_array['F'].PRO
		features.QA_Freebayes=varc_array['F'].QA
		features.QR_Freebayes=varc_array['F'].QR
		features.RO_TOT_Freebayes=varc_array['F'].RO_TOT
		features.RPL_Freebayes=varc_array['F'].RPL
		features.RPP_Freebayes=varc_array['F'].RPP
		features.RPPR_Freebayes=varc_array['F'].RPPR
		features.RPR_Freebayes=varc_array['F'].RPR
		features.RUN_Freebayes=varc_array['F'].RUN
		features.SAP_Freebayes=varc_array['F'].SAP
		features.SRP_Freebayes=varc_array['F'].SRP
		features.A_QB_Freebayes=varc_array['F'].A_QB
		features.R_QB_Freebayes=varc_array['F'].R_QB

		features.RF_GATK=varc_array['G'].RF
		features.GT_GATK=varc_array['G'].GT
		features.AO_GATK=varc_array['G'].AO
		features.RO_GATK=varc_array['G'].RO
		features.AO_f_GATK=varc_array['G'].AO_f
		features.AO_r_GATK=varc_array['G'].AO_r
		features.DP_f_GATK=varc_array['G'].DP_f
		features.DP_r_GATK=varc_array['G'].DP_r
		features.DP_GATK=varc_array['G'].DP
		features.QB_GATK=varc_array['G'].QB
		features.GQ_GATK=varc_array['G'].GQ
		features.CallGATK=varc_array['G'].Call
		features.AF_GATK=varc_array['G'].AF
		features.STRBIAS_GATK=varc_array['G'].STRBIAS
		features.FILTER_GATK=','.join(varc_array['G'].FILTER)
		features.AC_GATK=varc_array['G'].AC
		features.AN_GATK=varc_array['G'].AN
		features.STROR_GATK=varc_array['G'].STROR

		features.AF_TOT_GATK=varc_array['G'].AF_TOT
		features.BaseQRankSum_GATK=varc_array['G'].BaseQRankSum
		features.ClippingRankSum_GATK=varc_array['G'].ClippingRankSum
		features.DP_TOT_GATK=varc_array['G'].DP_TOT
		features.DS_GATK=varc_array['G'].DS
		features.END_GATK=varc_array['G'].END
		features.ExcessHet_GATK=varc_array['G'].ExcessHet
		features.FS_GATK=varc_array['G'].FS
		features.HaplotypeScore_GATK=varc_array['G'].HaplotypeScore
		features.InbreedingCoeff_GATK=varc_array['G'].InbreedingCoeff
		features.MLEAC_GATK=varc_array['G'].MLEAC
		features.MLEAF_GATK=varc_array['G'].MLEAF
		features.MQ_GATK=varc_array['G'].MQ
		features.MQRankSum_GATK=varc_array['G'].MQRankSum
		features.QD_GATK=varc_array['G'].QD
		features.RAW_MQ_GATK=varc_array['G'].RAW_MQ
		features.ReadPosRankSum_GATK=varc_array['G'].ReadPosRankSum
		features.SOR_GATK=varc_array['G'].SOR

		features.RF_Varscan=varc_array['V'].RF
		features.GT_Varscan=varc_array['V'].GT
		features.AO_Varscan=varc_array['V'].AO
		features.RO_Varscan=varc_array['V'].RO
		features.AO_f_Varscan=varc_array['V'].AO_f
		features.AO_r_Varscan=varc_array['V'].AO_r
		features.DP_f_Varscan=varc_array['V'].DP_f
		features.DP_r_Varscan=varc_array['V'].DP_r
		features.DP_Varscan=varc_array['V'].DP
		features.QB_Varscan=varc_array['V'].QB
		features.GQ_Varscan=varc_array['V'].GQ
		features.CallVarscan=varc_array['V'].Call
		features.AF_Varscan=varc_array['V'].AF
		features.STRBIAS_Varscan=varc_array['V'].STRBIAS
		features.FILTER_Varscan=','.join(varc_array['V'].FILTER)
		features.AC_Varscan=varc_array['V'].AC
		features.AN_Varscan=varc_array['V'].AN
		features.STROR_Varscan=varc_array['V'].STROR
		features.SDP_Varscan=varc_array['V'].SDP

		features.SimpleRepeat_iEVA = varc_array['ieva'].SimpleRepeat
		features.SimpleRepeatLength_iEVA = varc_array['ieva'].SimpleRepeatLength
		features.SimpleRepeatUnit_iEVA= varc_array['ieva'].SimpleRepeatUnit
		features.PseudoNucleotidesComposition_iEVA = '\t'.join((varc_array['ieva'].PseudoNucleotidesComposition).split(','))
		features.RepeatMasker_iEVA = varc_array['ieva'].RepeatMasker
		features.gcContent_iEVA = varc_array['ieva'].gcContent

		features.VariantClass_iEVA = varc_array['ieva'].VariantClass
		features.StrandBiasReads_iEVA = varc_array['ieva'].StrandBiasReads
		features.UnMappedReads_iEVA = varc_array['ieva'].UnMappedReads
		features.MeanMappingQuality_iEVA = varc_array['ieva'].MeanMappingQuality
		features.MappingQualityZero_iEVA = varc_array['ieva'].MappingQualityZero
		features.NotPrimaryAlignment_iEVA = varc_array['ieva'].NotPrimaryAlignment
		features.SupplementaryAlignment_iEVA = varc_array['ieva'].SupplementaryAlignment
		features.NotPairedReads_iEVA = varc_array['ieva'].NotPairedReads
		features.NotProperPairedReads_iEVA = varc_array['ieva'].NotProperPairedReads
		features.AlignmentScore_iEVA = varc_array['ieva'].AlignmentScore
		features.TotalDupReads_iEVA = varc_array['ieva'].TotalDupReads

		features.NumberReadDupRef_iEVA = varc_array['ieva'].NumberReadDupRef
		features.NumberReadDupAlt_iEVA = varc_array['ieva'].NumberReadDupAlt
		features.DuplicateReference_iEVA = varc_array['ieva'].DuplicateReference
		features.DuplicateAlternate_iEVA = varc_array['ieva'].DuplicateAlternate
		features.DeltaDuplicate_iEVA = varc_array['ieva'].DeltaDuplicate
		features.iEvaDepth_iEVA = varc_array['ieva'].iEvaDepth
		features.iAlleleDepth_iEVA = varc_array['ieva'].iAlleleDepth
		features.ReadRef_iEVA = varc_array['ieva'].ReadRef
		features.ReadAlt_iEVA = varc_array['ieva'].ReadAlt
		features.MeanRefQscore_iEVA = varc_array['ieva'].MeanRefQscore
		features.MeanAltQscore_iEVA = varc_array['ieva'].MeanAltQscore
		features.RefMeanMappingQuality_iEVA = varc_array['ieva'].RefMeanMappingQuality
		features.AltMeanMappingQuality_iEVA = varc_array['ieva'].AltMeanMappingQuality
		features.TotalDPUnfilter_iEVA = varc_array['ieva'].TotalDPUnfilter
		features.NumberClippedReadsRef_iEVA = varc_array['ieva'].NumberClippedReadsRef
		features.NumberClippedReadsAlt_iEVA = varc_array['ieva'].NumberClippedReadsAlt
		features.ClippedReadsRef_iEVA = varc_array['ieva'].ClippedReadsRef
		features.ClippedReadsAlt_iEVA = varc_array['ieva'].ClippedReadsAlt


		vett_MBQ = [features.QB_GATK,features.QB_Freebayes,features.QB_Varscan]
		vett_DP = [features.DP_GATK,features.DP_Freebayes,features.DP_Varscan]
		vett_AO = [features.AO_GATK,features.AO_Freebayes,features.AO_Varscan]
		vett_RO = [features.RO_GATK,features.RO_Freebayes,features.RO_Varscan]
		vett_AC = [features.AC_GATK,features.AC_Freebayes,features.AC_Varscan]
		vett_AN = [features.AN_GATK,features.AN_Freebayes,features.AN_Varscan]
		vett_RF_mean = [features.RF_GATK,features.RF_Freebayes,features.RF_Varscan]
		vett_AF_mean = [features.AF_GATK,features.AF_Freebayes,features.AF_Varscan]
		vett_STRB_mean = [features.STRBIAS_GATK,features.STRBIAS_Freebayes,features.STRBIAS_Varscan]
		vett_SOR_mean = [features.STROR_GATK,features.STROR_Freebayes,features.STROR_Varscan]
		
		AF_mean=0
		SB_mean=0
		AC_mean=0
		AC_median=0
		DP_mean='.'
		DP_median='.'
		AO_mean='.'
		RO_mean='.'
		AO_median='.'
		RO_median='.'
		RF_mean='.'
		RF_median='.'


		v=[]
		for dp in vett_DP:
			if dp != '' and dp is not '.':
				v=v+[int(dp)]
		try:
			features.DP_mean=int(np.ceil(statistics.mean(v)))
		except:
			features.DP_mean='.'
		try:
			features.DP_median=int(statistics.median(v))
		except:
			features.DP_median='.'

				
		v=[]
		for ao in vett_AO:
			if ao != '' and ao is not '.':
				v=v+[int(ao)]
		try:
			features.AO_mean=int(np.ceil(statistics.mean(v)))
		except:
			features.AO_mean='.'
		try:
			features.AO_median=int(statistics.median(v))
		except:
			features.AO_median='.'

		v=[]
		for ro in vett_RO:
			if ro != '' and ro is not '.' :
				v=v+[int(ro)]
		try:
			features.RO_mean=int(np.ceil(statistics.mean(v)))
		except:
			features.RO_mean='.'
		try:
			features.RO_median=int(statistics.median(v))
		except:
			features.RO_median='.'

		v=[]
		for bq in vett_MBQ:
			if bq != '' and bq is not '.':
				v=v+[float(bq)]
		try:
			features.MBQ_mean=int(statistics.mean(v))
		except:
			features.MBQ_mean='.'
		try:
			features.MBQ_median=int(statistics.median(v))
		except:
			features.MBQ_median='.'	

		v=[]
		for af in vett_AF_mean:
			if af != '' and af is not '0'and af is not '.':
				v=v+[float(af)]
		try:
			features.AF_mean=round(statistics.mean(v),3)
		except:
			features.AF_mean='.'
		try:
			features.AF_median=round(statistics.median(v),3)
		except:
			features.AF_median='.'

		v=[]
		for strb in vett_STRB_mean:
			if strb != '' and strb is not '.':
				v=v+[float(strb)]
		try:
			features.STRBIAS_mean=round(statistics.mean(v),3)
		except:
			features.STRBIAS_mean='.'
		try:
			features.STRBIAS_median=round(statistics.median(v),3)
		except:
			features.STRBIAS_median='.'

		v=[]
		for ac in vett_AC:
			if ac != '' and ac is not '.':
				v=v+[int(ac)]
		try:
			features.AC_mean=int(statistics.mean(v))
		except:
			features.AC_mean='.'
		try:
			features.AC_median=int(statistics.median(v))
		except:
			features.AC_median='.'

		try:
			features.AC=max(v)
		except:
			features.AC='.'

		
		v=[]
		for an in vett_AN:
			if an != '' and an is not '.':
				v=v+[int(an)]
		try:
			features.AN_mean=int(statistics.mean(v))
		except:
			features.AN_mean='.'
		try:
			features.AN_median=int(statistics.median(v))
		except:
			features.AN_median='.'
		try:
			features.AN=max(v)
		except:
			features.AN='.'


		v=[]
		for rf in vett_RF_mean:
			if rf != '' and rf is not '.':
				v=v+[float(rf)]
		try:
			features.RF_mean=round(statistics.mean(v),3)
		except:
			features.RF_mean='.'
		try:
			features.RF_median=round(statistics.median(v),3)
		except:
			features.RF_median='.'

		v=[]
		for mq in [features.MQ_GATK,features.MQ_A_Freebayes]:
			if mq != '' and mq is not '.':
				v=v+[float(mq)]
		try:
			features.MQ_mean=round(statistics.mean(v),3)
		except:
			features.MQ_mean='.'
		try:
			features.MQ_median=round(statistics.median(v),3)
		except:
			features.MQ_median='.'

		v=[]
		for SOR in vett_SOR_mean:
			if SOR != '' and SOR is not '.':
				v=v+[float(SOR)]
		try:
			features.SOR_mean=round(statistics.mean(v),3)
		except:
			features.SOR_mean='.'
		try:
			features.SOR_median=round(statistics.median(v),3)
		except:
			features.SOR_median='.'

		v=[]
		for f in [features.FILTER_GATK,features.FILTER_Freebayes,features.FILTER_Varscan]:
			if f != '' and f != '.':
				if f not in v:
					v += [f]
		if v == []:
			v=['.']

		features.FILTER += set_filters(features)

		features.FILTER = ';'.join(v)

		variants[var]['features']= features


def set_filters(features):

	filters = []
	if features.GT_GATK == './.' and features.GT_Freebayes == '0/0' or
		 features.GT_GATK == '0/0' and features.GT_Freebayes == './.' or
		 	 features.GT_GATK == '0/0' and features.GT_Freebayes == '0/0':
		 	 	filters += ['PROB-WT']
	if features.AO_mean < 3.0:
		filters += ['LOW-AD']
	if features.AF_mean > 0.20:
		filters += ['LOW-FREQ']
	if features.MQ_mean < 40.0:
		filters += ['LOW-MAPQUAL']
	if features.MBQ_mean < 20.0:
		filters += ['LOW-BASEQUAL']
	if features.FS_mean > 60.0:
		filters += ['HIGH-FS']
	if features.SOR_mean > 3.0:
		filters += ['HIGH-SOR']

	return filters

def split_format(format,sformat):
	G_format = []
	F_format = []
	V_format = []
	G_sample = []
	F_sample = []
	V_sample = []
	I_format = []
	I_sample = []
	for f in format:
		if f.endswith('_G'):
			G_sample += [sformat[format.index(f)]]
			newf = re.sub('_G','',f)
			G_format += [newf]
		elif f.endswith('_F'):
			F_sample += [sformat[format.index(f)]]
			newf = re.sub('_F','',f)
			F_format += [newf]
		elif f.endswith('_V'):
			V_sample += [sformat[format.index(f)]]
			newf = re.sub('_V','',f)
			V_format += [newf]
		else:
			I_sample += [sformat[format.index(f)]]
			I_format += [f]

	return [G_format,G_sample],[F_format,F_sample],[V_format,V_sample],[I_format,I_sample]

def split_info(info):
	G_info = []
	F_info = []
	V_info = []
	I_info= []

	for f in info:
		if f.split('=')[0].endswith('_G'):
			newf = re.sub('_G','',f)
			G_info += [newf]
		elif f.split('=')[0].endswith('_F'):
			newf = re.sub('_F','',f)
			F_info += [newf]
		elif f.split('=')[0].endswith('_V'):
			newf = re.sub('_V','',f)
			V_info += [newf]
		else:
			I_info += [f]

	return G_info,F_info,V_info,I_info


def split_filter(filter):
	G_filter = []
	F_filter = []
	V_filter = []

	for f in filter:
		if f.endswith('_G'):
			newf = re.sub('_G','',f)
			G_filter += [newf]
		elif f.endswith('_F'):
			newf = re.sub('_F','',f)
			F_filter += [newf]
		elif f.endswith('_V'):
			newf = re.sub('_V','',f)
			V_filter += [newf]
	return G_filter,F_filter,V_filter


def readline(file,sample,variants):
	'''legge il vcf e splitta le varie sezioni'''
	vcf = open(file,'r')
	for line in vcf:
		line = line.rstrip()
		if line.startswith('##'):
			continue
		elif line.startswith('#CHROM'):
			sample_index = line.split('\t').index(sample)
		else:
			try:
				var = line.split("\t")
				chrom,pos,id,ref,alt,qual,filter,info,format=line.split("\t")[:9]
				IDvar='\t'.join([chrom,pos,ref,alt])
				info=info.split(";")
				format=format.split(":")
				#try:

				sformat = line.split("\t")[sample_index].split(':')
				format,sformat = addInfo_gvcf(chrom,pos,format,sformat,sample)

				[G_format,G_sample],[F_format,F_sample],[V_format,V_sample],[I_format,I_sample] = split_format(format,sformat)
				[G_info,F_info,V_info,I_info] = split_info(info)
				[G_filter,F_filter,V_filter] = split_filter(filter)
				[G_qual,F_qual,V_qual] = qual.split(',')

				variants[IDvar] = dict()

				variants[IDvar]['G'] = get_info_GATK(chrom,pos,ref,alt,G_filter,G_info,G_format,G_sample,GATK())
				variants[IDvar]['F'] = get_info_Freebayes(chrom,pos,ref,alt,F_filter,F_info,F_format,F_sample,Freebayes())
				variants[IDvar]['V'] = get_info_Varscan(chrom,pos,ref,alt,V_filter,V_info,V_format,V_sample,Varscan())
				variants[IDvar]['I'] = get_info_Ieva(chrom,pos,ref,alt,I_filter,I_info,I_format,I_sample,Ieva())

			except Exception:
				print(chrom,pos)
				raise
	vcf.close()
	return variants
				
def control(vars):
	''' esegue un controllo sulle varianti, se non hanno variant caller che le chiama vengono eliminate'''
	for var in vars.keys():
		if vars[var]['G'].GT == './.' and vars[var]['F'].GT == './.' and vars[var]['V'].GT == './.':
			del vars[var]
		else:
			v=[]
			for ao in [vars[var]['G'].AO,vars[var]['F'].AO,vars[var]['V'].AO]:
				if ao != '' and ao is not '.':
					v=v+[int(ao)]
			if np.ceil(statistics.mean(v)) == 0.0:
				del vars[var]

def print_var(dictionary,out,sample_name):


	lista_features=open(opts.listaFeatures,'r')
	dataset_varianti=open(out + '/' + sample_name + '.tsv','w')
	header=[]
	features_variante=[]
	
	for line in lista_features:
		line = line.rstrip()
		if line.startswith('#'):
			continue
		else:
			header=header+[line]
			features_variante=features_variante+['features.'+line]

	dataset_varianti.write('CHROM\tPOS\tID\tREF\tALT\t' + '\t'.join(header)+ '\n')
	for variante in dictionary.keys():
		features = dictionary.get(variante)['features']
		features_variante_eval=[]
		for feat in features_variante:
		 	feat_eval=str(eval(feat))
		 	features_variante_eval=features_variante_eval + [feat_eval]
		var=variante.split('\t')[0]+'\t'+variante.split('\t')[1]+'\t' +sample_name +'\t'+variante.split('\t')[2]+'\t'+variante.split('\t')[3]+ '\t' + '\t'.join(features_variante_eval)
		dataset_varianti.write(var+ '\n')
	dataset_varianti.close()
	lista_features.close()

def samples_name_extract(vcf):
	ovcf = open(vcf,'r')
	samples = []
	for line in ovcf:
		line=line.rstrip()
		if line.startswith('#CHROM'):
			line_split = line.split('\t')
			samples = line_split[9:]
	ovcf.close()
	return samples


def split_vcf(vcf_dir,sample):
	vcf_name = os.path.basename(vcf_dir)
	vcf_path = os.path.dirname(vcf_dir)

	vcf = open(vcf_dir,'r')

	header = []
	header_chrom = []
	varianti = []
	
	if 'FreeB' in vcf_name:
			variant_caller = 'FreeBayes'
	elif 'GATK' in vcf_name:
			variant_caller = 'GATK'
	elif 'VarScan' in vcf_name:
			variant_caller = 'VarScan'
	print('\n'+variant_caller +':')
	
	for line in vcf:
		line=line.rstrip()
		if line.startswith('##'):
		 	header = header + [line]
		elif line.startswith('#CHROM'):
		 	header_chrom = line.split('\t')
		else:
		 	varianti = varianti + [line]
	i=0
	for sample in samples:
		print(sample)
		try: 
			os.mkdir(opts.out_path +'/' + sample)
		except:
			pass
		
		sample_vcf = open(opts.out_path +'/' + sample +'/' + sample + '_'+variant_caller +'.vcf','w')

def addInfo_gvcf(chrom,pos,format,fsample,sample):
		gvcf = open(opts.gvcf_path +'/' + sample +'.g.vcf','r')
		sSB = '.'
		sQD = '.'

		for line in gvcf:
			line = line.rstrip()
			if line.startswith(chrom+'\t'+pos) and line.split('\t')[4] != '<NON_REF>':
				gformat = line.split('\t')[-2]
				gsample = line.split('\t')[-1]
				qual = line.split('\t')[5]
				info = line.split('\t')[7].split(';')
				try:
					ad = (gsample.split(':')[(gformat.split(':')).index('AD')]).split(',')
				except:
					ad = ['0','0','0']
				
				ad = map(float, ad)
				ad_sum = sum(ad[1:])

				try:
					sSB = gsample.split(':')[(gformat.split(':')).index('SB')]
				except:
					sSB = '.'

				try:
					sQD = round(float(qual)/ad_sum ,2)
				except:
					sQD = 0.0
				break
		
		format = format + ['SB_G','SQD_G']
		fsample = fsample + [sSB,str(sQD)]
		gvcf.close()
		return format,fsample


def main():

	parser = argparse.ArgumentParser('Parse VCF output from Variant callers to output a variant_dataset.txt.  Output is to stdout.')
	parser.add_argument('-l', '--listaFeatures', help="Lista di features da stampare",default=None)
	parser.add_argument('-m', '--merged', help="vcf merged from GATK,Freebayes and Varscan2")
	parser.add_argument('-a', '--amplicon',help="Amplicon design", action='store_true')
	parser.add_argument('-o', '--out_path',help="path di output")
	parser.add_argument('-G', '--gvcf_path',help="gvcf path")

	global opts 
	opts = parser.parse_args()
	samples_file = open(opts.out_path+'/tsv.list','w')
	
	try:
		os.mkdir(opts.out_path)
	except:
		pass
	
	samples = samples_name_extract(opts.merged)
	for sample in samples:
		start_time = datetime.datetime.now()
		variants=readline(opts.merged,sample,dict())
		set_features(variants)
		set_filters(variants)
		control(variants)
		print_var(variants,opts.out_path,sample)
		elapsed_time = divmod((datetime.datetime.now() - start_time).total_seconds(),60)
		samples_file.write(opts.out_path+'/'+sample+'.tsv\n')
		print("- "+sample+": %d min, %d sec" % elapsed_time)
	samples_file.close()

main()
