import argparse
import gzip
import json
from collections import Counter
from pathlib import Path


NON_VARIANT_ALLELES = {".", "<NON_REF>"}


def open_vcf(path):
    path = Path(path)
    if path.suffix == ".gz":
        return gzip.open(path, "rt")
    return path.open()


def parse_vcf(path, preferred_sample=""):
    variants = set()
    filtered_variants = set()
    sample_columns = []
    selected_sample_index = None
    counts = Counter(records=0, pass_records=0, snvs=0, indels=0, het=0, hom_alt=0, no_call=0)

    with open_vcf(path) as handle:
        for line in handle:
            if line.startswith("#CHROM"):
                sample_columns = line.rstrip("\n").split("\t")[9:]
                if preferred_sample in sample_columns:
                    selected_sample_index = sample_columns.index(preferred_sample)
                elif sample_columns:
                    selected_sample_index = 0
                continue
            if line.startswith("#") or not line.strip():
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 8:
                continue
            chrom, pos, _identifier, ref, alt_field, _qual, filter_value, _info = fields[:8]
            alts = [alt for alt in alt_field.split(",") if alt not in NON_VARIANT_ALLELES]
            if not alts:
                continue
            counts["records"] += 1
            is_pass = filter_value in {"PASS", "."}
            if is_pass:
                counts["pass_records"] += 1
            for alt in alts:
                key = (chrom, int(pos), ref, alt)
                if is_pass:
                    variants.add(key)
                    if len(ref) == 1 and len(alt) == 1:
                        counts["snvs"] += 1
                    else:
                        counts["indels"] += 1
                else:
                    filtered_variants.add(key)

            if selected_sample_index is None or len(fields) <= 9 + selected_sample_index:
                continue
            format_keys = fields[8].split(":")
            sample_values = fields[9 + selected_sample_index].split(":")
            genotype = dict(zip(format_keys, sample_values)).get("GT", "")
            alleles = genotype.replace("|", "/").split("/") if genotype else []
            if not alleles or any(allele == "." for allele in alleles):
                counts["no_call"] += 1
            elif len(set(alleles)) > 1:
                counts["het"] += 1
            elif alleles[0] != "0":
                counts["hom_alt"] += 1

    return {
        "variants": variants,
        "filtered_variants": filtered_variants,
        "sample_columns": sample_columns,
        "counts": dict(counts),
    }


def compare_vcfs(callsets, analysis_groups):
    return compare_callset_summaries([summarize_callset(callset) for callset in callsets], analysis_groups)


def summarize_callset(callset):
    parsed = parse_vcf(callset["path"], callset.get("sample_name", ""))
    return {
        "analysis_id": callset.get("analysis_id", ""),
        "role": callset.get("role", ""),
        "sample_name": callset.get("sample_name", ""),
        "vcf": Path(callset["path"]).name,
        "variants": [list(variant) for variant in sorted(parsed["variants"])],
        "filtered_variants": [list(variant) for variant in sorted(parsed["filtered_variants"])],
        "sample_columns": parsed["sample_columns"],
        "counts": parsed["counts"],
    }


def compare_callset_summaries(callset_summaries, analysis_groups):
    parsed_callsets = [
        {
            **summary,
            "variants": {tuple(variant) for variant in summary.get("variants", [])},
            "filtered_variants": {tuple(variant) for variant in summary.get("filtered_variants", [])},
        }
        for summary in callset_summaries
    ]

    germline_callsets = [callset for callset in parsed_callsets if callset.get("role") != "tumor-normal"]
    somatic_callsets = [callset for callset in parsed_callsets if callset.get("role") == "tumor-normal"]
    occurrence = Counter(
        variant
        for callset in germline_callsets
        for variant in callset["variants"]
    )
    by_sample = {callset.get("sample_name"): callset for callset in germline_callsets}
    somatic_by_group = {callset.get("analysis_id"): callset for callset in somatic_callsets}

    group_reports = []
    for group in analysis_groups:
        analysis_id = group.get("analysis_id", "")
        analysis_type = group.get("analysis_type", "")
        members = group.get("members", [])
        if analysis_type == "family":
            group_reports.append(family_report(analysis_id, members, by_sample))
        elif analysis_type == "case-control":
            group_reports.append(case_control_report(analysis_id, members, by_sample))
        elif analysis_type == "only cases":
            group_reports.append(only_case_report(analysis_id, members, by_sample, occurrence))
        elif analysis_type == "tumor-normal":
            callset = somatic_by_group.get(analysis_id)
            group_reports.append(
                {
                    "analysis_id": analysis_id,
                    "analysis_type": analysis_type,
                    "somatic_variants": len(callset["variants"]) if callset else 0,
                    "missing_callset": callset is None,
                }
            )

    sample_reports = []
    for callset in parsed_callsets:
        sample_reports.append(
            {
                "analysis_id": callset.get("analysis_id", ""),
                "role": callset.get("role", ""),
                "sample_name": callset.get("sample_name", ""),
                "vcf": callset.get("vcf", ""),
                "variant_count": len(callset["variants"]),
                "filtered_variant_count": len(callset["filtered_variants"]),
                **callset["counts"],
            }
        )

    frequency_distribution = Counter(occurrence.values())
    return {
        "schema_version": 1,
        "calling_strategy": "single-sample",
        "comparison_basis": "PASS variants emitted in each VCF",
        "interpretation_note": (
            "Absence from a single-sample VCF does not prove a homozygous-reference genotype; "
            "use stored gVCFs when reference-confidence genotyping is required."
        ),
        "run": {
            "germline_callsets": len(germline_callsets),
            "somatic_callsets": len(somatic_callsets),
            "unique_germline_variants": len(occurrence),
            "singleton_germline_variants": frequency_distribution.get(1, 0),
            "shared_germline_variants": sum(count for frequency, count in frequency_distribution.items() if frequency > 1),
            "occurrence_distribution": {
                str(frequency): count for frequency, count in sorted(frequency_distribution.items())
            },
        },
        "samples": sample_reports,
        "groups": group_reports,
        "variant_presence": [
            {
                "chrom": variant[0],
                "pos": variant[1],
                "ref": variant[2],
                "alt": variant[3],
                "sample_count": occurrence[variant],
                "samples": sorted(
                    callset.get("sample_name", "")
                    for callset in germline_callsets
                    if variant in callset["variants"]
                ),
            }
            for variant in sorted(occurrence, key=lambda item: (item[0], item[1], item[2], item[3]))
        ],
    }


def member_callset(members, relationship, by_sample):
    member = next((item for item in members if item.get("relationship") == relationship), None)
    return by_sample.get(member.get("sample_name")) if member else None


def family_report(analysis_id, members, by_sample):
    proband = member_callset(members, "proband", by_sample)
    father = member_callset(members, "father", by_sample)
    mother = member_callset(members, "mother", by_sample)
    proband_variants = proband["variants"] if proband else set()
    father_variants = father["variants"] if father else set()
    mother_variants = mother["variants"] if mother else set()
    relatives = [by_sample.get(member.get("sample_name")) for member in members if member.get("relationship") != "proband"]
    relative_union = set().union(*(item["variants"] for item in relatives if item)) if relatives else set()
    return {
        "analysis_id": analysis_id,
        "analysis_type": "family",
        "proband_variants": len(proband_variants),
        "shared_with_father": len(proband_variants & father_variants),
        "shared_with_mother": len(proband_variants & mother_variants),
        "shared_with_both_parents": len(proband_variants & father_variants & mother_variants),
        "shared_with_any_relative": len(proband_variants & relative_union),
        "not_seen_in_relatives": len(proband_variants - relative_union),
        "missing_samples": sorted(
            member.get("sample_name", "") for member in members if member.get("sample_name") not in by_sample
        ),
    }


def case_control_report(analysis_id, members, by_sample):
    case = member_callset(members, "case", by_sample)
    control = member_callset(members, "control", by_sample)
    case_variants = case["variants"] if case else set()
    control_variants = control["variants"] if control else set()
    union = case_variants | control_variants
    return {
        "analysis_id": analysis_id,
        "analysis_type": "case-control",
        "case_variants": len(case_variants),
        "control_variants": len(control_variants),
        "shared_variants": len(case_variants & control_variants),
        "case_only_variants": len(case_variants - control_variants),
        "control_only_variants": len(control_variants - case_variants),
        "jaccard_similarity": round(len(case_variants & control_variants) / len(union), 6) if union else 1.0,
        "missing_samples": sorted(
            member.get("sample_name", "") for member in members if member.get("sample_name") not in by_sample
        ),
    }


def only_case_report(analysis_id, members, by_sample, occurrence):
    sample_name = members[0].get("sample_name", "") if members else ""
    callset = by_sample.get(sample_name)
    variants = callset["variants"] if callset else set()
    return {
        "analysis_id": analysis_id,
        "analysis_type": "only cases",
        "sample_name": sample_name,
        "variant_count": len(variants),
        "unique_in_run": sum(1 for variant in variants if occurrence[variant] == 1),
        "shared_in_run": sum(1 for variant in variants if occurrence[variant] > 1),
        "missing_callset": callset is None,
    }


def write_comparison_report(report, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "run.vcf_statistics.json"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    write_tsv(output_dir / "run.sample_statistics.tsv", report["samples"])
    group_rows = []
    for group in report["groups"]:
        for metric, value in group.items():
            if metric in {"analysis_id", "analysis_type"}:
                continue
            if isinstance(value, list):
                value = ",".join(str(item) for item in value)
            group_rows.append(
                {
                    "analysis_id": group["analysis_id"],
                    "analysis_type": group["analysis_type"],
                    "metric": metric,
                    "value": value,
                }
            )
    write_tsv(output_dir / "run.group_comparison.tsv", group_rows)
    presence_rows = [
        {**row, "samples": ",".join(row["samples"])} for row in report["variant_presence"]
    ]
    write_tsv(output_dir / "run.variant_presence.tsv", presence_rows)
    return output_dir


def write_callset_summary(summary, path):
    path = Path(path)
    if path.suffix == ".gz":
        with gzip.open(path, "wt") as handle:
            json.dump(summary, handle, sort_keys=True)
            handle.write("\n")
    else:
        path.write_text(json.dumps(summary, sort_keys=True) + "\n")
    return path


def read_callset_summary(path):
    path = Path(path)
    if path.suffix == ".gz":
        with gzip.open(path, "rt") as handle:
            return json.load(handle)
    return json.loads(path.read_text())


def write_tsv(path, rows):
    rows = list(rows)
    if not rows:
        path.write_text("")
        return
    columns = list(rows[0])
    with path.open("w") as handle:
        handle.write("\t".join(columns) + "\n")
        for row in rows:
            handle.write("\t".join(str(row.get(column, "")) for column in columns) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare single-sample VCFs inside one Helper run")
    subparsers = parser.add_subparsers(dest="command", required=True)

    summarize_parser = subparsers.add_parser("summarize", help="Convert one VCF into a compact callset summary")
    summarize_parser.add_argument("--vcf", required=True)
    summarize_parser.add_argument("--analysis-id", required=True)
    summarize_parser.add_argument("--role", required=True)
    summarize_parser.add_argument("--sample-name", required=True)
    summarize_parser.add_argument("--output", required=True)

    aggregate_parser = subparsers.add_parser("aggregate", help="Create run and analysis-group comparisons")
    aggregate_parser.add_argument("--summaries", nargs="+", required=True)
    aggregate_parser.add_argument("--run-config", required=True)
    aggregate_parser.add_argument("--output-dir", default=".")
    args = parser.parse_args(argv)

    if args.command == "summarize":
        summary = summarize_callset(
            {
                "analysis_id": args.analysis_id,
                "role": args.role,
                "sample_name": args.sample_name,
                "path": args.vcf,
            }
        )
        write_callset_summary(summary, args.output)
        return

    run_config = json.loads(Path(args.run_config).read_text())
    summaries = [read_callset_summary(path) for path in args.summaries]
    report = compare_callset_summaries(summaries, run_config.get("analysis_groups", []))
    write_comparison_report(report, args.output_dir)


if __name__ == "__main__":
    main()
