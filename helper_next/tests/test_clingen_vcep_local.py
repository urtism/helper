"""ERepo source fixtures and failure/retention behavior; no remote requests."""
import csv
import hashlib
import io
import json
import sqlite3
from pathlib import Path

import pytest

from helper_variants import clingen_vcep_local as local, clinvar_local, source_registry


FIXTURES = Path(__file__).parent / "fixtures/clingen_vcep_local"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Offline VCEP operation attempted HTTP")
    monkeypatch.setattr(local, "urlopen", forbidden)


def install(target=None, *, summary=True):
    return local.build_database(FIXTURES / "erepo.tsv", target,
                                summary=FIXTURES / "summary.json" if summary else None)


def changed_export(tmp_path, change):
    with (FIXTURES / "erepo.tsv").open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = list(reader)
        columns = reader.fieldnames
    change(rows, columns)
    path = tmp_path / "changed.tsv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_frozen_official_assertions_are_lossless_and_versioned():
    release = install()
    provenance = json.loads((FIXTURES / "provenance.json").read_text())
    assert release["counts"]["assertions"] == provenance["fixture_records"] == 7
    for filename, expected in provenance["fixture_sha256"].items():
        assert hashlib.sha256((FIXTURES / filename).read_bytes()).hexdigest() == expected
    with (FIXTURES / "erepo.tsv").open(newline="") as handle:
        original = {r["Uuid"]: r for r in csv.DictReader(handle, delimiter="\t")}
    with local.ClinGenVCEPLocal() as reader:
        rows = reader.query(limit=10000)
        assert {r["classification_id"]: r["original"] for r in rows} == original
        for row in rows:
            raw = original[row["classification_id"]]
            assert row["classification"] == raw["Assertion"]
            assert row["disease_id"] == raw["Mondo Id"]
            assert row["expert_panel"] == raw["Expert Panel"]
            assert row["source_url"] == raw["Evidence Repo Link"]
            assert row["official_url"].endswith(row["classification_id"])
            assert row["scv"] is None
            for status, column in (("Met", "Applied Evidence Codes (Met)"), ("Not Met", "Applied Evidence Codes (Not Met)")):
                assert [x["code"] for x in row["criteria"] if x["status"] == status] == local._list(raw[column])
        versioned = [row for row in rows if row["classification_version"]]
        assert len(versioned) == 6
        assert any(row["gene_id"] for row in versioned)
        assert all(row["gene_id"].startswith("NCBI_GENE:") for row in versioned if row["gene_id"])
        assert all(row["classification_version"] in row["available_versions"] for row in versioned)
        assert all(row["classification_version"] is None for row in rows if row["retracted"])
        assert any(row["caid"] is None for row in rows)
        assert any(row["variation_id"] is None for row in rows)
        assert any(row["retracted"] is None for row in rows)
        assert reader.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not reader.connection.execute("PRAGMA foreign_key_check").fetchall()


def test_tsv_only_never_infers_versions_gene_ids_or_scv():
    result = install(summary=False)
    assert result["source_version"] is None
    with local.ClinGenVCEPLocal() as reader:
        for row in reader.query():
            assert row["classification_version"] is row["available_versions"] is row["gene_id"] is row["scv"] is None
            assert row["version_availability"] == "NOT_IN_SELECTED_EXPORTS"
            assert row["original"]["Guideline"]


def test_same_variant_keeps_distinct_contexts_and_exact_filters():
    install()
    with local.ClinGenVCEPLocal() as reader:
        rows = reader.query(variation_id=12982)
        assert len(rows) == 2
        assert len({r["classification_id"] for r in rows}) == 2
        for row in rows:
            assert reader.query(caid=row["caid"], disease_id=row["disease_id"],
                                expert_panel=row["expert_panel"], classification_id=row["classification_id"]) == [row]
        assert reader.query(caid=rows[0]["caid"], variation_id=999999999) == []
        assert reader.query(gene="ryr1") == reader.query(gene="RYR1")
        assert not any(row["retracted"] for row in reader.query(include_retracted=False))
        assert len(reader.query(limit=2, offset=2)) == 2
        statements = []
        reader.connection.set_trace_callback(statements.append)
        reader.query(limit=10000)
        assert len(statements) == 3  # One assertion query and two batch child queries.


def test_hgvs_is_accession_version_specific_and_never_a_gene_label():
    install()
    with local.ClinGenVCEPLocal() as reader:
        hits = reader.query(hgvs="NM_004333.4:c.740T>C")
        assert len(hits) == 1
        assert reader.query(hgvs="NM_004333:c.740T>C") == []
        assert reader.query(hgvs="BRAF") == []
        assert reader.query(hgvs="EX4DEL") == []
        assert reader.lookup_genomic("GRCh38", "chr7", 140801532, "A", "G")["matches"] == hits
        assert reader.lookup_genomic("hg19", "NC_000007.13", 140501332, "a", "g")["matches"] == hits
        assert reader.lookup_genomic("GRCh37", "7", 140801532, "A", "G")["status"] == "NOT_FOUND"
        assert reader.lookup_genomic("GRCh38", "7", 140801532, "A", "C")["status"] == "NOT_FOUND"
        plan = reader.connection.execute("EXPLAIN QUERY PLAN SELECT classification_id FROM hgvs WHERE expression=?", ("x",)).fetchall()
        assert any("hgvs_expression" in row[3] for row in plan)


@pytest.mark.parametrize("allele", [
    ("unknown", "7", 1, "A", "G"), ("GRCh38", "7", 1, "A", "<DEL>"),
    ("GRCh38", "7", 1, "AT", "A"), ("GRCh38", "7", 1, "A", "C,G"),
    ("GRCh38", "MT", 1, "A", "G"), ("GRCh38", "NC_000007.13", 1, "A", "G"),
    ("GRCh38", "7", 0, "A", "G"), ("GRCh38", "7", True, "A", "G"),
])
def test_unsupported_genomic_query_is_not_source_absence(allele):
    install()
    with local.ClinGenVCEPLocal() as reader:
        assert reader.lookup_genomic(*allele)["status"] == "UNSUPPORTED"


def test_snapshot_pinning_backup_retention_rollback_and_cleanup(tmp_path):
    first = install()
    path = local.database_path()
    with local.ClinGenVCEPLocal() as pinned:
        original = pinned.query()
        second = install(summary=False)
        state = local.installation_status()
        assert state["backup"]["snapshot_id"] == first["snapshot_id"]
        assert pinned.release()["snapshot_id"] == first["snapshot_id"]
        assert pinned.query() == original
        with pytest.raises(clinvar_local.ClinVarLocalError, match="active readers"):
            install()
        assert local.installation_status()["manifest"]["snapshot_id"] == second["snapshot_id"]
    third = install()
    assert third["snapshot_id"] == first["snapshot_id"]
    versions = path.parent / (path.name + ".snapshots")
    assert len(list(versions.glob("*.sqlite3"))) == 2
    assert local.rollback()["manifest"]["snapshot_id"] == second["snapshot_id"]
    assert local.rollback()["manifest"]["snapshot_id"] == first["snapshot_id"]
    staging = versions / ".vcep-build-abandoned"
    staging.mkdir()
    (staging / "dataset.sqlite3").touch()
    foreign = versions / ".vcep-build-foreign"
    foreign.mkdir()
    (foreign / "keep.txt").write_text("unrelated")
    result = local.cleanup_snapshots()
    assert str(staging) in result["removed"]
    assert str(foreign) in result["deferred"]
    assert (foreign / "keep.txt").read_text() == "unrelated"


def test_reads_and_registry_are_local_and_do_not_modify_files():
    release = install()
    path = Path(release["snapshot_path"])
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    with local.ClinGenVCEPLocal() as reader:
        reader.query()
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            reader.connection.execute("DELETE FROM assertions")
    source = source_registry.administrative_catalog("clingen_vcep_variants")["sources"][0]
    assert source["installed"] is True and source["status"] == "installed"
    assert source["snapshot_id"] == release["snapshot_id"]
    assert source["version"] is None and source["update_supported"] is False
    assert source["details"]["manifest"]["counts"]["assertions"] == 7
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_missing_corrupt_and_incompatible_sources_do_not_become_not_found(tmp_path):
    path = local.database_path()
    assert local.installation_status()["status"] == "missing"
    assert not path.parent.exists()
    with pytest.raises(local.ClinGenVCEPLocalError):
        local.ClinGenVCEPLocal()
    path.parent.mkdir(parents=True)
    path.write_bytes(b"corrupt")
    assert local.installation_status()["status"] == "error"
    other = tmp_path / "clinvar.sqlite3"
    with sqlite3.connect(str(other)) as db:
        db.execute("PRAGMA user_version=1")
        db.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY,value TEXT)")
        db.execute("INSERT INTO metadata VALUES ('release',?)", (json.dumps(dict(
            source="NCBI ClinVar", validation="complete", snapshot_id="other-source")),))
    with pytest.raises(local.ClinGenVCEPLocalError, match="incompatible"):
        local.ClinGenVCEPLocal(other)


@pytest.mark.parametrize("failure", ["empty", "missing_header", "duplicate_uuid", "uuid", "date", "retracted", "variation_id", "ragged"])
def test_bad_tsv_never_changes_installed_roles(tmp_path, failure):
    first = install()
    path = local.database_path()
    target = path.readlink()
    def change(rows, columns):
        if failure == "empty":
            rows.clear()
        elif failure == "duplicate_uuid":
            rows.append(dict(rows[0]))
        elif failure == "missing_header":
            columns.remove("Uuid")
            for row in rows:
                row.pop("Uuid")
        else:
            field = {"uuid": "Uuid", "date": "Approval Date", "retracted": "Retracted", "variation_id": "ClinVar Variation Id", "ragged": "Uuid"}[failure]
            rows[0][field] = {"uuid": "oops", "date": "2026-99-99", "retracted": "maybe", "variation_id": "bad", "ragged": None}[failure]
    bad = changed_export(tmp_path, change)
    if failure == "ragged":
        lines = bad.read_text().splitlines()
        lines[1] += "\textra"
        bad.write_text("\n".join(lines) + "\n")
    with pytest.raises((local.ClinGenVCEPLocalError, ValueError, sqlite3.Error)):
        local.build_database(bad)
    assert path.readlink() == target
    assert local.installation_status()["manifest"]["snapshot_id"] == first["snapshot_id"]


@pytest.mark.parametrize("field", ["classification", "caId", "cvId", "gene", "mondoId", "condition", "moi", "preferredVarTitle", "summaryDesc", "ep", "publishedDate", "retracted", "hgvs", "metCodes", "docVersion"])
def test_inconsistent_summary_is_rejected_before_publication(tmp_path, field):
    install()
    pointer = local.database_path().readlink()
    payload = json.loads((FIXTURES / "summary.json").read_text())
    payload["data"][0][field] = ["wrong"] if field in ("hgvs", "metCodes") else "wrong"
    bad = tmp_path / "summary.json"
    bad.write_text(json.dumps(payload))
    with pytest.raises(local.ClinGenVCEPLocalError):
        local.build_database(FIXTURES / "erepo.tsv", summary=bad)
    assert local.database_path().readlink() == pointer


@pytest.mark.parametrize("change", ["missing", "duplicate", "unknown"])
def test_summary_completeness_and_uuid_uniqueness(tmp_path, change):
    payload = json.loads((FIXTURES / "summary.json").read_text())
    if change == "missing":
        payload["data"].pop()
    elif change == "duplicate":
        payload["data"].append(payload["data"][0])
    else:
        payload["data"].append(dict(payload["data"][0], uuid="11111111-1111-4111-8111-111111111111"))
    path = tmp_path / "bad-summary.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(local.ClinGenVCEPLocalError):
        local.build_database(FIXTURES / "erepo.tsv", summary=path)
    assert not local.database_path().exists()


def test_extra_columns_are_preserved_and_checksums_are_checked(tmp_path):
    def change(rows, columns):
        columns.append("Future Field")
        for row in rows:
            row["Future Field"] = "future value"
    path = changed_export(tmp_path, change)
    local.build_database(path)
    with local.ClinGenVCEPLocal() as reader:
        assert reader.query()[0]["original"]["Future Field"] == "future value"
    with pytest.raises(local.ClinGenVCEPLocalError, match="SHA-256"):
        local.build_database(path, sources={"export": {"sha256": "0" * 64}})


def test_downloads_only_bulk_sources_and_records_acquisition(tmp_path, monkeypatch):
    requests = []
    def request(url):
        requests.append(url)
        data = (FIXTURES / ("erepo.tsv" if url == local.EXPORT_URL else "summary.json")).read_bytes()
        response = io.BytesIO(data)
        response.headers = {"Content-Length": str(len(data))}
        return response
    monkeypatch.setattr(local, "_request", request)
    sources = local.download_sources(tmp_path)
    assert requests == [local.EXPORT_URL, local.SUMMARY_URL + "?pgSize=20000&pg=1"]
    result = local.build_database(tmp_path / "erepo.tsv", summary=tmp_path / "erepo-summary.json", sources=sources)
    assert all(item["downloaded_at"] for item in result["sources"].values())
    assert all(item["upstream_checksum_verified"] is False for item in result["sources"].values())


def test_truncated_download_preserves_previous_file(tmp_path, monkeypatch):
    path = tmp_path / "erepo.tsv"
    path.write_text("previous download")
    response = io.BytesIO((FIXTURES / "erepo.tsv").read_bytes())
    response.headers = {"Content-Length": "999999999"}
    monkeypatch.setattr(local, "_request", lambda url: response)
    with pytest.raises(local.ClinGenVCEPLocalError, match="Incomplete"):
        local.download_sources(tmp_path)
    assert path.read_text() == "previous download"
    assert not list(tmp_path.glob(".vcep-download-*"))


def test_failed_publication_preserves_current(tmp_path, monkeypatch):
    install()
    pointer = local.database_path().readlink()
    def fail(*args):
        raise OSError("simulated publication error")
    monkeypatch.setattr(clinvar_local, "_select_roles", fail)
    with pytest.raises(OSError, match="simulated"):
        install(summary=False)
    assert local.database_path().readlink() == pointer
    versions = local.database_path().parent / (local.database_path().name + ".snapshots")
    assert len(list(versions.glob("*.sqlite3"))) == 1


def test_interrupted_after_commit_keeps_roles_and_cleanup_retires_orphan(monkeypatch):
    first = install()
    second = install(summary=False)
    switch = clinvar_local._switch_pointer
    def interrupt(*args):
        switch(*args)
        raise KeyboardInterrupt("after atomic publication")
    monkeypatch.setattr(clinvar_local, "_switch_pointer", interrupt)
    with pytest.raises(KeyboardInterrupt, match="after atomic"):
        install()
    state = local.installation_status()
    assert state["manifest"]["snapshot_id"] == first["snapshot_id"]
    assert state["backup"]["snapshot_id"] == second["snapshot_id"]
    local.cleanup_snapshots()
    versions = local.database_path().parent / (local.database_path().name + ".snapshots")
    assert len(list(versions.glob("*.sqlite3"))) == 2


def test_cli_build_info_query_rollback_and_cleanup(tmp_path, capsys):
    target = tmp_path / "vcep.sqlite3"
    prefix = ["--database", str(target)]
    assert local.main(prefix + ["build", str(FIXTURES / "erepo.tsv")]) == 0
    capsys.readouterr()
    assert local.main(prefix + ["info"]) == 0
    assert json.loads(capsys.readouterr().out)["installed"]
    assert local.main(prefix + ["query", "--variation-id", "12982"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 2
    assert local.main(prefix + ["build", str(FIXTURES / "erepo.tsv"), "--summary", str(FIXTURES / "summary.json")]) == 0
    capsys.readouterr()
    assert local.main(prefix + ["rollback"]) == 0
    capsys.readouterr()
    assert local.main(prefix + ["cleanup"]) == 0
    assert json.loads(capsys.readouterr().out)["deferred"] == []
