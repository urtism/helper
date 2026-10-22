"""Private local VCF sources, independent of analysis history."""
import gzip
import json
import os
import re
import shutil
from pathlib import Path
from uuid import uuid4

from helper_variants import indexer, query, store
from helper_next.core.acmg_reference import reference_record


MAX_UPLOAD = 256 * 1024 * 1024
MAX_EXPANDED = 1024 * 1024 * 1024
MAX_LINE = 4 * 1024 * 1024
MAX_RECORDS = 5000000


def root():
    base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    return Path(os.environ.get("HELPER_EXTERNAL_VCF_DIR", str(base / "helper_next/external_vcf")))


def directory(identifier):
    if not re.fullmatch(r"external-[a-f0-9]{32}", identifier):
        raise ValueError("Invalid external source identifier")
    return root() / identifier


def get(identifier):
    path = directory(identifier) / "source.json"
    return json.loads(path.read_text()) if path.is_file() else None


def list_sources():
    return [json.loads(p.read_text()) for p in sorted(root().glob("external-*/source.json"))]


def allocate(filename):
    if not str(filename).lower().endswith((".vcf", ".vcf.gz")):
        raise ValueError("Only .vcf and .vcf.gz are supported")
    identifier = "external-" + uuid4().hex
    folder = directory(identifier)
    folder.mkdir(parents=True, mode=0o700)
    return identifier, folder / ("input.vcf.gz" if filename.lower().endswith(".gz") else "input.vcf")


def discard(identifier):
    shutil.rmtree(str(directory(identifier)), ignore_errors=True)


def validate(path):
    """Bound decompression and line allocations before using the shared parser."""
    opener = gzip.open if str(path).endswith(".gz") else open
    total = 0
    header = None
    records = 0
    builds = set()
    with opener(str(path), "rb") as handle:
        first = handle.readline(MAX_LINE + 1)
        if len(first) > MAX_LINE:
            raise ValueError("VCF line limit exceeded")
        if not first.startswith(b"##fileformat=VCFv4."):
            raise ValueError("Missing VCFv4 fileformat header")
        total += len(first)
        while True:
            line = handle.readline(MAX_LINE + 1)
            if not line:
                break
            total += len(line)
            if len(line) > MAX_LINE or total > MAX_EXPANDED:
                raise ValueError("VCF decompressed size or line limit exceeded")
            text = line.decode("utf-8", errors="strict").rstrip("\r\n")
            if text.startswith(("##reference=", "##assembly=")):
                builds.add(text.split("=", 1)[1])
            if text.startswith("#CHROM"):
                header = text.split("\t")
                if header[:8] != ["#CHROM", "POS", "ID", "REF", "ALT", "QUAL", "FILTER", "INFO"]:
                    raise ValueError("Invalid VCF columns")
                if len(set(header[9:])) != len(header[9:]):
                    raise ValueError("Duplicate VCF samples")
            elif text and not text.startswith("#"):
                records += 1
                if records > MAX_RECORDS:
                    raise ValueError("VCF record limit exceeded")
                fields = text.split("\t")
                if header is None or len(fields) != len(header):
                    raise ValueError("Invalid VCF column count")
                if not fields[1].isdigit() or int(fields[1]) < 1 or not fields[3] or not fields[4]:
                    raise ValueError("Invalid VCF allele coordinates")
    if header is None:
        raise ValueError("VCF header has no #CHROM line")
    return sorted(builds)


def finish(identifier, path, filename, assembly):
    if assembly not in ("GRCh37", "GRCh38"):
        raise ValueError("Explicit GRCh37 or GRCh38 confirmation is required")
    metadata = validate(path)
    # A declaration conflicting with the user's confirmation requires resolution.
    known = {"hg19": "GRCh37", "hg38": "GRCh38", "GRCh37": "GRCh37", "GRCh38": "GRCh38"}
    if any(known.get(b, assembly) != assembly for b in metadata):
        raise ValueError("Assembly confirmation conflicts with VCF metadata")
    folder = directory(identifier)
    database = indexer.index_path(folder)
    reference, config = reference_record(assembly)
    fasta = indexer.open_reference(reference, assembly)
    if config and fasta is None:
        raise ValueError("Configured reference FASTA/.fai is unavailable")
    try:
        with store.connect(database, "run") as db:
            local_id = store.register_run(db, identifier, assembly, metadata={"source_type": "EXTERNAL_UPLOAD"})
            indexer.index_vcf(db, local_id, identifier, folder, path, "annotation", assembly, {}, reference_reader=fasta)
    finally:
        if fasta:
            fasta.close()
    record = {
        "id": identifier, "run_id": Path(filename.replace("\\", "/")).name,
        "source_type": "EXTERNAL_UPLOAD", "run_dir": str(folder),
        "created_at": store.utc_now(), "status": "external",
        "sha256": indexer.sha256_file(path), "size_bytes": path.stat().st_size,
        "assembly_metadata": metadata, "assembly_confirmed": True,
        "run_config": {"reference_version": assembly}, "samples": [],
    }
    (folder / "source.json").write_text(json.dumps(record), encoding="utf-8")
    return record


def public_sources():
    result = []
    for record in list_sources():
        result.append({
            "history_id": record["id"], "run_id": record["run_id"],
            "source_type": "EXTERNAL_UPLOAD", "created_at": record["created_at"],
            "index_status": "complete", "run_status": "external", "panel": "",
            "pipeline": "External VCF", "reference_build": indexer.reference_build(record),
            "summary": query.run_summary(indexer.index_path(record["run_dir"])),
        })
    return result
