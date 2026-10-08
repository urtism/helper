from pathlib import Path

import pytest

from helper_variants import igv


def _record(tmp_path, reference=None):
    return {
        "run_dir": str(tmp_path / "run"),
        "run_config": {
            "reference_version": "GRCh38",
            "reference_fasta": str(reference) if reference else "",
        },
    }


def test_manifest_prefers_indexed_preprocessed_alignment_and_local_reference(tmp_path):
    reference = tmp_path / "GRCh38.fa"
    reference.write_text(">chr1\nAAAA\n")
    Path(str(reference) + ".fai").write_text("chr1\t4\t6\t4\t5\n")
    record = _record(tmp_path, reference)
    results = Path(record["run_dir"]) / "results"
    alignment = results / "ALIGNMENT" / "S1.sort.bam"
    alignment.parent.mkdir(parents=True)
    alignment.write_bytes(b"aligned")
    Path(str(alignment) + ".bai").write_bytes(b"aligned-index")
    preprocessed = results / "PREPROCESSING" / "S1.preprocessed.bam"
    preprocessed.parent.mkdir(parents=True)
    preprocessed.write_bytes(b"preprocessed")
    Path(str(preprocessed) + ".bai").write_bytes(b"preprocessed-index")

    payload, resources = igv.manifest(record, {"display_name": "S1"})

    assert payload["available"] is True
    assert payload["tracks"][0]["stage"] == "preprocessed"
    assert resources["alignment"] == preprocessed.resolve()
    assert resources["alignment-index"] == Path(str(preprocessed) + ".bai").resolve()
    assert payload["reference"]["local"] is True
    assert payload["reference"]["contig_prefix"] == "chr"
    assert resources["reference"] == reference.resolve()


def test_manifest_reports_missing_alignment_index_without_exposing_the_path(tmp_path):
    record = _record(tmp_path)
    alignment = Path(record["run_dir"]) / "results" / "ALIGNMENT" / "S1.sort.bam"
    alignment.parent.mkdir(parents=True)
    alignment.write_bytes(b"bam")

    payload, resources = igv.manifest(record, {"display_name": "S1"})

    assert payload["available"] is True
    assert payload["alignment_available"] is False
    assert all(track["type"] != "alignment" for track in payload["tracks"])
    assert resources == {}
    assert "index is missing" in payload["warnings"][0]
    assert str(tmp_path) not in str(payload)


def test_manifest_adds_local_variant_and_panel_target_tracks(tmp_path):
    record = _record(tmp_path)
    target = tmp_path / "panel.bed"
    target.write_text("chr1\t0\t100\tEXON1\n")
    record["panel_design"] = {"assets": {"target_bed": str(target)}}
    results = Path(record["run_dir"]) / "results"
    alignment = results / "PREPROCESSING" / "S1.preprocessed.bam"
    alignment.parent.mkdir(parents=True)
    alignment.write_bytes(b"bam")
    Path(str(alignment) + ".bai").write_bytes(b"index")
    vcf = results / "ANNOTATION" / "S1.annotated.vcf.gz"
    vcf.parent.mkdir(parents=True)
    vcf.write_bytes(b"vcf")
    Path(str(vcf) + ".tbi").write_bytes(b"tabix")

    payload, resources = igv.manifest(record, {"display_name": "S1"})

    tracks = {track["id"]: track for track in payload["tracks"]}
    assert tracks["sample-alignment"]["stage"] == "preprocessed"
    assert tracks["split-read-evidence"]["mode"] == "split-reads"
    assert tracks["split-read-evidence"]["default_visible"] is False
    assert tracks["sample-variants"]["index_resource"] == "variants-index"
    assert tracks["panel-targets"]["format"] == "bed"
    assert tracks["refseq-transcripts"]["format"] == "refgene"
    assert tracks["refseq-transcripts"]["default_visible"] is True
    assert tracks["giab-difficult"]["url"].endswith("GRCh38_alldifficultregions.bb")
    assert tracks["clinvar-variants"]["index_url"].endswith("clinvar.vcf.gz.tbi")
    assert tracks["gnomad-regional"]["source_type"] == "custom"
    assert resources["variants"] == vcf.resolve()
    assert resources["variants-index"] == Path(str(vcf) + ".tbi").resolve()
    assert resources["targets"] == target.resolve()
    assert str(tmp_path) not in str(payload)


def test_manifest_does_not_offer_compressed_feature_without_tabix_index(tmp_path):
    record = _record(tmp_path)
    vcf = Path(record["run_dir"]) / "results" / "ANNOTATION" / "S1.annotated.vcf.gz"
    vcf.parent.mkdir(parents=True)
    vcf.write_bytes(b"not-indexed")

    payload, resources = igv.manifest(record, {"display_name": "S1"})

    assert all(track["id"] != "sample-variants" for track in payload["tracks"])
    assert "variants" not in resources


@pytest.mark.parametrize("name", ("../S1", "folder/S1", ""))
def test_manifest_rejects_unsafe_sample_names(tmp_path, name):
    with pytest.raises(igv.IgvResourceError):
        igv.manifest(_record(tmp_path), {"display_name": name})
