nextflow.enable.dsl = 2


process ALIGN_BWA {
    tag "${row.sample_name}"
    cpus { align_threads }
    memory { align_ram }
    publishDir "${params.outdir}/ALIGNMENT", mode: 'copy', pattern: '*.sort.bam*'
    publishDir "${params.outdir}/ALIGNMENT/intermediates", mode: 'copy', pattern: '*.sam', enabled: params.keep_intermediates == true || params.keep_intermediates?.toString()?.toLowerCase() in ['true', '1', 'yes']
    publishDir "${params.outdir}/ALIGNMENT/intermediates", mode: 'copy', pattern: '*.unsorted.bam', enabled: params.keep_intermediates == true || params.keep_intermediates?.toString()?.toLowerCase() in ['true', '1', 'yes']
    publishDir "${params.outdir}/LOGS/ALIGNMENT/samples", mode: 'copy', pattern: '*.alignment.log'
    publishDir "${params.outdir}/LOGS/ALIGNMENT/samples", mode: 'copy', pattern: '*.alignment.status.tsv'

    input:
    val row
    val align_threads
    val align_ram
    val bwa_path
    val samtools_path
    val algorithm
    val extra_args
    val reference_fasta

    output:
    tuple val(row.sample_id), val(row.role), val(row.sample_name), path("${row.sample_name}.sort.bam"), path("${row.sample_name}.sort.bam.bai"), optional: true, emit: bams
    tuple val(row.sample_id), val(row.role), val(row.sample_name), path("${row.sample_name}.sam"), path("${row.sample_name}.unsorted.bam"), optional: true, emit: intermediates
    tuple val(row.sample_id), val(row.role), val(row.sample_name), path("${row.sample_name}.alignment.log"), path("${row.sample_name}.alignment.status.tsv"), emit: statuses

    script:
    def fastq2 = row.fastq_r2 ? row.fastq_r2 : ''
    def bwa_algorithm = algorithm ?: 'mem'
    """
    set +e
    set -o pipefail
    {
        echo "step=alignment"
        echo "tool=BWA"
        echo "sample_id=${row.sample_id}"
        echo "role=${row.role}"
        echo "sample_name=${row.sample_name}"
        echo "threads=${task.cpus}"
        echo "reference=${reference_fasta}"
        echo "fastq_r1=${row.fastq_r1}"
        echo "fastq_r2=${row.fastq_r2}"
        echo "started=\$(date -Is)"
        echo "align_command=${bwa_path} ${bwa_algorithm} -t ${task.cpus} ${extra_args} ${reference_fasta} ${row.fastq_r1} ${fastq2} > ${row.sample_name}.sam"
        echo "keep_intermediates=${params.keep_intermediates}"
        echo "samtobam_command=${samtools_path} view -@ ${task.cpus} -b -o ${row.sample_name}.unsorted.bam ${row.sample_name}.sam"
        echo "sort_command=${samtools_path} sort -@ ${task.cpus} -o ${row.sample_name}.sort.bam ${row.sample_name}.unsorted.bam"
        echo "index_command=${samtools_path} index ${row.sample_name}.sort.bam"
        echo
    } > ${row.sample_name}.alignment.log
    started_at=\$(date -Is)
    ${bwa_path} ${bwa_algorithm} -t ${task.cpus} ${extra_args} ${reference_fasta} ${row.fastq_r1} ${fastq2} \
        > ${row.sample_name}.sam 2>> ${row.sample_name}.alignment.log
    align_exit=\$?
    if [ "\${align_exit}" -eq 0 ]; then
        ${samtools_path} view -@ ${task.cpus} -b -o ${row.sample_name}.unsorted.bam ${row.sample_name}.sam >> ${row.sample_name}.alignment.log 2>&1
        samtobam_exit=\$?
    else
        samtobam_exit=0
    fi
    if [ "\${align_exit}" -eq 0 ] && [ "\${samtobam_exit}" -eq 0 ]; then
        ${samtools_path} sort -@ ${task.cpus} -o ${row.sample_name}.sort.bam ${row.sample_name}.unsorted.bam >> ${row.sample_name}.alignment.log 2>&1
        sort_exit=\$?
    else
        sort_exit=0
    fi
    if [ "\${align_exit}" -eq 0 ] && [ "\${samtobam_exit}" -eq 0 ] && [ "\${sort_exit}" -eq 0 ]; then
        ${samtools_path} index ${row.sample_name}.sort.bam >> ${row.sample_name}.alignment.log 2>&1
        index_exit=\$?
    else
        index_exit=0
    fi
    completed_at=\$(date -Is)
    if [ "\${align_exit}" -eq 0 ] && [ "\${samtobam_exit}" -eq 0 ] && [ "\${sort_exit}" -eq 0 ] && [ "\${index_exit}" -eq 0 ]; then
        status=completed
        exit_code=0
        echo "completed=\${completed_at}" >> ${row.sample_name}.alignment.log
    else
        status=failed
        exit_code=\${align_exit}
        if [ "\${samtobam_exit}" -ne 0 ]; then
            exit_code=\${samtobam_exit}
        fi
        if [ "\${sort_exit}" -ne 0 ]; then
            exit_code=\${sort_exit}
        fi
        if [ "\${index_exit}" -ne 0 ]; then
            exit_code=\${index_exit}
        fi
        rm -f ${row.sample_name}.sort.bam ${row.sample_name}.sort.bam.bai
        echo "failed=\${completed_at}" >> ${row.sample_name}.alignment.log
        echo "exit_code=\${exit_code}" >> ${row.sample_name}.alignment.log
    fi
    if [ "${params.keep_intermediates}" != "true" ] && [ "${params.keep_intermediates}" != "1" ] && [ "${params.keep_intermediates}" != "yes" ]; then
        rm -f ${row.sample_name}.sam ${row.sample_name}.unsorted.bam
    fi
    printf "step\\ttool\\tsample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n" > ${row.sample_name}.alignment.status.tsv
    printf "alignment\\tBWA\\t${row.sample_id}\\t${row.role}\\t${row.sample_name}\\t\${status}\\t\${exit_code}\\t\${started_at}\\t\${completed_at}\\n" >> ${row.sample_name}.alignment.status.tsv
    exit 0
    """
}


process ALIGN_BOWTIE2 {
    tag "${row.sample_name}"
    cpus { align_threads }
    memory { align_ram }
    publishDir "${params.outdir}/ALIGNMENT", mode: 'copy', pattern: '*.sort.bam*'
    publishDir "${params.outdir}/ALIGNMENT/intermediates", mode: 'copy', pattern: '*.sam', enabled: params.keep_intermediates == true || params.keep_intermediates?.toString()?.toLowerCase() in ['true', '1', 'yes']
    publishDir "${params.outdir}/ALIGNMENT/intermediates", mode: 'copy', pattern: '*.unsorted.bam', enabled: params.keep_intermediates == true || params.keep_intermediates?.toString()?.toLowerCase() in ['true', '1', 'yes']
    publishDir "${params.outdir}/LOGS/ALIGNMENT/samples", mode: 'copy', pattern: '*.alignment.log'
    publishDir "${params.outdir}/LOGS/ALIGNMENT/samples", mode: 'copy', pattern: '*.alignment.status.tsv'

    input:
    val row
    val align_threads
    val align_ram
    val bowtie2_path
    val samtools_path
    val extra_args
    val reference_fasta

    output:
    tuple val(row.sample_id), val(row.role), val(row.sample_name), path("${row.sample_name}.sort.bam"), path("${row.sample_name}.sort.bam.bai"), optional: true, emit: bams
    tuple val(row.sample_id), val(row.role), val(row.sample_name), path("${row.sample_name}.sam"), path("${row.sample_name}.unsorted.bam"), optional: true, emit: intermediates
    tuple val(row.sample_id), val(row.role), val(row.sample_name), path("${row.sample_name}.alignment.log"), path("${row.sample_name}.alignment.status.tsv"), emit: statuses

    script:
    def fastq2 = row.fastq_r2 ? "-2 ${row.fastq_r2}" : ''
    def reference_index = reference_fasta.toString().replaceFirst(/\.[^.]+$/, '')
    """
    set +e
    set -o pipefail
    {
        echo "step=alignment"
        echo "tool=BOWTIE2"
        echo "sample_id=${row.sample_id}"
        echo "role=${row.role}"
        echo "sample_name=${row.sample_name}"
        echo "threads=${task.cpus}"
        echo "reference_index=${reference_index}"
        echo "fastq_r1=${row.fastq_r1}"
        echo "fastq_r2=${row.fastq_r2}"
        echo "started=\$(date -Is)"
        echo "align_command=${bowtie2_path} -x ${reference_index} -1 ${row.fastq_r1} ${fastq2} --threads ${task.cpus} ${extra_args} > ${row.sample_name}.sam"
        echo "keep_intermediates=${params.keep_intermediates}"
        echo "samtobam_command=${samtools_path} view -@ ${task.cpus} -b -o ${row.sample_name}.unsorted.bam ${row.sample_name}.sam"
        echo "sort_command=${samtools_path} sort -@ ${task.cpus} -o ${row.sample_name}.sort.bam ${row.sample_name}.unsorted.bam"
        echo "index_command=${samtools_path} index ${row.sample_name}.sort.bam"
        echo
    } > ${row.sample_name}.alignment.log
    started_at=\$(date -Is)
    ${bowtie2_path} -x ${reference_index} -1 ${row.fastq_r1} ${fastq2} --threads ${task.cpus} ${extra_args} \
        > ${row.sample_name}.sam 2>> ${row.sample_name}.alignment.log
    align_exit=\$?
    if [ "\${align_exit}" -eq 0 ]; then
        ${samtools_path} view -@ ${task.cpus} -b -o ${row.sample_name}.unsorted.bam ${row.sample_name}.sam >> ${row.sample_name}.alignment.log 2>&1
        samtobam_exit=\$?
    else
        samtobam_exit=0
    fi
    if [ "\${align_exit}" -eq 0 ] && [ "\${samtobam_exit}" -eq 0 ]; then
        ${samtools_path} sort -@ ${task.cpus} -o ${row.sample_name}.sort.bam ${row.sample_name}.unsorted.bam >> ${row.sample_name}.alignment.log 2>&1
        sort_exit=\$?
    else
        sort_exit=0
    fi
    if [ "\${align_exit}" -eq 0 ] && [ "\${samtobam_exit}" -eq 0 ] && [ "\${sort_exit}" -eq 0 ]; then
        ${samtools_path} index ${row.sample_name}.sort.bam >> ${row.sample_name}.alignment.log 2>&1
        index_exit=\$?
    else
        index_exit=0
    fi
    completed_at=\$(date -Is)
    if [ "\${align_exit}" -eq 0 ] && [ "\${samtobam_exit}" -eq 0 ] && [ "\${sort_exit}" -eq 0 ] && [ "\${index_exit}" -eq 0 ]; then
        status=completed
        exit_code=0
        echo "completed=\${completed_at}" >> ${row.sample_name}.alignment.log
    else
        status=failed
        exit_code=\${align_exit}
        if [ "\${samtobam_exit}" -ne 0 ]; then
            exit_code=\${samtobam_exit}
        fi
        if [ "\${sort_exit}" -ne 0 ]; then
            exit_code=\${sort_exit}
        fi
        if [ "\${index_exit}" -ne 0 ]; then
            exit_code=\${index_exit}
        fi
        rm -f ${row.sample_name}.sort.bam ${row.sample_name}.sort.bam.bai
        echo "failed=\${completed_at}" >> ${row.sample_name}.alignment.log
        echo "exit_code=\${exit_code}" >> ${row.sample_name}.alignment.log
    fi
    if [ "${params.keep_intermediates}" != "true" ] && [ "${params.keep_intermediates}" != "1" ] && [ "${params.keep_intermediates}" != "yes" ]; then
        rm -f ${row.sample_name}.sam ${row.sample_name}.unsorted.bam
    fi
    printf "step\\ttool\\tsample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n" > ${row.sample_name}.alignment.status.tsv
    printf "alignment\\tBOWTIE2\\t${row.sample_id}\\t${row.role}\\t${row.sample_name}\\t\${status}\\t\${exit_code}\\t\${started_at}\\t\${completed_at}\\n" >> ${row.sample_name}.alignment.status.tsv
    exit 0
    """
}


process ALIGN_NOVOALIGN {
    tag "${row.sample_name}"
    cpus { align_threads }
    memory { align_ram }
    publishDir "${params.outdir}/ALIGNMENT", mode: 'copy', pattern: '*.sort.bam*'
    publishDir "${params.outdir}/ALIGNMENT/intermediates", mode: 'copy', pattern: '*.sam', enabled: params.keep_intermediates == true || params.keep_intermediates?.toString()?.toLowerCase() in ['true', '1', 'yes']
    publishDir "${params.outdir}/ALIGNMENT/intermediates", mode: 'copy', pattern: '*.unsorted.bam', enabled: params.keep_intermediates == true || params.keep_intermediates?.toString()?.toLowerCase() in ['true', '1', 'yes']
    publishDir "${params.outdir}/LOGS/ALIGNMENT/samples", mode: 'copy', pattern: '*.alignment.log'
    publishDir "${params.outdir}/LOGS/ALIGNMENT/samples", mode: 'copy', pattern: '*.alignment.status.tsv'

    input:
    val row
    val align_threads
    val align_ram
    val novoalign_path
    val samtools_path
    val extra_args
    val reference_fasta

    output:
    tuple val(row.sample_id), val(row.role), val(row.sample_name), path("${row.sample_name}.sort.bam"), path("${row.sample_name}.sort.bam.bai"), optional: true, emit: bams
    tuple val(row.sample_id), val(row.role), val(row.sample_name), path("${row.sample_name}.sam"), path("${row.sample_name}.unsorted.bam"), optional: true, emit: intermediates
    tuple val(row.sample_id), val(row.role), val(row.sample_name), path("${row.sample_name}.alignment.log"), path("${row.sample_name}.alignment.status.tsv"), emit: statuses

    script:
    def fastq2 = row.fastq_r2 ? row.fastq_r2 : ''
    def reference_index = reference_fasta.toString().replaceFirst(/\.[^.]+$/, '')
    """
    set +e
    set -o pipefail
    {
        echo "step=alignment"
        echo "tool=NOVOALIGN"
        echo "sample_id=${row.sample_id}"
        echo "role=${row.role}"
        echo "sample_name=${row.sample_name}"
        echo "threads=${task.cpus}"
        echo "reference_index=${reference_index}"
        echo "fastq_r1=${row.fastq_r1}"
        echo "fastq_r2=${row.fastq_r2}"
        echo "started=\$(date -Is)"
        echo "align_command=${novoalign_path} -d ${reference_index} -f ${row.fastq_r1} ${fastq2} -c ${task.cpus} ${extra_args} > ${row.sample_name}.sam"
        echo "keep_intermediates=${params.keep_intermediates}"
        echo "samtobam_command=${samtools_path} view -@ ${task.cpus} -b -o ${row.sample_name}.unsorted.bam ${row.sample_name}.sam"
        echo "sort_command=${samtools_path} sort -@ ${task.cpus} -o ${row.sample_name}.sort.bam ${row.sample_name}.unsorted.bam"
        echo "index_command=${samtools_path} index ${row.sample_name}.sort.bam"
        echo
    } > ${row.sample_name}.alignment.log
    started_at=\$(date -Is)
    ${novoalign_path} -d ${reference_index} -f ${row.fastq_r1} ${fastq2} -c ${task.cpus} ${extra_args} \
        > ${row.sample_name}.sam 2>> ${row.sample_name}.alignment.log
    align_exit=\$?
    if [ "\${align_exit}" -eq 0 ]; then
        ${samtools_path} view -@ ${task.cpus} -b -o ${row.sample_name}.unsorted.bam ${row.sample_name}.sam >> ${row.sample_name}.alignment.log 2>&1
        samtobam_exit=\$?
    else
        samtobam_exit=0
    fi
    if [ "\${align_exit}" -eq 0 ] && [ "\${samtobam_exit}" -eq 0 ]; then
        ${samtools_path} sort -@ ${task.cpus} -o ${row.sample_name}.sort.bam ${row.sample_name}.unsorted.bam >> ${row.sample_name}.alignment.log 2>&1
        sort_exit=\$?
    else
        sort_exit=0
    fi
    if [ "\${align_exit}" -eq 0 ] && [ "\${samtobam_exit}" -eq 0 ] && [ "\${sort_exit}" -eq 0 ]; then
        ${samtools_path} index ${row.sample_name}.sort.bam >> ${row.sample_name}.alignment.log 2>&1
        index_exit=\$?
    else
        index_exit=0
    fi
    completed_at=\$(date -Is)
    if [ "\${align_exit}" -eq 0 ] && [ "\${samtobam_exit}" -eq 0 ] && [ "\${sort_exit}" -eq 0 ] && [ "\${index_exit}" -eq 0 ]; then
        status=completed
        exit_code=0
        echo "completed=\${completed_at}" >> ${row.sample_name}.alignment.log
    else
        status=failed
        exit_code=\${align_exit}
        if [ "\${samtobam_exit}" -ne 0 ]; then
            exit_code=\${samtobam_exit}
        fi
        if [ "\${sort_exit}" -ne 0 ]; then
            exit_code=\${sort_exit}
        fi
        if [ "\${index_exit}" -ne 0 ]; then
            exit_code=\${index_exit}
        fi
        rm -f ${row.sample_name}.sort.bam ${row.sample_name}.sort.bam.bai
        echo "failed=\${completed_at}" >> ${row.sample_name}.alignment.log
        echo "exit_code=\${exit_code}" >> ${row.sample_name}.alignment.log
    fi
    if [ "${params.keep_intermediates}" != "true" ] && [ "${params.keep_intermediates}" != "1" ] && [ "${params.keep_intermediates}" != "yes" ]; then
        rm -f ${row.sample_name}.sam ${row.sample_name}.unsorted.bam
    fi
    printf "step\\ttool\\tsample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n" > ${row.sample_name}.alignment.status.tsv
    printf "alignment\\tNOVOALIGN\\t${row.sample_id}\\t${row.role}\\t${row.sample_name}\\t\${status}\\t\${exit_code}\\t\${started_at}\\t\${completed_at}\\n" >> ${row.sample_name}.alignment.status.tsv
    exit 0
    """
}


process BAM_QC {
    tag "${sample_name}"
    cpus { align_threads }
    memory { align_ram }
    publishDir "${params.outdir}/ALIGNMENT/bam_qc", mode: 'copy', pattern: 'bam_fastqc_out/*'
    publishDir "${params.outdir}/LOGS/ALIGNMENT/samples", mode: 'copy', pattern: '*.bam_QC.alignment.log'
    publishDir "${params.outdir}/LOGS/ALIGNMENT/samples", mode: 'copy', pattern: '*.bam_QC.alignment.status.tsv'

    input:
    tuple val(sample_id), val(role), val(sample_name), path(bam), path(bai)
    val align_threads
    val align_ram
    val fastqc_path
    val fastqc_args

    output:
    tuple val(sample_id), val(role), val(sample_name), path('bam_fastqc_out/*'), optional: true, emit: reports
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.bam_QC.alignment.log"), path("${sample_name}.bam_QC.alignment.status.tsv"), emit: statuses

    script:
    """
    set +e
    mkdir -p bam_fastqc_out
    if [ -x "${fastqc_path}" ]; then
        fastqc_cmd="${fastqc_path}"
    else
        fastqc_cmd="perl ${fastqc_path}"
    fi
    {
        echo "step=alignment"
        echo "operation=bam_QC"
        echo "tool=FASTQC"
        echo "sample_id=${sample_id}"
        echo "role=${role}"
        echo "sample_name=${sample_name}"
        echo "threads=${task.cpus}"
        echo "bam=${bam}"
        echo "started=\$(date -Is)"
        echo "command=\${fastqc_cmd} -t ${task.cpus} -o bam_fastqc_out ${fastqc_args} ${bam}"
        echo
    } > ${sample_name}.bam_QC.alignment.log
    started_at=\$(date -Is)
    \${fastqc_cmd} -t ${task.cpus} -o bam_fastqc_out ${fastqc_args} ${bam} >> ${sample_name}.bam_QC.alignment.log 2>&1
    exit_code=\$?
    completed_at=\$(date -Is)
    if [ "\${exit_code}" -eq 0 ]; then
        status=completed
        echo "completed=\${completed_at}" >> ${sample_name}.bam_QC.alignment.log
    else
        status=failed
        echo "failed=\${completed_at}" >> ${sample_name}.bam_QC.alignment.log
        echo "exit_code=\${exit_code}" >> ${sample_name}.bam_QC.alignment.log
    fi
    printf "step\\ttool\\tsample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n" > ${sample_name}.bam_QC.alignment.status.tsv
    printf "alignment\\tFASTQC\\t${sample_id}\\t${role}\\t${sample_name}\\t\${status}\\t\${exit_code}\\t\${started_at}\\t\${completed_at}\\n" >> ${sample_name}.bam_QC.alignment.status.tsv
    exit 0
    """
}


process ALIGNMENT_STEP_LOG {
    tag 'alignment'
    publishDir "${params.outdir}/LOGS/ALIGNMENT", mode: 'copy'

    input:
    val tool_name
    path sample_statuses

    output:
    path "alignment.step.log", emit: log

    script:
    """
    {
        echo "step=alignment"
        echo "tool=${tool_name}"
        echo "generated=\$(date -Is)"
        echo "sample_count=\$(ls -1 *.alignment.status.tsv 2>/dev/null | wc -l)"
        echo "completed_count=\$(awk -F '\\t' 'FNR > 1 && \$6 == "completed" { count++ } END { print count + 0 }' *.alignment.status.tsv 2>/dev/null)"
        echo "failed_count=\$(awk -F '\\t' 'FNR > 1 && \$6 == "failed" { count++ } END { print count + 0 }' *.alignment.status.tsv 2>/dev/null)"
        echo
        printf "sample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n"
        for sample_status in *.alignment.status.tsv; do
            [ -e "\${sample_status}" ] || continue
            awk -F '\\t' 'FNR > 1 { printf "%s\\t%s\\t%s\\t%s\\t%s\\t%s\\t%s\\n", \$3, \$4, \$5, \$6, \$7, \$8, \$9 }' "\${sample_status}"
        done
    } > alignment.step.log
    """
}


process ALIGNMENT_ASSERT_SUCCESS {
    tag 'alignment-check'

    input:
    path sample_statuses
    path step_log

    output:
    path "alignment.success", emit: ready

    script:
    """
    failed_count=\$(awk -F '\\t' 'FNR > 1 && \$6 == "failed" { count++ } END { print count + 0 }' *.alignment.status.tsv 2>/dev/null)
    if [ "\${failed_count}" -gt 0 ]; then
        echo "Alignment failed for \${failed_count} sample(s). See ${step_log} and sample status files." >&2
        exit 1
    fi
    touch alignment.success
    """
}


workflow ALIGNMENT {
    take:
    samples_ch
    pipeline_config
    tools_config
    reference_fasta
    infra_ready

    main:
    alignment_cfg = pipeline_config.alignment ?: [:]
    enabled_operations = alignment_cfg.workflow ?: []
    bam_qc_enabled = enabled_operations.contains('bam_QC')
    resolved_cfg = alignment_cfg.resolved ?: [:]
    alignment_step_cfg = alignment_cfg.fastq_alignment ?: [:]
    tool_name = alignment_step_cfg.tool ?: 'BWA v.0.7.17'
    tool_cfg = tools_config[tool_name] ?: [:]
    align_threads = (alignment_cfg.threads ?: 1) as int
    align_ram = alignment_cfg.ram ?: '1 GB'
    tool_path = resolved_cfg.fastq_alignment?.path ?: tool_cfg.path ?: tool_name.toLowerCase()
    tool_upper = tool_name.toUpperCase()
    tool_specific_cfg = alignment_step_cfg[tool_name] ?: [:]
    algorithm = tool_specific_cfg.algorithm ?: 'mem'
    extra_args = resolved_cfg.fastq_alignment?.resolved_args ?: (tool_specific_cfg.args ?: []).join(' ')
    samtools_path = resolved_cfg.samtools?.path ?: tools_config.SAMTOOLS?.path ?: 'samtools'
    bam_qc_cfg = alignment_cfg.bam_QC ?: [:]
    bam_qc_tool_name = bam_qc_cfg.tool ?: 'FASTQC v.0.11.8'
    bam_qc_tool_cfg = tools_config[bam_qc_tool_name] ?: [:]
    bam_qc_path = bam_qc_tool_cfg.path ?: 'fastqc'
    bam_qc_args = (bam_qc_cfg[bam_qc_tool_name]?.args ?: bam_qc_cfg.args ?: []).join(' ')

    fastq_samples = samples_ch
        .filter { row -> row.fastq_r1 && row.fastq_r2 }
        .combine(infra_ready)
        .map { row, ready -> row }

    if (tool_upper.startsWith('BWA')) {
        ALIGN_BWA(fastq_samples, align_threads, align_ram, tool_path, samtools_path, algorithm, extra_args, reference_fasta)
        aligned_bams = ALIGN_BWA.out.bams
        aligned_statuses = ALIGN_BWA.out.statuses
    } else if (tool_upper.startsWith('BOWTIE2')) {
        ALIGN_BOWTIE2(fastq_samples, align_threads, align_ram, tool_path, samtools_path, extra_args, reference_fasta)
        aligned_bams = ALIGN_BOWTIE2.out.bams
        aligned_statuses = ALIGN_BOWTIE2.out.statuses
    } else if (tool_upper.startsWith('NOVOALIGN')) {
        ALIGN_NOVOALIGN(fastq_samples, align_threads, align_ram, tool_path, samtools_path, extra_args, reference_fasta)
        aligned_bams = ALIGN_NOVOALIGN.out.bams
        aligned_statuses = ALIGN_NOVOALIGN.out.statuses
    } else {
        error "Unsupported aligner: ${tool_name}"
    }

    alignment_statuses = aligned_statuses
    bam_qc_reports = Channel.empty()
    if (bam_qc_enabled) {
        BAM_QC(aligned_bams, align_threads, align_ram, bam_qc_path, bam_qc_args)
        alignment_statuses = alignment_statuses.mix(BAM_QC.out.statuses)
        bam_qc_reports = BAM_QC.out.reports
    }

    status_files = alignment_statuses.map { sample_id, role, sample_name, log_file, status_file -> status_file }.collect()
    alignment_tool_names = bam_qc_enabled ? "${tool_name},${bam_qc_tool_name}" : tool_name
    ALIGNMENT_STEP_LOG(alignment_tool_names, status_files)
    ALIGNMENT_ASSERT_SUCCESS(status_files, ALIGNMENT_STEP_LOG.out.log)

    emit:
    bams = aligned_bams
    bam_qc_reports = bam_qc_reports
    statuses = alignment_statuses
    step_log = ALIGNMENT_STEP_LOG.out.log
    ready = ALIGNMENT_ASSERT_SUCCESS.out.ready
}
