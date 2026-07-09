nextflow.enable.dsl = 2


process GATK_HAPLOTYPECALLER {
    tag "${sample_name}"
    cpus { variant_threads }
    memory { variant_ram }
    publishDir "${params.outdir}/VARIANTCALLING", mode: 'copy', pattern: '*.vcf*'
    publishDir "${params.outdir}/VARIANTCALLING/realigned_bam", mode: 'copy', pattern: '*.realign.bam*', enabled: params.keep_intermediates == true || params.keep_intermediates?.toString()?.toLowerCase() in ['true', '1', 'yes']
    publishDir "${params.outdir}/LOGS/VARIANTCALLING/samples", mode: 'copy', pattern: '*.variantcalling.log'
    publishDir "${params.outdir}/LOGS/VARIANTCALLING/samples", mode: 'copy', pattern: '*.variantcalling.status.tsv'

    input:
    tuple val(sample_id), val(role), val(sample_name), path(input_bam)
    val variant_threads
    val variant_ram
    val gatk_path
    val gatk_args
    val gatk_java_home
    val gatk_java_cmd
    val reference_fasta
    val calling_mode

    output:
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.GATK.vcf"), optional: true, emit: vcfs
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.GATK.g.vcf"), optional: true, emit: gvcfs
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.GATK.realign.bam"), optional: true, emit: realigned_bams
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.variantcalling.log"), path("${sample_name}.variantcalling.status.tsv"), emit: statuses

    script:
    def output_vcf = calling_mode == 'single-sample' ? "${sample_name}.GATK.vcf" : "${sample_name}.GATK.g.vcf"
    def gvcf_arg = calling_mode == 'single-sample' ? "" : "-ERC GVCF"
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
        echo "step=variantcalling"
        echo "tool=GATK HaplotypeCaller"
        echo "sample_id=${sample_id}"
        echo "role=${role}"
        echo "sample_name=${sample_name}"
        echo "calling_mode=${calling_mode}"
        echo "threads=${task.cpus}"
        echo "reference=${reference_fasta}"
        echo "input_bam=${input_bam}"
        echo "java_home=\${JAVA_HOME:-}"
        echo "java_version=\$(java -version 2>&1 | head -n 1)"
        echo "started=\$(date -Is)"
        echo "command=${gatk_path} --java-options -Xmx${task.memory.toGiga()}g HaplotypeCaller -R ${reference_fasta} -I ${input_bam} -O ${output_vcf} -bamout ${sample_name}.GATK.realign.bam ${gvcf_arg} --native-pair-hmm-threads ${task.cpus} ${gatk_args}"
        echo
    } > ${sample_name}.variantcalling.log
    started_at=\$(date -Is)
    ${gatk_path} --java-options "-Xmx${task.memory.toGiga()}g" HaplotypeCaller \
        -R "${reference_fasta}" \
        -I "${input_bam}" \
        -O "${output_vcf}" \
        -bamout "${sample_name}.GATK.realign.bam" \
        ${gvcf_arg} \
        --native-pair-hmm-threads ${task.cpus} \
        ${gatk_args} >> ${sample_name}.variantcalling.log 2>&1
    exit_code=\$?
    completed_at=\$(date -Is)
    if [ "\${exit_code}" -eq 0 ]; then
        status=completed
        echo "completed=\${completed_at}" >> ${sample_name}.variantcalling.log
    else
        status=failed
        rm -f ${sample_name}.GATK.vcf ${sample_name}.GATK.vcf.idx ${sample_name}.GATK.g.vcf ${sample_name}.GATK.g.vcf.idx ${sample_name}.GATK.realign.bam
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


process GATK_JOINT_GENOTYPING {
    tag "${group_name}"
    cpus { variant_threads }
    memory { variant_ram }
    publishDir "${params.outdir}/VARIANTCALLING", mode: 'copy', pattern: '*.GATK.vcf*'
    publishDir "${params.outdir}/LOGS/VARIANTCALLING/samples", mode: 'copy', pattern: '*.variantcalling.log'
    publishDir "${params.outdir}/LOGS/VARIANTCALLING/samples", mode: 'copy', pattern: '*.variantcalling.status.tsv'

    input:
    tuple val(sample_id), val(role), val(group_name), path(gvcfs)
    val variant_threads
    val variant_ram
    val gatk_path
    val joint_args
    val gatk_java_home
    val gatk_java_cmd
    val reference_fasta
    val calling_mode

    output:
    tuple val(sample_id), val(role), val(group_name), path("${group_name}.GATK.vcf"), optional: true, emit: vcfs
    tuple val(sample_id), val(role), val(group_name), path("${group_name}.variantcalling.log"), path("${group_name}.variantcalling.status.tsv"), emit: statuses

    script:
    def variant_inputs = gvcfs.collect { "-V ${it}" }.join(' ')
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
        echo "step=variantcalling"
        echo "tool=GATK Joint Genotyping"
        echo "calling_mode=${calling_mode}"
        echo "sample_id=${sample_id}"
        echo "role=${role}"
        echo "sample_name=${group_name}"
        echo "threads=${task.cpus}"
        echo "reference=${reference_fasta}"
        echo "input_gvcfs=${gvcfs.join(',')}"
        echo "java_home=\${JAVA_HOME:-}"
        echo "java_version=\$(java -version 2>&1 | head -n 1)"
        echo "started=\$(date -Is)"
        echo "combine_command=${gatk_path} --java-options -Xmx${task.memory.toGiga()}g CombineGVCFs -R ${reference_fasta} ${variant_inputs} -O ${group_name}.combined.g.vcf"
        echo "genotype_command=${gatk_path} --java-options -Xmx${task.memory.toGiga()}g GenotypeGVCFs -R ${reference_fasta} -V ${group_name}.combined.g.vcf -O ${group_name}.GATK.vcf ${joint_args}"
        echo
    } > ${group_name}.variantcalling.log
    started_at=\$(date -Is)
    ${gatk_path} --java-options "-Xmx${task.memory.toGiga()}g" CombineGVCFs \
        -R "${reference_fasta}" \
        ${variant_inputs} \
        -O "${group_name}.combined.g.vcf" >> ${group_name}.variantcalling.log 2>&1
    exit_code=\$?
    if [ "\${exit_code}" -eq 0 ]; then
        ${gatk_path} --java-options "-Xmx${task.memory.toGiga()}g" GenotypeGVCFs \
            -R "${reference_fasta}" \
            -V "${group_name}.combined.g.vcf" \
            -O "${group_name}.GATK.vcf" \
            ${joint_args} >> ${group_name}.variantcalling.log 2>&1
        exit_code=\$?
    fi
    completed_at=\$(date -Is)
    if [ "\${exit_code}" -eq 0 ]; then
        status=completed
        echo "completed=\${completed_at}" >> ${group_name}.variantcalling.log
    else
        status=failed
        rm -f ${group_name}.combined.g.vcf ${group_name}.combined.g.vcf.idx ${group_name}.GATK.vcf ${group_name}.GATK.vcf.idx
        echo "failed=\${completed_at}" >> ${group_name}.variantcalling.log
        echo "exit_code=\${exit_code}" >> ${group_name}.variantcalling.log
    fi
    printf "step\\ttool\\tsample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n" > ${group_name}.variantcalling.status.tsv
    printf "variantcalling\\tGATK_JOINT_GENOTYPING\\t${sample_id}\\t${role}\\t${group_name}\\t\${status}\\t\${exit_code}\\t\${started_at}\\t\${completed_at}\\n" >> ${group_name}.variantcalling.status.tsv
    exit 0
    """
}


process DEEPVARIANT_CALLER {
    tag "${sample_name}"
    cpus { variant_threads }
    memory { variant_ram }
    container { deepvariant_container ?: null }
    publishDir "${params.outdir}/VARIANTCALLING", mode: 'copy', pattern: '*.DeepVariant.vcf*'
    publishDir "${params.outdir}/VARIANTCALLING", mode: 'copy', pattern: '*.DeepVariant.g.vcf*'
    publishDir "${params.outdir}/LOGS/VARIANTCALLING/samples", mode: 'copy', pattern: '*.variantcalling.log'
    publishDir "${params.outdir}/LOGS/VARIANTCALLING/samples", mode: 'copy', pattern: '*.variantcalling.status.tsv'

    input:
    tuple val(sample_id), val(role), val(sample_name), path(input_bam)
    val variant_threads
    val variant_ram
    val deepvariant_path
    val deepvariant_container
    val deepvariant_args
    val reference_fasta
    val model_type
    val target_intervals

    output:
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.DeepVariant.vcf"), optional: true, emit: vcfs
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.DeepVariant.g.vcf"), optional: true, emit: gvcfs
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.variantcalling.log"), path("${sample_name}.variantcalling.status.tsv"), emit: statuses

    script:
    def regions_arg = target_intervals ? "--regions ${target_intervals}" : ''
    """
    set +e
    {
        echo "step=variantcalling"
        echo "tool=DeepVariant"
        echo "sample_id=${sample_id}"
        echo "role=${role}"
        echo "sample_name=${sample_name}"
        echo "threads=${task.cpus}"
        echo "reference=${reference_fasta}"
        echo "input_bam=${input_bam}"
        echo "container=${deepvariant_container}"
        echo "model_type=${model_type}"
        echo "target_intervals=${target_intervals}"
        echo "started=\$(date -Is)"
        echo "command=${deepvariant_path} --model_type=${model_type} --ref=${reference_fasta} --reads=${input_bam} --output_vcf=${sample_name}.DeepVariant.vcf --output_gvcf=${sample_name}.DeepVariant.g.vcf --num_shards=${task.cpus} ${regions_arg} ${deepvariant_args}"
        echo
    } > ${sample_name}.variantcalling.log
    started_at=\$(date -Is)
    ${deepvariant_path} \
        --model_type="${model_type}" \
        --ref="${reference_fasta}" \
        --reads="${input_bam}" \
        --output_vcf="${sample_name}.DeepVariant.vcf" \
        --output_gvcf="${sample_name}.DeepVariant.g.vcf" \
        --num_shards="${task.cpus}" \
        ${regions_arg} \
        ${deepvariant_args} >> ${sample_name}.variantcalling.log 2>&1
    exit_code=\$?
    completed_at=\$(date -Is)
    if [ "\${exit_code}" -eq 0 ]; then
        status=completed
        echo "completed=\${completed_at}" >> ${sample_name}.variantcalling.log
    else
        status=failed
        rm -f ${sample_name}.DeepVariant.vcf ${sample_name}.DeepVariant.vcf.gz ${sample_name}.DeepVariant.vcf.idx ${sample_name}.DeepVariant.g.vcf ${sample_name}.DeepVariant.g.vcf.gz ${sample_name}.DeepVariant.g.vcf.idx
        echo "failed=\${completed_at}" >> ${sample_name}.variantcalling.log
        echo "exit_code=\${exit_code}" >> ${sample_name}.variantcalling.log
    fi
    printf "step\\ttool\\tsample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n" > ${sample_name}.variantcalling.status.tsv
    printf "variantcalling\\tDEEPVARIANT\\t${sample_id}\\t${role}\\t${sample_name}\\t\${status}\\t\${exit_code}\\t\${started_at}\\t\${completed_at}\\n" >> ${sample_name}.variantcalling.status.tsv
    exit 0
    """
}


process FREEBAYES_CALLER {
    tag "${sample_name}"
    cpus { variant_threads }
    memory { variant_ram }
    container { freebayes_container ?: null }
    publishDir "${params.outdir}/VARIANTCALLING", mode: 'copy', pattern: '*.Freebayes.vcf*'
    publishDir "${params.outdir}/LOGS/VARIANTCALLING/samples", mode: 'copy', pattern: '*.variantcalling.log'
    publishDir "${params.outdir}/LOGS/VARIANTCALLING/samples", mode: 'copy', pattern: '*.variantcalling.status.tsv'

    input:
    tuple val(sample_id), val(role), val(sample_name), path(input_bams), val(use_bam_list)
    val variant_threads
    val variant_ram
    val freebayes_path
    val freebayes_container
    val freebayes_args
    val freebayes_filter_args
    val reference_fasta
    val target_intervals
    val calling_mode

    output:
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.Freebayes.vcf"), optional: true, emit: vcfs
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.variantcalling.log"), path("${sample_name}.variantcalling.status.tsv"), emit: statuses

    script:
    def target_arg = target_intervals ? "-t ${target_intervals}" : ''
    def bam_arg = use_bam_list ? "-L ${sample_name}.bam.list" : "-b ${input_bams}"
    """
    set +e
    if [ "${use_bam_list}" = "true" ]; then
        printf "%s\\n" ${input_bams} > ${sample_name}.bam.list
    fi
    {
        echo "step=variantcalling"
        echo "tool=FreeBayes"
        echo "calling_mode=${calling_mode}"
        echo "sample_id=${sample_id}"
        echo "role=${role}"
        echo "sample_name=${sample_name}"
        echo "threads=${task.cpus}"
        echo "reference=${reference_fasta}"
        echo "input_bams=${input_bams}"
        echo "container=${freebayes_container}"
        echo "target_intervals=${target_intervals}"
        echo "started=\$(date -Is)"
        echo "command=${freebayes_path} -f ${reference_fasta} -v ${sample_name}.Freebayes.vcf --pooled-discrete --pooled-continuous --genotype-qualities --report-genotype-likelihood-max --allele-balance-priors-off ${bam_arg} ${freebayes_filter_args} ${target_arg} ${freebayes_args}"
        echo
    } > ${sample_name}.variantcalling.log
    started_at=\$(date -Is)
    ${freebayes_path} \
        -f "${reference_fasta}" \
        -v "${sample_name}.Freebayes.vcf" \
        --pooled-discrete \
        --pooled-continuous \
        --genotype-qualities \
        --report-genotype-likelihood-max \
        --allele-balance-priors-off \
        ${bam_arg} \
        ${freebayes_filter_args} \
        ${target_arg} \
        ${freebayes_args} >> ${sample_name}.variantcalling.log 2>&1
    exit_code=\$?
    completed_at=\$(date -Is)
    if [ "\${exit_code}" -eq 0 ]; then
        status=completed
        echo "completed=\${completed_at}" >> ${sample_name}.variantcalling.log
    else
        status=failed
        rm -f ${sample_name}.Freebayes.vcf
        echo "failed=\${completed_at}" >> ${sample_name}.variantcalling.log
        echo "exit_code=\${exit_code}" >> ${sample_name}.variantcalling.log
    fi
    printf "step\\ttool\\tsample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n" > ${sample_name}.variantcalling.status.tsv
    printf "variantcalling\\tFREEBAYES\\t${sample_id}\\t${role}\\t${sample_name}\\t\${status}\\t\${exit_code}\\t\${started_at}\\t\${completed_at}\\n" >> ${sample_name}.variantcalling.status.tsv
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
    run_config
    reference_fasta
    infra_ready

    main:
    variant_cfg = pipeline_config.variantcalling ?: [:]
    resolved_cfg = variant_cfg.resolved ?: [:]
    variant_threads = (variant_cfg.threads ?: 1) as int
    variant_ram = variant_cfg.ram ?: '1 GB'
    gatk_tool = (variant_cfg.tools ?: []).find { tool -> tool.toString().toUpperCase().startsWith('GATK') }
    deepvariant_tool = (variant_cfg.tools ?: []).find { tool -> tool.toString().toUpperCase().startsWith('DEEPVARIANT') }
    freebayes_tool = (variant_cfg.tools ?: []).find { tool -> tool.toString().toUpperCase().startsWith('FREEBAYES') }
    tool_name = gatk_tool ?: deepvariant_tool ?: freebayes_tool ?: 'GATK v.4.1'
    tool_upper = tool_name.toString().toUpperCase()
    if (!tool_upper.startsWith('GATK') && !tool_upper.startsWith('DEEPVARIANT') && !tool_upper.startsWith('FREEBAYES')) {
        error "The Nextflow variantcalling slice currently supports GATK HaplotypeCaller, DeepVariant, and FreeBayes"
    }
    tool_cfg = tools_config[tool_name] ?: [:]
    gatk_path = resolved_cfg.caller?.path ?: tool_cfg.path ?: 'gatk'
    gatk_args = resolved_cfg.caller?.resolved_args ?: (variant_cfg[tool_name]?.args ?: []).join(' ')
    joint_args = variant_cfg.joint_args instanceof List ? variant_cfg.joint_args.join(' ') : (variant_cfg.joint_args ?: '')
    gatk_java_home = resolved_cfg.caller?.java_home ?: tool_cfg.java_home ?: tool_cfg.javaHome ?: System.getenv('GATK_JAVA_HOME') ?: ''
    gatk_java_cmd = resolved_cfg.caller?.java_path ?: resolved_cfg.caller?.java_cmd ?: tool_cfg.java_path ?: tool_cfg.java_cmd ?: tool_cfg.java ?: System.getenv('GATK_JAVA_CMD') ?: ''
    sample_organization = (run_config.sample_organization ?: 'only cases').toString()
    pipeline_samples_org = (variant_cfg.samples_org ?: variant_cfg.samples_organization ?: 'single-sample').toString()
    calling_mode = sample_organization == 'trio'
        ? 'trio'
        : (sample_organization == 'case-control'
            ? 'case-control'
            : (pipeline_samples_org == 'cohort' ? 'cohort' : 'single-sample'))

    ready_bams = bam_ch
        .combine(infra_ready)
        .map { sample_id, role, sample_name, bam, bai, ready -> tuple(sample_id, role, sample_name, bam) }

    if (tool_upper.startsWith('DEEPVARIANT')) {
        deepvariant_container = (tool_cfg.container instanceof Map ? tool_cfg.container.image : tool_cfg.container) ?: resolved_cfg.caller?.container?.image ?: ''
        deepvariant_path = deepvariant_container ? (tool_cfg.path ?: resolved_cfg.caller?.path ?: '/opt/deepvariant/bin/run_deepvariant') : (resolved_cfg.caller?.path ?: tool_cfg.path ?: 'run_deepvariant')
        deepvariant_args = resolved_cfg.caller?.resolved_args ?: (variant_cfg[tool_name]?.args ?: []).join(' ')
        model_type = variant_cfg[tool_name]?.model_type ?: variant_cfg.model_type ?: 'WES'
        target_intervals = resolved_cfg.caller?.target_intervals ?: ''
        DEEPVARIANT_CALLER(ready_bams, variant_threads, variant_ram, deepvariant_path, deepvariant_container, deepvariant_args, reference_fasta, model_type, target_intervals)
        output_vcfs = DEEPVARIANT_CALLER.out.vcfs
        output_statuses = DEEPVARIANT_CALLER.out.statuses
        status_files = DEEPVARIANT_CALLER.out.statuses.map { sample_id, role, sample_name, log_file, status_file -> status_file }.collect()
    } else if (tool_upper.startsWith('FREEBAYES')) {
        freebayes_container = (tool_cfg.container instanceof Map ? tool_cfg.container.image : tool_cfg.container) ?: resolved_cfg.caller?.container?.image ?: ''
        freebayes_path = freebayes_container ? (tool_cfg.path ?: resolved_cfg.caller?.path ?: 'freebayes') : (resolved_cfg.caller?.path ?: tool_cfg.path ?: 'freebayes')
        freebayes_args = variant_cfg[tool_name]?.args instanceof List ? variant_cfg[tool_name].args.join(' ') : (variant_cfg[tool_name]?.args ?: '')
        target_intervals = resolved_cfg.caller?.target_intervals ?: ''
        filters = variant_cfg.filters instanceof Map ? variant_cfg.filters : [:]
        freebayes_filter_args = [
            filters.min_base_quality_score ? "--min-base-quality ${filters.min_base_quality_score}" : '',
            filters.min_alt_coverage ? "--min-alternate-count ${filters.min_alt_coverage}" : '',
            filters.min_alt_freq ? "--min-alternate-fraction ${filters.min_alt_freq}" : '',
            filters.min_mapping_quality_score ? "--min-mapping-quality ${filters.min_mapping_quality_score}" : '',
        ].findAll { it }.join(' ')
        if (calling_mode == 'single-sample') {
            freebayes_inputs = ready_bams.map { sample_id, role, sample_name, bam -> tuple(sample_id, role, sample_name, bam, false) }
        } else {
            freebayes_inputs = ready_bams
                .map { sample_id, role, sample_name, bam ->
                    def group_id = calling_mode == 'cohort' ? 'cohort' : sample_id
                    def group_role = calling_mode == 'cohort' ? 'cohort' : (calling_mode == 'trio' ? 'trio' : 'case-control')
                    def group_name = calling_mode == 'cohort' ? 'cohort' : "${sample_id}.${calling_mode.replace('-', '_')}"
                    tuple([group_id, group_role, group_name], bam)
                }
                .groupTuple()
                .map { group_key, bams -> tuple(group_key[0], group_key[1], group_key[2], bams, true) }
        }
        FREEBAYES_CALLER(freebayes_inputs, variant_threads, variant_ram, freebayes_path, freebayes_container, freebayes_args, freebayes_filter_args, reference_fasta, target_intervals, calling_mode)
        output_vcfs = FREEBAYES_CALLER.out.vcfs
        output_statuses = FREEBAYES_CALLER.out.statuses
        status_files = FREEBAYES_CALLER.out.statuses.map { sample_id, role, sample_name, log_file, status_file -> status_file }.collect()
    } else {
        GATK_HAPLOTYPECALLER(ready_bams, variant_threads, variant_ram, gatk_path, gatk_args, gatk_java_home, gatk_java_cmd, reference_fasta, calling_mode)
        haplotype_statuses = GATK_HAPLOTYPECALLER.out.statuses.map { sample_id, role, sample_name, log_file, status_file -> status_file }

        if (calling_mode == 'single-sample') {
            output_vcfs = GATK_HAPLOTYPECALLER.out.vcfs
            output_statuses = GATK_HAPLOTYPECALLER.out.statuses
            status_files = haplotype_statuses.collect()
        } else {
            grouped_gvcfs = GATK_HAPLOTYPECALLER.out.gvcfs
                .map { sample_id, role, sample_name, gvcf ->
                    def group_id = calling_mode == 'cohort' ? 'cohort' : sample_id
                    def group_role = calling_mode == 'cohort' ? 'cohort' : (calling_mode == 'trio' ? 'trio' : 'case-control')
                    def group_name = calling_mode == 'cohort' ? 'cohort' : "${sample_id}.${calling_mode.replace('-', '_')}"
                    tuple([group_id, group_role, group_name], gvcf)
                }
                .groupTuple()
                .map { group_key, gvcfs -> tuple(group_key[0], group_key[1], group_key[2], gvcfs) }
            GATK_JOINT_GENOTYPING(grouped_gvcfs, variant_threads, variant_ram, gatk_path, joint_args, gatk_java_home, gatk_java_cmd, reference_fasta, calling_mode)
            output_vcfs = GATK_JOINT_GENOTYPING.out.vcfs
            output_statuses = GATK_JOINT_GENOTYPING.out.statuses
            joint_statuses = GATK_JOINT_GENOTYPING.out.statuses.map { sample_id, role, sample_name, log_file, status_file -> status_file }
            status_files = haplotype_statuses.mix(joint_statuses).collect()
        }
    }

    VARIANTCALLING_STEP_LOG(tool_name, status_files)
    VARIANTCALLING_ASSERT_SUCCESS(status_files, VARIANTCALLING_STEP_LOG.out.log)

    emit:
    vcfs = output_vcfs
    statuses = output_statuses
    step_log = VARIANTCALLING_STEP_LOG.out.log
    ready = VARIANTCALLING_ASSERT_SUCCESS.out.ready
}
