"""Main-only, shared molecular analysis and immutable user classification checks."""
import copy
import json
import sqlite3
from dataclasses import asdict

import pytest
from fastapi import HTTPException

from helper_next.api import acmg_calculator as api
from helper_next.core import acmg_classification as scoring
from helper_next.core import acmg_classification_store as saved
from helper_next.core import acmg_pvs1_store as pvs1_saved
from helper_next.core import acmg_automatic_store as automatic_saved
from helper_next.core.acmg_digest import digest
from test_pvs1_calculator import sample_fixture
from test_pvs1_store import indexed


@pytest.fixture
def automatic(indexed, monkeypatch):
    run_dir, database, payload = indexed
    monkeypatch.setenv("HELPER_GENE_PHENOTYPE_DB", str(run_dir / "missing.sqlite"))
    pvs1_saved._pending.clear()
    with sqlite3.connect(database) as db:
        db.row_factory = sqlite3.Row
        row = dict(db.execute("SELECT * FROM annotations WHERE id=7").fetchone())
        db.execute("UPDATE annotations SET canonical=1,impact='HIGH' WHERE id=7")
    annotation = {**row, "canonical": True, "impact": "HIGH", "metadata": json.loads(row["metadata_json"])}
    detail = dict(reference_build="GRCh38", chromosome="chr1", position=1100, reference="C", alternate="T", annotations=[annotation])
    monkeypatch.setattr(api.query, "_variant_detail", lambda *a, **k: copy.deepcopy(detail))
    monkeypatch.setattr(api.query, "variant_detail", lambda *a, **k: pytest.fail("Automatic ACMG reads local annotations only"))
    builds, analyses, evaluations = [], [], []
    diseases = ["MONDO:1", "MONDO:2"]

    def catalog(value, **kwargs):
        builds.append(value)
        return {"annotations": [dict(annotation_id=ann["id"], transcript=ann["transcript"], gene_symbol=ann["gene"],
            cache_status="ready", cache_refreshing=False, contexts=[dict(
                id="context-" + digest(dict(annotation_id=ann["id"], gene="HGNC:1", disease=disease))["value"][:24],
                context=dict(gene={"identifier": "HGNC:1"}, disease={"identifier": disease}, inheritance_modes=["AUTOSOMAL_DOMINANT"]), origin={})
                for disease in diseases]) for ann in value["annotations"]]}

    def prepare(value, ann, choice):
        evaluations.append(choice["context"])
        sample = sample_fixture()
        sample.disease_context["disease"] = choice["context"]["disease"]["identifier"]
        if sample.disease_context["disease"] == "MONDO:2": sample.disease_context["molecular_mechanism"] = "GoF"
        sample.transcript["accession"] = ann["transcript"]
        sample.molecular_effect["products"][0]["transcript_ref"] = ann["transcript"] + "|synthetic-product:v1"
        return sample, "INDEXED_ANNOTATION", [], None

    def molecular(value, ann, **kwargs):
        analyses.append((ann["id"], kwargs))
        return dict(transcripts=[], warnings=[], release_verified=True)

    monkeypatch.setattr(api.acmg_context, "build", catalog)
    monkeypatch.setattr(api, "prepare_pvs1_input", prepare)
    monkeypatch.setattr(api, "analyze_transcripts", molecular)
    yield dict(run_dir=run_dir, database=database, payload=payload, detail=detail, diseases=diseases,
               builds=builds, analyses=analyses, evaluations=evaluations)
    pvs1_saved._pending.clear()


def test_one_batch_shares_main_product_and_persists_rebuildable_results(automatic):
    case = automatic
    result = api.automatic_classification(case["payload"])
    assert len(case["builds"]) == 1 and len(case["analyses"]) == 1 and len(case["evaluations"]) == 2
    assert case["analyses"][0] == (7, {"selected_only": True, "record": {"run_dir": str(case["run_dir"])}})
    assert result["mains"][0]["annotation_id"] == 7 and result["automatic_criteria"] == ["PVS1"]
    first, second = result["automatic"]
    assert first["assessment"]["classification"] == "LIKELY_PATHOGENIC" and first["assessment"]["total_points"] == 8
    assert first["assessment"]["criteria"][0]["origin"] == "PVS1_AUTO"
    assert second["assessment"]["classification"] == "NOT_EVALUATED" and not second["assessment"]["criteria"]
    assert second["pvs1"]["status"] == "INACTIVE"
    assert pvs1_saved.path(case["run_dir"]).exists()
    assert saved.latest(case["run_dir"], first["identity"]) is None
    text = json.dumps(result)
    assert "reference_sequence" not in text and len(text) < 15000


def test_multiple_lof_diseases_reuse_the_same_molecular_analysis(automatic, monkeypatch):
    case = automatic
    prepare = api.prepare_pvs1_input
    def both_lof(detail, annotation, choice):
        sample, origin, warnings, assessment = prepare(detail, annotation, choice)
        sample.disease_context["molecular_mechanism"] = "LoF"
        return sample, origin, warnings, assessment
    monkeypatch.setattr(api, "prepare_pvs1_input", both_lof)
    result = api.automatic_classification(case["payload"])
    assert len(case["analyses"]) == 1 and len(result["automatic"]) == 2
    assert all(row["assessment"]["total_points"] == 8 for row in result["automatic"])


def test_reopening_and_expired_tickets_reuse_persisted_active_and_inactive_results(automatic):
    case = automatic
    first = api.automatic_classification(case["payload"])
    token = first["automatic"][0]["assessment"]["criteria"][0]["pvs1_evaluation_id"]
    pvs1_saved._pending.clear()  # A process restart or ticket expiry loses only the save tickets.
    case["analyses"].clear(); case["evaluations"].clear()
    repeated = api.automatic_classification(case["payload"])
    assert not case["analyses"] and not case["evaluations"]
    assert [item["assessment"]["classification"] for item in repeated["automatic"]] == ["LIKELY_PATHOGENIC", "NOT_EVALUATED"]
    refreshed = repeated["automatic"][0]["assessment"]["criteria"][0]["pvs1_evaluation_id"]
    assert refreshed != token
    assert pvs1_saved.pending(refreshed, case["run_dir"])["snapshot"]["result"]["applied_strength"] == "VERY_STRONG"


def test_real_annotation_change_invalidates_automatic_results(automatic):
    case = automatic
    api.automatic_classification(case["payload"])
    case["analyses"].clear(); case["evaluations"].clear()
    with sqlite3.connect(case["database"]) as db:
        db.execute("UPDATE annotations SET hgvsc='new annotation' WHERE id=7")
    api.automatic_classification(case["payload"])
    assert len(case["analyses"]) == 1 and len(case["evaluations"]) == 2


def test_population_cache_updates_do_not_repeat_pvs1(automatic):
    case = automatic
    api.automatic_classification(case["payload"])
    case["analyses"].clear(); case["evaluations"].clear()
    with sqlite3.connect(case["database"]) as db:
        db.execute("UPDATE variants SET metadata_json=? WHERE id=1", (json.dumps(dict(
            gnomad_enrichment=dict(retrieved_at="now", release="population release"))),))
    api.automatic_classification(case["payload"])
    assert not case["analyses"] and not case["evaluations"]


def test_real_reference_change_invalidates_automatic_results(automatic):
    case = automatic
    fasta = case["run_dir"] / "reference.fa"
    fasta.write_text(">1\nACGT\n")
    api._entry(case["payload"]["run_id"])["record"]["run_config"] = dict(reference_fasta=str(fasta), reference_version="test")
    api.automatic_classification(case["payload"])
    case["analyses"].clear(); case["evaluations"].clear()
    fasta.write_text(">1\nACGTACGT\n")
    api.automatic_classification(case["payload"])
    assert len(case["analyses"]) == 1 and len(case["evaluations"]) == 2


def test_parallel_requests_evaluate_the_same_allele_once(automatic, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    case = automatic
    entered, second_started, release = Event(), Event(), Event()
    original = api.prepare_pvs1_input
    def prepare(*args):
        entered.set()
        assert release.wait(3)
        return original(*args)
    monkeypatch.setattr(api, "prepare_pvs1_input", prepare)
    def second():
        second_started.set()
        return api.automatic_classification(case["payload"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(api.automatic_classification, case["payload"])
        assert entered.wait(3)
        other = pool.submit(second)
        assert second_started.wait(3)
        release.set()
        assert len(first.result()["automatic"]) == len(other.result()["automatic"]) == 2
    assert len(case["analyses"]) == 1 and len(case["evaluations"]) == 2


def test_run_preparation_exposes_automatic_classes_before_opening_details(automatic):
    from helper_next.api import variants
    case = automatic
    state, checkpoints = {}, []
    record = dict(id=case["payload"]["run_id"], run_dir=str(case["run_dir"]))
    automatic_saved.prepare_run(case["database"], record, api.automatic_classification, state,
                                lambda: checkpoints.append(copy.deepcopy(state)), lambda: False)
    assert state["status"] == "complete" and state["attempted"] == state["total"] == 1
    assert checkpoints[-1]["status"] == "complete"
    items = [dict(variant_id=1, reference_build="GRCh38", chromosome="chr1", position=1100, reference="C", alternate="T")]
    variants._attach_classification_summaries(dict(database=case["database"], record=record), 1, items)
    assert {row["classification"] for row in items[0]["acmg_classifications"]} == {"LIKELY_PATHOGENIC", "NOT_EVALUATED"}
    case["analyses"].clear(); case["evaluations"].clear()
    api.automatic_classification(case["payload"])
    assert not case["analyses"] and not case["evaluations"]
    with sqlite3.connect(case["database"]) as db:
        db.execute("UPDATE annotations SET hgvsc='modified' WHERE id=7")
    variants._attach_classification_summaries(dict(database=case["database"], record=record), 1, items)
    assert not items[0]["acmg_classifications"]


def test_background_preparation_reuses_entry_and_defers_save_tickets_until_browsing(automatic, monkeypatch):
    case = automatic
    entry = api._entry(case["payload"]["run_id"])
    with monkeypatch.context() as patch:
        patch.setattr(api, "_entry", lambda *a: pytest.fail("Run entry must be reused"))
        patch.setattr(pvs1_saved, "remember", lambda *a: pytest.fail("Background work must not allocate UI tickets"))
        result = api.prepare_automatic_classification(case["payload"], entry)
    assert result == {"automatic": []}
    assert not pvs1_saved._pending
    assert len(case["analyses"]) == 1 and len(case["evaluations"]) == 2
    case["analyses"].clear(); case["evaluations"].clear()
    response = api.automatic_classification(case["payload"])
    assert not case["analyses"] and not case["evaluations"]
    token = response["automatic"][0]["assessment"]["criteria"][0]["pvs1_evaluation_id"]
    assert pvs1_saved.pending(token, case["run_dir"])["snapshot"]["result"]["applied_strength"] == "VERY_STRONG"


@pytest.mark.parametrize("canonical,impact,release,expected", [(0, "HIGH", 1, 7), (1, "LOW", 1, 7),
    (1, "HIGH", 1, 7), (1, "HIGH", 2, 8)])
def test_main_matches_existing_variants_ordering(automatic, canonical, impact, release, expected):
    case = automatic
    with sqlite3.connect(case["database"]) as db:
        if release == 2:
            db.execute("INSERT INTO annotation_releases(id,release_key,annotator,reference_build,created_at) VALUES (2,'release2','synthetic','GRCh38','new')")
        db.execute("INSERT INTO annotations(id,variant_id,release_id,gene,transcript,consequence,impact,canonical,metadata_json) "
                   "SELECT 8,variant_id,?,gene,'TX.2',consequence,?,?,metadata_json FROM annotations WHERE id=7", (release, impact, canonical))
    case["detail"]["annotations"].append({**case["detail"]["annotations"][0], "id": 8, "transcript": "TX.2", "canonical": canonical, "impact": impact})
    result = api.automatic_classification(case["payload"])
    assert [row["annotation_id"] for row in result["mains"]] == [expected]
    assert {row[0] for row in case["analyses"]} == {expected}


def test_fresh_saved_user_worksheet_wins_and_avoids_recalculation(automatic):
    case = automatic
    result = api.automatic_classification(case["payload"])
    row = result["automatic"][0]
    selection = {**case["payload"], "context_id": row["context_id"], "interpretation_context": result["contexts"]["annotations"][0]["contexts"][0]["context"]}
    loaded = api.load_classification(selection)
    request = {**selection, "signature": loaded["signature"], "criteria": [dict(code="BS3", strength="STRONG")], "note": "User classification"}
    saved_row = api.save_classification(request)["saved"]
    case["analyses"].clear(); case["evaluations"].clear()
    updated = api.automatic_classification(case["payload"])
    assert not case["evaluations"]
    assert not case["analyses"]
    assert updated["items"][0]["classification"] == "LIKELY_BENIGN" and updated["items"][0]["revision"] == 1
    assert all(item["identity"]["disease"] != "MONDO:1" for item in updated["automatic"])
    assert api.load_classification(selection)["saved"] == saved_row


def test_automatic_provenance_is_verified_saved_and_reusable_after_ticket_expiry(automatic):
    case = automatic
    result = api.automatic_classification(case["payload"])
    row = result["automatic"][0]
    selection = {**case["payload"], "context_id": row["context_id"], "interpretation_context": result["contexts"]["annotations"][0]["contexts"][0]["context"]}
    loaded = api.load_classification(selection)
    request = {**selection, "signature": loaded["signature"], "criteria": row["assessment"]["criteria"]}
    altered = copy.deepcopy(request); altered["criteria"][0]["strength"] = "SUPPORTING"
    with pytest.raises(HTTPException): api.save_classification(altered)
    wrong = copy.deepcopy(request); wrong["interpretation_context"]["inheritance_modes"] = ["AUTOSOMAL_RECESSIVE"]
    wrong["signature"] = api.load_classification(wrong)["signature"]
    with pytest.raises(HTTPException): api.save_classification(wrong)
    saved_row = api.save_classification(request)["saved"]
    assert saved_row["assessment"]["automatic_pvs1"]["result"]["applied_strength"] == "VERY_STRONG"
    pvs1_saved._pending.clear()
    request["criteria"][0]["note"] = "User reviewed the automatic criterion"
    updated = api.save_classification({**request, "note": "accepted", "expected_revision": 1})["saved"]
    assert updated["revision"] == 2 and not api.load_classification(selection)["needs_review"]
    with sqlite3.connect(case["database"]) as db: db.execute("UPDATE annotations SET hgvsc='updated' WHERE id=7")
    refreshed = api.load_classification(selection)
    assert refreshed["needs_review"]
    with pytest.raises(HTTPException): api.save_classification({**request, "signature": refreshed["signature"], "expected_revision": 2})


@pytest.mark.parametrize("strength,points", [("MODERATE", 2), ("NONE", 0)])
def test_automatic_reuses_saved_pvs1_and_respects_manual_strength(automatic, monkeypatch, strength, points):
    case = automatic
    catalog = api.acmg_context.build(case["detail"])
    choice = catalog["annotations"][0]["contexts"][0]
    selection = {**case["payload"], "context_id": choice["id"], "interpretation_context": choice["context"]}
    run_dir, identity, signature = api._saved_selection(selection, choice=choice)
    sample = sample_fixture()
    result = api.calculate_pvs1(sample)
    result, override = api._strength_override(result, strength)
    snapshot = pvs1_saved.compact_snapshot(dict(input=asdict(sample), result=asdict(result), strength_override=override))
    pvs1_saved.save(run_dir, identity, signature, snapshot)
    monkeypatch.setattr(api, "analyze_transcripts", lambda *a, **k: pytest.fail("Saved PVS1 should be reused; other context is GoF"))
    automatic_result = api.automatic_classification(case["payload"])
    row = next(item for item in automatic_result["automatic"] if item["identity"]["disease"] == "MONDO:1")
    assert row["assessment"]["total_points"] == points
    assert row["pvs1"]["manual"]
    if points:
        assert row["assessment"]["criteria"][0]["origin"] == "PVS1_SAVED" and row["assessment"]["criteria"][0]["pvs1_revision"] == 1
    else:
        assert not row["assessment"]["criteria"] and row["assessment"]["classification"] == "NOT_EVALUATED"


def test_failed_reference_is_attempted_once_for_all_contexts(automatic, monkeypatch):
    case = automatic
    calls = []
    def fail(*a, **k):
        calls.append(1); raise ValueError("Reference unavailable")
    monkeypatch.setattr(api, "analyze_transcripts", fail)
    result = api.automatic_classification(case["payload"])
    assert len(calls) == 1
    assert result["automatic"][0]["error"] == "Reference unavailable" and result["automatic"][0]["assessment"]["requires_review"]
    assert result["automatic"][1]["pvs1"]["status"] == "INACTIVE"


def test_missense_without_splice_predictions_avoids_reference_analysis(automatic, monkeypatch):
    case = automatic
    case["detail"]["annotations"][0]["consequence"] = "missense_variant"
    monkeypatch.setattr(api, "analyze_transcripts", lambda *a, **k: pytest.fail("No product analysis for missense"))
    api.automatic_classification(case["payload"])


def test_missing_inheritance_stays_unknown_without_choosing_a_mode(automatic):
    case = automatic
    original = api.acmg_context.build
    def missing(value, **kwargs):
        catalog = original(value, **kwargs)
        for entry in catalog["annotations"]:
            for choice in entry["contexts"]: choice["context"]["inheritance_modes"] = []
        return catalog
    api.acmg_context.build = missing
    try: result = api.automatic_classification(case["payload"])
    finally: api.acmg_context.build = original
    assert not case["analyses"] and not case["evaluations"]
    assert all(not row["identity"]["inheritance"] and row["assessment"]["classification"] == "NOT_EVALUATED" for row in result["automatic"])


def test_criterion_pvs1_uses_and_saves_the_explicit_inheritance(automatic, monkeypatch):
    case = automatic
    build = api.acmg_context.build
    def multiple_modes(detail, **kwargs):
        catalog = build(detail, **kwargs)
        for entry in catalog["annotations"]:
            for choice in entry["contexts"]:
                choice["context"]["inheritance_modes"] = ["AUTOSOMAL_DOMINANT", "AUTOSOMAL_RECESSIVE"]
        return catalog
    monkeypatch.setattr(api.acmg_context, "build", multiple_modes)
    choice = multiple_modes(case["detail"])["annotations"][0]["contexts"][0]
    payload = {**case["payload"], "context_id": choice["id"], "inheritance": "AUTOSOMAL_RECESSIVE"}
    result = api.evaluate_pvs1(payload)
    assert case["evaluations"][-1]["inheritance_modes"] == ["AUTOSOMAL_RECESSIVE"]
    ticket = pvs1_saved.pending(result["evaluation_id"], case["run_dir"])
    assert ticket["identity"]["inheritance"] == ["AUTOSOMAL_RECESSIVE"]
    with pytest.raises(HTTPException): api.evaluate_pvs1({**payload, "inheritance": "X_LINKED"})
