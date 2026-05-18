from __future__ import unicode_literals

import json
import os
import re
from pathlib import Path
from helper_next.core.project import get_project_paths


FASTQ_SUFFIXES = (".fastq", ".fastq.gz", ".fq", ".fq.gz")
ALIGNMENT_SUFFIXES = (".bam", ".sam", ".cram")
VCF_SUFFIXES = (".vcf", ".vcf.gz")
TSV_SUFFIXES = (".tsv", ".tsv.gz")

STEP_COLUMNS = {
    "prealignment": ["sample_name", "fastq_R1", "fastq_R2", "fastq_I2"],
    "alignment": ["sample_name", "fastq_R1", "fastq_R2", "fastq_I2"],
    "preprocessing": ["sample_name", "bam"],
    "variantcalling": ["sample_name", "bam"],
    "postprocessing": ["sample_name", "gatk_vcf", "freebayes_vcf", "varscan_vcf", "somatic_vcf"],
    "annotation": ["sample_name", "merged_vcf", "variants_tsv"],
    "postannotation": ["sample_name", "merged_vcf", "variants_tsv"],
}

ORGANIZATION_ROLES = {
    "only cases": ["case"],
    "case-control": ["case", "control"],
    "trio": ["case", "parent1", "parent2"],
}

MAX_RESOLVE_MATCHES = 2


def columns_for_step(step):
    return STEP_COLUMNS.get(step, STEP_COLUMNS["prealignment"])


def suffixes_for_step(step):
    if step in ("prealignment", "alignment"):
        return FASTQ_SUFFIXES
    if step in ("preprocessing", "variantcalling"):
        return ALIGNMENT_SUFFIXES
    if step == "postprocessing":
        return VCF_SUFFIXES
    if step in ("annotation", "postannotation"):
        return VCF_SUFFIXES + TSV_SUFFIXES
    return ()


def resolve_file_paths(files, extra_roots=None):
    roots = resolve_search_roots(extra_roots or [])
    resolved = []
    warnings = []
    cache = {}

    for item in [file_name.strip() for file_name in files if file_name and file_name.strip()]:
        if is_absolute_path(item) and Path(item).exists():
            resolved.append(item)
            continue

        name = Path(item).name
        if name not in cache:
            cache[name] = find_file_matches(name, roots)
        matches = cache[name]

        if len(matches) == 1:
            resolved.append(str(matches[0]))
        elif len(matches) > 1:
            resolved.append(item)
            warnings.append("Multiple files named {} found; using browser value only".format(name))
        else:
            resolved.append(item)
            warnings.append("Could not resolve full path for {}".format(name))

    return resolved, warnings


def resolve_search_roots(extra_roots):
    roots = []
    for root in extra_roots:
        add_search_root(roots, root)
    try:
        paths = get_project_paths()
        add_search_root(roots, paths.files)
        add_search_root(roots, paths.root)
    except Exception:
        pass
    add_search_root(roots, Path.home())
    return roots


def add_search_root(roots, root):
    path = Path(root).expanduser().resolve()
    if path.exists() and path.is_dir() and path not in roots:
        roots.append(path)


def find_file_matches(name, roots):
    matches = []
    skipped_dirs = {
        ".cache",
        ".conda",
        ".git",
        ".local",
        ".mypy_cache",
        ".pytest_cache",
        "__pycache__",
        "envs",
        "miniconda3",
        "node_modules",
    }
    for root in roots:
        for current, dirs, filenames in os.walk(str(root)):
            dirs[:] = [directory for directory in dirs if directory not in skipped_dirs and not directory.startswith(".")]
            if name in filenames:
                matches.append((Path(current) / name).resolve())
                if len(matches) >= MAX_RESOLVE_MATCHES:
                    return matches
    return matches


def is_absolute_path(path):
    return Path(path).is_absolute() or re.match(r"^[A-Za-z]:[\\/]", path) is not None


def detect_file_type(path):
    lowered = path.lower()
    if lowered.endswith(FASTQ_SUFFIXES):
        return "fastq"
    if lowered.endswith(ALIGNMENT_SUFFIXES):
        return "alignment"
    if lowered.endswith(VCF_SUFFIXES):
        return "vcf"
    if lowered.endswith(TSV_SUFFIXES):
        return "tsv"
    return "unknown"


def is_step_compatible(step, file_type):
    if file_type == "fastq":
        return step in ("prealignment", "alignment")
    if file_type == "alignment":
        return step in ("preprocessing", "variantcalling")
    if file_type == "vcf":
        return step in ("postprocessing", "annotation", "postannotation")
    if file_type == "tsv":
        return step in ("annotation", "postannotation")
    return False


def sample_name_from_fastq(path):
    name = Path(path).name
    sample = re.split(r"_S(\d+)", name)[0]
    if sample == name:
        sample = strip_known_suffixes(name, FASTQ_SUFFIXES)
        sample = re.split(r"([._-](R1|R2|I2)([._-]|$))", sample, flags=re.IGNORECASE)[0]
    return normalize_sample_name(sample)


def sample_name_from_bam(path):
    return normalize_sample_name(strip_known_suffixes(Path(path).name, ALIGNMENT_SUFFIXES))


def sample_name_from_vcf(path):
    sample = strip_known_suffixes(Path(path).name, VCF_SUFFIXES)
    sample = strip_analysis_tokens(sample)
    return normalize_sample_name(sample)


def sample_name_from_tsv(path):
    sample = strip_known_suffixes(Path(path).name, TSV_SUFFIXES)
    sample = strip_analysis_tokens(sample)
    return normalize_sample_name(sample)


def strip_known_suffixes(name, suffixes):
    lowered = name.lower()
    for suffix in sorted(suffixes, key=len, reverse=True):
        if lowered.endswith(suffix):
            return name[: -len(suffix)]
    return name


def normalize_sample_name(name):
    return name.strip().replace("-", "_")


def strip_analysis_tokens(name):
    return re.sub(
        r"([._-](gatk|haplotypecaller|freebayes|varscan|somatic|mutect2?|merged|variants?))+$",
        "",
        name,
        flags=re.IGNORECASE,
    )


def rows_from_files(step, files):
    clean_files = [item.strip() for item in files if item and item.strip()]
    if not clean_files:
        return [], []

    warnings = []
    compatible_files = []

    for path in clean_files:
        file_type = detect_file_type(path)
        if is_step_compatible(step, file_type):
            compatible_files.append(path)
        elif file_type == "unknown":
            warnings.append("Unsupported file type: {}".format(path))
        else:
            warnings.append("{} file ignored for {} step: {}".format(file_type.upper(), step, path))

    compatible_types = {detect_file_type(path) for path in compatible_files}
    if not compatible_files:
        return [], warnings or ["No compatible files for {} step".format(step)]

    if compatible_types <= {"fastq"}:
        rows, row_warnings = _fastq_rows(compatible_files)
    elif compatible_types <= {"alignment"}:
        rows, row_warnings = _bam_rows(compatible_files), []
    elif step == "postprocessing" and compatible_types <= {"vcf"}:
        rows, row_warnings = _postprocessing_rows(compatible_files)
    elif step in ("annotation", "postannotation") and compatible_types <= {"vcf", "tsv"}:
        rows, row_warnings = _annotation_rows(compatible_files)
    else:
        rows, row_warnings = [], ["Mixed compatible file types are not valid for {} step".format(step)]

    warnings.extend(row_warnings)
    return rows, warnings


def _fastq_rows(files):
    file_set = set(files)
    rows = []
    for path in sorted(files):
        name = Path(path).name
        if not is_fastq_read(name, "R1"):
            continue
        folder = str(Path(path).parent)
        sample = sample_name_from_fastq(path)
        r2 = matching_fastq_path(folder, name, "R1", "R2")
        i2 = matching_fastq_path(folder, name, "R1", "I2")
        rows.append(
            {
                "sample_name": sample,
                "fastq_R1": path,
                "fastq_R2": r2 if r2 in file_set else "",
                "fastq_I2": i2 if i2 in file_set else "",
            }
        )
    warnings = []
    r1_samples = {row["sample_name"] for row in rows}
    for path in files:
        if is_fastq_read(Path(path).name, "R2") and sample_name_from_fastq(path) not in r1_samples:
            warnings.append("R2 without matching R1 ignored: {}".format(path))
    return sorted(rows, key=lambda row: row["sample_name"]), warnings


def is_fastq_read(name, read):
    return re.search(r"(^|[._-]){}([._-]|$)".format(read), name, flags=re.IGNORECASE) is not None


def matching_fastq_path(folder, name, source_read, target_read):
    paired_name = re.sub(
        r"(^|[._-]){}([._-]|$)".format(source_read),
        lambda match: "{}{}{}".format(match.group(1), target_read, match.group(2)),
        name,
        count=1,
        flags=re.IGNORECASE,
    )
    return str(Path(folder) / paired_name)


def _bam_rows(files):
    return sorted(
        [{"sample_name": sample_name_from_bam(path), "bam": path} for path in files],
        key=lambda row: row["sample_name"],
    )


def _postprocessing_rows(files):
    rows_by_sample = {}
    warnings = []
    for path in files:
        sample = sample_name_from_vcf(path)
        row = rows_by_sample.setdefault(
            sample,
            {"sample_name": sample, "gatk_vcf": "", "freebayes_vcf": "", "varscan_vcf": "", "somatic_vcf": ""},
        )
        column = postprocessing_column(path)
        if column:
            row[column] = path
        else:
            warnings.append("VCF caller not recognized, leaving unassigned: {}".format(path))
    return sorted(rows_by_sample.values(), key=lambda row: row["sample_name"]), warnings


def postprocessing_column(path):
    lowered = Path(path).name.lower()
    if "gatk" in lowered or "haplotypecaller" in lowered:
        return "gatk_vcf"
    if "freebayes" in lowered or "free" in lowered:
        return "freebayes_vcf"
    if "varscan" in lowered:
        return "varscan_vcf"
    if "somatic" in lowered or "mutect" in lowered:
        return "somatic_vcf"
    return None


def _annotation_rows(files):
    rows_by_sample = {}
    for path in files:
        file_type = detect_file_type(path)
        sample = sample_name_from_vcf(path) if file_type == "vcf" else sample_name_from_tsv(path)
        row = rows_by_sample.setdefault(sample, {"sample_name": sample, "merged_vcf": "", "variants_tsv": ""})
        if file_type == "vcf":
            row["merged_vcf"] = path
        elif file_type == "tsv":
            row["variants_tsv"] = path
    return sorted(rows_by_sample.values(), key=lambda row: row["sample_name"]), []


def build_samplesheet(step, organization, rows, organization_rows=None):
    organization_rows = organization_rows or default_organization_rows(rows, organization)
    sample_list = [row["sample_id"] for row in organization_rows if row.get("sample_id")]
    samples_by_name = {row.get("sample_name"): row for row in rows if row.get("sample_name")}
    roles = ORGANIZATION_ROLES.get(organization, ORGANIZATION_ROLES["only cases"])

    step_payload = {}
    for org_row in organization_rows:
        sample_id = org_row.get("sample_id")
        if not sample_id:
            continue
        step_payload[sample_id] = {}
        for role in roles:
            source_name = org_row.get(role, "")
            source = samples_by_name.get(source_name)
            if source:
                step_payload[sample_id][role] = _row_payload(step, source)

    return {
        "sample_list": sample_list,
        "sample_organization": organization,
        step: step_payload,
    }


def default_organization_rows(rows, organization):
    names = [row.get("sample_name", "") for row in rows if row.get("sample_name")]
    if organization == "case-control":
        return [
            {"sample_id": names[index], "case": names[index], "control": names[index + 1] if index + 1 < len(names) else ""}
            for index in range(0, len(names), 2)
        ]
    if organization == "trio":
        return [
            {
                "sample_id": names[index],
                "case": names[index],
                "parent1": names[index + 1] if index + 1 < len(names) else "",
                "parent2": names[index + 2] if index + 2 < len(names) else "",
            }
            for index in range(0, len(names), 3)
        ]
    return [{"sample_id": name, "case": name} for name in names]


def _row_payload(step, row):
    return {column: row.get(column, "") for column in columns_for_step(step)}


def load_samplesheet_text(content, selected_step=None):
    data = json.loads(content)
    step = selected_step if selected_step in STEP_COLUMNS else next((name for name in STEP_COLUMNS if name in data), "prealignment")
    organization = data.get("sample_organization", "only cases")
    rows = flatten_samplesheet(data, step)
    return {
        "step": step,
        "organization": organization,
        "rows": rows,
        "organization_rows": organization_rows_from_samplesheet(data, step, organization),
        "samplesheet": data,
    }


def flatten_samplesheet(data, step):
    seen = {}
    step_data = data.get(step, {})
    roles = ORGANIZATION_ROLES.get(data.get("sample_organization", "only cases"), ORGANIZATION_ROLES["only cases"])
    for sample_id in data.get("sample_list", []):
        grouped = step_data.get(sample_id, {})
        for role in roles:
            row = grouped.get(role)
            if row and row.get("sample_name"):
                seen[row["sample_name"]] = row
    return [seen[name] for name in sorted(seen)]


def organization_rows_from_samplesheet(data, step, organization):
    rows = []
    roles = ORGANIZATION_ROLES.get(organization, ORGANIZATION_ROLES["only cases"])
    for sample_id in data.get("sample_list", []):
        grouped = data.get(step, {}).get(sample_id, {})
        row = {"sample_id": sample_id}
        for role in roles:
            row[role] = grouped.get(role, {}).get("sample_name", "")
        rows.append(row)
    return rows
