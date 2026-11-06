"""Lossless compact details, conditional reuse and lightweight source requests."""
import asyncio
import copy
import json
from pathlib import Path
import sqlite3

from fastapi import FastAPI, HTTPException
import httpx
import pytest

from helper_next.api import variants as api
from helper_next.core import acmg_context, variant_detail_cache
from helper_variants import query, store
from helper_variants.detail_transport import compact_detail
from test_biological_identity import reference_record
from test_clinvar_integration import install, at
from test_clinvar_local import submission
from test_sample_priority_loading import run_loading_js
from test_variant_query import query_store


def local_entry(tmp_path, monkeypatch):
    database, sample, other = query_store(tmp_path)
    record = dict(run_dir=str(tmp_path), **reference_record(tmp_path, {"1": "AAAAAAAAAAAA"}))
    monkeypatch.setattr(api, "_entry", lambda identifier: {"database": database, "record": record})
    monkeypatch.setattr(api, "_entry_database", lambda entry: database)
    return database, sample, other, record


def forbidden(*args, **kwargs):
    pytest.fail("A lightweight request must not rebuild the full variant detail")


def test_secondary_endpoints_read_only_the_sample_allele(tmp_path, monkeypatch):
    database, sample, other, _ = local_entry(tmp_path, monkeypatch)
    monkeypatch.setattr(query, "variant_detail", forbidden)
    monkeypatch.setattr(query, "_variant_detail", forbidden)
    monkeypatch.setattr(api, "LocalEvidence", forbidden)
    monkeypatch.setattr(api.liftover, "project_variant", lambda *args: {"allele": args})
    seen = []
    monkeypatch.setattr(api.gnomad_frequency, "lookup_variant", lambda *args, **kwargs:
                        seen.append((args, kwargs)) or {"status": "observed"})
    assert api.sample_variant_liftover("RUN", sample, 1)["allele"] == ("GRCh38", "1", 1, "A", "G")
    assert api.sample_variant_gnomad_frequency("RUN", sample, 1) == {"status": "observed"}
    assert seen[0][1]["metadata"] == query.variant_identity(database, sample, 1)["metadata"]
    assert len(api.sample_variant_carriers("RUN", sample, 1)["same_run"]) == 2
    assert query.variant_identity(database, other, 2) is None


@pytest.mark.parametrize("endpoint", [api.sample_variant_liftover, api.sample_variant_gnomad_frequency,
                                    api.sample_variant_carriers])
def test_lightweight_endpoints_still_require_sample_membership(tmp_path, monkeypatch, endpoint):
    _, _, other, _ = local_entry(tmp_path, monkeypatch)
    for sample, variant in ((other, 2), (999, 1)):
        with pytest.raises(HTTPException) as error:
            endpoint("RUN", sample, variant)
        assert error.value.status_code == 404


def test_submission_page_matches_full_api_without_annotations_or_priority(tmp_path, monkeypatch):
    _, sample, _, _ = local_entry(tmp_path, monkeypatch)
    install(tmp_path, monkeypatch, [at(1)], [submission(SCV=f"SCV{i:09d}.1") for i in range(1, 104)])
    expected = api.sample_variant_detail("RUN", sample, 1, submissions_offset=100)["clinvar_evidence"]
    monkeypatch.setattr(query, "variant_detail", forbidden)
    monkeypatch.setattr(query, "_variant_detail", forbidden)
    monkeypatch.setattr(query, "list_variants", forbidden)
    monkeypatch.setattr(api.acmg_context, "build", forbidden)
    assert api.sample_variant_submissions("RUN", sample, 1, limit=100, offset=100) == expected
    with pytest.raises(HTTPException) as error:
        api.sample_variant_submissions("RUN", sample, 999, limit=100, offset=0)
    assert error.value.status_code == 404


def test_compact_detail_roundtrips_exactly_in_browser_and_preserves_context_fingerprints(tmp_path, monkeypatch):
    _, sample, _, _ = local_entry(tmp_path, monkeypatch)
    install(tmp_path, monkeypatch, [at(1)])
    full = api.sample_variant_detail("RUN", sample, 1)
    resource = {"vep": {"version": "116", "source": "test"}}
    context = dict(gene={"identifier": "HGNC:1"}, disease={"identifier": "MONDO:1"}, inheritance_modes=[])
    origin = {"assertions": [{"id": "curated", "evidence": "source-specific evidence"}]}
    for annotation in full["annotations"]:
        annotation["release_resources"] = copy.deepcopy(resource)
    catalog = dict(schema_version="test", annotations=[])
    for index, annotation in enumerate(full["annotations"]):
        catalog["annotations"].append(dict(annotation_id=annotation["id"], transcript=annotation["transcript"],
            contexts=[dict(id=f"context-{index}", context=copy.deepcopy(context), origin=copy.deepcopy(origin),
                           fingerprint={"algorithm": "sha256", "value": str(index) * 64})]))
    full["interpretation_context"] = catalog
    before = copy.deepcopy(full)
    wire = compact_detail(full)
    assert full == before, "Transport packing cannot mutate the standard API result"
    assert len(wire["shared"]) == 3
    run_loading_js("const expected=" + json.dumps(full) + "; const wire=" + json.dumps(wire) + r''';
      const restored=viewer.expandVariantDetail(wire);
      assert.deepEqual(restored,expected);
      assert.strictEqual(restored.annotations[0].release_resources,restored.annotations[1].release_resources);
      assert.strictEqual(viewer.expandVariantDetail(expected),expected,'Legacy responses remain supported');
      wire.detail.annotations[0].release_resources=999;
      assert.throws(()=>viewer.expandVariantDetail(wire),/Invalid compact/);
    ''')
    first = catalog["annotations"][0]
    selected, choice = acmg_context.select(catalog, first["annotation_id"], first["transcript"], "context-0", "0" * 64)
    assert selected == context and choice["origin"] == origin


def test_http_detail_reuses_unchanged_response_without_recalculating(tmp_path, monkeypatch):
    database, sample, _, _ = local_entry(tmp_path, monkeypatch)
    install(tmp_path, monkeypatch, [at(1)])
    from test_clingen_vcep_integration import dataset
    dataset(tmp_path)
    monkeypatch.setattr(variant_detail_cache.time, "time", lambda: 1800000000)
    app = FastAPI()
    app.include_router(api.router)
    def get(path, **kwargs):
        async def perform():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                return await client.get(path, **kwargs)
        return asyncio.run(perform())
    path = f"/api/variants/runs/RUN/samples/{sample}/variants/1?compact=true"
    first = get(path)
    assert first.status_code == 200
    assert first.json()["format"] == "helper-variant-detail-compact-v1"
    assert "etag" in first.headers
    original = api._sample_variant_detail
    monkeypatch.setattr(api, "_sample_variant_detail", forbidden)
    second = get(path, headers={"If-None-Match": first.headers["etag"]})
    assert second.status_code == 304 and second.content == b""
    assert second.headers["cache-control"] == "private, no-cache"
    weak = get(path, headers={"If-None-Match": '"other",' + first.headers["etag"].removeprefix("W/")})
    assert weak.status_code == 304
    missing = get(path.replace("/variants/1?", "/variants/999?"), headers={"If-None-Match": first.headers["etag"]})
    assert missing.status_code == 404
    monkeypatch.setattr(api, "_sample_variant_detail", original)
    with store.connect(database) as connection:
        connection.execute("UPDATE variants SET metadata_json='{}' WHERE id=1")
    updated = get(path, headers={"If-None-Match": first.headers["etag"]})
    assert updated.status_code == 200
    assert updated.headers["etag"] != first.headers["etag"]


def test_source_errors_are_not_cached_as_healthy_details(tmp_path, monkeypatch):
    from fastapi import Request, Response

    _, sample, _, _ = local_entry(tmp_path, monkeypatch)
    response = Response()
    detail = api.sample_variant_detail("RUN", sample, 1,
                                      request=Request({"type": "http", "headers": []}), response=response)
    assert detail["clinvar_evidence"]["matching_status"] == "ERROR"
    assert "etag" not in response.headers


@pytest.mark.parametrize("change", ["run_wal", "gnomad", "clinvar", "vcep", "gene", "fasta", "fai", "profile", "representation", "freshness"])
def test_detail_validator_tracks_evidence_reference_and_representation(tmp_path, monkeypatch, change):
    database, sample, _, record = local_entry(tmp_path, monkeypatch)
    clock = [1800000000]
    monkeypatch.setattr(variant_detail_cache.time, "time", lambda: clock[0])
    identity = query.variant_identity(database, sample, 1)
    options = {}
    token = lambda: variant_detail_cache.detail_etag(database, record, identity, sample, 1, **options)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        before = token()
        main_stat = database.stat()
        if change == "run_wal":
            connection.execute("UPDATE variants SET metadata_json='{}' WHERE id=1")
            connection.commit()
            assert database.stat().st_mtime_ns == main_stat.st_mtime_ns
        elif change in ("gnomad", "clinvar", "vcep", "gene"):
            source = {"gnomad": variant_detail_cache.gnomad_frequency.cache_path,
                      "clinvar": variant_detail_cache.clinvar_local.database_path,
                      "vcep": variant_detail_cache.clingen_vcep_local.database_path,
                      "gene": variant_detail_cache.gene_phenotype.cache_path}[change]()
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("new source revision")
        elif change in ("fasta", "fai"):
            path = Path(record["run_config"]["reference_fasta"] + (".fai" if change == "fai" else ""))
            path.write_text(path.read_text() + "\n")
        elif change == "profile":
            options["scoring_version"] = "other-profile"
        elif change == "representation":
            options["compact"] = True
        else:
            clock[0] += 60
        assert token() != before


def test_browser_conditional_request_uses_cache_and_accepts_updated_response():
    run_loading_js(r'''
      const cache={}; let calls=0; const original=global.fetch;
      global.fetch=async(url,options)=>{
        calls++;
        assert(!('responseCache' in options),'Internal cache state must not be sent to fetch');
        if(calls===1) return new Response(JSON.stringify({value:1}),{headers:{ETag:'"one"'}});
        assert.equal(options.headers.get('If-None-Match'),'"one"');
        if(calls===2) return new Response(null,{status:304,headers:{ETag:'"one"'}});
        return new Response(JSON.stringify({value:2}),{headers:{ETag:'"two"'}});
      };
      try {
        assert.deepEqual(await viewer.request('/detail',{responseCache:cache}),{value:1});
        assert.deepEqual(await viewer.request('/detail',{responseCache:cache}),{value:1});
        assert.deepEqual(await viewer.request('/detail',{responseCache:cache}),{value:2});
        assert.equal(cache.etag,'"two"');
      } finally {global.fetch=original;}
    ''')


def test_browser_ignores_outdated_detail_and_bounds_cache():
    run_loading_js(r'''
      global.window={clearTimeout};
      viewer.loadLiftover=viewer.loadCarriers=viewer.loadGenePhenotypes=viewer.loadGnomadFrequency=()=>{};
      const responses=[];
      viewer.request=(url,options)=>new Promise(resolve=>responses.push({url,options,resolve}));
      const first=viewer.loadDetail(workspace,1);
      const second=viewer.loadDetail(workspace,2);
      responses[1].resolve({variant_id:2,annotations:[]}); await second;
      responses[0].resolve({variant_id:1,annotations:[]}); await first;
      assert.equal(workspace.detail.variant_id,2,'Late responses cannot replace the current variant');
      viewer.request=async()=>({annotations:[]});
      for(let id=3;id<=12;id++) await viewer.loadDetail(workspace,id);
      assert.equal(workspace.detailCache.size,8);
      assert(!workspace.detailCache.has(1));
    ''')


@pytest.mark.parametrize("method,field", [("loadLiftover", "liftover"),
    ("loadGnomadFrequency", "gnomadFrequency"), ("loadCarriers", "carriers"),
    ("loadGenePhenotypes", "genePhenotypes")])
def test_superseded_source_requests_cannot_overwrite_the_same_variant(method, field):
    run_loading_js("const method=" + json.dumps(method) + ";const field=" + json.dumps(field) + r''';
      global.window={clearTimeout,setTimeout};
      viewer.renderDetailSection=()=>{};
      viewer.genePhenotypeGenes=()=>[{symbol:'G'}];
      workspace.detail={variant_id:1,annotations:[]};
      const responses=[];
      viewer.request=()=>new Promise(resolve=>responses.push(resolve));
      const first=viewer[method](workspace,1);
      const second=viewer[method](workspace,1);
      responses[1]({marker:'current',cache:{status:'ready'}});await second;
      responses[0]({marker:'outdated',cache:{status:'ready'}});await first;
      const result=workspace.detail[field];
      assert.equal((Array.isArray(result)?result[0]:result).marker,'current');
    ''')
