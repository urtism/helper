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

The manifest is a TSV with stable columns. Schema v2 adds analysis and pedigree
metadata while retaining the original `sample_id`, `role`, and file columns:

```text
sample_id role sample_name analysis_id analysis_type relationship individual_id sex father mother affected control_relationship specimen_type tumor_purity twin_group fastq_r1 fastq_r2 fastq_i2 bam merged_vcf variants_tsv
```

For `case-control` and `trio` samplesheets, every biological role becomes its
own row while preserving the shared `sample_id`.

Schema v2 samplesheets use `sample_organization: mixed` and an
`analysis_groups` list. Germline samples are called independently. GATK and
DeepVariant retain one GVCF per sample for storage while their per-sample VCFs
feed downstream processing and within-run comparisons. Tumor-normal pairs are
excluded from germline calling and processed independently with GATK Mutect2
followed by FilterMutectCalls. Family, phenotype, pedigree, control, and
specimen metadata remain in the manifest and run configuration for comparative
interpretation.

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

The implemented workflow can also be submitted from the **Analysis** tab by
choosing the real Nextflow workflow. Helper writes a run directory with:

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
results/LOGS/VARIANTCALLING/variantcalling.step.log
results/LOGS/POSTPROCESSING/postprocessing.step.log
results/LOGS/ANNOTATION/annotation.step.log
nextflow.log
```

The run matrix summarizes each step with total/running/completed/failed/planned
job counts and lists every sample with its current state. For implemented
sample-level steps, Helper builds this view from `manifest.tsv` and the
per-sample `*.status.tsv` files. Samples without a final status are shown as
`running` while the Nextflow process is alive.

This gives a single evolving view of sample-level progress, workflow plan,
process trace, step summary, and raw Nextflow output.

This real mode requires `nextflow` in `PATH`, accessible input files, a usable
reference, and every selected tool configured with an executable path or
container in `configs/tools_cfg/tools.cfg`.

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

The implemented linear DAG currently covers:

```text
prealignment -> alignment -> preprocessing -> variantcalling -> postprocessing -> annotation
```

Each run can start from the file type required by any implemented entry step;
for example, FASTQ for alignment, BAM for preprocessing or variant calling, and
VCF for postprocessing or annotation.

## Stabilized Real Slice Demo

The current wrapper-backed orchestration demo covers:

```text
prealignment -> alignment -> preprocessing -> variantcalling -> postprocessing
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
    POSTPROCESSING/
    LOGS/
```

Use this demo to verify orchestration, logging, status collection, and UI
monitoring on a machine with Nextflow installed before testing with real NGS
tool installations. It uses local wrapper executables rather than performing a
biological validation of the tools or their output.

## Prealignment

Prealignment supports adapter trimming followed by FASTQ QC:

```text
Cutadapt or SurecallTrimmer -> FastQC
```

It is controlled by `prealignment.workflow`:

```json
"prealignment": {
  "workflow": ["trim_adapters", "fastq_QC"],
  "threads": "1",
  "ram": "1g",
  "trim_adapters": {
    "tool": "CUTADAPT",
    "adapter1": "CTGTCTCTTATACACATCT",
    "adapter2": "CTGTCTCTTATACACATCT",
    "CUTADAPT": {"args": []}
  },
  "fastq_QC": {
    "tool": "FASTQC v.0.11.8",
    "FASTQC v.0.11.8": {"args": []}
  }
}
```

Each manifest row with paired FASTQ inputs becomes an independent trimming task.
If `fastq_QC` is also enabled, FastQC reads the trimmed pair; alignment always
receives the trimmed pair when `trim_adapters` is enabled. SurecallTrimmer uses
the JAR path and JVM RAM from `tools.cfg`, and takes its library-mode arguments
(for example `-hs`, `-xt`, or `-qxt`) from the selected pipeline.

The prealignment step publishes deterministic trimmed FASTQs, FastQC reports,
and operation-specific status files under:

```text
results/PREALIGNMENT/trimmed/<sample>.R1.trim.fastq.gz
results/PREALIGNMENT/trimmed/<sample>.R2.trim.fastq.gz
results/PREALIGNMENT/fastqc/
results/LOGS/PREALIGNMENT/samples/<sample>.<operation>.prealignment.log
results/LOGS/PREALIGNMENT/samples/<sample>.<operation>.prealignment.status.tsv
results/LOGS/PREALIGNMENT/prealignment.step.log
```

When a configured run starts from a `prealignment` samplesheet, Helper can
launch the complete selected downstream sequence, for example:

```text
prealignment -> alignment -> preprocessing -> variantcalling -> postprocessing -> annotation
```

Alignment waits for the prealignment success check, so every enabled trimming
and FastQC task must finish successfully before alignment is submitted.

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
`preprocessing`, `variantcalling`, `postprocessing`, and `annotation` when
those steps are enabled.

## Variant Calling

`Variant Calling` is the macro-step. Its domain substeps are:

```text
Short Variants
CNV Calling
SV Calling
```

The implemented Nextflow slice is `Short Variants` and currently supports:

```text
GATK 4 HaplotypeCaller + CombineGVCFs + GenotypeGVCFs
GATK 4 Mutect2 + FilterMutectCalls
DeepVariant
FreeBayes
```

One caller family is executed per run. When more than one supported caller is
listed, selection priority is GATK, then DeepVariant, then FreeBayes. Other
short-variant callers are not part of the current Nextflow slice.

It is controlled by `variantcalling.tools`:

```json
"variantcalling": {
  "tools": ["GATK v.4.3"],
  "threads": "2",
  "ram": "8g",
  "filters": {},
  "GATK v.4.3": {"args": []},
  "joint_args": [],
  "mutect2_args": [],
  "mutect2_filter_args": [],
  "samples_org": "single-sample"
}
```

For legacy samplesheets, `samples_org` and `sample_organization` retain the
existing single-sample, cohort, trio, and case-control behavior. Grouped legacy
modes may still perform joint genotyping. DeepVariant remains per-sample and
FreeBayes remains VCF-only because it does not emit a reference-confidence
GVCF.

For schema v2 samplesheets, the run is split into two independent calling
branches:

```text
germline members -> selected caller -> one VCF per sample
tumor-normal pair -> Mutect2 -> FilterMutectCalls -> one filtered VCF per pair
```

Family, case-control, and only-case members are always processed independently;
their VCFs are compared only after calling. Samples with `tumor` or `normal`
roles are excluded from the germline caller.

Tumor-normal groups require exactly one tumor and one matched normal with a
shared `individual_id`. DeepVariant and FreeBayes may be selected for the
germline samples, but a schema v2 run containing tumor-normal analyses also
requires a configured GATK 4 installation for Mutect2.

After calling, Helper compares PASS variants emitted in the VCFs and produces
run-wide occurrence statistics plus analysis-specific summaries:

```text
family       -> overlap with father, mother, both parents, and other relatives
case-control -> shared, case-only, control-only, and Jaccard similarity
only cases   -> variants unique to or shared within the run
tumor-normal -> summary of the paired somatic callset
```

These comparisons do not interpret absence from a single-sample VCF as proof
of a homozygous-reference genotype. The stored GVCFs remain available if a
future reference-confidence or joint-genotyping analysis is needed.

Representative outputs are:

```text
results/VARIANTCALLING/<sample>.GATK.vcf
results/VARIANTCALLING/<sample>.DeepVariant.vcf
results/VARIANTCALLING/GVCF/<sample>.GATK.g.vcf.gz
results/VARIANTCALLING/GVCF/<sample>.GATK.g.vcf.gz.tbi
results/VARIANTCALLING/GVCF/<sample>.DeepVariant.g.vcf.gz
results/VARIANTCALLING/GVCF/<sample>.DeepVariant.g.vcf.gz.tbi
results/VARIANTCALLING/<analysis_id>.tumor_normal.Mutect2.vcf
results/REPORTS/VARIANTCALLING/run.vcf_statistics.json
results/REPORTS/VARIANTCALLING/run.sample_statistics.tsv
results/REPORTS/VARIANTCALLING/run.group_comparison.tsv
results/REPORTS/VARIANTCALLING/run.variant_presence.tsv
results/LOGS/VARIANTCALLING/samples/<sample>.variantcalling.log
results/LOGS/VARIANTCALLING/samples/<sample>.variantcalling.status.tsv
results/LOGS/VARIANTCALLING/variantcalling.step.log
```

The comparison report describes VCF overlap. It does not yet perform
reference-confidence inheritance filtering, validated de novo prioritization,
or pedigree visualization.

## Postprocessing

The first implemented postprocessing slice supports:

```text
vcf_norm
vcf_filter
vcf_to_tsv
```

`vcf_to_tsv` is implemented directly in the Nextflow process as a compact core
field export. `vcf_norm` uses `BCFTOOLS` when selected: it first splits and
left-aligns multiallelic records, then removes duplicate normalized alleles
(including duplicates produced by overlapping target intervals). `vcf_filter`
either uses a configured GATK `VariantFiltration` command or passes the current
VCF through when no filter tool is configured.

When run after variant calling, postprocessing consumes every VCF emitted by
the selected branch: the run-wide germline VCF and each filtered tumor-normal
VCF. It can also start from a postprocessing samplesheet with VCF inputs.

Outputs are published under:

```text
results/POSTPROCESSING/<sample>.postprocessed.vcf
results/POSTPROCESSING/<sample>.variants.tsv
results/LOGS/POSTPROCESSING/samples/<sample>.postprocessing.log
results/LOGS/POSTPROCESSING/samples/<sample>.postprocessing.status.tsv
results/LOGS/POSTPROCESSING/postprocessing.step.log
```

## Annotation

The implemented annotation slice supports:

```text
VEP annotation
annotated VCF to compact TSV export
```

It consumes postprocessed VCFs when postprocessing is enabled, consumes variant
calling VCFs directly when it is not, or starts from VCFs provided by an
annotation samplesheet. Reference, target BED, gene list, and transcript list
assets are resolved from the run and panel configuration.

Outputs are published under:

```text
results/ANNOTATION/<sample>.annotated.vcf
results/ANNOTATION/<sample>.annotated.tsv
results/LOGS/ANNOTATION/samples/<sample>.annotation.log
results/LOGS/ANNOTATION/samples/<sample>.annotation.status.tsv
results/LOGS/ANNOTATION/annotation.step.log
```

## Current Validation Level

- Python validation, samplesheet round trips, manifest generation, run
  configuration, submission, and monitoring are covered by automated tests.
- The schema v2 mixed calling graph has been compiled with Nextflow `-preview`,
  including single-sample germline calling and the tumor-normal branch.
- The VCF summary and aggregation processes have been executed with synthetic
  case-control VCFs and their published reports verified.
- The wrapper-backed demo exercises the legacy linear graph through
  postprocessing when run manually.
- A complete schema v2 run has not yet been executed with real BAMs and real
  GATK tools. Postprocessing and VEP have not yet been validated end-to-end on
  mixed germline and tumor-normal outputs.
- CNV calling, SV calling, and postannotation are not connected to the current
  Nextflow DAG.

## Next Steps

1. Execute an end-to-end schema v2 test matrix covering only-case, family,
   case-control, tumor-normal, and a run containing all four analysis types.
2. Verify propagation of per-sample germline VCFs and tumor-normal VCFs through
   postprocessing and VEP.
3. Add explicit pedigree/PED export and downstream segregation or inheritance
   analysis using the family metadata.
4. Extend the somatic branch with explicit configuration for germline resources,
   panel of normals, contamination estimation, and orientation-bias filtering.
5. Add pending prealignment and preprocessing operations such as FASTQ
   filtering, BAM filtering, and UMI merging.
6. Implement CNV calling, SV calling, and postannotation modules.
7. Complete and validate container/runtime mapping for local and HPC profiles.

### Persistent analysis history

Helper Next now archives each new analysis attempt in SQLite before launching
Nextflow. The **Analysis History** page searches runs and samples, displays the
resolved pipeline/substeps, panel, tools, sample sheet, execution settings and
recorded sample/step progress, and exports the archived metadata as JSON.
Background monitoring saves status and recent log tails independently of whether
the browser is open. Monitoring is recovered when the API starts again. If the
API was stopped and the working directory disappeared before a final status was
saved, the outcome may be unknown; saved metadata remains available.

The database defaults to `$XDG_DATA_HOME/helper_next/analysis_history.sqlite3`
(or `~/.local/share/helper_next/analysis_history.sqlite3`). Set
`HELPER_ANALYSIS_HISTORY_DB` to choose another persistent location outside run
directories, and include this file in backups. The history endpoints read the
archive rather than reconstructing records from old working directories. Runs
made before this feature are not automatically imported.

**Reanalyse** creates a new run with a link to its original attempt, using archived
sample sheet, resolved pipeline, tool configuration and panel settings. Original
input data and referenced resources must still exist; these large files and the
workflow source/tool binaries are not copied into the archive. **Resume from
cache** requires the original working directory and Nextflow cache and applies to
the most recent attempt for that directory. Every launch also writes
`input.tools.json` in the run directory and passes that tool snapshot to Nextflow.
Deleting a workdir therefore preserves history and reanalysis settings, but
removes its cached execution/results.

**Restart from step** also keeps the original run directory and uses `-resume`,
but builds the execution graph from the selected step onward. The selected step
reads the published result of the preceding step (or the original samplesheet
input when it is already the analysis entry step), so earlier modules are not
instantiated and cannot be rerun. A new restart token changes the task hashes of
the selected and downstream steps without deleting cache entries. Their
replacement outputs are published in the same result directories. The selected
step, effective downstream-step list, and token are recorded in
`nextflow.command.txt` and in the history record; a subsequent normal resume of
that attempt preserves the same restart graph and token.
