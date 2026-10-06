# Variant analysis platform roadmap

This roadmap builds the variant viewer first on durable, testable storage. Each
milestone must leave the application usable and preserve the original VCF/GVCF
as the source of truth.

## Architectural invariants

- A run database is an immutable snapshot of what was known when the run was
  produced.
- The cohort database stores normalized observations across runs and keeps
  annotation releases side by side; reannotation never overwrites history.
- Subject, biological sample, analysis, variant, call, and annotation are
  distinct entities.
- A missing call is never interpreted as homozygous reference without callable
  region or joint-genotyping evidence.
- Variants from different reference builds are never merged implicitly.
- Every import is transactional, idempotent, traceable to its source, and safe
  to resume.

## Delivery chain

### M0 — Durable storage foundation

- [x] Define the run/cohort relational model and schema invariants.
- [x] Add versioned SQLite initialization for per-run and cohort stores.
- [x] Add stable registration primitives for runs, subjects, samples, analyses,
  normalized variants, calls, and versioned annotations.
- [x] Enable foreign keys, WAL mode, busy timeout, and idempotency constraints.
- [x] Test schema creation, isolation, duplicate handling, and annotation
  history.
- [x] Add forward-only schema migrations when schema version 2 is needed.

### M1 — Run discovery and indexing

- [x] Discover annotated VCF, postprocessed VCF, and compact TSV artifacts from
  a history record without accepting arbitrary client filesystem paths. GVCFs
  remain reserved for the later callability/joint-genotyping layer rather than
  being expanded into the interactive variant index.
- [x] Read VCF headers and sample names; recognize `ANN` and `CSQ` layouts from
  their declared headers instead of assuming a fixed column order.
- [x] Normalize multiallelic records to minimal biallelic alleles and, when the
  run's indexed FASTA is available, left-align indels and validate REF alleles.
  Record explicitly when reference validation could not be performed.
- [x] Stream records into `results/VARIANT_VIEWER/variants.sqlite` in bounded
  batches without loading the whole callset into memory.
- [x] Record source checksums, sizes, modification times, pipeline versions,
  and indexing checkpoints.
- [x] Resume interrupted indexing and reject changed inputs until explicitly
  rebuilt.
- [x] Expose indexing status and structured errors in the API.
- [x] Add synthetic SNV, indel, multiallelic, multi-transcript, and malformed
  VCF tests.

### M2 — Fast read API

- [x] Extract storage, indexing, and queries into the standalone
  `helper_variants` package; keep only history/path authorization in Helper.
- [x] Add endpoints to list indexed runs and their samples.
- [x] Add keyset-paginated variant queries with stable ordering and bounded
  page sizes.
- [x] Return a compact table projection separately from full variant detail.
- [x] Add run/sample summary counts and annotation availability.
- [x] Address runs by history identifier, never by a browser-supplied path.
- [x] Test pagination without gaps or duplicates and enforce run isolation.

### M3 — First variant viewer

- [x] Build the reusable viewer JS/CSS/templates inside `helper_variants`; expose
  host mounting hooks instead of coupling the viewer to Helper's application
  shell.
- [x] Attach the module to Helper with a thin `Variants` navigation entry and
  direct run/sample URLs.
- [x] Add run search and sample cards with role, family, panel, status, and
  counts.
- [x] Add independent sample workspaces whose state survives switching.
- [x] Render only visible rows and fetch small cursor-based pages.
- [x] Add a lazy detail drawer with transcript annotations and call metrics.
- [x] Handle missing, stale, indexing, and inaccessible run databases clearly.
- [ ] Add browser-level tests for navigation and large synthetic result sets.

### M4 — Historical runs and portability

> The manual archived-VCF workflow is parked and hidden in Helper while the
> viewer for runs produced by Helper is completed. Its host integration remains
> opt-in for later work.

- [x] Offer one-click indexing for pre-viewer runs already present in Helper's
  analysis history.
- [x] Allow users to create an archived Helper run from one or more selected
  VCF/VCF.gz files without copying the source data.
- [ ] Store a portable manifest beside databases created from Helper runs.
- [ ] Relink moved run directories using their stable identity and manifest.
- [ ] Report missing source files without losing archived metadata.

### M4.5 — Reference-build interoperability

- [ ] Register versioned, checksummed hg19/GRCh37-to-GRCh38 chain files and the
  matching GRCh38 FASTA as configurable resources with explicit provenance.
- [ ] Extend the schema to retain the original locus and a derived target-build
  locus, liftover status, failure reason, chain version, and validation state;
  never overwrite or implicitly merge the original allele.
- [ ] Implement hg19/GRCh37-to-GRCh38 liftover with reverse-strand allele
  handling, target-REF validation, and post-liftover left normalization.
- [ ] Reject and report unmapped, ambiguous, multi-mapped, REF-mismatched, and
  unsupported complex variants instead of presenting uncertain coordinates.
- [ ] Calculate and cache lifted coordinates during indexing without slowing
  interactive reads; add a resumable backfill for existing run databases.
- [ ] Expose both builds and the conversion status through the API and Variant
  Browser, linking validated GRCh38 alleles to gnomAD v4 while retaining the
  original-build gnomAD link as a fallback.
- [ ] Test SNVs, indels, reverse-strand mappings, contig aliases, PAR/sex
  chromosomes, mitochondrial variants, unmapped loci, and REF mismatches.

### M5 — Cohort publication

- [ ] Add a configurable cohort database location and health/status endpoint.
- [ ] Publish approved run observations transactionally and idempotently.
- [ ] Keep individual, biological specimen, library/aliquot, and analysis IDs
  separate so repeated samples do not inflate carrier counts.
- [ ] Store QC, coverage/callability, kit, panel, caller, pipeline, phenotype,
  consent/access metadata, and provenance.
- [ ] Support withdrawal or logical exclusion without destroying run evidence.
- [ ] Add reconciliation reports for partial or rejected publications.

### M6 — Filters and saved analysis sessions

- [ ] Add indexed filters for locus, gene, consequence, genotype, quality,
  depth, allele fraction, population frequency, and clinical evidence.
- [ ] Add deterministic sorting and reusable named filter profiles.
- [ ] Save per-user review state, notes, tags, classifications, and audit trail
  separately from pipeline output.
- [ ] Export filtered results with query, database-release, and provenance
  metadata.

### M7 — Families, cohorts, and somatic comparisons

- [ ] Resolve pedigrees from stable subject relationships.
- [ ] Implement de novo, recessive, compound-heterozygous, dominant, X-linked,
  and mitochondrial candidate queries.
- [ ] Distinguish unknown, not callable, reference, and variant genotypes.
- [ ] Add tumor-normal, longitudinal, case-control, and cross-run comparisons.
- [ ] Validate inheritance logic with joint-call/GVCF fixtures.

### M8 — Reannotation and knowledge changes

- [ ] Extract unique normalized alleles for annotation once per release.
- [ ] Register immutable annotation releases and resource versions.
- [x] Add a versioned local GenCC cache and aggregate gene–disease/phenotype
  assertions across contributing sources by HGNC gene and MONDO disease,
  retaining classification, inheritance, submitter, report link, and dates.
- [ ] Add supplemental direct adapters for HPO term expansion and sources not
  redistributed by GenCC (including licensed/configured OMIM access), without
  making interactive variant review depend on remote availability.
- [ ] Implement a ClinVar resolver that queries by Variation ID/VCV when
  available and falls back to rsID; disambiguate every result against the
  variant's reference build, chromosome, position, REF, and ALT before linking
  or importing it.
- [ ] Retrieve and normalize ClinVar classification, review status/stars,
  conditions, accessions, submitter assertions, and last-evaluated dates with
  the source release and retrieval timestamp.
- [ ] Cache ClinVar responses and explicit no-match/ambiguous-match outcomes so
  opening variant details never depends on a live remote request; provide a
  resumable refresh job with rate limiting and retry handling.
- [ ] Test exact, absent, merged, multi-record, conflicting, and build-mismatch
  ClinVar results using deterministic fixtures rather than the live service.
- [ ] Schedule resumable reannotation jobs and retain failures for retry.
- [ ] Compare original, prior, and current annotations field by field.
- [ ] Add a review queue for changed ClinVar assertions, consequences,
  transcripts, frequencies, and prioritization scores.

### M9 — Cohort statistics and production hardening

- [ ] Report distinct subjects, specimens, analyses, alleles, and callable
  non-carriers separately.
- [ ] Add internal allele frequency and stratified statistics with minimum
  group-size/privacy safeguards.
- [ ] Add PostgreSQL support behind the same repository boundary when concurrent
  writes or cohort scale outgrow SQLite.
- [ ] Add backup/restore, integrity checking, observability, authorization,
  retention, and disaster-recovery procedures.
- [ ] Benchmark ingestion and interactive queries against agreed exome/genome
  workloads before declaring the platform production-ready.
