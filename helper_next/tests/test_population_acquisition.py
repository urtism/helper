"""Bounded acquisition, shared work and source-bound secondary projections."""
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
import threading

import pytest

from helper_variants.acquisition import SingleFlight, frequency_flights, projection_flights
from helper_variants import acquisition, gnomad_frequency as g, liftover
from helper_prioritization import RULESET_VERSION, score_variant
from test_gnomad_frequency import ALLELE, provider, response_for


def test_single_flight_shares_active_work_releases_memory_and_isolates_results(monkeypatch):
    flight = SingleFlight()
    entered, release, waiting = threading.Event(), threading.Event(), threading.Event()
    class TrackedFuture(Future):
        def result(self, *args, **kwargs):
            waiting.set()
            return super().result(*args, **kwargs)
        def set_result(self, value):
            assert 'allele' not in flight._active
            return super().set_result(value)
    monkeypatch.setattr(acquisition, 'Future', TrackedFuture)
    def acquire(keys):
        entered.set()
        assert release.wait(3)
        return {'allele': {'values': [1]}}
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(flight.batch, ['allele'], acquire)
        assert entered.wait(3)
        second = pool.submit(flight.batch, ['allele'], acquire)
        assert waiting.wait(3)
        release.set()
        a, b = first.result(3), second.result(3)
    a['allele']['values'].append(2)
    assert b['allele']['values'] == [1]
    assert not flight._active


def test_single_flight_failure_does_not_leave_a_blocked_entry():
    flight = SingleFlight()
    with pytest.raises(ValueError, match='incomplete'):
        flight.batch(['a', 'b'], lambda keys: {'a': 1})
    assert not flight._active
    assert flight.run('a', lambda: 42) == 42


def test_priority_omits_non_ukb_and_detail_upgrades_without_priority_change(monkeypatch):
    calls = provider(monkeypatch)
    main = g.lookup_variant(*ALLELE, include_non_ukb=False)
    assert len(calls) == 1 and 'v0_non_ukb:' not in calls[0][0]
    assert main['non_ukb_pending'] and not main['subsets']
    assert g.lookup_variant(*ALLELE, include_non_ukb=False)['cache'] == 'hit'
    assert len(calls) == 1
    full = g.lookup_variant(*ALLELE)
    assert len(calls) == 2 and 'v0_non_ukb:' in calls[1][0]
    assert not full['non_ukb_pending']
    assert full['datasets'] == main['datasets']
    assert not full['priority_evidence_changed']
    assert not frequency_flights._active


def test_priority_reads_only_main_evidence_without_changing_scores_or_detail_cache(monkeypatch):
    provider(monkeypatch)
    full = g.lookup_variant(*ALLELE)
    expected = score_variant(g.priority_context(full, scoring_version=RULESET_VERSION))
    compact = g.cached_contexts([ALLELE], scoring_version=RULESET_VERSION)[0]
    evidence = compact['population_frequency_evidence']
    assert 'subsets' not in evidence and 'populations' not in evidence
    assert evidence['datasets'] == full['datasets']
    assert score_variant(compact) == expected
    assert g.cached_variant(*ALLELE)['subsets'] == full['subsets']


@pytest.mark.parametrize('detail', [False, True])
def test_concurrent_frequency_calls_share_main_acquisition_and_upgrade_optional_subset(monkeypatch, detail):
    entered, release, waiting = threading.Event(), threading.Event(), threading.Event()
    class TrackedFuture(Future):
        def result(self, *args, **kwargs):
            waiting.set()
            return super().result(*args, **kwargs)
    monkeypatch.setattr(acquisition, 'Future', TrackedFuture)
    calls = []
    def fetch(query, variables, timeout):
        calls.append(query)
        if len(calls) == 1:
            entered.set()
            assert release.wait(3)
        return response_for(variables)
    monkeypatch.setattr(g, '_request_graphql', fetch)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(g.lookup_variant, *ALLELE, include_non_ukb=False)
        assert entered.wait(3)
        second = pool.submit(g.lookup_variant, *ALLELE, include_non_ukb=detail)
        assert waiting.wait(3)
        release.set()
        a, b = first.result(3), second.result(3)
    assert len(calls) == (2 if detail else 1)
    assert a['datasets'] == b['datasets']
    assert b['non_ukb_pending'] == (not detail)
    assert not frequency_flights._active


def metadata_for(source, target):
    return {'original_vcf': dict(chromosome=source[1], position=source[2],
        reference=source[3], alternate=source[4], alternates=[source[4]], alt_index=1,
        info={'HG38': ':'.join(map(str, target[1:]))})}


def test_complete_secondary_projection_bypasses_ncbi_and_is_used_by_cached_priority(monkeypatch):
    calls = provider(monkeypatch)
    source = ('GRCh37', '1', 55000000, 'G', 'T')
    metadata = metadata_for(source, ALLELE)
    monkeypatch.setattr(liftover, 'project_variant', lambda *a, **k: pytest.fail('Secondary projection exists'))
    result = g.lookup_variant(*source, metadata=metadata, include_non_ukb=False)
    assert calls[0][1]['id0'] == '1-55039974-G-T'
    assert result['identity_resolution']['target_identity']['reference_provenance']['normalization'] == 'SUPPLIED_ASSEMBLY_PROJECTION'
    cached = g.cached_variants([source], metadata=[metadata])[0]
    assert cached['datasets'] == result['datasets']
    assert g.cached_contexts([source], metadata=[metadata])[0]
    attached = {'gnomad_enrichment': {'identity_resolution': result['identity_resolution'],
                                     'cache_key': g.cache_key(*ALLELE)}}
    assert g._supplied_target(source, attached) == ALLELE
    attached['gnomad_enrichment']['cache_key'] += 'wrong'
    assert g._supplied_target(source, attached) is None


def test_position_only_wrong_source_and_multiallelic_projections_are_conservative():
    source = ('GRCh37', '1', 50, 'G', 'T')
    metadata = metadata_for(source, ALLELE)
    bad = deepcopy(metadata)
    bad['original_vcf']['info'] = {'HG38_POS': 55039974}
    assert g._supplied_target(source, bad) is None
    bad = deepcopy(metadata)
    bad['original_vcf']['position'] += 1
    assert g._supplied_target(source, bad) is None
    multi = deepcopy(metadata)
    multi['original_vcf'].update(alternates=['A', 'T'], alt_index=2)
    assert g._supplied_target(source, multi) is None
    multi['original_vcf']['info']['HG38'] = '1:55039974:G:A,1:55039974:G:T'
    assert g._supplied_target(source, multi) == ALLELE


def test_projection_pipeline_overlaps_frequency_fetch_and_keeps_order(monkeypatch):
    monkeypatch.delenv('HELPER_GNOMAD_OFFLINE', raising=False)
    alleles = [('GRCh37', '1', pos, 'G', 'T') for pos in range(1, 7)]
    third = threading.Event()
    def project(build, chrom, pos, ref, alt, **kwargs):
        if pos == 3:
            third.set()
        return dict(status='mapped', source=dict(zip(
            ('reference_build','chromosome','position','reference','alternate'), (build,chrom,pos,ref,alt))),
            target=dict(reference_build='GRCh38',chromosome=chrom,position=pos+100,reference=ref,alternate=alt))
    monkeypatch.setattr(liftover, 'project_variant', project)
    def fetch(query, variables, timeout):
        assert third.wait(3), 'Next projection must run while the first frequency batch is fetched'
        return response_for(variables)
    monkeypatch.setattr(g, '_request_graphql', fetch)
    result = g.lookup_variants(alleles, batch_size=1, include_non_ukb=False)
    assert [r['position'] for r in result] == list(range(101,107))
    assert [r['identity_resolution']['original'] for r in result] == [list(a) for a in alleles]


def test_concurrent_projection_is_retrieved_only_once(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []
    def retrieve(*args, **kwargs):
        calls.append(args)
        entered.set()
        assert release.wait(3)
        return liftover._result('mapped', target={'reference_build': 'GRCh38',
            'chromosome': '1', 'position': 2, 'reference': 'G', 'alternate': 'T'})
    monkeypatch.setattr(liftover, '_retrieve', retrieve)
    database = tmp_path / 'projections.sqlite3'
    allele = ('GRCh37','1',1,'G','T')
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(liftover.project_variant, *allele, database=database)
        assert entered.wait(3)
        second = pool.submit(liftover.project_variant, *allele, database=database)
        release.set()
        a, b = first.result(3), second.result(3)
    assert len(calls) == 1
    assert a['target'] == b['target'] and a['status'] == b['status'] == 'mapped'
    assert not projection_flights._active
