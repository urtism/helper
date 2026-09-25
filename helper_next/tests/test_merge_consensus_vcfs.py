import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/merge_consensus_vcfs.py"
SPEC = importlib.util.spec_from_file_location("helper_merge_consensus_vcfs", SCRIPT)
MERGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MERGER)


def write_vcf(path, caller, records):
    lines = [
        "##fileformat=VCFv4.2",
        "##contig=<ID=1,length=1000000>",
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1",
    ]
    lines.extend(records)
    path.write_text("\n".join(lines) + "\n")
    return str(path)


def three_callers(tmp_path, deepvariant_gt="0/1", freebayes_gq=80, strand_bias=False):
    if strand_bias:
        gatk_sb = "30,30,40,0"
        freebayes_strand = "SRF=27;SRR=27;SAF=36;SAR=0"
    else:
        gatk_sb = "30,30,22,18"
        freebayes_strand = "SRF=27;SRR=27;SAF=19;SAR=17"
    gatk = write_vcf(
        tmp_path / "gatk.vcf",
        "GATK",
        [
            "1\t100\trs1\tA\tG\t100\tPASS\tQD=10;MQ=60;FS=1;SOR=0.5"
            "\tGT:DP:AD:GQ:SB\t0/1:100:60,40:99:{}".format(gatk_sb),
            "1\t200\t.\tC\tT\t70\tPASS\tQD=8;MQ=58\tGT:DP:AD:GQ:SB\t0/1:40:30,10:70:15,15,5,5",
        ],
    )
    freebayes = write_vcf(
        tmp_path / "freebayes.vcf",
        "FREEBAYES",
        [
            "1\t100\t.\tA\tG\t90\tPASS\t{};MQM=55"
            "\tGT:DP:AD:GQ:QA\t0/1:90:54,36:{}:1000".format(freebayes_strand, freebayes_gq),
        ],
    )
    deepvariant = write_vcf(
        tmp_path / "deepvariant.vcf",
        "DEEPVARIANT",
        [
            "1\t100\t.\tA\tG\t110\tPASS\t.\tGT:DP:AD:GQ\t{}:110:66,44:98".format(deepvariant_gt),
        ],
    )
    return {"GATK": gatk, "FREEBAYES": freebayes, "DEEPVARIANT": deepvariant}


def output_records(path):
    return [line.split("\t") for line in path.read_text().splitlines() if line and not line.startswith("#")]


def parse_info(raw):
    return dict(item.split("=", 1) for item in raw.split(";"))


def test_merge_builds_consensus_and_retains_single_caller_variants(tmp_path):
    inputs = three_callers(tmp_path)
    output = tmp_path / "merged.vcf"

    counts = MERGER.merge_vcfs(inputs, output, MERGER.load_config(None))
    records = output_records(output)
    first, second = records
    first_info = parse_info(first[7])

    assert counts == {"total": 2, "pass": 1, "filtered": 1}
    assert first[0:5] == ["1", "100", "rs1", "A", "G"]
    assert first[6] == "PASS"
    assert first_info["CALLERS"] == "GATK,FREEBAYES,DEEPVARIANT"
    assert first_info["PASS_CALLERS"] == "GATK,FREEBAYES,DEEPVARIANT"
    assert first_info["STRAND_SOURCES"] == "GATK,FREEBAYES"
    assert first_info["GATK_FILTER_HELPER"] == "PASS"
    assert first_info["DV_INFO_RAW"] == "."
    assert first[8] == "GT:DP:AD:RO:AO:AF:GQ:ADF:ADR:ABF:FS:SOR"
    sample = first[9].split(":")
    assert sample[:7] == ["0/1", "100", "60,40", "60", "40", "0.4", "98"]
    assert sample[7:9] == ["29,21", "29,18"]
    assert second[1] == "200"
    assert second[6] == "LOW_CALLER_SUPPORT"


def test_caller_filters_exclude_failed_caller_from_consensus(tmp_path):
    inputs = three_callers(tmp_path, freebayes_gq=20)
    output = tmp_path / "merged.vcf"
    config = MERGER.deep_update(
        MERGER.load_config(None),
        {"caller_filters": {"FREEBAYES": {"min_gq": 30}}},
    )

    MERGER.merge_vcfs(inputs, output, config)
    record = output_records(output)[0]
    info = parse_info(record[7])

    assert record[6] == "PASS"
    assert info["PASS_CALLERS"] == "GATK,DEEPVARIANT"
    assert info["FREEB_FILTER_HELPER"] == "LOW_GQ"
    assert info["CALLER_FILTER_DISCORDANCE"] == "1"
    assert record[9].split(":")[:7] == ["0/1", "105", "63,42", "63", "42", "0.4", "99"]


def test_genotype_disagreement_is_retained_and_filtered(tmp_path):
    inputs = three_callers(tmp_path, deepvariant_gt="1/1")
    output = tmp_path / "merged.vcf"

    MERGER.merge_vcfs(inputs, output, MERGER.load_config(None))
    record = output_records(output)[0]
    info = parse_info(record[7])

    assert record[6] == "GT_CONFLICT"
    assert record[9].split(":", 1)[0] == "0/1"
    assert info["GT_CONFLICT"] == "1"


def test_consensus_strand_filter_uses_gatk_and_freebayes_counts(tmp_path):
    inputs = three_callers(tmp_path, strand_bias=True)
    output = tmp_path / "merged.vcf"
    config = MERGER.deep_update(
        MERGER.load_config(None),
        {"consensus_filters": {"min_alt_strand_fraction": 0.1, "min_strand_alt_depth": 6}},
    )

    MERGER.merge_vcfs(inputs, output, config)
    record = output_records(output)[0]

    assert "ALT_STRAND_BIAS" in record[6].split(";")
    assert record[9].split(":")[7:10] == ["29,38", "29,0", "1"]


def test_multiallelic_input_must_be_normalized_before_merge(tmp_path):
    gatk = write_vcf(
        tmp_path / "gatk.vcf",
        "GATK",
        ["1\t100\t.\tA\tG,T\t100\tPASS\t.\tGT:DP:AD:GQ\t1/2:100:50,25,25:99"],
    )

    with pytest.raises(ValueError, match="must be split before merging"):
        MERGER.merge_vcfs({"GATK": gatk}, tmp_path / "merged.vcf", MERGER.load_config(None))


def test_exact_duplicate_records_from_overlapping_regions_are_collapsed(tmp_path):
    record = "1\t100\t.\tA\tG\t90\tPASS\tSRF=27;SRR=27;SAF=19;SAR=17\tGT:DP:AD:GQ\t0/1:90:54,36:80"
    freebayes = write_vcf(tmp_path / "freebayes.vcf", "FREEBAYES", [record, record])
    output = tmp_path / "merged.vcf"

    counts = MERGER.merge_vcfs({"FREEBAYES": freebayes}, output, MERGER.load_config(None))

    assert counts == {"total": 1, "filtered": 1}
    assert len(output_records(output)) == 1


def test_conflicting_duplicate_records_are_rejected(tmp_path):
    freebayes = write_vcf(
        tmp_path / "freebayes.vcf",
        "FREEBAYES",
        [
            "1\t100\t.\tA\tG\t90\tPASS\t.\tGT:DP:AD:GQ\t0/1:90:54,36:80",
            "1\t100\t.\tA\tG\t70\tPASS\t.\tGT:DP:AD:GQ\t0/1:80:50,30:70",
        ],
    )

    with pytest.raises(ValueError, match="conflicting duplicate normalized variant"):
        MERGER.merge_vcfs({"FREEBAYES": freebayes}, tmp_path / "merged.vcf", MERGER.load_config(None))


def test_fisher_exact_handles_large_read_counts_without_overflow():
    p_value = MERGER.fisher_exact_two_sided(1000, 1000, 1200, 800)

    assert 0.0 <= p_value <= 1.0
