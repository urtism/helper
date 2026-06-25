nextflow.enable.dsl = 2


process GATK_HAPLOTYPECALLER {
    tag "${sample_name}"
    cpus { variant_threads }
    memory { variant_ram }
    publishDir "${params.outdir}/VARIANTCALLING", mode: 'copy', pattern: '*.g.vcf*'
    publishDir "${params.outdir}/VARIANTCALLING/realigned_bam", mode: 'copy', pattern: '*.realign.bam*', enabled: params.keep_intermediates == true || params.keep_intermediates?.toString()?.toLowerCase() in ['true', '1', 'yes']
    publishDir "${params.outdir}/LOGS/VARIANTCALLING/samples", mode: 'copy', pattern: '*.variantcalling.log'
    publishDir "${params.outdir}/LOGS/VARIANTCALLING/samples", mode: 'copy', pattern: '*.variantcalling.status.tsv'

    input:
    tuple val(sample_id), val(role), val(sample_name), path(input_bam)
    val variant_threads
    val variant_ram
    val gatk_path
    val gatk_args
    val reference_fasta

    output:
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.GATK.g.vcf"), optional: true, emit: vcfs
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.GATK.realign.bam"), optional: true, emit: realigned_bams
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.variantcalling.log"), path("${sample_name}.variantcalling.status.tsv"), emit: statuses

    script:
    """
    set +e
    {
        echo "step=variantcalling"
        echo "tool=GATK HaplotypeCaller"
        echo "sample_id=${sample_id}"
        echo "role=${role}"
        echo "sample_name=${sample_name}"
        echo "threads=${task.cpus}"
        echo "reference=${reference_fasta}"
        echo "input_bam=${input_bam}"
        echo "started=\$(date -Is)"
        echo "command=${gatk_path} --java-options -Xmx${task.memory.toGiga()}g HaplotypeCaller -R ${reference_fasta} -I ${input_bam} -O ${sample_name}.GATK.g.vcf -bamout ${sample_name}.GATK.realign.bam -ERC GVCF --native-pair-hmm-threads ${task.cpus} ${gatk_args}"
        echo
    } > ${sample_name}.variantcalling.log
    started_at=\$(date -Is)
    ${gatk_path} --java-options "-Xmx${task.memory.toGiga()}g" HaplotypeCaller \
        -R "${reference_fasta}" \
        -I "${input_bam}" \
        -O "${sample_name}.GATK.g.vcf" \
        -bamout "${sample_name}.GATK.realign.bam" \
        -ERC GVCF \
        --native-pair-hmm-threads ${task.cpus} \
        ${gatk_args} >> ${sample_name}.variantcalling.log 2>&1
    exit_code=\$?
    completed_at=\$(date -Is)
    if [ "\${exit_code}" -eq 0 ]; then
        status=completed
        echo "completed=\${completed_at}" >> ${sample_name}.variantcalling.log
    else
        status=failed
        rm -f ${sample_name}.GATK.g.vcf ${sample_name}.GATK.g.vcf.idx ${sample_name}.GATK.realign.bam
        echo "failed=\${completed_at}" >> ${sample_name}.variantcalling.log
        echo "exit_code=\${exit_code}" >> ${sample_name}.variantcalling.log
    fi
    if [ "${params.keep_intermediates}" != "true" ] && [ "${params.keep_intermediates}" != "1" ] && [ "${params.keep_intermediates}" != "yes" ]; then
        rm -f ${sample_name}.GATK.realign.bam
    fi
    printf "step\\ttool\\tsample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n" > ${sample_name}.variantcalling.status.tsv
    printf "variantcalling\\tGATK_HAPLOTYPECALLER\\t${sample_id}\\t${role}\\t${sample_name}\\t\${status}\\t\${exit_code}\\t\${started_at}\\t\${completed_at}\\n" >> ${sample_name}.variantcalling.status.tsv
    exit 0
    """
}


process VARIANTCALLING_STEP_LOG {
    tag 'variantcalling'
    publishDir "${params.outdir}/LOGS/VARIANTCALLING", mode: 'copy'

    input:
    val tool_name
    path sample_statuses

    output:
    path "variantcalling.step.log", emit: log

    script:
    """
    {
        echo "step=variantcalling"
        echo "tool=${tool_name}"
        echo "generated=\$(date -Is)"
        echo "sample_count=\$(ls -1 *.variantcalling.status.tsv 2>/dev/null | wc -l)"
        echo "completed_count=\$(awk -F '\\t' 'FNR > 1 && \$6 == "completed" { count++ } END { print count + 0 }' *.variantcalling.status.tsv 2>/dev/null)"
        echo "failed_count=\$(awk -F '\\t' 'FNR > 1 && \$6 == "failed" { count++ } END { print count + 0 }' *.variantcalling.status.tsv 2>/dev/null)"
        echo
        printf "sample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n"
        for sample_status in *.variantcalling.status.tsv; do
            [ -e "\${sample_status}" ] || continue
            awk -F '\\t' 'FNR > 1 { printf "%s\\t%s\\t%s\\t%s\\t%s\\t%s\\t%s\\n", \$3, \$4, \$5, \$6, \$7, \$8, \$9 }' "\${sample_status}"
        done
    } > variantcalling.step.log
    """
}


process VARIANTCALLING_ASSERT_SUCCESS {
    tag 'variantcalling-check'

    input:
    path sample_statuses
    path step_log

    output:
    path "variantcalling.success", emit: ready

    script:
    """
    failed_count=\$(awk -F '\\t' 'FNR > 1 && \$6 == "failed" { count++ } END { print count + 0 }' *.variantcalling.status.tsv 2>/dev/null)
    if [ "\${failed_count}" -gt 0 ]; then
        echo "Variant calling failed for \${failed_count} sample(s). See ${step_log} and sample status files." >&2
        exit 1
    fi
    touch variantcalling.success
    """
}


workflow VARIANTCALLING {
    take:
    bam_ch
    pipeline_config
    tools_config
    reference_fasta
    infra_ready

    main:
    variant_cfg = pipeline_config.variantcalling ?: [:]
    resolved_cfg = variant_cfg.resolved ?: [:]
    variant_threads = (variant_cfg.threads ?: 1) as int
    variant_ram = variant_cfg.ram ?: '1 GB'
    tool_name = (variant_cfg.tools ?: []).find { tool -> tool.toString().toUpperCase().startsWith('GATK') } ?: 'GATK v.4.1'
    if (!tool_name.toString().toUpperCase().startsWith('GATK')) {
        error "The first Nextflow variantcalling slice currently supports only GATK HaplotypeCaller"
    }
    tool_cfg = tools_config[tool_name] ?: [:]
    gatk_path = resolved_cfg.caller?.path ?: tool_cfg.path ?: 'gatk'
    gatk_args = resolved_cfg.caller?.resolved_args ?: (variant_cfg[tool_name]?.args ?: []).join(' ')

    ready_bams = bam_ch
        .combine(infra_ready)
        .map { sample_id, role, sample_name, bam, bai, ready -> tuple(sample_id, role, sample_name, bam) }

    GATK_HAPLOTYPECALLER(ready_bams, variant_threads, variant_ram, gatk_path, gatk_args, reference_fasta)
    status_files = GATK_HAPLOTYPECALLER.out.statuses.map { sample_id, role, sample_name, log_file, status_file -> status_file }.collect()
    VARIANTCALLING_STEP_LOG(tool_name, status_files)
    VARIANTCALLING_ASSERT_SUCCESS(status_files, VARIANTCALLING_STEP_LOG.out.log)

    emit:
    vcfs = GATK_HAPLOTYPECALLER.out.vcfs
    statuses = GATK_HAPLOTYPECALLER.out.statuses
    step_log = VARIANTCALLING_STEP_LOG.out.log
    ready = VARIANTCALLING_ASSERT_SUCCESS.out.ready
}
