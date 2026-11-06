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
    assert result.ruleset_id == "PVS1_GENERAL" and result.ruleset_version == "1.1.0"
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
    assert result.applied_strength is None and result.calculated_strength is None
    assert product["basis"] == basis
    if basis == "PREDICTED":
        assert result.status == "REQUIRES_REVIEW"
        assert trace(result)["splice_scenarios"]["status"] == "NOT_EVALUATED"
        assert trace(result)["rna_quality"]["status"] == "NOT_APPLICABLE"
    elif basis == "OBSERVED":
        assert result.status == "REQUIRES_REVIEW"
        assert trace(result)["rna_quality"]["status"] == "NOT_EVALUATED"
        assert trace(result)["splice_basis"]["source"] == [SOURCE]
    else:
        assert result.status == "NOT_EVALUABLE"


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


@pytest.mark.parametrize("field", ["molecular_mechanism", "confidence", "disease", "inheritance", "scope"])
def test_missing_mechanism_or_context_never_becomes_negative(field):
    sample = sample_fixture()
    sample.disease_context.pop(field)
    result = calculate_pvs1(sample)
    assert result.status == "NOT_EVALUABLE" and result.applied_strength is None
    assert result.missing_data
    assert trace(result)["nmd"]["status"] == "PASS"  # Known technical facts still inspected.


def test_documented_nonlof_is_inactive_but_inferred_lof_requires_review():
    sample = sample_fixture()
    sample.disease_context["molecular_mechanism"] = "GoF"
    result = calculate_pvs1(sample)
    assert result.status == "INACTIVE" and result.applied_strength is None
    assert trace(result)["mechanism"]["status"] == "FAIL"
    assert trace(result)["nmd"]["status"] == "NOT_EVALUATED"
    sample.disease_context.update(molecular_mechanism="LoF", confidence="INFERRED")
    assert calculate_pvs1(sample).status == "REQUIRES_REVIEW"


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
        assert result.status == "REQUIRES_REVIEW" and result.applied_strength is None
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
    from helper_next.api import acmg_calculator as api
    record = dict(id="G2P-SYNTHETIC", gene_id="HGNC:999999", disease_id="MONDO:9999999", disease_mim="OMIM:999999",
                  disease_name="Synthetic disease", mechanism="loss of function", original_mechanism="loss of function",
                  confidence="definitive", accepted=True, allelic_requirement="biallelic_autosomal",
                  url="https://example.test/g2p/synthetic", publications="PMID:synthetic", last_reviewed="2026-01-01")
    association = dict(disease_id=record["disease_id"], disease=record["disease_name"],
                       assertions=[dict(id="SGC-synthetic", gene_id=record["gene_id"], inheritance="Autosomal recessive")])
    knowledge = dict(gene_identifiers=[record["gene_id"]], associations=[association], g2p_records=[record],
                     cache=dict(status="ready", updated_at="synthetic-cache-v1"))
    monkeypatch.setattr(acmg_context.gene_phenotype, "query_gene", lambda *args: copy.deepcopy(knowledge))
    monkeypatch.setattr(api.TranscriptReferenceProvider, "get", lambda *args, **kwargs: {"data": None})
    return knowledge


def test_local_g2p_association_mechanism_and_sources_reach_new_calculator(local_g2p):
    from helper_next.api import acmg_calculator as api
    detail = detail_fixture()
    detail["annotations"][0]["consequence"] = "splice_donor_variant"
    choice = api.acmg_context.build(detail)["annotations"][0]["contexts"][0]
    sample, _, _ = api.prepare_pvs1_input(detail, detail["annotations"][0], choice)
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
    sample, _, _ = api.prepare_pvs1_input(detail, detail["annotations"][0], choice)
    assert sample.disease_context["molecular_mechanism"] == "LoF"
    assert local_g2p == before


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
    sample, _, _ = api.prepare_pvs1_input(detail, detail["annotations"][0], choice)
    assert sample.disease_context["molecular_mechanism"] == "UNKNOWN"
    assert not sample.disease_context.get("source_refs", {}).get("molecular_mechanism")


def test_unidentified_g2p_disease_is_not_matched_by_name(local_g2p):
    from helper_next.api import acmg_calculator as api
    local_g2p["g2p_records"][0].update(disease_id="", disease_mim="")
    detail = detail_fixture()
    choices = api.acmg_context.build(detail)["annotations"][0]["contexts"]
    assert len(choices) == 1
    sample, _, warnings = api.prepare_pvs1_input(detail, detail["annotations"][0], choices[0])
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
    sample, _, _ = api.prepare_pvs1_input(detail, detail["annotations"][0], choice)
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


def test_annotation_first_adapter_uses_numerical_stop_and_cache_only_when_available(monkeypatch):
    from helper_next.api import acmg_calculator as api
    from unittest.mock import patch
    monkeypatch.setattr(api.TranscriptReferenceProvider, "get", lambda *args, **kwargs: {"data": reference_fixture()})
    detail = detail_fixture()
    with patch.object(api, "compute_molecular_evidence", wraps=api.compute_molecular_evidence) as molecular:
        sample, origin, _ = api.prepare_pvs1_input(detail, detail["annotations"][0])
        molecular.assert_not_called()
    assert origin == "VEP_STOP_ANNOTATION"
    assert sample.molecular_effect["products"][0]["ptc_start"] == 7
    result = calculate_pvs1(sample)
    assert result.status == "NOT_EVALUABLE" and trace(result)["nmd"]["status"] == "PASS"
    assert "biologically_relevant" not in sample.transcript
    detail["annotations"][0].update(hgvsp="", metadata={"fields": {"Gene": GENE}})
    with patch.object(api, "compute_molecular_evidence", wraps=api.compute_molecular_evidence) as molecular:
        sample, origin, _ = api.prepare_pvs1_input(detail, detail["annotations"][0])
        molecular.assert_called_once()
    assert origin == "TRANSCRIPT_CACHE" and sample.molecular_effect["products"][0]["ptc_start"] == 7
    monkeypatch.setattr(api.TranscriptReferenceProvider, "get", lambda *args, **kwargs: {"data": None})
    sample, origin, warnings = api.prepare_pvs1_input(detail, detail["annotations"][0])
    assert origin == "ANNOTATION_ONLY" and sample.molecular_effect is None
    assert any("nessun download" in warning for warning in warnings)


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
    monkeypatch.setattr(api.TranscriptReferenceProvider, "get", lambda *args, **kwargs: pytest.fail("Existing PVS1 input must not fetch reference"))
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
def test_new_calculator_panel_opens_and_explains_requirements(tmp_path):
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
        response["molecular_impact"] = {"gene": GENE, "assembly": "GRCh38", "release": "116", "catalog_complete": True,
            "transcripts": [
                {"transcript": TX, "status": "AFFECTED_CODING", "selected": True, "consequence": "stop_gained",
                 "cds_length_nt": 1503, "cds_position": 301, "first_affected_reference_codon": 101,
                 "reference_cds_untranslated_percent": 80, "protein_impact_percent": 80, "physical_cds_deleted_percent": 0,
                 "nmd_predicted": True, "formulas": {"stop_gain": "100 * (500 - 101 + 1) / 500"}},
                {"transcript": "ENST00000000002.1", "status": "NON_CODING", "consequence": "non_coding_transcript_variant"},
                {"transcript": "ENST00000000003.1", "status": "INSUFFICIENT_DATA", "missing_data": ["Incomplete CDS"]},
            ]}
    module = (root / "helper_next/src/helper_variants/web/static/variant-browser.js").as_uri()
    script = r"""
      const until=async f=>{for(let n=0;n<200;n++){if(f())return;await new Promise(r=>setTimeout(r,10));}throw Error('UI timed out');};
      const requests=[]; let incomplete=false;
      const originalFetch=window.fetch.bind(window);
      window.fetch=async(url,options={})=>{
        if(String(url)==='/api/acmg-calculator/pvs1'){
          const body=JSON.parse(options.body);requests.push(body);
          return new Response(JSON.stringify(RESPONSES[incomplete?1:0]),{status:200,headers:{'Content-Type':'application/json'}});
        }
        if(String(url).startsWith('/api/acmg'))throw Error('Legacy ACMG API called');
        if(String(url).startsWith('/api/'))return new Response('{"runs":[],"items":[]}',{status:200});
        return originalFetch(url,options);
      };
      await import(MODULE);
      const host=document.querySelector('variant-browser');
      const workspace={key:'synthetic',runId:'synthetic',sample:{sample_id:1},items:[{variant_id:1,transcript:TX}],
        detail:{variant_id:1,reference_build:'GRCh38',chromosome:'1',position:1100,reference:'C',alternate:'T',
          calls:[],annotations:[{id:7,gene:GENE,transcript:TX,consequence:'stop_gained',hgvsc:'c.100C>T',hgvsp:'p.Gln34Ter'}]}};
      host.shadowRoot.append(host.renderDetail(workspace));
      const button=host.shadowRoot.querySelector('.new-acmg-open');button.focus();button.click();
      await until(()=>host.shadowRoot.querySelector('#new-acmg-requirements'));
      const shadow=host.shadowRoot;
      const nmd=shadow.querySelector('[data-requirement-id=nmd]'); nmd.open=true;
      const molecular=shadow.querySelector('#transcript-molecular-impact');
      molecular.querySelector('tbody button').click();
      const result={title:shadow.querySelector('#new-acmg-calculator-title').textContent,
        status:shadow.querySelector('#new-acmg-result').dataset.status, nmd:nmd.innerText,
        requirements:shadow.querySelectorAll('#new-acmg-requirements details').length,
        transcript:shadow.querySelector('#new-acmg-transcript').selectedOptions[0].textContent,
        hasOtherCriteria:/PS1|PM2|PP3/.test(shadow.querySelector('#new-acmg-calculator').textContent),
        molecularRows:molecular.querySelectorAll('tr[data-transcript]').length,
        selectedTranscript:molecular.querySelector('tr[aria-current=true]').dataset.transcript,
        molecularText:molecular.innerText,
        molecularExpanded:molecular.querySelector('tbody button').getAttribute('aria-expanded')};
      incomplete=true;
      [...shadow.querySelectorAll('#new-acmg-calculator button')].find(b=>b.textContent==='Valuta PVS1').click();
      await until(()=>shadow.querySelector('[data-requirement-id=mechanism]')?.dataset.status==='UNKNOWN');
      result.missingStatus=shadow.querySelector('#new-acmg-result').dataset.status;
      result.missingVisible=shadow.querySelector('#new-acmg-result').innerText.includes('Informazioni necessarie mancanti');
      result.requests=requests;
      document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
      result.closed=shadow.querySelector('#new-acmg-calculator')===null;
      result.focusRestored=shadow.activeElement===button;
      return result;
    """.replace('RESPONSES', json.dumps(responses)).replace('MODULE', json.dumps(module)).replace('TX', json.dumps(TX)).replace('GENE', json.dumps(GENE))
    page = tmp_path / "pvs1-browser.html"
    page.write_text('<!doctype html><variant-browser></variant-browser><pre id="pvs1-check"></pre><script type="module">'
                    '(async()=>{' + script + '})().then(value=>document.querySelector("#pvs1-check").textContent=JSON.stringify(value))'
                    '.catch(error=>document.querySelector("#pvs1-check").textContent=JSON.stringify({error:error.stack}));</script>')
    browser = subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--disable-background-networking",
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
    assert result['title'] == 'ACMG Calculator' and result['status'] == 'ACTIVE'
    assert result['requirements'] >= 12 and '50' in result['nmd'] and SOURCE in result['nmd']
    assert TX in result['transcript'] and not result['hasOtherCriteria']
    assert result['molecularRows'] == 3 and result['selectedTranscript'] == TX
    assert result['molecularExpanded'] == 'true' and '80.00% non tradotta' in result['molecularText']
    assert 'NON_CODING' in result['molecularText'] and 'INSUFFICIENT_DATA' in result['molecularText']
    assert result['missingStatus'] == 'NOT_EVALUABLE' and result['missingVisible']
    assert result['closed'] and result['focusRestored']
    assert len(result['requests']) == 2 and all(body['transcript'] == TX for body in result['requests'])
