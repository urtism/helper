import json

from helper_next.core.vcf_comparison import (
    compare_callset_summaries,
    compare_vcfs,
    read_callset_summary,
    summarize_callset,
    write_callset_summary,
    write_comparison_report,
)


def write_vcf(path, sample_name, variants):
    lines = [
        "##fileformat=VCFv4.2",
        f"#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t{sample_name}",
    ]
    lines.extend(
        f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t50\t{filter_value}\t.\tGT\t{genotype}"
        for chrom, pos, ref, alt, filter_value, genotype in variants
    )
    path.write_text("\n".join(lines) + "\n")
    return path


def test_compare_vcfs_reports_run_family_case_control_and_only_case(tmp_path):
    shared = ("1", 10, "A", "G", "PASS", "0/1")
    callsets = []
    definitions = {
        "CHILD": [shared, ("1", 20, "C", "T", "PASS", "0/1"), ("1", 30, "G", "A", "q10", "0/1")],
        "FATHER": [shared],
        "MOTHER": [("1", 40, "T", "C", "PASS", "0/1")],
        "CASE": [shared, ("2", 10, "A", "AT", "PASS", "1/1")],
        "CONTROL": [shared, ("2", 20, "G", "C", "PASS", "0/1")],
        "SINGLE": [("3", 10, "A", "C", "PASS", "0/1")],
    }
    metadata = {
        "CHILD": ("FAM-01", "proband"),
        "FATHER": ("FAM-01", "father"),
        "MOTHER": ("FAM-01", "mother"),
        "CASE": ("CC-01", "case"),
        "CONTROL": ("CC-01", "control"),
        "SINGLE": ("SINGLE", "proband"),
    }
    for sample_name, variants in definitions.items():
        path = write_vcf(tmp_path / f"{sample_name}.vcf", sample_name, variants)
        analysis_id, role = metadata[sample_name]
        callsets.append({"analysis_id": analysis_id, "role": role, "sample_name": sample_name, "path": str(path)})

    groups = [
        {
            "analysis_id": "FAM-01",
            "analysis_type": "family",
            "members": [
                {"sample_name": "CHILD", "relationship": "proband"},
                {"sample_name": "FATHER", "relationship": "father"},
                {"sample_name": "MOTHER", "relationship": "mother"},
            ],
        },
        {
            "analysis_id": "CC-01",
            "analysis_type": "case-control",
            "members": [
                {"sample_name": "CASE", "relationship": "case"},
                {"sample_name": "CONTROL", "relationship": "control"},
            ],
        },
        {
            "analysis_id": "SINGLE",
            "analysis_type": "only cases",
            "members": [{"sample_name": "SINGLE", "relationship": "proband"}],
        },
    ]

    report = compare_vcfs(callsets, groups)

    assert report["run"] == {
        "germline_callsets": 6,
        "somatic_callsets": 0,
        "unique_germline_variants": 6,
        "singleton_germline_variants": 5,
        "shared_germline_variants": 1,
        "occurrence_distribution": {"1": 5, "4": 1},
    }
    family = report["groups"][0]
    assert family["proband_variants"] == 2
    assert family["shared_with_father"] == 1
    assert family["not_seen_in_relatives"] == 1
    case_control = report["groups"][1]
    assert (case_control["shared_variants"], case_control["case_only_variants"], case_control["control_only_variants"]) == (1, 1, 1)
    only_case = report["groups"][2]
    assert (only_case["unique_in_run"], only_case["shared_in_run"]) == (1, 0)
    child = next(sample for sample in report["samples"] if sample["sample_name"] == "CHILD")
    assert (child["variant_count"], child["filtered_variant_count"], child["het"]) == (2, 1, 3)


def test_compare_vcfs_reports_tumor_normal_as_paired_callset(tmp_path):
    path = write_vcf(
        tmp_path / "PAIR-01.Mutect2.vcf",
        "TUMOR",
        [("7", 140453136, "A", "T", "PASS", "0/1")],
    )
    callsets = [{"analysis_id": "PAIR-01", "role": "tumor-normal", "sample_name": "PAIR-01.tumor_normal", "path": str(path)}]
    groups = [{"analysis_id": "PAIR-01", "analysis_type": "tumor-normal", "members": []}]

    report = compare_vcfs(callsets, groups)

    assert report["run"]["germline_callsets"] == 0
    assert report["run"]["somatic_callsets"] == 1
    assert report["groups"][0]["somatic_variants"] == 1


def test_write_comparison_report_creates_machine_readable_outputs(tmp_path):
    report = {
        "samples": [{"sample_name": "S1", "variant_count": 1}],
        "groups": [{"analysis_id": "S1", "analysis_type": "only cases", "variant_count": 1}],
        "variant_presence": [{"chrom": "1", "pos": 10, "ref": "A", "alt": "G", "sample_count": 1, "samples": ["S1"]}],
    }

    write_comparison_report(report, tmp_path)

    assert json.loads((tmp_path / "run.vcf_statistics.json").read_text()) == report
    assert "sample_name\tvariant_count" in (tmp_path / "run.sample_statistics.tsv").read_text()
    assert "analysis_id\tanalysis_type\tmetric\tvalue" in (tmp_path / "run.group_comparison.tsv").read_text()
    assert "chrom\tpos\tref\talt\tsample_count\tsamples" in (tmp_path / "run.variant_presence.tsv").read_text()


def test_callset_summary_round_trip_keeps_variants_for_later_aggregation(tmp_path):
    vcf = write_vcf(tmp_path / "S1.vcf", "S1", [("1", 10, "A", "G", "PASS", "0/1")])
    summary = summarize_callset({"analysis_id": "S1", "role": "proband", "sample_name": "S1", "path": str(vcf)})
    summary_path = write_callset_summary(summary, tmp_path / "S1.callset.json.gz")

    loaded = read_callset_summary(summary_path)
    report = compare_callset_summaries(
        [loaded],
        [{"analysis_id": "S1", "analysis_type": "only cases", "members": [{"sample_name": "S1"}]}],
    )

    assert report["run"]["unique_germline_variants"] == 1
    assert report["samples"][0]["vcf"] == "S1.vcf"
