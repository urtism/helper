from helper_next.core.samplesheet import build_samplesheet, load_samplesheet_text, resolve_file_paths, rows_from_files


def test_rows_from_fastq_pairs_r1_r2_and_normalizes_sample_name():
    rows, warnings = rows_from_files(
        "prealignment",
        [
            "/data/A-1_S1_R1_001.fastq.gz",
            "/data/A-1_S1_R2_001.fastq.gz",
            "/data/B_S2_R1_001.fastq.gz",
        ],
    )

    assert warnings == []
    assert rows[0]["sample_name"] == "A_1"
    assert rows[0]["fastq_R2"].endswith("_R2_001.fastq.gz")
    assert rows[1]["sample_name"] == "B"
    assert rows[1]["fastq_R2"] == ""


def test_rows_from_fastq_reports_orphan_r2():
    rows, warnings = rows_from_files(
        "prealignment",
        [
            "/data/A_S1_R1_001.fastq.gz",
            "/data/B_S2_R2_001.fastq.gz",
        ],
    )

    assert [row["sample_name"] for row in rows] == ["A"]
    assert warnings == ["R2 without matching R1 ignored: /data/B_S2_R2_001.fastq.gz"]


def test_rows_from_bam_ignores_incompatible_files():
    rows, warnings = rows_from_files(
        "variantcalling",
        [
            "/data/S1.bam",
            "/data/S2.fastq.gz",
        ],
    )

    assert rows == [{"sample_name": "S1", "bam": "/data/S1.bam"}]
    assert warnings == ["FASTQ file ignored for variantcalling step: /data/S2.fastq.gz"]


def test_rows_from_alignment_files_accepts_bam_sam_and_cram():
    rows, warnings = rows_from_files(
        "preprocessing",
        [
            "/data/S1.bam",
            "/data/S2.sam",
            "/data/S3.cram",
        ],
    )

    assert warnings == []
    assert rows == [
        {"sample_name": "S1", "bam": "/data/S1.bam"},
        {"sample_name": "S2", "bam": "/data/S2.sam"},
        {"sample_name": "S3", "bam": "/data/S3.cram"},
    ]


def test_resolve_file_paths_finds_unique_match_in_roots(tmp_path):
    fastq = tmp_path / "run" / "S1_R1.fastq.gz"
    fastq.parent.mkdir()
    fastq.write_text("")

    files, warnings = resolve_file_paths(["S1_R1.fastq.gz"], [tmp_path])

    assert files == [str(fastq.resolve())]
    assert warnings == []


def test_rows_from_postprocessing_groups_vcf_callers_by_sample():
    rows, warnings = rows_from_files(
        "postprocessing",
        [
            "/data/S1.gatk.vcf.gz",
            "/data/S1.freebayes.vcf.gz",
            "/data/S1.varscan.vcf",
            "/data/S1.mutect2.vcf",
        ],
    )

    assert warnings == []
    assert rows == [
        {
            "sample_name": "S1",
            "gatk_vcf": "/data/S1.gatk.vcf.gz",
            "freebayes_vcf": "/data/S1.freebayes.vcf.gz",
            "varscan_vcf": "/data/S1.varscan.vcf",
            "somatic_vcf": "/data/S1.mutect2.vcf",
        }
    ]


def test_rows_from_annotation_pairs_merged_vcf_and_tsv():
    rows, warnings = rows_from_files(
        "annotation",
        [
            "/data/S1.merged.vcf.gz",
            "/data/S1.variants.tsv",
        ],
    )

    assert warnings == []
    assert rows == [{"sample_name": "S1", "merged_vcf": "/data/S1.merged.vcf.gz", "variants_tsv": "/data/S1.variants.tsv"}]


def test_build_only_cases_samplesheet():
    rows = [{"sample_name": "S1", "bam": "/data/S1.bam"}]
    samplesheet = build_samplesheet("variantcalling", "only cases", rows)

    assert samplesheet["sample_list"] == ["S1"]
    assert samplesheet["sample_organization"] == "only cases"
    assert samplesheet["variantcalling"]["S1"]["case"]["bam"] == "/data/S1.bam"


def test_load_existing_samplesheet():
    content = """
    {
      "sample_list": ["S1"],
      "sample_organization": "only cases",
      "preprocessing": {
        "S1": {
          "case": {"sample_name": "S1", "bam": "/data/S1.bam"}
        }
      }
    }
    """

    loaded = load_samplesheet_text(content)

    assert loaded["step"] == "preprocessing"
    assert loaded["rows"] == [{"sample_name": "S1", "bam": "/data/S1.bam"}]
    assert loaded["organization_rows"] == [{"sample_id": "S1", "case": "S1"}]
