"""CACHE-08: local external assertions, with no clinical interpretation transfer."""
import csv
import json
import socket
from pathlib import Path

import pytest

from helper_next.api import variants as api
from helper_next.core.acmg_sources import SourceManager
from helper_variants import clingen_vcep_local as local, clingen_vcep_adapter as adapter
from helper_variants import query
from test_variant_query import query_store


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    adapter._REFERENCES.clear()
    def forbidden(*args, **kwargs):
        pytest.fail("Variant evidence must remain offline")
    monkeypatch.setattr(local, "urlopen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def dataset(tmp_path, *, revision=1):
    """Synthetic assertions using the independently verified ERepo headers."""
    original = Path(__file__).parent / "fixtures/clingen_vcep_local/erepo.tsv"
    with original.open(newline="") as handle:
        template = next(csv.DictReader(handle, delimiter="\t"))
    rows = []
    for index in range(5):
        group = 0 if index < 3 else index - 2
        caid, variation_id = ("CA111", "11111") if group == 0 else ("CA222", "22222") if group == 1 else ("CA333", "33333")
        expressions = ("NM_000001.1:c.1A>G,NM_000001.1(GENE1):c.1A>G,NC_000001.11:g.1A>G,NC_000001.10:g.10A>G" if group == 0
                       else "NM_000001.1:c.2A>T,NC_000001.11:g.2A>T" if group == 1
                       else "NM_000001.1:c.3del,NC_000001.11:g.3del")
        identifier = "{:08d}-1111-4111-8111-111111111111".format(revision * 10 + index)
        row = dict(template, Uuid=identifier, Variation=expressions.split(",")[0],
                   Disease="Disease " + str(index), Assertion="Pathogenic" if index != 1 else "Likely Benign",
                   Retracted="true" if index == 1 else "" if index == 2 else "false")
        row.update({"ClinVar Variation Id": variation_id, "Allele Registry Id": caid,
                    "HGVS Expressions": expressions, "HGNC Gene Symbol": "GENE1", "Mondo Id": "MONDO:000000" + str(index + 1),
                    "Mode of Inheritance": "Autosomal dominant inheritance", "Expert Panel": "Panel " + str(index),
                    "Summary of interpretation": "External panel interpretation <script>unsafe()</script>",
                    "Applied Evidence Codes (Met)": "PS3_Strong,PM2_Supporting,PVS1",
                    "Applied Evidence Codes (Not Met)": "PS4,BS1",
                    "Evidence Repo Link": local.classification_url(identifier)})
        rows.append(row)
    path = tmp_path / ("source-" + str(revision) + ".tsv")
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=local.COLUMNS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    summaries = []
    for row in rows:
        summaries.append(dict(uuid=row["Uuid"], caId=row["Allele Registry Id"], cvId=row["ClinVar Variation Id"],
                              gene=row["HGNC Gene Symbol"], mondoId=row["Mondo Id"], condition=row["Disease"],
                              moi=row["Mode of Inheritance"], preferredVarTitle=row["Variation"],
                              summaryDesc=row["Summary of interpretation"], classification=row["Assertion"], ep=row["Expert Panel"],
                              approvedDate=row["Approval Date"], publishedDate=row["Published Date"],
                              retracted={"true": True, "false": False, "": None}[row["Retracted"]],
                              hgvs=row["HGVS Expressions"].split(","), metCodes=row["Applied Evidence Codes (Met)"].split(","),
                              unMetCodes=row["Applied Evidence Codes (Not Met)"].split(","),
                              docVersion="2.1.0", versionsList=["1.0.0", "2.1.0"], geneNcbiId="1", affiliationId=str(50000 + rows.index(row))))
    summary = tmp_path / ("summary-" + str(revision) + ".json")
    summary.write_text(json.dumps(dict(data=summaries)))
    return local.build_database(path, summary=summary), rows


def snv(position=1, alt="G", assembly="GRCh38"):
    return dict(assembly=assembly, chromosome="1", position=position, reference="A", alternate=alt)


def test_source_manager_exact_ids_all_contexts_and_original_criteria(tmp_path):
    release, _ = dataset(tmp_path)
    manager = SourceManager()
    result = manager.vcep({}, variation_ids=[11111], caids=["CA111"], hgvs=["NM_000001.1:c.1A>G"])
    assert result["status"] == "FOUND" and result["snapshot_id"] == release["snapshot_id"]
    assert result["application"] == "INFORMATION_ONLY" and result["clinical_context_status"] == "NOT_SELECTED"
    assert len(result["assertions"]) == 3
    assert manager.vcep({}, hgvs=["NM_000001.1(GENE1):c.1A>G"])["status"] == "FOUND"
    assert len({r["expert_panel"] for r in result["assertions"]}) == 3
    assert len({r["disease_id"] for r in result["assertions"]}) == 3
    assert {r["retracted"] for r in result["assertions"]} == {True, False, None}
    for row in result["assertions"]:
        assert row["source_id"] == "clingen_vcep_variants"
        assert row["classification_version"] == "2.1.0"
        assert row["available_versions"] == ["1.0.0", "2.1.0"]
        assert row["gene_id"] == "NCBI_GENE:1"
        assert row["met_codes"] == ["PS3_Strong", "PM2_Supporting", "PVS1"]
        assert row["not_met_codes"] == ["PS4", "BS1"]
        assert {r["code"]: r["strength"] for r in row["criteria"]} == {
            "PS3_Strong": "Strong", "PM2_Supporting": "Supporting", "PVS1": None, "PS4": None, "BS1": None}
        assert "original" not in row and "hgvs" not in row  # Large aliases/raw JSON stay in the source DB.


def test_supported_snv_uses_ga2_but_erepo_ref_stays_unverified(tmp_path):
    dataset(tmp_path)
    result = SourceManager().vcep(snv())
    assert result["status"] == "FOUND"
    assert result["match_methods"] == ["EXACT_GENOMIC_SNV_HGVS"]
    assert result["reference_status"] == "UNVERIFIED"
    assert result["allele_identity"]["allele_ref"].startswith("ga2:")
    assert SourceManager().vcep(snv(10, assembly="GRCh37"))["status"] == "FOUND"
    assert SourceManager().vcep(snv(10, assembly="GRCh38"))["status"] == "NOT_FOUND"


def test_attached_identity_is_qualified_for_the_requested_allele(tmp_path):
    dataset(tmp_path)
    manager = SourceManager()
    attached = manager.vcep(snv())["allele_identity"]
    result = manager.vcep(snv(2), allele_identity=attached)
    assert result["status"] == "NOT_FOUND"
    assert result["allele_identity"]["original"]["position"] == 2


def test_reference_verification_does_not_upgrade_erepo_or_hide_ref_mismatch(tmp_path):
    from test_biological_identity import reference_record
    dataset(tmp_path)
    verified = SourceManager().vcep(snv(), record=reference_record(tmp_path, {"1": "AAAAAA"}))
    assert verified["status"] == "FOUND"
    assert verified["allele_identity"]["reference_provenance"]["ref_status"] == "VERIFIED"
    assert verified["reference_status"] == "UNVERIFIED"
    mismatch = SourceManager().vcep(dict(snv(), reference="C"),
                                    record=reference_record(tmp_path, {"1": "AAAAAA"}))
    assert mismatch["status"] == "UNSUPPORTED"
    assert mismatch["allele_identity"]["reference_provenance"]["ref_status"] == "MISMATCH"


def test_absent_supported_queries_are_not_errors_or_benign(tmp_path):
    dataset(tmp_path)
    result = SourceManager().vcep(snv(100))
    assert result["status"] == "NOT_FOUND" and not result["assertions"]
    assert result["snapshot_id"]
    assert SourceManager().vcep({}, caids=["CA999999"])["status"] == "NOT_FOUND"


def test_indels_require_exact_identifiers_or_existing_versioned_hgvs(tmp_path):
    dataset(tmp_path)
    identity = dict(snv(3), reference="AT", alternate="A")
    manager = SourceManager()
    assert manager.vcep(identity)["status"] == "UNSUPPORTED"
    assert manager.vcep(identity, variation_ids=[33333])["status"] == "FOUND"
    assert manager.vcep(identity, hgvs=["NM_000001.1:c.3del"])["status"] == "FOUND"
    assert manager.vcep(identity, hgvs=["NM_000001:c.3del", "c.3del", "NP_000001.1:p.Ala1Gly"])["status"] == "UNSUPPORTED"
    assert manager.vcep(dict(gene="GENE1", rsid="rs123"))["status"] == "UNSUPPORTED"


@pytest.mark.parametrize("extra", [dict(variation_ids=[22222]), dict(caids=["CA222"]),
                                     dict(hgvs=["NM_000001.1:c.2A>T"]), dict(variation_ids=[11111, 22222]),
                                     dict(variation_ids=[99999]), dict(hgvs=["NM_000001.1:c.999A>G"])])
def test_discordant_signals_are_ambiguous_and_never_select_a_candidate(tmp_path, extra):
    dataset(tmp_path)
    result = SourceManager().vcep(snv(), **extra)
    assert result["status"] == "AMBIGUOUS"
    assert not result["assertions"] and result["candidate_assertions"]


def test_database_missing_corrupt_wrong_schema_and_broken_tables(tmp_path, monkeypatch):
    manager = SourceManager()
    assert manager.vcep(snv())["status"] == "ERROR"
    target = local.database_path()
    assert not target.parent.exists()
    target.parent.mkdir(parents=True)
    target.write_bytes(b"corrupt")
    assert manager.vcep(snv())["status"] == "ERROR"
    target.unlink()
    dataset(tmp_path)
    import sqlite3
    broken = tmp_path / "broken.sqlite3"
    with sqlite3.connect(str(broken)) as connection:
        connection.execute("PRAGMA user_version=999")
    assert SourceManager(vcep_database=broken).vcep(snv())["status"] == "ERROR"


def test_snapshot_change_invalidates_uuid_cache_without_patient_writes(tmp_path):
    first, _ = dataset(tmp_path)
    manager = SourceManager()
    old = manager.vcep(snv())
    assert old["snapshot_id"] == first["snapshot_id"]
    second, _ = dataset(tmp_path, revision=2)
    current = manager.vcep(snv())
    assert current["status"] == "FOUND" and current["snapshot_id"] == second["snapshot_id"]
    assert {r["classification_id"] for r in old["assertions"]}.isdisjoint(r["classification_id"] for r in current["assertions"])
    # The cache holds only references, never assertions, criteria or summaries.
    assert "External panel interpretation" not in repr(adapter._REFERENCES)
    assert "PS3_Strong" not in repr(adapter._REFERENCES)


def test_batch_deduplicates_queries_and_reuses_only_snapshot_scoped_references(tmp_path, monkeypatch):
    dataset(tmp_path)
    traces = []
    init = local.ClinGenVCEPLocal.__init__
    def traced(self, *args, **kwargs):
        init(self, *args, **kwargs)
        self.connection.set_trace_callback(traces.append)
    monkeypatch.setattr(local.ClinGenVCEPLocal, "__init__", traced)
    contexts = [dict(snv(), caids=["CA111"], variation_ids=[11111])] * 1100
    results = SourceManager().vcep_batch(contexts)
    assert len(results) == 1100 and all(r["status"] == "FOUND" for r in results)
    assert len(traces) == 6  # Three alias queries, assertions, criteria, HGVS.
    traces.clear()
    SourceManager().vcep_batch(contexts)
    assert len(traces) == 3  # UUID references reused; source facts read fresh.
    assert all("FROM assertions WHERE classification_id IN" in sql or "FROM criteria" in sql or "FROM hgvs WHERE classification_id IN" in sql for sql in traces)
    assert len(adapter._REFERENCES) == 1


def test_batch_uses_chunked_queries_for_distinct_variants(tmp_path, monkeypatch):
    dataset(tmp_path)
    traces = []
    init = local.ClinGenVCEPLocal.__init__
    def traced(self, *args, **kwargs):
        init(self, *args, **kwargs)
        self.connection.set_trace_callback(traces.append)
    monkeypatch.setattr(local.ClinGenVCEPLocal, "__init__", traced)
    results = SourceManager().vcep_batch([snv(position) for position in range(1, 601)])
    assert len(results) == 600 and results[0]["status"] == "FOUND"
    assert all(row["status"] == "NOT_FOUND" for row in results[1:])
    assert len(traces) == 5  # Two HGVS IN queries, three selected-detail queries.


def test_context_extraction_does_not_promote_display_ids_or_multiallelic_info():
    detail = dict(reference_build="GRCh38", chromosome="1", position=3, reference="AT", alternate="A",
                  database_ids=dict(clinvar=["9999"], clingen=["CA999"]),
                  metadata=dict(vcf_id="rs123;CA999", original_vcf=dict(alternates=["A", "G"],
                                info=dict(CLNVID="11111", CAID="CA999"))),
                  annotations=[dict(hgvsc="NM_000001.1:c.3del", metadata=dict(fields={
                      "ClinVarVariationID": "33333", "ClinGen_CAID": "CA333", "Existing_variation": "SCV000011111.1"}))])
    context = adapter.variant_context(detail)
    assert context["variation_ids"] == ["33333"]
    assert context["caids"] == ["CA333"]
    assert context["hgvs"] == ["NM_000001.1:c.3del"]


def test_api_adds_vcep_without_changing_clinvar_priority_or_acmg_context(tmp_path, monkeypatch):
    from test_clinvar_integration import install, at
    install(tmp_path, monkeypatch, [at(1, VariationID="11111")])
    path, sample, _ = query_store(tmp_path)
    monkeypatch.setattr(api, "_entry", lambda identifier: {"database": path})
    monkeypatch.setattr(api, "_entry_database", lambda entry: path)
    baseline = api.sample_variant_detail("RUN", sample, 1)
    original_bytes = path.read_bytes()
    release, _ = dataset(tmp_path)
    available = api.sample_variant_detail("RUN", sample, 1)
    # Conflicting trusted original IDs (456/CA789) versus the actual genomic
    # match are reported instead of silently accepting either source.
    assert available["clingen_vcep_evidence"]["status"] == "AMBIGUOUS"
    for key in ("priority", "clinvar_evidence", "interpretation_context", "allele_identity"):
        assert available[key] == baseline[key]
    assert path.read_bytes() == original_bytes
    assert available["clingen_vcep_evidence"]["snapshot_id"] == release["snapshot_id"]
    # The query used by the independent ACMG calculator still transports the
    # original local ClinVar data and never injects VCEP criterion activation.
    raw = query.variant_detail(path, sample, 1)
    assert "clingen_vcep_evidence" not in raw


def test_actual_browser_detail_receives_all_matching_assertions(tmp_path, monkeypatch):
    path, sample, _ = query_store(tmp_path)
    from helper_variants import store
    with store.connect(path) as db:
        # Remove deliberately conflicting annotation IDs from this fixture.
        db.execute("UPDATE annotations SET metadata_json='{}',hgvsc='' WHERE variant_id=1")
    monkeypatch.setattr(api, "_entry", lambda identifier: {"database": path})
    monkeypatch.setattr(api, "_entry_database", lambda entry: path)
    dataset(tmp_path)
    detail = api.sample_variant_detail("RUN", sample, 1)
    assert detail["clingen_vcep_evidence"]["status"] == "FOUND"
    assert len(detail["clingen_vcep_evidence"]["assertions"]) == 3
