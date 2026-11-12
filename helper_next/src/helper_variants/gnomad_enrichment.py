"""Explicit run enrichment using the existing frequency and run stores."""
import json
import sqlite3
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from helper_variants import gene_phenotype, gnomad_frequency, indexer, store


def prepare_sample(database, sample_id, *, after_variant_id=0, limit=50, record=None,
                   prepare_gene_context=False):
    return prepare_batch(database, sample_id=sample_id, after_variant_id=after_variant_id,
                         limit=limit, record=record, prepare_gene_context=prepare_gene_context)


def prepare_batch(database, *, sample_id=None, after_variant_id=0, limit=50, record=None,
                  prepare_gene_context=False):
    """Acquire required population evidence before scoring/display, in bounded batches.

    Each sequence-resolved sample allele is visited once per pass, independently
    of display filters. Unsupported REF/ALT alleles are excluded before batching.
    The provider reuses valid cached lookups and obtains missing regional coverage.
    No run database transaction is held during remote acquisition.
    """
    if not 1 <= limit <= 100 or after_variant_id < 0:
        raise ValueError('Invalid evidence batch limit or cursor')
    with store.connect(database) as connection:
        if sample_id is not None and not connection.execute('SELECT 1 FROM samples WHERE id=?', (sample_id,)).fetchone():
            raise ValueError('sample not found')
        membership = (' AND EXISTS (SELECT 1 FROM calls c JOIN analyses a ON a.id=c.analysis_id '
                      'WHERE c.variant_id=v.id AND a.sample_id=?)') if sample_id is not None else ''
        parameters = (after_variant_id, sample_id, limit + 1) if sample_id is not None else (after_variant_id, limit + 1)
        rows = connection.execute(
            'SELECT v.id,v.reference_build,v.chromosome,v.position,v.reference,v.alternate,v.metadata_json '
            'FROM variants v WHERE ' + store.SEQUENCE_VARIANT_FILTER + ' AND v.id>?'
            + membership + ' ORDER BY v.id LIMIT ?', parameters,
        ).fetchall()
    batch = rows[:limit]
    attached = [json.loads(row[6] or '{}') for row in batch]
    cached = gnomad_frequency.cached_variants([tuple(row)[1:6] for row in batch], metadata=attached, priority_only=True)
    ready = [gnomad_frequency._reusable(result, include_non_ukb=False)
             and not gnomad_frequency._needs_region_coverage(result) for result in cached]
    first_missing = next((i for i, available in enumerate(ready) if not available), None)
    if first_missing is not None:
        # Report the cached prefix immediately, without making it wait behind
        # remote timeouts. At a cache miss keep acquisition bounded to five.
        width = first_missing or 5
        batch, attached = batch[:width], attached[:width]
        cached, ready = cached[:width], ready[:width]
    shared_context = gene_phenotype.prepare_priority_contexts() if prepare_gene_context else None
    if shared_context and shared_context.get('refreshing'):
        raise ValueError('Gene-disease update is still running; retry sample loading after it completes')
    alleles = [tuple(row)[1:6] for row in batch]
    # Reconstruct source-bound identities locally, including projections already
    # in the shared cache. Only unresolved projections need the narrow pipeline.
    resolutions = gnomad_frequency.resolve_alleles(alleles, metadata=attached, fetch=False)
    pending = [i for i, available in enumerate(ready) if not available]
    pipeline = any(resolutions[i][0] is None for i in pending)
    acquired = gnomad_frequency.lookup_variants([alleles[i] for i in pending], record=record,
                    metadata=[attached[i] for i in pending], include_non_ukb=False,
                    batch_size=3 if pipeline else 24) if pending else []
    if len(acquired) != len(pending):
        raise ValueError('Population provider returned an incomplete batch; reopen the sample')
    results = [dict(value, identity_resolution=resolution) if available else None
               for value, available, (_, resolution) in zip(cached, ready, resolutions)]
    for i, value in zip(pending, acquired):
        results[i] = value
    outcomes = Counter()
    updated = 0
    with store.connect(database) as connection:
        for row, result, available in zip(batch, results, ready):
            outcome = result.get('retrieval_status', 'UNAVAILABLE')
            if result.get('partial') or result.get('region_coverage_pending'):
                outcome = 'UNAVAILABLE'
            if (result.get('region_coverage') or {}).get('status') == 'ERROR':
                outcome = 'UNAVAILABLE'
            outcomes[outcome] += 1
            # Preserve metadata written by other operations during acquisition.
            raw = connection.execute('SELECT metadata_json FROM variants WHERE id=?', (row[0],)).fetchone()
            if raw is None:
                raise ValueError('Variant index changed during evidence acquisition; reopen the sample')
            metadata = json.loads(raw[0] or '{}')
            resolution = result.get('identity_resolution') or {}
            target = resolution.get('target_identity') or {}
            key = (gnomad_frequency.cache_key(*gnomad_frequency._identity_allele(target['identity']))
                   if target.get('status') == 'RESOLVED' else None)
            binding = dict(
                retrieval_status=outcome, release=gnomad_frequency.FREQUENCY_RELEASE,
                cache_key=key, allele_ref=target.get('allele_ref'),
                error=result.get('error') or result.get('message') or None,
                attempted_at=datetime.now(timezone.utc).isoformat(), identity_resolution=resolution,
            )
            previous = metadata.get('gnomad_enrichment') or {}
            previous_resolution = previous.get('identity_resolution') or {}
            # A cache read is not a new acquisition. Preserve the original
            # provenance/timestamp and avoid invalidating detail/table caches.
            if (available and key and all(previous.get(k) == binding[k] for k in
                    ('retrieval_status', 'release', 'cache_key', 'allele_ref', 'error'))
                    and previous_resolution.get('original') == resolution.get('original')
                    and (previous_resolution.get('target_identity') or {}).get('identity') == target.get('identity')
                    and (previous_resolution.get('target_identity') or {}).get('status') == 'RESOLVED'):
                continue
            metadata['gnomad_enrichment'] = binding
            connection.execute('UPDATE variants SET metadata_json=? WHERE id=?', (json.dumps(metadata), row[0]))
            updated += 1
    result = dict(attempted=len(batch), outcomes=dict(outcomes),
                  cached=len(batch) - len(pending), acquired=len(pending), updated=updated,
                  next_after_variant_id=batch[-1][0] if len(rows) > len(batch) else None)
    if shared_context is not None:
        result['gene_context'] = {key: shared_context.get(key) for key in
                                 ('status', 'stale', 'preparation_error')}
    return result

_active = set()
_lock = threading.Lock()


def begin(database):
    key = str(Path(database).resolve())
    with _lock:
        if key in _active:
            return False
        _active.add(key)
        return True


def finish(database):
    with _lock:
        _active.discard(str(Path(database).resolve()))


def status(database):
    database = Path(database)
    with _lock:
        active = str(database.resolve()) in _active
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as connection:
        row = connection.execute('SELECT metadata_json FROM runs ORDER BY id LIMIT 1').fetchone()
    result = json.loads(row[0]).get('gnomad_enrichment', {}) if row else {}
    return dict(result, status='running' if active else result.get('status', 'not_started'))


def _summary(connection, result):
    rows = connection.execute('SELECT id,metadata_json FROM runs').fetchall()
    for run_id, raw in rows:
        data = json.loads(raw)
        data['gnomad_enrichment'] = result
        connection.execute('UPDATE runs SET metadata_json=? WHERE id=?', (json.dumps(data), run_id))
    connection.commit()


def enrich_run(record, *, database=None, batch_size=100, frequency_database=None):
    """Stream every unique run allele, sharing all samples; never blocks indexing.

    Only status, identity relation and cache key are retained in the run. Public
    frequency payloads live exclusively in the existing global frequency cache.
    """
    database = Path(database or indexer.index_path(record['run_dir']))
    counts = Counter()
    start = datetime.now(timezone.utc).isoformat()
    summary = dict(status='running', started_at=start, release=gnomad_frequency.FREQUENCY_RELEASE,
                   assembly='GRCh38', attempted=0, outcomes={})
    with sqlite3.connect(database) as connection:
        _summary(connection, summary)
        last_id = 0
        try:
            while True:
                rows = connection.execute('SELECT id,reference_build,chromosome,position,reference,alternate,metadata_json '
                                          'FROM variants WHERE id>? ORDER BY id LIMIT ?',
                                          (last_id, max(1, min(int(batch_size), 1000)))).fetchall()
                if not rows:
                    break
                results = gnomad_frequency.lookup_variants([row[1:6] for row in rows],
                            database=frequency_database, record=record,
                            metadata=[json.loads(row[6]) for row in rows])
                for row, result in zip(rows, results):
                    outcome = result['retrieval_status']
                    if result.get('partial'):
                        outcome = 'UNAVAILABLE'
                    counts[outcome] += 1
                    metadata = json.loads(row[6])
                    resolution = result.get('identity_resolution', {})
                    target = resolution.get('target_identity') or {}
                    key = None
                    if target.get('status') == 'RESOLVED':
                        key = gnomad_frequency.cache_key(*gnomad_frequency._identity_allele(target['identity']))
                    metadata['gnomad_enrichment'] = dict(retrieval_status=outcome, release=summary['release'],
                        cache_key=key, allele_ref=target.get('allele_ref'),
                        error=result.get('error') or result.get('message') or None,
                        attempted_at=datetime.now(timezone.utc).isoformat(), identity_resolution=resolution)
                    connection.execute('UPDATE variants SET metadata_json=? WHERE id=?', (json.dumps(metadata), row[0]))
                last_id = rows[-1][0]
                summary.update(attempted=sum(counts.values()), outcomes=dict(counts))
                _summary(connection, summary)
        except Exception as exc:
            summary.update(status='failed', error=str(exc))
        else:
            summary['status'] = 'partial' if counts['UNAVAILABLE'] or counts['ERROR'] else 'complete'
        summary.update(finished_at=datetime.now(timezone.utc).isoformat())
        _summary(connection, summary)
    return summary
