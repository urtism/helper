"""Offline coverage of missing alleles: no site AN or absence is fabricated."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import socket

import pytest

from helper_prioritization import RULESET_VERSION, get_profile, score_variant
from helper_variants import gnomad_frequency as g, liftover


ALLELE = ('GRCh38', '2', 1000, 'T', 'TA')


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.delenv('HELPER_GNOMAD_OFFLINE', raising=False)
    monkeypatch.setenv('HELPER_LIFTOVER_CACHE', str(tmp_path / 'projection.sqlite3'))
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('Unexpected network'))


def region_response(variables, *, exome=(30, .95), genome=(30, .95), edit=None):
    data = {}
    for key, chrom in variables.items():
        if not key.startswith('chrom'):
            continue
        index = key.removeprefix('chrom')
        start, stop = variables['start' + index], variables['stop' + index]
        rows = {}
        for name, metrics in [('exome', exome), ('genome', genome)]:
            # Official regional queries pad by 75 bp: only the requested window counts.
            rows[name] = [{'pos': p, 'mean': metrics[0], 'over_20': metrics[1]}
                          for p in range(max(1, start - 75), stop + 76)] if metrics else []
        region = dict(chrom=chrom, start=start, stop=stop, reference_genome='GRCh38', coverage=rows)
        if edit:
            edit(region)
        data['coverage' + index] = region
    return {'data': data}


def provider(monkeypatch, **options):
    calls = []

    def request(query, variables, timeout):
        calls.append((query, variables))
        if 'coverage(dataset:' in query:
            return region_response(variables, **options)
        return {'data': {'v' + name.removeprefix('id') + '_' + subset: None
                         for name in variables for subset in ('all', 'non_ukb')}}

    monkeypatch.setattr(g, '_request_graphql', request)
    return calls


def priority(result):
    return next(c for c in score_variant(g.priority_context(result, scoring_version=RULESET_VERSION))['components']
                if c['key'] == 'maf')


@pytest.mark.parametrize('exome,genome,status,adequate', [
    ((30,.95), (30,.95), 'ADEQUATE', ['exomes','genomes']),
    ((30,.2), (30,.95), 'ADEQUATE', ['genomes']),
    ((20,.8), None, 'ADEQUATE', ['exomes']),
    ((19.9,.95), (30,.79), 'LOW', []),
    ((100,.7), (100,.7), 'LOW', []),
    (None, None, 'UNAVAILABLE', []),
])
def test_missing_allele_checks_both_datasets_and_keeps_unverified_absence(monkeypatch, exome, genome, status, adequate):
    calls = provider(monkeypatch, exome=exome, genome=genome)
    result = g.lookup_variant(*ALLELE)
    coverage = result['region_coverage']
    assert len(calls) == 2
    assert (coverage['start'], coverage['stop'], coverage['locus_start'], coverage['locus_stop']) == (975,1026,1000,1001)
    assert coverage['status'] == status and coverage['adequate_datasets'] == adequate
    assert not coverage['absence_verified'] and not coverage['site_an_available']
    assert result['retrieval_status'] == 'NOT_FOUND' and result['availability'] == 'AVAILABLE'
    assert result['an'] is None and result['af'] is None and not result['population_absent']
    assert all(r['an'] is None and r['filter'] is None for r in result['datasets'].values())
    c = priority(result)
    assert c['score'] == (25 if status == 'ADEQUATE' else 0)
    assert c['evaluated'] == (status == 'ADEQUATE') and c['applicable'] and c['max_score'] == 25
    assert c['frequency_status'] == ('NOT_FOUND_COVERED' if status == 'ADEQUATE' else 'NOT_FOUND_UNVERIFIED')
    assert c['quality_evidence']['region_coverage_status'] == status
    assert c['quality_status'] == ('REGION_COVERED_NO_SITE_AN' if status == 'ADEQUATE' else 'REGION_COVERAGE_' + status)
    assert g.lookup_variant(*ALLELE)['region_coverage'] == coverage
    assert len(calls) == 2  # Both the variant miss and coverage are cached together.


@pytest.mark.parametrize('version', ['germline-wes-v2.0.0', 'germline-wes-v2.1.0'])
def test_old_profiles_keep_zero_for_covered_missing_allele(monkeypatch, version):
    provider(monkeypatch)
    result = g.lookup_variant(*ALLELE)
    profile = get_profile(version)
    scored = score_variant(g.priority_context(result, scoring_version=version), profile)
    c = next(c for c in scored['components'] if c['key'] == 'maf')
    assert c['score'] == 0 and not c['evaluated']
    assert c['frequency_status'] == 'NOT_FOUND_UNVERIFIED'
    assert priority(result)['score'] == 25


def test_regional_bonus_is_explicit_and_does_not_change_other_weights(monkeypatch):
    provider(monkeypatch)
    result = g.lookup_variant(*ALLELE)
    version = RULESET_VERSION
    new = score_variant(g.priority_context(result, scoring_version=version))
    old = score_variant(g.priority_context(result, scoring_version='germline-wes-v2.1.0'),
                        get_profile('germline-wes-v2.1.0'))
    c = next(c for c in new['components'] if c['key'] == 'maf')
    assert c['quality_evidence']['absence_evidence'] == 'regional_coverage_heuristic'
    assert c['quality_evidence']['absence_verified'] is False
    assert c['observed_af'] is None and c['observed_af_source'] is None
    assert 'Heuristic rarity bonus' in c['reason']
    assert 'site-specific AN unavailable' in c['reason']
    assert 'Population frequency' not in new['missing_evidence']
    assert new['max_score'] == old['max_score']
    assert new['score'] - old['score'] == 25
    assert [c for c in new['components'] if c['key'] != 'maf'] == [c for c in old['components'] if c['key'] != 'maf']


@pytest.mark.parametrize('change', [
    {'status': 'LOW'}, {'adequate': False}, {'locus_status': 'INCOMPLETE'},
    {'positions_evaluated': 1}, {'positions_expected': None}, {'fraction_bases_adequate': .98},
])
def test_inconsistent_or_incomplete_summary_never_gains_the_bonus(monkeypatch, change):
    provider(monkeypatch, exome=(30,.2))
    result = deepcopy(g.lookup_variant(*ALLELE))
    result['region_coverage']['datasets']['genomes'].update(change)
    assert priority(result)['score'] == 0
    assert priority(result)['frequency_status'] == 'NOT_FOUND_UNVERIFIED'


@pytest.mark.parametrize('change', [
    {'availability': 'NOT_QUERIED'}, {'region_coverage_pending': True},
    {'error': 'retrieval failed'}, {'partial': True}, {'variant_flags': ['unreliable']},
])
def test_unfinished_or_failed_lookup_never_gains_a_regional_bonus(monkeypatch, change):
    provider(monkeypatch)
    result = deepcopy(g.lookup_variant(*ALLELE))
    result.update(change)
    assert priority(result)['score'] == 0


def test_reported_deletion_has_genome_supported_heuristic_bonus(monkeypatch):
    # Offline regression using synthetic per-base coverage at the reported locus.
    provider(monkeypatch, exome=(20.3,.52), genome=(30.98,.98))
    source = ('GRCh37','11',108153607,'GTA','G')
    target = ('GRCh38','11',108282880,'GTA','G')
    projection = liftover._result('mapped', source=liftover._locus(*source), target=liftover._locus(*target))
    liftover._store(liftover.cache_path(), '|'.join(map(str,source)), projection)
    monkeypatch.setattr(liftover, 'project_variant', lambda *a,**k: projection)
    result = g.lookup_variant(*source)
    assert result['retrieval_status'] == 'NOT_FOUND'
    assert result['region_coverage']['adequate_datasets'] == ['genomes']
    assert result['region_coverage']['datasets']['genomes']['positions_evaluated'] == 53
    c = priority(result)
    assert c['score'] == 25 and c['frequency_status'] == 'NOT_FOUND_COVERED'
    assert c['quality_evidence']['adequate_datasets'] == ['genomes']
    assert result['an'] is None and result['af'] is None and not result['population_absent']


def test_query_uses_new_default_without_reusing_the_old_version_cursor(tmp_path, monkeypatch):
    from helper_variants import query
    from test_variant_query import query_store
    from test_clinvar_integration import install, at
    install(tmp_path, monkeypatch, [at()])
    path, sample, _ = query_store(tmp_path)
    provider(monkeypatch)
    g.lookup_variants([('GRCh38','1',p,'A','G') for p in range(1,6)])
    old = query.list_variants(path, sample, limit=2, scoring_version='germline-wes-v2.1.0')
    new = query.list_variants(path, sample, limit=2)
    for page, expected in [(old,0),(new,25)]:
        assert all(next(c for c in item['priority']['components'] if c['key']=='maf')['score'] == expected
                   for item in page['items'])
    assert new['items'][0]['priority']['ruleset'] == RULESET_VERSION
    assert old['next_cursor'] != new['next_cursor']
    with pytest.raises(query.VariantQueryError):
        query.list_variants(path, sample, cursor=old['next_cursor'])


def test_flank_drop_cannot_be_hidden_by_a_high_regional_average(monkeypatch):
    def edit(region):
        for name in ('exome','genome'):
            for row in region['coverage'][name]:
                if row['pos'] == region['start']:
                    row.update(mean=5, over_20=.1)
    provider(monkeypatch, exome=(100,.99), genome=(100,.99), edit=edit)
    result = g.lookup_variant(*ALLELE)
    assert result['region_coverage']['status'] == 'LOW'
    for summary in result['region_coverage']['datasets'].values():
        assert summary['mean'] > 90 and summary['mean_min'] == 5
        assert summary['locus_status'] == 'ADEQUATE'
        assert summary['fraction_bases_adequate'] < 1


@pytest.mark.parametrize('change', ['missing_position', 'missing_metric', 'duplicate_position', 'wrong_assembly', 'wrong_region'])
def test_partial_and_mismatched_coverage_do_not_assert_evaluability(monkeypatch, change):
    def edit(region):
        for name in ('exome','genome'):
            rows = region['coverage'][name]
            target = next(r for r in rows if r['pos'] == 1000)
            if change == 'missing_position': rows.remove(target)
            if change == 'missing_metric': target['over_20'] = None
            if change == 'duplicate_position': rows.append(dict(target))
        if change == 'wrong_assembly': region['reference_genome'] = 'GRCh37'
        if change == 'wrong_region': region['start'] += 1
    provider(monkeypatch, edit=edit)
    result = g.lookup_variant(*ALLELE)
    expected = 'INCOMPLETE' if change.startswith('missing') else 'ERROR'
    assert result['region_coverage']['status'] == expected
    assert result['region_coverage']['adequate_datasets'] == []
    assert priority(result)['score'] == 0


def test_cached_missing_allele_gains_coverage_without_refetching_variant(monkeypatch):
    result = g._parse_response({'data': {'variant': None}}, g.DATASETS['GRCh38'], ALLELE, '')
    assert result['region_coverage_pending']
    g._store(g.cache_path(), g.cache_key(*ALLELE), result)
    calls = provider(monkeypatch)
    covered = g.lookup_variant(*ALLELE)
    assert not covered['region_coverage_pending']
    assert len(calls) == 1 and 'coverage(dataset:' in calls[0][0]
    assert covered['region_coverage']['status'] == 'ADEQUATE'
    monkeypatch.setenv('HELPER_GNOMAD_OFFLINE','1')
    assert g.lookup_variant(*ALLELE)['region_coverage'] == covered['region_coverage']
    assert len(calls) == 1


def test_policy_change_refreshes_coverage_without_requerying_the_allele(monkeypatch):
    calls = provider(monkeypatch)
    assert g.lookup_variant(*ALLELE)['region_coverage']['status'] == 'ADEQUATE'
    assert len(calls) == 2
    monkeypatch.setattr(g, 'MIN_MEAN_COVERAGE', 31)
    cached = g.cached_variant(*ALLELE)
    assert cached['region_coverage_pending']
    refreshed = g.lookup_variant(*ALLELE)
    assert refreshed['region_coverage']['status'] == 'LOW'
    assert refreshed['region_coverage']['minimum_mean'] == 31
    assert len(calls) == 3 and 'coverage(dataset:' in calls[-1][0]


def test_coverage_error_is_separate_from_missing_allele_and_retry_is_bounded(monkeypatch):
    calls = provider(monkeypatch)
    original = g._request_graphql

    def fail_coverage(query, variables, timeout):
        if 'coverage(dataset:' in query:
            calls.append((query, variables))
            raise g.GnomadFrequencyError('coverage timeout')
        return original(query, variables, timeout)

    monkeypatch.setattr(g, '_request_graphql', fail_coverage)
    result = g.lookup_variant(*ALLELE)
    assert result['retrieval_status'] == 'NOT_FOUND' and not result['error']
    assert result['region_coverage']['status'] == 'ERROR'
    assert priority(result)['quality_status'] == 'REGION_COVERAGE_ERROR'
    assert g.lookup_variant(*ALLELE)['region_coverage']['status'] == 'ERROR'
    assert len(calls) == 2
    result['region_coverage']['retrieved_at'] = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    g._store(g.cache_path(), g.cache_key(*ALLELE), result)
    g.lookup_variant(*ALLELE)
    assert len(calls) == 3 and 'coverage(dataset:' in calls[-1][0]


def test_failed_allele_lookup_does_not_start_coverage(monkeypatch):
    calls = []
    def error(query, variables, timeout):
        calls.append(query)
        raise g.GnomadFrequencyError('allele lookup failed')
    monkeypatch.setattr(g, '_request_graphql', error)
    result = g.lookup_variant(*ALLELE)
    assert len(calls) == 1 and result['retrieval_status'] == 'UNAVAILABLE'
    assert 'region_coverage' not in result


def test_coverage_batches_are_bounded_and_duplicate_alleles_share_one_read(monkeypatch):
    calls = provider(monkeypatch)
    alleles = [('GRCh38','2',1000+i,'A','G') for i in range(5)]
    results = g.lookup_variants(alleles * 3)
    coverage_calls = [(q,v) for q,v in calls if 'coverage(dataset:' in q]
    assert len(results) == 15 and len(calls) == 4 and len(coverage_calls) == 3
    assert all(q.count('coverage(dataset:') <= 2 for q,v in coverage_calls)
    assert all(r['region_coverage']['status'] == 'ADEQUATE' for r in results)
    for allele, result in zip(alleles*3, results):
        assert result['region_coverage']['locus_start'] == allele[2]


def test_grch37_coverage_is_queried_at_projected_grch38_coordinates(monkeypatch):
    calls = provider(monkeypatch)
    source = ('GRCh37','2',48032123,'T','TA')
    target = ('GRCh38','2',47804984,'T','TA')
    projection = liftover._result('mapped', source=liftover._locus(*source), target=liftover._locus(*target))
    liftover._store(liftover.cache_path(), '|'.join(map(str,source)), projection)
    monkeypatch.setattr(liftover,'project_variant',lambda *a,**k: projection)
    result = g.lookup_variant(*source)
    assert result['region_coverage']['locus_start'] == 47804984
    assert calls[1][1]['start0'] == 47804959
    assert result['region_coverage']['status'] == 'ADEQUATE'


def test_large_region_is_explicitly_unsupported_without_a_coverage_request(monkeypatch):
    calls = provider(monkeypatch)
    result = g.lookup_variant('GRCh38','2',1000,'A'*300,'A')
    assert len(calls) == 1
    assert result['region_coverage']['status'] == 'UNSUPPORTED'
    assert priority(result)['score'] == 0


def test_chromosome_start_is_clipped_and_api_padding_is_ignored(monkeypatch):
    def edit(region):
        for rows in region['coverage'].values():
            for row in rows:
                if row['pos'] > region['stop']:
                    row.update(mean=0,over_20=0)
    provider(monkeypatch,edit=edit)
    result = g.lookup_variant('GRCh38','2',1,'A','G')
    assert result['region_coverage']['start'] == 1
    assert result['region_coverage']['status'] == 'ADEQUATE'
    assert result['region_coverage']['datasets']['genomes']['positions_expected'] == 26
