"""CACHE-05.2: persistent verification, invalidation and unchanged ga2 behavior."""
import builtins
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest

from helper_next.core import acmg_reference, biological_identity, reference_validation as validation
from helper_variants import indexer
from test_biological_identity import reference_record, allele


@pytest.fixture(autouse=True)
def isolated_manifests(tmp_path, monkeypatch):
    monkeypatch.setenv("HELPER_REFERENCE_VALIDATION_DIR", str(tmp_path / "receipts"))
    acmg_reference._checksum.cache_clear()


def enroll(record, **kwargs):
    return validation.validate_reference("GRCh38", record, managed_immutable=True, **kwargs)


def no_hash(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Unchanged verified FASTA must not be hashed during consultation")
    monkeypatch.setattr(acmg_reference, "_checksum", forbidden)
    monkeypatch.setattr(indexer, "sha256_file", forbidden)


def test_full_validation_publishes_real_checksum_and_fai_proof(tmp_path):
    record = reference_record(tmp_path)
    result = enroll(record)
    assert result["reused"] is False
    receipt = json.loads(Path(result["manifest"]).read_text())
    assert receipt["status"] == "verified" and receipt["trust"] == validation.TRUST
    assert receipt["digest"]["value"] == hashlib.sha256(Path(record["run_config"]["reference_fasta"]).read_bytes()).hexdigest()
    assert receipt["fai_verified"] is True
    assert all(key in receipt["files"]["fasta"] for key in ("path", "device", "inode", "size", "mtime_ns", "ctime_ns"))
    assert validation.validate_reference("hg38", record, check=True)["reused"] is True


def test_new_process_reuses_manifest_and_preserves_entire_ga2_result(tmp_path):
    record = reference_record(tmp_path)
    expected = allele(record)
    enroll(record)
    code = """
import json, sys
from helper_next.core import acmg_reference, biological_identity
from helper_variants import indexer
def forbidden(*a, **kw):
    raise AssertionError('Full checksum in new process')
acmg_reference._checksum = indexer.sha256_file = forbidden
record = json.loads(sys.argv[1])
print(json.dumps(biological_identity.allele_refs('GRCh38', '1', 7, 'G', 'T', record=record)[0]))
"""
    process = subprocess.run([sys.executable, "-c", code, json.dumps(record)], capture_output=True, text=True, check=True)
    assert json.loads(process.stdout) == expected


@pytest.mark.parametrize("build", ["GRCh37", "GRCh38", "hg19", "hg38"])
def test_fast_path_keeps_snv_indel_mismatch_and_provenance(tmp_path, monkeypatch, build):
    record = reference_record(tmp_path)
    queries = [(build, "1", 7, "G", "T"), (build, "chr1", 4, "AA", "A"),
               (build, "1", 5, "A", "AA"), (build, "1", 7, "AT", "AC")]
    before = biological_identity.allele_refs_batch(queries, record=record)
    validation.validate_reference(build, record, managed_immutable=True)
    no_hash(monkeypatch)
    assert biological_identity.allele_refs_batch(queries, record=record) == before
    identity = dict(assembly=before[0][0]["identity"]["assembly"], chromosome="1", position=7, reference="G", alternate="T")
    assert acmg_reference.verify(identity, record)["digest"] == before[0][0]["reference_provenance"]["digest"]


@pytest.mark.parametrize("change", ["modified", "same_size_mtime", "replaced", "fai", "fai_replaced", "symlink"])
def test_changed_file_invalidates_receipt_and_uses_full_path(tmp_path, monkeypatch, change):
    record = reference_record(tmp_path)
    result = enroll(record)
    fasta = Path(record["run_config"]["reference_fasta"])
    fai = Path(str(fasta) + ".fai")
    if change == "modified":
        fasta.write_bytes(fasta.read_bytes().replace(b"ACGT", b"ACGA"))
    elif change == "same_size_mtime":
        status = fasta.stat()
        fasta.write_bytes(fasta.read_bytes().replace(b"ACGT", b"ACGA"))
        os.utime(fasta, ns=(status.st_atime_ns, status.st_mtime_ns))
        assert fasta.stat().st_ctime_ns != status.st_ctime_ns
    elif change in ("replaced", "fai_replaced"):
        target = fasta if change == "replaced" else fai
        other = tmp_path / "replacement"
        other.write_bytes(target.read_bytes())
        os.replace(other, target)
    elif change == "fai":
        # Still parseable by the legacy reader, but no longer the verified file.
        fai.write_text(fai.read_text() + "\n")
    else:
        other = tmp_path / "other.fa"
        other.write_bytes(fasta.read_bytes())
        fasta.unlink()
        fasta.symlink_to(other)
    with pytest.raises(ValueError, match="requires validation"):
        enroll(record, check=True)
    tracked = Mock(wraps=indexer.sha256_file)
    monkeypatch.setattr(indexer, "sha256_file", tracked)
    assert allele(record)["status"] == "RESOLVED"
    assert tracked.call_count == 1
    assert json.loads(Path(result["manifest"]).read_text())["files"] == result["files"]


@pytest.mark.parametrize("damage", ["absent", "json", "assembly", "version", "trust", "status", "digest", "permissions"])
def test_unusable_manifest_falls_back_without_writes(tmp_path, monkeypatch, damage):
    record = reference_record(tmp_path)
    result = enroll(record)
    path = Path(result["manifest"])
    receipt = json.loads(path.read_text())
    if damage == "absent":
        path.unlink()
    elif damage == "json":
        path.write_text('{"partial":')
    elif damage == "permissions":
        path.chmod(0o666)
    else:
        receipt[damage] = {"assembly": "GRCh37", "version": "other", "trust": "declared-only",
                           "status": "pending", "digest": {"algorithm": "md5", "value": "bad"}}[damage]
        path.write_text(json.dumps(receipt))
    before = path.read_bytes() if path.exists() else None
    tracked = Mock(wraps=indexer.sha256_file)
    monkeypatch.setattr(indexer, "sha256_file", tracked)
    assert allele(record)["status"] == "RESOLVED"
    assert tracked.call_count == 1
    assert (path.read_bytes() if path.exists() else None) == before


def test_declaration_alone_and_full_only_receipt_do_not_enable_reuse(tmp_path, monkeypatch):
    record = reference_record(tmp_path)
    config = tmp_path / "references.json"
    config.write_text(json.dumps({"GRCh38": dict(fasta=record["run_config"]["reference_fasta"], version="v1", managed_immutable=True)}))
    monkeypatch.setenv("HELPER_ACMG_REFERENCE_CONFIG", str(config))
    tracked = Mock(wraps=indexer.sha256_file)
    monkeypatch.setattr(indexer, "sha256_file", tracked)
    assert allele(record)["status"] == "RESOLVED"
    assert tracked.call_count == 1
    assert list(validation._directory().glob("*.checksum.json"))
    assert all(
        path.name.endswith(".checksum.json") for path in validation._directory().glob("*.json"))
    result = validation.validate_reference("GRCh38")
    assert result["trust"] == "full-check-only"
    with pytest.raises(ValueError, match="requires validation"):
        validation.validate_reference("GRCh38", check=True)
    assert enroll(record)["reused"] is False


def test_expected_checksum_mismatch_cannot_reuse_or_publish(tmp_path, monkeypatch):
    record = reference_record(tmp_path)
    config = tmp_path / "references.json"
    declaration = dict(fasta=record["run_config"]["reference_fasta"], version="v1")
    config.write_text(json.dumps({"GRCh38": declaration}))
    monkeypatch.setenv("HELPER_ACMG_REFERENCE_CONFIG", str(config))
    result = enroll(record)
    path = Path(result["manifest"])
    before = path.read_bytes()
    declaration["sha256"] = "0" * 64
    config.write_text(json.dumps({"GRCh38": declaration}))
    assert "checksum mismatch" in allele(record)["reason"]
    with pytest.raises(ValueError, match="checksum mismatch"):
        enroll(record, force=True)
    assert path.read_bytes() == before
    declaration["sha256"] = result["digest"]["value"]
    config.write_text(json.dumps({"GRCh38": declaration}))
    no_hash(monkeypatch)
    assert allele(record)["status"] == "RESOLVED"


@pytest.mark.parametrize("content", ["1\t12\t4\t12\t13\n", "1\t12\t3\t12\t13\n1\t12\t3\t12\t13\n", "garbage\n", ""])
def test_invalid_fai_never_creates_receipt(tmp_path, content):
    record = reference_record(tmp_path)
    Path(record["run_config"]["reference_fasta"] + ".fai").write_text(content)
    with pytest.raises(ValueError, match=".fai"):
        enroll(record)
    assert not validation._directory().exists()


@pytest.mark.parametrize("ending", [b"\n", b"\r\n"])
def test_full_scan_accepts_wrapped_contigs_and_short_last_lines(tmp_path, ending):
    path = tmp_path / "wrapped.fa"
    first = b">1 description" + ending
    second = b">2" + ending
    sequence = first + b"ACGT" + ending + b"nn" + ending
    offset2 = len(sequence) + len(second)
    path.write_bytes(sequence + second + b"gtca" + ending)
    Path(str(path) + ".fai").write_text("1\t6\t{}\t4\t{}\n2\t4\t{}\t4\t{}\n".format(
        len(first), 4 + len(ending), offset2, 4 + len(ending)))
    result = enroll({"run_config": {"reference_fasta": str(path)}})
    assert result["digest"]["value"] == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("content", [b">1\nAC\nGTAA\n", b">1\nACGT\n>1\nACGT\n", b">1\n", b">1\nBAD!\n"])
def test_invalid_fasta_never_publishes_success(tmp_path, content):
    record = reference_record(tmp_path)
    Path(record["run_config"]["reference_fasta"]).write_bytes(content)
    with pytest.raises(ValueError, match="FASTA"):
        enroll(record)
    assert not validation._directory().exists()


def test_concurrent_first_verifications_in_separate_processes(tmp_path):
    record = reference_record(tmp_path)
    command = [sys.executable, "-c", "import json,sys; from helper_next.core.reference_validation import validate_reference; "
               "print(json.dumps(validate_reference('GRCh38',json.loads(sys.argv[1]),managed_immutable=True,force=True)))", json.dumps(record)]
    children = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(4)]
    results = []
    for child in children:
        stdout, stderr = child.communicate(timeout=20)
        assert child.returncode == 0, stderr
        results.append(json.loads(stdout))
    assert len({r["manifest"] for r in results}) == 1
    assert enroll(record, check=True)["digest"] == results[0]["digest"]
    assert not list(validation._directory().glob(".reference-*"))


def test_force_really_scans_again_and_closes_readers(tmp_path, monkeypatch):
    record = reference_record(tmp_path)
    scan = Mock(wraps=validation._scan_fasta)
    opened = []
    original = indexer.open_reference
    def tracked(*args):
        reader = original(*args)
        opened.append(reader)
        return reader
    monkeypatch.setattr(validation, "_scan_fasta", scan)
    monkeypatch.setattr(indexer, "open_reference", tracked)
    enroll(record)
    enroll(record)
    enroll(record, force=True)
    assert scan.call_count == 2
    allele(record)
    assert all(reader.handle.closed for reader in opened)


def test_reader_closes_on_bad_index_and_validation_interruption(tmp_path, monkeypatch):
    record = reference_record(tmp_path)
    fasta = Path(record["run_config"]["reference_fasta"])
    opened = []
    original = builtins.open
    def tracked(path, *args, **kwargs):
        stream = original(path, *args, **kwargs)
        if str(path) == str(fasta):
            opened.append(stream)
        return stream
    monkeypatch.setattr(builtins, "open", tracked)
    fai = Path(str(fasta) + ".fai")
    good = fai.read_text()
    fai.write_text("1\tbad\t3\t12\t13\n")
    with pytest.raises(ValueError):
        enroll(record)
    fai.write_text(good)
    def interrupted(*args):
        raise KeyboardInterrupt()
    monkeypatch.setattr(validation, "_scan_fasta", interrupted)
    with pytest.raises(KeyboardInterrupt):
        enroll(record)
    assert len(opened) == 2 and all(stream.closed for stream in opened)


def test_change_during_scan_cannot_publish_receipt(tmp_path, monkeypatch):
    record = reference_record(tmp_path)
    original = validation._scan_fasta
    def changed(reader):
        checksum = original(reader)
        reader.path.write_bytes(reader.path.read_bytes() + b"N")
        return checksum
    monkeypatch.setattr(validation, "_scan_fasta", changed)
    with pytest.raises(ValueError, match="changed during validation"):
        enroll(record)
    assert not validation._directory().exists()


def test_atomic_publication_and_concurrent_writers(tmp_path, monkeypatch):
    record = reference_record(tmp_path)
    result = enroll(record)
    replace = os.replace
    seen = []
    def inspected(source, destination):
        # Before every commit, destination is the previous complete receipt.
        assert json.loads(Path(destination).read_text())["status"] == "verified"
        assert json.loads(Path(source).read_text())["status"] == "verified"
        seen.append(1)
        replace(source, destination)
    monkeypatch.setattr(os, "replace", inspected)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: enroll(record, force=True), range(8)))
    assert len(seen) == 8
    assert all(row["digest"] == result["digest"] for row in results)
    assert enroll(record, check=True)["digest"] == result["digest"]
    assert not list(validation._directory().glob(".reference-*"))


def test_failed_atomic_replace_preserves_previous_manifest(tmp_path, monkeypatch):
    record = reference_record(tmp_path)
    result = enroll(record)
    before = Path(result["manifest"]).read_bytes()
    def fail(*args):
        raise OSError("interrupted commit")
    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError, match="interrupted commit"):
        enroll(record, force=True)
    assert Path(result["manifest"]).read_bytes() == before
    assert not list(validation._directory().glob(".reference-*"))


def test_multiple_reference_versions_do_not_share_receipts(tmp_path):
    record = reference_record(tmp_path)
    first = enroll(record)
    record["run_config"]["reference_version"] = "v2"
    with pytest.raises(ValueError, match="requires validation"):
        enroll(record, check=True)
    second = enroll(record)
    third = validation.validate_reference("GRCh37", record, managed_immutable=True)
    assert len({r["manifest"] for r in (first, second, third)}) == 3


def test_cli_verify_check_and_force(tmp_path):
    record = reference_record(tmp_path)
    path = tmp_path / "record.json"
    path.write_text(json.dumps(record))
    command = [sys.executable, "-m", "helper_next.cli", "reference-verify", "--assembly", "hg38", "--record", str(path)]
    missing = subprocess.run(command + ["--check"], capture_output=True, text=True)
    assert missing.returncode == 1 and "requires validation" in missing.stderr
    verified = subprocess.run(command + ["--managed-immutable"], capture_output=True, text=True, check=True)
    assert json.loads(verified.stdout)["reused"] is False
    checked = subprocess.run(command + ["--check"], capture_output=True, text=True, check=True)
    assert json.loads(checked.stdout)["reused"] is True
    forced = subprocess.run(command + ["--force", "--managed-immutable"], capture_output=True, text=True, check=True)
    assert json.loads(forced.stdout)["reused"] is False
