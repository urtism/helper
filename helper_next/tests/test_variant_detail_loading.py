"""Cold detail requests verify REF and normalize indels without FASTA checksums."""
import pytest

from helper_next.api import variants as api
from helper_next.core import acmg_reference, reference_validation
from helper_next.core.acmg_sources import SourceManager
from helper_variants import indexer, store
from test_biological_identity import reference_record
from test_variant_query import query_store


@pytest.fixture
def forbid_hashes(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Variant browsing must not hash the full reference")
    monkeypatch.setattr(acmg_reference, "reference_checksum", forbidden)
    monkeypatch.setattr(acmg_reference, "_checksum", forbidden)
    monkeypatch.setattr(indexer, "sha256_file", forbidden)


@pytest.mark.parametrize("reference,alternate", [("A", "G"), ("AA", "A"), ("GA", "G")])
def test_cold_detail_checks_reference_without_checksum(tmp_path, monkeypatch, forbid_hashes, reference, alternate):
    database, sample, _ = query_store(tmp_path)
    record = reference_record(tmp_path, {"1": "AAAAAAAAAAAA"})
    with store.connect(database) as db:
        analysis = db.execute("SELECT id FROM analyses WHERE sample_id=?", (sample,)).fetchone()[0]
        variant = store.get_or_create_variant(db, "GRCh38", "1", 4, reference, alternate,
                                              "SNV" if len(reference) == len(alternate) else "INDEL")
        store.record_call(db, analysis, variant, "DETAIL", "0/1", depth=30)
    monkeypatch.setattr(api, "_entry", lambda identifier: {"database": database, "record": record})
    monkeypatch.setattr(api, "_entry_database", lambda entry: database)
    result = api.sample_variant_detail("RUN", sample, variant)
    identity = result["allele_identity"]
    provenance = identity["reference_provenance"]
    assert provenance["digest"] is None
    if reference == "GA":
        assert identity["status"] == "UNRESOLVED"
        assert provenance["ref_status"] == "MISMATCH"
    else:
        assert identity["status"] == "RESOLVED"
        assert provenance["ref_status"] == "VERIFIED"
        assert provenance["checksum_status"] == "NOT_CHECKED"
        assert identity["allele_ref"].startswith("ga2:")
        if reference == "AA":
            assert identity["identity"]["position"] == 1
    assert result["priority"]["components"]
    assert "clingen_vcep_evidence" in result and "interpretation_context" in result
    assert not reference_validation._directory().exists()


def test_vcep_fallback_can_verify_snv_without_checksum(tmp_path, monkeypatch, forbid_hashes):
    from helper_variants import clingen_vcep_adapter

    record = reference_record(tmp_path)
    received = []
    def lookup(contexts, database):
        received.extend(contexts)
        return [{} for context in contexts]
    monkeypatch.setattr(clingen_vcep_adapter, "lookup_batch", lookup)
    SourceManager().vcep_batch([dict(assembly="GRCh38", chromosome="1", position=7,
                                     reference="G", alternate="T")],
                               record=record, checksum_reference=False)
    identity = received[0]["allele_identity"]
    assert identity["status"] == "RESOLVED"
    assert identity["reference_provenance"]["checksum_status"] == "NOT_CHECKED"
