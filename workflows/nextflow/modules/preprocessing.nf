nextflow.enable.dsl = 2


process INIT_PREPROCESSING_SAMPLE {
    tag "${sample_name}"

    input:
    tuple val(sample_id), val(role), val(sample_name), path(input_bam)

    output:
    tuple val(sample_id), val(role), val(sample_name), path(input_bam), path("${sample_name}.preprocessing.partial.log"), emit: initialized

    script:
    """
    {
        echo "step=preprocessing"
        echo "operation=macro_step"
        echo "sample_id=${sample_id}"
        echo "role=${role}"
        echo "sample_name=${sample_name}"
        echo "input_bam=${input_bam}"
        echo "started=\$(date -Is)"
        echo
    } > ${sample_name}.preprocessing.partial.log
    """
}


process ADD_READGROUPS {
    tag "${sample_name}"
    cpus { preprocess_threads }
    memory { preprocess_ram }

    input:
    tuple val(sample_id), val(role), val(sample_name), path(input_bam), path(cumulative_log)
    val preprocess_threads
    val preprocess_ram
    val picard_path
    val add_readgroups_args

    output:
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.readgroups.bam"), path("${sample_name}.preprocessing.partial.log"), emit: bams

    script:
    """
    set +e
    cp "${cumulative_log}" ${sample_name}.preprocessing.partial.log
    {
        echo "===== add_readgroups ====="
        echo "tool=${picard_path}"
        echo "input_bam=${input_bam}"
        echo "started=\$(date -Is)"
        echo "command=java -Xmx${task.memory.toGiga()}g -jar ${picard_path} AddOrReplaceReadGroups I=${input_bam} O=${sample_name}.readgroups.bam RGID=${sample_name} RGLB=${sample_name} RGPL=ILLUMINA RGPU=${sample_name} RGSM=${sample_name} ${add_readgroups_args}"
        echo
    } >> ${sample_name}.preprocessing.partial.log
    java -Xmx${task.memory.toGiga()}g -jar ${picard_path} AddOrReplaceReadGroups \
        I="${input_bam}" \
        O="${sample_name}.readgroups.bam" \
        RGID="${sample_name}" \
        RGLB="${sample_name}" \
        RGPL="ILLUMINA" \
        RGPU="${sample_name}" \
        RGSM="${sample_name}" \
        ${add_readgroups_args} >> ${sample_name}.preprocessing.partial.log 2>&1
    exit_code=\$?
    completed_at=\$(date -Is)
    if [ "\${exit_code}" -eq 0 ]; then
        echo "completed=\${completed_at}" >> ${sample_name}.preprocessing.partial.log
    else
        rm -f ${sample_name}.readgroups.bam
        echo "failed=\${completed_at}" >> ${sample_name}.preprocessing.partial.log
        echo "exit_code=\${exit_code}" >> ${sample_name}.preprocessing.partial.log
    fi
    echo >> ${sample_name}.preprocessing.partial.log
    exit 0
    """
}


process MARK_PCR_DUP {
    tag "${sample_name}"
    cpus { preprocess_threads }
    memory { preprocess_ram }
    publishDir "${params.outdir}/LOGS/PREPROCESSING/samples", mode: 'copy', pattern: '*.markdup.metrics.txt'

    input:
    tuple val(sample_id), val(role), val(sample_name), path(input_bam), path(cumulative_log)
    val preprocess_threads
    val preprocess_ram
    val picard_path
    val markdup_args

    output:
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.markdup.bam"), path("${sample_name}.preprocessing.partial.log"), emit: bams

    script:
    """
    set +e
    cp "${cumulative_log}" ${sample_name}.preprocessing.partial.log
    {
        echo "===== mark_pcr_dup ====="
        echo "tool=${picard_path}"
        echo "input_bam=${input_bam}"
        echo "started=\$(date -Is)"
        echo "command=java -Xmx${task.memory.toGiga()}g -jar ${picard_path} MarkDuplicates I=${input_bam} O=${sample_name}.markdup.bam M=${sample_name}.markdup.metrics.txt ${markdup_args}"
        echo
    } >> ${sample_name}.preprocessing.partial.log
    java -Xmx${task.memory.toGiga()}g -jar ${picard_path} MarkDuplicates \
        I="${input_bam}" \
        O="${sample_name}.markdup.bam" \
        M="${sample_name}.markdup.metrics.txt" \
        ${markdup_args} >> ${sample_name}.preprocessing.partial.log 2>&1
    exit_code=\$?
    completed_at=\$(date -Is)
    if [ "\${exit_code}" -eq 0 ]; then
        echo "completed=\${completed_at}" >> ${sample_name}.preprocessing.partial.log
    else
        rm -f ${sample_name}.markdup.bam
        echo "failed=\${completed_at}" >> ${sample_name}.preprocessing.partial.log
        echo "exit_code=\${exit_code}" >> ${sample_name}.preprocessing.partial.log
    fi
    echo >> ${sample_name}.preprocessing.partial.log
    exit 0
    """
}


process FINALIZE_PREPROCESSING {
    tag "${sample_name}"
    cpus { preprocess_threads }
    memory { preprocess_ram }
    publishDir "${params.outdir}/PREPROCESSING", mode: 'copy', pattern: '*.preprocessed.bam*'
    publishDir "${params.outdir}/LOGS/PREPROCESSING/samples", mode: 'copy', pattern: '*.preprocessing.log'
    publishDir "${params.outdir}/LOGS/PREPROCESSING/samples", mode: 'copy', pattern: '*.preprocessing.status.tsv'

    input:
    tuple val(sample_id), val(role), val(sample_name), path(input_bam), path(cumulative_log)
    val preprocess_threads
    val preprocess_ram
    val samtools_path
    val operations

    output:
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.preprocessed.bam"), path("${sample_name}.preprocessed.bam.bai"), optional: true, emit: bams
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.preprocessing.log"), path("${sample_name}.preprocessing.status.tsv"), emit: statuses

    script:
    """
    set +e
    cp "${cumulative_log}" ${sample_name}.preprocessing.log
    {
        echo "===== finalize ====="
        echo "operations=${operations.join(',')}"
        echo "input_bam=${input_bam}"
        echo "started=\$(date -Is)"
        echo "copy_command=cp ${input_bam} ${sample_name}.preprocessed.bam"
        echo "index_command=${samtools_path} index ${sample_name}.preprocessed.bam"
        echo
    } >> ${sample_name}.preprocessing.log
    started_at=\$(date -Is)
    cp "${input_bam}" ${sample_name}.preprocessed.bam >> ${sample_name}.preprocessing.log 2>&1
    copy_exit=\$?
    if [ "\${copy_exit}" -eq 0 ]; then
        ${samtools_path} index ${sample_name}.preprocessed.bam >> ${sample_name}.preprocessing.log 2>&1
        index_exit=\$?
    else
        index_exit=0
    fi
    completed_at=\$(date -Is)
    if [ "\${copy_exit}" -eq 0 ] && [ "\${index_exit}" -eq 0 ]; then
        status=completed
        exit_code=0
        echo "completed=\${completed_at}" >> ${sample_name}.preprocessing.log
    else
        status=failed
        exit_code=\${copy_exit}
        if [ "\${index_exit}" -ne 0 ]; then exit_code=\${index_exit}; fi
        rm -f ${sample_name}.preprocessed.bam ${sample_name}.preprocessed.bam.bai
        echo "failed=\${completed_at}" >> ${sample_name}.preprocessing.log
        echo "exit_code=\${exit_code}" >> ${sample_name}.preprocessing.log
    fi
    printf "step\\ttool\\tsample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n" > ${sample_name}.preprocessing.status.tsv
    printf "preprocessing\\tPICARD+SAMTOOLS\\t${sample_id}\\t${role}\\t${sample_name}\\t\${status}\\t\${exit_code}\\t\${started_at}\\t\${completed_at}\\n" >> ${sample_name}.preprocessing.status.tsv
    exit 0
    """
}


process PREPROCESSING_STEP_LOG {
    tag 'preprocessing'
    publishDir "${params.outdir}/LOGS/PREPROCESSING", mode: 'copy'

    input:
    val tool_name
    path sample_statuses

    output:
    path "preprocessing.step.log", emit: log

    script:
    """
    {
        echo "step=preprocessing"
        echo "tool=${tool_name}"
        echo "generated=\$(date -Is)"
        echo "sample_count=\$(ls -1 *.preprocessing.status.tsv 2>/dev/null | wc -l)"
        echo "completed_count=\$(awk -F '\\t' 'FNR > 1 && \$6 == "completed" { count++ } END { print count + 0 }' *.preprocessing.status.tsv 2>/dev/null)"
        echo "failed_count=\$(awk -F '\\t' 'FNR > 1 && \$6 == "failed" { count++ } END { print count + 0 }' *.preprocessing.status.tsv 2>/dev/null)"
        echo
        printf "sample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n"
        for sample_status in *.preprocessing.status.tsv; do
            [ -e "\${sample_status}" ] || continue
            awk -F '\\t' 'FNR > 1 { printf "%s\\t%s\\t%s\\t%s\\t%s\\t%s\\t%s\\n", \$3, \$4, \$5, \$6, \$7, \$8, \$9 }' "\${sample_status}"
        done
    } > preprocessing.step.log
    """
}


workflow PREPROCESSING {
    take:
    bam_ch
    pipeline_config
    tools_config
    infra_ready

    main:
    preprocessing_cfg = pipeline_config.preprocessing ?: [:]
    operations = preprocessing_cfg.workflow ?: ['add_readgroups', 'mark_pcr_dup']
    preprocess_threads = (preprocessing_cfg.threads ?: 1) as int
    preprocess_ram = preprocessing_cfg.ram ?: '1 GB'

    add_cfg = preprocessing_cfg.add_readgroups ?: [:]
    markdup_cfg = preprocessing_cfg.mark_pcr_dup ?: [:]
    tool_name = add_cfg.tool ?: markdup_cfg.tool ?: 'PICARD v.2.7.1'
    picard_path = tools_config[tool_name]?.path ?: tool_name
    samtools_path = tools_config.SAMTOOLS?.path ?: 'samtools'
    add_args = (add_cfg[tool_name]?.args ?: add_cfg.args ?: []).join(' ')
    markdup_args = (markdup_cfg[tool_name]?.args ?: markdup_cfg.args ?: []).join(' ')

    ready_bams = bam_ch
        .combine(infra_ready)
        .map { sample_id, role, sample_name, bam, bai, ready -> tuple(sample_id, role, sample_name, bam) }

    INIT_PREPROCESSING_SAMPLE(ready_bams)
    current_bams = INIT_PREPROCESSING_SAMPLE.out.initialized

    if (operations.contains('add_readgroups')) {
        ADD_READGROUPS(current_bams, preprocess_threads, preprocess_ram, picard_path, add_args)
        current_bams = ADD_READGROUPS.out.bams
    }

    if (operations.contains('mark_pcr_dup')) {
        MARK_PCR_DUP(current_bams, preprocess_threads, preprocess_ram, picard_path, markdup_args)
        current_bams = MARK_PCR_DUP.out.bams
    }

    FINALIZE_PREPROCESSING(current_bams, preprocess_threads, preprocess_ram, samtools_path, operations)
    PREPROCESSING_STEP_LOG(tool_name, FINALIZE_PREPROCESSING.out.statuses.map { sample_id, role, sample_name, log_file, status_file -> status_file }.collect())

    emit:
    bams = FINALIZE_PREPROCESSING.out.bams
    statuses = FINALIZE_PREPROCESSING.out.statuses
    step_log = PREPROCESSING_STEP_LOG.out.log
}
