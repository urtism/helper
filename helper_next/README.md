# Helper Next

Il calcolatore ACMG locale implementa attualmente PVS1: [uso e limiti](../docs/HELPER_NEW_ACMG_PVS1_MVP.md).
Il pulsante **Valuta ACMG** nel dettaglio variante richiama direttamente
`POST /api/acmg-calculator/pvs1`, senza un servizio di valutazione separato.
[Audit e pulizia strutturale](../docs/HELPER_STRUCTURAL_CLEANUP.md).

Prototype for the next Helper interface.

The goal is to develop a local web app without touching the existing PyQt GUI.
It reuses the current repository resources (`configs/`, `files/`, `scripts/`,
and `bin/`) while new code lives under `helper_next/`.

The experimental variant review priority preserves full mechanism points for a
consequence-compatible LoF even when gene records span multiple disease
contexts. The zygosity/inheritance component is capped at 15 points: a
heterozygous AD call scores 10, a homozygous AR call scores 15, and a confirmed
in-trans AR compound scores 15; de novo evidence is reserved for a separate
family score. A missing population AF gets 25 points only when gnomAD confirms
absence with adequate coverage; if coverage is inadequate or unavailable, it
gets a provisional 10 positive points. Occurrence scores 15 when a variant is carried by only one sample
in a run, 10 when multiple samples from one unrelated group carry it, and -10
when more than two unrelated groups carry it; exactly two groups receive no
adjustment. Samples in the same family/analysis group count once.
ClinVar contributes up to 20 points: P and LP both score 20 with at least two
review stars, 15 with one star, and 10 with zero stars. P/LP versus VUS
conflicts retain 75% of that score; B/LB uses the same weights with a negative
sign. A conflict containing both P/LP and B/LB scores zero, as do VUS-only
and unresolved conflicts. These are review-priority weights, not ClinVar or
ACMG classification rules; disease matching does not scale this component.
Opening variant detail performs a fresh exact-allele ClinVar lookup and
uses the same evidence for both the evidence panel and the priority score.
The list reuses this evidence from the local cache, without bulk network
lookups or VCF ClinVar annotations; variants without cached evidence receive
zero ClinVar points. Cache changes invalidate the priority order, and expired
evidence is excluded (ordering is rechecked at least once a minute).

## Run

From this directory:

```bash
python -m pip install -e .
helper-next serve
```

PVS1 viene eseguito nello stesso processo Python del backend. Le fonti
biologiche esterne e le cache locali esistenti restano disponibili.
La classificazione ACMG completa e i profili di valutazione del precedente
servizio non hanno un equivalente nel calcolatore locale attuale.

Use `python -m pip` rather than plain `pip` in the `gatk43` environment. On
some workstations the `pip` command still points to Python 2.7.

Then open:

```text
http://127.0.0.1:8765
```

During early development you can also run:

```bash
uvicorn helper_next.api.app:create_app --factory --reload --port 8765
```

## Structure

- `src/helper_next/api/`: FastAPI app and HTTP routes.
- `src/helper_next/core/`: repository discovery and future pipeline services.
- `src/helper_next/web/static/`: first static frontend.
- `tests/`: future tests for API and core services.

## Migration Strategy

1. Keep the current PyQt GUI working.
2. Expose read-only project/config discovery in Helper Next.
3. Add safe builders for samplesheets and pipeline commands.
4. Add execution and log streaming after the command layer is tested.

## Nextflow Bridge

Helper Next can now generate a stable TSV manifest from the existing Helper
samplesheet JSON:

```bash
helper-next nextflow-manifest \
  --samplesheet run.samplesheet \
  --pipeline ../configs/pipelines/Germline.pipeline \
  --tools ../configs/tools_cfg/tools.cfg \
  --out work/manifest.tsv \
  --run-config work/run_config.json
```

See `../docs/NEXTFLOW_MIGRATION.md` for the initial Nextflow workflow.
