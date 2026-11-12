"""Task 28A synthetic source fixtures, never clinical evidence."""

import pytest

from helper_next.core import acmg_mechanism_normalizer as norm
from helper_next.core.acmg_mechanism_assessment import assess
from helper_next.core.acmg_mechanism_models import SourcePacket, SourceState
from helper_next.core.acmg_digest import digest
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


@pytest.mark.parametrize("classification, status", [
    ("Disputed Evidence", "DISPUTED"), ("Refuted Evidence", "DISPUTED"),
    ("Strong", "CURATED"), ("Limited", "CURATED"), ("No Known Disease Relationship", "CURATED"),
])
def test_gencc_original_validity_labels_are_recognized_without_creating_mechanisms(classification, status):
    result = assess(matrix({"gencc": [dict(gencc(), classification_title=classification)]}))
    assert result.gene_disease_association_status == status
    assert result.mechanism == "UNKNOWN" and not result.assertions


def test_isolated_constraint_is_unknown():
    result = assess(matrix({"gnomad": [{"gene_id":"HGNC:1", "gene_symbol":"GENE_X", "loeuf":0.01}]}))
    assert result.mechanism_confidence == "UNKNOWN"
    assert result.assertions == []


def indicator_row(metric, value, **changes):
    row = {"gene_symbol": "GENE_X", "gene_id": "123" if metric == "HI" else "ENSG000001",
           "gene_mapping": {"method": "LOCAL_CURATED_UNIQUE_SYMBOL", "gene_id": "HGNC:1",
                            "gene_symbol": "GENE_X", "source_urls": ["https://example.test/curated"]}}
    if metric == "HI":
        row.update(assessment="haploinsufficiency", hi_score=value, report_url="https://example.test/HI")
    else:
        row.update(pli=value, transcript_id="ENST000001.1", available=1, canonical=True,
                   constraint_flags=[], gene_flags=[], lof_expected=25, release="synthetic-1")
    return dict(row, **changes)


@pytest.mark.parametrize("score,interpretation", [(0, "NO_EVIDENCE"), (1, "LITTLE_EVIDENCE"),
    (2, "SOME_EVIDENCE"), (3, "SUFFICIENT_EVIDENCE"), (30, "RECESSIVE_DISEASE"), (40, "DOSAGE_UNLIKELY"),
    (None, "UNAVAILABLE"), ("", "UNAVAILABLE"), ("nan", "UNAVAILABLE"), (99, "UNAVAILABLE"), (True, "UNAVAILABLE")])
def test_hi_codes_are_categories_not_a_numeric_ranking(score, interpretation):
    result = assess(matrix({"clingen_dosage": [indicator_row("HI", score)]}))
    indicator, = result.gene_level_indicators
    assert indicator["interpretation"] == interpretation
    assert indicator["supports_lof"] == (score == 3)
    assert bool(result.assertions) == (score == 3)
    assert result.mechanism_confidence == ("INFERRED" if score == 3 else "UNKNOWN")
    assert result.contextual_evidence[0].raw_assertion["hi_score"] == score


@pytest.mark.parametrize("pli,support", [(0, False), (0.8999, False), (0.9, True), (1, True),
    (None, False), ("nan", False), ("bad", False), (1.01, False), (-0.01, False), (True, False)])
def test_qualified_pli_infers_only_gene_level_lof_intolerance(pli, support):
    result = assess(matrix({"gnomad": [indicator_row("pLI", pli)]}))
    indicator, = result.gene_level_indicators
    assert indicator["supports_lof"] is support
    assert bool(result.assertions) is support
    assert result.mechanism_confidence == ("INFERRED" if support else "UNKNOWN")
    if support:
        assert result.mechanism_scope == "GENE_LEVEL"
        assert result.gene_disease_association_status == "NOT_FOUND"
        assert result.supporting_evidence[0].source == "gnomad"


@pytest.mark.parametrize("changes,issue", [
    ({"constraint_flags": ["lof_too_many"]}, "QUALITY_FLAGS"),
    ({"gene_flags": ["outlier"]}, "QUALITY_FLAGS"),
    ({"constraint_flags": None}, "UNVERIFIED_QUALITY"),
    ({"constraint_flags": ""}, "UNVERIFIED_QUALITY"),
    ({"available": 0}, "UNAVAILABLE_CONSTRAINT"),
    ({"lof_expected": 0}, "MISSING_OR_ZERO_EXPECTED_LOF"),
    ({"lof_expected": None}, "MISSING_OR_ZERO_EXPECTED_LOF"),
    ({"gene_mapping": {}}, "UNRESOLVED_GENE_MAPPING"),
    ({"transcript_id": ""}, "MISSING_TRANSCRIPT"),
])
def test_unqualified_pli_is_retained_but_does_not_drive_inference(changes, issue):
    result = assess(matrix({"gnomad": [indicator_row("pLI", 0.99, **changes)]}))
    indicator, = result.gene_level_indicators
    assert not indicator["supports_lof"] and issue in indicator["issues"]
    assert result.mechanism == "UNKNOWN"
    assert result.contextual_evidence[0].raw_assertion["pli"] == 0.99


def test_legacy_pli_does_not_invent_a_release_from_the_source_url():
    m = matrix({"gnomad": [indicator_row("pLI", 0.99, release=None)]})
    m = m.copy(update={"contextual_evidence": [e.copy(update={"source_dataset_version": None}) for e in m.contextual_evidence]})
    result = assess(m)
    assert "UNVERIFIED_RELEASE" in result.gene_level_indicators[0]["issues"]
    assert result.mechanism == "UNKNOWN"


def test_pli_uses_mane_then_canonical_never_the_largest_value():
    canonical = indicator_row("pLI", 0.01)
    alternate = indicator_row("pLI", 0.99, transcript_id="ENST000002.1", canonical=False)
    result = assess(matrix({"gnomad": [canonical, alternate]}))
    assert result.mechanism == "UNKNOWN"
    chosen, = [i for i in result.gene_level_indicators if i["selected_for_gene_assessment"]]
    assert chosen["value"] == 0.01
    alternate["mane_select"] = True
    result = assess(matrix({"gnomad": [canonical, alternate]}))
    assert result.mechanism_confidence == "INFERRED"
    assert result.supporting_evidence[0].raw_assertion["transcript_id"] == "ENST000002.1"
    alternate.pop("mane_select")
    alternate["canonical"] = True
    result = assess(matrix({"gnomad": [canonical, alternate]}))
    assert result.mechanism == "UNKNOWN"
    assert all("AMBIGUOUS_TRANSCRIPT" in i["issues"] for i in result.gene_level_indicators)


@pytest.mark.parametrize("mechanism,requirement,pli,hi", [
    ("loss of function", "biallelic_autosomal", 0, 30),
    ("gain of function", "monoallelic_autosomal", 0.99, 3),
    ("dominant negative", "monoallelic_autosomal", 0.99, 3),
])
def test_hi_and_pli_never_overwrite_a_curated_disease_mechanism(mechanism, requirement, pli, hi):
    result = assess(matrix({"g2p": [g2p(mechanism=mechanism, requirement=requirement)],
        "clingen_dosage": [indicator_row("HI", hi)], "gnomad": [indicator_row("pLI", pli)]},
        "AR" if requirement.startswith("biallelic") else "AD"))
    assert result.mechanism == norm.molecular_mechanism(mechanism)
    assert result.mechanism_confidence == "DEFINITIVE" and result.mechanism_scope == "DISEASE_SPECIFIC"
    assert len(result.gene_level_indicators) == 2 and not result.conflicting_evidence


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
