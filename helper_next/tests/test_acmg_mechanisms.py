"""Task 27A: deterministic public-source fixtures, cache lifecycle and engine boundary."""
import copy
import asyncio
import io
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.error import URLError

import pytest
from fastapi import HTTPException

from helper_next.api import acmg_mechanisms as api
from helper_next.core import acmg_mechanism_normalizer as norm
from helper_next.core.acmg_mechanism_models import SOURCES
from helper_next.core.acmg_mechanism_store import compare_snapshots
from helper_next.core.acmg_mechanisms import MechanismEvidenceCache
from helper_next.core.acmg_sources import SourceManager
from helper_variants import gene_phenotype
from test_gene_phenotype import HEADER


STAMP = "2026-01-01T12:00:00Z"


def g2p(record="G2P-1", disease="MONDO:1", mechanism="loss of function", requirement="monoallelic_autosomal", **values):
    return dict(g2p_id=record, gene_curie="HGNC:1", gene_symbol="GENE_X", disease_curie=disease,
                disease_mim="", disease_name="Synthetic disease", allelic_requirement=requirement,
                confidence="definitive", mechanism=mechanism, mechanism_category="", mechanism_support="observed",
                variant_consequence="frameshift_variant", publications="PMID:1", last_reviewed="2026-01-01",
                record_url="https://example.test/" + record, **values)


def gencc(record="SGC-1", disease="MONDO:1"):
    return dict(sgc_id=record, version_number=2, gene_curie="HGNC:1", gene_symbol="GENE_X",
                disease_curie=disease, disease_original_curie="", disease_title="Synthetic disease",
                moi_title="Autosomal dominant", classification_title="Strong", submitter_title="Synthetic submitter",
                public_report_url="https://example.test/assertion", pmids="PMID:1", submitted_run_date="2026-01-01")


def packets(rows=None):
    rows = rows or {}
    return {s: dict(source=s, status="AVAILABLE" if rows.get(s) else "NO_RECORDS", records=rows.get(s, []),
                    dataset_version="synthetic-1", retrieved_at=STAMP, source_url="https://example.test/" + s)
            for s in SOURCES}


class FixtureSources(SourceManager):
    def __init__(self, data):
        super().__init__()
        self.data, self.calls, self.revision = data, [], 1

    def mechanism_revision(self):
        return self.revision

    def mechanism_records(self, gene_id, symbol="", sources=None, **kwargs):
        self.calls.append(set(sources))
        return {s: copy.deepcopy(self.data[s]) for s in sources}


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("HELPER_MECHANISM_DB", str(tmp_path / "mechanism.sqlite"))
    monkeypatch.setenv("HELPER_MECHANISM_FETCH", "0")
    sources = FixtureSources(packets({"g2p": [g2p()], "gencc": [gencc()]}))
    return MechanismEvidenceCache(sources, tmp_path / "mechanism.sqlite")


def resolve(cache, disease="MONDO:1", **kwargs):
    return cache.resolve_gene_disease_mechanism("HGNC:1", disease, **kwargs)


def test_gene_multiple_diseases_remain_distinct(cache):
    cache.sources.data = packets({"g2p": [g2p(), g2p("G2P-2", "MONDO:2", "gain of function")]})
    first, second = resolve(cache), resolve(cache, "MONDO:2")
    assert first.candidate_mechanisms == ["LOSS_OF_FUNCTION"]
    assert second.candidate_mechanisms == ["GAIN_OF_FUNCTION"]
    assert first.snapshot_id != second.snapshot_id
    assert len(cache.sources.calls) == 1  # One gene acquisition shared across disease queries.


def test_other_disease_update_does_not_invalidate_unchanged_association(cache):
    cache.sources.data = packets({"g2p": [g2p(), g2p("G2P-2", "MONDO:2", "gain of function")]})
    before = resolve(cache)
    cache.sources.data["g2p"]["records"][1]["mechanism"] = "dominant negative"
    cache.sources.revision = 2
    assert resolve(cache).snapshot_id == before.snapshot_id


def test_conflicting_assertions_kept_without_consensus(cache):
    cache.sources.data = packets({"g2p": [g2p(), g2p("G2P-2", mechanism="gain of function")]})
    result = resolve(cache)
    assert result.resolution_status == "CONFLICTING_ASSERTIONS"
    assert result.candidate_mechanisms == ["GAIN_OF_FUNCTION", "LOSS_OF_FUNCTION"]
    assert len(result.direct_evidence) == len(result.contradictory_evidence) == 2
    assert all(h.contradictory_evidence_refs for h in result.hypotheses)
    assert result.review_status == "NOT_REVIEWED" and "CONTRADICTORY_ASSERTIONS" in result.issues
    assert "confidence_score" not in result.dict()


def test_inheritance_scopes_never_collapse(cache):
    cache.sources.data = packets({"g2p": [g2p(), g2p("G2P-2", mechanism="gain of function", requirement="biallelic")]})
    all_scopes = resolve(cache)
    assert all_scopes.resolution_status == "MULTIPLE_COMPATIBLE_ASSERTIONS"
    assert len(all_scopes.hypotheses) == 2 and all_scopes.contradictory_evidence == []
    mono = resolve(cache, allelic_requirement="monoallelic_autosomal")
    assert mono.candidate_mechanisms == ["LOSS_OF_FUNCTION"]
    ad = resolve(cache, allelic_requirement="AD")
    assert ad.candidate_mechanisms == ["LOSS_OF_FUNCTION"]
    assert any(e.applicability == "DIFFERENT_INHERITANCE" for e in ad.contextual_evidence)
    generic = resolve(cache, allelic_requirement="monoallelic")
    assert generic.candidate_mechanisms == []


@pytest.mark.parametrize("mechanism", ["decreased gene product level", "altered gene product structure"])
def test_specific_g2p_vocabulary_not_flattened_to_lof_or_gof(cache, mechanism):
    cache.sources.data = packets({"g2p": [g2p(mechanism=mechanism)]})
    result = resolve(cache)
    assert result.candidate_mechanisms == ["OTHER"]
    assert result.direct_evidence[0].original_mechanism == mechanism


def test_sequence_consequence_and_validity_do_not_establish_mechanism(cache):
    cache.sources.data = packets({"g2p": [g2p(mechanism="frameshift_variant")], "gencc": [gencc()]})
    result = resolve(cache)
    assert not result.candidate_mechanisms
    assert result.gene_disease_validity[0]["classification"] == "Strong"
    assert any(e.raw_assertion.get("variant_consequence") == "frameshift_variant" for e in result.contextual_evidence)


@pytest.mark.parametrize("loeuf", [0.01, 2.5, None])
def test_constraint_without_direct_mechanism_is_context_only(cache, loeuf):
    raw = dict(gene_symbol="GENE_X", gene_id="ENSG000001", transcript_id="ENST000001.2",
               loeuf=loeuf, lof_observed=None, lof_expected=25, lof_oe=None, available=1)
    cache.sources.data = packets({"gnomad": [raw]})
    result = resolve(cache)
    assert result.resolution_status == "INSUFFICIENT_EVIDENCE" and not result.candidate_mechanisms
    assert result.contextual_evidence[0].raw_assertion["loeuf"] == loeuf
    assert result.contextual_evidence[0].raw_assertion["lof_observed"] is None
    assert result.contextual_evidence[0].raw_assertion["transcript_id"] == "ENST000001.2"


def test_dosage_gene_level_and_nonpositive_scores_remain_context(cache):
    rows = [dict(gene_symbol="GENE_X", gene_id="123", assessment=assessment, hi_score="30", ts_score="40",
                 hi_disease_id="", ts_disease_id="", report_url="https://example.test/dosage")
            for assessment in ("haploinsufficiency", "triplosensitivity")]
    cache.sources.data = packets({"clingen_dosage": rows})
    result = resolve(cache)
    assert not result.candidate_mechanisms and len(result.contextual_evidence) == 2
    assert {e.raw_assertion["assessment"] for e in result.contextual_evidence} == {"haploinsufficiency", "triplosensitivity"}
    assert all(e.raw_assertion["hi_score"] == "30" and e.raw_assertion["ts_score"] == "40" for e in result.contextual_evidence)


def test_clinvar_aggregate_and_submission_references_are_one_context(cache):
    raw = dict(identifiers=["123", "VCV000000123.4"], gene_id="HGNC:1", condition_ids=["MONDO:1"],
               classifications=["Pathogenic"], review_statuses=[{"stars": 2}], molecular_consequence="missense_variant",
               rcv_accessions=["RCV000001"], scv_accessions=["SCV000001", "SCV000002"], source_url="https://example.test/VCV123")
    cache.sources.data = packets({"clinvar": [raw]})
    result = resolve(cache)
    assert result.candidate_mechanisms == [] and len(result.contextual_evidence) == 1
    evidence = result.contextual_evidence[0]
    assert evidence.source_record_version == "4" and evidence.raw_assertion["scv_accessions"] == raw["scv_accessions"]


def test_hit_persistent_between_instances_and_offline_snapshot(cache):
    result = resolve(cache)
    repeated = resolve(cache)
    assert result.snapshot_id == repeated.snapshot_id and len(cache.sources.calls) == 1
    other = MechanismEvidenceCache(cache.sources, cache.store.path)
    assert resolve(other, cache_policy="CACHE_ONLY").snapshot_id == result.snapshot_id
    replay = resolve(other, cache_policy="SNAPSHOT", snapshot_id=result.snapshot_id)
    assert replay.dict() == cache.store.snapshot(result.snapshot_id).dict()
    assert len(cache.sources.calls) == 1


def test_source_unavailable_keeps_last_complete_snapshot(cache):
    before = resolve(cache)
    cache.sources.data["g2p"].update(status="UNREACHABLE", records=[])
    after = resolve(cache, cache_policy="FORCE_REFRESH")
    assert after.snapshot_id == before.snapshot_id and after.candidate_mechanisms == before.candidate_mechanisms
    assert next(s for s in after.source_status if s.source == "g2p").status == "UNREACHABLE"
    assert "SOURCE_UNAVAILABLE" in after.issues and any("retained" in w for w in after.warnings)
    assert cache.store.snapshot(before.snapshot_id).dict() == before.dict()


def test_transport_exception_is_not_negative_cache(cache, monkeypatch):
    before = resolve(cache)
    monkeypatch.setattr(cache.sources, "mechanism_records", lambda *a, **k: (_ for _ in ()).throw(URLError("synthetic offline")))
    after = resolve(cache, cache_policy="FORCE_REFRESH")
    assert after.snapshot_id == before.snapshot_id
    assert all(s.status == "UNREACHABLE" for s in after.source_status)


def test_source_change_immutable_snapshot_replay_and_structured_diff(cache):
    before = resolve(cache)
    cache.sources.data["g2p"]["records"][0]["mechanism"] = "gain of function"
    cache.sources.data["g2p"]["dataset_version"] = "synthetic-2"
    cache.sources.revision = 2
    after = resolve(cache)
    assert after.snapshot_id != before.snapshot_id and after.candidate_mechanisms == ["GAIN_OF_FUNCTION"]
    assert cache.store.snapshot(before.snapshot_id).dict() == before.dict()
    differences = compare_snapshots(before, after)
    assert differences["changed_evidence"] == [["g2p", "G2P-1"]]
    assert differences["mechanism_status_changed"] and differences["source_version_changed"]
    assert not differences["mapping_changed"]
    with cache.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM mechanism_changes").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM mechanism_reviews").fetchone()[0] == 0
        with pytest.raises(sqlite3.IntegrityError, match="Immutable"):
            db.execute("UPDATE mechanism_snapshots SET matrix_hash='bad' WHERE snapshot_id=?", (before.snapshot_id,))


def test_unchanged_refresh_does_not_create_scientific_revision(cache):
    before = resolve(cache)
    cache.sources.data["g2p"]["retrieved_at"] = "2026-02-01T00:00:00Z"
    after = resolve(cache, cache_policy="FORCE_REFRESH")
    assert before.snapshot_id == after.snapshot_id


def test_normalizer_reconciliation_and_mapping_versions_are_separate(cache, monkeypatch):
    before = resolve(cache)
    monkeypatch.setattr(norm, "RECONCILIATION_VERSION", "synthetic-reconciliation-2")
    after = resolve(cache)
    diff = compare_snapshots(before, after)
    assert diff["reconciliation_version_changed"] and not diff["normalizer_version_changed"]
    assert after.snapshot_id != before.snapshot_id and len(cache.sources.calls) == 1


def test_disease_mapping_uses_ids_not_names_and_ambiguous_crossrefs(cache):
    rows = [g2p(), g2p("G2P-2", "MONDO:2", "gain of function")]
    rows[0]["disease_mim"] = rows[1]["disease_mim"] = "OMIM:1"
    cache.sources.data = packets({"g2p": rows})
    result = resolve(cache)
    assert result.candidate_mechanisms == ["LOSS_OF_FUNCTION"]
    assert "UNVERIFIED_DISEASE_MAPPING" in result.issues
    assert result.identity.disease_aliases == []
    ambiguous = resolve(cache, "OMIM:1")
    assert ambiguous.resolution_status == "INSUFFICIENT_EVIDENCE"
    assert ambiguous.candidate_mechanisms == [] and "AMBIGUOUS_DISEASE_MAPPING" in ambiguous.issues


def test_source_provenance_round_trip_original_and_record_version(cache):
    result = resolve(cache)
    evidence = result.direct_evidence[0]
    raw = cache.store.source_record(evidence.source_record_ref)
    assert raw["raw_payload"] == cache.sources.data["g2p"]["records"][0]
    assert evidence.source_record_hash == raw["content_hash"]
    assert raw["dataset_version"] == "synthetic-1"
    gencc_record = next(e for e in result.contextual_evidence if e.source == "gencc")
    assert gencc_record.source_record_id == "SGC-1" and gencc_record.source_record_version == "2"


def test_http_api_routes_and_body_validation(cache, monkeypatch):
    httpx = pytest.importorskip("httpx")
    from helper_next.api.app import create_app
    monkeypatch.setattr(api, "MechanismEvidenceCache", lambda: cache)

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://synthetic") as client:
            response = await client.post("/api/acmg/mechanisms/resolve", json={"gene": "HGNC:1", "disease": "MONDO:1"})
            assert response.status_code == 200
            data = response.json()
            assert data["candidate_mechanisms"] == ["LOSS_OF_FUNCTION"]
            snapshot = await client.get("/api/acmg/mechanisms/snapshots/" + data["snapshot_id"])
            assert snapshot.status_code == 200 and snapshot.json()["snapshot_id"] == data["snapshot_id"]
            invalid = await client.post("/api/acmg/mechanisms/resolve", json={"gene": "GENE_X", "disease": "MONDO:1"})
            assert invalid.status_code == 422
            unexpected = await client.post("/api/acmg/mechanisms/resolve", json={"gene": "HGNC:1", "disease": "MONDO:1", "patient_id": "synthetic-rejected"})
            assert unexpected.status_code == 422
    asyncio.run(exercise())


def test_ttl_selective_refresh_and_expiring_negative_cache(cache):
    now = [1000.0]
    cache.clock = lambda: now[0]
    cache.ttl = {s: 100 for s in SOURCES}
    cache.ttl["g2p"], cache.negative_ttl = 10, 20
    resolve(cache)
    now[0] += 11
    resolve(cache)
    assert cache.sources.calls[-1] == {"g2p"}
    now[0] += 10
    resolve(cache)
    assert cache.sources.calls[-1] == {"g2p", "clingen_dosage", "gnomad", "clinvar"}


@pytest.mark.parametrize("bad", ["missing_id", "nan", "mixed_release", "duplicate"])
def test_invalid_payload_does_not_overwrite_valid_sources(cache, bad):
    before = resolve(cache)
    row = cache.sources.data["g2p"]["records"][0]
    if bad == "missing_id":
        del row["g2p_id"]
    elif bad == "nan":
        row["unsupported_metric"] = float("nan")
    elif bad == "mixed_release":
        row["dataset_version"] = "synthetic-wrong-release"
    else:
        cache.sources.data["g2p"]["records"].append(copy.deepcopy(row))
    after = resolve(cache, cache_policy="FORCE_REFRESH")
    assert after.snapshot_id == before.snapshot_id
    assert next(s for s in after.source_status if s.source == "g2p").status == "NORMALIZATION_ERROR"
    assert cache.store.source_record(before.direct_evidence[0].source_record_ref)["raw_payload"]["mechanism"] == "loss of function"


def test_concurrent_refresh_deduplicates_and_publishes_atomically(cache):
    barrier = threading.Barrier(5)

    def run(_):
        barrier.wait(timeout=10)
        return resolve(MechanismEvidenceCache(cache.sources, cache.store.path)).snapshot_id

    with ThreadPoolExecutor(max_workers=5) as pool:
        snapshots = list(pool.map(run, range(5)))
    assert len(set(snapshots)) == 1 and len(cache.sources.calls) == 1
    with cache.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM mechanism_snapshots").fetchone()[0] == 1
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT COUNT(*) FROM mechanism_refresh_leases").fetchone()[0] == 0


def test_failed_transaction_does_not_publish_partial_snapshot(cache):
    before = resolve(cache)
    cache.sources.data["g2p"]["records"][0]["mechanism"] = "gain of function"
    with cache.store.connect() as db:
        db.execute("CREATE TRIGGER synthetic_fail BEFORE INSERT ON mechanism_snapshots BEGIN SELECT RAISE(ABORT, 'synthetic interruption'); END")
    with pytest.raises(sqlite3.IntegrityError, match="synthetic interruption"):
        resolve(cache, cache_policy="FORCE_REFRESH")
    assert cache.store.current(norm.association_key(before.identity)).snapshot_id == before.snapshot_id
    with cache.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM source_records WHERE source_name='g2p'").fetchone()[0] == 1


def test_real_index_accessor_reuses_current_formats_and_independent_g2p(tmp_path):
    database = tmp_path / "gene.sqlite"
    rows = "g2p id,gene symbol,hgnc id,disease name,disease MONDO,allelic requirement,confidence,molecular mechanism\nG2P-1,GENE_X,HGNC:1,Only G2P,MONDO:1,monoallelic_autosomal,strong,loss of function\n"
    dosage = "#Gene Symbol\tGene ID\tHaploinsufficiency Score\tTriplosensitivity Score\nGENE_X\t123\t30\t40\n"
    gene_phenotype.build_cache(io.StringIO(HEADER), database, g2p_stream=io.StringIO(rows), dosage_stream=io.StringIO(dosage))
    sources = SourceManager(gene_database=database)
    result = resolve(MechanismEvidenceCache(sources, tmp_path / "mechanism.sqlite"), cache_policy="CACHE_ONLY")
    assert result.candidate_mechanisms == ["LOSS_OF_FUNCTION"]
    assert len([e for e in result.contextual_evidence if e.source == "clingen_dosage"]) == 2
    assert next(s for s in result.source_status if s.source == "gencc").status == "NO_RECORDS"
    assert next(s for s in result.source_status if s.source == "gnomad").status == "CACHE_MISS"
    assert next(s for s in result.source_status if s.source == "clinvar").status == "NOT_SUPPORTED"
    assert result.direct_evidence[0].source_dataset_version is None


def test_existing_orpha_mapping_alone_never_establishes_equivalence(tmp_path):
    database = tmp_path / "gene.sqlite"
    rows = "g2p id,gene symbol,hgnc id,disease name,disease MONDO,allelic requirement,confidence,molecular mechanism\nG2P-1,GENE_X,HGNC:1,Synthetic,MONDO:1,monoallelic,strong,loss of function\n"
    gene_phenotype.build_cache(io.StringIO(HEADER), database, g2p_stream=io.StringIO(rows))
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO orpha_aliases VALUES('MONDO:1','ORPHA:1','E (Exact mapping)')")
    cache = MechanismEvidenceCache(SourceManager(gene_database=database), tmp_path / "mechanism.sqlite")
    result = resolve(cache, "ORPHA:1", cache_policy="CACHE_ONLY")
    assert result.candidate_mechanisms == []
    assert "NO_VERIFIED_MAPPING" in result.mapping_uncertainty
    assert any(e["source"] == "orphadata" and e["source_record_ref"] for e in result.mapping_evidence)


def test_consultation_api_snapshot_diff_and_cross_association_guard(cache, monkeypatch):
    monkeypatch.setattr(api, "MechanismEvidenceCache", lambda: cache)
    first = api.resolve(api.MechanismRequest(gene="HGNC:1", disease="MONDO:1"))
    assert api.snapshot(first["snapshot_id"]) == cache.store.snapshot(first["snapshot_id"]).dict()
    ref = first["direct_evidence"][0]["source_record_ref"]
    assert api.source_record(ref)["source_record_id"] == "G2P-1"
    assert api.compare(api.ComparisonRequest(previous_snapshot=first["snapshot_id"], current_snapshot=first["snapshot_id"]))["changed_evidence"] == []
    with pytest.raises(HTTPException) as exc:
        api.resolve(api.MechanismRequest(gene="HGNC:1", disease="MONDO:2", cache_policy="SNAPSHOT", snapshot_id=first["snapshot_id"]))
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException) as exc:
        api.snapshot("missing")
    assert exc.value.status_code == 404
