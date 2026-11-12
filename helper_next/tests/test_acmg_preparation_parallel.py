"""Bounded ACMG concurrency, durable bulk writes and ordered resume cursors."""
import copy
import io
from concurrent.futures import ThreadPoolExecutor
import sqlite3
from threading import Barrier, Event, Lock

import pytest

from helper_next.core import acmg_automatic_store as cache
from helper_next.core.acmg_cache_writer import CacheWriteError, CacheWriter, use_writer, write_batch
from helper_variants import store
from helper_variants import gene_phenotype
from helper_next.core import acmg_context
from test_gene_phenotype import HEADER
from test_variant_query import query_store


def identity(sample, variant, disease="MONDO:1"):
    return dict(sample=str(sample), assembly="GRCh38", chromosome="1", position=variant,
                reference="A", alternate="G", gene="HGNC:1", disease=disease,
                transcript="TX.1", inheritance=["AUTOSOMAL_DOMINANT"])


def result(context):
    return dict(identity=context, automatic=True, assessment=dict(classification="LIKELY_PATHOGENIC",
        total_points=8, requires_review=False, criteria=[dict(code="PVS1", strength="VERY_STRONG",
        origin="PVS1_AUTO", pvs1_evaluation_id="a" * 32)]))


def pairs(database):
    with store.connect(database) as db:
        return [tuple(row) for row in db.execute("SELECT DISTINCT a.sample_id,c.variant_id FROM calls c "
            "JOIN analyses a ON a.id=c.analysis_id ORDER BY a.sample_id,c.variant_id")]


def assert_ordered(checkpoints, expected):
    for checkpoint in checkpoints:
        count = checkpoint["attempted"]
        if count:
            assert (checkpoint["after_sample"], checkpoint["after_variant"]) == expected[count - 1]


def test_parallel_preparation_is_bounded_and_checkpoints_contiguous(tmp_path):
    database, *_ = query_store(tmp_path)
    expected = pairs(database)
    active = peak = 0
    calls, checkpoints = [], []
    guard, first_workers = Lock(), Barrier(2)
    def evaluate(payload):
        nonlocal active, peak
        pair = (payload["sample_id"], payload["variant_id"])
        with guard:
            calls.append(pair)
            active += 1
            peak = max(active, peak)
            early = len(calls) <= 2
        if early:
            first_workers.wait(timeout=3)
        with guard:
            active -= 1
        return {"automatic": []}
    state = {}
    cache.prepare_run(database, dict(id="RUN", run_dir=tmp_path), evaluate, state,
        lambda: checkpoints.append(copy.deepcopy(state)), lambda: False, workers=2)
    assert peak == state["workers"] == 2
    assert sorted(calls) == expected
    assert state["status"] == "complete" and state["attempted"] == state["total"] == len(expected)
    assert_ordered(checkpoints, expected)


def test_writer_batches_contexts_and_acknowledges_only_committed_results(tmp_path):
    barrier = Barrier(4)
    def evaluate(number, writer):
        with use_writer(writer), write_batch(tmp_path):
            for disease in ("MONDO:1", "MONDO:2"):
                context = identity(1, number, disease)
                cache.save(tmp_path, context, "signature", result(context), None, "source", "inputs")
            barrier.wait(timeout=3)
        # No acknowledgement can precede the actual SQLite commit.
        assert cache.load(tmp_path, identity(1, number), "signature") is not None
    with CacheWriter(tmp_path, coalesce_seconds=.02) as writer:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(evaluate, number, writer) for number in range(1, 5)]
            for future in futures:
                future.result(timeout=5)
    assert 1 <= writer.commits <= 4  # Eight contexts need at most one commit per allele.
    with sqlite3.connect(cache.pvs1.path(tmp_path)) as db:
        assert db.execute("SELECT COUNT(*) FROM automatic_classifications").fetchone()[0] == 8
    stored, _ = cache.load(tmp_path, identity(1, 1), "signature")
    assert "pvs1_evaluation_id" not in stored["assessment"]["criteria"][0]


def test_writer_failure_reaches_all_waiters_without_partial_commits(tmp_path):
    with CacheWriter(tmp_path, coalesce_seconds=.02) as writer:
        with sqlite3.connect(writer.filename) as db:
            db.execute("CREATE TRIGGER reject_cache BEFORE INSERT ON automatic_classifications "
                       "BEGIN SELECT RAISE(ABORT,'simulated write failure'); END")
        def fail(number):
            context = identity(1, number)
            with use_writer(writer):
                cache.save(tmp_path, context, "signature", result(context), None, "source", "inputs")
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(fail, number) for number in (1, 2)]
            for future in futures:
                with pytest.raises(CacheWriteError, match="simulated write failure"):
                    future.result(timeout=5)
    assert writer.error is not None
    assert cache.load(tmp_path, identity(1, 1), "signature") is None
    assert cache.load(tmp_path, identity(1, 2), "signature") is None


def test_stop_and_resume_reuses_results_completed_out_of_order(tmp_path):
    database, *_ = query_store(tmp_path)
    expected = pairs(database)
    entered, fast_done, release, stop = Event(), Event(), Event(), Event()
    computed, checkpoints = [], []
    guard = Lock()
    def evaluate(payload):
        pair = (payload["sample_id"], payload["variant_id"])
        context = identity(*pair)
        if cache.load(tmp_path, context, "signature"):
            return {"automatic": []}
        if pair == expected[0] and not release.is_set():
            entered.set()
            assert release.wait(3)
        cache.save(tmp_path, context, "signature", result(context), None, "source", "inputs")
        with guard:
            computed.append(pair)
        if pair == expected[1]:
            fast_done.set()
        return {"automatic": []}
    state = {}
    def run():
        cache.prepare_run(database, dict(id="RUN", run_dir=tmp_path), evaluate, state,
            lambda: checkpoints.append(copy.deepcopy(state)), stop.is_set, workers=2)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run)
        try:
            assert entered.wait(3) and fast_done.wait(3)
            stop.set()
        finally:
            release.set()
        future.result(timeout=5)
    assert state["status"] == "interrupted"
    stop.clear()
    run()
    assert state["status"] == "complete" and state["attempted"] == state["total"] == len(expected)
    assert sorted(computed) == expected
    assert_ordered(checkpoints, expected)


def test_worker_configuration_is_capped_and_invalid_values_rejected(monkeypatch):
    monkeypatch.setenv("HELPER_ACMG_WORKERS", "8")
    assert cache._worker_count(2, None) == 2
    for value in ("0", "17", "bad"):
        monkeypatch.setenv("HELPER_ACMG_WORKERS", value)
        with pytest.raises(ValueError):
            cache._worker_count(100, None)


def test_gene_facts_are_shared_without_changing_contexts_and_refresh_on_update(tmp_path, monkeypatch):
    database = tmp_path / "genes.sqlite3"
    gene_phenotype.build_cache(io.StringIO(HEADER +
        'SGC-1,1,HGNC:1,GENE1,MONDO:1,Disease one,,,Definitive,,Autosomal dominant,ClinGen,,,,,\n'), database)
    monkeypatch.setattr(gene_phenotype, "cache_path", lambda: database)
    detail = {"annotations": [dict(id=1, gene="GENE1", transcript="TX.1", metadata={})]}
    expected = acmg_context.build(detail)
    original = gene_phenotype.query_gene
    calls = []
    def query(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr(gene_phenotype, "query_gene", query)
    with ThreadPoolExecutor(max_workers=4) as pool:
        contexts = list(pool.map(lambda _: acmg_context.build(detail, lookup_gene=cache.gene_knowledge), range(12)))
    assert contexts == [expected] * 12
    assert len(calls) == 1
    revision = cache.gene_revision("GENE1")
    assert len(calls) == 1  # The source signature shares the same facts.
    facts = cache.gene_knowledge("GENE1")
    facts["associations"].clear()
    facts["cache"]["status"] = "invalid"
    monkeypatch.setattr(gene_phenotype, "is_refreshing", lambda: True)
    fresh = cache.gene_knowledge("GENE1")
    assert len(fresh["associations"]) == 1
    assert fresh["cache"]["status"] == "ready" and fresh["cache"]["refreshing"] is True
    with sqlite3.connect(database) as db:
        db.execute("UPDATE assertions SET disease_title='Changed disease'")
    assert cache.gene_revision("GENE1") != revision
    updated = acmg_context.build(detail, lookup_gene=cache.gene_knowledge)
    assert updated == acmg_context.build(detail)
    assert updated["annotations"][0]["contexts"][0]["context"]["disease"]["label"] == "Changed disease"
    assert len(calls) == 3  # Cached refresh + the uncached equivalence check.


def test_missing_gene_cache_remains_explicit_with_shared_lookup(tmp_path, monkeypatch):
    monkeypatch.setattr(gene_phenotype, "cache_path", lambda: tmp_path / "missing.sqlite3")
    detail = {"annotations": [dict(id=1, gene="GENE1", transcript="TX.1")]}
    assert acmg_context.build(detail, lookup_gene=cache.gene_knowledge) == acmg_context.build(detail)
