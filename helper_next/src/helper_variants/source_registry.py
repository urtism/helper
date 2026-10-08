"""Read-only registry of the evidence sources currently used by the browser."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from helper_variants import (
    clinvar, gene_phenotype, gnomad_frequency, liftover, panelapp, secondary_findings,
)


REGISTRY_SCHEMA_VERSION = "1"


def catalog(gene_database=None, panelapp_database=None, clinvar_database=None,
            gnomad_frequency_database=None):
    """Return source releases and snapshot dates without making network requests."""
    gene_status = gene_phenotype.cache_status(gene_database)
    metrics = _gene_cache_metrics(gene_database or gene_status.get("database"))
    common_status = _snapshot_status(gene_status)
    synchronized_at = gene_status.get("updated_at", "")

    sources = [
        _source(
            "clinvar", "ClinVar", "Variant classifications and review status",
            "Current NCBI weekly aggregate", "on_demand",
            "https://www.ncbi.nlm.nih.gov/clinvar/",
            note="E-utilities does not expose a numbered global release; exact alleles are cached for 7 days.",
            **_clinvar_fields(clinvar_database),
        ),
        _source(
            "gencc", "GenCC", "Gene–disease validity",
            "Continuous submissions export", common_status,
            gene_status.get("source_url") or gene_phenotype.GENCC_DOWNLOAD_URL,
            data_updated_at=metrics["gencc"]["updated"],
            synchronized_at=synchronized_at,
            record_count=metrics["gencc"]["count"],
            note="Assertions are individually versioned; no single numbered database release is published in the export.",
        ),
        _source(
            "g2p", "Gene2Phenotype", "Disease mechanism and allelic requirement",
            "Full panel export snapshot", common_status,
            gene_status.get("g2p_source_url") or gene_phenotype.G2P_DOWNLOAD_URL,
            data_updated_at=metrics["g2p"]["updated"],
            synchronized_at=synchronized_at,
            record_count=metrics["g2p"]["count"],
            note="The date shown is the newest record review date in the imported snapshot.",
        ),
        _source(
            "hpo", "Human Phenotype Ontology", "Disease phenotypic features",
            "phenotype.hpoa latest snapshot", common_status,
            gene_status.get("hpo_source_url") or gene_phenotype.HPO_ANNOTATIONS_URL,
            synchronized_at=synchronized_at,
            record_count=metrics["hpo"]["count"],
            note="The current importer did not retain the upstream HPO release identifier.",
        ),
        _source(
            "clingen_dosage", "ClinGen Dosage Sensitivity", "Haploinsufficiency and triplosensitivity",
            "GRCh38 gene curation export snapshot", common_status,
            gene_status.get("clingen_dosage_source_url") or gene_phenotype.CLINGEN_DOSAGE_URL,
            data_updated_at=metrics["clingen_dosage"]["updated"],
            synchronized_at=synchronized_at,
            record_count=metrics["clingen_dosage"]["count"],
            note="The date shown is the newest evaluation date in the imported snapshot.",
        ),
        _source(
            "orphadata", "Orphadata", "ORPHA, ICD-10 and cross-reference mappings",
            "Product 1 XML snapshot", common_status,
            gene_status.get("orphadata_source_url") or gene_phenotype.ORPHADATA_URL,
            synchronized_at=synchronized_at,
            record_count=metrics["orphadata"]["count"],
            note="The current importer did not retain the upstream Orphadata release identifier.",
        ),
        _source(
            "gnomad", "gnomAD", "Gene constraint metrics",
            "v4.1.2", "on_demand", "https://gnomad.broadinstitute.org/",
            data_updated_at=metrics["gnomad"]["updated"],
            synchronized_at=metrics["gnomad"]["updated"],
            record_count=metrics["gnomad"]["count"],
            note="Constraint is retrieved per gene and cached locally for 30 days.",
        ),
        _gnomad_frequency_source(gnomad_frequency_database),
        _liftover_source(),
        _panelapp_source(panelapp_database),
        _acmg_source(),
    ]
    return {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "summary": _summary(sources),
    }


def _source(identifier, name, role, release, status, source_url, **fields):
    return {
        "id": identifier, "name": name, "role": role, "release": release,
        "data_updated_at": fields.get("data_updated_at", ""),
        "synchronized_at": fields.get("synchronized_at", ""),
        "record_count": int(fields.get("record_count") or 0),
        "status": status, "source_url": source_url,
        "note": fields.get("note", ""),
    }


def _snapshot_status(status):
    if status.get("status") != "ready":
        return "unavailable"
    return "stale" if status.get("stale") else "synchronized"


def _gene_cache_metrics(database):
    empty = {
        "gencc": {"count": 0, "updated": ""},
        "hpo": {"count": 0, "updated": ""},
        "g2p": {"count": 0, "updated": ""},
        "clingen_dosage": {"count": 0, "updated": ""},
        "orphadata": {"count": 0, "updated": ""},
        "gnomad": {"count": 0, "updated": ""},
    }
    if not database or not Path(database).is_file():
        return empty
    queries = {
        "gencc": "SELECT COUNT(*), COALESCE(MAX(submitted_run_date), '') FROM assertions",
        "hpo": "SELECT COUNT(*), '' FROM hpo_features",
        "g2p": "SELECT COUNT(*), COALESCE(MAX(last_reviewed), '') FROM g2p_records",
        "clingen_dosage": "SELECT COUNT(*), COALESCE(MAX(last_evaluated), '') FROM clingen_dosage",
        "orphadata": "SELECT COUNT(*), '' FROM disease_codes",
        "gnomad": "SELECT COUNT(*), COALESCE(MAX(updated_at), '') FROM gnomad_constraints",
    }
    try:
        with sqlite3.connect(str(database)) as connection:
            for key, query in queries.items():
                try:
                    count, updated = connection.execute(query).fetchone()
                    empty[key] = {"count": int(count or 0), "updated": str(updated or "")}
                except sqlite3.Error:
                    continue
    except sqlite3.Error:
        pass
    return empty


def _clinvar_fields(database):
    status = clinvar.cache_status(database)
    return {
        "data_updated_at": status.get("latest_record_update", ""),
        "synchronized_at": status.get("synchronized_at", ""),
        "record_count": status.get("record_count", 0),
    }


def _gnomad_frequency_source(database):
    status = gnomad_frequency.cache_status(database)
    return _source(
        "gnomad_frequency", "gnomAD genomes", "Allele frequency and locus coverage",
        "v2.1.1 (GRCh37); v4.1 (GRCh38)", "on_demand",
        gnomad_frequency.SOURCE_URL,
        synchronized_at=status.get("synchronized_at", ""),
        record_count=status.get("record_count", 0),
        note=(
            "Exact alleles are retrieved from the assembly-matched genomes dataset and cached "
            "locally. Absence is distinguished from missing data using locus coverage."
        ),
    )


def _panelapp_source(database):
    status = panelapp.cache_status(database)
    state = "unavailable"
    if status.get("status") == "ready":
        state = "stale" if status.get("stale") else "synchronized"
    return _source(
        "panelapp", "PanelApp", "Versioned diagnostic gene panels",
        "Per-panel versions in catalogue snapshot", state,
        "https://panelapp.genomicsengland.co.uk/",
        data_updated_at=status.get("latest_panel_update", ""),
        synchronized_at=status.get("synced_at", ""),
        record_count=status.get("panel_count", 0),
        note="Each panel retains its own version; the date shown is the newest panel update in the catalogue.",
    )


def _liftover_source(database=None):
    status = liftover.cache_status(database)
    return _source(
        "ncbi_variation", "NCBI Variation Services", "GRCh37/GRCh38 allele projection",
        "SPDI API v0 · fixed RefSeq assembly accessions", "on_demand",
        liftover.SOURCE_URL,
        synchronized_at=status.get("synchronized_at", ""),
        record_count=status.get("record_count", 0),
        note=(
            "Exact sequence alleles are projected and normalized on demand; successful and "
            "negative mappings are cached locally."
        ),
    )


def _acmg_source():
    versions = secondary_findings.catalog()
    current = next((item for item in versions if item.get("current")), versions[0])
    return _source(
        "acmg_sf", "ACMG Secondary Findings", "Secondary findings gene lists",
        "v{} (bundled; v3.0–v3.3 available)".format(current["version"]), "bundled",
        secondary_findings.detail(current["id"])["source_url"],
        data_updated_at=current.get("version_created", ""),
        record_count=current.get("gene_count", 0),
        note="Versioned snapshots are shipped with the application and do not require synchronization.",
    )


def _summary(sources):
    counts = {"total": len(sources)}
    for source in sources:
        status = source["status"]
        counts[status] = counts.get(status, 0) + 1
    return counts
