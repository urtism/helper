"""CACHE-05: local snapshots drive operational evidence, ordering and detail."""
import fcntl
import json
import socket
import sqlite3
from pathlib import Path

import pytest

from helper_next.api import variants as api
from helper_prioritization import apply_clinvar_evidence, score_variant
from helper_variants import clinvar, clinvar_local as local, query
from helper_variants.clinvar_adapter import LocalEvidence
from test_clinvar_local import inputs, summary, submission
from test_variant_query import query_store


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Ordinary variant browsing must not use HTTP")
    monkeypatch.setattr(clinvar, "_request", forbidden)
    monkeypatch.setattr(clinvar, "cached_evidence", forbidden)
    monkeypatch.setattr(local, "urlopen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def install(tmp_path, monkeypatch, variants=None, submissions=None):
    source_dir = tmp_path / "sources"
    source_dir.mkdir(exist_ok=True)
    paths = inputs(source_dir, variants, submissions)
    target = tmp_path / "clinvar.sqlite3"
    release = local.build_database(*paths, database=target)
    monkeypatch.setenv("HELPER_CLINVAR_LOCAL_DB", str(target))
    return target, release


def at(position=5, **kwargs):
    fields = dict(Chromosome="1", ChromosomeAccession="NC_000001.11",
                  PositionVCF=str(position), ReferenceAlleleVCF="A", AlternateAlleleVCF="G")
    fields.update(kwargs)
    return summary(**fields)


def test_adapter_batch_fields_duplicates_and_only_grouped_submission_counts(tmp_path, monkeypatch):
    target, _ = install(tmp_path, monkeypatch)
    allele = ("GRCh38", "7", 4781213, "G", "T")
    with LocalEvidence() as source:
        statements = []
        source.reader.connection.set_trace_callback(statements.append)
        rows = source.batch([allele] * 1100)
        assert rows[0] == rows[-1]
        result = rows[0]
        assert result["matching_status"] == "FOUND"
        assert result["clinical_status"] == "CLASSIFIED"
        assert result["classifications"] == ["Pathogenic"]
        assert result["review_statuses"][0]["stars"] == 2
        assert result["allele_id"] == 15041
        assert result["variation_id"] == 2
        assert result["submitter_count"] == 2
        assert result["conditions"] == ["Hereditary spastic paraplegia 48", "Second condition"]
        assert result["rcv_accessions"] == ["RCV000000012", "RCV005255549"]
        assert result["source"] == "ClinVar Local"
        assert result["snapshot_id"] == source.manifest["snapshot_id"]
        assert result["provenance"]["common_release_verified"] is False
        assert result["allele_identity"][0]["allele_ref"].startswith("ga2:")
        assert "VCV" not in json.dumps(result["identifiers"])
        assert result["submission_classification_breakdown"] == [{"label": "Pathogenic", "count": 1}]
        assert len(statements) == 4  # genomic, variants, aggregates, grouped submission counts
        assert not any("SELECT * FROM submissions" in sql for sql in statements)
        reader = source.reader
    with pytest.raises(sqlite3.ProgrammingError):
        reader.connection.execute("SELECT 1")
    with target.resolve().open("rb") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_combined_benign_classification_has_separate_submission_counts_in_list(tmp_path, monkeypatch):
    install(tmp_path, monkeypatch, [at(1, ClinicalSignificance="Benign/Likely benign")], [
        submission(SCV="SCV000000001.1", ClinicalSignificance="Benign"),
        submission(SCV="SCV000000002.1", ClinicalSignificance="Likely benign"),
        submission(SCV="SCV000000003.1", ClinicalSignificance="Likely benign"),
        submission(SCV="SCV000000004.1", ClinicalSignificance="not provided"),
    ])
    path, sample, _ = query_store(tmp_path)
    page = query.list_variants(path, sample)
    evidence = next(row["clinvar_evidence"] for row in page["items"] if row["position"] == 1)
    assert evidence["classifications"] == ["Benign/Likely benign"]
    assert evidence["has_conflict"] is False
    assert evidence["submission_classification_breakdown"] == [
        {"label": "Likely benign", "count": 2}, {"label": "Benign", "count": 1},
        {"label": "not provided", "count": 1},
    ]
    assert "submissions" not in evidence


@pytest.mark.parametrize("sort_by", ["priority", "gene", ""])
def test_clinvar_class_filter_precedes_pagination_and_uses_local_submission_labels(tmp_path, monkeypatch, sort_by):
    install(tmp_path, monkeypatch, [
        at(1, ClinicalSignificance="Benign"),
        at(2, VariationID="3", ClinicalSignificance="Conflicting classifications of pathogenicity"),
        at(4, VariationID="4"),
    ], [
        submission(ClinicalSignificance="Benign"),
        submission(VariationID="3", SCV="SCV000000002.1"),
        submission(VariationID="3", SCV="SCV000000003.1", ClinicalSignificance="Uncertain significance"),
        submission(VariationID="4", SCV="SCV000000004.1"),
    ])
    path, sample, _ = query_store(tmp_path)
    kwargs = dict(clinical_significances="pathogenic", sort_by=sort_by, limit=1)
    first = query.list_variants(path, sample, **kwargs)
    assert first["next_cursor"]
    second = query.list_variants(path, sample, cursor=first["next_cursor"], **kwargs)
    assert sorted(row["position"] for row in first["items"] + second["items"]) == [2, 4]
    assert second["next_cursor"] is None
    benign = query.list_variants(path, sample, clinical_significances="benign", sort_by=sort_by)
    assert [row["position"] for row in benign["items"]] == [1]  # VCF calls this pathogenic.
    assert benign["items"][0]["clinvar_evidence"]["submission_classification_breakdown"] == [{"label": "Benign", "count": 1}]
    vus = query.list_variants(path, sample, clinical_significances="uncertain_significance", sort_by=sort_by)
    assert [row["position"] for row in vus["items"]] == [2]
    absent = query.list_variants(path, sample, clinical_significances="__not_reported__", sort_by=sort_by)
    assert sorted(row["position"] for row in absent["items"]) == [3, 5]
    multiple = query.list_variants(path, sample, clinical_significances="benign,pathogenic", sort_by=sort_by)
    assert sorted(row["position"] for row in multiple["items"]) == [1, 2, 4]
    restricted = query.list_variants(path, sample, clinical_significances="pathogenic", genes="GENE1", sort_by=sort_by)
    assert [row["position"] for row in restricted["items"]] == [2]
    install(tmp_path, monkeypatch, [at(1, ClinicalSignificance="Benign")], [submission(ClinicalSignificance="Benign")])
    assert query.list_variants(path, sample, **kwargs)["items"] == []


def test_detail_classification_counts_only_reviewed_submissions_across_pages(tmp_path, monkeypatch):
    install(tmp_path, monkeypatch, [at(1)], [
        submission(SCV="SCV000000001.1"),
        submission(SCV="SCV000000002.1", ReviewStatus="no assertion criteria provided"),
        submission(SCV="SCV000000003.1", ClinicalSignificance="Benign", ReviewStatus="no assertion criteria provided"),
        submission(SCV="SCV000000004.1", ClinicalSignificance="Uncertain significance", ReviewStatus="unknown review status"),
        submission(SCV="SCV000000005.1", ClinicalSignificance="Likely pathogenic", ReviewStatus="reviewed by expert panel"),
    ])
    path, sample, _ = query_store(tmp_path)
    detail = query.variant_detail(path, sample, 1, submissions_limit=1)
    evidence = detail["clinvar_evidence"]
    assert len(evidence["submissions"]) == 1
    assert evidence["submission_classification_breakdown"][0] == {"label": "Pathogenic", "count": 2}
    assert evidence["reviewed_submission_classification_breakdown"] == [
        {"label": "Likely pathogenic", "count": 1}, {"label": "Pathogenic", "count": 1},
    ]
    assert evidence["classifications"] == ["Pathogenic"]


def test_batch_many_unique_alleles_has_bounded_queries(tmp_path, monkeypatch):
    install(tmp_path, monkeypatch, [at(position=i, VariationID=str(i + 10), AlleleID=str(i + 100))
                                    for i in range(1, 202)])
    with LocalEvidence() as source:
        statements = []
        source.reader.connection.set_trace_callback(statements.append)
        results = source.batch([("GRCh38", "1", i, "A", "G") for i in range(1, 202)])
    assert all(row["matching_status"] == "FOUND" for row in results)
    assert len(statements) == 5  # 2 genomic chunks, variants, classifications, grouped counts


def test_conflict_list_counts_are_batched_without_loading_submission_rows(tmp_path, monkeypatch):
    install(tmp_path, monkeypatch, [at(1, ClinicalSignificance="Conflicting classifications of pathogenicity")], [
        submission(SCV="SCV000000001.1"),
        submission(SCV="SCV000000001.1", ReportedPhenotypeInfo="Another condition"),
        submission(SCV="SCV000000002.1", ClinicalSignificance="Benign"),
    ])
    with LocalEvidence() as source:
        statements = []
        source.reader.connection.set_trace_callback(statements.append)
        rows = source.batch([("GRCh38", "1", 1, "A", "G")] * 1000)
        assert rows[0]["submission_classification_breakdown"] == [
            {"label": "Benign", "count": 1}, {"label": "Pathogenic", "count": 1},
        ]
        assert len(statements) == 4
        assert "submissions" not in rows[0]
        assert not any("SELECT * FROM submissions" in sql for sql in statements)
        assert rows[0] == rows[-1]
        def fail(*args):
            raise sqlite3.DatabaseError("unreadable counts")
        monkeypatch.setattr(source.reader, "submission_classification_counts_batch", fail)
        fallback = source.batch([("GRCh38", "1", 1, "A", "G")])[0]
        assert fallback["matching_status"] == "FOUND"
        assert fallback["classifications"] == rows[0]["classifications"]
        assert fallback["submission_classification_breakdown"] == []


@pytest.mark.parametrize("allele,state", [
    (("GRCh38", "7", 4781213, "G", "T"), "FOUND"),
    (("GRCh37", "7", 4820846, "G", "T"), "FOUND"),
    (("GRCh38", "7", 4781214, "G", "T"), "NOT_FOUND"),
    (("unknown", "7", 4781213, "G", "T"), "UNRESOLVED"),
    (("GRCh38", "7", 4781213, "G", "T,A"), "UNRESOLVED"),
    (("GRCh38", "1", 100, "AA", "A"), "FOUND"),
    (("GRCh38", "1", 101, "AA", "A"), "UNRESOLVED"),
])
def test_matching_states_and_assemblies(tmp_path, monkeypatch, allele, state):
    install(tmp_path, monkeypatch, [summary(), summary(Assembly="GRCh37", ChromosomeAccession="NC_000007.13",
        PositionVCF="4820846"), at(100, VariationID="3", AlleleID="99", ReferenceAlleleVCF="AA", AlternateAlleleVCF="A")])
    with LocalEvidence() as source:
        result = source.batch([allele])[0]
    assert result["matching_status"] == state
    if state != "FOUND":
        assert result["classifications"] == []
        assert result["clinical_status"] in {"NOT_FOUND", "NOT_EVALUABLE"}


def test_ambiguous_never_picks_first(tmp_path, monkeypatch):
    install(tmp_path, monkeypatch, [summary(), summary(VariationID="3", AlleleID="99")])
    with LocalEvidence() as source:
        result = source.batch([("GRCh38", "7", 4781213, "G", "T")])[0]
    assert result["matching_status"] == "AMBIGUOUS"
    assert len(result["matches"]) == 2
    assert result["classifications"] == []
    assert "variation_id" not in result


def test_run_reference_resolves_shifted_indel_without_new_normalization(tmp_path, monkeypatch):
    install(tmp_path, monkeypatch, [at(1, ReferenceAlleleVCF="CA", AlternateAlleleVCF="C")])
    fasta = tmp_path / "reference.fa"
    fasta.write_text(">1\nCAAAAAGTACGT\n")
    Path(str(fasta) + ".fai").write_text("1\t12\t3\t12\t13\n")
    record = {"run_config": {"reference_fasta": str(fasta), "reference_version": "fixture-1"}}
    with LocalEvidence() as source:
        allele = ("GRCh38", "1", 4, "AA", "A")
        assert source.batch([allele])[0]["matching_status"] == "UNRESOLVED"
        evidence = source.batch([allele], record=record)[0]
        assert evidence["matching_status"] == "FOUND"
        assert evidence["match_method"] == "ga2"
        assert evidence["allele_identity"][0]["reference_provenance"]["ref_status"] == "VERIFIED"


def test_submission_breakdown_counts_distinct_scvs_across_pages_without_changing_aggregate(tmp_path, monkeypatch):
    install(tmp_path, monkeypatch, [summary(ClinicalSignificance="Conflicting classifications of pathogenicity")], [
        submission(SCV="SCV000000001.1"),
        submission(SCV="SCV000000001.1", ReportedPhenotypeInfo="Another condition"),
        submission(SCV="SCV000000002.1", ClinicalSignificance="Benign"),
        submission(SCV="SCV000000003.1", ClinicalSignificance="-", Oncogenicity="Oncogenic"),
        submission(SCV="SCV000000004.1", ClinicalSignificance="Benign", ContributesToAggregateClassification="no"),
    ])
    with LocalEvidence() as source:
        evidence = source.batch([("GRCh38", "7", 4781213, "G", "T")])[0]
        priority = apply_clinvar_evidence(score_variant({}), evidence)
        source.submissions(evidence, limit=1)
        assert len(evidence["submissions"]) == 1
        assert evidence["submission_count"] == 4
        assert evidence["submission_interpretation_count"] == 5
        assert evidence["submission_classification_breakdown"] == [
            {"label": "Benign", "count": 2}, {"label": "Pathogenic", "count": 1},
        ]
        assert evidence["classifications"] == ["Conflicting classifications of pathogenicity"]
        assert evidence["classification_breakdown"] == []  # No inferred aggregate contributors.
        assert apply_clinvar_evidence(score_variant({}), evidence) == priority
        source.submissions(evidence, limit=1, offset=4)
        assert evidence["submission_classification_breakdown"][0] == {"label": "Benign", "count": 2}


def test_optional_submission_error_does_not_change_priority_and_reader_closes(tmp_path, monkeypatch):
    install(tmp_path, monkeypatch)
    with LocalEvidence() as source:
        evidence = source.batch([("GRCh38", "7", 4781213, "G", "T")])[0]
        priority = apply_clinvar_evidence(score_variant({}), evidence)
        def fail(*args, **kwargs):
            raise sqlite3.DatabaseError("unreadable submissions page")
        monkeypatch.setattr(source.reader, "submissions", fail)
        source.submissions(evidence)
        assert "unreadable" in evidence["submissions_error"]
        assert apply_clinvar_evidence(score_variant({}), evidence) == priority
        connection = source.reader.connection
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


@pytest.mark.parametrize("damage", ["missing", "corrupt", "schema"])
def test_database_errors_preserve_variants_and_ignore_api_cache(tmp_path, monkeypatch, damage):
    target = tmp_path / "bad.sqlite3"
    if damage == "corrupt":
        target.write_bytes(b"not sqlite")
    elif damage == "schema":
        with sqlite3.connect(target) as db:
            db.execute("PRAGMA user_version=999")
    monkeypatch.setenv("HELPER_CLINVAR_LOCAL_DB", str(target))
    # Old API evidence must never be substituted, even when usable and fresh.
    clinvar._store(clinvar.cache_path(), "GRCh38|1|5|A|G", {
        "status": "available", "classifications": ["Pathogenic"], "review_statuses": [{"stars": 4}],
    })
    api_bytes = clinvar.cache_path().read_bytes()
    path, sample, _ = query_store(tmp_path)
    page = query.list_variants(path, sample)
    assert len(page["items"]) == 5
    assert page["clinvar_status"] == "ERROR"
    for row in page["items"]:
        assert row["clinvar_evidence"]["matching_status"] == "ERROR"
        assert row["clinvar_evidence"]["last_error"]
        assert not component(row)["evaluated"]
        assert component(row)["score"] == 0
    detail = query.variant_detail(path, sample, page["items"][0]["variant_id"])
    assert detail["clinvar_evidence"]["matching_status"] == "ERROR"
    assert clinvar.cache_path().read_bytes() == api_bytes


def component(item):
    return next(row for row in item["priority"]["components"] if row["key"] == "clinvar")


@pytest.mark.parametrize("label,review", [
    ("Pathogenic", "practice guideline"), ("Likely pathogenic", "reviewed by expert panel"),
    ("Benign/Likely benign", "criteria provided, multiple submitters, no conflicts"),
    ("Uncertain significance", "criteria provided, single submitter"),
    ("not yet mapped", "new unknown review"), ("-", "-"),
])
def test_equivalent_legacy_and_local_scores_for_non_conflicting_aggregates(tmp_path, monkeypatch, label, review):
    install(tmp_path, monkeypatch, [summary(ClinicalSignificance=label, ReviewStatus=review)])
    with LocalEvidence() as source:
        evidence = source.batch([("GRCh38", "7", 4781213, "G", "T")])[0]
        legacy = clinvar._summary_evidence({"uid": "2", "germline_classification": {
            "description": label if label != "-" else "",
            "review_status": review if review != "-" else "",
        }})
        base = score_variant({"consequence": "missense_variant", "population_af": 0.0001})
        assert apply_clinvar_evidence(base, legacy) == apply_clinvar_evidence(base, evidence)
        once = apply_clinvar_evidence(base, evidence)
        assert apply_clinvar_evidence(once, evidence) == once


def test_missing_germline_and_discordant_scvs_do_not_create_aggregate(tmp_path, monkeypatch):
    install(tmp_path, monkeypatch, [summary(ClinicalSignificance="-", ReviewStatus="-", Oncogenicity="Oncogenic")],
            [submission(), submission(SCV="SCV000000002.1", ClinicalSignificance="Benign", Submitter="B")])
    with LocalEvidence() as source:
        evidence = source.batch([("GRCh38", "7", 4781213, "G", "T")])[0]
        before = apply_clinvar_evidence(score_variant({}), evidence)
        source.submissions(evidence, limit=1)
        assert evidence["submissions_next_offset"] == 1
        assert evidence["submissions"][0]["contributes_to_germline_aggregate"] is None
        assert evidence["clinical_status"] == "NO_GERMLINE_CLASSIFICATION"
        assert evidence["oncogenicity"] == ["Oncogenic"]
        assert evidence["classifications"] == []
        assert apply_clinvar_evidence(score_variant({}), evidence) == before


def test_global_priority_snapshot_invalidation_and_reuse(tmp_path, monkeypatch):
    target, _ = install(tmp_path, monkeypatch, [at()])
    path, sample, other_sample = query_store(tmp_path)
    seen = []
    original = query.score_variant
    monkeypatch.setattr(query, "score_variant", lambda row, **kwargs: (seen.append(row), original(row, **kwargs))[1])
    first = query.list_variants(path, sample, limit=1)
    assert len(seen) == 5
    assert first["items"][0]["position"] == 5
    assert component(first["items"][0])["score"] == 20
    query.list_variants(path, sample, limit=1, cursor=first["next_cursor"])
    assert len(seen) == 6
    old_snapshot = first["clinvar_snapshot_id"]
    install(tmp_path, monkeypatch, [at(ClinicalSignificance="Benign")])
    second = query.list_variants(path, sample)
    assert len(seen) == 11  # entire candidate set recalculated
    assert second["clinvar_snapshot_id"] != old_snapshot
    assert second["items"][-1]["position"] == 5
    assert component(second["items"][-1])["score"] == -20
    assert len([c for c in second["items"][-1]["priority"]["components"] if c["key"] == "clinvar"]) == 1
    # Shared allele does not change matching with carrier/sample or duplicate input.
    assert query.list_variants(path, other_sample)["items"][0]["clinvar_evidence"]["matching_status"] == "NOT_FOUND"
    with LocalEvidence() as source:
        connection = source.reader.connection
        with pytest.raises(RuntimeError):
            with LocalEvidence() as nested:
                nested_connection = nested.reader.connection
                raise RuntimeError("request aborted")
        with pytest.raises(sqlite3.ProgrammingError):
            nested_connection.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
    assert len(list(target.parent.glob(target.name + ".snapshots/*.sqlite3"))) == 2


def test_shared_allele_uses_same_evidence_across_samples_and_runs(tmp_path, monkeypatch):
    install(tmp_path, monkeypatch, [at(1)])
    path, sample, other_sample = query_store(tmp_path)
    first = query.list_variants(path, sample, variant_id=1)["items"][0]
    shared = query.list_variants(path, other_sample)["items"][0]
    another = tmp_path / "another-run"
    another.mkdir()
    other_path, third_sample, _ = query_store(another)
    third = query.list_variants(other_path, third_sample, variant_id=1)["items"][0]
    assert first["clinvar_evidence"] == shared["clinvar_evidence"] == third["clinvar_evidence"]
    assert first["clinvar_evidence"]["matching_status"] == "FOUND"
    assert component(first) == component(shared) == component(third)


def test_pinned_current_changes_during_operation_then_readers_release(tmp_path, monkeypatch):
    target, _ = install(tmp_path, monkeypatch, [at()])
    with LocalEvidence() as pinned:
        allele = ("GRCh38", "1", 5, "A", "G")
        first = pinned.batch([allele])[0]
        install(tmp_path, monkeypatch, [at(ClinicalSignificance="Benign")])
        assert pinned.batch([allele])[0] == first
        with LocalEvidence() as current:
            assert current.snapshot_id != pinned.snapshot_id
            assert current.batch([allele])[0]["classifications"] == ["Benign"]
    # A third publication can retire the previous reader's snapshot after close.
    install(tmp_path, monkeypatch, [at(ClinicalSignificance="Uncertain significance")])
    assert len(list(target.parent.glob(target.name + ".snapshots/*.sqlite3"))) == 2


def test_detail_api_local_submission_pages_and_no_remote_refresh(tmp_path, monkeypatch):
    install(tmp_path, monkeypatch, [at(1, SCVsForAggregateGermlineClassification="SCV001451119.1")],
            [submission(), submission(SCV="SCV000000002.1", Submitter="B", ClinicalSignificance="Benign")])
    path, sample, _ = query_store(tmp_path)
    monkeypatch.setattr(api, "_entry", lambda identifier: {"database": path})
    monkeypatch.setattr(api, "_entry_database", lambda entry: path)
    page = api.sample_variants("RUN", sample, limit=100)
    item = next(row for row in page["items"] if row["position"] == 1)
    detail = api.sample_variant_detail("RUN", sample, item["variant_id"], refresh_clinvar=True,
                                       submissions_limit=1)
    evidence = detail["clinvar_evidence"]
    assert detail["clinvar_refresh"]["status"] == "NOT_APPLICABLE"
    assert detail["priority"] == item["priority"]
    assert evidence["snapshot_id"] == item["clinvar_evidence"]["snapshot_id"]
    assert evidence["classifications"] == ["Pathogenic"]
    assert evidence["review_statuses"][0]["stars"] == 2
    assert evidence["source_url"].endswith("/variation/2/")
    assert evidence["submissions"][0]["source_url"].startswith("https://www.ncbi.nlm.nih.gov/clinvar/")
    assert evidence["submissions"][0]["contributes_to_germline_aggregate"] is False
    assert detail["vcf_clinvar_evidence"]["source"] == "Original VCF annotation"
    assert detail["vcf_clinvar_evidence"]["identifiers"] == ["456", "VCV000000456.2"]
    assert detail["database_ids"]["clinvar"] == ["2"]
    next_detail = api.sample_variant_detail("RUN", sample, item["variant_id"], submissions_limit=1,
                                            submissions_offset=1)
    assert next_detail["clinvar_evidence"]["submissions"][0]["contributes_to_germline_aggregate"] is True
    assert next_detail["clinvar_evidence"]["submissions_next_offset"] is None
    assert next_detail["priority"] == detail["priority"]
    with pytest.raises(api.HTTPException) as exc:
        api.sample_variant_detail("RUN", sample, item["variant_id"], submissions_limit=0)
    assert exc.value.status_code == 400


def test_benign_vus_conflict_priority_agrees_in_list_and_submission_pages(tmp_path, monkeypatch):
    labels = ["Likely benign"] * 8 + ["Benign"] * 3 + ["Uncertain significance"]
    install(tmp_path, monkeypatch, [at(1,
        ClinicalSignificance="Conflicting classifications of pathogenicity",
        ReviewStatus="criteria provided, conflicting classifications",
    )], [submission(SCV="SCV{:09d}.1".format(index), ClinicalSignificance=label)
         for index, label in enumerate(labels, 1)])
    path, sample, _ = query_store(tmp_path)
    monkeypatch.setattr(api, "_entry", lambda identifier: {"database": path})
    monkeypatch.setattr(api, "_entry_database", lambda entry: path)
    page = api.sample_variants("RUN", sample, limit=100)
    item = next(row for row in page["items"] if row["position"] == 1)
    assert component(item)["score"] == -11.2
    assert "B/LB and VUS" in component(item)["reason"]
    assert item["clinvar_evidence"]["classifications"] == ["Conflicting classifications of pathogenicity"]
    for offset in (0, 8, 11):
        detail = api.sample_variant_detail("RUN", sample, item["variant_id"],
                                           submissions_limit=1, submissions_offset=offset)
        assert len(detail["clinvar_evidence"]["submissions"]) == 1
        assert detail["priority"] == item["priority"]
