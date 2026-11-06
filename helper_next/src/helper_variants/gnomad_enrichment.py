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
    """Acquire required population evidence before scoring/display, in bounded batches.

    Each sequence-resolved sample allele is visited once per pass, independently
    of display filters. Unsupported REF/ALT alleles are excluded before batching.
    The provider reuses valid cached lookups and obtains missing regional coverage.
    No run database transaction is held during remote acquisition.
    """
    if not 1 <= limit <= 100 or after_variant_id < 0:
        raise ValueError('Invalid evidence batch limit or cursor')
    with store.connect(database) as connection:
        if not connection.execute('SELECT 1 FROM samples WHERE id=?', (sample_id,)).fetchone():
            raise ValueError('sample not found')
        rows = connection.execute(
            'SELECT v.id,v.reference_build,v.chromosome,v.position,v.reference,v.alternate,v.metadata_json '
            'FROM variants v WHERE ' + store.SEQUENCE_VARIANT_FILTER + ' AND v.id>? AND EXISTS ('
            'SELECT 1 FROM calls c JOIN analyses a ON a.id=c.analysis_id '
            'WHERE c.variant_id=v.id AND a.sample_id=?) ORDER BY v.id LIMIT ?',
            (after_variant_id, sample_id, limit + 1),
        ).fetchall()
    batch = rows[:limit]
    attached = [json.loads(row[6] or '{}') for row in batch]
    cached = gnomad_frequency.cached_variants([tuple(row)[1:6] for row in batch], metadata=attached, priority_only=True)
    needs_acquisition = any(not gnomad_frequency._reusable(result, include_non_ukb=False)
                            or gnomad_frequency._needs_region_coverage(result) for result in cached)
    if needs_acquisition:
        # Return progress after five remote lookups instead of waiting for fifty
        # sequential GRCh37 projections. Fully cached batches keep the large size.
        batch = batch[:5]
        attached = attached[:5]
    shared_context = gene_phenotype.prepare_priority_contexts() if prepare_gene_context else None
    if shared_context and shared_context.get('refreshing'):
        raise ValueError('Gene-disease update is still running; retry sample loading after it completes')
    # Start gnomAD after the first three resolved alleles while the remaining
    # projections continue. Fully resolved/cached samples retain wide batches.
    pipeline = needs_acquisition and any(
        str(row[1]).lower() in ('grch37', 'hg19', 'b37', '37', 'grch37hg19')
        and gnomad_frequency._supplied_target(tuple(row)[1:6], data) is None
        for row, data in zip(batch, attached))
    results = gnomad_frequency.lookup_variants([tuple(row)[1:6] for row in batch], record=record,
                    metadata=attached, include_non_ukb=False, batch_size=3 if pipeline else 24) if batch else []
    if len(results) != len(batch):
        raise ValueError('Population provider returned an incomplete batch; reopen the sample')
    outcomes = Counter()
    with store.connect(database) as connection:
        for row, result in zip(batch, results):
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
            metadata['gnomad_enrichment'] = dict(
                retrieval_status=outcome, release=gnomad_frequency.FREQUENCY_RELEASE,
                cache_key=key, allele_ref=target.get('allele_ref'),
                error=result.get('error') or result.get('message') or None,
                attempted_at=datetime.now(timezone.utc).isoformat(), identity_resolution=resolution,
            )
            connection.execute('UPDATE variants SET metadata_json=? WHERE id=?', (json.dumps(metadata), row[0]))
    result = dict(attempted=len(batch), outcomes=dict(outcomes),
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
