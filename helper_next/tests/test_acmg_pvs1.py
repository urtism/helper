"""Small public-reference/synthetic nonsense cases; no patient data or live sources."""
import copy
import io
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from helper_next.core.acmg_evidence import EvidenceCoordinator, gene_disease_candidates
from helper_next.core.acmg_pvs1 import nonsense, transform
from helper_next.core.acmg_sources import SourceManager
from helper_next.core.acmg_task22 import Task22Client
from helper_next.core.acmg_transcripts import TranscriptReferenceProvider, qualify, mrna_to_genomic
from helper_next.core.acmg_workbench import prepare
from helper_variants import gene_phenotype, indexer, query, store
from test_acmg_evidence import engine, PROTOCOL, ENGINE
from test_gene_phenotype import HEADER
from test_variant_indexer import write_vcf, record


@pytest.fixture(autouse=True)
def offline_transcript_sources(monkeypatch, tmp_path):
    monkeypatch.setenv("HELPER_TRANSCRIPT_FETCH", "0")
    monkeypatch.setenv("HELPER_TRANSCRIPT_CACHE", str(tmp_path / "default-transcripts"))


def bundle(strand="+"):
    cds = "ATG" + "CAA" * 8 + "TAA"
    cdna = "CC" + cds + "GG"
    intervals = [(101, 112), (201, 212), (301, 310)] if strand == "+" else [(301, 312), (201, 212), (101, 110)]
    exons, cursor = [], 1
    for i, (start, end) in enumerate(intervals):
        exons.append({"id": "EX" + str(i), "start": start, "end": end, "assembly_name": "GRCh38",
                      "seq_region_name": "1", "strand": 1 if strand == "+" else -1,
                      "exon_id": "EX" + str(i), "genomic_start": start, "genomic_end": end,
                      "mrna_start": cursor, "mrna_end": cursor + end - start})
        cursor += end - start + 1
    ends = [mrna_to_genomic(exons, strand, p) for p in (3, 32)]
    return {"release_before": {"releases": [115]}, "release_after": {"releases": [115]},
            "lookup": {"id": "ENST000001", "version": 1, "assembly_name": "GRCh38", "species": "homo_sapiens",
                       "object_type": "Transcript", "seq_region_name": "1", "strand": 1 if strand == "+" else -1,
                       "Exon": exons, "Translation": {"id": "ENSP000001", "start": min(ends), "end": max(ends), "length": 9},
                       "Parent": "ENSG000001", "biotype": "protein_coding", "length": len(cdna),
                       "MANE": [{"type": "MANE_Select"}]},
            "cdna": {"id": "ENST000001", "seq": cdna}, "cds": {"id": "ENST000001", "seq": cds},
            "protein": {"id": "ENSP000001", "seq": "M" + "Q" * 8},
            "hgnc": [{"dbname": "HGNC", "primary_id": "HGNC:1"}]}


def provider(tmp_path, raw):
    calls = []

    def fetch(url):
        calls.append(url)
        path, params = urlsplit(url).path, parse_qs(urlsplit(url).query)
        name = "release_before" if path == "/info/data" else "lookup" if "/lookup/" in path else "hgnc" if "/xrefs/" in path else params["type"][0]
        return copy.deepcopy(raw[name])

    return TranscriptReferenceProvider(tmp_path / "transcripts", "115", fetch), calls


def source(tmp_path, raw):
    manager, _ = provider(tmp_path, raw)
    return manager.get("ENST000001.1", "GRCh38", fetch=True)


def case(reference, coding_position=4):
    position = mrna_to_genomic(reference["exons"], reference["strand"], reference["cds_start"] + coding_position - 1)
    ref, alt = ("C", "T") if reference["strand"] == "+" else ("G", "A")
    identity = {"assembly": "GRCh38", "chromosome": "1", "position": position, "reference": ref, "alternate": alt}
    annotation = {"id": 1, "gene": "DEMO", "transcript": "ENST000001.1", "consequence": "stop_gained",
                  "hgvsc": f"c.{coding_position}C>T", "hgvsp": "p.GlnTer", "metadata": {"fields": {"HGNC_ID": "HGNC:1"}}}
    return identity, annotation


CONTEXT = {"gene": {"namespace": "HGNC", "identifier": "HGNC:1"},
           "disease": {"namespace": "MONDO", "identifier": "MONDO:1"}, "inheritance_modes": ["AUTOSOMAL_DOMINANT"]}


def document(tmp_path, monkeypatch, reference, coding_position=4, from_vcf=False, public=None):
    identity, annotation = (public["variant"], public["annotation"]) if public else case(reference, coding_position)
    context = ({**CONTEXT, "gene": {"namespace": "ENSEMBL", "identifier": "ENSEMBL:ENSG00000244734"}}
               if public else CONTEXT)
    genome = ["N"] * (max(e["genomic_end"] for e in reference["exons"]) + 90)
    for exon in reference["exons"]:
        seq = reference["cdna"][exon["mrna_start"] - 1:exon["mrna_end"]]
        if reference["strand"] == "-":
            from helper_next.core.acmg_transcripts import complement
            seq = complement(seq)
        genome[exon["genomic_start"] - 1:exon["genomic_end"]] = seq
    fasta = tmp_path / "reference.fa"
    chromosome = identity["chromosome"]
    fasta.write_text(">" + chromosome + "\n" + "".join(genome) + "\n")
    Path(str(fasta) + ".fai").write_text(f"{chromosome}\t{len(genome)}\t{len(chromosome) + 2}\t{len(genome)}\t{len(genome) + 1}\n")
    config = tmp_path / "reference.json"
    config.write_text(json.dumps({"GRCh38": {"fasta": str(fasta), "version": "synthetic-25"}}))
    monkeypatch.setenv("HELPER_ACMG_REFERENCE_CONFIG", str(config))
    detail = {"reference_build": "GRCh38", **{k: v for k, v in identity.items() if k != "assembly"},
              "metadata": {}, "annotations": [annotation]}
    if from_vcf:
        write_vcf(tmp_path / "run/results/ANNOTATION/S1.annotated.vcf",
                  f"{chromosome}\t{identity['position']}\t.\t{identity['reference']}\t{identity['alternate']}\t60\tPASS\t"
                  f"ANN={identity['alternate']}|stop_gained|HIGH|DEMO|{context['gene']['identifier']}|transcript|{annotation['transcript']}|protein_coding|1/3|{annotation['hgvsc']}|{annotation['hgvsp']}\tGT\t0/1\n")
        indexer.index_run(record(tmp_path / "run"))
        database = indexer.index_path(tmp_path / "run")
        with store.connect(database) as db:
            sample = db.execute("SELECT id FROM samples LIMIT 1").fetchone()[0]
            variant = db.execute("SELECT id FROM variants LIMIT 1").fetchone()[0]
        detail = query.variant_detail(database, sample, variant)
    return prepare(detail, {"source_id": "synthetic-25"}, context, annotation["transcript"], "GRCh38")


@pytest.mark.parametrize("strand", ["+", "-"])
def test_targeted_provider_versioned_cache_and_sequence_checks(tmp_path, strand):
    raw = bundle(strand)
    manager, calls = provider(tmp_path, raw)
    assert manager.get("ENST000001.1", "GRCh38")["data"] is None and not calls
    result = manager.get("ENST000001.1", "GRCh38", fetch=True)
    assert result["data"] is not None, result
    assert len(calls) == 7
    ref = result["data"]
    assert ref["cds_start"] == 3 and ref["cds_end"] == 32 and ref["protein_length"] == 9
    assert len(ref["coding_segments"]) == 3 and ref["mane"] == "SELECT"
    assert [j["mrna_position"] for j in ref["junctions"]] == [12, 24]
    assert manager.get("ENST000001.1", "GRCh38") == result and len(calls) == 7
    assert manager.get("ENST000001.2", "GRCh38")["data"] is None
    path = next((tmp_path / "transcripts").glob("*.json"))
    bad = json.loads(path.read_text())
    bad["raw"]["cds"]["seq"] = "AAA"
    path.write_text(json.dumps(bad))
    assert "checksum" in manager.get("ENST000001.1", "GRCh38")["missing"]


@pytest.mark.parametrize("strand,coding,ptc,distance", [("+", 4, 6, 18), ("-", 4, 6, 18),
                                                       ("+", 10, 12, 12), ("-", 10, 12, 12),
                                                       ("+", 25, 27, None), ("-", 25, 27, None)])
def test_verified_nonsense_junction_and_terminal_exon(tmp_path, strand, coding, ptc, distance):
    ref = source(tmp_path, bundle(strand))["data"]
    identity, annotation = case(ref, coding)
    facts = nonsense(identity, annotation, ref)
    assert facts["reference_codon"] == "CAA" and facts["altered_codon"] == "TAA"
    assert facts["ptc_mrna_position"] == ptc
    assert facts["ptc_to_last_junction_nt"] == distance
    assert facts["ptc_genomic_position"] == mrna_to_genomic(ref["exons"], strand, ptc)
    if coding == 10:
        assert facts["ptc_to_next_junction_nt"] == 0
    if coding == 25:
        assert facts["junction"] is None
    assert not any(k in facts for k in ("nmd", "strength", "activation"))


@pytest.mark.parametrize("change", ["transcript", "assembly", "ref", "nonstop", "outside", "gene"])
def test_wrong_identity_or_unconfirmed_stop_never_produces_ptc(tmp_path, change):
    src = source(tmp_path, bundle())
    identity, annotation = case(src["data"])
    if change == "transcript":
        annotation["transcript"] = "ENST000001.2"
    elif change == "assembly":
        identity["assembly"] = "GRCh37"
    elif change == "ref":
        identity["reference"] = "G"
    elif change == "nonstop":
        identity["alternate"] = "A"
    elif change == "outside":
        identity["position"] = 150
    context = {**CONTEXT, "gene_disease": {"inheritance_modes": CONTEXT["inheritance_modes"]}}
    if change == "gene":
        context["gene"] = {"namespace": "HGNC", "identifier": "HGNC:2"}
    result = transform(identity, annotation, context, src, [])
    assert result["status"] == "INCOMPLETE"
    assert result["evidence"]["observation"]["transcript_effects"] == []
    assert result["original"]["calculation"] is None


@pytest.mark.parametrize("missing", ["Translation", "cds", "release", "version"])
def test_unqualified_transcript_or_cds_is_incomplete(tmp_path, missing):
    raw = bundle()
    if missing == "release":
        raw["release_before"] = {"releases": [114]}
    elif missing == "version":
        raw["lookup"]["version"] = 2
    elif missing == "Translation":
        del raw["lookup"][missing]
    else:
        raw["cds"]["seq"] = ""
    result = source(tmp_path, raw)
    assert result["data"] is None and result["status"] == "ERROR" and result["missing"]


@pytest.mark.parametrize("consequence", [
    "frameshift_variant", "splice_donor_variant", "splice_acceptor_variant",
    "splice_region_variant", "start_lost", "exon_loss_variant", "transcript_amplification",
])
@pytest.mark.parametrize("has_reference", [True, False])
def test_annotated_technical_classes_remain_incomplete_without_qualified_effect(tmp_path, consequence, has_reference):
    """Annotation-only fixtures establish missing-data handling, not class coverage."""
    src = source(tmp_path, bundle())
    identity, annotation = case(src["data"])
    annotation["consequence"] = consequence
    if not has_reference:
        src = {"data": None, "missing": "Qualified transcript/CDS unavailable"}
    context = {**CONTEXT, "gene_disease": {"inheritance_modes": CONTEXT["inheritance_modes"]}}
    result = transform(identity, annotation, context, src, [])
    assert result["status"] == "INCOMPLETE"
    assert result["evidence"]["observation"]["transcript_effects"] == []
    assert result["evidence"]["observation"]["structural"] is None
    assert result["original"]["calculation"] is None
    assert result["original"]["technical_consequence"] == consequence
    assert bool(result["original"]["technical_context"]) == has_reference
    reasons = " ".join(m["reason"] for m in result["missing_evidence"])
    assert "annotation" in reasons.lower()
    if not has_reference:
        assert "Qualified transcript/CDS unavailable" in reasons


@pytest.mark.parametrize("strand", ["+", "-"])
def test_vcf_to_coordinator_and_real_engine_contract(tmp_path, monkeypatch, engine, strand):
    manager, _ = provider(tmp_path, bundle(strand))
    src = manager.get("ENST000001.1", "GRCh38", fetch=True)
    doc = document(tmp_path, monkeypatch, src["data"], from_vcf=True)
    before = copy.deepcopy(doc)
    result = EvidenceCoordinator(engine, SourceManager(transcript_provider=manager)).build(doc, PROTOCOL)
    assert not result["errors"], result["errors"]
    assert before == doc
    envelope = next(e for e in result["contract"]["evidence"] if e["value"]["kind"] == "PVS1")
    obs = envelope["value"]["observation"]
    assert obs["transcript_effects"][0]["consequence"]["ptc_mrna_position"] == 6
    assert obs["mechanism"]["lof_established"] == "UNKNOWN" and obs["mechanism"]["mechanisms"] == []
    assert envelope["validation_status"] == "UNVERIFIED" and envelope["quality_status"] == "UNKNOWN"
    assert json.loads(envelope["received_json"])["calculation"]["altered_codon"] == "TAA"
    assert envelope["transformations"][0]["software_version"] == "helper-nonsense-1.0"
    assert result["transformers"][0]["status"] == "TECHNICALLY_VERIFIED"
    assert any("mechanism" in m["path"] for m in result["missing_evidence"])


def test_missing_transcript_still_validates_incomplete_pvs1(tmp_path, monkeypatch, engine):
    ref = source(tmp_path, bundle())["data"]
    doc = document(tmp_path, monkeypatch, ref)
    manager = TranscriptReferenceProvider(tmp_path / "empty", "115")
    result = EvidenceCoordinator(engine, SourceManager(transcript_provider=manager)).build(doc, PROTOCOL)
    assert not result["errors"]
    obs = next(e["value"]["observation"] for e in result["contract"]["evidence"] if e["value"]["kind"] == "PVS1")
    assert obs["transcript_effects"] == []
    assert result["transformers"][0]["status"] == "INCOMPLETE"


def test_g2p_only_disease_and_conflicts_are_independent_of_gencc(tmp_path):
    rows = ("g2p id,gene symbol,hgnc id,disease name,disease MONDO,allelic requirement,confidence,molecular mechanism\n"
            "G2P-1,DEMO,HGNC:1,Only G2P,MONDO:1,monoallelic_autosomal,strong,loss of function\n"
            "G2P-2,DEMO,HGNC:1,Only G2P,MONDO:1,biallelic,strong,gain of function\n")
    database = tmp_path / "gene.sqlite"
    gene_phenotype.build_cache(io.StringIO(HEADER), database, g2p_stream=io.StringIO(rows))
    raw = SourceManager(gene_database=database).gene_disease("DEMO", "HGNC:1")["data"]
    assert raw["associations"] == [] and len(raw["g2p_records"]) == 2
    candidates, originals = gene_disease_candidates(raw, CONTEXT, "2026-01-01T00:00:00Z")
    assert [c["id"] for c in candidates] == ["helper-g2p-candidates"]
    retained = originals["helper-g2p-candidates"]["records"]
    assert {r["mechanism"] for r in retained} == {"loss of function", "gain of function"}
    assert all(r["confidence"] == "strong" for r in retained)
    assert originals["helper-g2p-candidates"]["divergent_records_require_review"] is True


@pytest.mark.parametrize("protocol", ["ACMG_2015", "CLINGEN_GENERAL"])
def test_public_hbb_reference_vcf_through_real_pvs1_engine(tmp_path, monkeypatch, engine, protocol):
    public = json.loads((Path(__file__).parent / "fixtures/task25/hbb_ensembl_116.json").read_text())
    raw = public["raw"]

    def fetch(url):
        path, params = urlsplit(url).path, parse_qs(urlsplit(url).query)
        key = "release_before" if path == "/info/data" else "lookup" if "/lookup/" in path else "hgnc" if "/xrefs/" in path else params["type"][0]
        return raw[key]

    manager = TranscriptReferenceProvider(tmp_path / "public-cache", "116", fetch)
    src = manager.get("ENST00000335295.4", "GRCh38", fetch=True)
    assert src["data"] is not None, src
    doc = document(tmp_path, monkeypatch, src["data"], from_vcf=True, public=public)
    result = EvidenceCoordinator(engine, SourceManager(transcript_provider=manager)).build(doc, PROTOCOL)
    assert not result["errors"], result["errors"]
    item = next(e for e in result["contract"]["evidence"] if e["value"]["kind"] == "PVS1")
    facts = json.loads(item["received_json"])["calculation"]
    assert (facts["reference_codon"], facts["altered_codon"]) == ("CAG", "TAG")
    assert facts["ptc_mrna_position"] == 168 and facts["ptc_genomic_position"] == 5226774
    assert facts["ptc_to_last_junction_nt"] == 197 and facts["ptc_to_last_junction_inclusive_nt"] == 198
    # Invoke the actual scientific service in its existing Pydantic runtime.
    script = """
import json,sys
from acmg_engine.domain.criteria_protocol import CriteriaEvaluationRequest
from acmg_engine.services.criteria_protocols import CriteriaProtocolService
request = CriteriaEvaluationRequest.model_validate(json.load(sys.stdin))
result = CriteriaProtocolService(allow_research=True).evaluate(request)
row = next(r for r in result.criteria if r.criterion_id == 'PVS1')
print(row.model_dump_json())
"""
    executable = os.environ.get("HELPER_TEST_ENGINE_PYTHON", str(ENGINE / ".venv/bin/python"))
    process = subprocess.run([executable, "-c", script],
                             input=json.dumps({"evidence": result["contract"], "protocol": dict(PROTOCOL, protocol=protocol)}),
                             capture_output=True, text=True, timeout=30, env=dict(os.environ, PYTHONPATH=str(ENGINE / "src")))
    assert process.returncode == 0, process.stderr
    row = json.loads(process.stdout)
    assert row["activation_status"] == "INACTIVE" and row["assigned_strength"] is None
    assert row["pvs1_evaluation"]["mechanism_confidence"] == "UNKNOWN"
    assert row["execution"] and row["rationale"]


@pytest.mark.skipif(os.environ.get("HELPER_TEST_TASK25_SERVICE") != "1", reason="Opt-in existing local engine REST service")
def test_existing_local_rest_pvs1(tmp_path, monkeypatch):
    manager, _ = provider(tmp_path, bundle("-"))
    src = manager.get("ENST000001.1", "GRCh38", fetch=True)
    doc = document(tmp_path, monkeypatch, src["data"], from_vcf=True)
    result = EvidenceCoordinator(Task22Client(), SourceManager(transcript_provider=manager)).build(doc, PROTOCOL)
    assert not result["errors"]
    assert any(e["value"]["kind"] == "PVS1" for e in result["contract"]["evidence"])
