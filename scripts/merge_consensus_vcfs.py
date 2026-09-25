#!/usr/bin/env python3
"""Build a consensus from single-sample VCFs produced by different callers.

Caller-specific evidence is retained in INFO while a caller-independent FORMAT
is calculated for the consensus sample. Inputs must already be left-aligned and
split into biallelic records. Exact duplicate records from overlapping calling
regions are collapsed; conflicting duplicates are rejected. Variants are
filtered, never discarded.
"""

import argparse
import gzip
import json
import math
import re
import statistics
import sys
from collections import Counter, OrderedDict
from dataclasses import dataclass
from urllib.parse import quote


CALLER_ORDER = ("GATK", "FREEBAYES", "DEEPVARIANT", "VARSCAN")
CALLER_TAGS = {"GATK": "GATK", "FREEBAYES": "FREEB", "DEEPVARIANT": "DV", "VARSCAN": "VARSCAN"}
DEFAULT_CONFIG = {
    "min_pass_callers": 2,
    "honor_original_filter": True,
    "filter_gt_conflict": True,
    "filter_caller_discordance": False,
    "caller_filters": {},
    "consensus_filters": {},
}
FILTER_DESCRIPTIONS = OrderedDict([
    ("LOW_CALLER_SUPPORT", "Fewer callers passed than required"),
    ("GT_CONFLICT", "Passing callers reported discordant genotypes"),
    ("CALLER_FILTER_DISCORDANCE", "At least one caller passed and at least one caller failed"),
    ("LOW_DP", "Consensus read depth is below threshold"),
    ("LOW_ALT_DEPTH", "Consensus alternate read depth is below threshold"),
    ("LOW_AF", "Consensus alternate allele fraction is below threshold"),
    ("LOW_GQ", "Consensus genotype quality is below threshold"),
    ("MISSING_DP", "Consensus read depth is unavailable"),
    ("MISSING_ALT_DEPTH", "Consensus alternate read depth is unavailable"),
    ("MISSING_AF", "Consensus alternate allele fraction is unavailable"),
    ("MISSING_GQ", "Consensus genotype quality is unavailable"),
    ("ALT_STRAND_BIAS", "Alternate observations are strongly imbalanced between strands"),
    ("HIGH_FS", "Consensus Fisher strand score exceeds threshold"),
    ("HIGH_SOR", "Consensus strand odds ratio exceeds threshold"),
])


@dataclass
class VcfRecord:
    caller: str
    chrom: str
    pos: int
    identifier: str
    ref: str
    alt: str
    qual: str
    original_filter: str
    info: dict
    sample: dict
    raw_info: str
    raw_format: str
    raw_sample: str

    @property
    def key(self):
        return self.chrom, self.pos, self.ref, self.alt


@dataclass
class CallerEvidence:
    record: VcfRecord
    gt: str
    dp: float
    ro: float
    ao: float
    af: float
    gq: float
    strand: tuple
    helper_filters: list

    @property
    def caller(self):
        return self.record.caller

    @property
    def passed(self):
        return not self.helper_filters


def open_text(path, mode="rt"):
    if str(path).endswith(".gz"):
        return gzip.open(path, mode, encoding="utf-8")
    return open(path, mode, encoding="utf-8")


def parse_info(raw_info):
    result = {}
    if raw_info in ("", "."):
        return result
    for item in raw_info.split(";"):
        if not item:
            continue
        if "=" in item:
            key, value = item.split("=", 1)
            result[key] = value
        else:
            result[item] = True
    return result


def read_vcf(path, caller):
    records = OrderedDict()
    sample_name = None
    contigs = []
    with open_text(path) as handle:
        for line_number, raw_line in enumerate(handle, 1):
            line = raw_line.rstrip("\n")
            if line.startswith("##contig="):
                contigs.append(line)
                continue
            if line.startswith("##"):
                continue
            if line.startswith("#CHROM"):
                columns = line.split("\t")
                if len(columns) != 10:
                    raise ValueError("{}: exactly one sample is required".format(path))
                sample_name = columns[9]
                continue
            if not line:
                continue
            if sample_name is None:
                raise ValueError("{}:{}: missing #CHROM header".format(path, line_number))
            columns = line.split("\t")
            if len(columns) != 10:
                raise ValueError("{}:{}: expected 10 VCF columns".format(path, line_number))
            chrom, pos, identifier, ref, alt, qual, original_filter, raw_info, raw_format, raw_sample = columns
            if "," in alt:
                raise ValueError("{}:{}: multiallelic record {}:{} must be split before merging".format(path, line_number, chrom, pos))
            format_keys = [] if raw_format in ("", ".") else raw_format.split(":")
            sample_values = [] if raw_sample in ("", ".") else raw_sample.split(":")
            sample = {key: sample_values[index] if index < len(sample_values) else "." for index, key in enumerate(format_keys)}
            record = VcfRecord(
                caller, chrom, int(pos), identifier, ref, alt, qual, original_filter,
                parse_info(raw_info), sample, raw_info, raw_format, raw_sample,
            )
            if record.key in records:
                if records[record.key] == record:
                    continue
                raise ValueError(
                    "{}:{}: conflicting duplicate normalized variant {}:{}:{}>{}".format(
                        path, line_number, chrom, pos, ref, alt,
                    )
                )
            records[record.key] = record
    if sample_name is None:
        raise ValueError("{}: no #CHROM header found".format(path))
    return sample_name, records, contigs


def as_float(value):
    if value in (None, "", "."):
        return None
    try:
        result = float(str(value).split(",", 1)[0])
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def as_number_list(value):
    if value in (None, "", "."):
        return []
    result = []
    for item in str(value).split(","):
        number = as_float(item)
        if number is None:
            return []
        result.append(number)
    return result


def first_value(record, names, include_info=True):
    for name in names:
        if record.sample.get(name) not in (None, "", "."):
            return record.sample[name]
    if include_info:
        for name in names:
            if record.info.get(name) not in (None, "", "."):
                return record.info[name]
    return None


def normalize_gt(value):
    if value in (None, "", ".", "./.", ".|."):
        return "./."
    alleles = re.split(r"[/|]", str(value))
    if not alleles or any(allele == "." or not allele.isdigit() for allele in alleles):
        return "./."
    return "/".join(sorted(alleles, key=int))


def gt_supports_alt(gt):
    return gt != "./." and any(allele.isdigit() and int(allele) > 0 for allele in gt.split("/"))


def record_strand_counts(record):
    if record.caller == "GATK":
        values = as_number_list(first_value(record, ("SB",)))
        if len(values) == 4:
            return tuple(values)
    if record.caller == "FREEBAYES":
        values = [as_float(record.info.get(name)) for name in ("SRF", "SRR", "SAF", "SAR")]
        if all(value is not None for value in values):
            return tuple(values)
    if record.caller == "VARSCAN":
        values = [as_float(record.sample.get(name)) for name in ("RDF", "RDR", "ADF", "ADR")]
        if all(value is not None for value in values):
            return tuple(values)
    return None


def caller_rules(config, caller):
    configured = config.get("caller_filters", {})
    rules = {}
    if isinstance(configured.get("default"), dict):
        rules.update(configured["default"])
    for name in (caller, CALLER_TAGS[caller]):
        if isinstance(configured.get(name), dict):
            rules.update(configured[name])
    return rules


def threshold_filter(reasons, name, value, rules, minimum=None, maximum=None):
    threshold = rules.get(minimum or maximum)
    if threshold in (None, ""):
        return
    if value is None:
        reasons.append("MISSING_{}".format(name))
    elif minimum and value < float(threshold):
        reasons.append("LOW_{}".format(name))
    elif maximum and value > float(threshold):
        reasons.append("HIGH_{}".format(name))


def build_evidence(record, config):
    gt = normalize_gt(first_value(record, ("GT",), include_info=False))
    dp = as_float(first_value(record, ("DP", "SDP")))
    ad = as_number_list(first_value(record, ("AD",), include_info=False))
    ro = ad[0] if len(ad) >= 2 else as_float(first_value(record, ("RO", "RD")))
    ao = ad[1] if len(ad) >= 2 else as_float(first_value(record, ("AO",)))
    af = as_float(first_value(record, ("AF", "VAF", "FREQ")))
    if af is not None and af > 1:
        af /= 100.0
    if af is None and ro is not None and ao is not None and ro + ao > 0:
        af = ao / (ro + ao)
    gq = as_float(first_value(record, ("GQ",), include_info=False))
    strand = record_strand_counts(record)
    rules = caller_rules(config, record.caller)
    reasons = []
    if not gt_supports_alt(gt):
        reasons.append("NO_ALT_GT")
    if config.get("honor_original_filter", True) and record.original_filter not in ("", ".", "PASS"):
        reasons.append("ORIGINAL_FILTER")
    threshold_filter(reasons, "DP", dp, rules, minimum="min_dp")
    threshold_filter(reasons, "ALT_DEPTH", ao, rules, minimum="min_alt_depth")
    threshold_filter(reasons, "AF", af, rules, minimum="min_af")
    threshold_filter(reasons, "GQ", gq, rules, minimum="min_gq")
    if record.caller == "GATK":
        threshold_filter(reasons, "QD", as_float(record.info.get("QD")), rules, minimum="min_qd")
        threshold_filter(reasons, "MQ", as_float(record.info.get("MQ")), rules, minimum="min_mq")
        threshold_filter(reasons, "FS", as_float(record.info.get("FS")), rules, maximum="max_fs")
        threshold_filter(reasons, "SOR", as_float(record.info.get("SOR")), rules, maximum="max_sor")
    elif record.caller == "FREEBAYES":
        threshold_filter(reasons, "MQ", as_float(record.info.get("MQM")), rules, minimum="min_mq")
        threshold_filter(reasons, "QA", as_float(first_value(record, ("QA",))), rules, minimum="min_qa")
    return CallerEvidence(record, gt, dp, ro, ao, af, gq, strand, list(OrderedDict.fromkeys(reasons)))


def rounded_median(values):
    usable = [float(value) for value in values if value is not None]
    return int(math.floor(statistics.median(usable) + 0.5)) if usable else None


def consensus_gt(values):
    usable = [value for value in values if value != "./."]
    if not usable:
        return "./.", False
    counts = Counter(usable)
    most_common = counts.most_common()
    conflict = len(counts) > 1
    if len(most_common) > 1 and most_common[0][1] == most_common[1][1]:
        return "./.", conflict
    return most_common[0][0], conflict


def fisher_exact_two_sided(a, b, c, d):
    a, b, c, d = [int(round(value)) for value in (a, b, c, d)]
    if any(value < 0 for value in (a, b, c, d)):
        return None
    row1, row2, col1 = a + b, c + d, a + c
    total = row1 + row2
    if total == 0:
        return None

    def log_probability(x):
        if x < 0 or x > row1 or col1 - x < 0 or col1 - x > row2:
            return None
        return (
            math.lgamma(row1 + 1)
            - math.lgamma(x + 1)
            - math.lgamma(row1 - x + 1)
            + math.lgamma(row2 + 1)
            - math.lgamma(col1 - x + 1)
            - math.lgamma(row2 - col1 + x + 1)
            - math.lgamma(total + 1)
            + math.lgamma(col1 + 1)
            + math.lgamma(total - col1 + 1)
        )

    observed = log_probability(a)
    lower, upper = max(0, col1 - row2), min(row1, col1)
    included = []
    for x in range(lower, upper + 1):
        log_p = log_probability(x)
        if log_p is not None and log_p <= observed + 1e-12:
            included.append(log_p)
    if not included:
        return 0.0
    maximum = max(included)
    log_sum = maximum + math.log(sum(math.exp(value - maximum) for value in included))
    return min(1.0, math.exp(log_sum))


def strand_statistics(strand):
    if strand is None:
        return None, None, None
    rf, rr, af, ar = strand
    alt_total = af + ar
    abf = af / alt_total if alt_total > 0 else None
    p_value = fisher_exact_two_sided(rf, rr, af, ar)
    fs = -10.0 * math.log10(max(p_value, 1e-300)) if p_value is not None else None
    try:
        rf, rr, af, ar = rf + 1.0, rr + 1.0, af + 1.0, ar + 1.0
        symmetric = (rf * ar) / (rr * af) + (rr * af) / (rf * ar)
        sor = math.log(symmetric) + math.log(min(rf, rr) / max(rf, rr)) - math.log(min(af, ar) / max(af, ar))
    except (ValueError, ZeroDivisionError):
        sor = None
    return abf, fs, sor


def consensus_filters(metrics, config):
    filters = []
    pass_count, caller_count = metrics["pass_caller_count"], metrics["caller_count"]
    if pass_count < int(config.get("min_pass_callers", 2)):
        filters.append("LOW_CALLER_SUPPORT")
    if metrics["gt_conflict"] and config.get("filter_gt_conflict", True):
        filters.append("GT_CONFLICT")
    if config.get("filter_caller_discordance", False) and 0 < pass_count < caller_count:
        filters.append("CALLER_FILTER_DISCORDANCE")
    rules = config.get("consensus_filters", {})
    for metric, rule, low_filter, missing_filter in (
        ("dp", "min_dp", "LOW_DP", "MISSING_DP"),
        ("ao", "min_alt_depth", "LOW_ALT_DEPTH", "MISSING_ALT_DEPTH"),
        ("af", "min_af", "LOW_AF", "MISSING_AF"),
        ("gq", "min_gq", "LOW_GQ", "MISSING_GQ"),
    ):
        threshold = rules.get(rule)
        if threshold in (None, ""):
            continue
        if metrics[metric] is None:
            filters.append(missing_filter)
        elif metrics[metric] < float(threshold):
            filters.append(low_filter)
    strand_depth = metrics["strand"][2] + metrics["strand"][3] if metrics["strand"] else 0
    minimum_depth = float(rules.get("min_strand_alt_depth", 6))
    minimum_fraction = rules.get("min_alt_strand_fraction")
    if minimum_fraction not in (None, "") and metrics["abf"] is not None and strand_depth >= minimum_depth:
        threshold = float(minimum_fraction)
        if metrics["abf"] < threshold or metrics["abf"] > 1.0 - threshold:
            filters.append("ALT_STRAND_BIAS")
    if rules.get("max_fs") not in (None, "") and metrics["fs"] is not None and metrics["fs"] > float(rules["max_fs"]):
        filters.append("HIGH_FS")
    if rules.get("max_sor") not in (None, "") and metrics["sor"] is not None and metrics["sor"] > float(rules["max_sor"]):
        filters.append("HIGH_SOR")
    return list(OrderedDict.fromkeys(filters))


def build_consensus(evidences, config):
    passing = [evidence for evidence in evidences if evidence.passed]
    alt_evidence = [evidence for evidence in evidences if gt_supports_alt(evidence.gt)]
    sources = passing or alt_evidence or evidences
    gt, gt_conflict = consensus_gt([evidence.gt for evidence in sources])
    dp = rounded_median([evidence.dp for evidence in sources])
    ro = rounded_median([evidence.ro for evidence in sources])
    ao = rounded_median([evidence.ao for evidence in sources])
    gq = rounded_median([evidence.gq for evidence in sources])
    af = ao / float(ro + ao) if ro is not None and ao is not None and ro + ao > 0 else None
    strand_evidence = [evidence for evidence in sources if evidence.strand is not None]
    strand = tuple(rounded_median([evidence.strand[index] for evidence in strand_evidence]) for index in range(4)) if strand_evidence else None
    abf, fs, sor = strand_statistics(strand)
    metrics = {
        "gt": gt, "gt_conflict": gt_conflict, "dp": dp, "ro": ro, "ao": ao, "af": af, "gq": gq,
        "strand": strand, "abf": abf, "fs": fs, "sor": sor,
        "callers": [evidence.caller for evidence in evidences],
        "pass_callers": [evidence.caller for evidence in passing],
        "sources": [evidence.caller for evidence in sources],
        "strand_sources": [evidence.caller for evidence in strand_evidence],
        "caller_count": len(evidences), "pass_caller_count": len(passing),
    }
    metrics["filters"] = consensus_filters(metrics, config)
    return metrics


def format_number(value, digits=3):
    if value is None:
        return "."
    if isinstance(value, int) or float(value).is_integer():
        return str(int(value))
    return ("{:.%df}" % digits).format(float(value)).rstrip("0").rstrip(".")


def encode_raw(value):
    return "." if value in (None, "") else quote(str(value), safe="._-")


def evidence_info(evidence):
    tag, record = CALLER_TAGS[evidence.caller], evidence.record
    values = OrderedDict()
    values[tag + "_QUAL"] = encode_raw(record.qual)
    values[tag + "_FILTER_ORIG"] = encode_raw(record.original_filter)
    values[tag + "_FILTER_HELPER"] = "PASS" if evidence.passed else ",".join(evidence.helper_filters)
    values[tag + "_GT"] = evidence.gt
    values[tag + "_DP"] = format_number(evidence.dp)
    values[tag + "_AD"] = "{},{}".format(format_number(evidence.ro), format_number(evidence.ao))
    values[tag + "_AF"] = format_number(evidence.af, 6)
    values[tag + "_GQ"] = format_number(evidence.gq)
    if evidence.strand:
        rf, rr, af, ar = evidence.strand
        values[tag + "_ADF"] = "{},{}".format(format_number(rf), format_number(af))
        values[tag + "_ADR"] = "{},{}".format(format_number(rr), format_number(ar))
    else:
        values[tag + "_ADF"], values[tag + "_ADR"] = ".", "."
    values[tag + "_INFO_RAW"] = encode_raw(record.raw_info)
    values[tag + "_FORMAT_RAW"] = encode_raw(record.raw_format)
    values[tag + "_SAMPLE_RAW"] = encode_raw(record.raw_sample)
    return values


def consensus_info(evidences, metrics):
    values = OrderedDict([
        ("CALLERS", ",".join(metrics["callers"]) or "."),
        ("CALLER_COUNT", str(metrics["caller_count"])),
        ("PASS_CALLERS", ",".join(metrics["pass_callers"]) or "."),
        ("PASS_CALLER_COUNT", str(metrics["pass_caller_count"])),
        ("CONSENSUS_SOURCES", ",".join(metrics["sources"]) or "."),
        ("STRAND_SOURCES", ",".join(metrics["strand_sources"]) or "."),
        ("GT_CONFLICT", "1" if metrics["gt_conflict"] else "0"),
        ("CALLER_FILTER_DISCORDANCE", "1" if 0 < metrics["pass_caller_count"] < metrics["caller_count"] else "0"),
    ])
    for evidence in evidences:
        values.update(evidence_info(evidence))
    return ";".join("{}={}".format(key, value) for key, value in values.items())


def consensus_sample(metrics):
    ad = "{},{}".format(format_number(metrics["ro"]), format_number(metrics["ao"]))
    if metrics["strand"]:
        rf, rr, af, ar = metrics["strand"]
        adf = "{},{}".format(format_number(rf), format_number(af))
        adr = "{},{}".format(format_number(rr), format_number(ar))
    else:
        adf, adr = ".", "."
    return ":".join([
        metrics["gt"], format_number(metrics["dp"]), ad, format_number(metrics["ro"]),
        format_number(metrics["ao"]), format_number(metrics["af"], 6), format_number(metrics["gq"]),
        adf, adr, format_number(metrics["abf"], 6), format_number(metrics["fs"]), format_number(metrics["sor"]),
    ])


def chromosome_sort_key(chrom):
    clean = chrom[3:] if chrom.lower().startswith("chr") else chrom
    upper = clean.upper()
    special = {"X": 23, "Y": 24, "M": 25, "MT": 25}
    if clean.isdigit():
        return 0, int(clean), ""
    if upper in special:
        return 0, special[upper], ""
    parts = re.split(r"(\d+)", upper)
    return 1, 0, tuple(int(part) if part.isdigit() else part for part in parts)


def write_header(handle, sample_name, contigs):
    handle.write("##fileformat=VCFv4.2\n##source=Helper_merge_consensus_vcfs\n")
    for contig in OrderedDict.fromkeys(contigs):
        handle.write(contig + "\n")
    for identifier, description in FILTER_DESCRIPTIONS.items():
        handle.write('##FILTER=<ID={},Description="{}">\n'.format(identifier, description))
    info_headers = [
        ("CALLERS", ".", "String", "Callers containing the normalized variant"),
        ("CALLER_COUNT", "1", "Integer", "Number of callers containing the normalized variant"),
        ("PASS_CALLERS", ".", "String", "Callers passing caller-specific filters"),
        ("PASS_CALLER_COUNT", "1", "Integer", "Number of callers passing caller-specific filters"),
        ("CONSENSUS_SOURCES", ".", "String", "Callers used to calculate consensus FORMAT values"),
        ("STRAND_SOURCES", ".", "String", "Callers contributing forward/reverse counts"),
        ("GT_CONFLICT", "1", "Integer", "Whether consensus sources contain discordant genotypes"),
        ("CALLER_FILTER_DISCORDANCE", "1", "Integer", "Whether caller-specific filter results disagree"),
    ]
    for identifier, number, field_type, description in info_headers:
        handle.write('##INFO=<ID={},Number={},Type={},Description="{}">\n'.format(identifier, number, field_type, description))
    for caller in CALLER_ORDER:
        tag = CALLER_TAGS[caller]
        caller_headers = [
            ("QUAL", "1", "String", "original QUAL"), ("FILTER_ORIG", "1", "String", "original FILTER"),
            ("FILTER_HELPER", ".", "String", "Helper caller filters"), ("GT", "1", "String", "genotype"),
            ("DP", "1", "Float", "read depth"), ("AD", "R", "Float", "ref and alt depths"),
            ("AF", "1", "Float", "alternate allele fraction"), ("GQ", "1", "Float", "genotype quality"),
            ("ADF", "R", "Float", "forward ref and alt depths"), ("ADR", "R", "Float", "reverse ref and alt depths"),
            ("INFO_RAW", "1", "String", "percent-encoded original INFO"),
            ("FORMAT_RAW", "1", "String", "percent-encoded original FORMAT"),
            ("SAMPLE_RAW", "1", "String", "percent-encoded original sample value"),
        ]
        for suffix, number, field_type, description in caller_headers:
            handle.write('##INFO=<ID={}_{},Number={},Type={},Description="{} {}">\n'.format(tag, suffix, number, field_type, caller, description))
    format_headers = [
        ("GT", "1", "String", "Consensus genotype"), ("DP", "1", "Integer", "Median read depth"),
        ("AD", "R", "Integer", "Median ref and alt depths"), ("RO", "1", "Integer", "Median reference depth"),
        ("AO", "1", "Integer", "Median alternate depth"), ("AF", "1", "Float", "AO divided by RO plus AO"),
        ("GQ", "1", "Integer", "Median genotype quality"), ("ADF", "R", "Integer", "Median forward ref and alt depths"),
        ("ADR", "R", "Integer", "Median reverse ref and alt depths"),
        ("ABF", "1", "Float", "Fraction of alternate observations on forward strand"),
        ("FS", "1", "Float", "Two-sided Fisher strand score"), ("SOR", "1", "Float", "Strand odds ratio"),
    ]
    for identifier, number, field_type, description in format_headers:
        handle.write('##FORMAT=<ID={},Number={},Type={},Description="{}">\n'.format(identifier, number, field_type, description))
    handle.write("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t{}\n".format(sample_name))


def merge_vcfs(inputs, output_path, config, sample_name=None):
    caller_records, samples, contigs, all_keys = OrderedDict(), [], [], set()
    for caller in CALLER_ORDER:
        path = inputs.get(caller)
        if not path:
            continue
        current_sample, records, current_contigs = read_vcf(path, caller)
        samples.append(current_sample)
        contigs.extend(current_contigs)
        caller_records[caller] = records
        all_keys.update(records)
    if not caller_records:
        raise ValueError("at least one caller VCF is required")
    if sample_name is None:
        if len(set(samples)) != 1:
            raise ValueError("caller VCF sample names differ: {}".format(", ".join(samples)))
        sample_name = samples[0]
    counts = Counter()
    with open_text(output_path, "wt") as output:
        write_header(output, sample_name, contigs)
        for key in sorted(all_keys, key=lambda item: (chromosome_sort_key(item[0]), item[1], item[2], item[3])):
            records = [caller_records[caller][key] for caller in CALLER_ORDER if key in caller_records.get(caller, {})]
            evidences = [build_evidence(record, config) for record in records]
            metrics = build_consensus(evidences, config)
            first = records[0]
            filters = ";".join(metrics["filters"]) if metrics["filters"] else "PASS"
            identifier = next((record.identifier for record in records if record.identifier not in ("", ".")), ".")
            output.write("\t".join([
                first.chrom, str(first.pos), identifier, first.ref, first.alt, ".", filters,
                consensus_info(evidences, metrics), "GT:DP:AD:RO:AO:AF:GQ:ADF:ADR:ABF:FS:SOR",
                consensus_sample(metrics),
            ]) + "\n")
            counts["total"] += 1
            counts["pass" if not metrics["filters"] else "filtered"] += 1
    return dict(counts)


def deep_update(base, update):
    result = dict(base)
    for key, value in update.items():
        result[key] = deep_update(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else value
    return result


def load_config(path):
    config = dict(DEFAULT_CONFIG)
    config["caller_filters"], config["consensus_filters"] = {}, {}
    if path:
        with open(path, encoding="utf-8") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, dict):
            raise ValueError("filter config must contain a JSON object")
        config = deep_update(config, loaded)
    return config


def build_parser():
    parser = argparse.ArgumentParser(description="Merge normalized single-sample VCFs into a filtered consensus VCF")
    parser.add_argument("-g", "--gatk", help="GATK VCF")
    parser.add_argument("-f", "--freebayes", help="FreeBayes VCF")
    parser.add_argument("-d", "--deepvariant", help="DeepVariant VCF")
    parser.add_argument("-v", "--varscan", help="Legacy VarScan VCF")
    parser.add_argument("-o", "--out", required=True, help="Output consensus VCF")
    parser.add_argument("--config", help="JSON filter configuration")
    parser.add_argument("--sample-name", help="Override output sample name")
    parser.add_argument("--min-pass-callers", type=int, help="Minimum passing callers; default: 2")
    parser.add_argument("--min-dp", type=float)
    parser.add_argument("--min-alt-depth", type=float)
    parser.add_argument("--min-af", type=float)
    parser.add_argument("--min-gq", type=float)
    parser.add_argument("--min-alt-strand-fraction", type=float)
    parser.add_argument("--min-strand-alt-depth", type=float)
    parser.add_argument("--max-fs", type=float)
    parser.add_argument("--max-sor", type=float)
    return parser


def config_from_args(args):
    config = load_config(args.config)
    if args.min_pass_callers is not None:
        config["min_pass_callers"] = args.min_pass_callers
    consensus = dict(config.get("consensus_filters", {}))
    for argument, key in (
        (args.min_dp, "min_dp"), (args.min_alt_depth, "min_alt_depth"), (args.min_af, "min_af"),
        (args.min_gq, "min_gq"), (args.min_alt_strand_fraction, "min_alt_strand_fraction"),
        (args.min_strand_alt_depth, "min_strand_alt_depth"), (args.max_fs, "max_fs"), (args.max_sor, "max_sor"),
    ):
        if argument is not None:
            consensus[key] = argument
    config["consensus_filters"] = consensus
    return config


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    inputs = {"GATK": args.gatk, "FREEBAYES": args.freebayes, "DEEPVARIANT": args.deepvariant, "VARSCAN": args.varscan}
    try:
        counts = merge_vcfs(inputs, args.out, config_from_args(args), args.sample_name)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print("merge_consensus_vcfs: total={} pass={} filtered={}".format(counts.get("total", 0), counts.get("pass", 0), counts.get("filtered", 0)), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
