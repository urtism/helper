"""Synthetic PVS1 MVP checks: no clinical validation or legacy engine execution."""
import copy
import json
import os
from dataclasses import asdict

import pytest

from pvs1.calculator import calculate_pvs1
from pvs1.models import PVS1Input


TX, GENE = "ENST00000000001.1", "ENSG00000000001"
SOURCE = "synthetic:explicit-curation:v1; not clinical evidence"


@pytest.fixture(autouse=True)
def isolate_mechanism_sources(monkeypatch, tmp_path):
    monkeypatch.setenv("HELPER_MECHANISM_DB", str(tmp_path / "mechanisms.sqlite3"))
    monkeypatch.setenv("HELPER_GENE_PHENOTYPE_DB", str(tmp_path / "gene-phenotype.sqlite3"))


def sample_fixture(kind="stop_gained"):
    context = dict(gene=GENE, disease="SYNTHETIC_DISEASE", inheritance="AD", molecular_mechanism="LoF",
                   confidence="DEFINITIVE", scope="DISEASE_SPECIFIC")
    context["source_refs"] = {key: [SOURCE] for key in context}
    tx = dict(accession=TX, strand="+", coordinate_system="transcript_1_based_closed", cds_interval=[1, 300],
              exon_genomic_intervals=[[1001, 1100], [2001, 2100], [3001, 3100]],
              exon_coordinate_system="genomic_1_based_closed", biologically_relevant=True,
              affected_exon_relevant=True, affected_exon_lof_tolerant=False, rescue_present=False)
    tx["source_refs"] = {key: [SOURCE] for key in tx}
    product = dict(basis="PREDICTED", transcript_ref=TX + "|synthetic-product:v1",
                   coordinate_system="transcript_1_based_closed", ptc_start=100,
                   ptc_junction_distances=[[100, 0], [200, 100]], frame_effect="IN_FRAME")
    effect = {"products": [product]}
    variant = dict(assembly="GRCh38", contig="1", position=1100, reference_allele="C", alternate_allele="T",
                   consequence=kind, coordinate_system="genomic_1_based", source_refs={"consequence": [SOURCE]})
    if kind == "frameshift_variant":
        variant.update(position=1003, reference_allele="AC", alternate_allele="A")
        product.update(frame_effect="OUT_OF_FRAME", ptc_junction_distances=[[99, -1], [199, 99]])
        effect.update(cds_edit_interval=[3, 4], cds_coordinate_system="cds_0_based_half_open")
    if kind.startswith("splice_"):
        product.update(event_type="EXON_SKIPPING", involved_exons=[2], genomic_junctions=[[1100, 3001]],
                       ptc_junction_distances=[[200, 100]], frame_effect="OUT_OF_FRAME")
        effect.update(splice_site_type="DONOR", splice_site_offset=1, native_splice_motif="GT")
        effect["source_refs"] = {key: [SOURCE] for key in ("splice_site_type", "splice_site_offset", "native_splice_motif")}
    product["source_refs"] = {key: [SOURCE] for key in product}
    return PVS1Input(variant=variant, disease_context=context, transcript=tx, molecular_effect=effect)


def trace(result):
    return {row["id"]: row for row in map(json.loads, result.decision_trace)}


@pytest.mark.parametrize("kind", ["stop_gained", "frameshift_variant"])
def test_documented_ptc_nmd_branch_and_immutable_input(kind):
    sample = sample_fixture(kind)
    before = copy.deepcopy(sample)
    result = calculate_pvs1(sample)
    assert result.status == "ACTIVE"
    assert result.calculated_strength == result.applied_strength == "VERY_STRONG"
    assert result.ruleset_id == "PVS1_GENERAL" and result.ruleset_version == "1.3.0"
    assert sample == before
    steps = trace(result)
    assert steps["nmd"]["status"] == "PASS"
    assert steps["nmd"]["threshold"]["value"] == 50
    assert all({"description", "status", "value", "threshold", "source", "reason"} <= row.keys() for row in steps.values())


@pytest.mark.parametrize("distance,nmd_status,strength", [(49, "FAIL", "STRONG"), (50, "FAIL", "STRONG"), (51, "PASS", "VERY_STRONG")])
def test_nmd_boundary_is_not_criterion_exclusion(distance, nmd_status, strength):
    sample = sample_fixture()
    sample.transcript["exon_genomic_intervals"] = [[1001, 1100], [2001, 2000 + distance], [3001, 3100]]
    product = sample.molecular_effect["products"][0]
    product.update(ptc_junction_distances=[[100, 0], [100 + distance, distance]],
                   lost_region_critical=True, functional_evidence=[SOURCE])
    product["source_refs"]["lost_region_critical"] = [SOURCE]
    result = calculate_pvs1(sample)
    assert trace(result)["nmd"]["status"] == nmd_status
    assert result.status == "ACTIVE" and result.applied_strength == strength


@pytest.mark.parametrize("basis", ["PREDICTED", "OBSERVED", "UNKNOWN"])
def test_splice_basis_and_unimplemented_scientific_checks(basis):
    sample = sample_fixture("splice_donor_variant")
    product = sample.molecular_effect["products"][0]
    product.update(basis=basis, evidence_quality="Synthetic assay record; quality not validated")
    result = calculate_pvs1(sample)
    assert product["basis"] == basis
    if basis == "PREDICTED":
        assert result.status == "ACTIVE"
        assert result.applied_strength == result.calculated_strength == "VERY_STRONG"
        assert any("PREDICTED" in warning for warning in result.warnings)
        assert trace(result)["splice_scenarios"]["status"] == "NOT_EVALUATED"
        assert trace(result)["rna_quality"]["status"] == "NOT_APPLICABLE"
    elif basis == "OBSERVED":
        assert result.status == "REQUIRES_REVIEW"
        assert result.applied_strength is None and result.calculated_strength is None
        assert trace(result)["rna_quality"]["status"] == "NOT_EVALUATED"
        assert trace(result)["splice_basis"]["source"] == [SOURCE]
    else:
        assert result.status == "NOT_EVALUABLE"
        assert result.applied_strength is None and result.calculated_strength is None


def test_noncanonical_prediction_and_observed_without_rna_quality_are_incomplete():
    sample = sample_fixture("splice_region_variant")
    sample.molecular_effect["splice_site_offset"] = 5
    assert calculate_pvs1(sample).status == "NOT_EVALUABLE"
    assert "P34" in calculate_pvs1(sample).reason
    product = sample.molecular_effect["products"][0]
    product["basis"] = "OBSERVED"
    assert trace(calculate_pvs1(sample))["rna_quality"]["status"] == "UNKNOWN"
    product["source_refs"] = {"ptc_start": [SOURCE]}
    assert trace(calculate_pvs1(sample))["splice_basis"]["status"] == "UNKNOWN"


@pytest.mark.parametrize("site, offset, motif", [
    ("DONOR", -1, "GT"), ("ACCEPTOR", 1, "AG"), ("DONOR", 1, "GC"),
])
def test_predicted_splice_requires_consistent_canonical_site(site, offset, motif):
    sample = sample_fixture("splice_donor_variant")
    sample.molecular_effect.update(splice_site_type=site, splice_site_offset=offset, native_splice_motif=motif)
    result = calculate_pvs1(sample)
    assert result.status == "NOT_EVALUABLE" and result.applied_strength is None
    assert trace(result)["splice_scenarios"]["status"] == "UNKNOWN"


@pytest.mark.parametrize("field", ["splice_site_type", "splice_site_offset", "native_splice_motif"])
def test_predicted_splice_requires_sources_for_canonical_site_fields(field):
    sample = sample_fixture("splice_donor_variant")
    sample.molecular_effect["source_refs"].pop(field)
    assert calculate_pvs1(sample).applied_strength is None


@pytest.mark.parametrize("block, field", [
    ("product", "frame_effect"), ("product", "ptc_start"),
    ("product", "ptc_junction_distances"), ("context", "molecular_mechanism"),
])
def test_prediction_permission_does_not_fill_missing_molecular_or_mechanism_facts(block, field):
    sample = sample_fixture("splice_donor_variant")
    if block == "product":
        sample.molecular_effect["products"][0].pop(field)
    else:
        sample.disease_context[field] = "UNKNOWN"
    result = calculate_pvs1(sample)
    assert result.status == "NOT_EVALUABLE" and result.applied_strength is None
    assert result.missing_data


@pytest.mark.parametrize("distance, strength", [(49, "STRONG"), (50, "STRONG"), (51, "VERY_STRONG")])
def test_predicted_splice_uses_nmd_boundary_and_documented_critical_region(distance, strength):
    sample = sample_fixture("splice_donor_variant")
    product = sample.molecular_effect["products"][0]
    product.update(ptc_start=200 - distance, ptc_junction_distances=[[200, distance]],
                   lost_region_critical=True, functional_evidence=[SOURCE])
    product["source_refs"]["lost_region_critical"] = [SOURCE]
    result = calculate_pvs1(sample)
    assert result.status == "ACTIVE" and result.applied_strength == strength
    assert trace(result)["nmd"]["value"]["predicted_nmd"] is (distance > 50)


def test_predicted_inframe_splice_can_use_documented_critical_region():
    sample = sample_fixture("splice_donor_variant")
    product = sample.molecular_effect["products"][0]
    product.update(frame_effect="IN_FRAME", ptc_start=None, protein_accession="synthetic:protein:v1",
                   protein_coordinate_system="protein_1_based_closed", lost_region_critical=True,
                   functional_evidence=[SOURCE])
    product.pop("ptc_junction_distances")
    for key in ("protein_accession", "lost_region_critical"):
        product["source_refs"][key] = [SOURCE]
    result = calculate_pvs1(sample)
    assert result.status == "ACTIVE" and result.applied_strength == "STRONG"
    assert trace(result)["nmd"]["status"] == "NOT_APPLICABLE"


@pytest.mark.parametrize("field", ["molecular_mechanism", "confidence", "disease", "inheritance", "scope"])
def test_missing_mechanism_or_context_never_becomes_negative(field):
    sample = sample_fixture()
    sample.disease_context.pop(field)
    result = calculate_pvs1(sample)
    assert result.status == "NOT_EVALUABLE" and result.applied_strength is None
    assert result.missing_data
    assert trace(result)["nmd"]["status"] == "PASS"  # Known technical facts still inspected.


def test_documented_nonlof_is_inactive_but_inferred_lof_is_accepted_with_warning():
    sample = sample_fixture()
    sample.disease_context["molecular_mechanism"] = "GoF"
    result = calculate_pvs1(sample)
    assert result.status == "INACTIVE" and result.applied_strength is None
    assert trace(result)["mechanism"]["status"] == "FAIL"
    assert trace(result)["nmd"]["status"] == "NOT_EVALUATED"
    sample.disease_context.update(molecular_mechanism="LoF", confidence="INFERRED")
    result = calculate_pvs1(sample)
    assert result.status == "ACTIVE" and result.applied_strength == "VERY_STRONG"
    assert trace(result)["mechanism"]["value"]["confidence"] == "INFERRED"
    assert any("LoF inferito" in warning for warning in result.warnings)


@pytest.mark.parametrize("scope", ["DISEASE_SPECIFIC", "GENE_LEVEL"])
def test_inferred_lof_preserves_mechanism_scope_and_requires_citations(scope):
    sample = sample_fixture()
    sample.disease_context.update(confidence="INFERRED", mechanism_scope=scope)
    sample.disease_context["source_refs"]["mechanism_scope"] = [SOURCE]
    result = calculate_pvs1(sample)
    assert result.status == "ACTIVE" and not result.requires_review
    assert trace(result)["context"]["status"] == "PASS"
    assert trace(result)["mechanism"]["value"]["scope"] == scope
    for field in ("molecular_mechanism", "confidence", "mechanism_scope"):
        incomplete = copy.deepcopy(sample)
        incomplete.disease_context["source_refs"].pop(field)
        result = calculate_pvs1(incomplete)
        assert result.status == "NOT_EVALUABLE" and result.applied_strength is None


def test_gene_level_inference_does_not_supply_a_missing_disease_association():
    sample = sample_fixture()
    sample.disease_context.update(confidence="INFERRED", scope="GENE_LEVEL")
    result = calculate_pvs1(sample)
    assert trace(result)["context"]["status"] == "UNKNOWN"
    assert result.applied_strength is None


@pytest.mark.parametrize("strength", ["VERY_STRONG", "STRONG", "MODERATE", "SUPPORTING", "NONE"])
@pytest.mark.parametrize("state", ["ACTIVE", "UNKNOWN", "DISPUTED", "GoF"])
def test_manual_strength_preserves_the_automatic_assessment(strength, state):
    from helper_next.api.acmg_calculator import _strength_override
    sample = sample_fixture()
    if state in {"UNKNOWN", "DISPUTED"}:
        sample.disease_context["confidence"] = state
    elif state == "GoF":
        sample.disease_context["molecular_mechanism"] = state
    automatic = calculate_pvs1(sample)
    before = copy.deepcopy(automatic)
    result, selection = _strength_override(automatic, strength)
    assert automatic == before
    assert result.applied_strength == (None if strength == "NONE" else strength)
    assert result.calculated_strength == automatic.calculated_strength
    assert result.status == automatic.status and result.requires_review == automatic.requires_review
    assert result.missing_data == automatic.missing_data and result.reason == automatic.reason
    assert result.decision_trace[:-1] == automatic.decision_trace
    assert trace(result)["manual_strength"]["status"] == "MANUAL"
    assert selection == dict(strength=strength, automatic_status=automatic.status,
                             automatic_applied_strength=automatic.applied_strength)
    assert _strength_override(automatic, None) == (automatic, None)


@pytest.mark.parametrize("strength", ["INVALID", "", True, 1, [], {}])
def test_invalid_manual_strength_is_rejected_before_accessing_variant_data(monkeypatch, strength):
    from fastapi import HTTPException
    from helper_next.api import acmg_calculator as api
    monkeypatch.setattr(api, "_selected_annotation", lambda *args: pytest.fail("Invalid selection must not load data"))
    with pytest.raises(HTTPException) as exc:
        api.evaluate_pvs1(dict(strength_override=strength))
    assert exc.value.status_code == 400 and "Strength manuale" in exc.value.detail


def test_api_manual_strength_and_restore_do_not_modify_the_input(monkeypatch):
    from helper_next.api import acmg_calculator as api
    sample = sample_fixture()
    detail = detail_fixture()
    detail.update(position=sample.variant["position"], reference=sample.variant["reference_allele"],
                  alternate=sample.variant["alternate_allele"])
    annotation = detail["annotations"][0]
    annotation["metadata"]["pvs1_input"] = asdict(sample)
    before = copy.deepcopy(detail)
    monkeypatch.setattr(api, "_selected_annotation", lambda payload: (detail, annotation))
    automatic = api.evaluate_pvs1({})
    manual = api.evaluate_pvs1(dict(strength_override="MODERATE"))
    assert manual["result"]["calculated_strength"] == "VERY_STRONG"
    assert manual["result"]["applied_strength"] == "MODERATE"
    assert manual["strength_override"]["automatic_applied_strength"] == "VERY_STRONG"
    disabled = api.evaluate_pvs1(dict(strength_override="NONE"))
    assert disabled["result"]["applied_strength"] is None
    assert disabled["result"]["calculated_strength"] == "VERY_STRONG"
    assert api.evaluate_pvs1(dict(strength_override=None)) == automatic
    assert detail == before


@pytest.mark.parametrize("value", [None, False, True])
def test_supplied_transcript_is_evaluated_without_biological_relevance_gate(value):
    sample = sample_fixture()
    sample.transcript.pop("biologically_relevant", None)
    sample.transcript["source_refs"].pop("biologically_relevant")
    if value is not None:
        sample.transcript["biologically_relevant"] = value
        sample.transcript["source_refs"]["biologically_relevant"] = [SOURCE]
    before = copy.deepcopy(sample)
    result = calculate_pvs1(sample)
    assert result.status == "ACTIVE" and result.applied_strength == "VERY_STRONG"
    assert trace(result)["transcript_relevance"]["status"] == "NOT_EVALUATED"
    assert trace(result)["transcript_relevance"]["value"] == value
    assert not any("biologically_relevant" in missing for missing in result.missing_data)
    assert any("rilevanza biologica" in warning for warning in result.warnings)
    assert sample == before


@pytest.mark.parametrize("field", ["affected_exon_relevant", "affected_exon_lof_tolerant", "rescue_present"])
@pytest.mark.parametrize("absence", ["field", "null", "source", "unsourced_exclusion"])
def test_missing_biology_warns_without_blocking_or_inference(field, absence):
    sample = sample_fixture()
    if absence == "field":
        sample.transcript.pop(field)
    elif absence == "null":
        sample.transcript[field] = None
    else:
        sample.transcript["source_refs"].pop(field)
        if absence == "unsourced_exclusion":
            sample.transcript[field] = not sample.transcript[field]
    before = copy.deepcopy(sample)
    result = calculate_pvs1(sample)
    key = {"affected_exon_relevant": "exon_relevance", "affected_exon_lof_tolerant": "tolerance",
           "rescue_present": "rescue"}[field]
    assert result.status == "ACTIVE" and result.applied_strength == result.calculated_strength == "VERY_STRONG"
    assert not result.requires_review and not result.missing_data
    assert trace(result)[key]["status"] == "UNKNOWN"
    assert trace(result)[key]["value"] == sample.transcript.get(field)
    assert any(field in warning and "opzionale" in warning for warning in result.warnings)
    assert sample == before


@pytest.mark.parametrize("kind", ["stop_gained", "frameshift_variant", "splice_donor_variant"])
def test_all_optional_biology_missing_preserves_molecular_branch(kind):
    sample = sample_fixture(kind)
    for field in ("affected_exon_relevant", "affected_exon_lof_tolerant", "rescue_present"):
        sample.transcript.pop(field)
        sample.transcript["source_refs"].pop(field)
    result = calculate_pvs1(sample)
    assert sum("Dato opzionale" in warning for warning in result.warnings) == 3
    assert not result.missing_data
    if kind.startswith("splice_"):
        assert result.status == "ACTIVE" and result.applied_strength == "VERY_STRONG"
        assert trace(result)["splice_scenarios"]["status"] == "NOT_EVALUATED"
    else:
        assert result.status == "ACTIVE" and result.applied_strength == "VERY_STRONG"
    sample.molecular_effect = None
    result = calculate_pvs1(sample)
    assert result.status == "NOT_EVALUABLE" and result.applied_strength is None
    assert trace(result)["product"]["status"] == "UNKNOWN"


@pytest.mark.parametrize("field", ["affected_exon_relevant", "affected_exon_lof_tolerant", "rescue_present"])
def test_documented_biological_exclusions_still_apply_with_other_fields_missing(field):
    sample = sample_fixture()
    sample.transcript[field] = not sample.transcript[field]
    for other in ("affected_exon_relevant", "affected_exon_lof_tolerant", "rescue_present"):
        if other != field:
            sample.transcript.pop(other)
    result = calculate_pvs1(sample)
    assert result.status == "INACTIVE" and result.applied_strength is None
    assert field in result.reason


def test_unknown_or_inconsistent_product_and_multiple_products_do_not_get_strength():
    for change in ({"ptc_start": None}, {"basis": "UNKNOWN"}, {"ptc_junction_distances": [[100, 1], [200, 100]]},
                   {"ptc_junction_distances": []}, {"ptc_start": 101}):
        sample = sample_fixture()
        sample.molecular_effect["products"][0].update(change)
        assert calculate_pvs1(sample).status == "NOT_EVALUABLE"
    sample = sample_fixture()
    sample.molecular_effect["products"] *= 2
    assert calculate_pvs1(sample).status == "REQUIRES_REVIEW"
    sample.molecular_effect = None
    assert calculate_pvs1(sample).status == "NOT_EVALUABLE"


def test_inframe_without_resolved_translation_and_mismatched_stop_locus_are_incomplete():
    sample = sample_fixture("splice_donor_variant")
    sample.molecular_effect["products"][0].update(frame_effect="IN_FRAME", ptc_start=None)
    sample.molecular_effect["products"][0].pop("ptc_junction_distances")
    result = calculate_pvs1(sample)
    assert result.status == "NOT_EVALUABLE" and trace(result)["product"]["status"] == "UNKNOWN"
    sample = sample_fixture()
    sample.variant["position"] = 1001
    assert calculate_pvs1(sample).status == "NOT_EVALUABLE"


@pytest.mark.parametrize("lost,strength", [(9, "MODERATE"), (10, None), (11, "STRONG")])
def test_protein_loss_fraction_and_exact_ten_percent(lost, strength):
    sample = sample_fixture()
    sample.transcript.update(cds_interval=[1, 303], exon_genomic_intervals=[[1001, 1100], [2001, 2100], [3001, 3103]])
    product = sample.molecular_effect["products"][0]
    ptc = 3 * (100 - lost) + 1
    sample.variant["position"] = 3001 + ptc - 201
    product.update(ptc_start=ptc, ptc_junction_distances=[[100, 100 - ptc], [200, 200 - ptc]],
                   protein_accession="synthetic:protein:v1", protein_coordinate_system="protein_1_based_closed",
                   lost_protein_region=[101 - lost, 100])
    product["source_refs"]["lost_protein_region"] = [SOURCE]
    result = calculate_pvs1(sample)
    assert result.applied_strength == strength
    assert result.status == ("ACTIVE" if strength else "REQUIRES_REVIEW")


@pytest.mark.parametrize("consequence", ["start_lost", "copy_number_change", "missense_variant"])
def test_unsupported_branches_and_policy_are_explicit(consequence):
    assert calculate_pvs1(sample_fixture(consequence)).status == "NOT_EVALUABLE"
    assert calculate_pvs1(sample_fixture(), policy="EXPERIMENTAL").status == "NOT_EVALUABLE"


def reference_fixture():
    cds = "ATG" + "CAA" * 80 + "TAA"
    return dict(transcript={"accession": TX.split(".")[0], "version": "1"}, assembly="GRCh38", chromosome="1", gene_ids=[GENE],
                strand="+", annotation_release="116", coordinate_convention="1-based inclusive; transcript 5-prime to 3-prime; CDS includes stop",
                artifact_digest={"algorithm": "sha256", "value": "a" * 64}, cdna="GGG" + cds + "CCC", cds=cds,
                protein="M" + "Q" * 80, protein_length=81, cds_start=4, cds_end=249,
                exons=[dict(genomic_start=100, genomic_end=189, mrna_start=1, mrna_end=90),
                       dict(genomic_start=300, genomic_end=389, mrna_start=91, mrna_end=180),
                       dict(genomic_start=500, genomic_end=571, mrna_start=181, mrna_end=252)],
                junctions=[{"mrna_position": 90}, {"mrna_position": 180}])


def detail_fixture():
    return {"variant_id": 1, "reference_build": "GRCh38", "chromosome": "1", "position": 106,
            "reference": "C", "alternate": "T", "annotations": [
                {"id": 7, "transcript": TX, "gene": GENE, "consequence": "stop_gained", "hgvsp": "p.Gln2Ter",
                 "metadata": {"fields": {"Gene": GENE, "Protein_position": "2"}}}]}


@pytest.fixture
def local_g2p(monkeypatch):
    from helper_next.core import acmg_context
    from helper_next.core.acmg_sources import SourceManager
    from helper_next.core.acmg_mechanism_models import SOURCES
    record = dict(id="G2P-SYNTHETIC", gene_id="HGNC:999999", disease_id="MONDO:9999999", disease_mim="OMIM:999999",
                  disease_name="Synthetic disease", mechanism="loss of function", original_mechanism="loss of function",
                  confidence="definitive", accepted=True, allelic_requirement="biallelic_autosomal",
                  url="https://example.test/g2p/synthetic", publications="PMID:synthetic", last_reviewed="2026-01-01")
    association = dict(disease_id=record["disease_id"], disease=record["disease_name"],
                       assertions=[dict(id="SGC-synthetic", gene_id=record["gene_id"], inheritance="Autosomal recessive")])
    knowledge = dict(gene_identifiers=[record["gene_id"]], associations=[association], g2p_records=[record],
                     cache=dict(status="ready", updated_at="synthetic-cache-v1"))
    monkeypatch.setattr(acmg_context.gene_phenotype, "query_gene", lambda *args: copy.deepcopy(knowledge))

    def source_records(gene_id, symbol="", sources=None, **kwargs):
        records = [dict(g2p_id=r["id"], gene_curie=r["gene_id"], gene_symbol="SYNTHETIC",
                        disease_curie=r["disease_id"], disease_mim=r["disease_mim"], disease_name=r["disease_name"],
                        allelic_requirement=r["allelic_requirement"], confidence=r["confidence"],
                        mechanism=r.get("original_mechanism") or r["mechanism"], record_url=r["url"],
                        publications=r["publications"], last_reviewed=r["last_reviewed"])
                   for r in knowledge["g2p_records"]]
        return {s: dict(source=s, status="AVAILABLE" if s == "g2p" and records else "NO_RECORDS",
                        records=records if s == "g2p" else [], retrieved_at="2026-01-01T00:00:00Z",
                        dataset_version="synthetic-cache-v1") for s in sources or SOURCES}

    monkeypatch.setattr(acmg_context.gene_phenotype, "mechanism_source_records", source_records)
    monkeypatch.setattr(SourceManager, "mechanism_revision", lambda self: json.dumps(knowledge, sort_keys=True))
    return knowledge


def test_local_g2p_association_mechanism_and_sources_reach_new_calculator(local_g2p):
    from helper_next.api import acmg_calculator as api
    detail = detail_fixture()
    detail["annotations"][0]["consequence"] = "splice_donor_variant"
    choice = api.acmg_context.build(detail)["annotations"][0]["contexts"][0]
    sample, _, _, _ = api.prepare_pvs1_input(detail, detail["annotations"][0], choice)
    assert sample.disease_context["inheritance"] == "AUTOSOMAL_RECESSIVE"
    assert sample.disease_context["molecular_mechanism"] == "LoF"
    assert sample.disease_context["confidence"] == "DEFINITIVE"
    assert sample.transcript["accession"] == TX and sample.molecular_effect is None
    result = calculate_pvs1(sample)
    checks = trace(result)
    assert checks["context"]["status"] == checks["mechanism"]["status"] == "PASS"
    assert checks["transcript_relevance"]["status"] == "NOT_EVALUATED"
    assert result.status == "NOT_EVALUABLE" and "SpliceAI" in checks["product"]["reason"]
    source = checks["mechanism"]["source"][0]
    assert all(value in source for value in ("G2P-SYNTHETIC", "https://example.test/g2p/synthetic", "PMID:synthetic", "synthetic-cache-v1"))
    assert "affected_exon_relevant" not in sample.transcript  # G2P does not supply exon biology.


def test_g2p_only_association_and_inheritance_are_selectable(local_g2p):
    from helper_next.api import acmg_calculator as api
    local_g2p.update(associations=[], gene_identifiers=[])
    detail = detail_fixture()
    before = copy.deepcopy(local_g2p)
    catalog = api.acmg_context.build(detail)
    choice = catalog["annotations"][0]["contexts"][0]
    assert choice["context"]["gene"]["identifier"] == "HGNC:999999"
    assert choice["context"]["inheritance_modes"] == ["AUTOSOMAL_RECESSIVE"]
    sample, _, _, _ = api.prepare_pvs1_input(detail, detail["annotations"][0], choice)
    assert sample.disease_context["molecular_mechanism"] == "LoF"
    assert local_g2p == before


def test_inferred_mechanism_does_not_overwrite_selected_association(local_g2p, monkeypatch):
    from helper_next.api import acmg_calculator as api
    detail = detail_fixture()
    choice = api.acmg_context.build(detail)["annotations"][0]["contexts"][0]
    mechanism = dict(molecular_mechanism="LoF", confidence="INFERRED", scope="GENE_LEVEL",
                     source_refs={key: ["synthetic:ClinGen HI=3"]
                                  for key in ("molecular_mechanism", "confidence", "scope")})
    monkeypatch.setattr(api, "resolve_pvs1_mechanism", lambda choice: (copy.deepcopy(mechanism), {}, []))
    sample, *_ = api.prepare_pvs1_input(detail, detail["annotations"][0], choice)
    context = sample.disease_context
    assert context["scope"] == "DISEASE_SPECIFIC" and context["mechanism_scope"] == "GENE_LEVEL"
    assert context["source_refs"]["scope"][0].startswith("HELPER association")
    assert context["source_refs"]["mechanism_scope"] == ["synthetic:ClinGen HI=3"]
    checks = trace(calculate_pvs1(sample))
    assert checks["context"]["status"] == checks["mechanism"]["status"] == "PASS"


@pytest.mark.parametrize("change", [
    {"gene_id": "HGNC:888888"},
    {"disease_id": "MONDO:8888888", "disease_mim": ""},
    {"allelic_requirement": "monoallelic_autosomal"},
    {"allelic_requirement": "biallelic"},
    {"accepted": False, "confidence": "uncertain"},
    {"original_mechanism": "frameshift_variant"},
    {"url": ""},
])
def test_g2p_unqualified_or_different_scope_is_not_imported(local_g2p, change):
    from helper_next.api import acmg_calculator as api
    local_g2p["g2p_records"][0].update(change)
    detail = detail_fixture()
    detail["annotations"][0]["metadata"]["fields"]["HGNC_ID"] = "999999"
    choices = api.acmg_context.build(detail)["annotations"][0]["contexts"]
    choice = next(c for c in choices if c["context"]["disease"]["identifier"] == "MONDO:9999999")
    sample, _, _, _ = api.prepare_pvs1_input(detail, detail["annotations"][0], choice)
    assert sample.disease_context["molecular_mechanism"] == "UNKNOWN"
    assert not sample.disease_context.get("source_refs", {}).get("molecular_mechanism")


def test_unidentified_g2p_disease_is_not_matched_by_name(local_g2p):
    from helper_next.api import acmg_calculator as api
    local_g2p["g2p_records"][0].update(disease_id="", disease_mim="")
    detail = detail_fixture()
    choices = api.acmg_context.build(detail)["annotations"][0]["contexts"]
    assert len(choices) == 1
    sample, _, warnings, _ = api.prepare_pvs1_input(detail, detail["annotations"][0], choices[0])
    assert sample.disease_context["molecular_mechanism"] == "UNKNOWN"
    assert any("G2P-SYNTHETIC" in warning and "identificativo di malattia" in warning for warning in warnings)
    local_g2p["associations"] = []
    assert api.acmg_context.build(detail)["annotations"][0]["contexts"] == []


def test_conflicting_g2p_mechanisms_are_retained_without_definitive_result(local_g2p):
    from helper_next.api import acmg_calculator as api
    opposite = dict(local_g2p["g2p_records"][0], id="G2P-OPPOSITE", mechanism="gain of function", original_mechanism="gain of function")
    local_g2p["g2p_records"].append(opposite)
    detail = detail_fixture()
    choice = api.acmg_context.build(detail)["annotations"][0]["contexts"][0]
    sample, _, _, _ = api.prepare_pvs1_input(detail, detail["annotations"][0], choice)
    assert sample.disease_context["confidence"] == "DISPUTED"
    assert sample.disease_context["molecular_mechanism"] == "UNKNOWN"
    assert len(sample.disease_context["source_refs"]["molecular_mechanism"]) == 2
    assert calculate_pvs1(sample).applied_strength is None


def test_route_rebuilds_and_imports_selected_local_g2p_context(local_g2p, monkeypatch):
    from helper_next.api import acmg_calculator as api
    detail = detail_fixture()
    choice = api.acmg_context.build(detail)["annotations"][0]["contexts"][0]
    monkeypatch.setattr(api, "_entry", lambda identifier: {})
    monkeypatch.setattr(api, "_entry_database", lambda entry: "synthetic-index")
    monkeypatch.setattr(api.query, "variant_detail", lambda *args: detail)
    response = api.evaluate_pvs1(dict(run_id="synthetic", sample_id=1, variant_id=1, annotation_id=7,
                                     transcript=TX, context_id=choice["id"]))
    checks = {row["id"]: row for row in map(json.loads, response["result"]["decision_trace"])}
    assert checks["context"]["status"] == checks["mechanism"]["status"] == "PASS"
    assert response["input"]["transcript"]["accession"] == TX
    assert response["input"]["disease_context"]["molecular_mechanism"] == "LoF"
    assert response["mechanism_assessment"]["snapshot_id"]
    assert response["mechanism_assessment"]["identity"]["gene_id"] == "HGNC:999999"


def test_input_adapter_does_not_infer_a_product_from_numerical_hgvs(monkeypatch):
    from helper_next.api import acmg_calculator as api
    from helper_next.core.acmg_transcripts import TranscriptReferenceProvider
    monkeypatch.setattr(TranscriptReferenceProvider, "get", lambda *args, **kwargs: pytest.fail("Input adaptation must not acquire references"))
    detail = detail_fixture()
    sample, origin, _, _ = api.prepare_pvs1_input(detail, detail["annotations"][0])
    assert origin == "ANNOTATION_ONLY" and sample.molecular_effect is None
    assert sample.transcript["accession"] == TX
    assert calculate_pvs1(sample).status == "NOT_EVALUABLE"


def test_stored_molecular_input_uses_the_selected_mechanism_without_mutation(local_g2p, monkeypatch):
    from helper_next.api import acmg_calculator as api
    sample = sample_fixture()
    sample.disease_context.update(disease="MONDO:9999999", inheritance="AUTOSOMAL_RECESSIVE")
    detail = detail_fixture()
    detail.update(position=sample.variant["position"], reference=sample.variant["reference_allele"],
                  alternate=sample.variant["alternate_allele"])
    detail["annotations"][0]["metadata"]["pvs1_input"] = asdict(sample)
    before = copy.deepcopy(detail)
    local_g2p["g2p_records"].append(dict(local_g2p["g2p_records"][0], id="G2P-conflict",
                                        original_mechanism="gain of function"))
    choice = api.acmg_context.build(detail)["annotations"][0]["contexts"][0]
    monkeypatch.setattr(api, "_entry", lambda _: {})
    monkeypatch.setattr(api, "_entry_database", lambda _: "synthetic")
    monkeypatch.setattr(api.query, "variant_detail", lambda *args: detail)
    monkeypatch.setattr(api, "analyze_transcripts", lambda *args, **kwargs: pytest.fail("Stored RNA must not be reconstructed"))
    response = api.evaluate_pvs1(dict(run_id="synthetic", sample_id=1, variant_id=1, annotation_id=7,
                                      transcript=TX, context_id=choice["id"]))
    assert response["result"]["status"] == "REQUIRES_REVIEW"
    assert response["result"]["applied_strength"] is None
    assert response["input"]["molecular_effect"] == asdict(sample)["molecular_effect"]
    assert response["mechanism_assessment"]["conflicting_evidence"]
    assert detail == before
    detail["annotations"][0]["metadata"]["pvs1_input"]["disease_context"]["inheritance"] = "AD"
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        api.evaluate_pvs1(dict(run_id="synthetic", sample_id=1, variant_id=1, annotation_id=7,
                             transcript=TX, context_id=choice["id"]))
    assert exc.value.status_code == 400 and "inheritance" in exc.value.detail


def test_sequence_and_annotation_release_gate_the_applied_strength(local_g2p, monkeypatch):
    from helper_next.api import acmg_calculator as api
    from helper_next.core.acmg_transcripts import TranscriptReferenceProvider
    detail = detail_fixture()
    choice = api.acmg_context.build(detail)["annotations"][0]["contexts"][0]
    monkeypatch.setenv("HELPER_ENSEMBL_RELEASE", "116")
    monkeypatch.setenv("HELPER_TRANSCRIPT_FETCH", "0")
    monkeypatch.setattr(TranscriptReferenceProvider, "get", lambda *args, **kwargs: {"data": reference_fixture()})
    monkeypatch.setattr(api, "_entry", lambda _: {})
    monkeypatch.setattr(api, "_entry_database", lambda _: "synthetic")
    monkeypatch.setattr(api.query, "variant_detail", lambda *args: detail)
    payload = dict(run_id="synthetic", sample_id=1, variant_id=1, annotation_id=7, transcript=TX, context_id=choice["id"])
    result = api.evaluate_pvs1(payload)
    assert not result["molecular_impact"]["release_verified"]
    assert result["input"]["molecular_effect"] is None
    assert result["result"]["applied_strength"] is None
    detail["annotations"][0]["release_resources"] = {"ensembl_release": "116"}
    result = api.evaluate_pvs1(payload)
    assert result["result"]["applied_strength"] == "VERY_STRONG"
    assert result["molecular_origin"] == "TRANSCRIPT_MOLECULAR_ANALYSIS"
    # A plausible numerical annotation cannot override a sequence disagreement.
    detail["annotations"][0]["hgvsp"] = "p.Gln3Ter"
    result = api.evaluate_pvs1(payload)
    assert result["result"]["applied_strength"] is None
    row = result["molecular_impact"]["transcripts"][0]
    assert "ANNOTATED_STOP_CONFLICT" in row["product_resolution"]["reason_codes"]


@pytest.mark.parametrize("optional_biology_missing", [False, True])
def test_http_route_calls_new_calculator_and_binds_existing_allele_transcript(monkeypatch, optional_biology_missing):
    from fastapi import FastAPI
    from helper_next.api import acmg_calculator as api
    from unittest.mock import patch
    detail, sample = detail_fixture(), sample_fixture()
    if optional_biology_missing:
        for field in ("affected_exon_relevant", "affected_exon_lof_tolerant", "rescue_present"):
            sample.transcript.pop(field)
            sample.transcript["source_refs"].pop(field)
    detail.update(reference_build=sample.variant["assembly"], chromosome=sample.variant["contig"], position=sample.variant["position"],
                  reference=sample.variant["reference_allele"], alternate=sample.variant["alternate_allele"])
    detail["annotations"][0]["metadata"]["pvs1_input"] = asdict(sample)
    monkeypatch.setattr(api, "_entry", lambda identifier: {})
    monkeypatch.setattr(api, "_entry_database", lambda entry: "synthetic-index")
    monkeypatch.setattr(api.query, "variant_detail", lambda *args: detail)
    monkeypatch.setattr(api, "analyze_transcripts", lambda *args, **kwargs: pytest.fail("Existing PVS1 input must not fetch reference"))
    app = FastAPI()
    app.include_router(api.router)
    payload = dict(run_id="synthetic", sample_id=1, variant_id=1, annotation_id=7, transcript=TX)
    assert any(route.path == "/api/acmg-calculator/pvs1" and "POST" in route.methods for route in app.routes)
    with patch.object(api, "calculate_pvs1", wraps=calculate_pvs1) as calculator:
        response = api.evaluate_pvs1(payload)
        calculator.assert_called_once()
    assert response["result"]["status"] == "ACTIVE"
    assert response["result"]["applied_strength"] == "VERY_STRONG"
    assert not response["result"]["missing_data"]
    assert sum("Dato opzionale" in warning for warning in response["result"]["warnings"]) == (3 if optional_biology_missing else 0)
    assert response["molecular_origin"] == "EXISTING_PVS1_INPUT"
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        api.evaluate_pvs1(dict(payload, transcript=TX.replace(".1", ".2")))
    assert error.value.status_code == 400
    detail["annotations"][0]["metadata"]["pvs1_input"]["variant"]["position"] += 1
    with pytest.raises(HTTPException) as error:
        api.evaluate_pvs1(payload)
    assert error.value.status_code == 400


def test_application_registers_new_route_without_starting_any_engine(monkeypatch):
    import socket
    import subprocess
    def unexpected(*args, **kwargs):
        pytest.fail("Application lifecycle must not start or contact an external evaluator")
    monkeypatch.setattr(subprocess, "Popen", unexpected)
    monkeypatch.setattr(socket, "create_connection", unexpected)
    from helper_next.api.app import create_app
    app = create_app()
    routes = {route.path for route in app.routes}
    assert "/api/acmg-calculator/pvs1" in routes
    assert "/api/acmg-calculator/molecular-impact" in routes
    assert "/api/acmg/mechanisms/resolve" in routes
    assert "/api/acmg/discovery" not in routes
    assert not any("/workspaces" in route or "/task22" in route for route in routes)
    import asyncio
    asyncio.run(app.router.startup())
    asyncio.run(app.router.shutdown())


def test_packaged_application_imports_pvs1_outside_repository(tmp_path):
    from pathlib import Path
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    packaged = tmp_path / "site-packages"
    built = subprocess.run(
        [sys.executable, "setup.py", "build_py", "--build-lib", str(packaged)],
        cwd=root / "helper_next", capture_output=True, text=True, timeout=60,
    )
    assert built.returncode == 0, built.stdout + built.stderr
    environment = dict(os.environ, PYTHONPATH=str(packaged),
                       PYTHONDONTWRITEBYTECODE="1")
    imported = subprocess.run(
        [sys.executable, "-c", (
            "from pathlib import Path; import pvs1; "
            "from helper_next.api.app import create_app; "
            "assert Path(pvs1.__file__).resolve().parent.parent == Path.cwd() / 'site-packages'; "
            "assert '/api/acmg-calculator/pvs1' in {r.path for r in create_app().routes}"
        )], cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30,
    )
    assert imported.returncode == 0, imported.stdout + imported.stderr


@pytest.mark.skipif(os.environ.get("HELPER_TEST_PVS1_CALCULATOR_BROWSER") != "1", reason="Opt in to the targeted Chrome check")
@pytest.mark.parametrize("viewport", [(1280, 900), (480, 900)])
def test_new_calculator_panel_opens_and_explains_requirements(tmp_path, viewport):
    from html.parser import HTMLParser
    from pathlib import Path
    import shutil
    import subprocess

    chrome = shutil.which("google-chrome")
    if not chrome:
        pytest.skip("Chrome unavailable")
    root = Path(__file__).resolve().parents[1]
    sample = sample_fixture()
    incomplete = sample_fixture()
    incomplete.disease_context["molecular_mechanism"] = "UNKNOWN"
    responses = [{"input": asdict(item), "result": asdict(calculate_pvs1(item)), "molecular_origin": "SYNTHETIC_TEST_ONLY"}
                 for item in (sample, incomplete)]
    for response in responses:
        response["mechanism_assessment"] = {"gene_level_indicators": [
            {"source": "clingen_dosage", "metric": "HI", "value": 3, "interpretation": "SUFFICIENT_EVIDENCE",
             "selected_for_gene_assessment": True, "supports_lof": True, "issues": [], "source_url": "https://example.test/HI"},
            {"source": "gnomad", "metric": "pLI", "value": 0, "interpretation": "NO_HIGH_LOF_INTOLERANCE",
             "selected_for_gene_assessment": True, "supports_lof": False, "issues": ["UNVERIFIED_RELEASE"],
             "transcript": "ENST00000000002", "release": None, "source_url": "https://example.test/pLI"},
        ]}
        response["molecular_impact"] = {"gene": GENE, "assembly": "GRCh38", "release": "116", "catalog_complete": True,
            "transcripts": [
                {"transcript": TX, "status": "AFFECTED_CODING", "selected": True, "consequence": "stop_gained",
                 "cds_length_nt": 1503, "cds_position": 301, "first_affected_reference_codon": 101,
                 "reference_protein_length": 500, "predicted_protein_length": 100, "physical_deleted_nt": 0,
                 "reference_cds_untranslated_percent": 80, "protein_impact_percent": 80, "physical_cds_deleted_percent": 0,
                 "product_resolution": {"status": "DETERMINED", "method": "CODON_VERIFICATION", "reason_codes": []},
                 "nmd_predicted": True, "formulas": {"stop_gain": "100 * (500 - 101 + 1) / 500"}},
                {"transcript": "ENST00000000002.1", "status": "NON_CODING", "consequence": "non_coding_transcript_variant"},
                {"transcript": "ENST00000000003.1", "status": "INSUFFICIENT_DATA", "missing_data": ["Incomplete CDS"]},
            ]}
    splice_response = copy.deepcopy(responses[0])
    splice_response["input"]["transcript"]["exon_genomic_intervals"] = [[1000 + i * 200, 1099 + i * 200] for i in range(32)]
    event = dict(basis="PREDICTED", event_type="EXON_SKIPPING", involved_exons=[24, 25, 26])
    splice_response["input"]["molecular_effect"]["products"][0].update(event, frame_effect="OUT_OF_FRAME")
    splice_response["molecular_impact"]["transcripts"][0].update(
        status="SPLICE_SCENARIO", cds_length_nt=9171, reference_protein_length=3056,
        predicted_protein_length=1195, physical_deleted_nt=10,
        splice_analysis={"site": {"type": "DONOR", "native_motif": "GT", "affected_offsets": [1, 2]},
                         "scenarios": [{"event": event, "coding_deleted_nt": 170, "frame_effect": "OUT_OF_FRAME"}]})
    responses.append(splice_response)
    cryptic_response = copy.deepcopy(splice_response)
    cryptic_event = dict(basis="PREDICTED", event_type="CRYPTIC_SITE", involved_exons=[25])
    cryptic_response["input"]["molecular_effect"]["products"][0].update(cryptic_event)
    cryptic_response["molecular_impact"]["transcripts"][0]["splice_analysis"]["scenarios"][0].update(
        event=cryptic_event, coding_deleted_nt=0, rna_inserted_nt=25, coding_inserted_nt=25)
    cryptic_response["molecular_impact"]["transcripts"][0]["splice_analysis"]["prediction"] = {
        "selection_status": "EXPLORATORY_LOW_DELTA"}
    responses.append(cryptic_response)
    inferred = copy.deepcopy(sample)
    inferred.disease_context.update(confidence="INFERRED", mechanism_scope="GENE_LEVEL")
    inferred.disease_context["source_refs"]["mechanism_scope"] = [SOURCE]
    inferred_response = copy.deepcopy(responses[0])
    inferred_response.update(input=asdict(inferred), result=asdict(calculate_pvs1(inferred)))
    hi = dict(evidence_id="hi", source="clingen_dosage", source_record_id="HI-SYNTHETIC",
              source_updated_at="2026-11-05", raw_assertion=dict(assessment="haploinsufficiency", hi_score=3,
              report_url="https://example.test/clingen/hi"))
    inferred_response["mechanism_assessment"].update(mechanism="LOSS_OF_FUNCTION", mechanism_scope="GENE_LEVEL",
        assertions=[dict(mechanism="LOSS_OF_FUNCTION", scope="GENE_LEVEL", supporting_evidence_refs=["hi"])],
        supporting_evidence=[hi])
    responses.append(inferred_response)
    discordant = copy.deepcopy(inferred)
    discordant.disease_context.update(confidence="DISPUTED")
    discordant_response = copy.deepcopy(inferred_response)
    discordant_response.update(input=asdict(discordant), result=asdict(calculate_pvs1(discordant)))
    discordant_response["mechanism_assessment"]["conflicting_evidence"] = [dict(
        evidence_id="conflict", source="gencc", source_record_id="SGC-CONFLICT", source_classification="Disputed Evidence",
        raw_assertion=dict(public_report_url="https://example.test/gencc/disputed"))]
    responses.append(discordant_response)
    module = (root / "helper_next/src/helper_variants/web/static/variant-browser.js").as_uri()
    script = r"""
      const until=async f=>{for(let n=0;n<200;n++){if(f())return;await new Promise(r=>setTimeout(r,10));}throw Error('UI timed out');};
      const requests=[], comparisons=[]; let responseIndex=0;
      const savedReads=[],saves=[],historyRequests=[],savedByContext=new Map(),tickets=new Map();let staleSources=false;
      const originalFetch=window.fetch.bind(window);
      window.fetch=async(url,options={})=>{
        if(String(url)==='/api/acmg-calculator/pvs1'){
          const body=JSON.parse(options.body);requests.push(body);
          const payload=structuredClone(__RESPONSES__[responseIndex]);
          if(body.strength_override){
            payload.strength_override={strength:body.strength_override,automatic_status:payload.result.status,
              automatic_applied_strength:payload.result.applied_strength};
            payload.result.applied_strength=body.strength_override==='NONE'?null:body.strength_override;
          }
          payload.molecular_impact.scope='SELECTED';
          payload.molecular_impact.transcripts=payload.molecular_impact.transcripts.slice(0,1);
          payload.evaluation_id=String(requests.length);
          payload.evaluation_signature=staleSources?'sources-v2':'sources-v1';
          tickets.set(payload.evaluation_id,{body,snapshot:{result:payload.result,strength_override:payload.strength_override},signature:payload.evaluation_signature});
          return new Response(JSON.stringify(payload),{status:200,headers:{'Content-Type':'application/json'}});
        }
        if(String(url)==='/api/acmg-calculator/pvs1/saved'){
          const body=JSON.parse(options.body);savedReads.push(body);
          return new Response(JSON.stringify({saved:savedByContext.get(body.context_id)||null,needs_review:staleSources}),{status:200});
        }
        if(String(url)==='/api/acmg-calculator/pvs1/save'){
          const body=JSON.parse(options.body);saves.push(body);const ticket=tickets.get(body.evaluation_id);
          const record={revision:(savedByContext.get(ticket.body.context_id)?.revision||0)+1,saved_at:'2026-11-10T12:00:00Z',
            snapshot:ticket.snapshot,signature:ticket.signature,note:body.note};
          savedByContext.set(ticket.body.context_id,record);
          return new Response(JSON.stringify({saved:record,needs_review:false}),{status:200});
        }
        if(String(url)==='/api/acmg-calculator/pvs1/history'){
          const body=JSON.parse(options.body);historyRequests.push(body);
          return new Response(JSON.stringify({items:[savedByContext.get(body.context_id)].filter(Boolean),next_before_revision:null}),{status:200});
        }
        if(String(url)==='/api/acmg-calculator/molecular-impact'){
          comparisons.push(JSON.parse(options.body));
          return new Response(JSON.stringify({...__RESPONSES__[0].molecular_impact,scope:'GENE'}),{status:200,headers:{'Content-Type':'application/json'}});
        }
        if(String(url).startsWith('/api/acmg'))throw Error('Legacy ACMG API called');
        if(String(url).startsWith('/api/'))return new Response('{"runs":[],"items":[]}',{status:200});
        return originalFetch(url,options);
      };
      await import(__MODULE__);
      const host=document.querySelector('variant-browser');
      const workspace={key:'synthetic',runId:'synthetic',sample:{sample_id:1},items:[{variant_id:1,transcript:__TX__}],
        detail:{variant_id:1,reference_build:'GRCh38',chromosome:'1',position:1100,reference:'C',alternate:'T',
          interpretation_context:{annotations:[{annotation_id:7,transcript:__TX__,contexts:['a','b'].map(id=>({
            id:'context-'+id,fingerprint:{value:id},context:{disease:{identifier:'MONDO:'+id,label:'Disease '+id},inheritance_modes:['AUTOSOMAL_DOMINANT']},
          }))}]},
          calls:[],annotations:[{id:7,gene:__GENE__,transcript:__TX__,consequence:'stop_gained',hgvsc:'c.100C>T',hgvsp:'p.Gln34Ter',metadata:{fields:{EXON:'2/3'}}}]}};
      host.shadowRoot.append(host.renderDetail(workspace));
      const button=host.shadowRoot.querySelector('.new-acmg-open');button.focus();button.click();
      await until(()=>host.shadowRoot.querySelector('#new-acmg-summary'));
      const shadow=host.shadowRoot;
      await until(()=>shadow.querySelector('link[rel=stylesheet]')?.sheet);
      const initialMolecularRows=shadow.querySelectorAll('#transcript-molecular-impact tr[data-transcript]').length;
      const initialComparisons=comparisons.length;
      const dialog=shadow.querySelector('#new-acmg-calculator');
      const advanced=shadow.querySelector('#new-acmg-advanced');
      const overview={advancedClosed:!advanced.open,requirementsDeferred:!shadow.querySelector('#new-acmg-requirements'),
        mechanismStatus:shadow.querySelector('[data-mechanism-status]')?.dataset.mechanismStatus,
        summary:shadow.querySelector('#new-acmg-molecular-summary').innerText,
        columns:getComputedStyle(shadow.querySelector('.pvs1-summary-grid')).gridTemplateColumns.split(' ').length,
        noHorizontalOverflow:dialog.scrollWidth<=dialog.clientWidth,
        labelFont:getComputedStyle(shadow.querySelector('.pvs1-summary-grid dt')).fontSize};
      advanced.querySelector('summary').focus();
      document.dispatchEvent(new KeyboardEvent('keydown',{key:'Tab',bubbles:true,cancelable:true}));
      overview.focusWrapped=shadow.activeElement===dialog.querySelector('.dialog-close');
      const reveal=async title=>{
        const section=[...shadow.querySelectorAll('#new-acmg-calculator details')].find(item=>item.dataset.disclosureKey===title);
        if(!section)throw Error('Missing section '+title);
        if(!section.open)section.querySelector('summary').click();
        await until(()=>section.querySelector(':scope > .detail-content')?.childElementCount);
        return section;
      };
      await reveal('Informazioni avanzate');
      const indicatorDetails=await reveal('ClinGen HI e gnomAD pLI');
      overview.indicators=indicatorDetails.innerText;
      await reveal('Requisiti PVS1 e fonti');
      await reveal('Trascritti e calcoli molecolari');
      const selectedMolecularRows=shadow.querySelectorAll('#transcript-molecular-impact tr[data-transcript]').length;
      [...shadow.querySelectorAll('#new-acmg-calculator button')].find(b=>b.textContent==='Analizza tutti i trascritti').click();
      await until(()=>shadow.querySelectorAll('#transcript-molecular-impact tr[data-transcript]').length===3);
      const nmd=shadow.querySelector('[data-requirement-id=nmd]'); nmd.open=true;
      await until(()=>nmd.querySelector('dl'));
      const molecular=shadow.querySelector('#transcript-molecular-impact');
      molecular.querySelector('tbody button').click();
      const result={title:shadow.querySelector('#new-acmg-calculator-title').textContent,
        status:shadow.querySelector('#new-acmg-result').dataset.status, nmd:nmd.innerText,
        predictedBasisVisible:shadow.querySelector('[data-basis=PREDICTED]')?.textContent==='Prodotto predetto',
        initialMolecularRows,initialComparisons,selectedMolecularRows,overview,
        requirements:shadow.querySelectorAll('#new-acmg-requirements details').length,
        transcript:shadow.querySelector('#new-acmg-transcript').selectedOptions[0].textContent,
        hasOtherCriteria:/PS1|PM2|PP3/.test(shadow.querySelector('#new-acmg-calculator').textContent),
        molecularRows:molecular.querySelectorAll('tr[data-transcript]').length,
        selectedTranscript:molecular.querySelector('tr[aria-current=true]').dataset.transcript,
        molecularText:molecular.innerText,
        molecularExpanded:molecular.querySelector('tbody button').getAttribute('aria-expanded')};
      responseIndex=1;
      [...shadow.querySelectorAll('#new-acmg-calculator button')].find(b=>b.textContent==='Valuta PVS1').click();
      await until(()=>shadow.querySelector('#new-acmg-result')?.dataset.status==='NOT_EVALUABLE');
      await reveal('Informazioni avanzate');
      await reveal('Requisiti PVS1 e fonti');
      await reveal('Trascritti e calcoli molecolari');
      await until(()=>shadow.querySelector('[data-requirement-id=mechanism]')?.dataset.status==='UNKNOWN');
      result.missingStatus=shadow.querySelector('#new-acmg-result').dataset.status;
      result.unknownMechanism=shadow.querySelector('[data-mechanism-status]')?.dataset.mechanismStatus;
      result.missingVisible=shadow.querySelector('#new-acmg-result').innerText.includes('Informazioni necessarie mancanti');
      result.comparisons=comparisons;
      result.reusedComparisonRows=shadow.querySelectorAll('#transcript-molecular-impact tr[data-transcript]').length;
      responseIndex=2;
      workspace.detail.annotations[0].consequence='splice_donor_variant';
      [...shadow.querySelectorAll('#new-acmg-calculator button')].find(b=>b.textContent==='Valuta PVS1').click();
      await until(()=>shadow.querySelector('#new-acmg-result')?.dataset.status==='ACTIVE');
      result.spliceOverview=shadow.querySelector('#new-acmg-molecular-summary').innerText;
      result.spliceLabels=[...shadow.querySelectorAll('#new-acmg-molecular-summary dt')].map(item=>item.textContent);
      responseIndex=3;
      [...shadow.querySelectorAll('#new-acmg-calculator button')].find(b=>b.textContent==='Valuta PVS1').click();
      await until(()=>shadow.querySelector('#new-acmg-result')?.dataset.status==='ACTIVE');
      result.crypticOverview=shadow.querySelector('#new-acmg-molecular-summary').innerText;
      result.mechanisms=[];
      for (const [index,status] of [[4,'ACTIVE'],[5,'REQUIRES_REVIEW']]) {
        responseIndex=index;
        [...shadow.querySelectorAll('#new-acmg-calculator button')].find(b=>b.textContent==='Valuta PVS1').click();
        await until(()=>shadow.querySelector('#new-acmg-result')?.dataset.status===status);
        const mechanism=shadow.querySelector('[data-mechanism-status]');
        const information=mechanism.querySelector('button');
        information.focus();
        const tooltip=mechanism.querySelector('[role=tooltip]');
        await until(()=>getComputedStyle(tooltip).visibility==='visible');
        const bounds=tooltip.getBoundingClientRect();
        result.mechanisms.push({state:mechanism.dataset.mechanismStatus,icon:information.textContent,
          tooltip:tooltip.textContent,visible:getComputedStyle(tooltip).visibility,
          described:information.getAttribute('aria-describedby')===tooltip.id,
          source:tooltip.querySelector('a')?.href,withinViewport:bounds.left>=0 && bounds.right<=innerWidth});
      }
      result.requests=[...requests];
      responseIndex=0;
      const chooseContext=async value=>{
        const control=shadow.querySelector('#new-acmg-context');control.value=value;
        control.dispatchEvent(new Event('change',{bubbles:true}));
        await until(()=>shadow.querySelector('#new-acmg-strength'));
      };
      const chooseStrength=async value=>{
        const control=shadow.querySelector('#new-acmg-strength');control.value=value;
        control.dispatchEvent(new Event('change',{bubbles:true}));
        await until(()=>shadow.querySelector('#new-acmg-strength')?.value===value);
      };
      await chooseContext('context-a');
      result.strengthOptions=[...shadow.querySelector('#new-acmg-strength').options].map(option=>option.text);
      result.manualStrengths=[];
      for(const value of ['VERY_STRONG','STRONG','MODERATE','SUPPORTING']){
        await chooseStrength(value);
        result.manualStrengths.push({value,mode:shadow.querySelector('#new-acmg-result').dataset.strengthMode,
          applied:shadow.querySelector('#new-acmg-result').dataset.appliedStrength,
          text:shadow.querySelector('#new-acmg-summary').textContent,
          focused:shadow.activeElement===shadow.querySelector('#new-acmg-strength')});
      }
      [...shadow.querySelectorAll('#new-acmg-calculator button')].find(b=>b.textContent==='Valuta PVS1').click();
      await until(()=>shadow.querySelector('#new-acmg-strength')?.value==='SUPPORTING');
      result.manualRetained=shadow.querySelector('#new-acmg-result').dataset.strengthMode==='MANUAL';
      await chooseContext('context-b');
      result.otherContextAutomatic=shadow.querySelector('#new-acmg-result').dataset.strengthMode==='AUTO';
      await chooseContext('context-a');
      result.originalContextRetained=shadow.querySelector('#new-acmg-strength').value==='SUPPORTING';
      await chooseStrength('NONE');
      result.manualDisabled=shadow.querySelector('#new-acmg-result').dataset.appliedStrength==='NONE'
        && shadow.querySelector('#new-acmg-summary').textContent.includes('Non applicato manualmente');
      await chooseStrength('');
      result.automaticRestored=shadow.querySelector('#new-acmg-result').dataset.strengthMode==='AUTO'
        && shadow.querySelector('#new-acmg-result').dataset.appliedStrength==='VERY_STRONG';
      result.manualRequests=requests.slice(6);
      result.savedReadsBeforeReopen=savedReads.length;
      result.historyInitiallyDeferred=historyRequests.length===0;
      await chooseStrength('MODERATE');
      const note=shadow.querySelector('input[aria-label="Nota della valutazione PVS1"]');
      note.value='Synthetic review';note.dispatchEvent(new Event('input',{bubbles:true}));
      const beforeSave=requests.length;
      shadow.querySelector('#new-acmg-save').click();
      await until(()=>shadow.querySelector('#new-acmg-save-status')?.dataset.saveStatus==='SAVED');
      result.savedWithoutRecalculation=requests.length===beforeSave;
      result.savedStatus=shadow.querySelector('#new-acmg-save-status').textContent;
      await reveal('Informazioni avanzate');
      const history=await reveal('Valutazioni salvate');
      [...history.querySelectorAll('button')].find(b=>b.textContent==='Carica storico').click();
      await until(()=>history.querySelector('dl'));
      result.savedHistoryText=history.textContent;
      const reopen=async()=>{
        document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
        delete workspace.pvs1StrengthOverrides;
        button.click();await until(()=>shadow.querySelector('#new-acmg-strength'));
        await chooseContext('context-a');
      };
      await reopen();
      result.persistedRestored=shadow.querySelector('#new-acmg-strength').value==='MODERATE'
        && shadow.querySelector('input[aria-label="Nota della valutazione PVS1"]').value==='Synthetic review';
      staleSources=true;
      await reopen();
      result.staleChoiceRetained=savedByContext.get('context-a').snapshot.strength_override.strength==='MODERATE';
      result.staleWarning=shadow.querySelector('#new-acmg-save-status').textContent;
      result.staleNotReapplied=shadow.querySelector('#new-acmg-strength').value==='';
      result.saveCount=saves.length;
      document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
      result.closed=shadow.querySelector('#new-acmg-calculator')===null;
      result.focusRestored=shadow.activeElement===button;
      const {renderTranscriptMolecularImpact}=await import(new URL('./acmg-calculator.js',__MODULE__));
      const splicePanel=renderTranscriptMolecularImpact(host,{scope:'SELECTED',transcripts:[{
        transcript:__TX__,status:'SPLICE_SCENARIO',conditional:true,
        product_resolution:{status:'CONDITIONAL',method:'CANONICAL_SPLICE_SCENARIO'},
        splice_analysis:{site:{type:'DONOR',exon:25,native_motif:'GT',altered_motif:'AC'},
          scenarios:[{event:{involved_exons:[25]},frame_effect:'OUT_OF_FRAME',rna_deleted_nt:170,coding_deleted_nt:170,
            nmd_predicted:true,nmd_distance_nt:5231}]}
      }]});
      shadow.append(splicePanel);splicePanel.querySelector('tbody button').click();
      result.spliceFrame=splicePanel.querySelector('tbody tr').cells[4].textContent;
      result.spliceColumns=splicePanel.querySelector('thead tr').cells.length;
      result.spliceText=splicePanel.textContent;splicePanel.remove();
      const crypticPanel=renderTranscriptMolecularImpact(host,{scope:'SELECTED',transcripts:[{
        transcript:__TX__,status:'SPLICE_SCENARIO',conditional:true,
        product_resolution:{status:'CONDITIONAL',method:'SPLICEAI_CRYPTIC_SCENARIO'},
        splice_analysis:{site:{type:'DONOR',exon:25,native_motif:'GT',altered_motif:'AT'},
          prediction:{threshold:0.5,records:[{DS_DL:0.95,DS_DG:0.9,DS_AL:0,DS_AG:0}],
            gained_site:{genomic_position:108153631,motif:'GT'},issues:[]},
          scenarios:[{event:{event_type:'CRYPTIC_SITE',involved_exons:[25]},frame_effect:'OUT_OF_FRAME',
            rna_deleted_nt:0,coding_deleted_nt:0,rna_inserted_nt:25,coding_inserted_nt:25,nmd_predicted:true}]}
      }]});
      shadow.append(crypticPanel);crypticPanel.querySelector('tbody button').click();
      result.crypticText=crypticPanel.innerText;crypticPanel.remove();
      return result;
    """.replace('__RESPONSES__', json.dumps(responses)).replace('__MODULE__', json.dumps(module)).replace('__TX__', json.dumps(TX)).replace('__GENE__', json.dumps(GENE))
    page = tmp_path / "pvs1-browser.html"
    page.write_text('<!doctype html><variant-browser></variant-browser><pre id="pvs1-check"></pre><script type="module">'
                    '(async()=>{' + script + '})().then(value=>document.querySelector("#pvs1-check").textContent=JSON.stringify(value))'
                    '.catch(error=>document.querySelector("#pvs1-check").textContent=JSON.stringify({error:error.stack}));</script>')
    browser = subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--disable-background-networking",
                              f"--window-size={viewport[0]},{viewport[1]}", "--force-device-scale-factor=1",
                              "--allow-file-access-from-files", "--user-data-dir=" + str(tmp_path / "chrome"),
                              "--dump-dom", "--virtual-time-budget=10000", page.as_uri()], capture_output=True, text=True, timeout=30)
    class CheckParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.collect, self.value = False, ''
        def handle_starttag(self, tag, attrs):
            if tag == 'pre' and dict(attrs).get('id') == 'pvs1-check':
                self.collect = True
        def handle_endtag(self, tag):
            if tag == 'pre':
                self.collect = False
        def handle_data(self, data):
            if self.collect:
                self.value += data
    parser = CheckParser()
    parser.feed(browser.stdout)
    if browser.returncode != 0 and not parser.value and "Operation not permitted" in browser.stderr:
        pytest.skip("Sandbox blocks Chrome socket setup; no browser UI verification performed")
    assert parser.value, browser.stderr[-2000:]
    result = json.loads(parser.value)
    assert 'error' not in result, result
    assert result['title'] == 'PVS1' and result['status'] == 'ACTIVE'
    assert result['predictedBasisVisible']
    assert result['requirements'] >= 12 and '50' in result['nmd'] and SOURCE in result['nmd']
    assert TX in result['transcript'] and not result['hasOtherCriteria']
    assert result['molecularRows'] == 3 and result['selectedTranscript'] == TX
    assert result['initialMolecularRows'] == 0 and result['initialComparisons'] == 0
    assert result['selectedMolecularRows'] == 1
    assert result['overview']['advancedClosed'] and result['overview']['requirementsDeferred']
    assert result['overview']['mechanismStatus'] == 'PROVEN' and result['unknownMechanism'] == 'UNKNOWN'
    inferred, discordant = result['mechanisms']
    assert inferred['state'] == 'INFERRED' and discordant['state'] == 'DISCORDANT'
    assert all(item['icon'] == '⚠' and item['visible'] == 'visible' and item['described'] and item['withinViewport']
               for item in result['mechanisms']), result['mechanisms']
    assert inferred['tooltip'] == 'ClinGen Dosage · HI=3'
    assert inferred['source'] == 'https://example.test/clingen/hi'
    assert discordant['tooltip'] == 'ClinGen Dosage · HI=3GenCC · SGC-CONFLICT'
    assert 'ClinGen HI' not in result['overview']['summary'] and 'gnomAD pLI' not in result['overview']['summary']
    assert '500 / 100 aa (80,00% in meno)' in result['overview']['summary']
    assert '0 / 1503 nt (0,00%)' in result['overview']['summary'] and '2 di 3' in result['overview']['summary']
    assert 'Evidenze sufficienti' in result['overview']['indicators']
    assert 'Un pLI basso non esclude LoF' in result['overview']['indicators']
    assert 'ENST00000000002' in result['overview']['indicators'] and 'Non documentata' in result['overview']['indicators']
    assert result['overview']['noHorizontalOverflow'] and result['overview']['focusWrapped']
    assert result['overview']['labelFont'] == '11px'
    assert result['overview']['columns'] == (2 if viewport[0] > 650 else 1)
    assert all(text in result['overview']['summary'] for text in ('Frame', 'NMD', 'Previsto'))
    assert len(result['comparisons']) == 1 and result['reusedComparisonRows'] == 3
    assert result['molecularExpanded'] == 'true' and '80.00% non tradotta' in result['molecularText']
    assert 'Determinato dalla sequenza' in result['molecularText'] and 'Verifica dei codoni modificati' in result['molecularText']
    assert 'NON_CODING' in result['molecularText'] and 'INSUFFICIENT_DATA' in result['molecularText']
    assert result['missingStatus'] == 'NOT_EVALUABLE' and result['missingVisible']
    assert result['closed'] and result['focusRestored']
    assert all(text in result['spliceText'] for text in ('Scenario splice condizionale', 'GT / AC', '170 / 170',
                                                       'predetto, non osservato', 'Siti criptici',
                                                       'NMD del prodotto ipotizzato', 'Previsto', '5231 nt'))
    assert result['spliceFrame'] == 'Out of frame' and result['spliceColumns'] == 8
    assert result['spliceLabels'] == ['Variante sul trascritto', 'Tipo di variante', 'Evento predetto', 'Esoni', 'Frame',
                                      'NMD', 'Meccanismo', 'Proteina reference / predetta', 'CDS rimossa']
    assert all(text in result['spliceOverview'] for text in ('Splice canonica · donatore', 'Exon skipping', '24, 25, 26 di 32',
        'Out of frame', '3056 / 1195 aa (60,90% in meno)', '170 / 9171 nt (1,85%)'))
    assert 'Utilizzo di sito criptico' in result['crypticOverview'] and '0 / 9171 nt (0,00%)' in result['crypticOverview']
    assert 'Scenario esplorativo: delta SpliceAI sotto soglia' in result['crypticOverview']
    assert all(text in result['crypticText'] for text in ('Scenario predetto da sito criptico SpliceAI', 'Sito criptico · esone 25',
        "Nucleotidi inclusi nell'RNA / nella CDS", '25 / 25', '0.95 / 0.9', '108153631'))
    assert 'Salto dell\'esone' not in result['crypticText'] and 'Siti criptici, ritenzione intronica' not in result['crypticText']
    assert len(result['requests']) == 6 and all(body['transcript'] == TX for body in result['requests'])
    assert result['strengthOptions'] == ['Automatico (Very Strong)', 'Very Strong', 'Strong', 'Moderate', 'Supporting', 'Non applicare']
    assert all(item['mode'] == 'MANUAL' and item['applied'] == item['value'] and item['focused']
               and 'Calcolata: Very Strong' in item['text'] and '(manuale)' in item['text'] for item in result['manualStrengths'])
    assert result['manualRetained'] and result['otherContextAutomatic'] and result['originalContextRetained']
    assert result['manualDisabled'] and result['automaticRestored']
    assert [request['strength_override'] for request in result['manualRequests']] == [
        None, 'VERY_STRONG', 'STRONG', 'MODERATE', 'SUPPORTING', 'SUPPORTING', None, 'SUPPORTING', 'NONE', None]
    assert result['savedReadsBeforeReopen'] == 3 and result['historyInitiallyDeferred']
    assert result['savedWithoutRecalculation'] and 'rev. 1' in result['savedStatus']
    assert 'Synthetic review' in result['savedHistoryText'] and 'Moderate' in result['savedHistoryText']
    assert result['persistedRestored'] and result['saveCount'] == 1
    assert result['staleChoiceRetained'] and result['staleNotReapplied']
    assert 'dati aggiornati' in result['staleWarning'] and 'Moderate (manuale)' in result['staleWarning']
