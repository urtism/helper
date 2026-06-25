nextflow.enable.dsl = 2


process ANNOTATE_VARIANTS {
    tag "${sample_name}"
    cpus { ann_threads }
    memory { ann_ram }
    publishDir "${params.outdir}/ANNOTATION", mode: 'copy', pattern: '*.annotated.vcf'
    publishDir "${params.outdir}/ANNOTATION", mode: 'copy', pattern: '*.annotated.tsv'
    publishDir "${params.outdir}/LOGS/ANNOTATION/samples", mode: 'copy', pattern: '*.annotation.log'
    publishDir "${params.outdir}/LOGS/ANNOTATION/samples", mode: 'copy', pattern: '*.annotation.status.tsv'

    input:
    tuple val(sample_id), val(role), val(sample_name), path(input_vcf)
    val ann_threads
    val ann_ram
    val operations
    val vep_path
    val vep_args
    val target_bed
    val gene_list
    val transcripts_list

    output:
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.annotated.vcf"), path("${sample_name}.annotated.tsv"), emit: variants
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.annotation.log"), path("${sample_name}.annotation.status.tsv"), emit: statuses

    script:
    def do_vep = operations.contains('vep_annotation') && vep_path
    def do_tsv = operations.contains('ann_vcf_to_tsv')
    """
    set +e
    {
        echo "step=annotation"
        echo "sample_id=${sample_id}"
        echo "role=${role}"
        echo "sample_name=${sample_name}"
        echo "threads=${task.cpus}"
        echo "operations=${operations.join(',')}"
        echo "input_vcf=${input_vcf}"
        echo "target_bed=${target_bed}"
        echo "gene_list=${gene_list}"
        echo "transcripts_list=${transcripts_list}"
        echo "started=\$(date -Is)"
        echo
    } > ${sample_name}.annotation.log
    started_at=\$(date -Is)
    current_vcf="${input_vcf}"
    exit_code=0

    if [ "${do_vep}" = "true" ]; then
        echo "===== vep_annotation =====" >> ${sample_name}.annotation.log
        echo "command=${vep_path} --input_file \${current_vcf} --output_file ${sample_name}.annotated.vcf --vcf --force_overwrite --fork ${task.cpus} ${vep_args}" >> ${sample_name}.annotation.log
        ${vep_path} --input_file "\${current_vcf}" --output_file "${sample_name}.annotated.vcf" --vcf --force_overwrite --fork ${task.cpus} ${vep_args} >> ${sample_name}.annotation.log 2>&1
        exit_code=\$?
        if [ "\${exit_code}" -eq 0 ]; then current_vcf="${sample_name}.annotated.vcf"; fi
    else
        echo "No VEP annotation requested; copying input VCF" >> ${sample_name}.annotation.log
        cp "\${current_vcf}" "${sample_name}.annotated.vcf" >> ${sample_name}.annotation.log 2>&1
        exit_code=\$?
        if [ "\${exit_code}" -eq 0 ]; then current_vcf="${sample_name}.annotated.vcf"; fi
    fi

    if [ "\${exit_code}" -eq 0 ] && [ "${do_tsv}" = "true" ]; then
        echo "===== ann_vcf_to_tsv =====" >> ${sample_name}.annotation.log
        awk 'BEGIN { OFS="\\t"; print "chrom","pos","id","ref","alt","qual","filter","info" } /^#/ { next } { print \$1,\$2,\$3,\$4,\$5,\$6,\$7,\$8 }' "${sample_name}.annotated.vcf" > "${sample_name}.annotated.tsv"
        exit_code=\$?
    elif [ "\${exit_code}" -eq 0 ]; then
        printf "chrom\\tpos\\tid\\tref\\talt\\tqual\\tfilter\\tinfo\\n" > "${sample_name}.annotated.tsv"
    fi

    completed_at=\$(date -Is)
    if [ "\${exit_code}" -eq 0 ]; then
        status=completed
        echo "completed=\${completed_at}" >> ${sample_name}.annotation.log
    else
        status=failed
        rm -f ${sample_name}.annotated.vcf ${sample_name}.annotated.tsv
        echo "failed=\${completed_at}" >> ${sample_name}.annotation.log
        echo "exit_code=\${exit_code}" >> ${sample_name}.annotation.log
    fi
    printf "step\\ttool\\tsample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n" > ${sample_name}.annotation.status.tsv
    printf "annotation\\tVARIANT_ANNOTATION\\t${sample_id}\\t${role}\\t${sample_name}\\t\${status}\\t\${exit_code}\\t\${started_at}\\t\${completed_at}\\n" >> ${sample_name}.annotation.status.tsv
    exit 0
    """
}


process ANNOTATION_STEP_LOG {
    tag 'annotation'
    publishDir "${params.outdir}/LOGS/ANNOTATION", mode: 'copy'

    input:
    path sample_statuses

    output:
    path "annotation.step.log", emit: log

    script:
    """
    {
        echo "step=annotation"
        echo "generated=\$(date -Is)"
        echo "sample_count=\$(ls -1 *.annotation.status.tsv 2>/dev/null | wc -l)"
        echo "completed_count=\$(awk -F '\\t' 'FNR > 1 && \$6 == "completed" { count++ } END { print count + 0 }' *.annotation.status.tsv 2>/dev/null)"
        echo "failed_count=\$(awk -F '\\t' 'FNR > 1 && \$6 == "failed" { count++ } END { print count + 0 }' *.annotation.status.tsv 2>/dev/null)"
        echo
        printf "sample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n"
        for sample_status in *.annotation.status.tsv; do
            [ -e "\${sample_status}" ] || continue
            awk -F '\\t' 'FNR > 1 { printf "%s\\t%s\\t%s\\t%s\\t%s\\t%s\\t%s\\n", \$3, \$4, \$5, \$6, \$7, \$8, \$9 }' "\${sample_status}"
        done
    } > annotation.step.log
    """
}


process ANNOTATION_ASSERT_SUCCESS {
    tag 'annotation-check'

    input:
    path sample_statuses
    path step_log

    output:
    path "annotation.success", emit: ready

    script:
    """
    failed_count=\$(awk -F '\\t' 'FNR > 1 && \$6 == "failed" { count++ } END { print count + 0 }' *.annotation.status.tsv 2>/dev/null)
    if [ "\${failed_count}" -gt 0 ]; then
        echo "Annotation failed for \${failed_count} sample(s). See ${step_log} and sample status files." >&2
        exit 1
    fi
    touch annotation.success
    """
}


workflow ANNOTATION {
    take:
    variants_ch
    pipeline_config
    tools_config
    run_config
    infra_ready

    main:
    ann_cfg = pipeline_config.annotation ?: [:]
    resolved_cfg = ann_cfg.resolved ?: [:]
    operations = ann_cfg.workflow ?: ['vep_annotation', 'ann_vcf_to_tsv']
    ann_threads = (ann_cfg.threads ?: 1) as int
    ann_ram = ann_cfg.ram ?: '2 GB'
    vep_cfg = ann_cfg.vep_annotation ?: [:]
    vep_tool_name = vep_cfg.tool ?: 'VEP v.95'
    vep_path = resolved_cfg.vep_annotation?.path ?: tools_config[vep_tool_name]?.path ?: ''
    vep_tool_cfg = vep_cfg[vep_tool_name] ?: [:]
    vep_args = vep_tool_cfg.resolved_args ?: ((vep_tool_cfg.args instanceof List ? vep_tool_cfg.args : vep_cfg.args ?: []).join(' '))
    panel_design = run_config.panel_design ?: [:]
    panel_assets = resolved_cfg.panel_assets ?: panel_design.assets ?: [:]
    target_bed = panel_assets.target_bed ?: ''
    gene_list = panel_assets.gene_list ?: ''
    transcripts_list = panel_assets.transcripts_list ?: ''

    ready_variants = variants_ch
        .combine(infra_ready)
        .map { sample_id, role, sample_name, vcf, ready -> tuple(sample_id, role, sample_name, vcf) }

    ANNOTATE_VARIANTS(ready_variants, ann_threads, ann_ram, operations, vep_path, vep_args, target_bed, gene_list, transcripts_list)
    status_files = ANNOTATE_VARIANTS.out.statuses.map { sample_id, role, sample_name, log_file, status_file -> status_file }.collect()
    ANNOTATION_STEP_LOG(status_files)
    ANNOTATION_ASSERT_SUCCESS(status_files, ANNOTATION_STEP_LOG.out.log)

    emit:
    variants = ANNOTATE_VARIANTS.out.variants
    statuses = ANNOTATE_VARIANTS.out.statuses
    step_log = ANNOTATION_STEP_LOG.out.log
    ready = ANNOTATION_ASSERT_SUCCESS.out.ready
}
