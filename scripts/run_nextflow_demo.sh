#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ROOT="${1:-/tmp/helper_next_demo_$$}"
BIN_DIR="${RUN_ROOT}/bin"
DATA_DIR="${RUN_ROOT}/data"
CONFIG_DIR="${RUN_ROOT}/config"
RESULTS_DIR="${RUN_ROOT}/results"

if ! command -v nextflow >/dev/null 2>&1; then
    echo "nextflow is not available in PATH" >&2
    exit 127
fi

for java_home in /usr/lib/jvm/java-21-openjdk-amd64 /usr/lib/jvm/openjdk-21 /usr/lib/jvm/java-17-openjdk-amd64; do
    if [ -x "${java_home}/bin/java" ]; then
        export JAVA_HOME="${java_home}"
        export JAVA_CMD="${java_home}/bin/java"
        export PATH="${java_home}/bin:${PATH}"
        break
    fi
done

mkdir -p "${BIN_DIR}" "${DATA_DIR}" "${CONFIG_DIR}" "${RESULTS_DIR}"

cat > "${BIN_DIR}/fastqc" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
outdir="."
while [ "$#" -gt 0 ]; do
    case "$1" in
        -o) outdir="$2"; shift 2 ;;
        -t) shift 2 ;;
        -*) shift ;;
        *) sample="$(basename "$1")"; touch "${outdir}/${sample}_fastqc.html" "${outdir}/${sample}_fastqc.zip"; shift ;;
    esac
done
STUB

cat > "${BIN_DIR}/bwa" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
echo '@HD	VN:1.6	SO:unknown'
echo '@SQ	SN:chrDemo	LN:1000'
echo 'demo_read	4	*	0	0	*	*	0	0	ACGT	FFFF'
STUB

cat > "${BIN_DIR}/samtools" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
command="$1"
shift
case "${command}" in
    view)
        out=""
        input=""
        while [ "$#" -gt 0 ]; do
            case "$1" in
                -o) out="$2"; shift 2 ;;
                -@|-b) shift; [ "$#" -gt 0 ] && [ "$1" != "-o" ] && shift || true ;;
                *) input="$1"; shift ;;
            esac
        done
        cp "${input}" "${out}"
        ;;
    sort)
        out=""
        input=""
        while [ "$#" -gt 0 ]; do
            case "$1" in
                -o) out="$2"; shift 2 ;;
                -@) shift 2 ;;
                *) input="$1"; shift ;;
            esac
        done
        cp "${input}" "${out}"
        ;;
    index)
        touch "$1.bai"
        ;;
    *)
        echo "unsupported samtools command: ${command}" >&2
        exit 2
        ;;
esac
STUB

cat > "${BIN_DIR}/picard-wrapper" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
operation="$1"
shift
input=""
output=""
metrics=""
for arg in "$@"; do
    case "${arg}" in
        I=*) input="${arg#I=}" ;;
        O=*) output="${arg#O=}" ;;
        M=*) metrics="${arg#M=}" ;;
    esac
done
cp "${input}" "${output}"
if [ "${operation}" = "MarkDuplicates" ] && [ -n "${metrics}" ]; then
    printf "metric\tvalue\nREAD_PAIRS_EXAMINED\t1\n" > "${metrics}"
fi
STUB

cat > "${BIN_DIR}/gatk" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
output=""
bamout=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --java-options) shift 2 ;;
        -O) output="$2"; shift 2 ;;
        -bamout) bamout="$2"; shift 2 ;;
        *) shift ;;
    esac
done
cat > "${output}" <<'EOF_VCF'
##fileformat=VCFv4.2
##source=helper-next-demo-gatk
#CHROM	POS	ID	REF	ALT	QUAL	FILTER	INFO
chrDemo	1	.	A	C	60	PASS	.
EOF_VCF
if [ -n "${bamout}" ]; then
    printf "demo realigned bam\n" > "${bamout}"
fi
STUB

cat > "${BIN_DIR}/gatk3" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail
operation=""
input=""
output=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        -T) operation="$2"; shift 2 ;;
        -I) input="$2"; shift 2 ;;
        -o) output="$2"; shift 2 ;;
        *) shift ;;
    esac
done
case "${operation}" in
    RealignerTargetCreator)
        printf "chrDemo:1-32\n" > "${output}"
        ;;
    IndelRealigner|PrintReads)
        cp "${input}" "${output}"
        ;;
    BaseRecalibrator)
        printf "covariate\tvalue\nReadGroup\t1\n" > "${output}"
        ;;
    *)
        echo "unsupported GATK3 operation: ${operation}" >&2
        exit 2
        ;;
esac
STUB

chmod +x "${BIN_DIR}/fastqc" "${BIN_DIR}/bwa" "${BIN_DIR}/samtools" "${BIN_DIR}/picard-wrapper" "${BIN_DIR}/gatk" "${BIN_DIR}/gatk3"

cat > "${DATA_DIR}/reference.fa" <<'EOF_REF'
>chrDemo
ACGTACGTACGTACGTACGTACGTACGTACGT
EOF_REF
cat > "${DATA_DIR}/dbsnp.vcf" <<'EOF_VCF'
##fileformat=VCFv4.2
#CHROM	POS	ID	REF	ALT	QUAL	FILTER	INFO
EOF_VCF
cat > "${DATA_DIR}/mills.vcf" <<'EOF_VCF'
##fileformat=VCFv4.2
#CHROM	POS	ID	REF	ALT	QUAL	FILTER	INFO
EOF_VCF

for sample in S1 S2; do
    cat > "${DATA_DIR}/${sample}_R1.fastq" <<EOF_FASTQ
@${sample}/1
ACGT
+
FFFF
EOF_FASTQ
    cat > "${DATA_DIR}/${sample}_R2.fastq" <<EOF_FASTQ
@${sample}/2
TGCA
+
FFFF
EOF_FASTQ
done

cat > "${CONFIG_DIR}/samplesheet.json" <<EOF_JSON
{
  "sample_list": ["S1", "S2"],
  "sample_organization": "only cases",
  "prealignment": {
    "S1": {"case": {"sample_name": "S1", "fastq_R1": "${DATA_DIR}/S1_R1.fastq", "fastq_R2": "${DATA_DIR}/S1_R2.fastq", "fastq_I2": ""}},
    "S2": {"case": {"sample_name": "S2", "fastq_R1": "${DATA_DIR}/S2_R1.fastq", "fastq_R2": "${DATA_DIR}/S2_R2.fastq", "fastq_I2": ""}}
  }
}
EOF_JSON

cat > "${CONFIG_DIR}/pipeline.json" <<'EOF_JSON'
{
  "analysis": "Demo",
  "reference_version": "demo_reference",
  "workflow": ["prealignment", "alignment", "preprocessing", "variantcalling", "postprocessing"],
  "prealignment": {
    "workflow": ["fastq_QC"],
    "threads": "1",
    "ram": "1g",
    "fastq_QC": {"tool": "FASTQC v.0.11.8", "FASTQC v.0.11.8": {"args": []}}
  },
  "alignment": {
    "workflow": ["fastq_alignment"],
    "threads": "1",
    "ram": "1g",
    "fastq_alignment": {"tool": "BWA v.0.7.17", "BWA v.0.7.17": {"algorithm": "mem", "args": []}}
  },
  "preprocessing": {
    "workflow": ["add_readgroups", "mark_pcr_dup", "indel_realignment", "BQ_recalibration"],
    "threads": "1",
    "ram": "1g",
    "add_readgroups": {"tool": "PICARD v.2.7.1", "PICARD v.2.7.1": {"args": []}},
    "mark_pcr_dup": {"tool": "PICARD v.2.7.1", "PICARD v.2.7.1": {"args": []}},
    "indel_realignment": {"tool": "GATK v.3.7", "GATK v.3.7": {"args": [], "mills": "mills"}},
    "BQ_recalibration": {"tool": "GATK v.3.7", "GATK v.3.7": {"args": [], "dbsnp": "dbsnp", "mills": "mills"}}
  },
  "variantcalling": {
    "tools": ["GATK v.4.1"],
    "threads": "1",
    "ram": "1g",
    "filters": {
      "min_base_quality_score": "",
      "min_alt_coverage": "",
      "min_alt_freq": "",
      "min_mapping_quality_score": ""
    },
    "GATK v.4.1": {"args": []},
    "samples_org": "single-sample"
  },
  "postprocessing": {
    "workflow": ["vcf_to_tsv"],
    "threads": "1",
    "ram": "1g",
    "vcf_norm": {"tool": "BCFTOOLS", "BCFTOOLS": {"args": []}},
    "vcf_filter": {"tool": "", "GATK v.4.1": {"args": []}},
    "vcf_to_tsv": {"tool": "", "args": {"tags_file": "", "format_tags": "", "info_tags": ""}}
  }
}
EOF_JSON

cat > "${CONFIG_DIR}/tools.json" <<EOF_JSON
{
  "demo_reference": {"fasta": "${DATA_DIR}/reference.fa", "version": "demo", "tags": "reference"},
  "FASTQC v.0.11.8": {"path": "${BIN_DIR}/fastqc", "version": "demo", "tags": "fastq_qc"},
  "BWA v.0.7.17": {"path": "${BIN_DIR}/bwa", "version": "demo", "tags": "fastq_alignment"},
  "PICARD v.2.7.1": {"path": "${BIN_DIR}/picard-wrapper", "version": "demo", "tags": "add_readgroups,mark_pcr_dup"},
  "GATK v.3.7": {"path": "${BIN_DIR}/gatk3", "version": "demo", "tags": "indel_realignment,BQ_recalibration"},
  "GATK v.4.1": {"path": "${BIN_DIR}/gatk", "version": "demo", "tags": "variantcalling"},
  "SAMTOOLS": {"path": "${BIN_DIR}/samtools", "version": "demo", "tags": "sam_to_bam,sort,index"},
  "BCFTOOLS": {"path": "bcftools", "version": "demo", "tags": "vcf_norm"},
  "dbsnp": {"path": "${DATA_DIR}/dbsnp.vcf", "version": "demo", "tags": "database"},
  "mills": {"path": "${DATA_DIR}/mills.vcf", "version": "demo", "tags": "database"}
}
EOF_JSON

PYTHONPATH="${ROOT}/helper_next/src" python -m helper_next.cli nextflow-manifest \
  --samplesheet "${CONFIG_DIR}/samplesheet.json" \
  --pipeline "${CONFIG_DIR}/pipeline.json" \
  --tools "${CONFIG_DIR}/tools.json" \
  --entry-step prealignment \
  --workflow prealignment,alignment,preprocessing,variantcalling,postprocessing \
  --out "${RUN_ROOT}/manifest.tsv" \
  --run-config "${RUN_ROOT}/run_config.json"

nextflow run "${ROOT}/workflows/nextflow/main.nf" \
  -work-dir "${RUN_ROOT}/work" \
  -c "${ROOT}/workflows/nextflow/nextflow.config" \
  -with-trace "${RUN_ROOT}/nextflow.trace.tsv" \
  --manifest "${RUN_ROOT}/manifest.tsv" \
  --pipeline "${CONFIG_DIR}/pipeline.json" \
  --tools "${CONFIG_DIR}/tools.json" \
  --run_config "${RUN_ROOT}/run_config.json" \
  --outdir "${RESULTS_DIR}" \
  --keep_intermediates true \
  -profile local

echo "Demo run completed: ${RUN_ROOT}"
echo "Workflow plan: ${RESULTS_DIR}/LOGS/workflow.plan.tsv"
echo "Trace: ${RUN_ROOT}/nextflow.trace.tsv"
