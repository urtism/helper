"""Task 28A synthetic source fixtures, never clinical evidence."""

import pytest

from helper_next.core import acmg_mechanism_normalizer as norm
from helper_next.core.acmg_mechanism_assessment import assess
from helper_next.core.acmg_mechanism_models import SourcePacket, SourceState
from helper_next.core.acmg_client import digest
from test_acmg_mechanisms import g2p, gencc, packets


def matrix(rows, requirement="AD"):
    data = packets(rows)
    records = [(SourcePacket.parse_obj(packet), row, f"fixture:{source}:{index}")
               for source, packet in data.items() for index, row in enumerate(packet["records"])]
    return norm.analyze(norm.identity("HGNC:1", "MONDO:1", requirement), records,
                        [SourceState(source=s, status=p["status"]) for s, p in data.items()])


def test_explicit_g2p_lof_is_definitive_but_not_human_approved():
    result = assess(matrix({"g2p": [g2p()]}))
    assert result.mechanism_confidence == "DEFINITIVE"
    assert result.mechanism_scope == "DISEASE_SPECIFIC" and result.gene_disease_association_status == "CURATED"
    assert result.supporting_evidence[0].source_record_id == "G2P-1"
    assert "not independent clinical validation" in result.limitations[1]


def test_gencc_validity_and_g2p_unknown_do_not_invent_a_mechanism():
    for rows in ({"gencc": [gencc()]}, {"g2p": [g2p(mechanism="unknown")]}):
        result = assess(matrix(rows))
        assert result.gene_disease_association_status == "CURATED"
        assert result.mechanism_confidence == "UNKNOWN" and result.mechanism == "UNKNOWN"


def test_isolated_constraint_is_unknown():
    result = assess(matrix({"gnomad": [{"gene_id":"HGNC:1", "gene_symbol":"GENE_X", "loeuf":0.01}]}))
    assert result.mechanism_confidence == "UNKNOWN"
    assert result.assertions == []


def dosage_matrix():
    result = matrix({"clingen_dosage":[{"gene_id":"1", "gene_symbol":"GENE_X", "assessment":"haploinsufficiency", "hi_score":"3"}]})
    # Qualified-gene-identity fixture; production must provide its own verified crosswalk.
    qualified = result.contextual_evidence[0].copy(update={"gene_id":"HGNC:1", "applicability":"GENE_LEVEL"})
    return result.copy(update={"contextual_evidence":[qualified]})


def test_sufficient_dosage_supports_only_gene_level_inference():
    result = assess(dosage_matrix())
    assert result.mechanism == "LOSS_OF_FUNCTION" and result.mechanism_confidence == "INFERRED"
    assert result.mechanism_scope == "GENE_LEVEL"
    assert result.gene_disease_association_status == "NOT_FOUND"
    assert result.provenance["inference_rules"]


def test_disease_specific_indirect_inference_requires_qualified_disease_and_mode():
    m = dosage_matrix()
    # Explicit adapter-scope fixture; current production dosage index lacks this qualification.
    qualified = m.contextual_evidence[0].copy(update={"applicability":"EXACT", "allelic_requirement":"AUTOSOMAL_DOMINANT", "disease_ids":["MONDO:1"]})
    m = m.copy(update={"contextual_evidence":[qualified]})
    result = assess(m)
    assert result.mechanism_confidence == "INFERRED" and result.mechanism_scope == "DISEASE_SPECIFIC"
    assert result.gene_disease_association_status == "INFERRED"


def test_real_conflict_preserves_each_assertion_record_and_source():
    result = assess(matrix({"g2p":[g2p(), g2p("G2P-2", mechanism="gain of function")]}))
    assert result.mechanism_confidence == "DISPUTED"
    assert result.gene_disease_association_status == "CURATED"
    assert {a.mechanism for a in result.assertions} == {"LOSS_OF_FUNCTION", "GAIN_OF_FUNCTION"}
    assert {e.source_record_id for e in result.conflicting_evidence} == {"G2P-1", "G2P-2"}


def test_other_disease_does_not_supply_target_mechanism():
    result = assess(matrix({"g2p":[g2p(disease="MONDO:2")]}))
    assert result.mechanism_confidence == "UNKNOWN" and result.gene_disease_association_status == "NOT_FOUND"


@pytest.mark.parametrize("requirement,expected", [("AD","LOSS_OF_FUNCTION"), ("AR","GAIN_OF_FUNCTION"), ("X_LINKED_RECESSIVE","DOMINANT_NEGATIVE")])
def test_inheritance_scopes_do_not_conflict(requirement, expected):
    result = assess(matrix({"g2p":[g2p(), g2p("G2P-2", mechanism="gain of function", requirement="biallelic_autosomal"),
                                   g2p("G2P-3", mechanism="dominant negative", requirement="monoallelic_X_hemizygous")]}, requirement))
    assert result.mechanism == expected and result.mechanism_confidence == "DEFINITIVE"
    assert not result.conflicting_evidence


def test_ambiguous_mapping_and_unknown_mode_cannot_become_definitive():
    m = matrix({"g2p":[g2p()]})
    ambiguous = m.direct_evidence[0].copy(update={"applicability":"AMBIGUOUS_DISEASE_MAPPING"})
    result = assess(m.copy(update={"direct_evidence":[], "contextual_evidence":[ambiguous], "mapping_uncertainty":["AMBIGUOUS"]}))
    assert result.mechanism_confidence == "UNKNOWN" and result.gene_disease_association_status == "AMBIGUOUS"
    assert result.mapping_uncertainty == ["AMBIGUOUS"]
    assert assess(matrix({"g2p":[g2p()]}, None)).mechanism_confidence == "UNKNOWN"


def test_exact_non_lof_mechanism_is_not_replaced_by_gene_level_lof():
    m = matrix({"g2p":[g2p(mechanism="gain of function")]})
    m = m.copy(update={"contextual_evidence":dosage_matrix().contextual_evidence})
    result = assess(m)
    assert result.mechanism == "GAIN_OF_FUNCTION" and result.mechanism_confidence == "DEFINITIVE"
    assert any(a.mechanism == "LOSS_OF_FUNCTION" and a.scope == "GENE_LEVEL" for a in result.assertions)


def vcep_record(base, mechanism="GAIN_OF_FUNCTION", **changes):
    # Synthetic archived official-specification fixture, never a production assertion.
    raw = {"source_url": "https://clinicalgenome.org/fixture-only/specification",
           "molecular_mechanism_statement": mechanism}
    return base.copy(update={"evidence_id": "fixture-vcep-" + mechanism, "source": "clingen_vcep",
        "source_record_id": "FIXTURE-VCEP", "source_record_version": "1.2.0",
        "source_review_status": "APPROVED", "asserted_mechanism": mechanism,
        "original_mechanism": mechanism, "raw_assertion": raw, "source_record_hash": digest(raw)["value"],
        **changes})


@pytest.mark.parametrize("mechanism", ["GAIN_OF_FUNCTION", "DOMINANT_NEGATIVE", "OTHER"])
def test_approved_explicit_vcep_has_priority_and_keeps_conflicts(mechanism):
    m = matrix({"g2p": [g2p()]})
    vcep = vcep_record(m.direct_evidence[0], mechanism)
    m = m.copy(update={"direct_evidence": [*m.direct_evidence, vcep],
                       "contextual_evidence": dosage_matrix().contextual_evidence})
    before = m.dict()
    result = assess(m)
    assert m.dict() == before
    assert result.mechanism == mechanism and result.mechanism_confidence == "DEFINITIVE"
    assert any(e.source == "g2p" for e in result.conflicting_evidence)
    assert result.provenance["selected_vcep_specifications"][0]["version"] == "1.2.0"
    assert any("review is required" in limitation for limitation in result.limitations)


@pytest.mark.parametrize("changes", [
    {"source_review_status": "DRAFT"}, {"source_record_version": None},
    {"original_mechanism": None}, {"source_record_hash": "mismatched"},
    {"evidence_category": "OTHER"}, {"disease_ids": ["MONDO:2"]},
    {"allelic_requirement": "AUTOSOMAL_RECESSIVE"},
])
def test_vcep_profile_unqualified_statement_or_other_scope_has_no_priority(changes):
    m = matrix({"g2p": [g2p()]})
    m = m.copy(update={"direct_evidence": [*m.direct_evidence, vcep_record(m.direct_evidence[0], **changes)]})
    result = assess(m)
    assert result.mechanism == "LOSS_OF_FUNCTION" and result.mechanism_confidence == "DEFINITIVE"
    assert result.provenance["selected_vcep_specifications"] == []


def test_incompatible_approved_vcep_statements_remain_disputed():
    m = matrix({"g2p": [g2p()]})
    m = m.copy(update={"direct_evidence": [vcep_record(m.direct_evidence[0], mechanism)
        for mechanism in ["GAIN_OF_FUNCTION", "DOMINANT_NEGATIVE"]]})
    result = assess(m)
    assert result.mechanism_confidence == "DISPUTED"
    assert len(result.conflicting_evidence) == 2


def test_contradictory_only_record_is_preserved_without_becoming_positive_support():
    m = matrix({"g2p": [g2p()]})
    negative = m.direct_evidence[0].copy(update={"evidence_direction": "CONTRADICTING"})
    result = assess(m.copy(update={"direct_evidence": [], "contradictory_evidence": [negative]}))
    assert result.mechanism_confidence == "UNKNOWN"
    assert result.supporting_evidence == [] and result.conflicting_evidence == [negative]


def test_assembler_preserves_assessment_and_provenance_in_real_engine_contract(tmp_path, monkeypatch, engine):
    from helper_next.core.acmg_evidence import EvidenceAssembler
    from helper_next.core.acmg_pvs1 import transform
    from test_acmg_pvs1 import bundle, provider, document
    manager, _ = provider(tmp_path, bundle())
    src = manager.get("ENST000001.1", "GRCh38", fetch=True)
    doc = document(tmp_path, monkeypatch, src["data"])
    snapshot = doc["normalized_evidence"]["snapshot"]
    assessment = assess(matrix({"g2p":[g2p()]}))
    transformed = transform(snapshot["variant"]["identity"], doc["original_vcf_evidence"]["annotations"][0],
                            snapshot["context"], src, [], assessment)
    snapshot["evidence"].append(transformed["evidence"])
    result = EvidenceAssembler(engine).assemble(doc, originals={transformed["evidence"]["id"]:transformed["original"]})
    assert not result["errors"], result["errors"]
    assert result["contract"]["schema_version"] == "evidence-contract-1.1"
    envelope = next(e for e in result["contract"]["evidence"] if e["value"]["kind"] == "PVS1")
    import json
    value = envelope["value"]["observation"]["mechanism"]["confidence_assessment"]
    assert value["mechanism_confidence"] == "DEFINITIVE"
    assert json.loads(value["source_evidence_json"])[0]["source_record_ref"] == assessment.supporting_evidence[0].source_record_ref
    assert json.loads(value["provenance_json"]) == assessment.provenance
    assert envelope["validation_status"] == "UNVERIFIED"
    assert any("verification" in item["path"] for item in transformed["missing_evidence"])


def test_assembler_does_not_relabel_an_assessment_for_different_inheritance(tmp_path):
    from helper_next.core.acmg_pvs1 import transform
    from test_acmg_pvs1 import bundle, provider, case, CONTEXT
    manager, _ = provider(tmp_path, bundle())
    src = manager.get("ENST000001.1", "GRCh38", fetch=True)
    identity, annotation = case(src["data"])
    assessment = assess(matrix({"g2p":[g2p(requirement="biallelic_autosomal")]}, "AR"))
    context = {"gene":CONTEXT["gene"], "disease":CONTEXT["disease"], "gene_disease":{"inheritance_modes":["AUTOSOMAL_DOMINANT"]}}
    result = transform(identity, annotation, context, src, [], assessment)
    assert "confidence_assessment" not in result["evidence"]["observation"]["mechanism"]
    assert result["original"]["rejected_mechanism_assessment"] == assessment.dict()
    assert any("does not match" in m["reason"] for m in result["missing_evidence"])


from test_acmg_evidence import engine  # Authoritative validator runs in its separate runtime.
