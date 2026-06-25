nextflow.enable.dsl = 2


process FASTQ_QC {
    tag "${row.sample_name}"
    cpus { prealign_threads }
    memory { prealign_ram }
    publishDir "${params.outdir}/PREALIGNMENT/fastqc", mode: 'copy', pattern: 'fastqc_out/*'
    publishDir "${params.outdir}/LOGS/PREALIGNMENT/samples", mode: 'copy', pattern: '*.prealignment.log'
    publishDir "${params.outdir}/LOGS/PREALIGNMENT/samples", mode: 'copy', pattern: '*.prealignment.status.tsv'

    input:
    val row
    val prealign_threads
    val prealign_ram
    val fastqc_path
    val fastqc_args

    output:
    tuple val(row.sample_id), val(row.role), val(row.sample_name), path("fastqc_out/*"), optional: true, emit: reports
    tuple val(row.sample_id), val(row.role), val(row.sample_name), path("${row.sample_name}.prealignment.log"), path("${row.sample_name}.prealignment.status.tsv"), emit: statuses

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
    } > ${row.sample_name}.prealignment.log
    started_at=\$(date -Is)
    \${fastqc_cmd} -t ${task.cpus} -o fastqc_out ${fastqc_args} ${row.fastq_r1} ${fastq2} >> ${row.sample_name}.prealignment.log 2>&1
    exit_code=\$?
    completed_at=\$(date -Is)
    if [ "\${exit_code}" -eq 0 ]; then
        status=completed
        echo "completed=\${completed_at}" >> ${row.sample_name}.prealignment.log
    else
        status=failed
        echo "failed=\${completed_at}" >> ${row.sample_name}.prealignment.log
        echo "exit_code=\${exit_code}" >> ${row.sample_name}.prealignment.log
    fi
    printf "step\\ttool\\tsample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n" > ${row.sample_name}.prealignment.status.tsv
    printf "prealignment\\tFASTQC\\t${row.sample_id}\\t${row.role}\\t${row.sample_name}\\t\${status}\\t\${exit_code}\\t\${started_at}\\t\${completed_at}\\n" >> ${row.sample_name}.prealignment.status.tsv
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
    fastq_qc_cfg = prealignment_cfg.fastq_QC ?: [:]
    tool_name = fastq_qc_cfg.tool ?: 'FASTQC v.0.11.8'
    tool_cfg = tools_config[tool_name] ?: [:]
    prealign_threads = (prealignment_cfg.threads ?: 1) as int
    prealign_ram = prealignment_cfg.ram ?: '1 GB'
    fastqc_path = tool_cfg.path ?: 'fastqc'
    fastqc_args = (fastq_qc_cfg[tool_name]?.args ?: fastq_qc_cfg.args ?: []).join(' ')

    fastq_samples = samples_ch
        .filter { row -> row.fastq_r1 && row.fastq_r2 }
        .combine(infra_ready)
        .map { row, ready -> row }

    FASTQ_QC(fastq_samples, prealign_threads, prealign_ram, fastqc_path, fastqc_args)
    status_files = FASTQ_QC.out.statuses.map { sample_id, role, sample_name, log_file, status_file -> status_file }.collect()
    PREALIGNMENT_STEP_LOG(tool_name, status_files)
    PREALIGNMENT_ASSERT_SUCCESS(status_files, PREALIGNMENT_STEP_LOG.out.log)

    emit:
    reports = FASTQ_QC.out.reports
    statuses = FASTQ_QC.out.statuses
    step_log = PREALIGNMENT_STEP_LOG.out.log
    ready = PREALIGNMENT_ASSERT_SUCCESS.out.ready
}
