"""Streaming construction of a run-local variant index from VCF artifacts."""
import gzip
import hashlib
import re
from pathlib import Path

from helper_variants import store as variant_store


INDEX_RELATIVE_PATH = Path("results") / "VARIANT_VIEWER" / "variants.sqlite"
STAGES = (
    ("annotation", Path("results") / "ANNOTATION", ("*.annotated.vcf", "*.annotated.vcf.gz")),
    ("postprocessing", Path("results") / "POSTPROCESSING", ("*.postprocessed.vcf", "*.postprocessed.vcf.gz")),
    ("variantcalling", Path("results") / "VARIANTCALLING", ("*.vcf", "*.vcf.gz")),
)
TSV_STAGES = (
    ("annotation", Path("results") / "ANNOTATION", ("*.annotated.tsv", "*.annotated.tsv.gz")),
    ("postprocessing", Path("results") / "POSTPROCESSING", ("*.variants.tsv", "*.variants.tsv.gz")),
)
FORMAT_RE = re.compile(
    r"(?:Format|Functional annotations)[^:]*:\s*['\"]?([^'\">]+)", re.IGNORECASE
)


class VariantIndexError(ValueError):
    pass


class SourceChangedError(VariantIndexError):
    pass


class IndexedFasta:
    """Small random-access FASTA reader backed by a standard .fai index."""

    def __init__(self, path):
        self.path = Path(path)
        self.handle = open(str(self.path), "rb")
        self.contigs = {}
        with open(str(self.path) + ".fai", "r", encoding="utf-8") as index:
            for line in index:
                fields = line.rstrip("\r\n").split("\t")
                if len(fields) >= 5:
                    self.contigs[fields[0]] = tuple(int(value) for value in fields[1:5])

    def close(self):
        self.handle.close()

    def sequence(self, chromosome, position, length):
        name = self._contig(chromosome)
        contig_length, offset, line_bases, line_width = self.contigs[name]
        start = int(position) - 1
        if start < 0 or length < 1 or start + length > contig_length:
            raise VariantIndexError("reference interval is outside {}".format(name))
        chunks = []
        remaining = length
        while remaining:
            line_number, column = divmod(start, line_bases)
            take = min(remaining, line_bases - column)
            self.handle.seek(offset + line_number * line_width + column)
            chunks.append(self.handle.read(take).decode("ascii"))
            start += take
            remaining -= take
        return "".join(chunks).upper()

    def _contig(self, chromosome):
        chromosome = str(chromosome)
        for candidate in (chromosome, "chr" + chromosome, chromosome[3:] if chromosome.startswith("chr") else ""):
            if candidate and candidate in self.contigs:
                return candidate
        raise VariantIndexError("chromosome {!r} is absent from the reference FASTA".format(chromosome))


def index_path(run_dir):
    return Path(run_dir).resolve() / INDEX_RELATIVE_PATH


def discover_run_vcfs(run_dir):
    """Return the best available VCF stage, confined to known result folders."""
    root = Path(run_dir).resolve()
    if not root.is_dir():
        raise VariantIndexError("run directory is not available: {}".format(root))
    for stage, relative_dir, patterns in STAGES:
        directory = root / relative_dir
        found = []
        for pattern in patterns:
            found.extend(directory.glob(pattern))
        found = sorted(
            path for path in set(found)
            if path.is_file() and not path.name.endswith((".g.vcf", ".g.vcf.gz"))
        )
        if found:
            return [{"path": path, "stage": stage, "kind": "vcf"} for path in found]
    for stage, relative_dir, patterns in TSV_STAGES:
        directory = root / relative_dir
        found = []
        for pattern in patterns:
            found.extend(directory.glob(pattern))
        found = sorted(path for path in set(found) if path.is_file())
        if found:
            return [{"path": path, "stage": stage, "kind": "tsv"} for path in found]
    return []


def reference_build(record):
    candidates = (
        record.get("run_config", {}).get("reference_version"),
        record.get("run_config", {}).get("reference_build"),
        record.get("pipeline_config", {}).get("reference_version"),
        record.get("request", {}).get("reference_version"),
    )
    for candidate in candidates:
        if candidate and str(candidate).strip():
            return str(candidate).strip()
    return "unknown"


def index_run(record, batch_size=500):
    """Index the best VCF artifacts for one archived analysis record."""
    run_dir = Path(record["run_dir"]).resolve()
    artifacts = discover_run_vcfs(run_dir)
    if not artifacts:
        raise VariantIndexError("no VCF artifacts found in known result directories")
    database = index_path(run_dir)
    build = reference_build(record)
    preferred_run_key = str(record.get("run_id") or run_dir.name)
    sample_metadata = _sample_metadata(record.get("samples", []))
    summaries = []
    fasta = open_reference(record, build)
    try:
        with variant_store.connect(database, "run") as db:
            run_id, run_key = _physical_run(
                db, preferred_run_key, build, run_dir,
                {
                    "run_id": record.get("run_id", run_dir.name),
                    "history_id": record.get("id", ""),
                    "pipeline_config": record.get("pipeline_config", {}),
                    "run_config": record.get("run_config", {}),
                    "reference_fasta": str(fasta.path) if fasta else "",
                    "reference_validated": fasta is not None,
                },
            )
            for artifact in artifacts:
                index_function = index_vcf if artifact["kind"] == "vcf" else index_tsv
                summaries.append(index_function(
                    db, run_id, run_key, run_dir, artifact["path"], artifact["stage"],
                    build, sample_metadata, batch_size, fasta,
                ))
    finally:
        if fasta:
            fasta.close()
    return {
        "status": "complete",
        "database": str(database),
        "reference_build": build,
        "reference_validated": fasta is not None,
        "sources": summaries,
    }


def _physical_run(db, preferred_run_key, build, run_dir, metadata):
    """Reuse one database run for every history attempt sharing a workdir."""
    row = db.execute(
        "SELECT r.id, r.run_key, r.reference_build, COUNT(s.id) AS source_count "
        "FROM runs r LEFT JOIN index_sources s ON s.run_id = r.id "
        "WHERE r.source_path = ? GROUP BY r.id "
        "ORDER BY source_count DESC, r.id LIMIT 1",
        (str(run_dir),),
    ).fetchone()
    if row is not None:
        if row["reference_build"] != build:
            raise VariantIndexError(
                "run directory is already indexed with reference build {!r}".format(
                    row["reference_build"]
                )
            )
        return row["id"], row["run_key"]
    run_id = variant_store.register_run(
        db, preferred_run_key, build, str(run_dir), metadata
    )
    return run_id, preferred_run_key


def index_status(run_dir):
    database = index_path(run_dir)
    if not database.is_file():
        return {"status": "unindexed", "database": str(database), "sources": []}
    with variant_store.connect(database) as db:
        sources = [dict(row) for row in db.execute(
            "SELECT relative_path, stage, size_bytes, sha256, status, records_processed, error, updated_at "
            "FROM index_sources ORDER BY relative_path"
        )]
        counts = {row["status"] for row in sources}
        status = "failed" if "failed" in counts else "indexing" if "indexing" in counts else (
            "complete" if sources and counts == {"complete"} else "pending"
        )
        return {
            "status": status,
            "database": str(database),
            "schema_version": variant_store.store_info(db)["schema_version"],
            "sources": sources,
        }


def index_vcf(db, run_id, run_key, run_dir, path, stage, build, sample_metadata,
              batch_size=500, reference_reader=None):
    # Keep the lexical path for server-created archive links. Resolving the
    # symlink here would incorrectly move the source outside the managed run.
    path = Path(path).absolute()
    relative_path = _relative_to(path, Path(run_dir).resolve())
    stat = path.stat()
    digest = sha256_file(path)
    source = db.execute(
        "SELECT * FROM index_sources WHERE run_id = ? AND relative_path = ?",
        (run_id, relative_path),
    ).fetchone()
    if source and (source["sha256"] != digest or source["size_bytes"] != stat.st_size):
        raise SourceChangedError(
            "indexed source changed; rebuild is required: {}".format(relative_path)
        )
    if source and source["status"] == "complete":
        return _source_summary(source, skipped=True)
    if source is None:
        db.execute(
            "INSERT INTO index_sources "
            "(run_id, relative_path, stage, size_bytes, mtime_ns, sha256, status, records_processed, error, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, '', ?)",
            (run_id, relative_path, stage, stat.st_size, _mtime_ns(stat), digest, variant_store.utc_now()),
        )
        source = db.execute(
            "SELECT * FROM index_sources WHERE run_id = ? AND relative_path = ?",
            (run_id, relative_path),
        ).fetchone()
    source_id = source["id"]
    resume_after = source["records_processed"]
    db.execute(
        "UPDATE index_sources SET status = 'indexing', error = '', updated_at = ? WHERE id = ?",
        (variant_store.utc_now(), source_id),
    )
    db.commit()

    processed = 0
    completed = resume_after
    committed = resume_after
    try:
        header, records = read_vcf(path)
        release_id = _annotation_release(db, run_key, build, digest, header)
        sample_names = header["samples"] or [_sample_name_from_path(path)]
        caller = _caller_from_path(path, stage)
        analyses = _register_analyses(
            db, run_id, run_key, sample_names, sample_metadata, stage, relative_path
        )
        for processed, fields in enumerate(records, 1):
            if processed <= resume_after:
                continue
            _index_record(db, fields, header, build, analyses, release_id, caller, reference_reader)
            completed = processed
            if processed % batch_size == 0:
                _checkpoint(db, source_id, processed)
                db.commit()
                committed = processed
        _checkpoint(db, source_id, completed, "complete")
        db.commit()
    except Exception as exc:
        db.rollback()
        db.execute(
            "UPDATE index_sources SET status = 'failed', records_processed = ?, error = ?, updated_at = ? "
            "WHERE id = ?",
            (committed, str(exc)[:2000], variant_store.utc_now(), source_id),
        )
        db.commit()
        raise
    row = db.execute("SELECT * FROM index_sources WHERE id = ?", (source_id,)).fetchone()
    return _source_summary(row)


def index_tsv(db, run_id, run_key, run_dir, path, stage, build, sample_metadata,
              batch_size=500, reference_reader=None):
    """Index the compact TSV fallback emitted by current postprocessing steps."""
    path = Path(path).resolve()
    relative_path = _relative_to(path, Path(run_dir).resolve())
    stat = path.stat()
    digest = sha256_file(path)
    source = db.execute(
        "SELECT * FROM index_sources WHERE run_id = ? AND relative_path = ?",
        (run_id, relative_path),
    ).fetchone()
    if source and (source["sha256"] != digest or source["size_bytes"] != stat.st_size):
        raise SourceChangedError(
            "indexed source changed; rebuild is required: {}".format(relative_path)
        )
    if source and source["status"] == "complete":
        return _source_summary(source, skipped=True)
    if source is None:
        db.execute(
            "INSERT INTO index_sources "
            "(run_id, relative_path, stage, size_bytes, mtime_ns, sha256, status, records_processed, error, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, '', ?)",
            (run_id, relative_path, stage, stat.st_size, _mtime_ns(stat), digest, variant_store.utc_now()),
        )
        source = db.execute(
            "SELECT * FROM index_sources WHERE run_id = ? AND relative_path = ?",
            (run_id, relative_path),
        ).fetchone()
    source_id = source["id"]
    resume_after = source["records_processed"]
    db.execute(
        "UPDATE index_sources SET status = 'indexing', error = '', updated_at = ? WHERE id = ?",
        (variant_store.utc_now(), source_id),
    )
    db.commit()

    processed = 0
    completed = resume_after
    committed = resume_after
    handle = gzip.open(str(path), "rt", encoding="utf-8", errors="replace") \
        if str(path).endswith(".gz") else open(str(path), "r", encoding="utf-8", errors="replace")
    try:
        header_line = handle.readline()
        if not header_line:
            raise VariantIndexError("empty variant TSV: {}".format(path))
        columns = [value.strip().lower() for value in header_line.rstrip("\r\n").split("\t")]
        required = ("chrom", "pos", "ref", "alt")
        if any(name not in columns for name in required):
            raise VariantIndexError("variant TSV requires chrom, pos, ref, and alt columns: {}".format(path))
        sample_name = _sample_name_from_path(path)
        analyses = _register_analyses(
            db, run_id, run_key, [sample_name], sample_metadata, stage, relative_path
        )
        release_id = variant_store.register_annotation_release(
            db, "{}:original:{}".format(run_key, digest[:16]), "compact-tsv", build,
            resources={"source_sha256": digest},
        )
        pseudo_header = {"samples": [], "info_layouts": {}}
        caller = _caller_from_path(path, stage)
        for line in handle:
            if not line.strip():
                continue
            processed += 1
            if processed <= resume_after:
                continue
            values = line.rstrip("\r\n").split("\t")
            row = dict(zip(columns, values))
            fields = [
                row.get("chrom", ""), row.get("pos", ""), row.get("id", "."),
                row.get("ref", ""), row.get("alt", ""), row.get("qual", "."),
                row.get("filter", ""), row.get("info", "."),
            ]
            _index_record(
                db, fields, pseudo_header, build, analyses, release_id, caller, reference_reader
            )
            completed = processed
            if processed % batch_size == 0:
                _checkpoint(db, source_id, processed)
                db.commit()
                committed = processed
        _checkpoint(db, source_id, completed, "complete")
        db.commit()
    except Exception as exc:
        db.rollback()
        db.execute(
            "UPDATE index_sources SET status = 'failed', records_processed = ?, error = ?, updated_at = ? "
            "WHERE id = ?",
            (committed, str(exc)[:2000], variant_store.utc_now(), source_id),
        )
        db.commit()
        raise
    finally:
        handle.close()
    row = db.execute("SELECT * FROM index_sources WHERE id = ?", (source_id,)).fetchone()
    return _source_summary(row)


def read_vcf(path):
    handle = gzip.open(str(path), "rt", encoding="utf-8", errors="replace") \
        if str(path).endswith(".gz") else open(str(path), "r", encoding="utf-8", errors="replace")
    info_layouts = {}
    info_definitions = {}
    metadata = []
    samples = []

    def records():
        try:
            for line_number, line in enumerate(handle, 1):
                if line.startswith("##INFO=<"):
                    info_id = _header_value(line, "ID")
                    info_definitions[info_id] = {"number": _header_value(line, "Number"), "definition": line.strip()}
                    if info_id in ("ANN", "CSQ"):
                        match = FORMAT_RE.search(line)
                        if match:
                            info_layouts[info_id] = [item.strip() for item in match.group(1).strip().split("|")]
                    continue
                if line.startswith("##"):
                    metadata.append(line.strip())
                if line.startswith("#CHROM"):
                    columns = line.rstrip("\r\n").split("\t")
                    samples[:] = columns[9:]
                    break
            else:
                raise VariantIndexError("VCF header has no #CHROM line: {}".format(path))
            for line_number, line in enumerate(handle, line_number + 1):
                if not line.strip() or line.startswith("#"):
                    continue
                fields = line.rstrip("\r\n").split("\t")
                if len(fields) < 8:
                    raise VariantIndexError("invalid VCF record at {}:{}".format(path, line_number))
                yield fields
        finally:
            handle.close()

    iterator = records()
    # Advance header parsing now so callers can inspect layouts and sample names.
    try:
        first = next(iterator)
    except StopIteration:
        first = None

    def with_first():
        if first is not None:
            yield first
        for item in iterator:
            yield item

    return {"info_layouts": info_layouts, "info_definitions": info_definitions, "metadata": metadata, "samples": samples}, with_first()


def normalize_allele(position, reference, alternate, chromosome=None, reference_reader=None):
    position = int(position)
    reference = reference.upper()
    alternate = alternate.upper()
    if not reference or not alternate or alternate.startswith("<") or "[" in alternate or "]" in alternate:
        return position, reference, alternate
    while reference[-1] == alternate[-1] and (len(reference) > 1 or len(alternate) > 1):
        if len(reference) == 1 or len(alternate) == 1:
            if reference_reader is None or chromosome is None or position <= 1:
                break
            previous = reference_reader.sequence(chromosome, position - 1, 1)
            reference, alternate = previous + reference, previous + alternate
            position -= 1
        reference, alternate = reference[:-1], alternate[:-1]
    while len(reference) > 1 and len(alternate) > 1 and reference[0] == alternate[0]:
        reference, alternate = reference[1:], alternate[1:]
        position += 1
    return position, reference, alternate


def open_reference(record, build):
    candidates = [record.get("run_config", {}).get("reference_fasta")]
    tools = record.get("tools_config", {})
    if isinstance(tools.get(build), dict):
        candidates.append(tools[build].get("fasta"))
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file() and Path(str(path) + ".fai").is_file() and not str(path).endswith(".gz"):
            return IndexedFasta(path)
    return None


def sha256_file(path):
    digest = hashlib.sha256()
    with open(str(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _index_record(db, fields, header, build, analyses, release_id, caller, reference_reader=None):
    chromosome, position, identifier, reference, alt_field, quality, filter_status, info_field = fields[:8]
    alternatives = alt_field.split(",")
    info = _parse_info(info_field)
    format_keys = fields[8].split(":") if len(fields) > 8 else []
    sample_fields = fields[9:] if len(fields) > 9 else []
    if reference_reader is not None and not reference.startswith("<"):
        observed = reference_reader.sequence(chromosome, int(position), len(reference))
        if observed != reference.upper():
            raise VariantIndexError(
                "reference mismatch at {}:{} (VCF {}, FASTA {})".format(
                    chromosome, position, reference, observed
                )
            )
    for alt_index, alternate in enumerate(alternatives, 1):
        normalized_position, normalized_ref, normalized_alt = normalize_allele(
            position, reference, alternate, chromosome, reference_reader
        )
        variant_metadata = {
            "vcf_id": identifier,
            "original_vcf": {
                "chromosome": chromosome, "position": position, "reference": reference,
                "alternate": alternate, "alt_index": alt_index,
                "alternates": alternatives, "qual": quality, "filter": filter_status,
                "info": info, "format_keys": format_keys,
            },
            "quality_metrics": {
                key: info[key] for key in ("FS", "SOR") if info.get(key) not in (None, "")
            },
        }
        clinvar_metadata = _clinvar_metadata(info) if len(alternatives) == 1 else {}
        if clinvar_metadata:
            variant_metadata["clinvar"] = clinvar_metadata
        variant_id = variant_store.get_or_create_variant(
            db, build, chromosome, normalized_position, normalized_ref, normalized_alt,
            _variant_type(normalized_ref, normalized_alt), variant_metadata,
        )
        _record_annotations(
            db, variant_id, release_id, alternate, alternatives, info, header["info_layouts"], reference
        )
        if sample_fields:
            for sample_name, sample_field in zip(header["samples"], sample_fields):
                call = dict(zip(format_keys, sample_field.split(":")))
                if not _carries_allele(call.get("GT", ""), alt_index):
                    continue
                _record_call(
                    db, analyses[sample_name], variant_id, call, alt_index,
                    _float_or_none(quality), filter_status, caller,
                )
        else:
            only_analysis = next(iter(analyses.values()))
            variant_store.record_call(
                db, only_analysis, variant_id, caller=caller, filter_status=filter_status,
                quality=_float_or_none(quality), metadata={"site_only": True},
            )


def _record_call(db, analysis_id, variant_id, call, alt_index, quality, filter_status, caller):
    genotype = call.get("GT", "")
    alleles = re.split(r"[/|]", genotype)
    dosage = sum(1 for allele in alleles if allele == str(alt_index))
    called = [allele for allele in alleles if allele != "."]
    if dosage == len(called) and called:
        zygosity = "hom_alt"
    elif dosage:
        zygosity = "het"
    else:
        zygosity = "unknown"
    ad = _number_list(call.get("AD", ""), int)
    af = _number_list(call.get("AF", ""), float)
    variant_store.record_call(
        db, analysis_id, variant_id, caller=caller, genotype=genotype, phased="|" in genotype,
        zygosity=zygosity, depth=_int_or_none(call.get("DP")),
        reference_depth=ad[0] if ad else None,
        alternate_depth=ad[alt_index] if len(ad) > alt_index else None,
        allele_fraction=af[alt_index - 1] if len(af) >= alt_index else None,
        genotype_quality=_float_or_none(call.get("GQ")), quality=quality,
        filter_status=filter_status, metadata={"format": call, "allele_number": alt_index},
    )


def _record_annotations(db, variant_id, release_id, alternate, alternatives, info, layouts, reference=""):
    for tag in ("ANN", "CSQ"):
        raw = info.get(tag)
        layout = layouts.get(tag)
        if not raw or not layout:
            continue
        for value in raw.split(","):
            values = value.split("|")
            data = dict(zip(layout, values))
            allele = _pick(data, "Allele")
            if len(alternatives) > 1:
                allele_number = data.get("ALLELE_NUM")
                if allele_number:
                    if allele_number != str(alternatives.index(alternate) + 1):
                        continue
                else:
                    # VEP may minimize indels; ambiguous labels are not assigned to
                    # multiple ALT alleles. The original INFO remains available.
                    matches = [a for a in alternatives if allele in (a, _annotation_allele(reference, a))]
                    if matches != [alternate]:
                        continue
            consequence = _pick(data, "Annotation", "Consequence")
            population_af = _float_or_none(_pick(data, "MAX_AF", "gnomAD_AF", "AF"))
            variant_store.record_annotation(
                db, variant_id, release_id, allele=allele,
                gene=_pick(data, "Gene_Name", "SYMBOL", "Gene"),
                transcript=_pick(data, "Feature_ID", "Feature", "Transcript"),
                consequence=consequence,
                impact=_pick(data, "Annotation_Impact", "IMPACT"),
                hgvsc=_pick(data, "HGVS.c", "HGVSc"), hgvsp=_pick(data, "HGVS.p", "HGVSp"),
                clinical_significance=_pick(data, "CLIN_SIG", "ClinVar_CLNSIG"),
                population_af=population_af,
                canonical=_pick(data, "CANONICAL").upper() in ("YES", "Y", "1"),
                metadata={"source": tag, "fields": data},
            )


def _annotation_release(db, run_key, build, digest, header):
    tags = sorted(header["info_layouts"])
    annotator = "+".join(tags) if tags else "unannotated"
    return variant_store.register_annotation_release(
        db, "{}:original:{}".format(run_key, digest[:16]), annotator, build,
        resources={"source_sha256": digest, "info_tags": tags,
                   "info_definitions": header.get("info_definitions", {}), "header_metadata": header.get("metadata", [])},
    )


def _register_analyses(db, run_id, run_key, names, metadata, stage, source):
    analyses = {}
    for name in names:
        details = metadata.get(name, {})
        sample_key = "{}:{}".format(run_key, name)
        sample_id = variant_store.register_sample(
            db, sample_key, name, specimen_type=str(details.get("specimen_type", "")), metadata=details,
        )
        analyses[name] = variant_store.register_analysis(
            db, sample_key, run_id, sample_id, str(details.get("role", "")),
            {"stage": stage, "source": source}, {},
        )
    return analyses


def _sample_metadata(samples):
    return {
        str(row.get("sample_name") or row.get("sample_id")): dict(row)
        for row in samples if row.get("sample_name") or row.get("sample_id")
    }


def _parse_info(value):
    result = {}
    if value in ("", "."):
        return result
    for item in value.split(";"):
        key, separator, field_value = item.partition("=")
        result[key] = field_value if separator else True
    return result


def _clinvar_metadata(info):
    result = {}
    for key, value in info.items():
        normalized = str(key).upper().replace("-", "_")
        if (
            normalized.startswith(("CLN", "ONC", "SCI"))
            or normalized in {"ALLELEID", "CLINVAR_VARIATION_ID", "CLINVARVARIATIONID"}
        ) and value not in (None, "", ".", False):
            result[str(key)] = value
    return result


def _header_value(line, key):
    match = re.search(r"(?:^|[,<]){}=([^,>]+)".format(re.escape(key)), line)
    return match.group(1).strip('"') if match else ""


def _pick(data, *names):
    for name in names:
        value = data.get(name)
        if value not in (None, ""):
            return value
    return ""


def _carries_allele(genotype, alt_index):
    if not genotype:
        return True
    if genotype in (".", "./.", ".|."):
        return False
    return str(alt_index) in re.split(r"[/|]", genotype)


def _number_list(value, conversion):
    if not value or value == ".":
        return []
    result = []
    for item in value.split(","):
        try:
            result.append(conversion(item))
        except (TypeError, ValueError):
            result.append(None)
    return result


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _variant_type(reference, alternate):
    if alternate.startswith("<"):
        return "symbolic"
    if len(reference) == len(alternate) == 1:
        return "SNV"
    if len(reference) == len(alternate):
        return "MNV"
    return "indel"


def _trimmed_alt(alternate):
    return alternate[1:] if len(alternate) > 1 else alternate


def _annotation_allele(reference, alternate):
    ref, alt = reference, alternate
    while ref and alt and ref[0] == alt[0]:
        ref, alt = ref[1:], alt[1:]
    while ref and alt and ref[-1] == alt[-1]:
        ref, alt = ref[:-1], alt[:-1]
    return alt or "-"


def _sample_name_from_path(path):
    name = path.name
    for suffix in (".vcf.gz", ".vcf", ".tsv.gz", ".tsv", ".annotated", ".postprocessed", ".variants"):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    return name or "site-only"


def _caller_from_path(path, stage):
    name = path.name.lower()
    for caller in ("deepvariant", "freebayes", "mutect2", "varscan", "gatk"):
        if caller in name:
            return caller.upper()
    return stage


def _relative_to(path, root):
    try:
        return str(path.relative_to(root))
    except ValueError:
        raise VariantIndexError("variant source is outside the run directory")


def _mtime_ns(stat):
    return getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1000000000))


def _checkpoint(db, source_id, processed, status="indexing"):
    db.execute(
        "UPDATE index_sources SET status = ?, records_processed = ?, error = '', updated_at = ? WHERE id = ?",
        (status, processed, variant_store.utc_now(), source_id),
    )


def _source_summary(row, skipped=False):
    return {
        "relative_path": row["relative_path"], "stage": row["stage"],
        "status": row["status"], "records_processed": row["records_processed"],
        "sha256": row["sha256"], "skipped": skipped,
    }
