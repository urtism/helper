# Helper Nextflow Migration

This is the first bridge between Helper JSON configuration and a Nextflow DAG.

The design keeps Helper configurable:

- samplesheets describe samples, roles, and the entry point files.
- pipeline JSON files describe enabled steps, resources, tools, and analysis mode.
- tools JSON files describe executable paths, versions, and later containers or conda environments.
- Nextflow executes the DAG selected by those JSON files.

## Generate A Manifest

From the repository root:

```bash
helper-next nextflow-manifest \
  --samplesheet /path/to/run.samplesheet \
  --pipeline configs/pipelines/Germline.pipeline \
  --tools configs/tools_cfg/tools.cfg \
  --out /path/to/work/manifest.tsv \
  --run-config /path/to/work/run_config.json
```

The command validates the selected entry step, enabled pipeline steps,
reference configuration, selected tools, and required sample file columns before
writing outputs.

The manifest is a TSV with stable columns:

```text
sample_id role sample_name fastq_r1 fastq_r2 fastq_i2 bam merged_vcf variants_tsv
```

For `case-control` and `trio` samplesheets, every biological role becomes its
own row while preserving the shared `sample_id`.

## Run The Initial Nextflow Slice

```bash
nextflow run workflows/nextflow/main.nf \
  -c workflows/nextflow/nextflow.config \
  --manifest /path/to/work/manifest.tsv \
  --pipeline configs/pipelines/Germline.pipeline \
  --tools configs/tools_cfg/tools.cfg \
  --run_config /path/to/work/run_config.json \
  --outdir /path/to/work/results \
  -profile local
```

The same real prealignment/alignment/preprocessing slice can also be submitted
from the **Analysis** tab by choosing the real Nextflow workflow. Helper writes
a run directory with:

```text
input.samplesheet.json
alignment.pipeline.json
manifest.tsv
run_config.json
nextflow.log
nextflow.trace.tsv
nextflow.command.txt
nextflow.pid
work/
results/
```

Before analytical steps start, Nextflow creates the run infrastructure. Step
directories are workflow-aware: only enabled macro-steps get output/log
directories. For a `prealignment -> alignment -> preprocessing` run, the
structure is:

```text
results/
  PREALIGNMENT/
  ALIGNMENT/
  PREPROCESSING/
  LOGS/
    PREALIGNMENT/samples/
    ALIGNMENT/samples/
    PREPROCESSING/samples/
    run.infrastructure.log
    workflow.plan.tsv
  MANIFEST/
  REPORTS/
  TMP/
```

Every step publishes its generated files under its own output directory and its
logs under `results/LOGS/<STEP>/`.
Directories for disabled steps, such as `VARIANTCALLING`, are not created.
Nextflow task work directories are kept inside `<run>/work`, so partial logs for
failed or interrupted tasks remain with the run instead of being mixed into the
repository-level work directory.

Two trace files help understand where the run is:

```text
results/LOGS/workflow.plan.tsv
nextflow.trace.tsv
```

`workflow.plan.tsv` is created at the beginning of the run and lists the Helper
workflow steps in order, with the expected output and log directories.
`nextflow.trace.tsv` is produced by Nextflow and records process-level execution
details, including process name, tag/sample, status, timing, and resource
fields. The Analysis UI reports both paths when a run is submitted.

The Analysis UI also includes a live console. After a run is submitted, the
browser polls Helper every few seconds and renders the current tail of:

```text
run matrix
results/LOGS/workflow.plan.tsv
nextflow.trace.tsv
results/LOGS/PREALIGNMENT/prealignment.step.log
results/LOGS/ALIGNMENT/alignment.step.log
results/LOGS/PREPROCESSING/preprocessing.step.log
nextflow.log
```

The run matrix summarizes each step with total/running/completed/failed/planned
job counts and lists every sample with its current state. For implemented
sample-level steps, Helper builds this view from `manifest.tsv` and the
per-sample `*.status.tsv` files. Samples without a final status are shown as
`running` while the Nextflow process is alive.

This gives a single evolving view of sample-level progress, workflow plan,
process trace, step summary, and raw Nextflow output.

This real mode requires `nextflow` in `PATH`, accessible FASTQ paths, configured
aligner paths in `configs/tools_cfg/tools.cfg`, `samtools`, and a usable indexed
reference for the selected aligner.

The Analysis tab exposes **Advanced Options** for execution details:

```text
Execution Profile: local | slurm
Queue / Partition: optional SLURM queue passed as --queue
Keep intermediate files: false by default
```

For HPC runs, start Helper from a node that can submit to the scheduler and use
a run directory on a filesystem shared by the submit node and compute nodes. The
live console continues to work as long as Helper can read the shared run
directory while Nextflow writes logs, trace files, and results.

The first implemented workflow slices are `prealignment`, `alignment`, and
`preprocessing`.

## Stabilized Real Slice Demo

The current stable real slice is:

```text
prealignment -> alignment -> preprocessing -> variantcalling
```

Each macro-step writes per-sample logs and status TSV files, then runs a
step-level success check. This keeps diagnostics available for the UI while
still stopping downstream execution when a sample fails.

A self-contained orchestration demo is available from the repository root:

```bash
scripts/run_nextflow_demo.sh /tmp/helper_next_demo
```

The demo creates tiny FASTQ inputs, a demo reference, and local wrapper tools
for FastQC, BWA, samtools, Picard, and GATK. Nextflow still executes the real
Helper workflow graph and writes the same run artifacts as a production run:

```text
/tmp/helper_next_demo/
  manifest.tsv
  run_config.json
  nextflow.trace.tsv
  work/
  results/
    PREALIGNMENT/
    ALIGNMENT/
    PREPROCESSING/
    VARIANTCALLING/
    LOGS/
```

Use this demo to verify orchestration, logging, status collection, and UI
monitoring on a machine with Nextflow installed before testing with real NGS
tool installations.

## Prealignment

Prealignment currently supports the first FASTQ QC operation:

```text
FastQC
```

It is controlled by `prealignment.workflow`:

```json
"prealignment": {
  "workflow": ["fastq_QC"],
  "threads": "1",
  "ram": "1g",
  "fastq_QC": {
    "tool": "FASTQC v.0.11.8",
    "FASTQC v.0.11.8": {"args": []}
  }
}
```

Each manifest row with paired FASTQ inputs becomes an independent FastQC task.
The prealignment step publishes FastQC reports and per-sample status files under:

```text
results/PREALIGNMENT/fastqc/
results/LOGS/PREALIGNMENT/samples/<sample>.prealignment.log
results/LOGS/PREALIGNMENT/samples/<sample>.prealignment.status.tsv
results/LOGS/PREALIGNMENT/prealignment.step.log
```

When a real run starts from a `prealignment` samplesheet, Helper now launches:

```text
prealignment -> alignment -> preprocessing
```

Alignment waits for the prealignment step log, so FastQC finishes before the
alignment tasks are submitted.

## Alignment

Alignment is driven by the `alignment.fastq_alignment.tool` value in the
pipeline JSON and currently supports `BWA`, `BOWTIE2`, and `NOVOALIGN`. The
selected tool must exist in the tools JSON and provide either `path` or
`container`.

For example:

```json
"fastq_alignment": {
  "tool": "BOWTIE2",
  "BOWTIE2": {
    "args": []
  }
}
```

Alignment is parallelized per manifest row. Each sample/role with paired FASTQ
inputs becomes an independent Nextflow task, so local runs execute as many
alignment tasks as resources allow and cluster profiles can submit them as
separate scheduler jobs.

For each sample, the alignment task runs four ordered sub-commands:

```text
aligner -> SAM
samtools view -> BAM
samtools sort -> sorted BAM
samtools index -> BAI
```

The selected aligner comes from JSON (`BWA`, `BOWTIE2`, or `NOVOALIGN`), while
SAM-to-BAM conversion, sorting, and indexing are handled by `SAMTOOLS` from the
tools configuration.

By default, intermediate `SAM` and unsorted `BAM` files are removed at the end of
each sample task. The Analysis UI exposes a troubleshooting flag, disabled by
default, that launches Nextflow with:

```text
--keep_intermediates true
```

When enabled, intermediate files are published under:

```text
results/ALIGNMENT/intermediates/<sample>.sam
results/ALIGNMENT/intermediates/<sample>.unsorted.bam
```

Alignment logs are written at two levels:

```text
results/LOGS/ALIGNMENT/samples/<sample>.alignment.log
results/LOGS/ALIGNMENT/samples/<sample>.alignment.status.tsv
results/LOGS/ALIGNMENT/alignment.step.log
```

The sample log captures metadata, the aligner command, the samtools view/sort
commands, the index command, tool stderr/stdout, and the final outcome for
troubleshooting. The sample status TSV captures the step, tool, sample
identifiers, final status, exit code, start time, and completion time.

The step log is intentionally compact. It records which step/tool ran, how many
samples completed or failed, and a per-sample status table. Detailed tool output
stays in the sample logs.

## Preprocessing

Preprocessing is split into independent Nextflow processes, controlled by the
`preprocessing.workflow` array. The implemented slice supports:

```text
AddOrReplaceReadGroups
MarkDuplicates
GATK3 RealignerTargetCreator + IndelRealigner
GATK3 BaseRecalibrator + PrintReads
```

The complete preprocessing domain model also includes `filter_bam` and
`merge_UMI`; those modules are shown in the UI as pending until their Nextflow
processes are implemented.

The enabled operations come from JSON:

```json
"preprocessing": {
  "workflow": ["add_readgroups", "mark_pcr_dup", "indel_realignment", "BQ_recalibration"],
  "threads": "2",
  "ram": "8g",
  "add_readgroups": {
    "tool": "PICARD v.2.7.1",
    "PICARD v.2.7.1": {"args": []}
  },
  "mark_pcr_dup": {
    "tool": "PICARD v.2.7.1",
    "PICARD v.2.7.1": {"args": []}
  },
  "indel_realignment": {
    "tool": "GATK v.3.7",
    "GATK v.3.7": {"args": [], "mills": "mills"}
  },
  "BQ_recalibration": {
    "tool": "GATK v.3.7",
    "GATK v.3.7": {"args": [], "dbsnp": "dbsnp", "mills": "mills"}
  }
}
```

Only the operations listed in `preprocessing.workflow` are executed. For
example, `["mark_pcr_dup"]` skips `AddOrReplaceReadGroups` entirely, while
`["add_readgroups", "mark_pcr_dup"]` chains both operations before finalizing
the preprocessed BAM.

Finalization is mandatory and silent: the last BAM emitted by the selected
preprocessing substeps is always copied to `<sample>.preprocessed.bam` and
indexed with samtools. It is not exposed as a selectable workflow substep.

When a run starts from FASTQ, preprocessing consumes the BAMs emitted by
alignment. When a run starts from a BAM samplesheet, preprocessing consumes the
manifest BAMs directly.

Preprocessing outputs are published under:

```text
results/PREPROCESSING/<sample>.preprocessed.bam
results/PREPROCESSING/<sample>.preprocessed.bam.bai
results/LOGS/PREPROCESSING/samples/<sample>.preprocessing.log
results/LOGS/PREPROCESSING/samples/<sample>.preprocessing.status.tsv
results/LOGS/PREPROCESSING/preprocessing.step.log
```

The sample `preprocessing.log` is cumulative for the macro-step. It contains
sections for the enabled sub-steps, such as `add_readgroups` and
`mark_pcr_dup`, plus the implicit finalization block, but only one sample log is
published for the preprocessing macro-step. The final
`preprocessing.status.tsv` captures the overall sample status for the
preprocessing step and feeds the live console run matrix.

The live console run matrix reports `prealignment`, `alignment`,
`preprocessing`, and `variantcalling` when those steps are enabled.

## Variant Calling

`Variant Calling` is the macro-step. Its domain substeps are:

```text
Short Variants
CNV Calling
SV Calling
```

The first implemented Nextflow slice is the `Short Variants` substep and
currently supports:

```text
GATK v.4.1 HaplotypeCaller
```

This is intentionally narrow. If a pipeline JSON lists multiple variant callers,
the current Nextflow slice selects the configured GATK tool and ignores the other
callers until their modules are implemented.

It is controlled by `variantcalling.tools`:

```json
"variantcalling": {
  "tools": ["GATK v.4.3"],
  "threads": "2",
  "ram": "8g",
  "filters": {},
  "GATK v.4.3": {"args": []},
  "samples_org": "single-sample"
}
```

Each manifest row with a BAM input becomes an independent HaplotypeCaller task.
When run after preprocessing, Nextflow passes the preprocessed BAM channel
directly into variant calling. The task emits a per-sample gVCF:

```text
results/VARIANTCALLING/<sample>.GATK.g.vcf
results/LOGS/VARIANTCALLING/samples/<sample>.variantcalling.log
results/LOGS/VARIANTCALLING/samples/<sample>.variantcalling.status.tsv
results/LOGS/VARIANTCALLING/variantcalling.step.log
```

The first variant calling slice does not yet implement cohort joint genotyping,
trio logic, somatic Mutect2, or secondary callers such as FreeBayes.

## Postprocessing

The first implemented postprocessing slice supports:

```text
vcf_norm
vcf_filter
vcf_to_tsv
```

`vcf_to_tsv` is implemented directly in the Nextflow process as a compact core
field export. `vcf_norm` uses `BCFTOOLS` when selected, and `vcf_filter` either
uses a configured GATK `VariantFiltration` command or passes the current VCF
through when no filter tool is configured.

When run after variant calling, postprocessing consumes the VCF channel emitted
by `GATK_HAPLOTYPECALLER`. It can also start from a postprocessing samplesheet
with VCF inputs.

Outputs are published under:

```text
results/POSTPROCESSING/<sample>.postprocessed.vcf
results/POSTPROCESSING/<sample>.variants.tsv
results/LOGS/POSTPROCESSING/samples/<sample>.postprocessing.log
results/LOGS/POSTPROCESSING/samples/<sample>.postprocessing.status.tsv
results/LOGS/POSTPROCESSING/postprocessing.step.log
```

## Next Steps

1. Add optional prealignment modules: adapter trimming and FASTQ filtering.
2. Add optional preprocessing modules: BAM filtering, indel realignment, and BQSR.
3. Extend variant calling with explicit barriers for single-sample, cohort, trio,
   and somatic case-control designs.
4. Add variant annotation and postannotation modules.
5. Add container fields to tools config and map them into Nextflow profiles.
