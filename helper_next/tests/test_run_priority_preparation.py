"""Run indexing owns population acquisition; sample opening only reads prepared data."""
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from helper_next.api import variants as api
from helper_variants import gene_phenotype, gnomad_enrichment, gnomad_frequency as g, query, run_evidence as jobs, store
from test_gnomad_frequency import provider
from test_variant_query import query_store
from test_variants_api import archived_run, CapturingBackgroundTasks


@pytest.fixture(autouse=True)
def local_gene_context(monkeypatch):
    jobs.resume()
    monkeypatch.setattr(gene_phenotype, 'prepare_priority_contexts', lambda: {'status': 'ready', 'stale': False})
    monkeypatch.delenv('HELPER_GNOMAD_OFFLINE', raising=False)


def test_run_visits_unique_alleles_of_all_samples_and_filters_unsupported(tmp_path, monkeypatch):
    database, first, second = query_store(tmp_path)
    with store.connect(database) as db:
        analysis = db.execute('SELECT id FROM analyses WHERE sample_id=?', (second,)).fetchone()[0]
        variant = store.get_or_create_variant(db, 'GRCh38', '1', 50, 'C', 'T')
        store.record_call(db, analysis, variant, 'GATK', '0/1')
        invalid = store.get_or_create_variant(db, 'GRCh38', '1', 51, 'A', '*')
        store.record_call(db, analysis, invalid, 'GATK', '0/1')
    calls = provider(monkeypatch)
    result = jobs.prepare_run(database)
    assert result['status'] == 'complete'
    assert result['attempted'] == result['total'] == 6
    assert result['outcomes'] == {'FOUND': 6}
    assert sum(len(variables) for _, variables in calls) == 6
    monkeypatch.setattr(g, '_request_graphql', lambda *a: pytest.fail('Sample opening must be local'))
    monkeypatch.setattr(gene_phenotype, 'prepare_priority_contexts', lambda: pytest.fail('Run already prepared'))
    monkeypatch.setattr(gnomad_enrichment, 'prepare_batch', lambda *a, **kw: pytest.fail('No repeated run pass'))
    assert jobs.prepare_run(database) == result
    assert len(query.list_variants(database, first, load_all=True)['items']) == 5
    assert len(query.list_variants(database, second, load_all=True)['items']) == 2


def test_checkpoint_resumes_after_interruption_without_refetching_completed_alleles(tmp_path, monkeypatch):
    database, sample, _ = query_store(tmp_path)
    with store.connect(database) as db:
        analysis = db.execute('SELECT id FROM analyses WHERE sample_id=?', (sample,)).fetchone()[0]
        for position in range(6, 9):
            variant = store.get_or_create_variant(db, 'GRCh38', '1', position, 'A', 'G')
            store.record_call(db, analysis, variant, 'GATK', '0/1')
    calls = provider(monkeypatch)
    original = gnomad_enrichment.prepare_batch
    def interrupt(*args, **kwargs):
        if kwargs['after_variant_id']:
            raise KeyboardInterrupt('simulate process interruption')
        return original(*args, **kwargs)
    monkeypatch.setattr(gnomad_enrichment, 'prepare_batch', interrupt)
    with pytest.raises(KeyboardInterrupt):
        jobs.prepare_run(database)
    state = jobs.status(database)
    assert state['status'] == 'interrupted'
    assert state['attempted'] == state['last_variant_id'] == 5
    with store.connect(database) as db:
        before = db.execute('SELECT metadata_json FROM variants WHERE id<=5 ORDER BY id').fetchall()
        before = [row[0] for row in before]
    monkeypatch.setattr(gnomad_enrichment, 'prepare_batch', original)
    complete = jobs.prepare_run(database)
    assert complete['status'] == 'complete' and complete['attempted'] == complete['total'] == 8
    assert complete['outcomes'] == {'FOUND': 8}
    assert sum(len(variables) for _, variables in calls) == 8
    with store.connect(database) as db:
        assert [row[0] for row in db.execute('SELECT metadata_json FROM variants WHERE id<=5 ORDER BY id')] == before


def test_process_lock_prevents_duplicate_jobs_and_releases_after_abandoned_queue(tmp_path):
    database, *_ = query_store(tmp_path)
    tasks = CapturingBackgroundTasks()
    queued = jobs.schedule(database, {}, tasks.add_task)
    try:
        assert queued['status'] == 'queued'
        second = CapturingBackgroundTasks()
        assert jobs.schedule(database, {}, second.add_task)['status'] == 'queued'
        assert second.task is None
        script = '''import sys
from helper_variants import run_evidence as jobs
def rejected(*args):
    raise AssertionError('Second process must not enqueue a duplicate job')
print(jobs.schedule(sys.argv[1], {}, rejected)['status'])
'''
        result = subprocess.run([sys.executable, '-c', script, str(database)], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == 'queued'
    finally:
        jobs._release(Path(database).resolve())
    assert jobs.status(database)['status'] == 'interrupted'


def test_failed_evidence_is_reported_and_explicit_retry_preserves_successes(tmp_path, monkeypatch):
    database, *_ = query_store(tmp_path)
    monkeypatch.setattr(g, '_request_graphql', lambda *a: (_ for _ in ()).throw(TimeoutError('source timeout')))
    partial = jobs.prepare_run(database)
    assert partial['status'] == 'partial' and partial['unavailable'] == 5
    assert partial['attempted'] == partial['total'] == 5
    assert jobs.prepare_run(database) == partial
    # Existing retry backoff is preserved; move acquisition timestamps into the past.
    with sqlite3.connect(g.cache_path()) as db:
        db.execute("UPDATE frequencies SET retrieved_at='2000-01-01T00:00:00+00:00'")
    calls = provider(monkeypatch)
    retry = jobs.prepare_run(database, force=True)
    assert retry['status'] == 'complete' and retry['unavailable'] == 0
    assert retry['outcomes'] == {'FOUND': 5} and len(calls) == 1


def test_preparation_invalidates_for_source_release_or_missing_cache(tmp_path, monkeypatch):
    database, *_ = query_store(tmp_path)
    provider(monkeypatch)
    assert jobs.prepare_run(database)['status'] == 'complete'
    with monkeypatch.context() as context:
        context.setattr(g, 'FREQUENCY_RELEASE', 'future-release')
        assert jobs.status(database)['status'] == 'stale'
    assert jobs.status(database)['status'] == 'complete'
    monkeypatch.setenv('HELPER_GNOMAD_FREQUENCY_CACHE', str(tmp_path / 'another-cache.sqlite3'))
    assert jobs.status(database)['status'] == 'stale'


def test_first_cache_creation_does_not_publish_active_job_as_stale(tmp_path, monkeypatch):
    database, *_ = query_store(tmp_path)
    queued = CapturingBackgroundTasks()
    jobs.schedule(database, {}, queued.add_task)
    try:
        provider(monkeypatch)
        g.lookup_variant('GRCh38', '1', 100, 'A', 'G', include_non_ukb=False)
        assert jobs.status(database)['status'] == 'queued'
        queued.task(*queued.args)
        assert jobs.status(database)['status'] == 'complete'
    finally:
        jobs._release(Path(database).resolve())


def test_indexing_prepares_run_automatically_and_readiness_checks_do_not_acquire(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, 'launch', lambda function, *args: function(*args))
    record = archived_run(tmp_path)
    calls = provider(monkeypatch)
    tasks = CapturingBackgroundTasks()
    api.start_variant_index(record['id'], tasks)
    tasks.task(*tasks.args)
    state = api.variant_index_status(record['id'])
    assert state['status'] == 'complete' and state['phase'] == 'ready'
    assert state['priority_preparation']['status'] == 'complete'
    assert state['priority_preparation']['attempted'] == 1 and len(calls) == 1
    assert state['priority_preparation']['acmg_preparation']['status'] == 'complete'
    assert state['priority_preparation']['acmg_preparation']['attempted'] == 1
    monkeypatch.setattr(g, '_request_graphql', lambda *a: pytest.fail('No acquisition on reopening'))
    monkeypatch.setattr(gene_phenotype, 'prepare_priority_contexts', lambda: pytest.fail('Already prepared'))
    assert api.run_priority_evidence_status(record['id'])['status'] == 'complete'
    repeat = CapturingBackgroundTasks()
    assert api.start_run_priority_evidence(record['id'], repeat)['status'] == 'complete'
    assert repeat.task is None


def test_polling_resumes_an_abandoned_preparation(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, 'launch', lambda function, *args: function(*args))
    database, *_ = query_store(tmp_path)
    monkeypatch.setattr(api, '_entry', lambda identifier: {'database': database, 'record': {}})
    tasks = CapturingBackgroundTasks()
    jobs.schedule(database, {}, tasks.add_task)
    jobs._release(Path(database).resolve())
    assert jobs.status(database)['status'] == 'interrupted'
    resumed = CapturingBackgroundTasks()
    assert api.run_priority_evidence_status('RUN', resumed)['status'] == 'queued'
    provider(monkeypatch)
    resumed.task(*resumed.args)
    assert jobs.status(database)['status'] == 'complete'


def test_http_index_pipeline_and_read_only_readiness_after_completion(tmp_path, monkeypatch):
    import asyncio
    import httpx
    from helper_next.api.app import create_app

    record = archived_run(tmp_path)
    calls = provider(monkeypatch)
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url='http://test') as client:
            base = '/api/variants/runs/' + record['id']
            indexed = await client.post(base + '/index')
            assert indexed.status_code == 202
            for _ in range(100):
                progress = (await client.get(base + '/index-status')).json()
                if progress['status'] == 'complete':
                    break
                await asyncio.sleep(.01)
            assert progress['status'] == 'complete' and progress['phase'] == 'ready'
            for _ in range(2):
                state = (await client.get(base + '/priority-evidence')).json()
                assert state['status'] == 'complete' and state['attempted'] == state['total'] == 1
            prepared = await client.post(base + '/priority-evidence')
            assert prepared.status_code == 202 and prepared.json()['status'] == 'complete'
    asyncio.run(exercise())
    assert len(calls) == 1


def test_shutdown_checkpoint_resumes_at_next_allele(tmp_path, monkeypatch):
    database, *_ = query_store(tmp_path)
    calls = provider(monkeypatch)
    original = gnomad_enrichment.prepare_batch
    cursors = []
    def small_batches(*args, **kwargs):
        cursors.append(kwargs['after_variant_id'])
        result = original(*args, **kwargs, limit=2)
        if len(cursors) == 1:
            jobs.stop()
        return result
    monkeypatch.setattr(gnomad_enrichment, 'prepare_batch', small_batches)
    try:
        stopped = jobs.prepare_run(database)
        assert stopped['status'] == 'interrupted'
        assert stopped['last_variant_id'] == stopped['attempted'] == 2
    finally:
        jobs.resume()
    ready = jobs.prepare_run(database)
    assert ready['status'] == 'complete' and ready['attempted'] == 5
    assert cursors == [0, 2, 4]
    assert sum(len(variables) for _, variables in calls) == 5


def test_startup_recovery_only_resumes_pending_unique_runs(tmp_path, monkeypatch):
    record = archived_run(tmp_path)
    database = Path(api.variant_indexer.index_run(record)['database'])
    queued = CapturingBackgroundTasks()
    jobs.schedule(database, record, queued.add_task)
    jobs._release(database.resolve())
    recovered = CapturingBackgroundTasks()
    monkeypatch.setattr(jobs, 'launch', recovered.add_task)
    monkeypatch.setattr(api.history, 'list_runs', lambda: [record, dict(record, id='retry-same-run')])
    monkeypatch.setattr(api.external_vcf, 'list_sources', lambda: [])
    api.recover_run_priority_preparations()
    assert recovered.task is not None and jobs.status(database)['status'] == 'queued'
    calls = provider(monkeypatch)
    recovered.task(*recovered.args)
    assert jobs.status(database)['status'] == 'complete' and len(calls) == 1
    recovered.task = None
    api.recover_run_priority_preparations()
    assert recovered.task is None, 'Completed runs are not acquired again at startup'


def test_http_queue_returns_and_status_is_readable_while_remote_source_is_blocked(tmp_path, monkeypatch):
    import asyncio
    import threading
    import httpx
    from helper_next.api.app import create_app

    record = archived_run(tmp_path)
    api.variant_indexer.index_run(record)
    provider(monkeypatch)
    original = g._request_graphql
    entered, release = threading.Event(), threading.Event()
    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)
    monkeypatch.setattr(g, '_request_graphql', slow)
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url='http://test') as client:
            base = '/api/variants/runs/' + record['id'] + '/priority-evidence'
            request = asyncio.create_task(client.post(base))
            try:
                for _ in range(100):
                    if request.done() and entered.is_set():
                        break
                    await asyncio.sleep(.01)
                assert request.done(), 'Enqueue HTTP response cannot wait for remote acquisition'
                assert (await request).status_code == 202
                assert entered.is_set()
                state = (await client.get(base)).json()
                assert state['status'] == 'running' and state['attempted'] == 0
            finally:
                release.set()
            for _ in range(100):
                state = (await client.get(base)).json()
                if state['status'] == 'complete':
                    break
                await asyncio.sleep(.01)
            assert state['status'] == 'complete'
    asyncio.run(exercise())


def test_application_lifecycle_recovers_jobs_and_requests_cooperative_stop(monkeypatch):
    import asyncio
    import threading
    from helper_next.api import app as app_module

    recovered = threading.Event()
    monkeypatch.setattr(app_module, 'recover_run_priority_preparations', recovered.set)
    async def checks():
        await asyncio.Future()
    monkeypatch.setattr(app_module, 'periodic_checks', checks)
    app = app_module.create_app()
    async def exercise():
        jobs.stop()
        await app.router.startup()
        assert not jobs._stopping.is_set()
        for _ in range(50):
            if recovered.is_set():
                break
            await asyncio.sleep(.01)
        assert recovered.is_set()
        await app.router.shutdown()
        assert jobs._stopping.is_set()
    try:
        asyncio.run(exercise())
    finally:
        jobs.resume()
