nextflow.enable.dsl = 2


process POSTPROCESS_CALLER_VCF {
    tag "${sample_name}:${caller}"
    cpus { post_threads }
    memory { post_ram }
    publishDir "${params.outdir}/POSTPROCESSING/callers", mode: 'copy', pattern: '*.caller.vcf'
    publishDir "${params.outdir}/LOGS/POSTPROCESSING/samples", mode: 'copy', pattern: '*.postprocessing.log'
    publishDir "${params.outdir}/LOGS/POSTPROCESSING/samples", mode: 'copy', pattern: '*.postprocessing.status.tsv'

    input:
    tuple val(sample_id), val(role), val(sample_name), val(caller), path(input_vcf)
    val post_threads
    val post_ram
    val operations
    val bcftools_path
    val gatk_path
    val gatk_java_home
    val gatk_java_cmd
    val norm_args
    val filter_args
    val reference_fasta
    val restart_token

    output:
    tuple val(sample_id), val(role), val(sample_name), val(caller), path("${sample_name}.${caller_tag}.caller.vcf"), optional: true, emit: variants
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.${caller_tag}.postprocessing.log"), path("${sample_name}.${caller_tag}.postprocessing.status.tsv"), emit: statuses

    script:
    caller_tag = caller.toString().replaceAll(/[^A-Za-z0-9._-]/, '_')
    def do_norm = operations.contains('vcf_norm') || operations.contains('multi_vcf_merge')
    def do_filter = operations.contains('vcf_filter')
    def do_gatk_filter = do_filter && caller.toString().toUpperCase() == 'GATK'
    """
    set +e
    if [ -n "${gatk_java_cmd}" ]; then
        export PATH="\$(dirname "${gatk_java_cmd}"):\${PATH}"
        export JAVA_HOME="\$(dirname "\$(dirname "${gatk_java_cmd}")")"
    elif [ -n "${gatk_java_home}" ]; then
        export JAVA_HOME="${gatk_java_home}"
        export PATH="${gatk_java_home}/bin:\${PATH}"
    fi
    {
        echo "step=postprocessing"
        echo "phase=caller_preparation"
        echo "caller=${caller}"
        echo "sample_id=${sample_id}"
        echo "role=${role}"
        echo "sample_name=${sample_name}"
        echo "threads=${task.cpus}"
        echo "operations=${operations.join(',')}"
        echo "input_vcf=${input_vcf}"
        echo "reference=${reference_fasta}"
        echo "started=\$(date -Is)"
        echo
    } > ${sample_name}.${caller_tag}.postprocessing.log
    started_at=\$(date -Is)
    current_vcf="${input_vcf}"
    exit_code=0

    if [ "${do_norm}" = "true" ]; then
        echo "===== vcf_norm =====" >> ${sample_name}.${caller_tag}.postprocessing.log
        echo "split_command=${bcftools_path} norm -m -any -f ${reference_fasta} -o ${sample_name}.${caller_tag}.split.vcf \${current_vcf} ${norm_args}" >> ${sample_name}.${caller_tag}.postprocessing.log
        echo "deduplicate_command=${bcftools_path} norm -d exact -o ${sample_name}.${caller_tag}.norm.vcf ${sample_name}.${caller_tag}.split.vcf" >> ${sample_name}.${caller_tag}.postprocessing.log
        ${bcftools_path} norm -m -any -f "${reference_fasta}" -o "${sample_name}.${caller_tag}.split.vcf" "\${current_vcf}" ${norm_args} >> ${sample_name}.${caller_tag}.postprocessing.log 2>&1
        exit_code=\$?
        if [ "\${exit_code}" -eq 0 ]; then
            ${bcftools_path} norm -d exact -o "${sample_name}.${caller_tag}.norm.vcf" "${sample_name}.${caller_tag}.split.vcf" >> ${sample_name}.${caller_tag}.postprocessing.log 2>&1
            exit_code=\$?
        fi
        rm -f "${sample_name}.${caller_tag}.split.vcf"
        if [ "\${exit_code}" -eq 0 ]; then current_vcf="${sample_name}.${caller_tag}.norm.vcf"; fi
    fi

    if [ "\${exit_code}" -eq 0 ] && [ "${do_gatk_filter}" = "true" ]; then
        echo "===== vcf_filter (GATK) =====" >> ${sample_name}.${caller_tag}.postprocessing.log
        if [ -n "${gatk_path}" ]; then
            cat >> ${sample_name}.${caller_tag}.postprocessing.log <<HELPER_FILTER_COMMAND
command=${gatk_path} VariantFiltration -R ${reference_fasta} -V \${current_vcf} -O ${sample_name}.${caller_tag}.filtered.vcf ${filter_args}
HELPER_FILTER_COMMAND
            ${gatk_path} VariantFiltration -R "${reference_fasta}" -V "\${current_vcf}" -O "${sample_name}.${caller_tag}.filtered.vcf" ${filter_args} >> ${sample_name}.${caller_tag}.postprocessing.log 2>&1
            exit_code=\$?
            if [ "\${exit_code}" -eq 0 ]; then current_vcf="${sample_name}.${caller_tag}.filtered.vcf"; fi
        else
            echo "No GATK filter tool configured; retaining the current VCF" >> ${sample_name}.${caller_tag}.postprocessing.log
        fi
    elif [ "\${exit_code}" -eq 0 ] && [ "${do_filter}" = "true" ]; then
        echo "===== vcf_filter (${caller}) =====" >> ${sample_name}.${caller_tag}.postprocessing.log
        echo "Caller-native FILTER values retained; caller-specific and consensus thresholds are evaluated by multi_vcf_merge" >> ${sample_name}.${caller_tag}.postprocessing.log
    fi

    if [ "\${exit_code}" -eq 0 ]; then
        cp "\${current_vcf}" "${sample_name}.${caller_tag}.caller.vcf" >> ${sample_name}.${caller_tag}.postprocessing.log 2>&1
        exit_code=\$?
    fi

    completed_at=\$(date -Is)
    if [ "\${exit_code}" -eq 0 ]; then
        status=completed
        echo "completed=\${completed_at}" >> ${sample_name}.${caller_tag}.postprocessing.log
    else
        status=failed
        rm -f ${sample_name}.${caller_tag}.caller.vcf
        echo "failed=\${completed_at}" >> ${sample_name}.${caller_tag}.postprocessing.log
        echo "exit_code=\${exit_code}" >> ${sample_name}.${caller_tag}.postprocessing.log
    fi
    printf "step\\ttool\\tsample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n" > ${sample_name}.${caller_tag}.postprocessing.status.tsv
    printf "postprocessing\\tVCF_PREPARE_${caller_tag}\\t${sample_id}\\t${role}\\t${sample_name}\\t\${status}\\t\${exit_code}\\t\${started_at}\\t\${completed_at}\\n" >> ${sample_name}.${caller_tag}.postprocessing.status.tsv
    exit 0
    """
}


process FINALIZE_POSTPROCESSING {
    tag "${sample_name}"
    cpus { post_threads }
    memory { post_ram }
    publishDir "${params.outdir}/POSTPROCESSING", mode: 'copy', pattern: '*.postprocessed.vcf'
    publishDir "${params.outdir}/POSTPROCESSING", mode: 'copy', pattern: '*.variants.tsv'
    publishDir "${params.outdir}/LOGS/POSTPROCESSING/samples", mode: 'copy', pattern: '*.postprocessing.log'
    publishDir "${params.outdir}/LOGS/POSTPROCESSING/samples", mode: 'copy', pattern: '*.postprocessing.status.tsv'

    input:
    tuple val(sample_id), val(role), val(sample_name), val(callers), path(caller_vcfs)
    val post_threads
    val post_ram
    val operations
    path merge_script
    val merge_args

    output:
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.postprocessed.vcf"), path("${sample_name}.variants.tsv"), optional: true, emit: variants
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.postprocessing.log"), path("${sample_name}.postprocessing.status.tsv"), emit: statuses

    script:
    def caller_options = []
    callers.eachWithIndex { caller, index ->
        def option = [GATK: '--gatk', FREEBAYES: '--freebayes', DEEPVARIANT: '--deepvariant', VARSCAN: '--varscan'][caller.toString().toUpperCase()]
        if (option) {
            caller_options << "${option} \"${caller_vcfs[index]}\""
        }
    }
    def merge_enabled = operations.contains('multi_vcf_merge') && caller_options.size() > 1
    def preferred_index = callers.findIndexOf { it.toString().toUpperCase() == 'GATK' }
    if (preferred_index < 0) {
        preferred_index = 0
    }
    def primary_vcf = caller_vcfs[preferred_index]
    def final_command = merge_enabled
        ? "python3 \"${merge_script}\" ${caller_options.join(' ')} --sample-name \"${sample_name}\" --out \"${sample_name}.postprocessed.vcf\" ${merge_args}"
        : "cp \"${primary_vcf}\" \"${sample_name}.postprocessed.vcf\""
    def final_tool = merge_enabled ? 'MULTI_VCF_MERGE' : 'VCF_FINALIZE'
    def do_tsv = operations.contains('vcf_to_tsv')
    """
    set +e
    {
        echo "step=postprocessing"
        echo "phase=multi_vcf_merge"
        echo "tool=${final_tool}"
        echo "sample_id=${sample_id}"
        echo "role=${role}"
        echo "sample_name=${sample_name}"
        echo "callers=${callers.join(',')}"
        echo "merge_enabled=${merge_enabled}"
        echo "started=\$(date -Is)"
        echo "command=${final_command}"
        echo
    } > ${sample_name}.postprocessing.log
    started_at=\$(date -Is)
    ${final_command} >> ${sample_name}.postprocessing.log 2>&1
    exit_code=\$?

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
    printf "postprocessing\\t${final_tool}\\t${sample_id}\\t${role}\\t${sample_name}\\t\${status}\\t\${exit_code}\\t\${started_at}\\t\${completed_at}\\n" >> ${sample_name}.postprocessing.status.tsv
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
        echo "process_count=\$(ls -1 *.postprocessing.status.tsv 2>/dev/null | wc -l)"
        echo "completed_count=\$(awk -F '\\t' 'FNR > 1 && \$6 == "completed" { count++ } END { print count + 0 }' *.postprocessing.status.tsv 2>/dev/null)"
        echo "failed_count=\$(awk -F '\\t' 'FNR > 1 && \$6 == "failed" { count++ } END { print count + 0 }' *.postprocessing.status.tsv 2>/dev/null)"
        echo
        printf "sample_id\\trole\\tsample_name\\ttool\\tstatus\\texit_code\\tstarted\\tcompleted\\n"
        for sample_status in *.postprocessing.status.tsv; do
            [ -e "\${sample_status}" ] || continue
            awk -F '\\t' 'FNR > 1 { printf "%s\\t%s\\t%s\\t%s\\t%s\\t%s\\t%s\\t%s\\n", \$3, \$4, \$5, \$2, \$6, \$7, \$8, \$9 }' "\${sample_status}"
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
        echo "Postprocessing failed for \${failed_count} process(es). See ${step_log} and sample status files." >&2
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
    restart_token

    main:
    post_cfg = pipeline_config.postprocessing ?: [:]
    resolved_cfg = post_cfg.resolved ?: [:]
    operations = post_cfg.workflow ?: ['vcf_to_tsv']
    post_threads = (post_cfg.threads ?: 1) as int
    post_ram = post_cfg.ram ?: '1 GB'
    norm_cfg = post_cfg.vcf_norm ?: [:]
    filter_cfg = post_cfg.vcf_filter ?: [:]
    merge_cfg = post_cfg.multi_vcf_merge ?: [:]
    norm_tool_name = norm_cfg.tool ?: 'BCFTOOLS'
    filter_tool_name = filter_cfg.tool ?: ''
    merge_tool_name = merge_cfg.tool ?: 'merge_consensus_vcfs.py'
    filter_tool_cfg = filter_tool_name ? (tools_config[filter_tool_name] ?: [:]) : [:]
    bcftools_path = resolved_cfg.vcf_norm?.path ?: tools_config[norm_tool_name]?.path ?: 'bcftools'
    gatk_path = filter_tool_name ? (resolved_cfg.vcf_filter?.path ?: tools_config[filter_tool_name]?.path ?: filter_tool_name) : ''
    gatk_java_home = filter_tool_name ? (resolved_cfg.vcf_filter?.java_home ?: filter_tool_cfg.java_home ?: filter_tool_cfg.javaHome ?: System.getenv('GATK_JAVA_HOME') ?: '') : ''
    gatk_java_cmd = filter_tool_name ? (resolved_cfg.vcf_filter?.java_path ?: resolved_cfg.vcf_filter?.java_cmd ?: filter_tool_cfg.java_path ?: filter_tool_cfg.java_cmd ?: filter_tool_cfg.java ?: System.getenv('GATK_JAVA_CMD') ?: '') : ''
    norm_args = (norm_cfg[norm_tool_name]?.args ?: norm_cfg.args ?: []).join(' ')
    filter_args = filter_tool_name ? (filter_cfg[filter_tool_name]?.args ?: filter_cfg.args ?: []).join(' ') : ''
    merge_args = (merge_cfg[merge_tool_name]?.args ?: merge_cfg.args ?: []).join(' ')
    merge_script = file("${projectDir}/../../scripts/merge_consensus_vcfs.py", checkIfExists: true)

    ready_variants = variants_ch
        .combine(infra_ready)
        .map { sample_id, role, sample_name, caller, vcf, ready -> tuple(sample_id, role, sample_name, caller, vcf) }

    POSTPROCESS_CALLER_VCF(ready_variants, post_threads, post_ram, operations, bcftools_path, gatk_path, gatk_java_home, gatk_java_cmd, norm_args, filter_args, reference_fasta, restart_token)
    grouped_variants = POSTPROCESS_CALLER_VCF.out.variants
        .map { sample_id, role, sample_name, caller, vcf -> tuple([sample_id, role, sample_name], caller, vcf) }
        .groupTuple()
        .map { sample_key, callers, vcfs -> tuple(sample_key[0], sample_key[1], sample_key[2], callers, vcfs) }
    FINALIZE_POSTPROCESSING(grouped_variants, post_threads, post_ram, operations, merge_script, merge_args)

    output_statuses = POSTPROCESS_CALLER_VCF.out.statuses.mix(FINALIZE_POSTPROCESSING.out.statuses)
    status_files = output_statuses.map { sample_id, role, sample_name, log_file, status_file -> status_file }.collect()
    POSTPROCESSING_STEP_LOG(status_files)
    POSTPROCESSING_ASSERT_SUCCESS(status_files, POSTPROCESSING_STEP_LOG.out.log)

    emit:
    variants = FINALIZE_POSTPROCESSING.out.variants
    statuses = output_statuses
    step_log = POSTPROCESSING_STEP_LOG.out.log
    ready = POSTPROCESSING_ASSERT_SUCCESS.out.ready
}
