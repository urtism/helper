import json
import sqlite3

import pytest

from helper_next.api import variants as api
from helper_variants import gnomad_enrichment as e, gnomad_frequency as g, query
from test_gnomad_frequency import provider
from test_variant_query import query_store


def test_all_unique_variants_shared_across_samples_and_cache_before_detail(tmp_path,monkeypatch):
    monkeypatch.delenv('HELPER_GNOMAD_OFFLINE',raising=False)
    path,first,second=query_store(tmp_path)
    calls=provider(monkeypatch)
    result=e.enrich_run({},database=path,batch_size=3)
    assert result['status']=='complete' and result['attempted']==5
    assert result['outcomes']['FOUND']==5 and len(calls)==2
    assert e.status(path)['status']=='complete'
    monkeypatch.setattr(g,'_request_graphql',lambda *a: pytest.fail('Already cached'))
    detail=query.variant_detail(path,first,1)
    assert detail['gnomad_frequency']['cache']=='hit'
    other=query.variant_detail(path,second,1)
    assert other['gnomad_frequency']['datasets']==detail['gnomad_frequency']['datasets']
    assert e.enrich_run({},database=path)['status']=='complete'
    with sqlite3.connect(path) as db:
        rows=db.execute('SELECT metadata_json FROM variants').fetchall()
        for (raw,) in rows:
            record=json.loads(raw)['gnomad_enrichment']
            assert record['cache_key'] and record['retrieval_status']=='FOUND'
            assert 'datasets' not in record


def test_error_attempts_every_allele_and_never_declares_completed(tmp_path,monkeypatch):
    monkeypatch.delenv('HELPER_GNOMAD_OFFLINE',raising=False)
    path,*_=query_store(tmp_path)
    monkeypatch.setattr(g,'_request_graphql',lambda *a: (_ for _ in ()).throw(g.GnomadFrequencyError('unreachable')))
    result=e.enrich_run({},database=path,batch_size=2)
    assert result['status']=='partial' and result['attempted']==5
    assert result['outcomes']['UNAVAILABLE']==5
    assert query.run_summary(path)['variant_count']==5


def test_enrichment_routes_are_explicit_and_reject_duplicate_run(tmp_path,monkeypatch):
    from fastapi import BackgroundTasks, HTTPException
    path,*_=query_store(tmp_path)
    monkeypatch.setattr(api,'_entry',lambda identifier: {'database':path,'record':{}})
    monkeypatch.setattr(api,'_entry_database',lambda entry:path)
    background=BackgroundTasks()
    assert api.run_gnomad_enrichment_status('RUN')['status']=='not_started'
    try:
        result=api.run_gnomad_enrichment_start('RUN',background)
        assert result['status']=='running' and len(background.tasks)==1
        with pytest.raises(HTTPException) as error:
            api.run_gnomad_enrichment_start('RUN',BackgroundTasks())
        assert error.value.status_code==409
    finally:
        e.finish(path)
