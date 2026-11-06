"""HELPER supplies local gene/disease contexts for indexed variant details."""
import io

import pytest

from helper_next.api import variants
from helper_next.core import acmg_context, analysis_history, external_vcf
from helper_variants import gene_phenotype, gnomad_frequency, indexer, query


HEADER = ("sgc_id,version_number,gene_curie,gene_symbol,disease_curie,disease_title,"
          "disease_original_curie,disease_original_title,classification_title,moi_curie,"
          "moi_title,submitter_title,submitted_as_date,submitted_as_public_report_url,"
          "submitted_as_pmids,submitted_as_assertion_criteria_url,submitted_run_date\n")
ROW = "SGC-test,1,HGNC:7577,MYH7,MONDO:0005045,Example cardiomyopathy,OMIM:192600,Example,Strong,,Autosomal dominant,Test source,2026-01-01,https://example.test/association,PMID:1,,2026-01-02\n"


@pytest.fixture
def knowledge(monkeypatch):
    gene_phenotype.build_cache(io.StringIO(HEADER + ROW), gene_phenotype.cache_path())


def detail():
    return {"annotations": [{"id": 1, "gene": "MYH7", "transcript": "ENST1.1", "metadata": {"fields": {}}}]}


def test_cache_exposes_curated_stable_gene_ids_without_manual_hgnc(knowledge):
    data = gene_phenotype.query_gene("MYH7")
    assert data["gene_identifiers"] == ["HGNC:7577"]
    assert data["associations"][0]["assertions"][0]["gene_id"] == "HGNC:7577"
    choice = acmg_context.build(detail())["annotations"][0]["contexts"][0]
    context, selected = acmg_context.select(acmg_context.build(detail()), 1, "ENST1.1")
    assert context["gene"]["identifier"] == "HGNC:7577"
    assert context["disease"]["identifier"] == "MONDO:0005045"
    assert context["inheritance_modes"] == ["AUTOSOMAL_DOMINANT"]
    assert selected["origin"]["assertions"][0]["id"] == "SGC-test"
    assert choice["origin"]["source_version"]


@pytest.mark.parametrize("source_type", ["run", "external"])
def test_variant_detail_supplies_context_without_manual_identifiers(tmp_path, knowledge, source_type, monkeypatch):
    monkeypatch.setenv("HELPER_CLINVAR_OFFLINE", "1")
    content = ('##fileformat=VCFv4.2\n'
               '##INFO=<ID=CSQ,Number=.,Type=String,Description="Format: Allele|SYMBOL|Feature|Consequence">\n'
               '#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\n'
               '14\t100\t.\tA\tG\t60\tPASS\tCSQ=G|MYH7|ENST1.1|missense_variant\tGT\t0/1\n')
    if source_type == "external":
        source_id, path = external_vcf.allocate("test.vcf")
        path.write_text(content)
        record = external_vcf.finish(source_id, path, "test.vcf", "GRCh38")
    else:
        root = tmp_path / "run"
        path = root / "results/ANNOTATION/test.annotated.vcf"
        path.parent.mkdir(parents=True)
        path.write_text(content)
        record = analysis_history.create({"run_id": "test", "run_dir": str(root), "run_config": {"reference_version": "GRCh38"}})
        source_id = record["id"]
        indexer.index_run(record)
    database = indexer.index_path(record["run_dir"])
    variant_id = query.list_variants(database, 1)["items"][0]["variant_id"]
    allele = ("GRCh38", "14", 100, "A", "G")
    cached = gnomad_frequency._parse_response({"data": {
        "variant": {"variant_id": "14-100-A-G", "genome": {"ac": 0, "an": 100000, "filters": [], "populations": []}},
        "region": {"coverage": {"genome": [{"pos": 100, "mean": 31, "over_20": .94}]}},
    }}, gnomad_frequency.DATASETS["GRCh38"], allele, "https://gnomad.broadinstitute.org/")
    gnomad_frequency._store(gnomad_frequency.cache_path(), gnomad_frequency.cache_key(*allele), cached)
    selected = variants.sample_variant_detail(source_id, 1, variant_id)
    assert selected["gnomad_frequency"]["ac"] == 0
    supplied = selected["interpretation_context"]["annotations"][0]
    assert supplied["gene"]["identifier"] == "HGNC:7577"
    context, resolution = acmg_context.select(selected["interpretation_context"], supplied["annotation_id"], "ENST1.1")
    assert context["gene"]["identifier"] == "HGNC:7577"
    assert context["disease"]["identifier"] == "MONDO:0005045"
    assert resolution["origin"]["source_version"]
    assert resolution["origin"]["assertions"][0]["source"] == "Test source"
    assert selected["gnomad_frequency"]["an"] == 100000
    assert selected["gnomad_frequency"]["release"] == "4.1.1"


def test_multiple_diseases_require_selection_not_identifier_typing():
    other = ROW.replace("SGC-test", "SGC-other").replace("MONDO:0005045", "MONDO:0099999").replace("Example cardiomyopathy", "Other disease")
    gene_phenotype.build_cache(io.StringIO(HEADER + ROW + other), gene_phenotype.cache_path())
    catalog = acmg_context.build(detail())
    choices = catalog["annotations"][0]["contexts"]
    assert len(choices) == 2
    with pytest.raises(ValueError, match="Select an available"):
        acmg_context.select(catalog, 1, "ENST1.1")
    chosen, _ = acmg_context.select(catalog, 1, "ENST1.1", choices[1]["id"], choices[1]["fingerprint"]["value"])
    assert chosen["disease"] == choices[1]["context"]["disease"]


def test_wrong_hgnc_fallback_missing_cache_and_fingerprints(knowledge, monkeypatch, tmp_path):
    selected = detail()
    selected["annotations"][0]["metadata"]["fields"]["HGNC_ID"] = "999"
    assert acmg_context.build(selected)["annotations"][0]["contexts"] == []
    catalog = acmg_context.build(detail())
    choice = catalog["annotations"][0]["contexts"][0]
    with pytest.raises(ValueError, match="changed after preview"):
        acmg_context.select(catalog, 1, "ENST1.1", choice["id"], "0" * 64)
    monkeypatch.setenv("HELPER_GENE_PHENOTYPE_DB", str(tmp_path / "absent.sqlite"))
    missing = acmg_context.build(selected)["annotations"][0]
    assert missing["gene"]["identifier"] == "HGNC:999"
    assert missing["status"] == "MISSING_DISEASE_CONTEXT" and not missing["contexts"]


def test_inheritance_ambiguity_preserved_and_unsupported_mode_not_invented():
    other = ROW.replace("SGC-test", "SGC-recessive").replace("Autosomal dominant", "Autosomal recessive")
    gene_phenotype.build_cache(io.StringIO(HEADER + ROW + other), gene_phenotype.cache_path())
    catalog = acmg_context.build(detail())
    context, choice = acmg_context.select(catalog, 1, "ENST1.1")
    assert context["inheritance_modes"] == []
    assert choice["context"]["inheritance_modes"] == ["AUTOSOMAL_DOMINANT", "AUTOSOMAL_RECESSIVE"]
    context, _ = acmg_context.select(catalog, 1, "ENST1.1", inheritance="AUTOSOMAL_RECESSIVE")
    assert context["inheritance_modes"] == ["AUTOSOMAL_RECESSIVE"]
    with pytest.raises(ValueError, match="not recorded"):
        acmg_context.select(catalog, 1, "ENST1.1", inheritance="MITOCHONDRIAL")
