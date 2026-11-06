"""Small public-reference/synthetic nonsense cases; no patient data or live sources."""
import copy
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from helper_next.core.acmg_pvs1 import nonsense
from helper_next.core.acmg_transcripts import TranscriptReferenceProvider, mrna_to_genomic


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


def test_public_hbb_nonsense_reference_without_external_evaluator(tmp_path):
    public = json.loads((Path(__file__).parent / "fixtures/task25/hbb_ensembl_116.json").read_text())
    raw = public["raw"]

    def fetch(url):
        path, params = urlsplit(url).path, parse_qs(urlsplit(url).query)
        key = "release_before" if path == "/info/data" else "lookup" if "/lookup/" in path else "hgnc" if "/xrefs/" in path else params["type"][0]
        return raw[key]

    manager = TranscriptReferenceProvider(tmp_path / "public-cache", "116", fetch)
    source = manager.get("ENST00000335295.4", "GRCh38", fetch=True)
    assert source["data"] is not None, source
    facts = nonsense(public["variant"], public["annotation"], source["data"])
    assert (facts["reference_codon"], facts["altered_codon"]) == ("CAG", "TAG")
    assert facts["ptc_mrna_position"] == 168 and facts["ptc_genomic_position"] == 5226774
    assert facts["ptc_to_last_junction_nt"] == 197 and facts["ptc_to_last_junction_inclusive_nt"] == 198
