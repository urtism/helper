"""Read-only views of biological sources for the browser and local administration."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from helper_variants import gnomad_constraint

from helper_variants import (
    gene_phenotype, gnomad_frequency, liftover, panelapp, secondary_findings,
)
from helper_variants.clinvar_adapter import LocalEvidence


REGISTRY_SCHEMA_VERSION = "1"


def catalog(gene_database=None, panelapp_database=None, clinvar_database=None,
            gnomad_frequency_database=None):
    """Return source releases and snapshot dates without making network requests."""
    gene_status = gene_phenotype.cache_status(gene_database)
    metrics = _gene_cache_metrics(gene_database or gene_status.get("database"))
    common_status = _snapshot_status(gene_status)
    synchronized_at = gene_status.get("updated_at", "")

    sources = [
        _clinvar_source(clinvar_database),
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
            gnomad_constraint.status(gene_database).get("release") or "Unverified legacy release",
            "local_tsv" if gnomad_constraint.status(gene_database).get("release") else "on_demand",
            gnomad_constraint.SOURCE_URL,
            data_updated_at=metrics["gnomad"]["updated"],
            synchronized_at=metrics["gnomad"]["updated"],
            record_count=metrics["gnomad"]["count"],
            note="Transcript-specific v4.1.2 TSV import is supervised; legacy GraphQL rows have no verified release.",
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


def _clinvar_source(database):
    with LocalEvidence(database) as source:
        manifest = source.manifest
        return _source(
            "clinvar", "ClinVar Local", "Variant classifications and review status",
            source.snapshot_id or "No installed snapshot",
            "unavailable" if source.error else "synchronized",
            "https://www.ncbi.nlm.nih.gov/clinvar/",
            synchronized_at=manifest.get("installed_at") or manifest.get("imported_at", ""),
            record_count=manifest.get("counts", {}).get("variants", 0),
            note=source.error or (
                "Installed composite snapshot; local date is installation/import, not scientific release. "
                "Variant lookup and priority use no ClinVar HTTP requests."
            ),
        )


def _gnomad_frequency_source(database):
    status = gnomad_frequency.cache_status(database)
    return _source(
        "gnomad_frequency", "gnomAD frequencies", "Exomes, genomes and joint allele frequencies",
        "v4.1.1 (GRCh38)", "on_demand",
        gnomad_frequency.SOURCE_URL,
        synchronized_at=status.get("synchronized_at", ""),
        record_count=status.get("record_count", 0),
        note=(
            "Submitted VCF alleles, including projected GRCh37 inputs; no local FASTA check. Alias batches and local cache. "
            "Coverage alone does not establish an allele-specific AN or AF=0."
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


def _administrative_source(source_id, name, category, storage_type, **fields):
    result = dict(source_id=source_id, name=name, category=category, storage_type=storage_type,
                  installed=False, status="missing", version=None, snapshot_id=None,
                  last_updated=None, last_checked=None, update_available=None,
                  update_supported=False, error=None, source_url=None, details={})
    result.update(fields)
    return result


def administrative_catalog(source_id=None):
    """Local metadata only. No refresh, inferred release, FASTA scan or run access.

    Keep the browser's historical catalog contract separate from this admin view.
    Selecting a source avoids scanning unrelated caches when polling a check.
    """
    from helper_variants import clinvar_local

    sources = []
    if source_id in (None, "clinvar"):
        state = clinvar_local.installation_status()
        manifest = state.get("manifest", {})
        sources.append(_administrative_source(
            "clinvar", "ClinVar", "variants_dynamic", "SQLite locale",
            installed=state["installed"], status=state["status"], error=state["error"],
            snapshot_id=manifest.get("snapshot_id"),
            last_updated=manifest.get("installed_at") or manifest.get("imported_at"),
            update_supported=state["installed"] and state["status"] == "installed",
            source_url="https://www.ncbi.nlm.nih.gov/clinvar/",
            details=dict(state, validation=manifest.get("validation"),
                         note="Composite snapshot; import date is not an upstream scientific release.")))
    if source_id in (None, "clingen_vcep_variants"):
        from helper_variants import clingen_vcep_local
        state = clingen_vcep_local.installation_status()
        manifest = state.get("manifest", {})
        sources.append(_administrative_source(
            "clingen_vcep_variants", "ClinGen — VCEP Variant Classifications",
            "variants_dynamic", "SQLite locale",
            installed=state["installed"], status=state["status"], error=state["error"],
            snapshot_id=manifest.get("snapshot_id"),
            last_updated=manifest.get("imported_at"),
            source_url="https://erepo.clinicalgenome.org/evrepo/",
            details=dict(state, validation=manifest.get("validation"),
                         note="ERepo assertions; distinct from GenCC, Dosage and CSpec. Import date is not a scientific release.")))
    if source_id in (None, "gnomad_frequency"):
        state = gnomad_frequency.cache_status()
        sources.append(_administrative_source(
            "gnomad_frequency", "gnomAD frequencies", "variants_dynamic", "Cache SQLite",
            installed=state["status"] == "ready", status=_administrative_status(state),
            error=state.get("error"), version=", ".join(state.get("releases", [])) or None,
            last_updated=state.get("synchronized_at") or None, source_url=gnomad_frequency.SOURCE_URL,
            details=dict(state, configured_datasets=gnomad_frequency.DATASETS,
                         note="Stored releases and configured datasets are distinct; date is latest cache acquisition.")))
    if source_id is None or source_id in ("gencc", "g2p", "hpo", "clingen_dosage", "orphadata", "gnomad"):
        sources.extend(_administrative_gene_sources(source_id))
    if source_id in (None, "gene2p_mechanisms"):
        sources.append(_administrative_mechanisms())
    if source_id in (None, "gene_struct"):
        sources.append(_administrative_transcripts())
    if source_id in (None, "panelapp"):
        state = panelapp.cache_status()
        sources.append(_administrative_source(
            "panelapp", "PanelApp", "gene2p", "Cache JSON", installed=state.get("status") == "ready",
            status=_administrative_status(state), error=state.get("error"),
            last_updated=state.get("synced_at") or None, source_url="https://panelapp.genomicsengland.co.uk/",
            details=dict(state, note="Per-panel versions are retained by the PanelApp catalogue; no single global release.")))
    if source_id in (None, "ncbi_variation"):
        state = liftover.cache_status()
        sources.append(_administrative_source(
            "ncbi_variation", "NCBI Variation Services", "variants_dynamic", "Cache SQLite",
            installed=state.get("status") == "ready", status=_administrative_status(state),
            error=state.get("error"), last_updated=state.get("synchronized_at") or None,
            source_url=liftover.SOURCE_URL, details=state))
    if source_id in (None, "acmg_sf"):
        state = _acmg_source()
        sources.append(_administrative_source(
            "acmg_sf", state["name"], "gene2p", "Dataset incluso", installed=True, status="installed",
            version=state["release"], last_updated=state["data_updated_at"] or None,
            source_url=state["source_url"], details={"record_count": state["record_count"]}))
    if source_id is None or source_id.startswith("reference_") or source_id == "vep":
        sources.extend(_administrative_references_and_tools(source_id))
    return {"sources": sources, "generated_at": datetime.now(timezone.utc).isoformat()}


def _administrative_status(state):
    return {"ready": "installed", "missing": "missing"}.get(state.get("status"), "error")


def _administrative_gene_sources(selected):
    state = gene_phenotype.cache_status()
    specs = (
        ("gencc", "GenCC", "row_count", "source_url", gene_phenotype.GENCC_DOWNLOAD_URL),
        ("g2p", "Gene2Phenotype", "g2p_row_count", "g2p_source_url", gene_phenotype.G2P_DOWNLOAD_URL),
        ("hpo", "Human Phenotype Ontology", "hpo_row_count", "hpo_source_url", gene_phenotype.HPO_ANNOTATIONS_URL),
        ("clingen_dosage", "ClinGen Dosage Sensitivity", "dosage_row_count", "clingen_dosage_source_url", gene_phenotype.CLINGEN_DOSAGE_URL),
        ("orphadata", "Orphadata", "disease_code_count", "orphadata_source_url", gene_phenotype.ORPHADATA_URL),
        ("gnomad", "gnomAD gene constraints", "constraint_row_count", None, gnomad_frequency.SOURCE_URL),
    )
    results = []
    for identifier, name, count_key, url_key, url in specs:
        if selected not in (None, identifier):
            continue
        if identifier == "gnomad":
            constraint = gnomad_constraint.status()
            results.append(_administrative_source(identifier, name, "gene2p", "Cache SQLite condivisa",
                installed=constraint["status"] == "ready", status=_administrative_status(constraint),
                version=constraint.get("release"), last_updated=constraint.get("acquired_at"),
                source_url=constraint["source_url"], error=constraint.get("error"),
                details=dict(constraint, database=state.get("database"),
                             legacy_record_count=state.get(count_key),
                             note="Explicit local v4.1.2 TSV import; no automatic downloads or reconstruction.")))
            continue
        # A shared SQLite file does not prove that an optional source was imported.
        imported = (identifier == "gencc" or bool(state.get(url_key))) if url_key else bool(state.get(count_key))
        installed = state.get("status") == "ready" and imported
        status = _administrative_status(state)
        if status == "installed" and not installed:
            status = "missing"
        results.append(_administrative_source(
            identifier, name, "gene2p", "Cache SQLite condivisa", installed=installed,
            status=status, error=state.get("error"), source_url=state.get(url_key) or url,
            last_updated=(state.get("updated_at") or None) if installed and url_key else None,
            details=dict(database=state.get("database"), schema_version=state.get("schema_version"), record_count=state.get(count_key),
                         index_acquired_at=state.get("updated_at"), stale=state.get("stale"),
                         etag=state.get("etag") if identifier == "gencc" else None,
                         last_modified=state.get("last_modified") if identifier == "gencc" else None,
                         note=("ClinGen Gene–Disease assertions may be included via GenCC submitters; no separate ClinGen validity dataset is imported."
                               if identifier == "gencc" else "No upstream dataset release retained by this importer."))))
    return results


def _administrative_mechanisms():
    from helper_next.core.acmg_mechanism_store import MechanismStore
    store = MechanismStore()
    item = _administrative_source("gene2p_mechanisms", "Gene2P — disease mechanisms",
                                  "gene2p", "Cache SQLite derivata")
    try:
        state = store.statistics()
        item.update(installed=state["exists"], status="installed" if state["exists"] else "missing", details=state)
    except (OSError, sqlite3.Error, ValueError) as exc:
        item.update(status="error", error=str(exc), details={"database": str(store.path)})
    return item


def _administrative_transcripts():
    from helper_next.core.acmg_transcripts import TranscriptReferenceProvider, VERSION
    provider = TranscriptReferenceProvider()
    item = _administrative_source("gene_struct", "Gene Struct — Ensembl transcripts", "gene_struct", "Cache JSON",
                                  source_url=provider.rest_url or "https://rest.ensembl.org/")
    releases, assemblies, dates, examples = set(), set(), [], []
    count = 0
    try:
        for path in provider.cache.glob("*.json"):
            value = json.loads(path.read_text())
            key = value["key"]
            if (key.get("schema") != VERSION or key.get("assembly") not in ("GRCh37", "GRCh38")
                    or not str(key.get("release", "")).isdigit()):
                raise ValueError("Invalid transcript artifact metadata: " + path.name)
            releases.add(str(key["release"]))
            assemblies.add(key["assembly"])
            if value.get("acquired_at"):
                dates.append(value["acquired_at"])
            if len(examples) < 20:
                examples.append(key)
            count += 1
        item.update(installed=bool(count), status="installed" if count else "missing",
                    version=", ".join(sorted(releases)) or None, last_updated=max(dates) if dates else None)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        item.update(status="error", error=str(exc))
    item["details"] = dict(path=str(provider.cache), configured_release=provider.release or None,
                           assemblies=sorted(assemblies), artifact_count=count, example_keys=examples,
                           note="Cached artifact metadata; structures are validated by the existing transcript provider on use.")
    return item


def _administrative_references_and_tools(selected):
    from helper_next.core.acmg_reference import reference_record
    from helper_next.core import reference_validation
    from helper_next.core.project import get_project_paths
    from helper_variants import indexer

    # Read the same tools file used by the main Tools page, without running its audit.
    tools, config_error = {}, None
    try:
        path = get_project_paths().configs / "tools_cfg/tools.cfg"
        tools = json.loads(path.read_text())
        if not isinstance(tools, dict):
            raise ValueError("Tools configuration must be an object")
    except (OSError, ValueError, RuntimeError) as exc:
        tools = {}
        config_error = str(exc)
    results = []
    for assembly, aliases in (("GRCh37", ("GRCh37", "GRch37", "hg19")), ("GRCh38", ("GRCh38", "GRch38", "hg38"))):
        identifier = "reference_" + assembly.lower()
        if selected not in (None, identifier):
            continue
        item = _administrative_source(identifier, "Reference FASTA — " + assembly, "reference", "Reference FASTA",
                                      status="not_configured", details={"assembly": assembly})
        fasta = None
        try:
            entry = next((tools[key] for key in aliases if isinstance(tools.get(key), dict) and tools[key].get("fasta")), {})
            record = {"run_config": {"reference_fasta": entry.get("fasta"), "reference_version": entry.get("version")}}
            record, config = reference_record(assembly, record)
            configured = record.get("run_config", {}).get("reference_fasta")
            item["details"].update(path=configured, configured_sha256=config.get("sha256"), validation="unknown")
            if configured:
                item.update(status="missing", version=record["run_config"].get("reference_version"))
                item["details"]["available"] = Path(configured).expanduser().is_file()
                fasta = indexer.open_reference(record, assembly)
                if fasta is not None:
                    item.update(installed=True, status="installed")
                    state = reference_validation.reference_state(fasta)
                    version = reference_validation.reference_version(assembly, record, config)
                    receipt = reference_validation.reusable_manifest(assembly, version, state, config.get("sha256"))
                    item["details"].update(validation="verified" if receipt else "requires_validation",
                                            verified_sha256=receipt["digest"]["value"] if receipt else None,
                                            verified_at=receipt["verified_at"] if receipt else None)
                else:
                    item["details"]["note"] = "An uncompressed FASTA and its .fai are required by the local reference reader."
            elif config_error:
                item.update(status="error", error=config_error)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            item.update(status="error", error=str(exc))
        finally:
            if fasta is not None:
                fasta.close()
        results.append(item)
    if selected in (None, "vep"):
        configured = [dict(name=name, version=value.get("version"), path=value.get("path"),
                           cache_dir=value.get("cache_dir"), container=value.get("container"))
                      for name, value in tools.items() if name.upper().startswith("VEP ") and isinstance(value, dict)]
        results.append(_administrative_source(
            "vep", "VEP — annotation configuration", "annotation_tools", "Configurazione tool",
            status="error" if config_error else "configured" if configured else "not_configured",
            installed=None, error=config_error, source_url="https://www.ensembl.org/info/docs/tools/vep/",
            details=dict(configured_tools=configured,
                         note="Declared tool versions, not verified installations. Actual annotation releases and static resources remain in each run's annotation_releases.")))
    return results
