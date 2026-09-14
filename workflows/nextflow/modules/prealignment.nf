nextflow.enable.dsl = 2


process TRIM_CUTADAPT {
    tag "${row.sample_name}"
    cpus { prealign_threads }
    memory { trim_ram }
    container { cutadapt_container ?: null }
    publishDir "${params.outdir}/PREALIGNMENT/trimmed", mode: 'copy', pattern: '*.trim.fastq.gz'
    publishDir "${params.outdir}/LOGS/PREALIGNMENT/samples", mode: 'copy', pattern: '*.trim_adapters.prealignment.log'
    publishDir "${params.outdir}/LOGS/PREALIGNMENT/samples", mode: 'copy', pattern: '*.trim_adapters.prealignment.status.tsv'

    input:
    val row
    val prealign_threads
    val trim_ram
    val cutadapt_path
    val cutadapt_container
    val cutadapt_args
    val adapter_args

    output:
    tuple val(row), path("${row.sample_name}.R1.trim.fastq.gz"), path("${row.sample_name}.R2.trim.fastq.gz"), optional: true, emit: reads
    tuple val(row.sample_id), val(row.role), val(row.sample_name), path("${row.sample_name}.trim_adapters.prealignment.log"), path("${row.sample_name}.trim_adapters.prealignment.status.tsv"), emit: statuses

    script:
    """
    set +e
    {
        echo "step=prealignment"
        echo "operation=trim_adapters"
        echo "tool=CUTADAPT"
        echo "sample_id=${row.sample_id}"
        echo "role=${row.role}"
        echo "sample_name=${row.sample_name}"
        echo "threads=${task.cpus}"
        echo "container=${cutadapt_container}"
        echo "fastq_r1=${row.fastq_r1}"
        echo "fastq_r2=${row.fastq_r2}"
        echo "started=\$(date -Is)"
        echo "command=${cutadapt_path} ${adapter_args} ${cutadapt_args} -o ${row.sample_name}.R1.trim.fastq.gz -p ${row.sample_name}.R2.trim.fastq.gz ${row.fastq_r1} ${row.fastq_r2}"
        echo
    } > ${row.sample_name}.trim_adapters.prealignment.log
    started_at=\$(date -Is)
    ${cutadapt_path} ${adapter_args} ${cutadapt_args} \
        -o ${row.sample_name}.R1.trim.fastq.gz \
        -p ${row.sample_name}.R2.trim.fastq.gz \
        ${row.fastq_r1} ${row.fastq_r2} >> ${row.sample_name}.trim_adapters.prealignment.log 2>&1
    exit_code=\$?
    completed_at=\$(date -Is)
    if [ "\${exit_code}" -eq 0 ]; then
        status=completed
        echo "completed=\${completed_at}" >> ${row.sample_name}.trim_adapters.prealignment.log
    else
        status=failed
        rm -f ${row.sample_name}.R1.trim.fastq.gz ${row.sample_name}.R2.trim.fastq.gz
        echo "failed=\${completed_at}" >> ${row.sample_name}.trim_adapters.prealignment.log
        echo "exit_code=\${exit_code}" >> ${row.sample_name}.trim_adapters.prealignment.log
    fi
    printf "step\\ttool\\tsample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n" > ${row.sample_name}.trim_adapters.prealignment.status.tsv
    printf "prealignment\\tCUTADAPT\\t${row.sample_id}\\t${row.role}\\t${row.sample_name}\\t\${status}\\t\${exit_code}\\t\${started_at}\\t\${completed_at}\\n" >> ${row.sample_name}.trim_adapters.prealignment.status.tsv
    exit 0
    """
}


process TRIM_SURECALL {
    tag "${row.sample_name}"
    cpus { prealign_threads }
    memory { trim_ram }
    publishDir "${params.outdir}/PREALIGNMENT/trimmed", mode: 'copy', pattern: '*.trim.fastq.gz'
    publishDir "${params.outdir}/LOGS/PREALIGNMENT/samples", mode: 'copy', pattern: '*.trim_adapters.prealignment.log'
    publishDir "${params.outdir}/LOGS/PREALIGNMENT/samples", mode: 'copy', pattern: '*.trim_adapters.prealignment.status.tsv'

    input:
    val row
    val prealign_threads
    val trim_ram
    val surecall_path
    val surecall_heap
    val surecall_args

    output:
    tuple val(row), path("${row.sample_name}.R1.trim.fastq.gz"), path("${row.sample_name}.R2.trim.fastq.gz"), optional: true, emit: reads
    tuple val(row.sample_id), val(row.role), val(row.sample_name), path("${row.sample_name}.trim_adapters.prealignment.log"), path("${row.sample_name}.trim_adapters.prealignment.status.tsv"), emit: statuses

    script:
    """
    set +e
    mkdir -p surecall_output
    {
        echo "step=prealignment"
        echo "operation=trim_adapters"
        echo "tool=SURECALLTRIMMER"
        echo "sample_id=${row.sample_id}"
        echo "role=${row.role}"
        echo "sample_name=${row.sample_name}"
        echo "threads=${task.cpus}"
        echo "fastq_r1=${row.fastq_r1}"
        echo "fastq_r2=${row.fastq_r2}"
        echo "started=\$(date -Is)"
        echo "command=java ${surecall_heap} -jar ${surecall_path} -fq1 ${row.fastq_r1} -fq2 ${row.fastq_r2} -out_loc surecall_output ${surecall_args}"
        echo
    } > ${row.sample_name}.trim_adapters.prealignment.log
    started_at=\$(date -Is)
    java ${surecall_heap} -jar ${surecall_path} \
        -fq1 ${row.fastq_r1} -fq2 ${row.fastq_r2} \
        -out_loc surecall_output ${surecall_args} >> ${row.sample_name}.trim_adapters.prealignment.log 2>&1
    exit_code=\$?
    if [ "\${exit_code}" -eq 0 ]; then
        r1_name=\$(basename ${row.fastq_r1})
        r2_name=\$(basename ${row.fastq_r2})
        r1_output=\$(find surecall_output -maxdepth 1 -type f -name "\${r1_name}*" ! -name '*.txt.gz' | head -n 1)
        r2_output=\$(find surecall_output -maxdepth 1 -type f -name "\${r2_name}*" ! -name '*.txt.gz' | head -n 1)
        if [ -n "\${r1_output}" ] && [ -n "\${r2_output}" ]; then
            cp "\${r1_output}" ${row.sample_name}.R1.trim.fastq.gz
            cp "\${r2_output}" ${row.sample_name}.R2.trim.fastq.gz
        else
            echo "SurecallTrimmer completed but paired FASTQ outputs were not found." >> ${row.sample_name}.trim_adapters.prealignment.log
            exit_code=1
        fi
    fi
    completed_at=\$(date -Is)
    if [ "\${exit_code}" -eq 0 ]; then
        status=completed
        echo "completed=\${completed_at}" >> ${row.sample_name}.trim_adapters.prealignment.log
    else
        status=failed
        rm -f ${row.sample_name}.R1.trim.fastq.gz ${row.sample_name}.R2.trim.fastq.gz
        echo "failed=\${completed_at}" >> ${row.sample_name}.trim_adapters.prealignment.log
        echo "exit_code=\${exit_code}" >> ${row.sample_name}.trim_adapters.prealignment.log
    fi
    printf "step\\ttool\\tsample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n" > ${row.sample_name}.trim_adapters.prealignment.status.tsv
    printf "prealignment\\tSURECALLTRIMMER\\t${row.sample_id}\\t${row.role}\\t${row.sample_name}\\t\${status}\\t\${exit_code}\\t\${started_at}\\t\${completed_at}\\n" >> ${row.sample_name}.trim_adapters.prealignment.status.tsv
    exit 0
    """
}


process FASTQ_QC {
    tag "${row.sample_name}"
    cpus { prealign_threads }
    memory { prealign_ram }
    publishDir "${params.outdir}/PREALIGNMENT/fastqc", mode: 'copy', pattern: 'fastqc_out/*'
    publishDir "${params.outdir}/LOGS/PREALIGNMENT/samples", mode: 'copy', pattern: '*.fastq_QC.prealignment.log'
    publishDir "${params.outdir}/LOGS/PREALIGNMENT/samples", mode: 'copy', pattern: '*.fastq_QC.prealignment.status.tsv'

    input:
    val row
    val prealign_threads
    val prealign_ram
    val fastqc_path
    val fastqc_args

    output:
    tuple val(row.sample_id), val(row.role), val(row.sample_name), path("fastqc_out/*"), optional: true, emit: reports
    tuple val(row.sample_id), val(row.role), val(row.sample_name), path("${row.sample_name}.fastq_QC.prealignment.log"), path("${row.sample_name}.fastq_QC.prealignment.status.tsv"), emit: statuses

    script:
    def fastq2 = row.fastq_r2 ? row.fastq_r2 : ''
    """
    set +e
    mkdir -p fastqc_out
    if [ -x "${fastqc_path}" ]; then
        fastqc_cmd="${fastqc_path}"
    else
        fastqc_cmd="perl ${fastqc_path}"
    fi
    {
        echo "step=prealignment"
        echo "operation=fastq_QC"
        echo "tool=FASTQC"
        echo "sample_id=${row.sample_id}"
        echo "role=${row.role}"
        echo "sample_name=${row.sample_name}"
        echo "threads=${task.cpus}"
        echo "fastq_r1=${row.fastq_r1}"
        echo "fastq_r2=${row.fastq_r2}"
        echo "started=\$(date -Is)"
        echo "command=\${fastqc_cmd} -t ${task.cpus} -o fastqc_out ${fastqc_args} ${row.fastq_r1} ${fastq2}"
        echo
    } > ${row.sample_name}.fastq_QC.prealignment.log
    started_at=\$(date -Is)
    \${fastqc_cmd} -t ${task.cpus} -o fastqc_out ${fastqc_args} ${row.fastq_r1} ${fastq2} >> ${row.sample_name}.fastq_QC.prealignment.log 2>&1
    exit_code=\$?
    completed_at=\$(date -Is)
    if [ "\${exit_code}" -eq 0 ]; then
        status=completed
        echo "completed=\${completed_at}" >> ${row.sample_name}.fastq_QC.prealignment.log
    else
        status=failed
        echo "failed=\${completed_at}" >> ${row.sample_name}.fastq_QC.prealignment.log
        echo "exit_code=\${exit_code}" >> ${row.sample_name}.fastq_QC.prealignment.log
    fi
    printf "step\\ttool\\tsample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n" > ${row.sample_name}.fastq_QC.prealignment.status.tsv
    printf "prealignment\\tFASTQC\\t${row.sample_id}\\t${row.role}\\t${row.sample_name}\\t\${status}\\t\${exit_code}\\t\${started_at}\\t\${completed_at}\\n" >> ${row.sample_name}.fastq_QC.prealignment.status.tsv
    exit 0
    """
}


process PREALIGNMENT_STEP_LOG {
    tag 'prealignment'
    publishDir "${params.outdir}/LOGS/PREALIGNMENT", mode: 'copy'

    input:
    val tool_name
    path sample_statuses

    output:
    path "prealignment.step.log", emit: log

    script:
    """
    {
        echo "step=prealignment"
        echo "tool=${tool_name}"
        echo "generated=\$(date -Is)"
        echo "sample_count=\$(ls -1 *.prealignment.status.tsv 2>/dev/null | wc -l)"
        echo "completed_count=\$(awk -F '\\t' 'FNR > 1 && \$6 == "completed" { count++ } END { print count + 0 }' *.prealignment.status.tsv 2>/dev/null)"
        echo "failed_count=\$(awk -F '\\t' 'FNR > 1 && \$6 == "failed" { count++ } END { print count + 0 }' *.prealignment.status.tsv 2>/dev/null)"
        echo
        printf "sample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n"
        for sample_status in *.prealignment.status.tsv; do
            [ -e "\${sample_status}" ] || continue
            awk -F '\\t' 'FNR > 1 { printf "%s\\t%s\\t%s\\t%s\\t%s\\t%s\\t%s\\n", \$3, \$4, \$5, \$6, \$7, \$8, \$9 }' "\${sample_status}"
        done
    } > prealignment.step.log
    """
}


process PREALIGNMENT_ASSERT_SUCCESS {
    tag 'prealignment-check'

    input:
    path sample_statuses
    path step_log

    output:
    path "prealignment.success", emit: ready

    script:
    """
    failed_count=\$(awk -F '\\t' 'FNR > 1 && \$6 == "failed" { count++ } END { print count + 0 }' *.prealignment.status.tsv 2>/dev/null)
    if [ "\${failed_count}" -gt 0 ]; then
        echo "Prealignment failed for \${failed_count} sample(s). See ${step_log} and sample status files." >&2
        exit 1
    fi
    touch prealignment.success
    """
}


workflow PREALIGNMENT {
    take:
    samples_ch
    pipeline_config
    tools_config
    infra_ready

    main:
    prealignment_cfg = pipeline_config.prealignment ?: [:]
    enabled_operations = prealignment_cfg.workflow ?: []
    trim_enabled = enabled_operations.contains('trim_adapters')
    fastq_qc_enabled = enabled_operations.contains('fastq_QC')
    trim_cfg = prealignment_cfg.trim_adapters ?: [:]
    trim_tool_name = trim_cfg.tool ?: 'CUTADAPT'
    trim_tool_cfg = tools_config[trim_tool_name] ?: [:]
    resolved_cfg = prealignment_cfg.resolved ?: [:]
    trim_tool_args = trim_cfg[trim_tool_name]?.args ?: trim_cfg.args ?: []
    fastq_qc_cfg = prealignment_cfg.fastq_QC ?: [:]
    fastq_qc_tool_name = fastq_qc_cfg.tool ?: 'FASTQC v.0.11.8'
    fastq_qc_tool_cfg = tools_config[fastq_qc_tool_name] ?: [:]
    prealign_threads = (prealignment_cfg.threads ?: 1) as int
    prealign_ram = prealignment_cfg.ram ?: '1 GB'
    trim_ram = trim_tool_cfg.ram ?: prealign_ram
    fastqc_path = fastq_qc_tool_cfg.path ?: 'fastqc'
    fastqc_args = (fastq_qc_cfg[fastq_qc_tool_name]?.args ?: fastq_qc_cfg.args ?: []).join(' ')

    fastq_samples = samples_ch
        .filter { row -> row.fastq_r1 && row.fastq_r2 }
        .combine(infra_ready)
        .map { row, ready -> row }

    operation_statuses = Channel.empty()
    reports_ch = Channel.empty()
    reads_ch = fastq_samples

    if (trim_enabled) {
        if (trim_tool_name.toUpperCase().startsWith('CUTADAPT')) {
            has_custom_adapters = trim_tool_args.any { arg ->
                def value = arg.toString()
                value in ['-a', '-A', '-g', '-G', '-b', '-B', '--adapter', '--front', '--anywhere'] ||
                    value.startsWith('--adapter=') || value.startsWith('--front=') || value.startsWith('--anywhere=')
            }
            default_adapter_args = []
            if (trim_cfg.adapter1) default_adapter_args.addAll(['-a', trim_cfg.adapter1])
            if (trim_cfg.adapter2) default_adapter_args.addAll(['-A', trim_cfg.adapter2])
            adapter_args = has_custom_adapters ? '' : default_adapter_args.join(' ')
            TRIM_CUTADAPT(
                fastq_samples,
                prealign_threads,
                trim_ram,
                trim_tool_cfg.path ?: 'cutadapt',
                (trim_tool_cfg.container instanceof Map ? trim_tool_cfg.container.image : trim_tool_cfg.container) ?: resolved_cfg.trim_adapters?.container?.image ?: '',
                trim_tool_args.join(' '),
                adapter_args,
            )
            reads_ch = TRIM_CUTADAPT.out.reads.map { row, fastq_r1, fastq_r2 ->
                row + [fastq_r1: fastq_r1, fastq_r2: fastq_r2]
            }
            operation_statuses = TRIM_CUTADAPT.out.statuses
        } else {
            surecall_heap = trim_tool_cfg.ram ? "-Xmx${trim_tool_cfg.ram}" : ''
            TRIM_SURECALL(
                fastq_samples,
                prealign_threads,
                trim_ram,
                trim_tool_cfg.path,
                surecall_heap,
                trim_tool_args.join(' '),
            )
            reads_ch = TRIM_SURECALL.out.reads.map { row, fastq_r1, fastq_r2 ->
                row + [fastq_r1: fastq_r1, fastq_r2: fastq_r2]
            }
            operation_statuses = TRIM_SURECALL.out.statuses
        }
    }

    if (fastq_qc_enabled) {
        FASTQ_QC(reads_ch, prealign_threads, prealign_ram, fastqc_path, fastqc_args)
        operation_statuses = operation_statuses.mix(FASTQ_QC.out.statuses)
        reports_ch = FASTQ_QC.out.reports
    }

    status_files = operation_statuses.map { sample_id, role, sample_name, log_file, status_file -> status_file }.collect()
    enabled_tool_names = []
    if (trim_enabled) enabled_tool_names << trim_tool_name
    if (fastq_qc_enabled) enabled_tool_names << fastq_qc_tool_name
    PREALIGNMENT_STEP_LOG(enabled_tool_names.join(','), status_files)
    PREALIGNMENT_ASSERT_SUCCESS(status_files, PREALIGNMENT_STEP_LOG.out.log)

    emit:
    reads = reads_ch
    reports = reports_ch
    statuses = operation_statuses
    step_log = PREALIGNMENT_STEP_LOG.out.log
    ready = PREALIGNMENT_ASSERT_SUCCESS.out.ready
}
