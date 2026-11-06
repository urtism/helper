"""CACHE-09: verified schemas, offline fixtures and exact allele identities."""
import copy
import io
import json
import socket
import sqlite3
from pathlib import Path

import pytest

from helper_variants import gnomad_frequency as g, liftover
from test_biological_identity import reference_record

FIXTURES = Path(__file__).parent / 'fixtures/gnomad_v4'
ALLELE = ('GRCh38', '1', 55039974, 'G', 'T')


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.delenv('HELPER_GNOMAD_OFFLINE', raising=False)
    monkeypatch.setenv('HELPER_LIFTOVER_CACHE', str(tmp_path / 'projection.sqlite3'))
    monkeypatch.setattr(socket.socket, 'connect', lambda *args: pytest.fail('Unexpected network access'))


def official():
    return json.loads((FIXTURES / 'frequency_4.1.1.json').read_text())


def response_for(variables, template=None):
    data = {}
    template = template or official()
    for name, variant_id in variables.items():
        i = name.removeprefix('id')
        chrom, pos, ref, alt = variant_id.split('-')
        for subset in ('all', 'non_ukb'):
            variant = copy.deepcopy(template['data']['v0_' + subset])
            if variant is not None:
                variant.update(variant_id=variant_id, chrom=chrom, pos=int(pos), ref=ref, alt=alt)
            data[f'v{i}_{subset}'] = variant
    return {'data': data}


def provider(monkeypatch, template=None):
    calls = []
    def fake(query, variables, timeout):
        calls.append((query, variables))
        if 'coverage(dataset:' in query:
            return {'data': {
                'coverage' + name.removeprefix('chrom'): {
                    'chrom': value, 'start': variables['start' + name.removeprefix('chrom')],
                    'stop': variables['stop' + name.removeprefix('chrom')],
                    'reference_genome': 'GRCh38', 'coverage': {'exome': [], 'genome': []},
                } for name, value in variables.items() if name.startswith('chrom')
            }}
        return response_for(variables, template)
    monkeypatch.setattr(g, '_request_graphql', fake)
    return calls


def test_http_cache_distinguishes_batch_queries_and_alleles(monkeypatch):
    cached_http = {}
    requests = []
    monkeypatch.setattr(g.time, 'sleep', lambda seconds: None)
    def open_cached(request, timeout):
        requests.append(request)
        payload = json.loads(request.data)
        if request.full_url not in cached_http:
            cached_http[request.full_url] = json.dumps(response_for(payload['variables'])).encode()
        return io.BytesIO(cached_http[request.full_url])
    monkeypatch.setattr(g, 'urlopen', open_cached)
    second = ('GRCh38', '1', 55039975, 'C', 'A')
    first = g._fetch_batch([ALLELE, second], 12)
    changed = g._fetch_batch([second, ALLELE], 12)
    single = g._fetch_batch([ALLELE], 12)
    assert all(row['retrieval_status'] == 'FOUND' for row in first + changed + single)
    assert len({request.full_url for request in requests}) == 3
    assert all('request=' in request.full_url for request in requests)
    assert all(request.get_header('Cache-control') == 'no-cache' for request in requests)


def test_wrong_alias_cached_error_is_retried_immediately(monkeypatch):
    calls = []
    def fetch(query, variables, timeout):
        calls.append(variables)
        return {'data': {'q0': None}} if len(calls) == 1 else response_for(variables)
    monkeypatch.setattr(g, '_request_graphql', fetch)
    broken = g.lookup_variant(*ALLELE)
    assert broken['retrieval_status'] == 'UNAVAILABLE'
    assert broken['error'] == 'Incomplete GraphQL response'
    recovered = g.lookup_variant(*ALLELE)
    assert recovered['retrieval_status'] == 'FOUND'
    assert len(calls) == 2


def test_grch38_official_products_precise_faf_populations_and_cache(tmp_path, monkeypatch):
    calls = provider(monkeypatch)
    database = tmp_path / 'frequencies.sqlite3'
    result = g.lookup_variant(*ALLELE, database=database)
    assert result['retrieval_status'] == 'FOUND'
    assert result['release'] == '4.1.1'
    assert result['reference_build'] == 'GRCh38'
    assert result['cache'] == 'miss'
    exome, genome, joint = (result['datasets'][p] for p in ('exomes', 'genomes', 'joint'))
    assert [p['ac'] for p in (exome, genome, joint)] == [21634, 1866, 23500]
    assert exome['af'] == 21634 / 1428186
    assert exome['grpmax_faf95'] == .01651719
    assert joint['grpmax_faf95'] == .01649444
    assert genome['grpmax_faf95'] == .015429449999999996
    assert joint['grpmax_faf95_population'] == 'nfe'
    assert exome['grpmax_faf99'] is None
    assert all(p['faf95'] is None for p in exome['populations'])
    assert any(p['id'] == 'afr_XX' for p in exome['populations'])
    assert result['subsets']['non_ukb']['datasets']['exomes']['ac'] == 7794
    assert result['subsets']['non_ukb']['datasets']['joint']['ac'] is None
    assert exome['quality_metrics']['site_quality_metrics']
    assert joint['freq_comparison_stats']['stat_union']['p_value'] == .5518385442268651
    cached = g.lookup_variant(*ALLELE, database=database)
    assert cached['cache'] == 'hit' and len(calls) == 1
    cached['datasets']['joint']['ac'] = 1
    assert g.cached_variant(*ALLELE, database=database)['datasets']['joint']['ac'] == 23500
    assert g.cache_status(database)['current_release_record_count'] == 1
    assert '@4.1.1|' in g.cache_key(*ALLELE)
    assert 'faf95 { popmax popmax_population }' in calls[0][0]
    assert 'dataset: gnomad_r4_non_ukb' in calls[0][0]


def test_hg19_projects_exact_allele_to_v4_without_v2_fallback(tmp_path, monkeypatch):
    calls = provider(monkeypatch)
    source = ('GRCh37', '1', 55505647, 'G', 'T')
    def project(*allele, **kwargs):
        assert allele == source
        result = liftover._result('mapped', source=liftover._locus(*source), target=liftover._locus(*ALLELE))
        liftover._store(liftover.cache_path(), '|'.join(map(str, source)), result)
        return result
    monkeypatch.setattr(liftover, 'project_variant', project)
    result = g.lookup_variant(*source)
    assert result['release'] == '4.1.1' and result['reference_build'] == 'GRCh38'
    assert calls[0][1]['id0'] == '1-55039974-G-T'
    assert 'gnomad_r2' not in calls[0][0]
    assert result['identity_resolution']['source_identity']['identity']['assembly'] == 'GRCh37'
    assert g.cached_variant(*source)['datasets']['genomes']['ac'] == 1866


@pytest.mark.parametrize('state', ['ambiguous', 'not_mapped', 'unavailable'])
def test_projection_failure_is_explicit_and_never_fetches_v2(monkeypatch, state):
    monkeypatch.setattr(liftover, 'project_variant', lambda *a, **k: {'status': state})
    monkeypatch.setattr(g, '_request_graphql', lambda *a: pytest.fail('No gnomAD call for invalid projection'))
    result = g.lookup_variant('GRCh37', '1', 10, 'A', 'C')
    assert result['retrieval_status'] == ('UNAVAILABLE' if state == 'unavailable' else 'UNSUPPORTED')
    assert result['af'] is None


def test_projection_source_allele_mismatch_is_rejected(monkeypatch):
    monkeypatch.setattr(liftover, 'project_variant', lambda *a, **k: {
        'status':'mapped', 'source':liftover._locus('GRCh37','1',10,'A','G'),
        'target':liftover._locus(*ALLELE)})
    assert g.lookup_variant('GRCh37','1',10,'A','C')['retrieval_status'] == 'UNSUPPORTED'


def test_indel_uses_submitted_allele_without_local_normalization(tmp_path, monkeypatch):
    from helper_variants import indexer
    from helper_next.core import biological_identity
    record = reference_record(tmp_path)
    monkeypatch.setattr(indexer, 'open_reference', lambda *a, **k: pytest.fail('No local FASTA access'))
    monkeypatch.setattr(biological_identity, 'allele_refs_batch', lambda *a, **k: pytest.fail('No local identity verification'))
    calls = provider(monkeypatch)
    result = g.lookup_variant('GRCh38', 'chr1', 3, 'AA', 'A', record=record)
    identity = result['identity_resolution']['target_identity']
    assert identity['status'] == 'RESOLVED'
    assert identity['reference_provenance']['ref_status'] == 'NOT_CHECKED'
    assert identity['reference_provenance']['normalization'] == 'AS_SUPPLIED'
    assert identity['allele_ref'] is None
    assert calls[0][1]['id0'] == '1-3-AA-A'
    assert result['position'] == 3 and result['reference'] == 'AA' and result['alternate'] == 'A'


def test_local_reference_does_not_override_submitted_ref(tmp_path, monkeypatch):
    record = reference_record(tmp_path)
    calls = provider(monkeypatch)
    result = g.lookup_variant('GRCh38','1',7,'A','T',record=record)
    assert calls[0][1]['id0'] == '1-7-A-T'
    assert result['retrieval_status'] == 'FOUND'
    assert result['identity_resolution']['source_identity']['reference_provenance']['ref_status'] == 'NOT_CHECKED'


@pytest.mark.parametrize('build,chrom,pos', [('GRCh38','2',47804984), ('hg19','chr2',48032123)])
def test_reported_insertion_lookup_cache_and_priority_without_fasta(tmp_path, monkeypatch, build, chrom, pos):
    from helper_next.core import biological_identity
    from helper_variants import indexer
    from helper_prioritization import RULESET_VERSION, score_variant

    monkeypatch.setattr(indexer, 'open_reference', lambda *a, **k: pytest.fail('No local FASTA access'))
    monkeypatch.setattr(biological_identity, 'allele_refs_batch', lambda *a, **k: pytest.fail('No ga2 reference verification'))
    monkeypatch.setenv('HELPER_ACMG_REFERENCE_CONFIG', str(tmp_path / 'missing-reference-config.json'))
    template = json.loads((FIXTURES / 'frequency_2_47804984_T_TA.json').read_text())
    calls = provider(monkeypatch, template)
    source = ('GRCh37','2',48032123,'T','TA')
    target = ('GRCh38','2',47804984,'T','TA')
    projection = liftover._result('mapped', source=liftover._locus(*source), target=liftover._locus(*target))
    liftover._store(liftover.cache_path(), '|'.join(map(str, source)), projection)
    monkeypatch.setattr(liftover, 'project_variant', lambda *a, **k: projection)
    allele = (build,chrom,pos,'T','TA')
    result = g.lookup_variant(*allele)
    assert result['retrieval_status'] == 'FOUND'
    assert calls[0][1]['id0'] == '2-47804984-T-TA'
    assert result['datasets']['joint']['ac'] == 15
    assert result['identity_resolution']['target_identity']['reference_provenance']['ref_status'] == 'NOT_CHECKED'
    # Reads and offline lookup must reuse exactly the same projected cache key.
    context = g.cached_contexts([allele], scoring_version=RULESET_VERSION)[0]
    c = next(c for c in score_variant(context)['components'] if c['key'] == 'maf')
    assert c['score'] == 15 and c['frequency_status'] == 'OBSERVED'
    assert c['observed_af_source']['population'] == 'eas'
    monkeypatch.setenv('HELPER_GNOMAD_OFFLINE','1')
    assert g.lookup_variant(*allele)['cache'] == 'hit'
    assert len(calls) == 1


def test_missing_indel_stays_unverified_without_fasta(monkeypatch):
    template = {'data': {'v0_all': None, 'v0_non_ukb': None}}
    calls = provider(monkeypatch, template)
    result = g.lookup_variant('GRCh38', '2', 47804984, 'T', 'TA')
    assert len(calls) == 2  # Allele lookup, then regional coverage without a variant record.
    assert result['retrieval_status'] == 'NOT_FOUND'
    assert result['af'] is None
    assert not result['population_absent']


@pytest.mark.parametrize('allele', [('GRCh38','1',10,'A','A'), ('GRCh38','MT',10,'A','G'),
                                  ('GRCh38','1',10,'A','<DEL>'), ('unknown','1',10,'A','G')])
def test_unsupported_does_not_use_network(allele, monkeypatch):
    monkeypatch.setattr(g, '_request_graphql', lambda *a: pytest.fail('Unsupported lookup'))
    assert g.lookup_variant(*allele)['retrieval_status'] == 'UNSUPPORTED'


@pytest.mark.parametrize('missing,present', [('exome','genome'), ('genome','exome')])
def test_single_dataset_presence_does_not_fabricate_counts(tmp_path, monkeypatch, missing, present):
    template = official()
    template['data']['v0_all'][missing] = None
    provider(monkeypatch, template)
    result = g.lookup_variant(*ALLELE)
    key = {'genome':'genomes','exome':'exomes'}
    assert result['datasets'][key[missing]]['presence'] == 'NOT_OBSERVED'
    assert result['datasets'][key[missing]]['ac'] is None
    assert result['datasets'][key[missing]]['filter'] is None
    assert result['datasets'][key[present]]['ac'] > 0
    assert result['retrieval_status'] == 'FOUND'


def test_absent_allele_preserves_explicit_an_but_missing_record_has_no_zero(monkeypatch):
    template = official()
    template['data']['v0_all']['exome']['ac'] = 0
    template['data']['v0_all']['exome']['homozygote_count'] = 0
    provider(monkeypatch, template)
    result = g.lookup_variant(*ALLELE)
    exome = result['datasets']['exomes']
    assert exome['ac'] == 0 and exome['an'] == 1428186 and exome['af'] == 0
    assert exome['presence'] == 'PRESENT'  # Explicit record, distinct from a null product.
    absent = g._parse_response({'data':{'variant':None}},g.DATASETS['GRCh38'],ALLELE,'')
    assert absent['retrieval_status'] == 'NOT_FOUND'
    assert absent['af'] is None and absent['datasets']['exomes']['an'] is None
    assert not g.priority_context(absent).get('population_absent')


@pytest.mark.parametrize('filters', ['EXOMES_FILTERED','GENOMES_FILTERED','BOTH_FILTERED'])
def test_original_filters_are_independent_and_preserved(monkeypatch, filters):
    template = official()
    variant = template['data']['v0_all']
    variant['exome']['filters'] = ['RF']
    variant['genome']['filters'] = []
    variant['joint']['filters'] = [filters]
    provider(monkeypatch, template)
    result = g.lookup_variant(*ALLELE)
    assert [result['datasets'][p]['filter'] for p in ('exomes','genomes','joint')] == ['RF','PASS',filters]
    assert g.priority_context(result)['population_af'] == max(result['af'],result['max_population_af'])


def test_priority_context_uses_genome_faf95_and_keeps_raw_af():
    result = g._parse_response(
        {'data': {'variant': official()['data']['v0_all']}},
        g.DATASETS['GRCh38'], ALLELE, '',
    )
    context = g.priority_context(result)

    assert context['population_faf'] == result['datasets']['genomes']['grpmax_faf95']
    assert context['population_af'] == max(result['af'], result['max_population_af'])


def test_genome_absence_requires_good_coverage_and_pass_filter(monkeypatch):
    template = official()
    genome = template['data']['v0_all']['genome']
    genome['ac'] = 0
    genome['homozygote_count'] = 0
    genome['filters'] = []
    for population in genome['populations']:
        population['ac'] = 0
        population['homozygote_count'] = 0
    provider(monkeypatch, template)

    result = g.lookup_variant(*ALLELE)
    context = g.priority_context(result)

    assert result['status'] == 'not_observed_covered'
    assert result['population_absent'] is True
    assert context['population_absent'] is True
    assert context['population_coverage_adequate'] is True
    assert context['population_faf'] == result['datasets']['genomes']['grpmax_faf95']


@pytest.mark.parametrize(
    'mean, over_20, filters',
    [(19.9, .99, []), (20, .79, []), (35, .99, ['RF'])],
)
def test_genome_absence_is_not_verified_with_poor_coverage_or_filters(
        monkeypatch, mean, over_20, filters):
    template = official()
    variant = template['data']['v0_all']
    genome = variant['genome']
    genome['ac'] = 0
    genome['homozygote_count'] = 0
    genome['filters'] = filters
    variant['coverage']['genome']['mean'] = mean
    variant['coverage']['genome']['over_20'] = over_20
    provider(monkeypatch, template)

    result = g.lookup_variant(*ALLELE)

    assert result['status'] != 'not_observed_covered'
    assert result['population_absent'] is False


@pytest.mark.parametrize('field,value', [('release','4.1'), ('dataset','gnomad_r2_1'), ('alternate','A'),
                                       ('reference_build','GRCh37'), ('parser_version','old')])
def test_cached_payload_identity_and_release_validated_in_all_readers(tmp_path, monkeypatch, field, value):
    provider(monkeypatch)
    db = tmp_path / 'cache.sqlite3'
    result = g.lookup_variant(*ALLELE,database=db)
    result[field] = value
    g._store(db,g.cache_key(*ALLELE),result)
    assert g.cached_variant(*ALLELE,database=db) is None
    assert g.cached_contexts([ALLELE,ALLELE],db) == [{},{}]
    monkeypatch.setenv('HELPER_GNOMAD_OFFLINE','1')
    assert g.lookup_variant(*ALLELE,database=db)['af'] is None


def test_release_key_does_not_overwrite_old_release(tmp_path, monkeypatch):
    provider(monkeypatch)
    db = tmp_path / 'cache.sqlite3'
    g.lookup_variant(*ALLELE,database=db)
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE frequencies SET cache_key=replace(cache_key,'@4.1.1','@4.1'),release='4.1'")
    assert g.cached_variant(*ALLELE,database=db) is None
    assert g.lookup_variant(*ALLELE,database=db)['cache'] == 'miss'
    assert g.cache_status(db)['record_count'] == 2


def test_network_error_is_not_a_negative_and_has_short_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(g,'_request_graphql',lambda *a: (_ for _ in ()).throw(g.GnomadFrequencyError('timeout')))
    db = tmp_path / 'cache.sqlite3'
    result = g.lookup_variant(*ALLELE,database=db)
    assert result['retrieval_status'] == 'UNAVAILABLE' and result['af'] is None
    assert result['availability'] == 'ERROR'
    calls = provider(monkeypatch)
    assert g.lookup_variant(*ALLELE,database=db)['cache'] == 'hit'
    assert not calls
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE frequencies SET retrieved_at='2000-01-01T00:00:00+00:00'")
    assert g.lookup_variant(*ALLELE,database=db)['retrieval_status'] == 'FOUND'
    assert len(calls) == 1


def test_alias_error_affects_only_corresponding_subset(monkeypatch):
    def fake(query,variables,timeout):
        result = response_for(variables)
        result['data']['v0_non_ukb'] = None
        result['errors'] = [{'path':['v0_non_ukb'],'message':'upstream timeout'}]
        return result
    monkeypatch.setattr(g,'_request_graphql',fake)
    result = g.lookup_variants([ALLELE,('GRCh38','1',55039975,'G','T')])
    assert not result[0].get('partial') and result[0]['retrieval_status'] == 'FOUND'
    assert result[0]['non_ukb_pending'] and result[0]['subset_errors']['non_ukb']
    assert result[0]['subsets']['non_ukb']['retrieval_status'] == 'UNAVAILABLE'
    assert not result[1].get('partial')


def test_wrong_returned_allele_never_cached_as_found(monkeypatch):
    def fake(query,variables,timeout):
        result=response_for(variables)
        result['data']['v0_all']['alt']='A'
        return result
    monkeypatch.setattr(g,'_request_graphql',fake)
    assert g.lookup_variant(*ALLELE)['retrieval_status'] == 'UNAVAILABLE'


def test_batch_thousand_alleles_and_recurrent_samples_are_deduplicated(monkeypatch):
    calls=provider(monkeypatch)
    alleles=[('GRCh38','1',p,'G','T') for p in range(1000,2000)]
    result=g.lookup_variants(alleles*3)
    assert len(result)==3000 and len(calls)==100
    assert all(r['retrieval_status']=='FOUND' for r in result)
    assert len(g.lookup_variants(alleles*2))==2000 and len(calls)==100


def test_batch_local_read_deduplicates_sql_and_keeps_genomes_priority_contract(monkeypatch):
    provider(monkeypatch)
    expected=g.lookup_variant(*ALLELE)
    queries=[]
    connect=sqlite3.connect
    def traced(*a,**k):
        connection=connect(*a,**k);connection.set_trace_callback(queries.append);return connection
    monkeypatch.setattr(g.sqlite3,'connect',traced)
    result=g.cached_contexts([ALLELE]*1100)
    assert len(result)==1100
    assert all(r['population_af']==max(expected['af'],expected['max_population_af']) for r in result)
    assert sum(q.startswith('SELECT') for q in queries)==1


def test_source_manager_reuses_same_evidence_without_fetch(monkeypatch):
    from helper_next.core.acmg_sources import SourceManager
    provider(monkeypatch)
    g.lookup_variant(*ALLELE)
    monkeypatch.setattr(g,'_request_graphql',lambda *a: pytest.fail('Read-only consumer'))
    result=SourceManager().population(dict(zip(('assembly','chromosome','position','reference','alternate'),ALLELE)))
    assert result['status']=='AVAILABLE' and result['release']=='4.1.1'
    assert result['data']['datasets']['joint']['ac']==23500


def test_invalid_cache_json_is_an_error_offline(monkeypatch):
    provider(monkeypatch);g.lookup_variant(*ALLELE)
    with sqlite3.connect(g.cache_path()) as db:
        db.execute("UPDATE frequencies SET payload='invalid json'")
    monkeypatch.setenv('HELPER_GNOMAD_OFFLINE','1')
    result=g.lookup_variant(*ALLELE)
    assert result['availability']=='ERROR' and result.get('af') is None
