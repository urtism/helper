"""Synthetic integration of existing mechanism evidence with PVS1; no live sources."""
import copy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from helper_next.core import acmg_pvs1_mechanism as adapter
from helper_next.core.acmg_mechanism_assessment import assess
from pvs1.calculator import calculate_pvs1
from pvs1.models import PVS1Input
from test_acmg_mechanisms import cache, g2p, gencc, packets


CHOICE = {"context": {"gene": {"identifier": "HGNC:1", "label": "GENE_X"},
                      "disease": {"identifier": "MONDO:1"}, "inheritance_modes": ["AUTOSOMAL_DOMINANT"]}}


@pytest.fixture(autouse=True)
def isolated_assessments():
    adapter._assessment.cache_clear()
    adapter._resolver.cache_clear()
    yield
    adapter._assessment.cache_clear()
    adapter._resolver.cache_clear()


def matrix_cache(matrix):
    return SimpleNamespace(resolve_gene_disease_mechanism=lambda *args, **kwargs: matrix)


def decision(fields):
    context = dict(gene="HGNC:1", disease="MONDO:1", inheritance="AUTOSOMAL_DOMINANT", scope="DISEASE_SPECIFIC")
    context["source_refs"] = {k: ["synthetic:selected-context"] for k in context}
    fields = dict(fields)
    sources = dict(fields.pop("source_refs", {}))
    if "scope" in fields:
        fields["mechanism_scope"] = fields.pop("scope")
        sources["mechanism_scope"] = sources.pop("scope", [])
    context.update(fields, source_refs={**context["source_refs"], **sources})
    source = "synthetic:molecular-facts"
    tx = dict(accession="ENST00000000001.1", strand="+", coordinate_system="transcript_1_based_closed",
              cds_interval=[1, 300], exon_genomic_intervals=[[1001, 1100], [2001, 2100], [3001, 3100]],
              exon_coordinate_system="genomic_1_based_closed")
    tx["source_refs"] = {k: [source] for k in tx}
    product = dict(basis="PREDICTED", transcript_ref="ENST00000000001.1|product", ptc_start=100,
                   coordinate_system="transcript_1_based_closed", frame_effect="IN_FRAME",
                   ptc_junction_distances=[[100, 0], [200, 100]])
    product["source_refs"] = {k: [source] for k in product}
    return calculate_pvs1(PVS1Input(
        variant=dict(assembly="GRCh38", contig="1", position=1100, reference_allele="C", alternate_allele="T",
                     coordinate_system="genomic_1_based", consequence="stop_gained"),
        disease_context=context, transcript=tx, molecular_effect={"products": [product]}))


def test_local_snapshot_and_assessment_are_reused_across_variants(cache):
    with patch.object(adapter, "assess", wraps=assess) as assess_once:
        first, report, _ = adapter.resolve_pvs1_mechanism(CHOICE, cache=cache)
        second, again, _ = adapter.resolve_pvs1_mechanism(CHOICE, cache=cache)
        assert assess_once.call_count == 1 and len(cache.sources.calls) == 1
    assert first == second and report["snapshot_id"] == again["snapshot_id"]
    assert report["identity"]["gene_id"] == "HGNC:1"
    assert first["molecular_mechanism"] == "LoF" and first["confidence"] == "DEFINITIVE"
    assert decision(first).applied_strength == "VERY_STRONG"
    assert "G2P-1" in first["source_refs"]["molecular_mechanism"][0]
    report["supporting_evidence"].clear()
    assert adapter.resolve_pvs1_mechanism(CHOICE, cache=cache)[1]["supporting_evidence"]
    # The source index revision invalidates both the association and assessment.
    cache.sources.data["g2p"]["records"][0]["mechanism"] = "gain of function"
    cache.sources.revision += 1
    updated, report, _ = adapter.resolve_pvs1_mechanism(CHOICE, cache=cache)
    assert updated["molecular_mechanism"] == "GoF" and decision(updated).status == "INACTIVE"


def test_an_explicit_normalized_assertion_outside_g2p_reaches_pvs1(cache):
    matrix = cache.resolve_gene_disease_mechanism("HGNC:1", "MONDO:1", "AD")
    original = matrix.direct_evidence[0]
    # Existing normalized evidence contract: this fixture does not assert that
    # the current ClinGen adapter can acquire such a statement automatically.
    evidence = original.copy(update={"source": "clingen", "source_record_id": "CLINGEN-explicit",
                                     "source_classification": None})
    matrix = matrix.copy(update={"direct_evidence": [evidence]})
    fields, report, _ = adapter.resolve_pvs1_mechanism(CHOICE, cache=matrix_cache(matrix))
    assert fields["molecular_mechanism"] == "LoF"
    assert report["supporting_evidence"][0]["source"] == "clingen"
    assert decision(fields).applied_strength == "VERY_STRONG"


@pytest.mark.parametrize("with_curated_mechanism", [False, True])
def test_hi_and_pli_reach_the_calculator_with_gene_scope_and_provenance(cache, with_curated_mechanism):
    from test_acmg_mechanism_assessment import indicator_row
    cache.sources.data = packets({"g2p": [g2p()] if with_curated_mechanism else [],
        "clingen_dosage": [indicator_row("HI", 3)], "gnomad": [indicator_row("pLI", 0.99)]})
    fields, report, _ = adapter.resolve_pvs1_mechanism(CHOICE, cache=cache)
    assert {i["metric"] for i in report["gene_level_indicators"]} == {"HI", "pLI"}
    assert all(i["supports_lof"] and i["source_record_ref"] for i in report["gene_level_indicators"])
    assert fields["molecular_mechanism"] == "LoF"
    assert fields["confidence"] == ("DEFINITIVE" if with_curated_mechanism else "INFERRED")
    assert fields["scope"] == ("DISEASE_SPECIFIC" if with_curated_mechanism else "GENE_LEVEL")
    assert decision(fields).applied_strength == "VERY_STRONG"
    if not with_curated_mechanism:
        assert any("LoF inferito" in warning for warning in decision(fields).warnings)
    assert len(report["contextual_evidence"]) == 2


@pytest.mark.parametrize("rows", [
    {"gencc": [gencc()]},
    {"g2p": [g2p(disease="MONDO:2")]},
    {"g2p": [g2p(requirement="biallelic_autosomal")]},
    {"g2p": [dict(g2p(), confidence="uncertain")]},
    {"g2p": [dict(g2p(), record_url="")]},
    {"g2p": [g2p(mechanism="unmapped source description")]},
])
def test_unqualified_or_different_contexts_never_apply_pvs1(cache, rows):
    cache.sources.data = packets(rows)
    fields, _, _ = adapter.resolve_pvs1_mechanism(CHOICE, cache=cache)
    assert fields["molecular_mechanism"] == "UNKNOWN"
    assert decision(fields).applied_strength is None


def test_conflicts_are_reported_and_require_review(cache):
    cache.sources.data = packets({"g2p": [g2p(), g2p("G2P-2", mechanism="gain of function")]})
    fields, report, warnings = adapter.resolve_pvs1_mechanism(CHOICE, cache=cache)
    assert fields["confidence"] == "DISPUTED"
    assert {e["source_record_id"] for e in report["conflicting_evidence"]} == {"G2P-1", "G2P-2"}
    assert any("conflitto" in warning for warning in warnings)
    assert decision(fields).status == "REQUIRES_REVIEW" and decision(fields).applied_strength is None


@pytest.mark.parametrize("classification", ["Disputed", "Disputed Evidence", "Refuted", "Refuted Evidence", "  REFUTED   EVIDENCE  "])
def test_disputed_association_blocks_an_explicit_lof(cache, classification):
    cache.sources.data["gencc"]["records"][0]["classification_title"] = classification
    fields, report, _ = adapter.resolve_pvs1_mechanism(CHOICE, cache=cache)
    assert fields["confidence"] == "DISPUTED"
    assert any(e["source"] == "gencc" for e in report["conflicting_evidence"])
    assert report["gene_disease_association_status"] == "DISPUTED"
    assert decision(fields).status == "REQUIRES_REVIEW"


def test_refuted_association_without_mechanism_keeps_its_original_source(cache):
    row = dict(gencc(), classification_title="Refuted Evidence")
    cache.sources.data = packets({"gencc": [row]})
    fields, report, warnings = adapter.resolve_pvs1_mechanism(CHOICE, cache=cache)
    assert fields["molecular_mechanism"] == "UNKNOWN" and fields["confidence"] == "DISPUTED"
    assert report["conflicting_evidence"][0]["raw_assertion"] == row
    assert any("SGC-1: Refuted Evidence" in message for message in warnings)
    assert decision(fields).status == "REQUIRES_REVIEW" and decision(fields).applied_strength is None


@pytest.mark.parametrize("changes", [
    {"disease_curie": "MONDO:2"},
    {"moi_title": "Autosomal recessive"},
    {"gene_curie": "HGNC:2"},
])
def test_refuted_association_in_other_context_does_not_block_lof(cache, changes):
    cache.sources.data["gencc"]["records"][0].update(classification_title="Refuted Evidence", **changes)
    fields, report, _ = adapter.resolve_pvs1_mechanism(CHOICE, cache=cache)
    assert fields["confidence"] == "DEFINITIVE"
    assert not report["conflicting_evidence"]
    assert decision(fields).applied_strength == "VERY_STRONG"


def test_approved_vcep_precedence_does_not_hide_conflicts(cache):
    from test_acmg_mechanism_assessment import vcep_record
    matrix = cache.resolve_gene_disease_mechanism("HGNC:1", "MONDO:1", "AD")
    expert = vcep_record(matrix.direct_evidence[0], "GAIN_OF_FUNCTION")
    matrix = matrix.copy(update={"direct_evidence": [*matrix.direct_evidence, expert]})
    assert assess(matrix).mechanism_confidence == "DEFINITIVE"
    fields, report, _ = adapter.resolve_pvs1_mechanism(CHOICE, cache=matrix_cache(matrix))
    assert fields["confidence"] == "DISPUTED"
    assert report["conflicting_evidence"]
    assert decision(fields).status == "REQUIRES_REVIEW"


def test_negative_only_assertion_is_visible_and_cannot_become_a_positive_mechanism(cache):
    matrix = cache.resolve_gene_disease_mechanism("HGNC:1", "MONDO:1", "AD")
    evidence = matrix.direct_evidence[0].copy(update={"evidence_direction": "CONTRADICTING"})
    matrix = matrix.copy(update={"direct_evidence": [], "contradictory_evidence": [evidence]})
    fields, report, warnings = adapter.resolve_pvs1_mechanism(CHOICE, cache=matrix_cache(matrix))
    assert fields["molecular_mechanism"] == "UNKNOWN" and report["conflicting_evidence"]
    assert "G2P-1" in fields["source_refs"]["confidence"][0]
    assert any("conflitto" in warning for warning in warnings)
    assert decision(fields).status == "REQUIRES_REVIEW"


def test_qualified_gene_level_support_does_not_qualify_an_unaccepted_disease_assertion(cache):
    matrix = cache.resolve_gene_disease_mechanism("HGNC:1", "MONDO:1", "AD")
    original = matrix.direct_evidence[0]
    unaccepted = original.copy(update={"source_classification": "uncertain"})
    dosage = original.copy(update={"evidence_id": "dosage", "source": "clingen_dosage",
        "evidence_category": "DOSAGE_SENSITIVITY", "applicability": "GENE_LEVEL", "disease_ids": [],
        "evidence_direction": "CONTEXTUAL", "raw_assertion": {"assessment": "haploinsufficiency", "hi_score": "3"}})
    matrix = matrix.copy(update={"direct_evidence": [unaccepted], "contextual_evidence": [dosage]})
    fields, _, _ = adapter.resolve_pvs1_mechanism(CHOICE, cache=matrix_cache(matrix))
    assert fields["molecular_mechanism"] == "UNKNOWN" and decision(fields).applied_strength is None


@pytest.mark.parametrize("scope", ["GENE_LEVEL", "EXACT"])
def test_dosage_inference_keeps_its_scope_and_never_becomes_definitive(cache, scope):
    matrix = cache.resolve_gene_disease_mechanism("HGNC:1", "MONDO:1", "AD")
    evidence = matrix.direct_evidence[0].copy(update={
        "source": "clingen_dosage", "source_record_id": "HI:1", "evidence_category": "DOSAGE_SENSITIVITY",
        "applicability": scope, "evidence_direction": "CONTEXTUAL", "evidence_directness": "INDIRECT",
        "disease_ids": [] if scope == "GENE_LEVEL" else ["MONDO:1"],
        "raw_assertion": {"assessment": "haploinsufficiency", "hi_score": "3"}})
    matrix = matrix.copy(update={"direct_evidence": [], "contextual_evidence": [evidence]})
    fields, report, _ = adapter.resolve_pvs1_mechanism(CHOICE, cache=matrix_cache(matrix))
    assert fields["confidence"] == "INFERRED"
    assert fields["scope"] == ("GENE_LEVEL" if scope == "GENE_LEVEL" else "DISEASE_SPECIFIC")
    assert decision(fields).applied_strength == "VERY_STRONG"


def test_ambiguous_inheritance_and_source_failure_leave_molecular_analysis_available():
    def unexpected(*args, **kwargs):
        pytest.fail("Ambiguous inheritance must not query the cache")
    choice = {"context": {**CHOICE["context"], "inheritance_modes": ["AD", "AR"]}}
    fields, report, _ = adapter.resolve_pvs1_mechanism(choice, cache=SimpleNamespace(resolve_gene_disease_mechanism=unexpected))
    assert fields["molecular_mechanism"] == "UNKNOWN" and report["status"] == "MISSING_INHERITANCE"

    def unavailable(*args, **kwargs):
        raise OSError("synthetic local cache unavailable")
    fields, report, warnings = adapter.resolve_pvs1_mechanism(CHOICE, cache=SimpleNamespace(resolve_gene_disease_mechanism=unavailable))
    assert report["status"] == "SOURCE_UNAVAILABLE" and warnings
    assert decision(fields).status == "NOT_EVALUABLE"


def test_calculator_adapter_disables_remote_acquisition(monkeypatch, cache):
    matrix = cache.resolve_gene_disease_mechanism("HGNC:1", "MONDO:1", "AD")
    with patch.object(adapter, "SourceManager", wraps=adapter.SourceManager) as sources:
        monkeypatch.setattr(adapter, "MechanismEvidenceCache", lambda **kwargs: matrix_cache(matrix))
        fields, _, _ = adapter.resolve_pvs1_mechanism(CHOICE)
    sources.assert_called_once_with(gene_database=str(adapter.gene_phenotype.cache_path().resolve()), mechanism_fetch=False)
    assert fields["molecular_mechanism"] == "LoF"


@pytest.fixture
def default_resolver(cache, tmp_path, monkeypatch):
    from test_acmg_ontology import load_reference
    load_reference(cache.registry, tmp_path, [('MONDO:1', 'skos:exactMatch', 'OMIM:1')])
    cache.sources.mapping_registry = None
    created, clock = [], [1700000000.0]
    cache.clock = lambda: clock[0]
    cache_type = type(cache)
    def construct(**kwargs):
        resolver = cache_type(**kwargs, clock=lambda: clock[0])
        created.append(resolver)
        return resolver
    monkeypatch.setattr(adapter, "SourceManager", lambda **kwargs: cache.sources)
    monkeypatch.setattr(adapter, "MechanismEvidenceCache", construct)
    return cache, created, clock


def test_default_resolver_loads_mondo_once_across_concurrent_contexts(default_resolver):
    from helper_next.core import acmg_ontology as ontology
    original, created, _ = default_resolver
    original.sources.data['g2p']['records'].append(g2p('G2P-2', 'MONDO:2', 'gain of function', 'biallelic_autosomal'))
    other = copy.deepcopy(CHOICE)
    other['context']['disease']['identifier'] = 'MONDO:2'
    other['context']['inheritance_modes'] = ['AUTOSOMAL_RECESSIVE']
    barrier = Barrier(4)
    def evaluate(choice):
        barrier.wait(timeout=5)
        return adapter.resolve_pvs1_mechanism(choice)
    choices = [CHOICE, other, CHOICE, other]
    with patch.object(ontology, 'digest', wraps=ontology.digest) as checked:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(evaluate, choices))
        # Hash validation of the full reference happens once, even on cold concurrent requests.
        verifications = [call for call in checked.call_args_list
                         if isinstance(call.args[0], dict) and call.args[0].get('mapping_source') == 'MONDO'
                         and 'mapping_id' not in call.args[0]]
        assert len(verifications) == 1
        assert len(created) == 1
        assert len(original.sources.calls) == 1
        assert [result[0]['molecular_mechanism'] for result in results] == ['LoF', 'GoF', 'LoF', 'GoF']
        for choice, result in zip(choices, results):
            assert adapter.resolve_pvs1_mechanism(choice) == result
            assert adapter.resolve_pvs1_mechanism(choice, cache=original) == result
        assert len([call for call in checked.call_args_list
                    if isinstance(call.args[0], dict) and call.args[0].get('mapping_source') == 'MONDO'
                    and 'mapping_id' not in call.args[0]]) == 1


def test_default_resolver_observes_new_ontology_release_and_preserves_pinned_views(default_resolver, tmp_path):
    from helper_next.core.acmg_ontology import OntologyMappingRegistry
    from test_acmg_ontology import load_reference
    original, created, _ = default_resolver
    original.sources.data['g2p']['records'][0]['disease_curie'] = 'OMIM:1'
    before = adapter.resolve_pvs1_mechanism(CHOICE)
    resolver = created[0]
    pinned = resolver.registry.pin()
    assert before[0]['molecular_mechanism'] == 'LoF'
    # Import through another instance, as happens when a different process updates sources.
    load_reference(OntologyMappingRegistry(resolver.store), tmp_path,
                   [('MONDO:2', 'skos:exactMatch', 'OMIM:1')], 'new-reference')
    after = adapter.resolve_pvs1_mechanism(CHOICE)
    assert len(created) == 1
    assert after[0]['molecular_mechanism'] == 'UNKNOWN'
    assert after[1]['snapshot_id'] != before[1]['snapshot_id']
    assert resolver.registry.canonical('OMIM:1') == 'MONDO:2'
    assert pinned.canonical('OMIM:1') == 'MONDO:1'
    assert len(original.sources.calls) == 1  # Registry updates do not acquire source packets again.


def test_default_resolver_preserves_source_revision_and_ttl_invalidation(default_resolver):
    original, created, clock = default_resolver
    assert adapter.resolve_pvs1_mechanism(CHOICE)[0]['molecular_mechanism'] == 'LoF'
    original.sources.data['g2p']['records'][0]['mechanism'] = 'gain of function'
    original.sources.revision += 1
    assert adapter.resolve_pvs1_mechanism(CHOICE)[0]['molecular_mechanism'] == 'GoF'
    original.sources.data['g2p']['records'][0]['mechanism'] = 'loss of function'
    assert adapter.resolve_pvs1_mechanism(CHOICE)[0]['molecular_mechanism'] == 'GoF'
    clock[0] += 8 * 86400
    assert adapter.resolve_pvs1_mechanism(CHOICE)[0]['molecular_mechanism'] == 'LoF'
    assert len(created) == 1 and len(original.sources.calls) == 3


@pytest.mark.parametrize('setting,value', [
    ('HELPER_MECHANISM_DB', 'other-mechanisms.sqlite'),
    ('HELPER_GENE_PHENOTYPE_DB', 'other-genes.sqlite'),
    ('HELPER_MECHANISM_TTL_JSON', '{"g2p": 600}'),
    ('HELPER_MECHANISM_TIMEOUT', '30'),
])
def test_default_resolver_isolates_database_and_policy_configuration(tmp_path, monkeypatch, setting, value):
    monkeypatch.setenv('HELPER_MECHANISM_DB', str(tmp_path / 'mechanisms.sqlite'))
    monkeypatch.setenv('HELPER_GENE_PHENOTYPE_DB', str(tmp_path / 'genes.sqlite'))
    first = adapter._shared_cache()
    assert adapter._shared_cache() is first
    monkeypatch.setenv(setting, str(tmp_path / value) if value.endswith('.sqlite') else value)
    second = adapter._shared_cache()
    assert second is not first and adapter._shared_cache() is second
    assert first.sources.mechanism_fetch is second.sources.mechanism_fetch is False
