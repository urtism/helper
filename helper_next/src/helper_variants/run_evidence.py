"""Run-level Priority preparation with disk checkpoints and process-safe ownership."""
from collections import Counter
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import threading

from helper_variants import gene_phenotype, gnomad_enrichment, gnomad_frequency, store


FIELD = 'priority_preparation'
_owners = {}
_guard = threading.Lock()
_stopping = threading.Event()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _lock_path(database):
    return Path(str(database) + '.priority.lock')


def _busy(database):
    with _guard:
        if str(database) in _owners:
            return True
    path = _lock_path(database)
    if not path.is_file():
        return False
    with path.open('rb') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle, fcntl.LOCK_UN)
    return False


def _signature(database):
    """Qualify existing source digests; never scan VCFs or FASTAs for checksums."""
    with store.connect(database) as db:
        sources = [list(row) for row in db.execute(
            'SELECT relative_path,sha256,status FROM index_sources ORDER BY id')]
        maximum = db.execute('SELECT COALESCE(MAX(id),0) FROM variants').fetchone()[0]
    cache = gnomad_frequency.cache_path().resolve()
    try:
        stat = cache.stat()
        identity = [stat.st_dev, stat.st_ino]
    except FileNotFoundError:
        identity = None
    return dict(version=2, sources=sources, maximum_variant_id=maximum,
                release=gnomad_frequency.FREQUENCY_RELEASE, parser=gnomad_frequency.PARSER_VERSION,
                coverage_policy=[gnomad_frequency.REGION_COVERAGE_POLICY,
                                 gnomad_frequency.REGION_COVERAGE_FLANK,
                                 gnomad_frequency.REGION_COVERAGE_MAX_SPAN,
                                 gnomad_frequency.MIN_MEAN_COVERAGE, gnomad_frequency.MIN_OVER_20],
                cache_path=str(cache), cache_identity=identity)


def _read(database):
    with store.connect(database) as db:
        row = db.execute('SELECT metadata_json FROM runs ORDER BY id LIMIT 1').fetchone()
    return (json.loads(row[0] or '{}').get(FIELD) or {}) if row else {}


def _save(database, state):
    with store.connect(database) as db:
        for row in db.execute('SELECT id,metadata_json FROM runs').fetchall():
            metadata = json.loads(row[1] or '{}')
            metadata[FIELD] = state
            db.execute('UPDATE runs SET metadata_json=? WHERE id=?', (json.dumps(metadata), row[0]))


def status(database):
    database = Path(database).resolve()
    state = _read(database)
    if not state:
        return dict(status='not_started', attempted=0, total=0, outcomes={})
    if state.get('status') in ('queued', 'running') and _busy(database):
        # A first cold batch creates the shared cache before its checkpoint.
        # The owning worker validates/adopts that identity before publishing.
        return state
    if state.get('signature') != _signature(database):
        return dict(state, status='stale')
    if state.get('status') in ('queued', 'running'):
        return dict(state, status='interrupted')
    return state


def schedule(database, record, submit, *, force=False):
    """Claim before enqueueing; submit may run inline or register a background task."""
    database = Path(database).resolve()
    key = str(database)
    with _guard:
        if key in _owners:
            return _read(database)
        handle = _lock_path(database).open('a+b')
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return _read(database)
        _owners[key] = handle
    try:
        signature = _signature(database)
        previous = _read(database)
        same = previous.get('signature') == signature
        if same and previous.get('status') in ('complete', 'partial') and not force:
            _release(database)
            return previous
        resume = same and previous.get('status') in ('queued', 'running', 'interrupted', 'failed') and not force
        with store.connect(database) as db:
            total = db.execute('SELECT COUNT(*) FROM variants v WHERE ' + store.SEQUENCE_VARIANT_FILTER).fetchone()[0]
        state = (dict(previous) if resume else
                 dict(attempted=0, last_variant_id=0, outcomes={}, started_at=_now()))
        state.update(status='queued', signature=signature, total=total, updated_at=_now())
        state.pop('error', None)
        state.pop('finished_at', None)
        _save(database, state)
        submit(_run, database, record, state)
        return _read(database)
    except BaseException:
        _release(database)
        raise


def _release(database):
    with _guard:
        handle = _owners.pop(str(database), None)
    if handle is not None:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def prepare_run(database, record=None, *, force=False):
    return schedule(database, record or {}, lambda function, *args: function(*args), force=force)


def launch(function, *args):
    """Detach long acquisition from the HTTP task; checkpoints own its lifetime."""
    worker = threading.Thread(target=function, args=args, daemon=True, name='run-priority-preparation')
    try:
        worker.start()
    except BaseException:
        _release(args[0])
        raise


def stop():
    _stopping.set()


def resume():
    _stopping.clear()


def recover(database, record):
    if _stopping.is_set():
        return
    if _read(database).get('status') in ('queued', 'running', 'interrupted'):
        return schedule(database, record, launch)


def _run(database, record, state):
    try:
        if _stopping.is_set():
            state['status'] = 'interrupted'
            return
        state.update(status='running', updated_at=_now())
        _save(database, state)
        context = gene_phenotype.prepare_priority_contexts()
        if context.get('refreshing'):
            raise ValueError('Gene-disease update is still running')
        state['gene_context'] = {k: context.get(k) for k in ('status', 'stale', 'preparation_error')}
        counts = Counter(state.get('outcomes') or {})
        after = state.get('last_variant_id', 0)
        while True:
            if _stopping.is_set():
                state['status'] = 'interrupted'
                return
            batch = gnomad_enrichment.prepare_batch(database, after_variant_id=after, record=record)
            counts.update(batch['outcomes'])
            state.update(attempted=state['attempted'] + batch['attempted'], outcomes=dict(counts),
                         updated_at=_now())
            if batch['next_after_variant_id'] is not None:
                state['last_variant_id'] = batch['next_after_variant_id']
            else:
                state['last_variant_id'] = state['signature']['maximum_variant_id']
            current = _signature(database)
            # The first cold batch may create the shared cache. Replacement of
            # an existing cache or an index/source change invalidates this pass.
            expected = dict(state['signature'])
            if expected['cache_identity'] is None:
                expected['cache_identity'] = current['cache_identity']
            if expected != current:
                raise ValueError('Evidence sources changed during preparation; prepare the run again')
            state['signature'] = current
            _save(database, state)
            if batch['next_after_variant_id'] is None:
                break
            after = batch['next_after_variant_id']
        if record.get('id') and record.get('run_dir'):
            from helper_next.core import acmg_automatic_store
            from helper_next.api.acmg_calculator import prepare_automatic_classification
            state['phase'] = 'ACMG'
            acmg_state = state.setdefault('acmg_preparation', {})
            entry = dict(database=database, record=record)
            acmg_automatic_store.prepare_run(database, record, lambda payload: prepare_automatic_classification(payload, entry), acmg_state,
                lambda: _save(database, state), _stopping.is_set)
            if _stopping.is_set():
                state['status'] = 'interrupted'
                return
        incomplete = sum(n for outcome, n in counts.items() if outcome not in ('FOUND', 'NOT_FOUND'))
        state['status'] = 'partial' if incomplete or context.get('status') != 'ready' else 'complete'
        if state.get('acmg_preparation', {}).get('errors'):
            state['status'] = 'partial'
        state['unavailable'] = incomplete
    except Exception as exc:
        state.update(status='failed', error=str(exc))
    finally:
        try:
            state.update(updated_at=_now(), finished_at=_now())
            _save(database, state)
        finally:
            _release(database)
