"""Offline CACHE-09 benchmark. HTTP/quota/liftover latency is deliberately excluded.

Run: PYTHONPATH=helper_next/src python scripts/benchmark_gnomad_integration.py
"""
import argparse
import copy
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

from helper_variants import gnomad_frequency as g


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--counts',default='100,1000')
    args=parser.parse_args()
    fixture=Path(__file__).resolve().parents[1]/'helper_next/tests/fixtures/gnomad_v4/frequency_4.1.1.json'
    template=json.loads(fixture.read_text())['data']
    report=[]
    for count in map(int,args.counts.split(',')):
        calls=0
        def fetch(query,variables,timeout):
            nonlocal calls
            calls+=1
            data={}
            for name,identifier in variables.items():
                chrom,pos,ref,alt=identifier.split('-')
                for subset in ('all','non_ukb'):
                    variant=copy.deepcopy(template['v0_'+subset])
                    variant.update(variant_id=identifier,chrom=chrom,pos=int(pos),ref=ref,alt=alt)
                    data['v'+name[2:]+'_'+subset]=variant
            return {'data':data}
        with TemporaryDirectory(prefix='helper-gnomad-benchmark-') as directory:
            database=Path(directory)/'frequencies.sqlite3'
            alleles=[('GRCh38','1',1000+i,'G','T') for i in range(count)]
            with patch.object(g,'_request_graphql',fetch), patch.dict('os.environ',{'HELPER_GNOMAD_OFFLINE':'0'}):
                start=time.perf_counter();results=g.lookup_variants(alleles*3,database=database)
                cold=time.perf_counter()-start
                assert all(r['retrieval_status']=='FOUND' for r in results)
                del results
                after_cold=calls
                start=time.perf_counter();contexts=g.cached_contexts(alleles*3,database=database)
                warm=time.perf_counter()-start
                assert all('population_af' in result for result in contexts)
                assert calls==after_cold
            with sqlite3.connect(database) as connection:
                rows=connection.execute('SELECT COUNT(*) FROM frequencies').fetchone()[0]
            assert rows==count
            report.append(dict(unique_alleles=count,input_alleles=count*3,
                alias_batches=calls,cold_simulated_seconds=round(cold,4),
                warm_local_seconds=round(warm,4),cache_rows=rows,
                cache_bytes=database.stat().st_size,network_requests=0))
    print(json.dumps(dict(mode='offline_official_schema_fixture',results=report),indent=2))


if __name__=='__main__':
    main()
