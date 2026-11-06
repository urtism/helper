"""Exact indexed coverage, conservative fallback and bounded reader resources."""
import pytest

from helper_variants import gnomad_coverage as c, gnomad_frequency as g
from test_gnomad_region_coverage import region_response


@pytest.fixture
def local_tracks(tmp_path, monkeypatch):
    bw = pytest.importorskip('pyBigWig')
    c._stop()
    c._retry_after = 0
    for folder, _ in c.DATASETS.values():
        directory = tmp_path / folder
        directory.mkdir()
        positions = [p for p in range(20000) if p != 999]
        for metric, value in [('mean', 30.), ('over_20', .95)]:
            with bw.open(str(directory / ('gnomad.coverage.' + metric + '.bw')), 'w') as handle:
                handle.addHeader([('chr2', 20000)])
                handle.addEntries(['chr2'] * len(positions), positions,
                                  ends=[p+1 for p in positions], values=[value] * len(positions))
    monkeypatch.setenv('HELPER_GNOMAD_COVERAGE_MODE', 'auto')
    monkeypatch.setenv('HELPER_GNOMAD_COVERAGE_DIR', str(tmp_path))
    yield tmp_path
    c._stop()
    c._retry_after = 0


def test_exact_indexed_coordinates_fraction_units_and_missing_bases(local_tracks):
    result = c.read_region('2', 998, 1002)
    assert set(result['data']) == {'exome', 'genome'}
    for rows in result['data'].values():
        assert [row['pos'] for row in rows] == [998, 999, 1001, 1002]
        assert rows[0]['mean'] == 30.
        assert rows[0]['over_20'] == pytest.approx(.95)
    assert result['sources']['exome']['over_20_units'] == 'fraction'
    assert c.read_region('2', 1, 1)['data']['exome'][0]['pos'] == 1
    with pytest.raises(ValueError):
        c.read_region('2', 1, 251)


def test_indexed_coverage_uses_existing_complete_per_base_policy(local_tracks, monkeypatch):
    monkeypatch.setattr(g, '_request_graphql', lambda *a: pytest.fail('Indexed files are available'))
    good, missing = g._fetch_region_coverages([
        ('GRCh38','2',2000,'GTA','G'), ('GRCh38','2',1000,'T','TA')], 12)
    assert good['status'] == 'ADEQUATE'
    assert good['adequate_datasets'] == ['exomes','genomes']
    assert (good['start'],good['stop']) == (1975,2027)
    assert good['datasets']['exomes']['positions_evaluated'] == 53
    assert good['datasets']['exomes']['source_files']['mean'].endswith('.mean.bw')
    assert not good['absence_verified'] and not good['site_an_available']
    assert missing['status'] == 'INCOMPLETE' and not missing['adequate_datasets']


def test_tile_and_open_file_caches_remain_bounded(local_tracks):
    for i in range(20):
        c.read_region('2', i*512+5, i*512+9)
    status = c.resource_status()
    assert status['tiles'] == status['maximum_tiles'] == 32
    assert status['open_files'] == status['maximum_open_files'] == 4
    assert status['pid']


def test_missing_indexed_dataset_falls_back_without_replacing_valid_indexed_rows(monkeypatch):
    def indexed(chrom, start, stop):
        return {'data': {'genome': [{'pos': p, 'mean': 30, 'over_20': .95}
                                    for p in range(start,stop+1)]},
                'sources': {'genome': {'source': 'indexed genome'}}}
    monkeypatch.setattr(c, 'read_region', indexed)
    monkeypatch.setattr(g, '_request_graphql', lambda q,v,t: region_response(v, exome=(10,.1), genome=(1,.1)))
    result = g._fetch_region_coverages([('GRCh38','2',1000,'T','TA')],12)[0]
    assert result['status'] == 'ADEQUATE' and result['adequate_datasets'] == ['genomes']
    assert result['datasets']['genomes']['source'] == 'indexed genome'
    assert result['datasets']['exomes']['status'] == 'LOW'
    def fail(*args):
        raise TimeoutError('GraphQL timeout')
    monkeypatch.setattr(g, '_request_graphql', fail)
    result = g._fetch_region_coverages([('GRCh38','2',1000,'T','TA')],12)[0]
    assert result['status'] == 'ADEQUATE' and result['error'] == 'GraphQL timeout'


def test_reader_timeout_terminates_worker_and_backs_off(monkeypatch):
    class Process:
        alive = True
        def is_alive(self): return self.alive
        def terminate(self): self.alive = False
        def join(self, timeout): pass
    class Connection:
        def send(self, command): pass
        def poll(self, timeout): return False
        def close(self): pass
    process = Process()
    monkeypatch.setattr(c, '_process', process)
    monkeypatch.setattr(c, '_connection', Connection())
    monkeypatch.setattr(c, '_retry_after', 0)
    result = c._read(({}, 'chr2', 0, 10))
    assert not result['data'] and 'time limit' in result['errors']['reader']
    assert not process.alive and c._process is None
    assert c._read(({}, 'chr2', 0, 10))['errors']['reader'].endswith('cooling down')
