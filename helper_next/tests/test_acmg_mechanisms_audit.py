"""Scientific regression boundaries established by the prepopulation audit."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from helper_next.core import acmg_mechanism_normalizer as norm
from helper_next.core.acmg_mechanisms_bulk import build_inventory, dataset_fingerprints
from test_acmg_mechanisms_bulk import population
from test_acmg_mechanisms import cache, g2p, gencc, packets, resolve


@pytest.mark.parametrize("g2p_term,hpo_term", [
    ("monoallelic_autosomal", "Autosomal dominant"),
    ("biallelic_autosomal", "Autosomal recessive"),
    ("monoallelic_X_hemizygous", "X-linked recessive"),
    ("monoallelic_X_heterozygous", "X-linked dominant"),
    ("monoallelic_Y_hemizygous", "Y-linked inheritance"),
])
def test_published_qualified_inheritance_crosswalk(g2p_term, hpo_term):
    assert norm.allelic(g2p_term) == norm.allelic(hpo_term)
    assert norm.allelic(norm.allelic(g2p_term)) == norm.allelic(g2p_term)


@pytest.mark.parametrize("left,right", [
    ("monoallelic", "AD"), ("biallelic", "AR"), ("AD", "AR"),
    ("monoallelic_X_hemizygous", "X-linked"),
    ("monoallelic_X_heterozygous", "X-linked"),
    ("monoallelic_X", "X-linked recessive"),
    ("Semidominant", "AD"),
])
def test_unspecified_or_different_scopes_remain_separate(left, right):
    assert norm.allelic(left) != norm.allelic(right)


def test_qualified_cross_source_mechanism_keeps_original_assertion_and_scope(cache):
    cache.sources.data = packets({"g2p": [g2p()], "gencc": [gencc()]})
    result = resolve(cache, allelic_requirement="AD")
    assert result.candidate_mechanisms == ["LOSS_OF_FUNCTION"]
    assert result.direct_evidence[0].original_allelic_requirement == "monoallelic_autosomal"
    assert result.gene_disease_validity[0]["applicability"] == "EXACT"
    assert result.review_status == "NOT_REVIEWED"
    assert "doi:10.1016/j.gim.2023.101029" in result.provenance["rules"]["inheritance_crosswalk"]


def test_undetermined_non_lof_does_not_assert_a_defined_mechanism(cache):
    cache.sources.data = packets({"g2p": [g2p(mechanism="undetermined non-loss-of-function")]})
    result = resolve(cache)
    assert result.direct_evidence == [] and result.candidate_mechanisms == []
    evidence = result.contextual_evidence[0]
    assert evidence.original_mechanism == "undetermined non-loss-of-function"
    assert evidence.asserted_mechanism == "UNKNOWN" and evidence.evidence_direction == "NOT_INFORMATIVE"


def test_bulk_reports_actual_source_overlap_after_disease_mapping(population):
    runner, source_db, _ = population
    import sqlite3
    with sqlite3.connect(source_db) as db:
        db.execute("UPDATE g2p_records SET allelic_requirement='monoallelic_autosomal' WHERE g2p_id='G2P-1'")
    inventory = build_inventory(runner.cache.sources)
    shared = [a for a in inventory["associations"] if a["sources"] == ["g2p", "gencc"]]
    assert inventory["report"]["cross_source_associations"] == len(shared) == 1
    one = shared[0]
    assert one["allelic_requirement"] == "AUTOSOMAL_DOMINANT"
    assert one["disease"] == "MONDO:1"
    counts = inventory["report"]["normalized_source_associations"]
    assert sum(counts.values()) - len(shared) == len(inventory["associations"])


def test_projection_fingerprints_reproducible_and_do_not_fabricate_releases(population):
    runner, _, _ = population
    raw = runner.cache.sources.mechanism_association_inventory()
    before = dataset_fingerprints(raw["tables"])
    reordered = {table: list(reversed(rows)) for table, rows in raw["tables"].items()}
    assert dataset_fingerprints(reordered) == before
    changed = copy.deepcopy(reordered)
    changed["assertions"][0]["version_number"] += 1
    after = dataset_fingerprints(changed)
    assert after["gencc"] != before["gencc"] and after["g2p"] == before["g2p"]
    report = build_inventory(runner.cache.sources)["report"]
    assert report["dataset_versions"]["g2p"] is None and report["dataset_versions"]["gencc"] is None
    assert before["gencc"]["scope"] == "LOCAL_INDEXED_ROWS_V1"


@pytest.mark.parametrize("include_second_exact", [True, False])
def test_ontology_audit_separates_primary_diseases_and_keeps_missing_mapping_unresolved(tmp_path, monkeypatch, include_second_exact):
    script = Path(__file__).resolve().parents[2] / "scripts/audit_mechanism_inventory.py"
    spec = importlib.util.spec_from_file_location("audit_mechanism_inventory", script)
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    g = g2p()
    g["disease_mim"] = "OMIM:1"
    c = gencc(disease="MONDO:2")
    c["disease_original_curie"] = "OMIM:1"
    mapping = tmp_path / "synthetic.sssom.tsv"
    mapping.write_text("subject_id\tpredicate_id\tobject_id\nMONDO:1\tskos:exactMatch\tOMIM:1\n"
                       + ("MONDO:2\tskos:exactMatch\tOrphanet:2\n" if include_second_exact else ""))
    monkeypatch.setattr(audit, "MONDO_SHA256", hashlib.sha256(mapping.read_bytes()).hexdigest())
    result = audit.ontology_audit({"g2p_records": [g], "assertions": [c]}, mapping)
    assert result["old_ambiguous_associations"] == 2
    assert result["ambiguity_classification"]["source_cross_references"] == 2
    assert result["ambiguity_classification"]["nonambiguous_verified_component"] == (2 if include_second_exact else 1)
    if not include_second_exact:
        assert result["ambiguity_classification"]["no_verified_mapping"] == 1
    assert result["unconfirmed_cross_reference_reasons"]["DIFFERENT_MONDO_TARGET"] == 1
    assert result["mode"] == "AUDIT_ONLY_COUNTERFACTUAL_NOT_APPLIED"


def test_ontology_audit_rejects_unpinned_reference(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts/audit_mechanism_inventory.py"
    spec = importlib.util.spec_from_file_location("audit_mechanism_inventory", script)
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    reference = tmp_path / "unverified.tsv"
    reference.write_text("unverified data")
    with pytest.raises(ValueError, match="checksum"):
        audit.ontology_audit({}, reference)


def test_selected_live_g2p_verification_detects_drift_without_updating_index(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts/audit_mechanism_inventory.py"
    spec = importlib.util.spec_from_file_location("audit_mechanism_inventory", script)
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    original = g2p()
    tables = {"g2p_records": [original]}
    document = {"stable_id": original["g2p_id"], "genotype": original["allelic_requirement"],
                "locus": {"ids": {"HGNC": "HGNC:1"}, "gene_symbol": "GENE_X"},
                "molecular_mechanism": {"mechanism": "loss of function", "mechanism_support": "observed"},
                "confidence": "definitive", "last_updated": "2026-01-01",
                "disease": {"ontology_terms": [{"source": "Mondo", "accession": "MONDO:1"}]}}
    response = tmp_path / "g2p-G2P-1.json"
    response.write_text(json.dumps(document))
    assert audit.verify_acquired_g2p_responses(tmp_path, tables)["records_with_differences"] == 0
    document["molecular_mechanism"]["mechanism"] = "undetermined"
    response.write_text(json.dumps(document))
    result = audit.verify_acquired_g2p_responses(tmp_path, tables)
    assert result["records_with_differences"] == 1
    assert result["items"][0]["differences"]["mechanism"] == {"indexed": "loss of function", "live": "undetermined"}
    assert original["mechanism"] == "loss of function"
