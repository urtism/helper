"""Explicit FASTA/FAI validation receipts for locally managed immutable references.

Receipts are trusted local administration data, not signatures. Only
validate_reference publishes a validation receipt after a complete scan.
Checksum-only cache entries are stored separately and cannot validate a FASTA/FAI.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from datetime import datetime, timezone

from helper_variants import indexer
from helper_variants.liftover import _assembly


SCHEMA = "helper-reference-validation-1"
TRUST = "managed-immutable-v1"


def file_identity(status):
    return dict(device=status.st_dev, inode=status.st_ino, size=status.st_size,
                mtime_ns=status.st_mtime_ns, ctime_ns=status.st_ctime_ns)


def reference_state(fasta):
    """Bind path identities to the actual FASTA handle and parsed FAI."""
    path = fasta.path.resolve(strict=True)
    index_path = Path(str(fasta.path) + ".fai").resolve(strict=True)
    fasta_stat, index_stat = path.stat(), index_path.stat()
    if (file_identity(fasta_stat) != file_identity(os.fstat(fasta.handle.fileno()))
            or file_identity(index_stat) != file_identity(fasta.index_stat)):
        raise ValueError("Reference FASTA or .fai changed while opening")
    return dict(fasta=dict(path=str(path), **file_identity(fasta_stat)),
                fai=dict(path=str(index_path), **file_identity(index_stat)))


def reference_version(assembly, selected, config):
    return str(config.get("version") or selected.get("run_config", {}).get("reference_version") or assembly)


def _directory():
    base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    return Path(os.environ.get("HELPER_REFERENCE_VALIDATION_DIR", str(base / "helper_next/reference_validation"))).expanduser()


def manifest_path(assembly, version, state):
    key = json.dumps([assembly, version, state["fasta"]["path"]], separators=(",", ":"))
    return _directory() / (hashlib.sha256(key.encode()).hexdigest() + ".json")


def _trusted(path):
    info = path.stat()
    return info.st_uid == os.getuid() and not info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)


def reusable_manifest(assembly, version, state, expected=None):
    """Return a completed, matching receipt or None; never hash the FASTA."""
    path = manifest_path(assembly, version, state)
    try:
        if not _trusted(path.parent) or not _trusted(path):
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if (value.get("schema") != SCHEMA or value.get("status") != "verified"
                or value.get("trust") != TRUST or value.get("assembly") != assembly
                or value.get("version") != version or value.get("files") != state
                or not value.get("verified_at") or value.get("fai_verified") is not True
                or not re.fullmatch(r"[0-9a-f]{64}", value.get("fai_sha256", ""))
                or value.get("digest", {}).get("algorithm") != "sha256"):
            return None
        checksum = value["digest"]["value"]
        if not re.fullmatch(r"[0-9a-f]{64}", checksum) or (expected and checksum != expected):
            return None
        return value
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def cached_checksum(assembly, version, state):
    """Reuse a digest across restarts; this is not a FASTA/FAI validation receipt."""
    path = manifest_path(assembly, version, state).with_suffix(".checksum.json")
    try:
        if not _trusted(path.parent) or not _trusted(path):
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if (value.get("schema") == "helper-reference-checksum-1"
                and value.get("assembly") == assembly and value.get("version") == version
                and value.get("files") == state and value.get("computed_at")
                and value.get("digest", {}).get("algorithm") == "sha256"
                and re.fullmatch(r"[0-9a-f]{64}", value["digest"]["value"])):
            return value["digest"]["value"]
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        pass
    return None


def cache_checksum(assembly, version, state, checksum):
    """Persist a completed hash atomically, without claiming full validation."""
    if not re.fullmatch(r"[0-9a-f]{64}", checksum):
        raise ValueError("Invalid reference SHA-256")
    value = dict(schema="helper-reference-checksum-1", assembly=assembly, version=version,
                 files=state, computed_at=datetime.now(timezone.utc).isoformat(),
                 digest=dict(algorithm="sha256", value=checksum))
    _publish(manifest_path(assembly, version, state).with_suffix(".checksum.json"), value)


def _scan_fasta(fasta):
    """Compute SHA-256 and independently reconstruct FAI geometry in one scan."""
    names = set()
    with open(str(fasta.path) + ".fai", encoding="utf-8") as index:
        for line in index:
            fields = line.rstrip("\r\n").split("\t")
            if len(fields) != 5 or not fields[0] or fields[0] in names:
                raise ValueError("Invalid or duplicate .fai entry")
            names.add(fields[0])
    digest = hashlib.sha256()
    contigs = {}
    name, length, offset, bases, width, previous = None, 0, 0, 0, 0, None
    position = 0
    fasta.handle.seek(0)
    for line in fasta.handle:
        digest.update(line)
        if line.startswith(b">"):
            if name is not None:
                if not length:
                    raise ValueError("Empty FASTA contig")
                contigs[name] = (length, offset, bases, width)
            words = line[1:].split()
            if not words:
                raise ValueError("Missing FASTA contig name")
            name = words[0].decode("ascii")
            if name in contigs:
                raise ValueError("Duplicate FASTA contig")
            length, offset, bases, width, previous = 0, position + len(line), 0, 0, None
        else:
            sequence = line.rstrip(b"\r\n")
            if name is None or not sequence or re.fullmatch(b"[ACGTRYSWKMBDHVNacgtryswkmbdhvn]+", sequence) is None:
                raise ValueError("Invalid FASTA sequence")
            if previous is not None and previous != (bases, width):
                raise ValueError("Irregular FASTA line widths")
            if not length:
                bases, width = len(sequence), len(line)
            elif len(sequence) > bases:
                raise ValueError("Irregular FASTA line widths")
            length += len(sequence)
            previous = (len(sequence), len(line))
        position += len(line)
    if name is None or not length:
        raise ValueError("Empty FASTA reference/contig")
    contigs[name] = (length, offset, bases, width)
    if contigs != fasta.contigs:
        raise ValueError("Reference .fai does not match FASTA sequence geometry")
    return digest.hexdigest()


def _publish(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not _trusted(path.parent):
        raise ValueError("Reference manifest directory must be owned by this user and not writable by others")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".reference-", delete=False) as stream:
            temporary = stream.name
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        descriptor = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if temporary is not None:
            os.unlink(temporary)


def validate_reference(assembly, record=None, *, managed_immutable=False, force=False, check=False):
    """Validate without opening a sample. --check never performs a full scan."""
    from helper_next.core.acmg_reference import reference_record

    assembly = _assembly(assembly)
    selected, config = reference_record(assembly, record)
    fasta = indexer.open_reference(selected, assembly)
    if fasta is None:
        raise ValueError("Configured uncompressed reference FASTA or .fai is unavailable")
    try:
        state = reference_state(fasta)
        version = reference_version(assembly, selected, config)
        receipt = reusable_manifest(assembly, version, state, config.get("sha256"))
        if check:
            if receipt is None:
                raise ValueError("Reference requires validation: no reusable managed-immutable manifest")
            return dict(manifest=str(manifest_path(assembly, version, state)), reused=True, **receipt)
        if receipt is not None and not force:
            return dict(manifest=str(manifest_path(assembly, version, state)), reused=True, **receipt)
        # Bypass the process checksum LRU even when forcing the same file again.
        checksum = _scan_fasta(fasta)
        if config.get("sha256") and checksum != config["sha256"]:
            raise ValueError("Configured reference FASTA checksum mismatch")
        fai_checksum = indexer.sha256_file(state["fai"]["path"])
        if reference_state(fasta) != state:
            raise ValueError("Reference FASTA or .fai changed during validation")
        receipt = dict(schema=SCHEMA, status="verified", assembly=assembly, version=version,
                       trust=TRUST if managed_immutable else "full-check-only",
                       verified_at=datetime.now(timezone.utc).isoformat(), files=state,
                       digest=dict(algorithm="sha256", value=checksum),
                       expected_sha256=config.get("sha256"), fai_verified=True, fai_sha256=fai_checksum)
        path = manifest_path(assembly, version, state)
        _publish(path, receipt)
        return dict(manifest=str(path), reused=False, **receipt)
    finally:
        fasta.close()
