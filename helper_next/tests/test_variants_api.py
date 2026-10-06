from fastapi import HTTPException
from pathlib import Path
import pytest

from helper_next.api import variants
from helper_next.api import samplesheet
from helper_next.api.app import create_app
from helper_next.core import analysis_history as history
from helper_variants import clinvar
from helper_variants import gene_phenotype
from helper_variants import indexer as variant_indexer


class CapturingBackgroundTasks:
    def __init__(self):
        self.task = None
        self.args = None

    def add_task(self, task, *args):
        self.task = task
        self.args = args


def archived_run(tmp_path, run_name="RUN-API", position=10):
    run_dir = tmp_path / run_name
    annotation = run_dir / "results" / "ANNOTATION"
    annotation.mkdir(parents=True)
    (annotation / "S1.annotated.vcf").write_text(
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\n"
        "1\t{}\t.\tA\tG\t50\tPASS\t.\tGT:DP\t0/1:30\n".format(position)
    )
    return history.create({
        "run_id": run_name, "run_dir": str(run_dir), "status": "completed",
        "samples": [{
            "sample_name": "S1", "sample_id": "FAM-01", "analysis_id": "FAM-01",
            "analysis_type": "family", "relationship": "proband", "role": "proband",
            "sex": "female", "father": "FATHER", "mother": "MOTHER",
            "affected": "affected", "specimen_type": "blood",
        }],
        "request": {"gene_panel_design": "Panel A", "pipeline_path": "/pipelines/PIPE-1.pipeline"},
        "pipeline_config": {
            "id": "PIPE-1", "workflow": ["alignment"],
            "resolved_tools": {"alignment": {
                "fastq_alignment": {"tool": "BWA", "version": "0.7.17"},
                "samtools": {"tool": "SAMTOOLS", "version": "1.20"},
            }},
        },
        "tools_config": {"BWA": {"version": "0.7.17"}, "SAMTOOLS": {"version": "1.20"}},
        "run_config": {"reference_version": "GRCh38"},
    })


def test_variant_routes_are_registered():
    paths = {route.path for route in create_app().routes}
    assert "/api/variants/runs" in paths
    assert "/api/variants/runs/{identifier}/index" in paths
    assert "/api/variants/runs/{identifier}/index-status" in paths
    assert "/api/variants/runs/{identifier}/samples" in paths
    assert "/api/variants/runs/{identifier}/tools" in paths
    assert "/api/variants/runs/{identifier}/samples/{sample_id}/variants" in paths
    assert "/api/variants/runs/{identifier}/samples/{sample_id}/variants/{variant_id}" in paths
    assert "/api/variants/runs/{identifier}/samples/{sample_id}/variants/{variant_id}/carriers" in paths
    assert "/api/variants/archived-runs" in paths
    assert "/api/variants/knowledge/gene-phenotypes/{gene}" in paths
    assert "/api/variants/knowledge/gene-phenotypes/refresh" in paths
    assert "/api/variants/knowledge/gene-panels" in paths
    assert "/api/variants/knowledge/gene-panels/sync" in paths
    assert "/api/variants/knowledge/gene-panels/{source}/{identifier}" in paths


def test_missing_gene_phenotype_cache_is_refreshed_in_background(monkeypatch):
    background = CapturingBackgroundTasks()
    monkeypatch.setattr(gene_phenotype, "query_gene", lambda gene, hgnc: {
        "gene": gene, "hgnc_id": hgnc, "associations": [],
        "cache": {"status": "missing", "refreshing": False},
    })
    monkeypatch.setattr(gene_phenotype, "begin_refresh", lambda: True)

    result = variants.gene_phenotypes("SKI", background, "HGNC:10896")

    assert result["cache"]["refreshing"] is True
    assert background.task is variants._refresh_gene_phenotype_cache


def test_missing_gnomad_constraint_is_refreshed_in_background(monkeypatch):
    background = CapturingBackgroundTasks()
    monkeypatch.setattr(gene_phenotype, "query_gene", lambda gene, hgnc: {
        "gene": gene, "hgnc_id": hgnc, "associations": [],
        "gene_constraint": {"status": "missing", "refreshing": False},
        "cache": {"status": "ready", "stale": False},
    })
    monkeypatch.setattr(gene_phenotype, "begin_constraint_refresh", lambda gene: True)

    result = variants.gene_phenotypes("SKI", background, "HGNC:10896")

    assert result["gene_constraint"]["refreshing"] is True
    assert background.task is variants._refresh_gene_constraint
    assert background.args == ("SKI",)


def test_add_archived_run_links_multiple_selected_vcfs_and_indexes_them(tmp_path):
    sources = []
    for sample, position in (("OLD-1", 42), ("OLD-2", 43)):
        source = tmp_path / "{}.vep.vcf".format(sample)
        source.write_text(
            "##fileformat=VCFv4.2\n"
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t{}\n"
            "1\t{}\t.\tA\tG\t60\tPASS\t.\tGT:DP\t0/1:31\n".format(sample, position)
        )
        sources.append(str(source))
    picker_id = "archived-run-picker"
    samplesheet.save_picker_selection(
        picker_id, samplesheet.PickerSelectionRequest(files=sources)
    )
    background = CapturingBackgroundTasks()

    response = variants.add_archived_variant_run(
        variants.ArchivedRunRequest(
            picker_id=picker_id, name="Old run", reference_build="GRCh37", panel="Panel A"
        ),
        background,
    )
    assert response["status"] == "indexing"
    assert response["artifacts"] == 2
    record = history.get(response["history_id"])
    assert record["status"] == "imported"
    assert all(Path(item["linked_path"]).is_symlink() for item in record["variant_sources"])

    background.task(*background.args)
    assert variants.variant_index_status(record["id"])["status"] == "complete"
    sample_names = {
        item["display_name"] for item in variants.variant_samples(record["id"])["samples"]
    }
    assert sample_names == {"OLD-1", "OLD-2"}


def test_api_indexes_only_a_run_resolved_from_history(tmp_path):
    record = archived_run(tmp_path)
    background = CapturingBackgroundTasks()

    response = variants.start_variant_index(record["id"], background)
    assert response["status"] == "indexing"
    assert response["artifacts"] == 1
    background.task(*background.args)

    status = variants.variant_index_status(record["id"])
    assert status["status"] == "complete"
    assert status["run_id"] == "RUN-API"
    assert status["sources"][0]["records_processed"] == 1
    assert variant_indexer.index_path(record["run_dir"]).is_file()

    run_list = variants.indexed_variant_runs()
    assert run_list["runs"][0]["summary"]["variant_count"] == 1
    samples = variants.variant_samples(record["id"])
    assert samples["run"] == {
        "history_id": record["id"], "run_id": "RUN-API", "status": "completed",
        "created_at": record["created_at"], "reference_build": "GRCh38",
        "panel": "Panel A", "pipeline": "PIPE-1", "sample_count": 1,
    }
    assert samples["samples"][0]["metadata"]["analysis_id"] == "FAM-01"
    sample_id = samples["samples"][0]["sample_id"]
    page = variants.sample_variants(record["id"], sample_id, limit=100)
    assert len(page["items"]) == 1
    detail = variants.sample_variant_detail(
        record["id"], sample_id, page["items"][0]["variant_id"]
    )
    assert detail["calls"][0]["depth"] == 30

    tools = variants.variant_run_tools(record["id"])
    assert tools["pipeline"] == "PIPE-1"
    assert [(tool["name"], tool["version"]) for tool in tools["tools"]] == [
        ("BWA", "0.7.17"), ("SAMTOOLS", "1.20"),
    ]


def test_api_rejects_unknown_history_identifier():
    with pytest.raises(HTTPException) as error:
        variants.variant_index_status("unknown")
    assert error.value.status_code == 404


def test_variant_detail_enriches_incomplete_vep_clinvar_evidence(monkeypatch):
    detail = {
        "reference_build": "GRCh37", "chromosome": "1", "position": 2160661,
        "reference": "C", "alternate": "T", "database_ids": {"dbsnp": ["rs149898447"]},
        "clinvar_evidence": {
            "status": "available", "classifications": ["Benign"],
            "identifiers": [], "review_statuses": [],
        },
    }
    monkeypatch.setattr(variants, "_entry", lambda identifier: {"database": Path("index")})
    monkeypatch.setattr(variants, "_entry_database", lambda entry: entry["database"])
    monkeypatch.setattr(variants.variant_query, "variant_detail", lambda *args: detail)
    monkeypatch.setattr(clinvar, "lookup_variant", lambda *args: {
        "status": "available", "identifiers": ["139111"],
        "classifications": ["Benign/Likely benign"],
        "review_statuses": [{
            "label": "criteria provided, multiple submitters, no conflicts", "stars": 2,
        }],
    })

    result = variants.sample_variant_detail("RUN", 1, 99)

    assert result["clinvar_evidence"]["classifications"] == ["Benign/Likely benign"]
    assert result["clinvar_evidence"]["review_statuses"][0]["stars"] == 2
    assert result["clinvar_evidence"]["retrieval_status"] == "available"


def test_panelapp_knowledge_routes_delegate_to_client(monkeypatch):
    monkeypatch.setattr(variants.panelapp, "search_panels", lambda query, limit: {
        "query": query, "panels": [{"id": 7}], "limit": limit,
    })
    monkeypatch.setattr(variants.panelapp, "panel_detail", lambda panel_id, version: {
        "id": panel_id, "version": version, "genes": {"green": ["GENE1"]},
    })

    assert variants.panelapp_panels("ataxia", 5)["panels"] == [{"id": 7}]
    assert variants.panelapp_panel(7, "2.1")["genes"]["green"] == ["GENE1"]


def test_combined_gene_panel_catalog_includes_acmg_versions_when_panelapp_is_offline(monkeypatch):
    monkeypatch.setattr(
        variants.panelapp, "list_panels",
        lambda: (_ for _ in ()).throw(variants.panelapp.PanelAppError("offline")),
    )

    result = variants.gene_panel_catalog()

    assert result["panelapp_count"] == 0
    assert result["sf_count"] == 4
    assert result["panels"][0]["name"] == "ACMG Secondary Findings v3.3"
    assert result["warning"] == "offline"


def test_api_reports_missing_artifacts_without_starting_a_task(tmp_path):
    run_dir = tmp_path / "empty-run"
    run_dir.mkdir()
    record = history.create({"run_id": "EMPTY", "run_dir": str(run_dir), "samples": []})
    background = CapturingBackgroundTasks()

    with pytest.raises(HTTPException) as error:
        variants.start_variant_index(record["id"], background)
    assert error.value.status_code == 409
    assert background.task is None


def test_history_identifier_keeps_run_databases_isolated(tmp_path):
    first = archived_run(tmp_path, "RUN-A", 10)
    second = archived_run(tmp_path, "RUN-B", 99)
    for record in (first, second):
        background = CapturingBackgroundTasks()
        variants.start_variant_index(record["id"], background)
        background.task(*background.args)

    first_sample = variants.variant_samples(first["id"])["samples"][0]["sample_id"]
    second_sample = variants.variant_samples(second["id"])["samples"][0]["sample_id"]
    first_page = variants.sample_variants(first["id"], first_sample, limit=100)
    second_page = variants.sample_variants(second["id"], second_sample, limit=100)

    assert first_page["items"][0]["position"] == 10
    assert second_page["items"][0]["position"] == 99


def test_variant_carriers_include_other_indexed_runs(tmp_path):
    first = archived_run(tmp_path, "RUN-CARRIER-A", 42)
    second = archived_run(tmp_path, "RUN-CARRIER-B", 42)
    for record in (first, second):
        background = CapturingBackgroundTasks()
        variants.start_variant_index(record["id"], background)
        background.task(*background.args)

    sample_id = variants.variant_samples(first["id"])["samples"][0]["sample_id"]
    variant_id = variants.sample_variants(first["id"], sample_id, limit=10)["items"][0]["variant_id"]
    carriers = variants.sample_variant_carriers(first["id"], sample_id, variant_id)

    assert carriers["same_run"][0]["display_name"] == "S1"
    assert [(item["run_id"], item["display_name"]) for item in carriers["historical"]] == [
        ("RUN-CARRIER-B", "S1")
    ]


def test_history_attempts_sharing_a_run_directory_are_deduplicated(tmp_path):
    original = archived_run(tmp_path, "RUN-SHARED", 10)
    retry = history.create(dict(original, id="ignored", status="failed"))

    first_background = CapturingBackgroundTasks()
    variants.start_variant_index(original["id"], first_background)
    first_background.task(*first_background.args)

    retry_background = CapturingBackgroundTasks()
    variants.start_variant_index(retry["id"], retry_background)
    retry_background.task(*retry_background.args)

    listed = variants.indexed_variant_runs()["runs"]
    assert len(listed) == 1
    assert listed[0]["history_id"] == retry["id"]
    samples = variants.variant_samples(retry["id"])["samples"]
    assert len(samples) == 1
    assert samples[0]["call_count"] == 1


def test_concurrent_attempts_for_same_directory_share_one_lock(tmp_path):
    original = archived_run(tmp_path, "RUN-LOCKED", 10)
    retry = history.create(dict(original, id="ignored", status="failed"))
    background = CapturingBackgroundTasks()
    variants.start_variant_index(original["id"], background)

    with pytest.raises(HTTPException) as error:
        variants.start_variant_index(retry["id"], CapturingBackgroundTasks())
    assert error.value.status_code == 409
    assert "already running" in error.value.detail

    background.task(*background.args)
