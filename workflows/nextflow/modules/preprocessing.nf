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
    def picard_cmd = picard_path.toString().endsWith('.jar') ? "java -Xmx${task.memory.toGiga()}g -jar ${picard_path}" : picard_path
    """
    set +e
    cp -L "${cumulative_log}" ${sample_name}.preprocessing.partial.log.tmp
    copy_log_exit=\$?
    if [ "\${copy_log_exit}" -ne 0 ]; then exit \${copy_log_exit}; fi
    mv ${sample_name}.preprocessing.partial.log.tmp ${sample_name}.preprocessing.partial.log
    {
        echo "===== add_readgroups ====="
        echo "tool=${picard_path}"
        echo "input_bam=${input_bam}"
        echo "started=\$(date -Is)"
        echo "command=${picard_cmd} AddOrReplaceReadGroups I=${input_bam} O=${sample_name}.readgroups.bam RGID=${sample_name} RGLB=${sample_name} RGPL=ILLUMINA RGPU=${sample_name} RGSM=${sample_name} CREATE_INDEX=true ${add_readgroups_args}"
        echo
    } >> ${sample_name}.preprocessing.partial.log
    ${picard_cmd} AddOrReplaceReadGroups \
        I="${input_bam}" \
        O="${sample_name}.readgroups.bam" \
        RGID="${sample_name}" \
        RGLB="${sample_name}" \
        RGPL="ILLUMINA" \
        RGPU="${sample_name}" \
        RGSM="${sample_name}" \
        CREATE_INDEX=true \
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
    exit \${exit_code}
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
    def picard_cmd = picard_path.toString().endsWith('.jar') ? "java -Xmx${task.memory.toGiga()}g -jar ${picard_path}" : picard_path
    """
    set +e
    cp -L "${cumulative_log}" ${sample_name}.preprocessing.partial.log.tmp
    copy_log_exit=\$?
    if [ "\${copy_log_exit}" -ne 0 ]; then exit \${copy_log_exit}; fi
    mv ${sample_name}.preprocessing.partial.log.tmp ${sample_name}.preprocessing.partial.log
    {
        echo "===== mark_pcr_dup ====="
        echo "tool=${picard_path}"
        echo "input_bam=${input_bam}"
        echo "started=\$(date -Is)"
        echo "command=${picard_cmd} MarkDuplicates I=${input_bam} O=${sample_name}.markdup.bam M=${sample_name}.markdup.metrics.txt CREATE_INDEX=true ${markdup_args}"
        echo
    } >> ${sample_name}.preprocessing.partial.log
    ${picard_cmd} MarkDuplicates \
        I="${input_bam}" \
        O="${sample_name}.markdup.bam" \
        M="${sample_name}.markdup.metrics.txt" \
        CREATE_INDEX=true \
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
    exit \${exit_code}
    """
}


process INDEL_REALIGNMENT {
    tag "${sample_name}"
    cpus { preprocess_threads }
    memory { preprocess_ram }
    container { gatk3_container ?: null }

    input:
    tuple val(sample_id), val(role), val(sample_name), path(input_bam), path(cumulative_log)
    val preprocess_threads
    val preprocess_ram
    val gatk3_path
    val gatk3_container
    val gatk3_java_home
    val gatk3_java_cmd
    val mills_path
    val target_intervals
    val indel_args
    val reference_fasta

    output:
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.indelrealigned.bam"), path("${sample_name}.preprocessing.partial.log"), emit: bams

    script:
    def java_bin = gatk3_java_cmd ?: (gatk3_java_home ? "${gatk3_java_home}/bin/java" : 'java')
    def java_cmd = gatk3_path.toString().endsWith('.jar') ? "${java_bin} -Xmx${task.memory.toGiga()}g -jar ${gatk3_path}" : gatk3_path
    def mills_arg = mills_path ? "-known ${mills_path}" : ''
    def target_arg = target_intervals ? "-L ${target_intervals}" : ''
    """
    set +e
    if [ -n "${gatk3_java_cmd}" ]; then
        export PATH="\$(dirname "${gatk3_java_cmd}"):\${PATH}"
        export JAVA_HOME="\$(dirname "\$(dirname "${gatk3_java_cmd}")")"
    elif [ -n "${gatk3_java_home}" ]; then
        export JAVA_HOME="${gatk3_java_home}"
        export PATH="${gatk3_java_home}/bin:\${PATH}"
    fi
    cp -L "${cumulative_log}" ${sample_name}.preprocessing.partial.log.tmp
    copy_log_exit=\$?
    if [ "\${copy_log_exit}" -ne 0 ]; then exit \${copy_log_exit}; fi
    mv ${sample_name}.preprocessing.partial.log.tmp ${sample_name}.preprocessing.partial.log
    {
        echo "===== indel_realignment ====="
        echo "tool=${gatk3_path}"
        echo "input_bam=${input_bam}"
        echo "reference=${reference_fasta}"
        echo "mills=${mills_path}"
        echo "target_intervals=${target_intervals}"
        echo "java_home=\${JAVA_HOME:-}"
        echo "java_version=\$(${java_bin} -version 2>&1 | head -n 1)"
        echo "started=\$(date -Is)"
        echo "target_command=${java_cmd} -T RealignerTargetCreator -R ${reference_fasta} -I ${input_bam} -o ${sample_name}.IndelRealigner.intervals ${target_arg} ${mills_arg} ${indel_args}"
        echo "realign_command=${java_cmd} -T IndelRealigner -R ${reference_fasta} -I ${input_bam} -targetIntervals ${sample_name}.IndelRealigner.intervals -o ${sample_name}.indelrealigned.bam ${mills_arg} ${indel_args}"
        echo
    } >> ${sample_name}.preprocessing.partial.log
    ${java_cmd} -T RealignerTargetCreator \
        -R "${reference_fasta}" \
        -I "${input_bam}" \
        -o "${sample_name}.IndelRealigner.intervals" \
        ${target_arg} \
        ${mills_arg} \
        ${indel_args} >> ${sample_name}.preprocessing.partial.log 2>&1
    target_exit=\$?
    if [ "\${target_exit}" -eq 0 ]; then
        ${java_cmd} -T IndelRealigner \
            -R "${reference_fasta}" \
            -I "${input_bam}" \
            -targetIntervals "${sample_name}.IndelRealigner.intervals" \
            -o "${sample_name}.indelrealigned.bam" \
            ${mills_arg} \
            ${indel_args} >> ${sample_name}.preprocessing.partial.log 2>&1
        realign_exit=\$?
    else
        realign_exit=0
    fi
    completed_at=\$(date -Is)
    if [ "\${target_exit}" -eq 0 ] && [ "\${realign_exit}" -eq 0 ]; then
        echo "completed=\${completed_at}" >> ${sample_name}.preprocessing.partial.log
    else
        rm -f ${sample_name}.indelrealigned.bam
        echo "failed=\${completed_at}" >> ${sample_name}.preprocessing.partial.log
        echo "exit_code=\${target_exit}" >> ${sample_name}.preprocessing.partial.log
        if [ "\${realign_exit}" -ne 0 ]; then echo "exit_code=\${realign_exit}" >> ${sample_name}.preprocessing.partial.log; fi
    fi
    echo >> ${sample_name}.preprocessing.partial.log
    if [ "\${target_exit}" -ne 0 ]; then exit \${target_exit}; fi
    exit \${realign_exit}
    """
}


process BQ_RECALIBRATION {
    tag "${sample_name}"
    cpus { preprocess_threads }
    memory { preprocess_ram }
    container { gatk3_container ?: null }

    input:
    tuple val(sample_id), val(role), val(sample_name), path(input_bam), path(cumulative_log)
    val preprocess_threads
    val preprocess_ram
    val gatk3_path
    val gatk3_container
    val gatk3_java_home
    val gatk3_java_cmd
    val dbsnp_path
    val mills_path
    val target_intervals
    val bqsr_args
    val reference_fasta

    output:
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.bqsr.bam"), path("${sample_name}.preprocessing.partial.log"), emit: bams

    script:
    def java_bin = gatk3_java_cmd ?: (gatk3_java_home ? "${gatk3_java_home}/bin/java" : 'java')
    def java_cmd = gatk3_path.toString().endsWith('.jar') ? "${java_bin} -Xmx${task.memory.toGiga()}g -jar ${gatk3_path}" : gatk3_path
    def dbsnp_arg = dbsnp_path ? "-knownSites ${dbsnp_path}" : ''
    def mills_arg = mills_path ? "-knownSites ${mills_path}" : ''
    def target_arg = target_intervals ? "-L ${target_intervals}" : ''
    """
    set +e
    if [ -n "${gatk3_java_cmd}" ]; then
        export PATH="\$(dirname "${gatk3_java_cmd}"):\${PATH}"
        export JAVA_HOME="\$(dirname "\$(dirname "${gatk3_java_cmd}")")"
    elif [ -n "${gatk3_java_home}" ]; then
        export JAVA_HOME="${gatk3_java_home}"
        export PATH="${gatk3_java_home}/bin:\${PATH}"
    fi
    cp -L "${cumulative_log}" ${sample_name}.preprocessing.partial.log.tmp
    copy_log_exit=\$?
    if [ "\${copy_log_exit}" -ne 0 ]; then exit \${copy_log_exit}; fi
    mv ${sample_name}.preprocessing.partial.log.tmp ${sample_name}.preprocessing.partial.log
    {
        echo "===== BQ_recalibration ====="
        echo "tool=${gatk3_path}"
        echo "input_bam=${input_bam}"
        echo "reference=${reference_fasta}"
        echo "dbsnp=${dbsnp_path}"
        echo "mills=${mills_path}"
        echo "target_intervals=${target_intervals}"
        echo "java_home=\${JAVA_HOME:-}"
        echo "java_version=\$(${java_bin} -version 2>&1 | head -n 1)"
        echo "started=\$(date -Is)"
        echo "recal_command=${java_cmd} -T BaseRecalibrator -R ${reference_fasta} -I ${input_bam} -o ${sample_name}.BQSR.table ${target_arg} ${dbsnp_arg} ${mills_arg} ${bqsr_args}"
        echo "printreads_command=${java_cmd} -T PrintReads -R ${reference_fasta} -I ${input_bam} -BQSR ${sample_name}.BQSR.table -o ${sample_name}.bqsr.bam ${target_arg} ${bqsr_args}"
        echo
    } >> ${sample_name}.preprocessing.partial.log
    ${java_cmd} -T BaseRecalibrator \
        -R "${reference_fasta}" \
        -I "${input_bam}" \
        -o "${sample_name}.BQSR.table" \
        ${target_arg} \
        ${dbsnp_arg} \
        ${mills_arg} \
        ${bqsr_args} >> ${sample_name}.preprocessing.partial.log 2>&1
    recal_exit=\$?
    if [ "\${recal_exit}" -eq 0 ]; then
        ${java_cmd} -T PrintReads \
            -R "${reference_fasta}" \
            -I "${input_bam}" \
            -BQSR "${sample_name}.BQSR.table" \
            -o "${sample_name}.bqsr.bam" \
            ${target_arg} \
            ${bqsr_args} >> ${sample_name}.preprocessing.partial.log 2>&1
        printreads_exit=\$?
    else
        printreads_exit=0
    fi
    completed_at=\$(date -Is)
    if [ "\${recal_exit}" -eq 0 ] && [ "\${printreads_exit}" -eq 0 ]; then
        echo "completed=\${completed_at}" >> ${sample_name}.preprocessing.partial.log
    else
        rm -f ${sample_name}.bqsr.bam
        echo "failed=\${completed_at}" >> ${sample_name}.preprocessing.partial.log
        echo "exit_code=\${recal_exit}" >> ${sample_name}.preprocessing.partial.log
        if [ "\${printreads_exit}" -ne 0 ]; then echo "exit_code=\${printreads_exit}" >> ${sample_name}.preprocessing.partial.log; fi
    fi
    echo >> ${sample_name}.preprocessing.partial.log
    if [ "\${recal_exit}" -ne 0 ]; then exit \${recal_exit}; fi
    exit \${printreads_exit}
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


process PREPROCESSING_ASSERT_SUCCESS {
    tag 'preprocessing-check'

    input:
    path sample_statuses
    path step_log

    output:
    path "preprocessing.success", emit: ready

    script:
    """
    failed_count=\$(awk -F '\\t' 'FNR > 1 && \$6 == "failed" { count++ } END { print count + 0 }' *.preprocessing.status.tsv 2>/dev/null)
    if [ "\${failed_count}" -gt 0 ]; then
        echo "Preprocessing failed for \${failed_count} sample(s). See ${step_log} and sample status files." >&2
        exit 1
    fi
    touch preprocessing.success
    """
}


workflow PREPROCESSING {
    take:
    bam_ch
    pipeline_config
    tools_config
    reference_fasta
    infra_ready

    main:
    preprocessing_cfg = pipeline_config.preprocessing ?: [:]
    resolved_cfg = preprocessing_cfg.resolved ?: [:]
    operations = preprocessing_cfg.workflow ?: ['add_readgroups', 'mark_pcr_dup']
    preprocess_threads = (preprocessing_cfg.threads ?: 1) as int
    preprocess_ram = preprocessing_cfg.ram ?: '1 GB'

    add_cfg = preprocessing_cfg.add_readgroups ?: [:]
    markdup_cfg = preprocessing_cfg.mark_pcr_dup ?: [:]
    indel_cfg = preprocessing_cfg.indel_realignment ?: [:]
    bqsr_cfg = preprocessing_cfg.BQ_recalibration ?: [:]
    tool_name = add_cfg.tool ?: markdup_cfg.tool ?: 'PICARD v.2.7.1'
    picard_path = resolved_cfg.picard?.path ?: tools_config[tool_name]?.path ?: tool_name
    samtools_path = resolved_cfg.samtools?.path ?: tools_config.SAMTOOLS?.path ?: 'samtools'
    add_args = (add_cfg[tool_name]?.args ?: add_cfg.args ?: []).join(' ')
    markdup_args = (markdup_cfg[tool_name]?.args ?: markdup_cfg.args ?: []).join(' ')
    gatk3_tool_name = indel_cfg.tool ?: bqsr_cfg.tool ?: 'GATK v.3.7'
    gatk3_tool_cfg = tools_config[gatk3_tool_name] ?: [:]
    gatk3_container = (gatk3_tool_cfg.container instanceof Map ? gatk3_tool_cfg.container.image : gatk3_tool_cfg.container) ?: resolved_cfg.gatk3?.container?.image ?: ''
    gatk3_path = gatk3_container ? (gatk3_tool_cfg.path ?: resolved_cfg.gatk3?.path ?: gatk3_tool_name) : (resolved_cfg.gatk3?.path ?: gatk3_tool_cfg.path ?: gatk3_tool_name)
    gatk3_java_home = gatk3_container ? '' : (resolved_cfg.gatk3?.java_home ?: resolved_cfg.gatk3?.javaHome ?: tools_config[gatk3_tool_name]?.java_home ?: tools_config[gatk3_tool_name]?.javaHome ?: System.getenv('GATK_JAVA_HOME') ?: '')
    gatk3_java_cmd = gatk3_container ? '' : (resolved_cfg.gatk3?.java_path ?: resolved_cfg.gatk3?.java_cmd ?: resolved_cfg.gatk3?.java ?: tools_config[gatk3_tool_name]?.java_path ?: tools_config[gatk3_tool_name]?.java_cmd ?: tools_config[gatk3_tool_name]?.java ?: System.getenv('GATK_JAVA_CMD') ?: '')
    target_intervals = resolved_cfg.target_intervals ?: preprocessing_cfg.target_intervals ?: preprocessing_cfg.target_list ?: preprocessing_cfg.target_bed ?: ''
    indel_tool_cfg = indel_cfg[gatk3_tool_name] ?: [:]
    bqsr_tool_cfg = bqsr_cfg[gatk3_tool_name] ?: [:]
    indel_args = (indel_tool_cfg.args ?: indel_cfg.args ?: []).join(' ')
    bqsr_args = (bqsr_tool_cfg.args ?: bqsr_cfg.args ?: []).join(' ')
    indel_mills_key = indel_tool_cfg.mills ?: indel_cfg.mills ?: bqsr_tool_cfg.mills ?: bqsr_cfg.mills ?: 'mills'
    bqsr_mills_key = bqsr_tool_cfg.mills ?: bqsr_cfg.mills ?: indel_mills_key
    bqsr_dbsnp_key = bqsr_tool_cfg.dbsnp ?: bqsr_cfg.dbsnp ?: 'dbsnp'
    indel_mills_path = resolved_cfg.databases?.indel_mills?.path ?: tools_config[indel_mills_key]?.path ?: tools_config[indel_mills_key?.toString()?.toLowerCase()]?.path ?: ''
    bqsr_mills_path = resolved_cfg.databases?.bqsr_mills?.path ?: tools_config[bqsr_mills_key]?.path ?: tools_config[bqsr_mills_key?.toString()?.toLowerCase()]?.path ?: ''
    bqsr_dbsnp_path = resolved_cfg.databases?.bqsr_dbsnp?.path ?: tools_config[bqsr_dbsnp_key]?.path ?: tools_config[bqsr_dbsnp_key?.toString()?.toLowerCase()]?.path ?: ''

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

    if (operations.contains('indel_realignment')) {
        INDEL_REALIGNMENT(current_bams, preprocess_threads, preprocess_ram, gatk3_path, gatk3_container, gatk3_java_home, gatk3_java_cmd, indel_mills_path, target_intervals, indel_args, reference_fasta)
        current_bams = INDEL_REALIGNMENT.out.bams
    }

    if (operations.contains('BQ_recalibration')) {
        BQ_RECALIBRATION(current_bams, preprocess_threads, preprocess_ram, gatk3_path, gatk3_container, gatk3_java_home, gatk3_java_cmd, bqsr_dbsnp_path, bqsr_mills_path, target_intervals, bqsr_args, reference_fasta)
        current_bams = BQ_RECALIBRATION.out.bams
    }

    FINALIZE_PREPROCESSING(current_bams, preprocess_threads, preprocess_ram, samtools_path, operations)
    status_files = FINALIZE_PREPROCESSING.out.statuses.map { sample_id, role, sample_name, log_file, status_file -> status_file }.collect()
    PREPROCESSING_STEP_LOG(tool_name, status_files)
    PREPROCESSING_ASSERT_SUCCESS(status_files, PREPROCESSING_STEP_LOG.out.log)

    emit:
    bams = FINALIZE_PREPROCESSING.out.bams
    statuses = FINALIZE_PREPROCESSING.out.statuses
    step_log = PREPROCESSING_STEP_LOG.out.log
    ready = PREPROCESSING_ASSERT_SUCCESS.out.ready
}
