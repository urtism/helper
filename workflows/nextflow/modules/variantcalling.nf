nextflow.enable.dsl = 2


def configuredContainer(config) {
    if (!(config instanceof Map)) {
        return ''
    }
    def container = config['container']
    return container instanceof Map ? (container['image'] ?: '') : (container ?: '')
}


process GATK_HAPLOTYPECALLER {
    tag "${sample_name}"
    cpus { variant_threads }
    memory { variant_ram }
    publishDir "${params.outdir}/VARIANTCALLING", mode: 'copy', pattern: '*.GATK.vcf*'
    publishDir "${params.outdir}/VARIANTCALLING/GVCF", mode: 'copy', pattern: '*.GATK.g.vcf*'
    publishDir "${params.outdir}/VARIANTCALLING/realigned_bam", mode: 'copy', pattern: '*.realign.bam*', enabled: params.keep_intermediates == true || params.keep_intermediates?.toString()?.toLowerCase() in ['true', '1', 'yes']
    publishDir "${params.outdir}/LOGS/VARIANTCALLING/samples", mode: 'copy', pattern: '*.variantcalling.log'
    publishDir "${params.outdir}/LOGS/VARIANTCALLING/samples", mode: 'copy', pattern: '*.variantcalling.status.tsv'

    input:
    tuple val(sample_id), val(role), val(sample_name), path(input_bam), path(input_bai)
    val variant_threads
    val variant_ram
    val gatk_path
    val gatk_args
    val gatk_java_home
    val gatk_java_cmd
    val reference_fasta
    val target_intervals
    val calling_mode
    val restart_token

    output:
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.GATK.vcf"), optional: true, emit: vcfs
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.GATK.g.vcf.gz"), optional: true, emit: gvcfs
    path "${sample_name}.GATK.g.vcf.gz.tbi", optional: true, emit: gvcf_indexes
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.GATK.realign.bam"), optional: true, emit: realigned_bams
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.GATK.variantcalling.log"), path("${sample_name}.GATK.variantcalling.status.tsv"), emit: statuses

    script:
    def target_arg = target_intervals ? "-L \"${target_intervals}\"" : ''
    def genotype_command = calling_mode == 'single-sample'
        ? "${gatk_path} --java-options -Xmx${task.memory.toGiga()}g GenotypeGVCFs -R ${reference_fasta} -V ${sample_name}.GATK.g.vcf.gz -O ${sample_name}.GATK.vcf ${target_arg}"
        : "not requested"
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
        echo "target_intervals=${target_intervals}"
        echo "input_bam=${input_bam}"
        echo "java_home=\${JAVA_HOME:-}"
        echo "java_version=\$(java -version 2>&1 | head -n 1)"
        echo "started=\$(date -Is)"
        echo "haplotype_command=${gatk_path} --java-options -Xmx${task.memory.toGiga()}g HaplotypeCaller -R ${reference_fasta} -I ${input_bam} -O ${sample_name}.GATK.g.vcf.gz -bamout ${sample_name}.GATK.realign.bam -ERC GVCF --native-pair-hmm-threads ${task.cpus} ${target_arg} ${gatk_args}"
        echo "genotype_command=${genotype_command}"
        echo
    } > ${sample_name}.GATK.variantcalling.log
    started_at=\$(date -Is)
    ${gatk_path} --java-options "-Xmx${task.memory.toGiga()}g" HaplotypeCaller \
        -R "${reference_fasta}" \
        -I "${input_bam}" \
        -O "${sample_name}.GATK.g.vcf.gz" \
        -bamout "${sample_name}.GATK.realign.bam" \
        -ERC GVCF \
        --native-pair-hmm-threads ${task.cpus} \
        ${target_arg} \
        ${gatk_args} >> ${sample_name}.GATK.variantcalling.log 2>&1
    exit_code=\$?
    if [ "\${exit_code}" -eq 0 ] && [ "${calling_mode}" = "single-sample" ]; then
        ${gatk_path} --java-options "-Xmx${task.memory.toGiga()}g" GenotypeGVCFs \
            -R "${reference_fasta}" \
            -V "${sample_name}.GATK.g.vcf.gz" \
            -O "${sample_name}.GATK.vcf" \
            ${target_arg} >> ${sample_name}.GATK.variantcalling.log 2>&1
        exit_code=\$?
    fi
    completed_at=\$(date -Is)
    if [ "\${exit_code}" -eq 0 ]; then
        status=completed
        echo "completed=\${completed_at}" >> ${sample_name}.GATK.variantcalling.log
    else
        status=failed
        rm -f ${sample_name}.GATK.vcf ${sample_name}.GATK.vcf.idx ${sample_name}.GATK.g.vcf.gz ${sample_name}.GATK.g.vcf.gz.tbi ${sample_name}.GATK.realign.bam
        echo "failed=\${completed_at}" >> ${sample_name}.GATK.variantcalling.log
        echo "exit_code=\${exit_code}" >> ${sample_name}.GATK.variantcalling.log
    fi
    if [ "${params.keep_intermediates}" != "true" ] && [ "${params.keep_intermediates}" != "1" ] && [ "${params.keep_intermediates}" != "yes" ]; then
        rm -f ${sample_name}.GATK.realign.bam
    fi
    printf "step\\ttool\\tsample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n" > ${sample_name}.GATK.variantcalling.status.tsv
    printf "variantcalling\\tGATK_HAPLOTYPECALLER\\t${sample_id}\\t${role}\\t${sample_name}\\t\${status}\\t\${exit_code}\\t\${started_at}\\t\${completed_at}\\n" >> ${sample_name}.GATK.variantcalling.status.tsv
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
    val target_intervals
    val calling_mode

    output:
    tuple val(sample_id), val(role), val(group_name), path("${group_name}.GATK.vcf"), optional: true, emit: vcfs
    tuple val(sample_id), val(role), val(group_name), path("${group_name}.GATK.variantcalling.log"), path("${group_name}.GATK.variantcalling.status.tsv"), emit: statuses

    script:
    def variant_inputs = gvcfs.collect { "-V ${it}" }.join(' ')
    def target_arg = target_intervals ? "-L \"${target_intervals}\"" : ''
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
        echo "target_intervals=${target_intervals}"
        echo "input_gvcfs=${gvcfs.join(',')}"
        echo "java_home=\${JAVA_HOME:-}"
        echo "java_version=\$(java -version 2>&1 | head -n 1)"
        echo "started=\$(date -Is)"
        echo "combine_command=${gatk_path} --java-options -Xmx${task.memory.toGiga()}g CombineGVCFs -R ${reference_fasta} ${variant_inputs} -O ${group_name}.combined.g.vcf ${target_arg}"
        echo "genotype_command=${gatk_path} --java-options -Xmx${task.memory.toGiga()}g GenotypeGVCFs -R ${reference_fasta} -V ${group_name}.combined.g.vcf -O ${group_name}.GATK.vcf ${target_arg} ${joint_args}"
        echo
    } > ${group_name}.GATK.variantcalling.log
    started_at=\$(date -Is)
    ${gatk_path} --java-options "-Xmx${task.memory.toGiga()}g" CombineGVCFs \
        -R "${reference_fasta}" \
        ${variant_inputs} \
        -O "${group_name}.combined.g.vcf" \
        ${target_arg} >> ${group_name}.GATK.variantcalling.log 2>&1
    exit_code=\$?
    if [ "\${exit_code}" -eq 0 ]; then
        ${gatk_path} --java-options "-Xmx${task.memory.toGiga()}g" GenotypeGVCFs \
            -R "${reference_fasta}" \
            -V "${group_name}.combined.g.vcf" \
            -O "${group_name}.GATK.vcf" \
            ${target_arg} \
            ${joint_args} >> ${group_name}.GATK.variantcalling.log 2>&1
        exit_code=\$?
    fi
    completed_at=\$(date -Is)
    if [ "\${exit_code}" -eq 0 ]; then
        status=completed
        echo "completed=\${completed_at}" >> ${group_name}.GATK.variantcalling.log
    else
        status=failed
        rm -f ${group_name}.combined.g.vcf ${group_name}.combined.g.vcf.idx ${group_name}.GATK.vcf ${group_name}.GATK.vcf.idx
        echo "failed=\${completed_at}" >> ${group_name}.GATK.variantcalling.log
        echo "exit_code=\${exit_code}" >> ${group_name}.GATK.variantcalling.log
    fi
    printf "step\\ttool\\tsample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n" > ${group_name}.GATK.variantcalling.status.tsv
    printf "variantcalling\\tGATK_JOINT_GENOTYPING\\t${sample_id}\\t${role}\\t${group_name}\\t\${status}\\t\${exit_code}\\t\${started_at}\\t\${completed_at}\\n" >> ${group_name}.GATK.variantcalling.status.tsv
    exit 0
    """
}


process GATK_MUTECT2 {
    tag "${group_name}"
    cpus { variant_threads }
    memory { variant_ram }
    publishDir "${params.outdir}/VARIANTCALLING", mode: 'copy', pattern: '*.Mutect2.vcf*'
    publishDir "${params.outdir}/LOGS/VARIANTCALLING/samples", mode: 'copy', pattern: '*.variantcalling.log'
    publishDir "${params.outdir}/LOGS/VARIANTCALLING/samples", mode: 'copy', pattern: '*.variantcalling.status.tsv'

    input:
    tuple val(analysis_id), val(role), val(group_name), val(tumor_name), path(tumor_bam), path(tumor_bai), val(normal_name), path(normal_bam), path(normal_bai)
    val variant_threads
    val variant_ram
    val gatk_path
    val mutect2_args
    val mutect2_filter_args
    val gatk_java_home
    val gatk_java_cmd
    val reference_fasta
    val target_intervals
    val restart_token

    output:
    tuple val(analysis_id), val(role), val(group_name), path("${group_name}.Mutect2.vcf"), optional: true, emit: vcfs
    tuple val(analysis_id), val(role), val(group_name), path("${group_name}.Mutect2.variantcalling.log"), path("${group_name}.Mutect2.variantcalling.status.tsv"), emit: statuses

    script:
    def target_arg = target_intervals ? "-L \"${target_intervals}\"" : ''
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
        echo "tool=GATK Mutect2"
        echo "analysis_id=${analysis_id}"
        echo "role=${role}"
        echo "sample_name=${group_name}"
        echo "tumor_name=${tumor_name}"
        echo "normal_name=${normal_name}"
        echo "tumor_bam=${tumor_bam}"
        echo "normal_bam=${normal_bam}"
        echo "reference=${reference_fasta}"
        echo "target_intervals=${target_intervals}"
        echo "java_home=\${JAVA_HOME:-}"
        echo "java_version=\$(java -version 2>&1 | head -n 1)"
        echo "started=\$(date -Is)"
        echo "mutect2_command=${gatk_path} --java-options -Xmx${task.memory.toGiga()}g Mutect2 -R ${reference_fasta} -I ${tumor_bam} -tumor ${tumor_name} -I ${normal_bam} -normal ${normal_name} -O ${group_name}.Mutect2.unfiltered.vcf ${target_arg} ${mutect2_args}"
        echo "filter_command=${gatk_path} --java-options -Xmx${task.memory.toGiga()}g FilterMutectCalls -R ${reference_fasta} -V ${group_name}.Mutect2.unfiltered.vcf -O ${group_name}.Mutect2.vcf ${target_arg} ${mutect2_filter_args}"
        echo
    } > ${group_name}.Mutect2.variantcalling.log
    started_at=\$(date -Is)
    ${gatk_path} --java-options "-Xmx${task.memory.toGiga()}g" Mutect2 \
        -R "${reference_fasta}" \
        -I "${tumor_bam}" \
        -tumor "${tumor_name}" \
        -I "${normal_bam}" \
        -normal "${normal_name}" \
        -O "${group_name}.Mutect2.unfiltered.vcf" \
        ${target_arg} \
        ${mutect2_args} >> ${group_name}.Mutect2.variantcalling.log 2>&1
    exit_code=\$?
    if [ "\${exit_code}" -eq 0 ]; then
        ${gatk_path} --java-options "-Xmx${task.memory.toGiga()}g" FilterMutectCalls \
            -R "${reference_fasta}" \
            -V "${group_name}.Mutect2.unfiltered.vcf" \
            -O "${group_name}.Mutect2.vcf" \
            ${target_arg} \
            ${mutect2_filter_args} >> ${group_name}.Mutect2.variantcalling.log 2>&1
        exit_code=\$?
    fi
    completed_at=\$(date -Is)
    if [ "\${exit_code}" -eq 0 ]; then
        status=completed
        echo "completed=\${completed_at}" >> ${group_name}.Mutect2.variantcalling.log
    else
        status=failed
        rm -f ${group_name}.Mutect2.vcf ${group_name}.Mutect2.vcf.idx
        echo "failed=\${completed_at}" >> ${group_name}.Mutect2.variantcalling.log
        echo "exit_code=\${exit_code}" >> ${group_name}.Mutect2.variantcalling.log
    fi
    rm -f ${group_name}.Mutect2.unfiltered.vcf ${group_name}.Mutect2.unfiltered.vcf.idx ${group_name}.Mutect2.unfiltered.vcf.stats
    printf "step\\ttool\\tsample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n" > ${group_name}.Mutect2.variantcalling.status.tsv
    printf "variantcalling\\tGATK_MUTECT2\\t${analysis_id}\\t${role}\\t${group_name}\\t\${status}\\t\${exit_code}\\t\${started_at}\\t\${completed_at}\\n" >> ${group_name}.Mutect2.variantcalling.status.tsv
    exit 0
    """
}


process DEEPVARIANT_CALLER {
    tag "${sample_name}"
    cpus { variant_threads }
    memory {
        def requested = MemoryUnit.of(variant_ram)
        def minimum = MemoryUnit.of(deepvariant_min_ram)
        requested > minimum ? requested : minimum
    }
    container { deepvariant_container ?: null }
    publishDir "${params.outdir}/VARIANTCALLING", mode: 'copy', pattern: '*.DeepVariant.vcf*'
    publishDir "${params.outdir}/VARIANTCALLING/GVCF", mode: 'copy', pattern: '*.DeepVariant.g.vcf*'
    publishDir "${params.outdir}/LOGS/VARIANTCALLING/samples", mode: 'copy', pattern: '*.variantcalling.log'
    publishDir "${params.outdir}/LOGS/VARIANTCALLING/samples", mode: 'copy', pattern: '*.variantcalling.status.tsv'

    input:
    tuple val(sample_id), val(role), val(sample_name), path(input_bam), path(input_bai)
    val variant_threads
    val variant_ram
    val deepvariant_min_ram
    val deepvariant_path
    val deepvariant_container
    val deepvariant_args
    val reference_fasta
    val model_type
    val target_intervals
    val restart_token

    output:
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.DeepVariant.vcf"), optional: true, emit: vcfs
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.DeepVariant.g.vcf.gz"), optional: true, emit: gvcfs
    path "${sample_name}.DeepVariant.g.vcf.gz.tbi", optional: true, emit: gvcf_indexes
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.DeepVariant.variantcalling.log"), path("${sample_name}.DeepVariant.variantcalling.status.tsv"), emit: statuses

    script:
    def regions_arg = target_intervals ? "--regions \"${target_intervals}\"" : ''
    """
    set +e
    {
        echo "step=variantcalling"
        echo "tool=DeepVariant"
        echo "sample_id=${sample_id}"
        echo "role=${role}"
        echo "sample_name=${sample_name}"
        echo "threads=${task.cpus}"
        echo "requested_memory=${variant_ram}"
        echo "effective_memory=${task.memory}"
        echo "reference=${reference_fasta}"
        echo "input_bam=${input_bam}"
        echo "container=${deepvariant_container}"
        echo "model_type=${model_type}"
        echo "target_intervals=${target_intervals}"
        echo "started=\$(date -Is)"
        echo "command=${deepvariant_path} --model_type=${model_type} --ref=${reference_fasta} --reads=${input_bam} --output_vcf=${sample_name}.DeepVariant.vcf --output_gvcf=${sample_name}.DeepVariant.g.vcf.gz --num_shards=${task.cpus} ${regions_arg} ${deepvariant_args}"
        echo
    } > ${sample_name}.DeepVariant.variantcalling.log
    started_at=\$(date -Is)
    ${deepvariant_path} \
        --model_type="${model_type}" \
        --ref="${reference_fasta}" \
        --reads="${input_bam}" \
        --output_vcf="${sample_name}.DeepVariant.vcf" \
        --output_gvcf="${sample_name}.DeepVariant.g.vcf.gz" \
        --num_shards="${task.cpus}" \
        ${regions_arg} \
        ${deepvariant_args} >> ${sample_name}.DeepVariant.variantcalling.log 2>&1
    exit_code=\$?
    completed_at=\$(date -Is)
    if [ "\${exit_code}" -eq 0 ]; then
        status=completed
        echo "completed=\${completed_at}" >> ${sample_name}.DeepVariant.variantcalling.log
    else
        status=failed
        rm -f ${sample_name}.DeepVariant.vcf ${sample_name}.DeepVariant.vcf.gz ${sample_name}.DeepVariant.vcf.idx ${sample_name}.DeepVariant.g.vcf.gz ${sample_name}.DeepVariant.g.vcf.gz.tbi
        echo "failed=\${completed_at}" >> ${sample_name}.DeepVariant.variantcalling.log
        echo "exit_code=\${exit_code}" >> ${sample_name}.DeepVariant.variantcalling.log
    fi
    printf "step\\ttool\\tsample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n" > ${sample_name}.DeepVariant.variantcalling.status.tsv
    printf "variantcalling\\tDEEPVARIANT\\t${sample_id}\\t${role}\\t${sample_name}\\t\${status}\\t\${exit_code}\\t\${started_at}\\t\${completed_at}\\n" >> ${sample_name}.DeepVariant.variantcalling.status.tsv
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
    tuple val(sample_id), val(role), val(sample_name), path(input_bams), path(input_bais), val(use_bam_list)
    val variant_threads
    val variant_ram
    val freebayes_path
    val freebayes_container
    val freebayes_args
    val freebayes_filter_args
    val reference_fasta
    val target_intervals
    val calling_mode
    val restart_token

    output:
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.Freebayes.vcf"), optional: true, emit: vcfs
    tuple val(sample_id), val(role), val(sample_name), path("${sample_name}.Freebayes.variantcalling.log"), path("${sample_name}.Freebayes.variantcalling.status.tsv"), emit: statuses

    script:
    def target_arg = target_intervals ? "-t \"${target_intervals}\"" : ''
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
    } > ${sample_name}.Freebayes.variantcalling.log
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
    ${freebayes_args} >> ${sample_name}.Freebayes.variantcalling.log 2>&1
    exit_code=\$?
    if [ "\${exit_code}" -eq 0 ] && { [ ! -s "${sample_name}.Freebayes.vcf" ] || grep -q "Failed to load index" "${sample_name}.Freebayes.variantcalling.log"; }; then
        exit_code=1
    fi
    completed_at=\$(date -Is)
    if [ "\${exit_code}" -eq 0 ]; then
        status=completed
        echo "completed=\${completed_at}" >> ${sample_name}.Freebayes.variantcalling.log
    else
        status=failed
        rm -f ${sample_name}.Freebayes.vcf
        echo "failed=\${completed_at}" >> ${sample_name}.Freebayes.variantcalling.log
        echo "exit_code=\${exit_code}" >> ${sample_name}.Freebayes.variantcalling.log
    fi
    printf "step\\ttool\\tsample_id\\trole\\tsample_name\\tstatus\\texit_code\\tstarted\\tcompleted\\n" > ${sample_name}.Freebayes.variantcalling.status.tsv
    printf "variantcalling\\tFREEBAYES\\t${sample_id}\\t${role}\\t${sample_name}\\t\${status}\\t\${exit_code}\\t\${started_at}\\t\${completed_at}\\n" >> ${sample_name}.Freebayes.variantcalling.status.tsv
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


process VCF_CALLSET_SUMMARY {
    tag "${sample_name}"

    input:
    tuple val(analysis_id), val(role), val(sample_name), path(input_vcf)
    path comparison_script

    output:
    path "*.callset.json.gz", emit: summaries

    script:
    def safe_name = "${analysis_id}.${role}.${sample_name}".replaceAll(/[^A-Za-z0-9._-]/, '_')
    """
    python3 "${comparison_script}" summarize \
        --vcf "${input_vcf}" \
        --analysis-id "${analysis_id}" \
        --role "${role}" \
        --sample-name "${sample_name}" \
        --output "${safe_name}.callset.json.gz"
    """
}


process VCF_RUN_COMPARISON {
    tag 'run-vcf-comparison'
    publishDir "${params.outdir}/REPORTS/VARIANTCALLING", mode: 'copy'

    input:
    path callset_summaries
    path run_config_file
    path comparison_script

    output:
    path "run.vcf_statistics.json", emit: statistics_json
    path "run.sample_statistics.tsv", emit: sample_statistics
    path "run.group_comparison.tsv", emit: group_comparison
    path "run.variant_presence.tsv", emit: variant_presence

    script:
    def summary_args = callset_summaries.collect { "\"${it}\"" }.join(' ')
    """
    python3 "${comparison_script}" aggregate \
        --summaries ${summary_args} \
        --run-config "${run_config_file}" \
        --output-dir .
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
    restart_token

    main:
    variant_cfg = pipeline_config.variantcalling ?: [:]
    resolved_cfg = variant_cfg.resolved ?: [:]
    resolved_callers = resolved_cfg.callers ?: [:]
    variant_threads = (variant_cfg.threads ?: 1) as int
    variant_ram = variant_cfg.ram ?: '1 GB'
    selected_tools = (variant_cfg.tools ?: []).findAll { tool ->
        def upper = tool.toString().toUpperCase()
        upper.startsWith('GATK') || upper.startsWith('DEEPVARIANT') || upper.startsWith('FREEBAYES')
    }
    gatk_tool = selected_tools.find { tool -> tool.toString().toUpperCase().startsWith('GATK') }
    deepvariant_tool = selected_tools.find { tool -> tool.toString().toUpperCase().startsWith('DEEPVARIANT') }
    freebayes_tool = selected_tools.find { tool -> tool.toString().toUpperCase().startsWith('FREEBAYES') }
    primary_tool = gatk_tool ?: deepvariant_tool ?: freebayes_tool
    if (!primary_tool) {
        error "The Nextflow variantcalling slice currently supports GATK HaplotypeCaller, DeepVariant, and FreeBayes"
    }
    tool_names = selected_tools.join(',')
    gatk_resolved = gatk_tool ? (resolved_callers[gatk_tool] ?: (resolved_cfg.caller?.tool == gatk_tool ? resolved_cfg.caller : [:])) : [:]
    deepvariant_resolved = deepvariant_tool ? (resolved_callers[deepvariant_tool] ?: (resolved_cfg.caller?.tool == deepvariant_tool ? resolved_cfg.caller : [:])) : [:]
    freebayes_resolved = freebayes_tool ? (resolved_callers[freebayes_tool] ?: (resolved_cfg.caller?.tool == freebayes_tool ? resolved_cfg.caller : [:])) : [:]
    target_intervals = resolved_callers.values().find { caller -> caller?.target_intervals }?.target_intervals ?:
        resolved_cfg.caller?.target_intervals ?: run_config.panel_design?.assets?.target_bed ?: ''

    gatk_cfg = gatk_tool ? (tools_config[gatk_tool] ?: [:]) : [:]
    gatk_path = gatk_resolved.path ?: gatk_cfg.path ?: 'gatk'
    gatk_raw_args = variant_cfg[gatk_tool]?.args
    gatk_args = gatk_resolved.resolved_args ?: (gatk_raw_args instanceof List ? gatk_raw_args.join(' ') : (gatk_raw_args ?: ''))
    joint_args = variant_cfg.joint_args instanceof List ? variant_cfg.joint_args.join(' ') : (variant_cfg.joint_args ?: '')
    mutect2_args = variant_cfg.mutect2_args instanceof List ? variant_cfg.mutect2_args.join(' ') : (variant_cfg.mutect2_args ?: '')
    mutect2_filter_args = variant_cfg.mutect2_filter_args instanceof List ? variant_cfg.mutect2_filter_args.join(' ') : (variant_cfg.mutect2_filter_args ?: '')
    gatk_java_home = gatk_resolved.java_home ?: gatk_cfg.java_home ?: gatk_cfg.javaHome ?: System.getenv('GATK_JAVA_HOME') ?: ''
    gatk_java_cmd = gatk_resolved.java_path ?: gatk_resolved.java_cmd ?: gatk_cfg.java_path ?: gatk_cfg.java_cmd ?: gatk_cfg.java ?: System.getenv('GATK_JAVA_CMD') ?: ''
    sample_organization = (run_config.sample_organization ?: 'only cases').toString()
    analysis_schema = ((run_config.schema_version ?: 1) as int) == 2 || sample_organization == 'mixed'
    has_tumor_normal = analysis_schema && (run_config.analysis_groups ?: []).any { group -> group.analysis_type == 'tumor-normal' }
    pipeline_samples_org = (variant_cfg.samples_org ?: variant_cfg.samples_organization ?: 'single-sample').toString()
    calling_mode = analysis_schema
        ? (run_config.calling_scope ?: 'single-sample').toString()
        : (sample_organization == 'trio'
        ? 'trio'
        : (sample_organization == 'case-control'
            ? 'case-control'
            : (pipeline_samples_org == 'cohort' ? 'cohort' : 'single-sample')))

    configured_gatk4_tool = tools_config.keySet().find { name -> name.toString().toUpperCase().startsWith('GATK V.4') }
    somatic_gatk_tool = gatk_tool?.toString()?.toUpperCase()?.startsWith('GATK V.4') ? gatk_tool : configured_gatk4_tool
    somatic_gatk_cfg = somatic_gatk_tool ? (tools_config[somatic_gatk_tool] ?: [:]) : [:]
    selected_gatk4 = somatic_gatk_tool && somatic_gatk_tool == gatk_tool
    somatic_gatk_path = selected_gatk4 ? gatk_path : (somatic_gatk_cfg.path ?: 'gatk')
    somatic_gatk_java_home = selected_gatk4
        ? gatk_java_home
        : (somatic_gatk_cfg.java_home ?: somatic_gatk_cfg.javaHome ?: System.getenv('GATK_JAVA_HOME') ?: '')
    somatic_gatk_java_cmd = selected_gatk4
        ? gatk_java_cmd
        : (somatic_gatk_cfg.java_path ?: somatic_gatk_cfg.java_cmd ?: somatic_gatk_cfg.java ?: System.getenv('GATK_JAVA_CMD') ?: '')

    ready_bams = bam_ch
        .combine(infra_ready)
        .map { sample_id, role, sample_name, bam, bai, ready -> tuple(sample_id, role, sample_name, bam, bai) }
    germline_bams = analysis_schema
        ? ready_bams.filter { sample_id, role, sample_name, bam, bai -> !(role in ['tumor', 'normal']) }
        : ready_bams

    gatk_vcfs = channel.empty()
    gatk_statuses = channel.empty()
    deepvariant_vcfs = channel.empty()
    deepvariant_statuses = channel.empty()
    freebayes_vcfs = channel.empty()
    freebayes_statuses = channel.empty()

    if (gatk_tool) {
        GATK_HAPLOTYPECALLER(germline_bams, variant_threads, variant_ram, gatk_path, gatk_args, gatk_java_home, gatk_java_cmd, reference_fasta, target_intervals, calling_mode, restart_token)
        if (calling_mode == 'single-sample') {
            gatk_vcfs = GATK_HAPLOTYPECALLER.out.vcfs
            gatk_statuses = GATK_HAPLOTYPECALLER.out.statuses
        } else {
            grouped_gvcfs = GATK_HAPLOTYPECALLER.out.gvcfs
                .map { sample_id, role, sample_name, gvcf ->
                    def group_id = calling_mode in ['cohort', 'run'] ? (run_config.calling_group ?: calling_mode) : sample_id
                    def group_role = calling_mode in ['cohort', 'run'] ? calling_mode : (calling_mode == 'trio' ? 'trio' : 'case-control')
                    def group_name = calling_mode in ['cohort', 'run'] ? (run_config.calling_group ?: calling_mode) : "${sample_id}.${calling_mode.replace('-', '_')}"
                    tuple([group_id, group_role, group_name], gvcf)
                }
                .groupTuple()
                .map { group_key, gvcfs -> tuple(group_key[0], group_key[1], group_key[2], gvcfs) }
            GATK_JOINT_GENOTYPING(grouped_gvcfs, variant_threads, variant_ram, gatk_path, joint_args, gatk_java_home, gatk_java_cmd, reference_fasta, target_intervals, calling_mode)
            gatk_vcfs = GATK_JOINT_GENOTYPING.out.vcfs
            gatk_statuses = GATK_HAPLOTYPECALLER.out.statuses.mix(GATK_JOINT_GENOTYPING.out.statuses)
        }
    }

    if (deepvariant_tool) {
        deepvariant_cfg = tools_config[deepvariant_tool] ?: [:]
        deepvariant_container = configuredContainer(deepvariant_cfg) ?: configuredContainer(deepvariant_resolved)
        deepvariant_min_ram = deepvariant_cfg.minimum_ram ?: '8 GB'
        deepvariant_path = deepvariant_container ? (deepvariant_cfg.path ?: deepvariant_resolved.path ?: '/opt/deepvariant/bin/run_deepvariant') : (deepvariant_resolved.path ?: deepvariant_cfg.path ?: 'run_deepvariant')
        deepvariant_raw_args = variant_cfg[deepvariant_tool]?.args
        deepvariant_args = deepvariant_resolved.resolved_args ?: (deepvariant_raw_args instanceof List ? deepvariant_raw_args.join(' ') : (deepvariant_raw_args ?: ''))
        model_type = variant_cfg[deepvariant_tool]?.model_type ?: variant_cfg.model_type ?: 'WES'
        DEEPVARIANT_CALLER(germline_bams, variant_threads, variant_ram, deepvariant_min_ram, deepvariant_path, deepvariant_container, deepvariant_args, reference_fasta, model_type, target_intervals, restart_token)
        deepvariant_vcfs = DEEPVARIANT_CALLER.out.vcfs
        deepvariant_statuses = DEEPVARIANT_CALLER.out.statuses
    }

    if (freebayes_tool) {
        freebayes_cfg = tools_config[freebayes_tool] ?: [:]
        freebayes_container = configuredContainer(freebayes_cfg) ?: configuredContainer(freebayes_resolved)
        freebayes_path = freebayes_container ? (freebayes_cfg.path ?: freebayes_resolved.path ?: 'freebayes') : (freebayes_resolved.path ?: freebayes_cfg.path ?: 'freebayes')
        freebayes_raw_args = variant_cfg[freebayes_tool]?.args
        freebayes_args = freebayes_resolved.resolved_args ?: (freebayes_raw_args instanceof List ? freebayes_raw_args.join(' ') : (freebayes_raw_args ?: ''))
        filters = variant_cfg.filters instanceof Map ? variant_cfg.filters : [:]
        freebayes_filter_args = [
            filters.min_base_quality_score ? "--min-base-quality ${filters.min_base_quality_score}" : '',
            filters.min_alt_coverage ? "--min-alternate-count ${filters.min_alt_coverage}" : '',
            filters.min_alt_freq ? "--min-alternate-fraction ${filters.min_alt_freq}" : '',
            filters.min_mapping_quality_score ? "--min-mapping-quality ${filters.min_mapping_quality_score}" : '',
        ].findAll { it }.join(' ')
        if (calling_mode == 'single-sample') {
            freebayes_inputs = germline_bams.map { sample_id, role, sample_name, bam, bai -> tuple(sample_id, role, sample_name, bam, bai, false) }
        } else {
            freebayes_inputs = germline_bams
                .map { sample_id, role, sample_name, bam, bai ->
                    def group_id = calling_mode in ['cohort', 'run'] ? (run_config.calling_group ?: calling_mode) : sample_id
                    def group_role = calling_mode in ['cohort', 'run'] ? calling_mode : (calling_mode == 'trio' ? 'trio' : 'case-control')
                    def group_name = calling_mode in ['cohort', 'run'] ? (run_config.calling_group ?: calling_mode) : "${sample_id}.${calling_mode.replace('-', '_')}"
                    tuple([group_id, group_role, group_name], bam, bai)
                }
                .groupTuple()
                .map { group_key, bams, bais -> tuple(group_key[0], group_key[1], group_key[2], bams, bais, true) }
        }
        FREEBAYES_CALLER(freebayes_inputs, variant_threads, variant_ram, freebayes_path, freebayes_container, freebayes_args, freebayes_filter_args, reference_fasta, target_intervals, calling_mode, restart_token)
        freebayes_vcfs = FREEBAYES_CALLER.out.vcfs
        freebayes_statuses = FREEBAYES_CALLER.out.statuses
    }

    germline_vcfs = gatk_tool ? gatk_vcfs : (deepvariant_tool ? deepvariant_vcfs : freebayes_vcfs)
    germline_caller_vcfs = gatk_vcfs
        .map { sample_id, role, sample_name, vcf -> tuple(sample_id, role, sample_name, 'GATK', vcf) }
        .mix(deepvariant_vcfs.map { sample_id, role, sample_name, vcf -> tuple(sample_id, role, sample_name, 'DEEPVARIANT', vcf) })
        .mix(freebayes_vcfs.map { sample_id, role, sample_name, vcf -> tuple(sample_id, role, sample_name, 'FREEBAYES', vcf) })
    germline_statuses = gatk_statuses.mix(deepvariant_statuses).mix(freebayes_statuses)

    if (has_tumor_normal) {
        somatic_pairs = ready_bams
            .filter { sample_id, role, sample_name, bam, bai -> role in ['tumor', 'normal'] }
            .groupTuple()
            .map { analysis_id, roles, sample_names, bams, bais ->
                def tumor_index = roles.indexOf('tumor')
                def normal_index = roles.indexOf('normal')
                def safe_id = analysis_id.toString().replaceAll(/[^A-Za-z0-9._-]/, '_')
                tuple(analysis_id, 'tumor-normal', "${safe_id}.tumor_normal", sample_names[tumor_index], bams[tumor_index], bais[tumor_index], sample_names[normal_index], bams[normal_index], bais[normal_index])
            }
        GATK_MUTECT2(somatic_pairs, variant_threads, variant_ram, somatic_gatk_path, mutect2_args, mutect2_filter_args, somatic_gatk_java_home, somatic_gatk_java_cmd, reference_fasta, target_intervals, restart_token)
        output_vcfs = germline_vcfs.mix(GATK_MUTECT2.out.vcfs)
        output_caller_vcfs = germline_caller_vcfs.mix(
            GATK_MUTECT2.out.vcfs.map { sample_id, role, sample_name, vcf -> tuple(sample_id, role, sample_name, 'MUTECT2', vcf) }
        )
        output_statuses = germline_statuses.mix(GATK_MUTECT2.out.statuses)
    } else {
        output_vcfs = germline_vcfs
        output_caller_vcfs = germline_caller_vcfs
        output_statuses = germline_statuses
    }
    status_files = output_statuses.map { sample_id, role, sample_name, log_file, status_file -> status_file }.collect()

    comparison_script = file("${projectDir}/../../helper_next/src/helper_next/core/vcf_comparison.py", checkIfExists: true)
    VCF_CALLSET_SUMMARY(output_vcfs, comparison_script)
    VCF_RUN_COMPARISON(VCF_CALLSET_SUMMARY.out.summaries.collect(), file(params.run_config), comparison_script)

    VARIANTCALLING_STEP_LOG(tool_names, status_files)
    VARIANTCALLING_ASSERT_SUCCESS(status_files, VARIANTCALLING_STEP_LOG.out.log)

    emit:
    vcfs = output_vcfs
    caller_vcfs = output_caller_vcfs
    statuses = output_statuses
    comparison_json = VCF_RUN_COMPARISON.out.statistics_json
    sample_statistics = VCF_RUN_COMPARISON.out.sample_statistics
    group_comparison = VCF_RUN_COMPARISON.out.group_comparison
    variant_presence = VCF_RUN_COMPARISON.out.variant_presence
    step_log = VARIANTCALLING_STEP_LOG.out.log
    ready = VARIANTCALLING_ASSERT_SUCCESS.out.ready
}
