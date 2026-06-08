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


workflow ALIGNMENT {
    take:
    samples_ch
    pipeline_config
    tools_config
    reference_fasta
    infra_ready

    main:
    alignment_cfg = pipeline_config.alignment ?: [:]
    alignment_step_cfg = alignment_cfg.fastq_alignment ?: [:]
    tool_name = alignment_step_cfg.tool ?: 'BWA v.0.7.17'
    tool_cfg = tools_config[tool_name] ?: [:]
    align_threads = (alignment_cfg.threads ?: 1) as int
    align_ram = alignment_cfg.ram ?: '1 GB'
    tool_path = tool_cfg.path ?: tool_name.toLowerCase()
    tool_upper = tool_name.toUpperCase()
    tool_specific_cfg = alignment_step_cfg[tool_name] ?: [:]
    algorithm = tool_specific_cfg.algorithm ?: 'mem'
    extra_args = (tool_specific_cfg.args ?: []).join(' ')
    samtools_path = tools_config.SAMTOOLS?.path ?: 'samtools'

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

    ALIGNMENT_STEP_LOG(tool_name, aligned_statuses.map { sample_id, role, sample_name, log_file, status_file -> status_file }.collect())

    emit:
    bams = aligned_bams
    statuses = aligned_statuses
    step_log = ALIGNMENT_STEP_LOG.out.log
}
