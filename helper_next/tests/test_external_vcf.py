import gzip
import asyncio

import pytest

from helper_next.core import analysis_history, external_vcf
from helper_variants import indexer, query
from helper_next.api import variants as api
from fastapi import HTTPException


VCF = ("##fileformat=VCFv4.2\n"
       '##INFO=<ID=CSQ,Number=.,Type=String,Description="Format: SYMBOL|Allele|Feature|Consequence|HGVSc">\n'
       "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\tS2\n"
       "1\t100\t.\tA\tG,T\t60\tPASS\tCSQ=GENE|G|ENST1.1|missense_variant|c.1A>G,GENE|T|ENST2.2|stop_gained|c.1A>T\tGT:DP\t1/2:20\t0/1:30\n")


@pytest.mark.parametrize("compressed", [False, True])
def test_external_and_run_use_same_records_without_history(tmp_path, monkeypatch, compressed):
    monkeypatch.setenv("HELPER_EXTERNAL_VCF_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("HELPER_ANALYSIS_HISTORY_DB", str(tmp_path / "history.sqlite"))
    filename = "../../external.vcf" + (".gz" if compressed else "")
    identifier, path = external_vcf.allocate(filename)
    path.write_bytes(gzip.compress(VCF.encode()) if compressed else VCF.encode())
    source = external_vcf.finish(identifier, path, filename, "GRCh38")
    assert analysis_history.list_runs() == []
    assert source["run_id"].startswith("external.vcf")
    database = indexer.index_path(source["run_dir"])
    samples = query.list_samples(database)
    assert len(samples) == 2
    variants = query.list_variants(database, samples[0]["sample_id"])["items"]
    assert len(variants) == 2
    detail = query.variant_detail(database, samples[0]["sample_id"], variants[0]["variant_id"])
    assert len(detail["annotations"]) == 1
    assert detail["metadata"]["original_vcf"]["info"]["CSQ"]
    run_dir = tmp_path / "real-run"
    artifact = run_dir / "results/ANNOTATION/test.annotated.vcf"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(VCF)
    indexer.index_run({"run_dir": str(run_dir), "run_id": "real", "run_config": {"reference_version": "GRCh38"}})
    other = query.list_variants(indexer.index_path(run_dir), 1)["items"]
    assert [(v["position"], v["alternate"]) for v in variants] == [(v["position"], v["alternate"]) for v in other]


@pytest.mark.parametrize("content", [b"invalid", b"##fileformat=VCFv4.2\n", VCF.encode().replace(b"100", b"-1")])
def test_reject_malformed_vcf(tmp_path, content):
    path = tmp_path / "bad.vcf"
    path.write_bytes(content)
    with pytest.raises(ValueError):
        external_vcf.validate(path)


def test_compressed_expansion_limit_and_path_guard(tmp_path, monkeypatch):
    path = tmp_path / "bomb.vcf.gz"
    path.write_bytes(gzip.compress(VCF.encode()))
    monkeypatch.setattr(external_vcf, "MAX_EXPANDED", 64)
    with pytest.raises(ValueError, match="limit"):
        external_vcf.validate(path)
    with pytest.raises(ValueError):
        external_vcf.directory("external-../../escape")


def test_streamed_upload_api_size_limit_cleanup_and_shared_routes(tmp_path, monkeypatch):
    async def immediate(fn, *args):
        return fn(*args)
    monkeypatch.setattr(api, "run_in_threadpool", immediate)
    class Request:
        async def stream(self):
            yield VCF.encode()[:100]
            yield VCF.encode()[100:]
    uploaded = asyncio.run(api.upload_external_vcf(Request(), "safe.vcf", "GRCh38"))
    source_id = uploaded["source_id"]
    assert api.variant_samples(source_id)["samples"][0]["sample_id"] == 1
    assert api.variant_index_status(source_id)["status"] == "complete"
    assert analysis_history.list_runs() == []
    assert api.indexed_variant_runs()["runs"][0]["source_type"] == "EXTERNAL_UPLOAD"
    monkeypatch.setattr(external_vcf, "MAX_UPLOAD", 10)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.upload_external_vcf(Request(), "safe.vcf", "GRCh38"))
    assert exc.value.status_code == 413
    assert len(list(external_vcf.root().iterdir())) == 1  # Failed upload removed.


def test_ambiguous_minimized_deletions_do_not_mix_alts(tmp_path):
    vcf = VCF.split("#CHROM")[0] + (
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\n"
        "1\t100\t.\tATG\tA,AT\t60\tPASS\tCSQ=GENE|-|ENST1.1|frameshift_variant|c.1del\tGT\t1/2\n")
    identifier, path = external_vcf.allocate("ambiguous.vcf")
    path.write_text(vcf)
    source = external_vcf.finish(identifier, path, "ambiguous.vcf", "GRCh38")
    database = indexer.index_path(source["run_dir"])
    for variant in query.list_variants(database, 1)["items"]:
        detail = query.variant_detail(database, 1, variant["variant_id"])
        assert detail["annotations"] == []
        assert detail["metadata"]["original_vcf"]["info"]["CSQ"]


def test_explicit_vep_allele_number_disambiguates_deletions(tmp_path):
    vcf = (VCF.split("#CHROM")[0].replace("Consequence|HGVSc", "Consequence|HGVSc|ALLELE_NUM") +
           "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\n"
           "1\t100\t.\tATG\tA,AT\t60\tPASS\tCSQ=GENE|-|ENST1.1|frameshift_variant|c.1del|1,GENE|-|ENST2.1|inframe_deletion|c.2del|2\tGT\t1/2\n")
    identifier, path = external_vcf.allocate("numbered.vcf")
    path.write_text(vcf)
    source = external_vcf.finish(identifier, path, "numbered.vcf", "GRCh38")
    database = indexer.index_path(source["run_dir"])
    transcripts = []
    for variant in query.list_variants(database, 1)["items"]:
        detail = query.variant_detail(database, 1, variant["variant_id"])
        assert len(detail["annotations"]) == 1
        transcripts.append(detail["annotations"][0]["transcript"])
    assert set(transcripts) == {"ENST1.1", "ENST2.1"}
