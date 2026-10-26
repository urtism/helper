# Task 23 — integration audit and delivery log

PVS1 follow-up: [adapter design and source inventory](TASK23_PVS1_ADAPTER_DESIGN.md)
(design only; no additional production mapping implemented).

Detailed offline audit: [HELPER sources and Evidence Contract](TASK23_DATA_EVIDENCE_AUDIT.md),
with [machine-readable observations](TASK23_DATA_EVIDENCE_AUDIT.json).

## Phase 0: verified sources (2026-10-23)

HELPER uses FastAPI (`helper_next/api`), plain ES modules inside the existing
variant-browser shadow DOM, and SQLite for variant indexes, source registries,
analysis history and append-only ACMG workspaces. There is no application login
or authenticated reviewer identity: this is a local application. UI state lives
in component state/localStorage; results and reviews belong in SQLite.

Run discovery and variant detail live in `api/variants.py`; `helper_variants`
provides the shared parser, ALT splitting/normalization, query/filter/table and
detail view. `external_vcf.py` already accepts VCF/VCF.gz with bounded validation,
explicit assembly and the same indexer, without submitting a Nextflow run.
`core/annotation.py` configures the existing VEP workflow/tool wrappers. There is
no verified standalone VEP annotation endpoint: unannotated input must be
annotated using that existing workflow before transcript-dependent evaluation.

Existing `acmg_client.py`, `acmg_workbench.py`, `api/acmg.py` and
`acmg-workbench.js` implement the earlier interpretation API, not Task 22's
criteria-only API. Preserve existing data and legacy results.

Engine inspected read-only at sibling `../acmg-engine`: final Task 22/22A reports,
OpenAPI, domain models, route implementations, portable schemas and PM2/PVS1
replay bundles. No engine imports or evaluators belong in HELPER production.

| Feature | Verified engine API (prefix /v1) | Contract | HELPER integration target |
| --- | --- | --- | --- |
| Evidence validation | GET /evidence-contracts/schema; POST /evidence-contracts/validate | evidence-contract-1.0; validated-evidence-context-1.0 | Adapt existing immutable snapshot; engine validation |
| Evidence requirements | POST /evidence/requirements | evidence-requirements-1.1 | Availability and progressive branch requirements |
| Criteria evaluation | POST /criteria/evaluate | criteria-matrix-1.0 | All 28 rows, exact status/strength |
| Protocol listing | No list endpoint; GET /criteria-protocols/{protocol}/{version} | ProtocolManifest; ACMG_2015/1.0.0, CLINGEN_GENERAL/1.0.0 verified | Explicit pinned versions, fetch manifests, fail closed |
| Decision tree | GET /criteria-protocols/{protocol}/{version}/trees/{criterion}; GET /criteria/executions/{id}/tree | decision-tree-1.0 | Actual execution tree; full graph and inspector |
| Execution trace | GET /criteria/executions/{id}; /nodes/{node_id}; /requirements; /replay-bundle | criterion-execution-1.0 | Persist real bundles; inspect offline after restart |
| Comparison | POST /criteria/compare; POST /criteria/executions/compare | criteria-comparison-1.0; TraceDifference | Engine comparison, no scientific inference |
| VCEP overrides | GET /criteria/tree-overrides declared, **not reachable in live REST verification** | VCEPNodeOverride | Mark catalog UNAVAILABLE; no inferred profiles |
| Review/replay | POST /criteria/reviews; POST /criteria/executions/{id}/replay | TreeManualReview; CriterionTreeExecution | Local append-only reviews and new evaluation attempts |

All Task 22 protocols are EXPERIMENTAL_NOT_CLINICALLY_APPROVED. No final
classification is available. The engine execution archive is process memory;
HELPER must save bundles to survive its restart. Identical engine inputs may
produce identical content-based execution IDs; use a distinct HELPER attempt ID
without modifying scientific evidence to manufacture engine identity.

## Incremental plan and gates

1. Existing variant → provider contract → real REST validation/evaluation →
   matrix → actual PM2/PVS1 graphs. Run focused contract and live REST checks.
2. Complete all supported criteria, requirements, graph interactions and inspector.
3. Pinned protocol comparison and explicitly scoped VCEP availability.
4. Typed corrections, separate manual review, history, before/after and exports.
5. Focused regressions/browser checks. Ask the user before computationally heavy
   suites, exhaustive path exploration or real annotation/Nextflow runs.

No new pipeline, parser, VCF viewer, scientific evaluator or production mock.

## Live API discrepancy

`GET /v1/criteria/tree-overrides` is shadowed by the earlier legacy
`GET /v1/criteria/{code}` route in the inspected engine's application factory.
It returns `CRITERION_NOT_FOUND`, despite appearing in OpenAPI. HELPER reports
the optional catalog as UNAVAILABLE, continues with the two verified base
protocols, and never claims that the registry is empty. Repair requires ordering
the engine routes correctly in its own repository; no engine modification is
included here. Explicit override references are still validated by the engine
when submitted through the API; availability/compatibility has not been verified.

## Implemented architecture

`Existing run or standalone VCF → shared helper_variants index/query → existing
variant detail → ACMG workspace → Task22 provider adapter → remote Pydantic
validation → criteria evaluation → matrix + archived replay bundles`.

`core/acmg_task22.py` is a REST/serialization boundary. It checks the live OpenAPI
request and response schemas using JSON Schema, pins provider contract and protocol
versions, and delegates semantic/scientific validation to the independent engine.
It imports no engine package. The existing client provides configurable URL,
token, finite timeout, response size bound, redirect refusal, strict JSON and a
correlation ID. Only GET requests receive one controlled retry; evaluation and
review writes are never automatically retried. Structured operational logs omit
clinical values. Provenance records HELPER correlation and engine request IDs.

The adapter reuses HELPER's existing selected-transcript evidence extraction,
local FASTA verification and gnomAD cache. Imported population and computational
values retain their original JSON, unverified provenance and explicit serializer
transformations; quality remains UNKNOWN until the engine assesses it. It never
invents AC/AN, predictor releases, transcript versions, LoF interpretation or
ClinVar-derived criterion activation. ClinVar and the original VCF source remain
inspectable in the immutable workspace. Missing reference/build/transcript
requirements block transport rather than manufacturing normalized data.

`api/acmg_task22.py` adds preflight/evaluate/compare/archive/node/review/diff/
trace-compare/export operations under `/api/acmg`. Automatic matrices are saved
before artifact retrieval. Failure to fetch a bundle returns the saved result ID
and a retry operation, without silently repeating evaluation. All 28 actual trees
and their traces are archived and tree checksums are checked against executions.
Local node inspection/export continues without contacting the engine.

`acmg-task22.js` renders inside `acmg-workbench.js`, reached from the existing
variant detail button. The legacy interpretation workspace remains accessible.
Every engine status stays distinct. Retirement is read from the selected rule,
not assumed for PP5/BP6. The matrix filters status, strength and benign/pathogenic
type. The SVG renderer draws all engine nodes/edges, executed transitions,
unvisited nodes and the terminal; it supports zoom, pan, fit, keyboard selection
and source/threshold/formula inspection. No hypothetical outcome is assigned to
SKIPPED nodes. The ordered path is the engine's execution_path, never inferred.

Protocol comparison uses `/v1/criteria/compare` and its native differences,
including first divergent node. Before/after inspection retains both original
results and evidence. Native trace comparison requires the original executions
to remain in engine memory; saved trace data stays available after restart.

Manual context is an explicit alternative when the local gene-disease cache has
no association. Manual decisions and reviewer IDs are local assertions, stored
append-only with rationale/fingerprint and separate from automatic status and
strength. A new HELPER attempt ID identifies every rerun. The initial typed form
supports population/computational observations through the live engine schema;
`corrections[].evidence` also accepts complete ProviderEvidence envelopes for the
other evidence families. Those envelopes must already satisfy Task 22's original/
transformation contract. No literature agent or evaluator is included.

Exports: `engine` is the unchanged response JSON; `audit` includes saved input,
provenance, bundles and separate reviews; `csv` is a readable criterion review
with formula-injection escaping. No final category is constructed.

## Files

- Created: `core/acmg_task22.py`, `api/acmg_task22.py`,
  `helper_variants/web/static/acmg-task22.js`, `acmg-schema-field.js`,
  `tests/test_acmg_task22.py`, `tests/test_acmg_task22_browser.py`, this document.
- Updated: `api/app.py` (router), `core/acmg_client.py` (transport),
  `acmg-workbench.js`/`.css` (existing workspace), `pyproject.toml` (jsonschema),
  `helper_next/README.md` (entry point), `tests/test_acmg_browser.py` (explicit
  legacy-engine discovery response in the existing optional browser fixture).
- No engine, Nextflow, parser, source schema or legacy PyQt changes.

## Setup

From HELPER's repository root, in separate terminals:

```bash
ACMG_ENABLE_RESEARCH_INTERPRETATION=true ../acmg-engine/.venv/bin/acmg-engine

HELPER_ACMG_AUTOSTART=0 ACMG_ENGINE_URL=http://127.0.0.1:8000 \
HELPER_ACMG_REFERENCE_CONFIG=/path/to/reference.json PYTHONPATH=helper_next/src \
python -m uvicorn helper_next.api.app:create_app --factory --host 127.0.0.1 --port 8765
```

Example reference configuration (paths must point to the actual matching FASTA
and its adjacent `.fai`; never label a different assembly as GRCh38):

```json
{"GRCh38": {"fasta": "/path/to/GRCh38.fa", "version": "your-explicit-reference-release"}}
```

Install HELPER's declared dependencies in its own environment if needed:
`python -m pip install -e helper_next`. Engine dependencies remain in its `.venv`.
The existing optional autostart also works with the sibling engine and the
existing `configs/acmg_engine.json`; Task 22 base protocols do not require those
legacy profile fixtures. Use `ACMG_ENGINE_URL`/`ACMG_ENGINE_TIMEOUT` for remote
configuration, `ACMG_ENGINE_TOKEN` for an existing authenticated proxy,
`ACMG_CRITERIA_PROTOCOL_VERSION` for an explicitly supported pinned release,
and `HELPER_ACMG_DB` to relocate the existing private SQLite archive.

Open `http://127.0.0.1:8765`, select a variant from an existing run or upload a
VCF/VCF.gz, open variant detail → Interpret with ACMG Engine, choose a curated
context or explicitly supply stable identifiers, then evaluate the selected
variant and open PM2/PVS1. No evaluation of the entire VCF is scheduled.

## Validation record and limits

- Milestone 1: six initial focused tests with real REST and the engine's exact
  PM2/PVS1 replay fixtures passed; initial Chrome graph/node smoke passed.
- Extended backend checks: 9 passed in 27.17 s, covering correction, two attempts,
  review/manual decision, native protocol/trace comparison, immutable history and
  offline audit/export. Final repeat after adding response format checks,
  engine request IDs and tree checksum verification: **9 passed in 27.31 s**.
- Extended Chrome: 1 passed in 23.60 s. One small VCF is actually uploaded and
  displayed using the existing table; context is entered via the UI, criteria
  evaluated, PM2/PVS1 graphs/nodes inspected, a review and typed correction saved,
  a second attempt executed, protocols compared and export equality checked.
- Focused regressions: 128 passed, 4 opt-in live tests skipped, in 4.17 s. Covers
  existing context/run integration, standalone/gzip/multiallelic VCF, viewer/API,
  legacy workbench, managed engine startup and new adapter. A sandbox ASGI hang
  was interrupted; the passing run was outside sandbox. Earlier development
  failures are not counted as passes.
- Python compilation, ES-module syntax and `git diff --check` passed.
- The existing optional browser test with a legacy mocked engine was adapted to
  explicitly report Task 22 as unsupported; that optional test was not rerun.
  The real Task 22 browser workflow above is the browser test actually executed.
- 389 tests collected for the ordinary HELPER suite. On 2026-10-26 the user
  explicitly chose **stop at focused tests**: the complete suite is not run.
  No real VEP/Nextflow run or exhaustive engine suite was run. Ask the user
  before computationally heavy tests.

Remaining limits: experimental/unapproved protocols, no authenticated reviewer
identity or clinical validation; unreachable VCEP catalog; no automatic
standalone VEP annotation endpoint; manual form initially covers only population
and computational types (complete validated envelopes remain accepted by API).
Unknown transcript versions require corrected source annotations. New evidence
or context can be evaluated as a new workspace/attempt; HELPER does not invent an
engine execution ID for identical inputs. Native replay is exported as an engine
bundle, not presented as a new clinical interpretation. General-vs-VCEP same-base
comparison has not been verified without a reachable registered override.
