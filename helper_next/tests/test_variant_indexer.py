import gzip
import json
from pathlib import Path

import pytest

from helper_variants import indexer as variant_indexer
from helper_variants import store as variant_store


ANN_HEADER = (
    "##INFO=<ID=ANN,Number=.,Type=String,Description=\"Functional annotations: "
    "'Allele | Annotation | Annotation_Impact | Gene_Name | Gene_ID | Feature_Type | "
    "Feature_ID | Transcript_BioType | Rank | HGVS.c | HGVS.p'\">\n"
)


def write_vcf(path, body, samples=("S1",)):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "##fileformat=VCFv4.2\n" + ANN_HEADER
    text += "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT"
    if samples:
        text += "\t" + "\t".join(samples)
    text += "\n" + body
    if str(path).endswith(".gz"):
        with gzip.open(str(path), "wt") as handle:
            handle.write(text)
    else:
        path.write_text(text)
    return path


def record(run_dir, samples=None):
    return {
        "id": "history-1", "run_id": "RUN-1", "run_dir": str(run_dir),
        "run_config": {"reference_version": "GRCh38"},
        "samples": samples or [{"sample_name": "S1", "role": "proband", "specimen_type": "blood"}],
    }


def test_discovery_prefers_annotation_and_ignores_gvcf(tmp_path):
    write_vcf(tmp_path / "results/VARIANTCALLING/S1.vcf", "")
    write_vcf(tmp_path / "results/ANNOTATION/S1.annotated.vcf", "")
    write_vcf(tmp_path / "results/ANNOTATION/S1.g.vcf", "")

    artifacts = variant_indexer.discover_run_vcfs(tmp_path)

    assert [(item["stage"], item["path"].name) for item in artifacts] == [
        ("annotation", "S1.annotated.vcf")
    ]


def test_indexes_multiallelic_calls_and_structured_ann_without_loading_whole_file(tmp_path):
    body = (
        "1\t100\trs1\tAA\tAG,AT\t60\tPASS\t"
        "ANN=AG|missense_variant|MODERATE|GENE1|G1|transcript|TX1|protein_coding|1/2|c.1A>G|p.K1R,"
        "AT|stop_gained|HIGH|GENE1|G1|transcript|TX2|protein_coding|2/2|c.2A>T|p.K2*\t"
        "GT:DP:AD:AF:GQ\t1/2:20:10,4,6:0.2,0.3:99\t0/0:22:22,0,0:0,0:80\n"
        "2\t200\t.\tG\tC\t50\tq10\tANN=C|intron_variant|MODIFIER|GENE2|G2|transcript|TX3|protein_coding|1/1|||\t"
        "GT:DP:AD:GQ\t0/1:18:9,9:70\t./.:.:.:.\n"
    )
    write_vcf(
        tmp_path / "results/ANNOTATION/S1.annotated.vcf.gz", body, ("S1", "S2")
    )

    result = variant_indexer.index_run(record(tmp_path, [
        {"sample_name": "S1", "role": "proband"},
        {"sample_name": "S2", "role": "mother"},
    ]), batch_size=1)

    assert result["status"] == "complete"
    assert result["sources"][0]["records_processed"] == 2
    with variant_store.connect(variant_indexer.index_path(tmp_path)) as db:
        variants = db.execute(
            "SELECT chromosome, position, reference, alternate FROM variants ORDER BY chromosome, alternate"
        ).fetchall()
        assert [tuple(row) for row in variants] == [
            ("1", 101, "A", "G"), ("1", 101, "A", "T"), ("2", 200, "G", "C")
        ]
        assert db.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 3
        assert db.execute("SELECT COUNT(*) FROM annotations").fetchone()[0] == 3
        call = db.execute(
            "SELECT c.genotype, c.depth, c.alternate_depth, c.allele_fraction, c.zygosity "
            "FROM calls c JOIN variants v ON v.id = c.variant_id WHERE v.alternate = 'T'"
        ).fetchone()
        assert tuple(call) == ("1/2", 20, 6, 0.3, "het")
        annotation = db.execute(
            "SELECT gene, transcript, consequence, impact, hgvsc, hgvsp FROM annotations "
            "WHERE consequence = 'stop_gained'"
        ).fetchone()
        assert tuple(annotation) == ("GENE1", "TX2", "stop_gained", "HIGH", "c.2A>T", "p.K2*")


def test_repeated_index_is_a_noop_and_changed_source_requires_rebuild(tmp_path):
    path = write_vcf(
        tmp_path / "results/ANNOTATION/S1.annotated.vcf",
        "1\t10\t.\tA\tG\t40\tPASS\tANN=G|missense_variant|MODERATE|GENE||||TX||||\tGT\t0/1\n",
    )
    first = variant_indexer.index_run(record(tmp_path))
    second = variant_indexer.index_run(record(tmp_path))
    assert first["sources"][0]["skipped"] is False
    assert second["sources"][0]["skipped"] is True

    path.write_text(path.read_text() + "2\t20\t.\tC\tT\t30\tPASS\t.\tGT\t0/1\n")
    with pytest.raises(variant_indexer.SourceChangedError, match="rebuild is required"):
        variant_indexer.index_run(record(tmp_path))


def test_history_attempts_for_same_directory_reuse_one_physical_run(tmp_path):
    write_vcf(
        tmp_path / "results/ANNOTATION/S1.annotated.vcf",
        "1\t10\t.\tA\tG\t40\tPASS\t.\tGT\t0/1\n",
    )
    first_record = record(tmp_path)
    second_record = dict(first_record, id="history-2")

    first = variant_indexer.index_run(first_record)
    second = variant_indexer.index_run(second_record)

    assert first["sources"][0]["skipped"] is False
    assert second["sources"][0]["skipped"] is True
    with variant_store.connect(variant_indexer.index_path(tmp_path)) as db:
        assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 1


def test_status_reports_persisted_failure_and_checkpoint(tmp_path):
    path = write_vcf(
        tmp_path / "results/ANNOTATION/S1.annotated.vcf",
        "1\t10\t.\tA\tG\t40\tPASS\t.\tGT\t0/1\ninvalid\n",
    )
    with pytest.raises(variant_indexer.VariantIndexError, match="invalid VCF record"):
        variant_indexer.index_run(record(tmp_path), batch_size=1)

    status = variant_indexer.index_status(tmp_path)
    assert status["status"] == "failed"
    assert status["sources"][0]["records_processed"] == 1
    assert "invalid VCF record" in status["sources"][0]["error"]
    assert path.is_file()


def test_incomplete_source_resumes_after_its_persisted_checkpoint(tmp_path):
    write_vcf(
        tmp_path / "results/ANNOTATION/S1.annotated.vcf",
        "1\t10\t.\tA\tG\t40\tPASS\t.\tGT\t0/1\n"
        "2\t20\t.\tC\tT\t30\tPASS\t.\tGT\t0/1\n",
    )
    variant_indexer.index_run(record(tmp_path), batch_size=1)
    database = variant_indexer.index_path(tmp_path)
    with variant_store.connect(database) as db:
        second = db.execute("SELECT id FROM variants WHERE chromosome = '2'").fetchone()[0]
        db.execute("DELETE FROM calls WHERE variant_id = ?", (second,))
        db.execute("DELETE FROM annotations WHERE variant_id = ?", (second,))
        db.execute("DELETE FROM variants WHERE id = ?", (second,))
        db.execute("UPDATE index_sources SET status = 'failed', records_processed = 1")

    result = variant_indexer.index_run(record(tmp_path), batch_size=1)

    assert result["sources"][0]["records_processed"] == 2
    with variant_store.connect(database) as db:
        assert db.execute("SELECT COUNT(*) FROM variants").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 2


def test_reads_csq_layout_declared_by_the_vcf_header(tmp_path):
    path = tmp_path / "results/ANNOTATION/S1.annotated.vcf"
    path.parent.mkdir(parents=True)
    path.write_text(
        "##fileformat=VCFv4.2\n"
        "##INFO=<ID=CSQ,Number=.,Type=String,Description=\"Consequence annotations. Format: "
        "Allele|Consequence|IMPACT|SYMBOL|Feature|HGVSc|HGVSp|CANONICAL|MAX_AF|CLIN_SIG|"
        "AFR_AF|SIFT|CADD_PHRED\">\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\n"
        "3\t30\t.\tA\tC\t70\tPASS\tFS=12.5;SOR=1.2;CLNSIG=Pathogenic;"
        "CLNREVSTAT=reviewed_by_expert_panel;CLNDN=Gene_3_disorder;CLNVID=789;"
        "CSQ=C|missense_variant|MODERATE|GENE3|TX3|c.3A>C|"
        "p.K1Q|YES|0.001|pathogenic|0.0002|deleterious(0.01)|24.1\tGT\t0/1\n"
    )

    variant_indexer.index_run(record(tmp_path))

    with variant_store.connect(variant_indexer.index_path(tmp_path)) as db:
        annotation = db.execute(
            "SELECT gene, transcript, canonical, population_af, clinical_significance, metadata_json "
            "FROM annotations"
        ).fetchone()
        assert tuple(annotation)[:5] == ("GENE3", "TX3", 1, 0.001, "pathogenic")
        fields = json.loads(annotation["metadata_json"])["fields"]
        assert fields["AFR_AF"] == "0.0002"
        assert fields["SIFT"] == "deleterious(0.01)"
        assert fields["CADD_PHRED"] == "24.1"
        variant_metadata = json.loads(db.execute("SELECT metadata_json FROM variants").fetchone()[0])
        assert variant_metadata["quality_metrics"] == {"FS": "12.5", "SOR": "1.2"}
        assert variant_metadata["clinvar"] == {
            "CLNSIG": "Pathogenic", "CLNREVSTAT": "reviewed_by_expert_panel",
            "CLNDN": "Gene_3_disorder", "CLNVID": "789",
        }


def test_compact_tsv_is_used_only_when_no_vcf_is_available(tmp_path):
    path = tmp_path / "results/ANNOTATION/S3.annotated.tsv"
    path.parent.mkdir(parents=True)
    path.write_text(
        "chrom\tpos\tid\tref\talt\tqual\tfilter\tinfo\n"
        "4\t40\trs4\tC\tT\t80\tPASS\tAC=1\n"
    )

    artifacts = variant_indexer.discover_run_vcfs(tmp_path)
    assert artifacts[0]["kind"] == "tsv"
    variant_indexer.index_run(record(tmp_path))

    with variant_store.connect(variant_indexer.index_path(tmp_path)) as db:
        variant = db.execute(
            "SELECT chromosome, position, reference, alternate FROM variants"
        ).fetchone()
        assert tuple(variant) == ("4", 40, "C", "T")
        assert db.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 1


def test_normalize_allele_rejects_no_coordinates_and_minimizes_indels():
    assert variant_indexer.normalize_allele(100, "CAA", "CGA") == (101, "A", "G")
    assert variant_indexer.normalize_allele(100, "AT", "A") == (100, "AT", "A")


def test_indexed_reference_validates_ref_and_left_aligns_repetitive_indels(tmp_path):
    fasta = tmp_path / "reference.fa"
    fasta.write_text(">1\nAAAA\n")
    Path(str(fasta) + ".fai").write_text("1\t4\t3\t4\t5\n")
    write_vcf(
        tmp_path / "results/ANNOTATION/S1.annotated.vcf",
        "1\t3\t.\tAA\tA\t40\tPASS\t.\tGT\t0/1\n",
    )
    archived = record(tmp_path)
    archived["run_config"]["reference_fasta"] = str(fasta)

    result = variant_indexer.index_run(archived)

    assert result["reference_validated"] is True
    with variant_store.connect(variant_indexer.index_path(tmp_path)) as db:
        variant = db.execute("SELECT position, reference, alternate FROM variants").fetchone()
        assert tuple(variant) == (1, "AA", "A")


def test_indexed_reference_rejects_ref_mismatch(tmp_path):
    fasta = tmp_path / "reference.fa"
    fasta.write_text(">1\nAAAA\n")
    Path(str(fasta) + ".fai").write_text("1\t4\t3\t4\t5\n")
    write_vcf(
        tmp_path / "results/ANNOTATION/S1.annotated.vcf",
        "1\t2\t.\tC\tG\t40\tPASS\t.\tGT\t0/1\n",
    )
    archived = record(tmp_path)
    archived["run_config"]["reference_fasta"] = str(fasta)

    with pytest.raises(variant_indexer.VariantIndexError, match="reference mismatch"):
        variant_indexer.index_run(archived)
