import json

from helper_next.core.samplesheet import build_samplesheet, load_samplesheet_text, resolve_file_paths, rows_from_files


def test_rows_from_fastq_pairs_r1_r2_and_preserves_exact_sample_id():
    rows, warnings = rows_from_files(
        "prealignment",
        [
            "/data/A-1_S1_R1_001.fastq.gz",
            "/data/A-1_S1_R2_001.fastq.gz",
            "/data/B_S2_R1_001.fastq.gz",
        ],
    )

    assert warnings == ["R1 without matching R2: /data/B_S2_R1_001.fastq.gz"]
    assert rows[0]["sample_name"] == "A-1"
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
    assert warnings == [
        "R1 without matching R2: /data/A_S1_R1_001.fastq.gz",
        "R2 without matching R1 ignored: /data/B_S2_R2_001.fastq.gz",
    ]


def test_rows_from_fastq_uses_illumina_suffix_as_delimiter_and_finds_r2_on_disk(tmp_path):
    r1 = tmp_path / "Patient-01_S6_L001_R1_001.fastq.gz"
    r2 = tmp_path / "Patient-01_S6_L001_R2_001.fastq.gz"
    r1.write_text("")
    r2.write_text("")

    rows, warnings = rows_from_files("prealignment", [str(r1)])

    assert warnings == []
    assert rows == [
        {
            "sample_name": "Patient-01",
            "fastq_R1": str(r1),
            "fastq_R2": str(r2),
            "fastq_I2": "",
        }
    ]


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


def test_rows_from_bam_preserves_exact_sample_id():
    rows, warnings = rows_from_files("variantcalling", ["/data/Patient-01.bam"])

    assert warnings == []
    assert rows == [{"sample_name": "Patient-01", "bam": "/data/Patient-01.bam"}]


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


def test_build_and_load_mixed_analysis_samplesheet_round_trip():
    rows = [
        {"sample_name": "CHILD", "bam": "/data/child.bam"},
        {"sample_name": "FATHER", "bam": "/data/father.bam"},
        {"sample_name": "MOTHER", "bam": "/data/mother.bam"},
        {"sample_name": "SINGLE", "bam": "/data/single.bam"},
    ]
    organization_rows = [
        {
            "sample_name": "CHILD",
            "analysis_type": "family",
            "analysis_id": "FAM-01",
            "relationship": "proband",
            "sex": "female",
            "father": "FATHER",
            "mother": "MOTHER",
            "affected": "affected",
            "twin_group": "",
        },
        {
            "sample_name": "FATHER",
            "analysis_type": "family",
            "analysis_id": "FAM-01",
            "relationship": "father",
            "sex": "male",
            "father": "",
            "mother": "",
            "affected": "unaffected",
            "twin_group": "",
        },
        {
            "sample_name": "MOTHER",
            "analysis_type": "family",
            "analysis_id": "FAM-01",
            "relationship": "mother",
            "sex": "female",
            "father": "",
            "mother": "",
            "affected": "unaffected",
            "twin_group": "",
        },
        {
            "sample_name": "SINGLE",
            "analysis_type": "only cases",
            "analysis_id": "SINGLE",
            "relationship": "proband",
        },
    ]

    samplesheet = build_samplesheet("variantcalling", "mixed", rows, organization_rows)

    assert samplesheet["schema_version"] == 2
    assert samplesheet["sample_organization"] == "mixed"
    assert samplesheet["sample_list"] == ["CHILD", "FATHER", "MOTHER", "SINGLE"]
    assert samplesheet["variantcalling"]["CHILD"]["bam"] == "/data/child.bam"
    assert samplesheet["analysis_groups"][0]["analysis_id"] == "FAM-01"
    assert samplesheet["analysis_groups"][0]["members"][0]["father"] == "FATHER"

    loaded = load_samplesheet_text(json.dumps(samplesheet))

    assert loaded["organization"] == "mixed"
    assert loaded["rows"] == rows
    loaded_members = {row["sample_name"]: row for row in loaded["organization_rows"]}
    assert loaded_members["CHILD"]["analysis_id"] == "FAM-01"
    assert loaded_members["CHILD"]["relationship"] == "proband"
    assert loaded_members["CHILD"]["father"] == "FATHER"
    assert loaded_members["SINGLE"]["analysis_type"] == "only cases"


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


def test_load_legacy_tabular_samplesheet_bam():
    content = "S1\t/data/S1.bam\nS2\t/data/S2.bam\n"

    loaded = load_samplesheet_text(content)

    assert loaded["step"] == "preprocessing"
    assert loaded["rows"] == [
        {"sample_name": "S1", "bam": "/data/S1.bam"},
        {"sample_name": "S2", "bam": "/data/S2.bam"},
    ]
    assert loaded["samplesheet"]["sample_list"] == ["S1", "S2"]


def test_load_legacy_tabular_samplesheet_fastq():
    content = "S1\t/data/S1_R1.fastq.gz\t/data/S1_R2.fastq.gz\n"

    loaded = load_samplesheet_text(content)

    assert loaded["step"] == "prealignment"
    assert loaded["rows"] == [
        {
            "sample_name": "S1",
            "fastq_R1": "/data/S1_R1.fastq.gz",
            "fastq_R2": "/data/S1_R2.fastq.gz",
            "fastq_I2": "",
        }
    ]
