"""Official 4.1.2 TSV excerpt; imports and consumers remain entirely offline."""
import csv
import io
import json
import socket
import sqlite3

import pytest

from helper_variants import gene_phenotype, gnomad_constraint as c, source_registry
from test_gene_phenotype import HEADER
from test_gnomad_frequency import FIXTURES


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *args: pytest.fail('Unexpected network'))


def initialized(tmp_path):
    path=tmp_path/'gene.sqlite3'
    gene_phenotype.build_cache(io.StringIO(HEADER),path)
    return path


def test_official_transcripts_release_version_flags_ranks_and_ci(tmp_path):
    path=initialized(tmp_path)
    result=c.import_tsv(FIXTURES/'constraint_4.1.2.tsv',path,confirmed=True)
    assert result['release']=='4.1.2' and result['assembly']=='GRCh38'
    assert result['record_count']==8 and len(result['sha256'])==64
    constraint=gene_phenotype.query_gene('A1BG',database=path)['gene_constraint']
    assert constraint['release']=='4.1.2' and constraint['stale'] is False
    transcripts={row['transcript_id']:row for row in constraint['transcripts']}
    assert 'NM_130786.4' in transcripts and 'ENST00000263100.8' in transcripts
    enst=transcripts['ENST00000263100.8']
    assert enst['loeuf']==1.2292
    assert enst['rank']==14080 and enst['decile']==7
    assert enst['lof']['oe_ci.upper']==enst['loeuf']
    assert enst['syn']['obs'] is not None and enst['syn']['oe_ci.lower'] is not None
    assert enst['constraint_flags']==[] and enst['gene_flags']==[]
    assert 'cds_length' not in enst and 'start_position' not in enst
    assert 'loeuf' not in constraint  # Multiple transcripts are never reduced to one gene score.
    packet=gene_phenotype.mechanism_source_records('HGNC:5','A1BG',path,sources=['gnomad'])['gnomad']
    assert packet['dataset_version']=='4.1.2' and not packet['stale']
    assert {row['transcript_id'] for row in packet['records']}==set(transcripts)
    assert packet['manifest']['sha256']==result['sha256']


def test_import_is_explicit_and_failure_preserves_existing_dataset(tmp_path):
    path=initialized(tmp_path)
    with pytest.raises(ValueError,match='confirmation'):
        c.import_tsv(FIXTURES/'constraint_4.1.2.tsv',path)
    c.import_tsv(FIXTURES/'constraint_4.1.2.tsv',path,confirmed=True)
    original=c.status(path)
    raw=(FIXTURES/'constraint_4.1.2.tsv').read_text()
    bad=tmp_path/'bad.tsv';bad.write_text(raw+'incomplete\trow\n')
    with pytest.raises((ValueError,KeyError,TypeError)):
        c.import_tsv(bad,path,confirmed=True)
    assert c.status(path)==original
    assert gene_phenotype.query_gene('A1BG',database=path)['gene_constraint']['transcripts']


def test_legacy_release_never_relabeled_and_refresh_cannot_replace_pinned(tmp_path,monkeypatch):
    path=initialized(tmp_path)
    response=io.BytesIO(b'{"data":{"gene":{"gene_id":"ENSG00000121410","canonical_transcript_id":"ENST00000263100","gnomad_constraint":{"oe_lof_upper":1.2292}}}}')
    monkeypatch.setattr(gene_phenotype,'_open_request',lambda *a: response)
    gene_phenotype.refresh_gnomad_constraint('A1BG',path)
    legacy=gene_phenotype.query_gene('A1BG',database=path)['gene_constraint']
    assert legacy['release'] is None and 'unverified' in legacy['source']
    c.import_tsv(FIXTURES/'constraint_4.1.2.tsv',path,confirmed=True)
    monkeypatch.setattr(gene_phenotype,'_open_request',lambda *a: pytest.fail('No unversioned API replacement'))
    assert gene_phenotype.refresh_gnomad_constraint('A1BG',path)
    assert all(r['release']=='4.1.2' for r in gene_phenotype.query_gene('A1BG',database=path)['gene_constraint']['transcripts'])


def test_existing_gene_refresh_preserves_supervised_constraint(tmp_path):
    path=initialized(tmp_path)
    manifest=c.import_tsv(FIXTURES/'constraint_4.1.2.tsv',path,confirmed=True)
    original=gene_phenotype.query_gene('A1BG',database=path)['gene_constraint']['transcripts']
    gene_phenotype.build_cache(io.StringIO(HEADER),path)
    assert c.status(path)['sha256']==manifest['sha256']
    assert gene_phenotype.query_gene('A1BG',database=path)['gene_constraint']['transcripts']==original


def test_admin_separates_target_and_installed_release(tmp_path,monkeypatch):
    path=initialized(tmp_path)
    monkeypatch.setenv('HELPER_GENE_PHENOTYPE_DB',str(path))
    row=source_registry.administrative_catalog('gnomad')['sources'][0]
    assert row['version'] is None and row['details']['target_release']=='4.1.2'
    c.import_tsv(FIXTURES/'constraint_4.1.2.tsv',path,confirmed=True)
    row=source_registry.administrative_catalog('gnomad')['sources'][0]
    assert row['version']=='4.1.2' and row['installed'] and row['last_updated']
    assert row['details']['access_mode']=='supervised_local_tsv'
    assert not row['update_supported']
