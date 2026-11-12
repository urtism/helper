"""Explicit, bounded PVS1 persistence; synthetic data and no reference analysis."""
import json
import sqlite3
from dataclasses import asdict

import pytest
from fastapi import HTTPException

from helper_next.api import acmg_calculator as api
from helper_next.core import acmg_pvs1_store as saved
from helper_variants import store
from pvs1.calculator import calculate_pvs1
from test_pvs1_calculator import sample_fixture


@pytest.fixture(autouse=True)
def isolate_pending(monkeypatch, tmp_path):
    saved._pending.clear()
    monkeypatch.setenv("HELPER_GENE_PHENOTYPE_DB", str(tmp_path / "missing-public-index.sqlite"))
    monkeypatch.delenv("HELPER_ACMG_REFERENCE_CONFIG", raising=False)
    yield
    saved._pending.clear()


def snapshot():
    sample = sample_fixture()
    sample.transcript["sequence"] = "ACGT" * 500000  # Must never enter persistence.
    return saved.compact_snapshot(dict(input=asdict(sample), result=asdict(calculate_pvs1(sample))))


@pytest.fixture
def indexed(monkeypatch, tmp_path):
    database = tmp_path / "variants.sqlite"
    sample = sample_fixture()
    sample.variant["contig"] = "chr1"
    metadata = json.dumps(dict(fields={"Gene": sample.disease_context["gene"]}, pvs1_input=asdict(sample)))
    with store.connect(database, store_kind="run") as db:
        db.execute("INSERT INTO runs(id,run_key,reference_build,imported_at) VALUES (1,'run','GRCh38','synthetic')")
        db.execute("INSERT INTO samples(id,sample_key,display_name) VALUES (1,'stable-sample','Synthetic')")
        db.execute("INSERT INTO analyses(id,analysis_key,run_id,sample_id) VALUES (1,'analysis',1,1)")
        db.execute("INSERT INTO variants(id,reference_build,chromosome,position,reference,alternate) VALUES (1,'GRCh38','chr1',1100,'C','T')")
        db.execute("INSERT INTO calls(analysis_id,variant_id) VALUES (1,1)")
        db.execute("INSERT INTO annotation_releases(id,release_key,annotator,reference_build,created_at) VALUES (1,'release','synthetic','GRCh38','synthetic')")
        db.execute("INSERT INTO annotations(id,variant_id,release_id,gene,transcript,consequence,metadata_json) VALUES (7,1,1,?,?,'stop_gained',?)",
                   (sample.disease_context["gene"], sample.transcript["accession"], metadata))
    entry = dict(database=database, record=dict(run_dir=str(tmp_path)))
    monkeypatch.setattr(api, "_entry", lambda _: entry)
    annotation = dict(id=7, transcript=sample.transcript["accession"], gene=sample.disease_context["gene"],
                      consequence="stop_gained", metadata=json.loads(metadata))
    detail = dict(reference_build="GRCh38", chromosome="chr1", position=1100, reference="C", alternate="T", annotations=[annotation])
    monkeypatch.setattr(api, "_selected_annotation", lambda payload: (detail, annotation))
    payload = dict(run_id="run", sample_id=1, variant_id=1, annotation_id=7, transcript=sample.transcript["accession"], prepare_save=True)
    return tmp_path, database, payload


def test_missing_reads_do_not_create_directories_or_databases(tmp_path):
    assert saved.latest(tmp_path, {"sample": "one"}) is None
    assert saved.history(tmp_path, {"sample": "one"}) == []
    assert not (tmp_path / "results").exists()


def test_compact_snapshot_omits_sequences_and_repeated_source_payloads():
    record = snapshot()
    text = json.dumps(record)
    assert len(text.encode()) < 12000
    assert "ACGTACGT" not in text and "source_refs" not in text
    assert "decision_trace" not in text and record["result"]["applied_strength"] == "VERY_STRONG"


def test_explicit_saves_are_append_only_and_identical_saves_are_deduplicated(tmp_path):
    identity = {"sample": "one", "transcript": "TX.1"}
    summary = snapshot()
    first = saved.save(tmp_path, identity, "v1", summary, "first")
    assert first["revision"] == 1
    assert saved.save(tmp_path, identity, "v1", summary, " first ") == first
    second = saved.save(tmp_path, identity, "v1", summary, "second")
    assert second["revision"] == 2
    assert saved.latest(tmp_path, identity) == second
    assert [item["note"] for item in saved.history(tmp_path, identity)] == ["second", "first"]
    assert saved.latest(tmp_path, {**identity, "transcript": "TX.2"}) is None


def test_history_is_indexed_and_paginated(tmp_path):
    identity, summary = {"sample": "one"}, snapshot()
    for n in range(45):
        saved.save(tmp_path, identity, "v1", summary, str(n))
    page = saved.history(tmp_path, identity, limit=10000)
    assert [item["revision"] for item in page] == list(range(45, 25, -1))
    assert saved.history(tmp_path, identity, before=26)[0]["revision"] == 25
    with sqlite3.connect(saved.path(tmp_path)) as db:
        plan = db.execute("EXPLAIN QUERY PLAN SELECT * FROM pvs1_evaluations WHERE identity_key=? AND revision<? ORDER BY revision DESC LIMIT 20", ("key", 100)).fetchall()
    assert any("SEARCH" in row[3] for row in plan) and all("SCAN" not in row[3] for row in plan)


def test_snapshot_and_notes_are_bounded_before_writing(tmp_path):
    with pytest.raises(ValueError):
        saved.save(tmp_path, {}, "v1", {"value": "x" * saved.MAX_SNAPSHOT_BYTES})
    with pytest.raises(ValueError):
        saved.save(tmp_path, {}, "v1", {}, "x" * 1001)
    assert not saved.path(tmp_path).exists()


def test_reference_updates_are_detected_using_metadata_only(monkeypatch, tmp_path):
    reference = tmp_path / "reference.fa"
    reference.write_text("synthetic")
    previous = saved.file_states([str(reference)])
    record = dict(signature="v1", snapshot=dict(reference_files=previous))
    monkeypatch.setattr(type(reference), "read_bytes", lambda *args: pytest.fail("No reference reads"))
    assert not saved.needs_review(record, "v1")
    assert saved.needs_review(record, "v2")
    reference.write_text("changed synthetic reference")
    assert saved.needs_review(record, "v1")


def test_pending_saves_are_bounded_expire_and_are_run_scoped(monkeypatch, tmp_path):
    monkeypatch.setattr(saved, "MAX_PENDING", 2)
    clock = [0]
    monkeypatch.setattr(saved.time, "monotonic", lambda: clock[0])
    first = saved.remember(tmp_path, {}, {}, "v1", {})
    second = saved.remember(tmp_path, {}, {}, "v1", {})
    saved.remember(tmp_path, {}, {}, "v1", {})
    assert len(saved._pending) == 2
    with pytest.raises(ValueError, match="scaduta"):
        saved.pending(first, tmp_path)
    with pytest.raises(ValueError, match="run"):
        saved.pending(second, tmp_path / "other-run")
    clock[0] = saved.PENDING_TTL
    with pytest.raises(ValueError, match="scaduta"):
        saved.pending(second, tmp_path)


def test_api_saves_the_evaluated_result_without_new_analysis(indexed, monkeypatch):
    run_dir, _, payload = indexed
    response = api.evaluate_pvs1({**payload, "strength_override": "SUPPORTING"})
    assert "evaluation_id" in response and not saved.path(run_dir).exists()
    for method in ("analyze_transcripts", "calculate_pvs1", "resolve_pvs1_mechanism"):
        monkeypatch.setattr(api, method, lambda *args, **kwargs: pytest.fail("Persistence must not recalculate"))
    assert api.saved_evaluation(payload)["saved"] is None
    record = api.save_evaluation(dict(run_id="run", evaluation_id=response["evaluation_id"], note="Synthetic review"))["saved"]
    assert record["snapshot"]["result"]["applied_strength"] == "SUPPORTING"
    assert record["snapshot"]["result"]["calculated_strength"] == "VERY_STRONG"
    assert record["snapshot"]["strength_override"]["strength"] == "SUPPORTING"
    assert api.saved_evaluation(payload) == dict(saved=record, needs_review=False)
    assert api.evaluation_history(payload)["items"] == [record]


def test_saved_identity_survives_rebuilt_numeric_ids(indexed):
    run_dir, database, payload = indexed
    scope, identity, signature = api._saved_selection(payload)
    saved.save(scope, identity, signature, snapshot())
    with sqlite3.connect(database) as db:
        db.execute("UPDATE variants SET id=22 WHERE id=1")
        db.execute("UPDATE calls SET variant_id=22")
        db.execute("UPDATE annotations SET variant_id=22,id=77")
        db.execute("UPDATE samples SET id=33")
        db.execute("UPDATE analyses SET sample_id=33")
    new = {**payload, "sample_id": 33, "variant_id": 22, "annotation_id": 77}
    assert api._saved_selection(new) == (str(run_dir), identity, signature)
    assert api.saved_evaluation(new)["saved"]["revision"] == 1


def test_context_lookup_does_not_reload_public_associations(indexed, monkeypatch):
    run_dir, _, payload = indexed
    context = dict(gene=dict(identifier="HGNC:1"), disease=dict(identifier="MONDO:1"),
                   inheritance_modes=["AUTOSOMAL_DOMINANT"])
    context_id = "context-" + api.digest(dict(annotation_id=7, gene="HGNC:1", disease="MONDO:1"))["value"][:24]
    selection = {**payload, "context_id": context_id, "interpretation_context": context}
    monkeypatch.setattr(api.acmg_context, "build", lambda *args: pytest.fail("Lookup must not rebuild public associations"))
    _, identity, signature = api._saved_selection(selection)
    saved.save(run_dir, identity, signature, snapshot())
    assert api.saved_evaluation(selection)["saved"]["identity"]["disease"] == "MONDO:1"
    assert api.evaluation_history(selection)["items"][0]["revision"] == 1
    with pytest.raises(ValueError, match="corrisponde"):
        api._saved_selection({**selection, "context_id": "context-different"})
    for field in ("gene", "disease"):
        with pytest.raises(ValueError, match="Identificativi"):
            api._saved_selection({**selection, "interpretation_context": {**context, field: None}})


def test_updated_annotation_is_flagged_and_old_evaluation_cannot_be_saved(indexed):
    _, database, payload = indexed
    response = api.evaluate_pvs1(payload)
    api.save_evaluation(dict(run_id="run", evaluation_id=response["evaluation_id"]))
    with sqlite3.connect(database) as db:
        db.execute("UPDATE annotations SET hgvsc='changed annotation'")
    assert api.saved_evaluation(payload)["needs_review"]
    with pytest.raises(HTTPException) as exc:
        api.save_evaluation(dict(run_id="run", evaluation_id=response["evaluation_id"]))
    assert "Dati aggiornati" in exc.value.detail


def test_storage_preparation_failure_does_not_block_calculation(indexed, monkeypatch):
    _, _, payload = indexed
    monkeypatch.setattr(api, "_saved_selection", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("read-only storage")))
    response = api.evaluate_pvs1(payload)
    assert response["result"]["applied_strength"] == "VERY_STRONG"
    assert response["persistence_error"] == "read-only storage"
    assert "evaluation_id" not in response
