nextflow.enable.dsl = 2

import groovy.json.JsonSlurper

include { ALIGNMENT } from './modules/alignment'
include { PREPROCESSING } from './modules/preprocessing'


def loadJson(String path) {
    if (!path) {
        return [:]
    }
    return new JsonSlurper().parse(new File(path))
}


if (!params.manifest) {
    error 'Missing required parameter: --manifest'
}
if (!params.pipeline) {
    error 'Missing required parameter: --pipeline'
}
if (!params.tools) {
    error 'Missing required parameter: --tools'
}

pipeline_config = loadJson(params.pipeline)
tools_config = loadJson(params.tools)
run_config = loadJson(params.run_config)
workflow_steps = run_config.workflow ?: pipeline_config.workflow ?: []
reference_version = pipeline_config.reference_version ?: run_config.reference_version
reference_fasta_path = params.reference_fasta ?: run_config.reference_fasta ?: tools_config[reference_version]?.fasta

if (!reference_fasta_path && workflow_steps.contains('alignment')) {
    error 'Alignment requires --reference_fasta or a reference fasta in tools/pipeline config'
}

samples_ch = Channel
    .fromPath(params.manifest)
    .splitCsv(header: true, sep: '\t')
    .map { row -> row.collectEntries { key, value -> [key, value ?: ''] } }

reference_fasta = reference_fasta_path ?: ''

process INIT_RUN_INFRA {
    tag 'run-infrastructure'

    output:
    path "run.infrastructure.ready", emit: ready

    script:
    def step_dir_names = [
        prealignment: 'PREALIGNMENT',
        alignment: 'ALIGNMENT',
        preprocessing: 'PREPROCESSING',
        variantcalling: 'VARIANTCALLING',
        cnvcalling: 'CNVCALLING',
        postprocessing: 'POSTPROCESSING',
        variant_annotation: 'ANNOTATION',
        cnv_annotation: 'ANNOTATION',
        annotation: 'ANNOTATION',
        postannotation: 'POSTANNOTATION',
    ]
    def step_dirs = workflow_steps.collect { step -> step_dir_names[step.toString()] ?: step.toString().toUpperCase() }.unique()
    def output_dirs = step_dirs ? step_dirs.collect { "${params.outdir}/${it}" }.join(' ') : ''
    def log_dirs = step_dirs ? step_dirs.collect { "${params.outdir}/LOGS/${it}/samples" }.join(' ') : ''
    def plan_rows = workflow_steps.withIndex().collect { step, index ->
        def step_dir = step_dir_names[step.toString()] ?: step.toString().toUpperCase()
        "${index + 1}\t${step}\tplanned\t${params.outdir}/${step_dir}\t${params.outdir}/LOGS/${step_dir}"
    }.join('\n')
    """
    mkdir -p ${params.outdir} ${params.outdir}/LOGS ${params.outdir}/TMP ${params.outdir}/MANIFEST ${params.outdir}/REPORTS
    if [ -n "${output_dirs}" ]; then mkdir -p ${output_dirs}; fi
    if [ -n "${log_dirs}" ]; then mkdir -p ${log_dirs}; fi
    {
        echo "step=init"
        echo "generated=\$(date -Is)"
        echo "outdir=${params.outdir}"
        echo "workflow=${workflow_steps.join(',')}"
    } > ${params.outdir}/LOGS/run.infrastructure.log
    {
        printf "order\\tstep\\tstatus\\toutput_dir\\tlog_dir\\n"
        cat <<'HELPER_WORKFLOW_PLAN'
${plan_rows}
HELPER_WORKFLOW_PLAN
    } > ${params.outdir}/LOGS/workflow.plan.tsv
    touch run.infrastructure.ready
    """
}

workflow {
    INIT_RUN_INFRA()

    if (workflow_steps.contains('alignment')) {
        ALIGNMENT(samples_ch, pipeline_config, tools_config, reference_fasta, INIT_RUN_INFRA.out.ready)
        ALIGNMENT.out.bams.view { item -> "aligned\t${item[0]}\t${item[1]}\t${item[2]}\t${item[3]}" }
    }

    if (workflow_steps.contains('preprocessing')) {
        if (workflow_steps.contains('alignment')) {
            preprocessing_input_bams = ALIGNMENT.out.bams
        } else {
            preprocessing_input_bams = samples_ch
                .filter { row -> row.bam }
                .map { row -> tuple(row.sample_id, row.role, row.sample_name, file(row.bam), '') }
        }
        PREPROCESSING(preprocessing_input_bams, pipeline_config, tools_config, INIT_RUN_INFRA.out.ready)
        PREPROCESSING.out.bams.view { item -> "preprocessed\t${item[0]}\t${item[1]}\t${item[2]}\t${item[3]}" }
    }

    if (!workflow_steps.contains('alignment') && !workflow_steps.contains('preprocessing')) {
        samples_ch.view { row -> "manifest\t${row.sample_id}\t${row.role}\t${row.sample_name}" }
    }
}
