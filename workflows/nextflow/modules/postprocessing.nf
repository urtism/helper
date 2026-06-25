nextflow.enable.dsl = 2


process POSTPROCESS_VARIANTS {
    tag "${sample_name}"
    cpus { post_threads }
    memory { post_ram }
    publishDir "${params.outdir}/POSTPROCESSING", mode: 'copy', pattern: '*.postprocessed.vcf'
    publishDir "${params.outdir}/POSTPROCESSING", mode: 'copy', pattern: '*.variants.tsv'
    publishDir "${params.outdir}/LOGS/POSTPROCESSING/samples", mode: 'copy', pattern: '*.postprocessing.log'
    publishDir "${params.outdir}/LOGS/POSTPROCESSING/samples", mode: 'copy', pattern: '*.postprocessing.status.tsv'

    input:
    tuple val(sample_id), val(role), val(sample_name), path(input_vcf)
    val post_threads
    val post_ram
    val operations
    val bcftools_path
    val gatk_path
    val norm_args
    val filter_args
    val reference_fasta

    output:
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.postprocessed.vcf"), path("${sample_name}.variants.tsv"), emit: variants
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.postprocessing.log"), path("${sample_name}.postprocessing.status.tsv"), emit: statuses

    script:
    def do_norm = operations.contains('vcf_norm')
    def do_filter = operations.contains('vcf_filter')
    def do_tsv = operations.contains('vcf_to_tsv')
    """
    set +e
    {
        echo "step=postprocessing"
        echo "sample_id=${sample_id}"
        echo "role=${role}"
        echo "sample_name=${sample_name}"
        echo "threads=${task.cpus}"
        echo "operations=${operations.join(',')}"
        echo "input_vcf=${input_vcf}"
        echo "reference=${reference_fasta}"
        echo "started=\$(date -Is)"
        echo
    } > ${sample_name}.postprocessing.log
    started_at=\$(date -Is)
    current_vcf="${input_vcf}"
    exit_code=0

    if [ "${do_norm}" = "true" ]; then
        echo "===== vcf_norm =====" >> ${sample_name}.postprocessing.log
        echo "command=${bcftools_path} norm -f ${reference_fasta} -o ${sample_name}.norm.vcf \${current_vcf} ${norm_args}" >> ${sample_name}.postprocessing.log
        ${bcftools_path} norm -f "${reference_fasta}" -o "${sample_name}.norm.vcf" "\${current_vcf}" ${norm_args} >> ${sample_name}.postprocessing.log 2>&1
        exit_code=\$?
        if [ "\${exit_code}" -eq 0 ]; then current_vcf="${sample_name}.norm.vcf"; fi
    fi

    if [ "\${exit_code}" -eq 0 ] && [ "${do_filter}" = "true" ]; then
        echo "===== vcf_filter =====" >> ${sample_name}.postprocessing.log
        if [ -n "${gatk_path}" ]; then
            echo "command=${gatk_path} VariantFiltration -R ${reference_fasta} -V \${current_vcf} -O ${sample_name}.filtered.vcf ${filter_args}" >> ${sample_name}.postprocessing.log
            ${gatk_path} VariantFiltration -R "${reference_fasta}" -V "\${current_vcf}" -O "${sample_name}.filtered.vcf" ${filter_args} >> ${sample_name}.postprocessing.log 2>&1
            exit_code=\$?
            if [ "\${exit_code}" -eq 0 ]; then current_vcf="${sample_name}.filtered.vcf"; fi
        else
            echo "No filter tool configured; copying current VCF" >> ${sample_name}.postprocessing.log
            cp "\${current_vcf}" "${sample_name}.filtered.vcf" >> ${sample_name}.postprocessing.log 2>&1
            exit_code=\$?
            if [ "\${exit_code}" -eq 0 ]; then current_vcf="${sample_name}.filtered.vcf"; fi
        fi
    fi

    if [ "\${exit_code}" -eq 0 ]; then
        cp "\${current_vcf}" "${sample_name}.postprocessed.vcf" >> ${sample_name}.postprocessing.log 2>&1
        exit_code=\$?
    fi

    if [ "\${exit_code}" -eq 0 ] && [ "${do_tsv}" = "true" ]; then
        echo "===== vcf_to_tsv =====" >> ${sample_name}.postprocessing.log
        awk 'BEGIN { OFS="\\t"; print "chrom","pos","id","ref","alt","qual","filter","info" } /^#/ { next } { print \$1,\$2,\$3,\$4,\$5,\$6,\$7,\$8 }' "${sample_name}.postprocessed.vcf" > "${sample_name}.variants.tsv"
        exit_code=\$?
    elif [ "\${exit_code}" -eq 0 ]; then
        printf "chrom\\tpos\\tid\\tref\\talt\\tqual\\tfilter\\tinfo\\n" > "${sample_name}.variants.tsv"
    fi

    completed_at=\$(date -Is)
    if [ "\${exit_code}" -eq 0 ]; then
        status=completed
        echo "completed=\${completed_at}" >> ${sample_name}.postprocessing.log
    else
        status=failed
        rm -f ${sample_name}.postprocessed.vcf ${sample_name}.variants.tsv
        echo "failed=\${completed_at}" >> ${sample_name}.postprocessing.log
        echo "exit_code=\${exit_code}" >> ${sample_name}.postprocessing.log
    fi
    printf "step\\ttool\\tsample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n" > ${sample_name}.postprocessing.status.tsv
    printf "postprocessing\\tVCF_POSTPROCESSING\\t${sample_id}\\t${role}\\t${sample_name}\\t\${status}\\t\${exit_code}\\t\${started_at}\\t\${completed_at}\\n" >> ${sample_name}.postprocessing.status.tsv
    exit 0
    """
}


process POSTPROCESSING_STEP_LOG {
    tag 'postprocessing'
    publishDir "${params.outdir}/LOGS/POSTPROCESSING", mode: 'copy'

    input:
    path sample_statuses

    output:
    path "postprocessing.step.log", emit: log

    script:
    """
    {
        echo "step=postprocessing"
        echo "generated=\$(date -Is)"
        echo "sample_count=\$(ls -1 *.postprocessing.status.tsv 2>/dev/null | wc -l)"
        echo "completed_count=\$(awk -F '\\t' 'FNR > 1 && \$6 == "completed" { count++ } END { print count + 0 }' *.postprocessing.status.tsv 2>/dev/null)"
        echo "failed_count=\$(awk -F '\\t' 'FNR > 1 && \$6 == "failed" { count++ } END { print count + 0 }' *.postprocessing.status.tsv 2>/dev/null)"
        echo
        printf "sample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n"
        for sample_status in *.postprocessing.status.tsv; do
            [ -e "\${sample_status}" ] || continue
            awk -F '\\t' 'FNR > 1 { printf "%s\\t%s\\t%s\\t%s\\t%s\\t%s\\t%s\\n", \$3, \$4, \$5, \$6, \$7, \$8, \$9 }' "\${sample_status}"
        done
    } > postprocessing.step.log
    """
}


process POSTPROCESSING_ASSERT_SUCCESS {
    tag 'postprocessing-check'

    input:
    path sample_statuses
    path step_log

    output:
    path "postprocessing.success", emit: ready

    script:
    """
    failed_count=\$(awk -F '\\t' 'FNR > 1 && \$6 == "failed" { count++ } END { print count + 0 }' *.postprocessing.status.tsv 2>/dev/null)
    if [ "\${failed_count}" -gt 0 ]; then
        echo "Postprocessing failed for \${failed_count} sample(s). See ${step_log} and sample status files." >&2
        exit 1
    fi
    touch postprocessing.success
    """
}


workflow POSTPROCESSING {
    take:
    variants_ch
    pipeline_config
    tools_config
    reference_fasta
    infra_ready

    main:
    post_cfg = pipeline_config.postprocessing ?: [:]
    resolved_cfg = post_cfg.resolved ?: [:]
    operations = post_cfg.workflow ?: ['vcf_to_tsv']
    post_threads = (post_cfg.threads ?: 1) as int
    post_ram = post_cfg.ram ?: '1 GB'
    norm_cfg = post_cfg.vcf_norm ?: [:]
    filter_cfg = post_cfg.vcf_filter ?: [:]
    norm_tool_name = norm_cfg.tool ?: 'BCFTOOLS'
    filter_tool_name = filter_cfg.tool ?: ''
    bcftools_path = resolved_cfg.vcf_norm?.path ?: tools_config[norm_tool_name]?.path ?: 'bcftools'
    gatk_path = filter_tool_name ? (resolved_cfg.vcf_filter?.path ?: tools_config[filter_tool_name]?.path ?: filter_tool_name) : ''
    norm_args = (norm_cfg[norm_tool_name]?.args ?: norm_cfg.args ?: []).join(' ')
    filter_args = filter_tool_name ? (filter_cfg[filter_tool_name]?.args ?: filter_cfg.args ?: []).join(' ') : ''

    ready_variants = variants_ch
        .combine(infra_ready)
        .map { sample_id, role, sample_name, vcf, ready -> tuple(sample_id, role, sample_name, vcf) }

    POSTPROCESS_VARIANTS(ready_variants, post_threads, post_ram, operations, bcftools_path, gatk_path, norm_args, filter_args, reference_fasta)
    status_files = POSTPROCESS_VARIANTS.out.statuses.map { sample_id, role, sample_name, log_file, status_file -> status_file }.collect()
    POSTPROCESSING_STEP_LOG(status_files)
    POSTPROCESSING_ASSERT_SUCCESS(status_files, POSTPROCESSING_STEP_LOG.out.log)

    emit:
    variants = POSTPROCESS_VARIANTS.out.variants
    statuses = POSTPROCESS_VARIANTS.out.statuses
    step_log = POSTPROCESSING_STEP_LOG.out.log
    ready = POSTPROCESSING_ASSERT_SUCCESS.out.ready
}
