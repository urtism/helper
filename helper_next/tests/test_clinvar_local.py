"""Offline CACHE-04 contracts; no application provider is replaced."""
import csv
import gzip
import hashlib
import io
import json
import socket
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from helper_variants import clinvar_local as local


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected network access")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(local, "urlopen", forbidden)
    monkeypatch.delenv("HELPER_ACMG_REFERENCE_CONFIG", raising=False)


def summary(**kwargs):
    row = dict.fromkeys(sorted(local.VARIANT_REQUIRED | {"Start", "Stop", "ReferenceAllele", "AlternateAllele", "Cytogenetic"} | {field for kind in local.KINDS for field in kind[1:]}), "-")
    row.update(AlleleID="15041", VariationID="2", Type="single nucleotide variant", Name="fixture",
               GeneID="9907", GeneSymbol="AP5Z1", HGNC_ID="HGNC:22197", Origin="germline",
               ClinicalSignificance="Pathogenic", LastEvaluated="Dec 17, 2024",
               ReviewStatus="criteria provided, multiple submitters, no conflicts", NumberSubmitters="2",
               RCVaccession="RCV000000012|RCV005255549", PhenotypeIDS="MedGen:C3150901|MedGen:C1",
               PhenotypeList="Hereditary spastic paraplegia 48|Second condition", Assembly="GRCh38",
               Chromosome="7", ChromosomeAccession="NC_000007.14", PositionVCF="4781213",
               ReferenceAlleleVCF="G", AlternateAlleleVCF="T")
    row.update(kwargs)
    return row


def submission(**kwargs):
    row = dict.fromkeys(sorted(local.SUBMISSION_REQUIRED | {"SomaticClinicalImpact", "Oncogenicity", "ContributesToAggregateClassification"}), "-")
    row.update(VariationID="2", SCV="SCV001451119.1", Submitter="Laboratory A", ClinicalSignificance="Pathogenic",
               DateLastEvaluated="Dec 17, 2024", ReviewStatus="criteria provided, single submitter",
               ReportedPhenotypeInfo="C3150901:Hereditary spastic paraplegia 48", SubmittedPhenotypeInfo="OMIM:613647",
               ContributesToAggregateClassification="yes")
    row.update(kwargs)
    return row


def write_tsv(path, rows, preamble=False):
    text = io.StringIO(newline="")
    if preamble:
        text.write("##Overview\n#VariationID: identifier assigned by ClinVar\n")
    writer = csv.writer(text, delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n")
    writer.writerow(["#" + list(rows[0])[0]] + list(rows[0])[1:])
    writer.writerows([row.values() for row in rows])
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as zipped:
            zipped.write(text.getvalue().encode("utf-8"))
    return path


def inputs(tmp_path, variants=None, submissions=None):
    return (write_tsv(tmp_path / local.FILES[0], variants or [summary()]),
            write_tsv(tmp_path / local.FILES[1], submissions or [submission()], True))


def build(tmp_path, variants=None, submissions=None):
    paths = inputs(tmp_path, variants, submissions)
    target = tmp_path / "clinvar_local.sqlite3"
    return target, local.build_database(*paths, database=target)


def test_schema_counts_identifiers_conditions_and_lazy_submissions(tmp_path):
    target, report = build(tmp_path, [summary(), summary(Assembly="GRCh37", ChromosomeAccession="NC_000007.13")],
                           [submission(), submission(SCV="SCV000000123.2", Submitter="Lab B", ClinicalSignificance="Benign")])
    assert target.is_symlink()
    assert report["counts"]["variants"] == 1
    assert report["counts"]["submissions"] == 2
    assert report["counts"]["genomic_positions"] == 2
    assert report["snapshot_kind"] == "composite"
    assert not report["common_release_verified"]
    with local.ClinVarLocal(target) as reader:
        assert reader.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        variant = reader.variant(2)
        assert variant["allele_id"] == 15041
        assert variant["vcv"] is None and variant["vcv_version"] is None
        statements = []
        reader.connection.set_trace_callback(statements.append)
        aggregate = reader.aggregate(2)[0]
        assert aggregate["classification"] == "Pathogenic" and aggregate["stars"] == 2
        assert not any("FROM submissions" in sql for sql in statements)
        conditions = reader.conditions(2)
        assert len(conditions) == 2
        assert conditions[0]["classification"] is None
        assert conditions[0]["classification_availability"] == "NOT_IN_SELECTED_DATASETS"
        scvs = reader.submissions(2)
        assert {r["clinical_significance"] for r in scvs} == {"Pathogenic", "Benign"}
        assert {r["scv_version"] for r in scvs} == {1, 2}
        assert len(reader.submissions(2, limit=1, offset=1)) == 1
        assert reader.submission_counts(2) == {"submissions": 2, "interpretation_rows": 2, "submitters": 2}
        disease = reader.condition_classifications(2)
        assert {r["clinical_significance"] for r in disease} == {"Pathogenic", "Benign"}
        assert all(r["scope"] == "submission_condition" for r in disease)
        assert reader.variant(99) is None
        assert reader.submissions(99) == []
        assert {p["assembly"] for p in reader.positions(2)} == {"GRCh37", "GRCh38"}


def test_matching_assembly_alias_alt_batch_multiallelic_and_ambiguity(tmp_path):
    variants = [summary(), summary(VariationID="3", AlleleID="15042", AlternateAlleleVCF="C"),
                summary(VariationID="4", AlleleID="15043")]
    target, _ = build(tmp_path, variants)
    with local.ClinVarLocal(target) as reader:
        queries = [("hg38", "chr7", 4781213, "G", "T"), ("hg38", "7", 4781213, "G", "C"),
                   ("GRCh37", "7", 4781213, "G", "C"), ("hg38", "7", 4781213, "G", "A"),
                   ("hg38", "7", 4781213, "G", "T,C"), ("GRCh38", "NC_000007.13", 4781213, "G", "T")]
        answers = reader.lookup_batch(queries + [queries[1]])
        assert [r["status"] for r in answers] == ["AMBIGUOUS", "FOUND", "NOT_FOUND", "NOT_FOUND", "UNRESOLVED", "UNRESOLVED", "FOUND"]
        assert answers[1] == answers[-1]
        assert answers[1]["allele_identity"][0]["allele_ref"].startswith("ga2:")
        assert [r["variation_id"] for r in answers[0]["matches"]] == [2, 4]
        assert reader.lookup_batch([]) == []
        assert reader.lookup_batch([None])[0]["status"] == "UNRESOLVED"


def test_indel_exact_and_reference_left_alignment(tmp_path):
    target, _ = build(tmp_path, [summary(Chromosome="1", ChromosomeAccession="NC_000001.11", PositionVCF="1", ReferenceAlleleVCF="CA", AlternateAlleleVCF="C")])
    fasta = tmp_path / "reference.fa"
    fasta.write_text(">1\nCAAAAAGTACGT\n")
    Path(str(fasta) + ".fai").write_text("1\t12\t3\t12\t13\n")
    record = {"run_config": {"reference_fasta": str(fasta), "reference_version": "fixture-1"}}
    with local.ClinVarLocal(target) as reader:
        exact = reader.lookup("hg38", "1", 1, "CA", "C")
        assert exact["status"] == "FOUND" and exact["match_method"] == "exact_ncbi_vcf"
        assert reader.lookup("hg38", "1", 4, "AA", "A")["status"] == "UNRESOLVED"
        assert reader.lookup("hg38", "1", 4, "AA", "A", record=record)["status"] == "FOUND"
        mismatch = reader.lookup("hg38", "1", 4, "GA", "G", record=record)
        assert mismatch["status"] == "UNRESOLVED"


def test_unmapped_and_submission_only_variants_survive(tmp_path):
    target, result = build(tmp_path, [summary(PositionVCF="-1", ReferenceAlleleVCF="na", AlternateAlleleVCF="na")],
                           [submission(), submission(VariationID="900", SCV="SCV000000900.1")])
    assert result["counts"]["variants_without_queryable_position"] == 2
    with local.ClinVarLocal(target) as reader:
        assert reader.variant(2)["name"] == "fixture"
        assert reader.variant(900)["allele_id"] is None
        assert len(reader.submissions(900)) == 1


def test_somatic_conflicts_and_unknown_stars(tmp_path):
    target, _ = build(tmp_path, [summary(ClinicalSignificance="Conflicting classifications of pathogenicity",
        ReviewStatus="criteria provided, conflicting classifications", SomaticClinicalImpact="Tier I",
        ReviewStatusClinicalImpact="criteria provided, multiple submitters", Oncogenicity="Oncogenic",
        ReviewStatusOncogenicity="reviewed by expert panel")])
    with local.ClinVarLocal(target) as reader:
        rows = {r["kind"]: r for r in reader.aggregate(2)}
        assert rows["germline"]["has_conflict"] == 1
        assert rows["germline"]["stars"] == 1
        assert rows["somatic_clinical_impact"]["stars"] == 2
        assert rows["somatic_clinical_impact"]["has_conflict"] is None
        assert rows["oncogenicity"]["stars"] == 3
    assert local.review_stars("new upstream vocabulary") is None


@pytest.mark.parametrize("fault", ["truncated", "columns", "header", "empty", "checksum", "scv"])
def test_failed_import_preserves_previous_database(tmp_path, fault):
    target, first = build(tmp_path)
    previous = target.resolve()
    before = previous.read_bytes()
    v, s = inputs(tmp_path)
    if fault == "truncated":
        s.write_bytes(s.read_bytes()[:-8])
    elif fault == "columns":
        with gzip.open(s, "at") as f:
            f.write("1\tbroken\n")
    elif fault == "header":
        with gzip.open(s, "wt") as f:
            f.write("#VariationID\tSCV\n")
    elif fault == "empty":
        with gzip.open(s, "wt") as f:
            f.write("#" + "\t".join(submission()) + "\n")
    elif fault == "checksum":
        Path(str(v) + ".md5").write_text("0" * 32 + "  " + v.name)
    elif fault == "scv":
        write_tsv(s, [submission(SCV="VCV000000002")])
    with pytest.raises((local.ClinVarLocalError, EOFError, gzip.BadGzipFile)):
        local.build_database(v, s, database=target)
    assert target.resolve() == previous
    assert previous.read_bytes() == before
    assert not list(target.parent.glob("*.sqlite3-journal"))


def test_rebuild_pins_old_readers_and_keeps_rollback_snapshot(tmp_path):
    target, first = build(tmp_path)
    with local.ClinVarLocal(target) as old:
        _, repeat = build(tmp_path, [summary(ClinicalSignificance="Benign")])
        assert repeat["previous_snapshot"] == str(old.path)
        assert old.aggregate(2)[0]["classification"] == "Pathogenic"
        with local.ClinVarLocal(target) as current:
            assert current.aggregate(2)[0]["classification"] == "Benign"
        assert Path(first["snapshot_path"]).is_file()
    _, third = build(tmp_path, [summary(ClinicalSignificance="Benign")])
    assert repeat["snapshot_id"] == third["snapshot_id"]
    assert repeat["counts"] == third["counts"]


def test_unmanaged_database_not_replaced(tmp_path):
    v, s = inputs(tmp_path)
    target = tmp_path / "unmanaged.sqlite3"
    target.write_bytes(b"unmanaged")
    with pytest.raises(local.ClinVarLocalError, match="unmanaged"):
        local.build_database(v, s, database=target)
    assert target.read_bytes() == b"unmanaged"


def test_paths_missing_db_and_read_only(tmp_path, monkeypatch):
    monkeypatch.delenv("HELPER_CLINVAR_LOCAL_DB", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert local.database_path() == tmp_path / "helper_variants" / "clinvar_local.sqlite3"
    monkeypatch.setenv("HELPER_CLINVAR_LOCAL_DB", str(tmp_path / "custom.sqlite3"))
    assert local.database_path() == tmp_path / "custom.sqlite3"
    with pytest.raises(local.ClinVarLocalError):
        local.ClinVarLocal()
    assert not local.database_path().exists()
    target, _ = build(tmp_path)
    with local.ClinVarLocal(target) as reader:
        with pytest.raises(sqlite3.OperationalError):
            reader.connection.execute("DELETE FROM variants")


@pytest.mark.parametrize("identifier, suffix", [(13961, "variation/13961/"), ("RCV000000012", "RCV000000012/"),
    ("VCV000013961.3", "variation/VCV000013961.3/"), ("SCV001451119.1", "?term=SCV001451119.1%5Bclv_acc%5D")])
def test_official_urls(identifier, suffix):
    assert local.clinvar_url(identifier) == "https://www.ncbi.nlm.nih.gov/clinvar/" + suffix


def test_md5_official_absolute_path_and_bsd_forms():
    digest = "1" * 32
    assert local._expected_md5(digest + "  /am/ftp-pub-clinvar/tab_delimited/variant_summary.txt.gz\n", local.FILES[0]) == digest
    assert local._expected_md5("MD5 (variant_summary.txt.gz) = " + digest, local.FILES[0]) == digest
    with pytest.raises(local.ClinVarLocalError):
        local._expected_md5(digest + "  wrong.txt.gz", local.FILES[0])


class Response(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(data)
        self.headers = headers or {}


@pytest.mark.parametrize("failure", [None, "length", "checksum"])
def test_download_integrity_and_single_acquisition(tmp_path, monkeypatch, failure):
    v, s = inputs(tmp_path)
    payloads = {name: (tmp_path / name).read_bytes() for name in local.FILES}
    calls = []
    def request(url, method="GET", timeout=120):
        calls.append(url)
        name = url.rsplit("/", 1)[-1]
        if name.endswith(".md5"):
            original = name[:-4]
            digest = hashlib.md5(payloads[original]).hexdigest() if failure != "checksum" else "0" * 32
            return Response((digest + "  " + original).encode())
        content = payloads[name]
        return Response(content, {"Content-Length": str(len(content) + (1 if failure == "length" else 0)), "Last-Modified": "fixture"})
    monkeypatch.setattr(local, "_request", request)
    directory = tmp_path / "download"
    if failure:
        with pytest.raises(local.ClinVarLocalError):
            local.download_sources(directory)
        assert not list(directory.glob("*.part"))
    else:
        sources = local.download_sources(directory)
        assert len(calls) == 4 and len(set(calls)) == 4
        assert all(m["checksum_verified"] for m in sources.values())
        target = tmp_path / "current.sqlite3"
        result = local.build_database(*(directory / name for name in local.FILES), database=target, sources=sources)
        assert result["sources"][local.FILES[0]]["downloaded_at"]
        assert not any(item["changed"] for item in local.check_for_updates(target).values())


def test_10000_batch_deduplicates_sql_and_preserves_order(tmp_path):
    target, _ = build(tmp_path)
    query = ("GRCh38", "7", 4781213, "G", "T")
    with local.ClinVarLocal(target) as reader:
        sql = []
        reader.connection.set_trace_callback(sql.append)
        results = reader.lookup_batch([query] * 10000)
        assert len(results) == 10000 and all(r["status"] == "FOUND" for r in results)
        assert len([s for s in sql if "WITH requested" in s]) == 1


def test_known_official_variants_match_frozen_source(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "clinvar_local"
    if not fixture.exists():
        pytest.fail("Missing frozen NCBI fixture")
    target = tmp_path / "official.sqlite3"
    result = local.build_database(fixture / "variant_summary.tsv.gz", fixture / "submission_summary.tsv.gz", database=target)
    with local.ClinVarLocal(target) as reader:
        assert reader.variant(13961)["gene_symbol"] == "BRAF"
        assert reader.variant(7105)["gene_symbol"] == "CFTR"
        for kind, name in ((local.VARIANT_REQUIRED, "variant_summary"), (local.SUBMISSION_REQUIRED, "submission_summary")):
            with local._rows(fixture / (name + ".tsv.gz"), kind) as (_, rows):
                for row in rows:
                    if name == "variant_summary":
                        aggregate = {r["kind"]: r for r in reader.aggregate(row["VariationID"])}
                        assert aggregate["germline"]["classification"] == local._text(row["ClinicalSignificance"])
                        assert aggregate["germline"]["review_status"] == local._text(row["ReviewStatus"])
                        assert reader.variant(row["VariationID"])["allele_id"] == int(row["AlleleID"])
                        p = local._position(row)
                        if p[5] == "queryable":
                            answer = reader.lookup(p[0], p[1], p[2], p[3], p[4])
                            assert int(row["VariationID"]) in [r["variation_id"] for r in answer["matches"]]
                    else:
                        scvs = reader.submissions(row["VariationID"], limit=10000)
                        original = next(r for r in scvs if r["scv"] == row["SCV"])
                        assert original["clinical_significance"] == local._text(row["ClinicalSignificance"])
                        assert original["condition_name"] == local._text(row["ReportedPhenotypeInfo"])
    assert result["counts"]["variants"] == 5


@pytest.mark.parametrize("change", [dict(ClinicalSignificance="Benign"), dict(GeneSymbol="OTHER"), dict(NumberSubmitters="0")])
def test_inconsistent_duplicate_rows_are_rejected(tmp_path, change):
    target, _ = build(tmp_path)
    before = target.resolve()
    paths = inputs(tmp_path, [summary(), summary(Assembly="GRCh37", ChromosomeAccession="NC_000007.13", **change)])
    with pytest.raises(sqlite3.IntegrityError, match="Inconsistent duplicate"):
        local.build_database(*paths, database=target)
    assert target.resolve() == before


def test_unknown_columns_and_unaligned_conditions_are_preserved(tmp_path):
    target, _ = build(tmp_path, [summary(NewUpstreamColumn="kept", PhenotypeList="one value", NumberSubmitters="0")],
                      [submission(UnknownSubmissionColumn="also kept")])
    with local.ClinVarLocal(target) as reader:
        variant = reader.variant(2)
        assert variant["number_submitters"] == 0
        assert variant["details"]["NewUpstreamColumn"] == "kept"
        assert variant["details"]["unaligned_condition_source"]["PhenotypeList"] == "one value"
        assert reader.conditions(2)[0]["condition_name"] is None
        assert reader.submissions(2)[0]["details"]["UnknownSubmissionColumn"] == "also kept"


def test_publication_failure_keeps_current_pointer(tmp_path, monkeypatch):
    target, _ = build(tmp_path)
    original = target.resolve()
    def fail(*args, **kwargs):
        raise OSError("simulated pointer publication failure")
    monkeypatch.setattr(local.os, "replace", fail)
    with pytest.raises(OSError, match="simulated"):
        build(tmp_path, [summary(ClinicalSignificance="Benign")])
    assert target.resolve() == original
    with local.ClinVarLocal(target) as reader:
        assert reader.aggregate(2)[0]["classification"] == "Pathogenic"


def test_missing_and_invalid_schema_never_report_a_biological_miss(tmp_path):
    target = tmp_path / "invalid.sqlite3"
    with sqlite3.connect(target) as db:
        db.execute("PRAGMA user_version=999")
    with pytest.raises(local.ClinVarLocalError, match="schema"):
        local.ClinVarLocal(target)
    target.write_bytes(b"not a database")
    with pytest.raises(local.ClinVarLocalError):
        local.ClinVarLocal(target)


def test_distinct_batch_keys_use_bounded_sql_chunks(tmp_path):
    target, _ = build(tmp_path)
    queries = [("GRCh38", "7", 4781213 + offset, "G", "T") for offset in range(1000)]
    with local.ClinVarLocal(target) as reader:
        sql = []
        reader.connection.set_trace_callback(sql.append)
        results = reader.lookup_batch(queries)
        assert results[0]["status"] == "FOUND"
        assert all(row["status"] == "NOT_FOUND" for row in results[1:])
        assert len([s for s in sql if "WITH requested" in s]) == 7


@pytest.mark.parametrize("query", [("unknown", "7", 4781213, "G", "T"), ("hg38", "7", 0, "G", "T"),
    ("hg38", "7", 4781213, "N", "T"), ("hg38", "7", 4781213, "G", "<DEL>"),
    ("hg38", "7", 4781213, "G", "G"), ("hg38", "7", True, "G", "T")])
def test_unsupported_alleles_do_not_match(tmp_path, query):
    target, _ = build(tmp_path)
    with local.ClinVarLocal(target) as reader:
        result = reader.lookup(*query)
        assert result["status"] == "UNRESOLVED" and result["matches"] == []


def test_query_methods_validate_identifiers_and_pagination(tmp_path):
    target, _ = build(tmp_path)
    with local.ClinVarLocal(target) as reader:
        with pytest.raises(local.ClinVarLocalError):
            reader.variant("2 OR 1=1")
        with pytest.raises(ValueError):
            reader.submissions(2, limit=0)
        with pytest.raises(ValueError):
            reader.condition_classifications(2, offset=-1)
        with pytest.raises(ValueError):
            local.clinvar_url("https://malicious.example")


def test_cli_info_and_local_build(tmp_path, capsys):
    v, s = inputs(tmp_path)
    target = tmp_path / "cli.sqlite3"
    local.main(["--database", str(target), "build", "--variant-summary", str(v), "--submission-summary", str(s)])
    built = json.loads(capsys.readouterr().out)
    local.main(["--database", str(target), "info"])
    info = json.loads(capsys.readouterr().out)
    assert info["snapshot_id"] == built["snapshot_id"]


def test_source_assembly_alias_is_canonicalized_and_raw_coordinates_survive(tmp_path):
    target, _ = build(tmp_path, [summary(Assembly="hg19", ChromosomeAccession="NC_000007.13", Start="4781214")])
    with local.ClinVarLocal(target) as reader:
        assert reader.lookup("GRCh37", "7", 4781213, "G", "T")["status"] == "FOUND"
        position = reader.positions(2)[0]
        assert position["assembly"] == "GRCh37"
        assert position["source_coordinates"]["Assembly"] == "hg19"
        assert position["source_coordinates"]["Start"] == "4781214"


def test_official_multiple_interpretations_with_same_versioned_scv_are_preserved(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "clinvar_local" / "submission_duplicate_scv.tsv.gz"
    v, _ = inputs(tmp_path)
    target = tmp_path / "duplicate-scv.sqlite3"
    report = local.build_database(v, fixture, database=target)
    assert report["counts"]["submissions"] == 2
    assert report["counts"]["distinct_scvs"] == 1
    with local.ClinVarLocal(target) as reader:
        original = json.loads((fixture.parent / "provenance.json").read_text())["duplicate_scv_fixture"]
        rows = reader.submissions(original["variation_ids"][0])
        assert len(rows) == 2
        assert {r["scv"] for r in rows} == {"SCV000024996.132"}
        assert {r["clinical_significance"] for r in rows} == {"not provided", "Pathogenic"}
        assert len({r["source_row"] for r in rows}) == 2
        assert reader.submission_counts(original["variation_ids"][0])["interpretation_rows"] == 2


def test_retention_consecutive_updates_keep_current_and_predecessor_only(tmp_path):
    target, first = build(tmp_path)
    previous = target.resolve()
    for label in ("Benign", "Uncertain significance", "Likely pathogenic", "Pathogenic"):
        _, result = build(tmp_path, [summary(ClinicalSignificance=label)])
        current, backup, generation = local._roles(target)
        assert current == target.resolve() and backup == previous
        assert set(local._snapshots(current.parent)) == {current, backup}
        assert len(list(current.parent.glob(".roles-*"))) == 1
        with local.ClinVarLocal(target) as reader:
            assert reader.aggregate(2)[0]["classification"] == label
        previous = current
    assert not Path(first["snapshot_path"]).exists()


def test_rollback_is_atomic_reversible_and_preserves_database_bytes(tmp_path, monkeypatch):
    target, _ = build(tmp_path)
    build(tmp_path, [summary(ClinicalSignificance="Benign")])
    current, backup, _ = local._roles(target)
    content = {p: p.read_bytes() for p in (current, backup)}
    def forbidden(*args, **kwargs):
        pytest.fail("Rollback must not build or download")
    monkeypatch.setattr(local, "build_database", forbidden)
    monkeypatch.setattr(local, "download_sources", forbidden)
    with local.ClinVarLocal(target) as pinned:
        local.rollback(target)
        assert local._roles(target)[:2] == (backup, current)
        assert pinned.aggregate(2)[0]["classification"] == "Benign"
        with local.ClinVarLocal(target) as restored:
            assert restored.aggregate(2)[0]["classification"] == "Pathogenic"
        local.rollback(target)
    assert local._roles(target)[:2] == (current, backup)
    assert {p: p.read_bytes() for p in (current, backup)} == content


@pytest.mark.parametrize("raw", [False, True])
def test_active_backup_blocks_third_snapshot_without_changing_roles(tmp_path, raw):
    target, _ = build(tmp_path)
    backup = target.resolve()
    build(tmp_path, [summary(ClinicalSignificance="Benign")])
    before = local._roles(target)[:2]
    reader = sqlite3.connect(str(backup)) if raw else local.ClinVarLocal(backup)
    try:
        if raw:
            reader.execute("SELECT * FROM metadata").fetchone()
        with pytest.raises(local.ClinVarLocalError, match="active"):
            build(tmp_path, [summary(ClinicalSignificance="Uncertain significance")])
        assert local._roles(target)[:2] == before
        assert len(local._snapshots(backup.parent)) == 2
        assert not list(backup.parent.glob(".clinvar-build-*"))
    finally:
        reader.close()
    build(tmp_path, [summary(ClinicalSignificance="Uncertain significance")])
    assert not backup.exists()


def test_failed_validation_and_interrupted_build_preserve_both_roles(tmp_path):
    target, _ = build(tmp_path)
    build(tmp_path, [summary(ClinicalSignificance="Benign")])
    before = local._roles(target)[:2]
    content = {p: p.read_bytes() for p in before}
    v, s = inputs(tmp_path)
    s.write_bytes(s.read_bytes()[:-8])
    with pytest.raises(EOFError):
        local.build_database(v, s, database=target)
    v, s = inputs(tmp_path)
    def interrupt(counts):
        raise KeyboardInterrupt("simulated interrupted import")
    with pytest.raises(KeyboardInterrupt):
        local.build_database(v, s, database=target, progress=interrupt)
    assert local._roles(target)[:2] == before
    assert {p: p.read_bytes() for p in before} == content
    assert len(local._snapshots(before[0].parent)) == 2
    assert not list(before[0].parent.glob(".clinvar-build-*"))


def test_interruption_after_atomic_commit_keeps_coherent_pair_and_prunes(tmp_path, monkeypatch):
    target, _ = build(tmp_path)
    first = target.resolve()
    build(tmp_path, [summary(ClinicalSignificance="Benign")])
    previous = target.resolve()
    switch = local._switch_pointer
    def interrupted_switch(*args):
        switch(*args)
        raise KeyboardInterrupt("after commit")
    monkeypatch.setattr(local, "_switch_pointer", interrupted_switch)
    with pytest.raises(KeyboardInterrupt):
        build(tmp_path, [summary(ClinicalSignificance="Uncertain significance")])
    current, backup, _ = local._roles(target)
    assert backup == previous and current != previous
    assert not first.exists()
    assert set(local._snapshots(current.parent)) == {current, backup}
    with local.ClinVarLocal(target) as reader:
        assert reader.aggregate(2)[0]["classification"] == "Uncertain significance"


def test_cleanup_abandoned_staging_preserves_open_files_and_foreign_artifacts(tmp_path):
    target, _ = build(tmp_path)
    versions = target.resolve().parent
    stale = versions / ".clinvar-build-abandoned"
    stale.mkdir()
    (stale / "dataset.sqlite3").write_bytes(b"interrupted build")
    active = versions / ".clinvar-build-reader"
    active.mkdir()
    (active / "dataset.sqlite3").write_bytes(b"open staging")
    foreign = versions / ".clinvar-build-foreign"
    foreign.mkdir()
    (foreign / "user-file.txt").write_text("keep")
    with (active / "dataset.sqlite3").open("rb"):
        result = local.cleanup_snapshots(target)
        assert not stale.exists() and active.exists() and foreign.exists()
        assert str(active) in result["deferred"]
    local.cleanup_snapshots(target)
    assert not active.exists() and foreign.exists()


def test_killed_builder_is_cleaned_without_touching_active_builder(tmp_path):
    target, _ = build(tmp_path)
    versions = target.resolve().parent
    stage = versions / ".clinvar-build-killed"
    code = """import fcntl,os,sqlite3,sys
from pathlib import Path
versions,stage=map(Path,sys.argv[1:])
fd=os.open(str(versions),os.O_RDONLY|os.O_DIRECTORY)
fcntl.flock(fd,fcntl.LOCK_EX)
stage.mkdir()
db=sqlite3.connect(str(stage/'dataset.sqlite3'))
db.execute('CREATE TABLE partial(x)');db.commit()
print('ready',flush=True)
sys.stdin.read()
"""
    process = subprocess.Popen([sys.executable, "-c", code, str(versions), str(stage)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == "ready"
        with pytest.raises(local.ClinVarLocalError, match="busy"):
            local.cleanup_snapshots(target)
        assert stage.exists()
        process.kill()
        process.wait(timeout=10)
        local.cleanup_snapshots(target)
        assert not stage.exists() and target.exists()
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)


def test_legacy_retention_requires_explicit_history_and_preserves_manifests(tmp_path):
    target, _ = build(tmp_path)
    first = target.resolve()
    saved = first.read_bytes()
    build(tmp_path, [summary(ClinicalSignificance="Benign")])
    current = target.resolve()
    target.unlink()
    target.symlink_to(current)
    orphan = current.parent / ("0" * 20 + "-" + "1" * 32 + ".sqlite3")
    orphan.write_bytes(saved)
    with pytest.raises(local.ClinVarLocalError, match="history"):
        local.cleanup_snapshots(target)
    assert orphan.exists() and first.exists()
    before = {p: p.read_bytes() for p in (current, first)}
    local.cleanup_snapshots(target, legacy_backup=first)
    assert local._roles(target)[:2] == (current, first)
    assert not orphan.exists()
    assert {p: p.read_bytes() for p in before} == before


def test_initial_legacy_store_migrates_without_creating_fake_backup(tmp_path):
    target, _ = build(tmp_path)
    current = target.resolve()
    content = current.read_bytes()
    target.unlink()
    target.symlink_to(current)
    result = local.cleanup_snapshots(target)
    assert result["backup"] is None and target.resolve() == current
    assert current.read_bytes() == content
    with pytest.raises(local.ClinVarLocalError, match="No BACKUP"):
        local.rollback(target)


def test_partial_download_cleanup_leaves_live_downloads_and_unowned_files(tmp_path):
    stale = tmp_path / ".clinvar-download-stale.part"
    active = tmp_path / ".clinvar-download-active.part"
    foreign = tmp_path / "unrelated.part"
    for p in (stale, active, foreign):
        p.write_bytes(b"partial")
    with active.open("rb") as handle:
        local.fcntl.flock(handle.fileno(), local.fcntl.LOCK_EX)
        result = local._cleanup_download_parts(tmp_path)
        assert not stale.exists() and active.exists() and foreign.exists()
        assert str(active) in result["deferred"]
    local._cleanup_download_parts(tmp_path)
    assert not active.exists() and foreign.exists()


def test_retention_cli_rollback_and_cleanup(tmp_path, capsys):
    target, _ = build(tmp_path)
    first = target.resolve()
    build(tmp_path, [summary(ClinicalSignificance="Benign")])
    local.main(["--database", str(target), "rollback"])
    assert json.loads(capsys.readouterr().out)["current"] == str(first)
    local.main(["--database", str(target), "cleanup"])
    assert json.loads(capsys.readouterr().out)["current"] == str(first)


@pytest.mark.parametrize("name,blocked", [("(sd-pam)", False), ("gnome-keyring-d", False), ("ssh-agent", False), ("python", True), ("unknown-reader", True)])
def test_proc_visibility_credential_helpers_do_not_veto_retention(tmp_path, monkeypatch, name, blocked):
    path = tmp_path / "probe.sqlite3"
    path.write_bytes(b"probe")
    class HiddenDescriptors:
        def iterdir(self):
            raise PermissionError("nondumpable process")
    class Process:
        name = "123"
        def stat(self):
            return SimpleNamespace(st_uid=local.os.getuid())
        def __truediv__(self, part):
            return HiddenDescriptors() if part == "fd" else SimpleNamespace(read_text=lambda: name)
    proc = SimpleNamespace(is_dir=lambda: True, iterdir=lambda: iter([Process()]))
    monkeypatch.setattr(local, "Path", lambda value: proc)
    assert local._open_elsewhere(path, -1) is blocked
