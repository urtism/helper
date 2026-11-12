"""Stable ACMG input digests and lossless compact sample tables."""
import asyncio
import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
from threading import Barrier

from fastapi import FastAPI
import httpx
import pytest

from helper_next.api import variants as api
from helper_next.core import acmg_automatic_store as automatic
from helper_next.core import acmg_input_revision_cache as cache
from helper_variants.table_transport import compact_table
from test_sample_priority_loading import run_loading_js
from test_variant_detail_optimization import local_entry
from test_variant_query import query_store


@pytest.fixture(autouse=True)
def isolate_revision_cache():
    cache._cache.cache_clear()
    yield
    cache._cache.cache_clear()


def test_input_digests_are_reused_for_overlapping_samples_and_after_restart(tmp_path):
    database, *_ = query_store(tmp_path)
    calls = []
    def calculate(database, ids):
        calls.append(ids)
        return automatic._calculate_input_revisions(database, ids)
    expected = automatic._calculate_input_revisions(database, [1, 2, 3])
    assert cache.revisions(database, [1, 2], calculate) == {key: expected[key] for key in (1, 2)}
    assert cache.revisions(database, [2, 3], calculate) == {key: expected[key] for key in (2, 3)}
    assert calls == [[1, 2], [3]]
    cache._cache.cache_clear()  # Simulate a new server process.
    assert cache.revisions(database, [1, 2, 3], calculate) == expected
    assert calls == [[1, 2], [3]]


def test_input_receipts_invalidate_for_in_place_wal_edits(tmp_path):
    database, *_ = query_store(tmp_path)
    with sqlite3.connect(database) as writer:
        writer.execute('PRAGMA journal_mode=WAL')
        before = automatic.input_revisions(database, [1, 2])
        cache._cache.cache_clear()
        writer.execute("UPDATE annotations SET hgvsc='changed' WHERE variant_id=1")
        writer.commit()
        after = automatic.input_revisions(database, [1, 2])
        assert after == automatic._calculate_input_revisions(database, [1, 2])
        assert before[1] != after[1] and before[2] == after[2]


def test_concurrent_sample_requests_share_one_input_hash_pass(tmp_path):
    database, *_ = query_store(tmp_path)
    start, calls = Barrier(4), []
    def calculate(database, ids):
        calls.append(ids)
        return automatic._calculate_input_revisions(database, ids)
    def read(_):
        start.wait(timeout=5)
        return cache.revisions(database, [1, 2], calculate)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(read, range(4)))
    assert results == [results[0]] * 4 and calls == [[1, 2]]


def test_index_edit_during_hashing_cannot_publish_old_digests(tmp_path):
    database, *_ = query_store(tmp_path)
    calls = []
    def calculate(database, ids):
        result = automatic._calculate_input_revisions(database, ids)
        calls.append(ids)
        if len(calls) == 1:
            with sqlite3.connect(database) as db:
                db.execute("UPDATE annotations SET hgvsc='edited while reading' WHERE variant_id=1")
        return result
    result = cache.revisions(database, [1, 2], calculate)
    assert result == automatic._calculate_input_revisions(database, [1, 2])
    assert calls == [[1, 2], [1, 2]]


def test_corrupt_or_unwritable_optional_receipts_do_not_block_loading(tmp_path, monkeypatch):
    database, *_ = query_store(tmp_path)
    path = Path(str(database.resolve()) + '.acmg-inputs.json')
    path.write_text('broken cache')
    def denied(*args, **kwargs):
        raise PermissionError('read-only run')
    monkeypatch.setattr(cache.tempfile, 'NamedTemporaryFile', denied)
    assert automatic.input_revisions(database, [1, 2]) == automatic._calculate_input_revisions(database, [1, 2])


def test_compact_table_roundtrips_in_browser_without_shared_mutable_filters():
    annotation = dict(gene='GENE', consequence='stop_gained', compound=True, parental_compound=False,
                      population_frequencies={'MAX_AF': .001, 'gnomAD_AF': '.001'})
    provenance = dict(source='ClinVar Local', snapshot='fixed', source_url='https://example.test/' + 'x' * 2000)
    full = dict(items=[dict(variant_id=variant, priority={'normalized_score': variant},
        filter_data=dict(annotations=[copy.deepcopy(annotation) for _ in range(40)], family_carriers=[1, 2]),
        clinvar_evidence=dict(provenance=copy.deepcopy(provenance), classifications=['Pathogenic']),
        acmg_classifications=[dict(classification='LIKELY_PATHOGENIC', inheritance=['AD'])]) for variant in (1, 2)],
        next_cursor=None, clinvar_snapshot_id='fixed')
    before = copy.deepcopy(full)
    wire = compact_table(full)
    assert full == before and len(wire['shared']) == 2
    assert len(json.dumps(wire)) < len(json.dumps(full)) / 4
    run_loading_js('const expected=' + json.dumps(full) + '; const wire=' + json.dumps(wire) + r''';
      const restored=viewer.expandVariantTable(wire);
      assert.deepEqual(restored,expected);
      assert.strictEqual(viewer.expandVariantTable(expected),expected);
      restored.items[0].filter_data.annotations[0].population_frequencies.MAX_AF=1;
      assert.equal(restored.items[1].filter_data.annotations[0].population_frequencies.MAX_AF,.001);
      wire.table.items[0].filter_data.annotations[0]=999;
      assert.throws(()=>viewer.expandVariantTable(wire),/Invalid compact variant table/);
    ''')


def test_http_compact_table_is_opt_in_and_preserves_full_sample_data(tmp_path, monkeypatch):
    _, sample, *_ = local_entry(tmp_path, monkeypatch)
    app = FastAPI()
    app.include_router(api.router)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
            path = f'/api/variants/runs/RUN/samples/{sample}/variants?load_all=true'
            full = await client.get(path)
            compact = await client.get(path + '&compact=true')
            assert full.status_code == compact.status_code == 200
            assert 'format' not in full.json()
            run_loading_js('const full=' + json.dumps(full.json()) + '; const wire=' + json.dumps(compact.json()) +
                           '; assert.deepEqual(viewer.expandVariantTable(wire),full);')
    asyncio.run(check())
