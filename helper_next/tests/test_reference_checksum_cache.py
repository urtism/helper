"""Persistent digest reuse without putting full-reference hashing in browsing."""
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest

from helper_next.core import acmg_reference, reference_validation as validation
from helper_variants import indexer
from test_biological_identity import allele, reference_record


@pytest.fixture(autouse=True)
def cold_checksum_cache():
    acmg_reference._checksum.cache_clear()


def test_new_process_reuses_checksum_without_validation_receipt(tmp_path):
    record = reference_record(tmp_path)
    expected = allele(record)
    assert len(list(validation._directory().glob("*.checksum.json"))) == 1
    with pytest.raises(ValueError, match="requires validation"):
        validation.validate_reference("GRCh38", record, check=True)
    code = """
import json, sys
from helper_next.core import acmg_reference, biological_identity
from helper_variants import indexer
def forbidden(*a, **kw):
    raise AssertionError('Full checksum after restart')
acmg_reference._checksum = indexer.sha256_file = forbidden
record = json.loads(sys.argv[1])
print(json.dumps(biological_identity.allele_refs('GRCh38', '1', 7, 'G', 'T', record=record)[0]))
"""
    process = subprocess.run([sys.executable, "-c", code, json.dumps(record)],
                             capture_output=True, text=True, check=True, timeout=20)
    assert json.loads(process.stdout) == expected


@pytest.mark.parametrize("change", ["fasta", "same_size_mtime", "fasta_replaced", "fai", "fai_replaced", "version", "path"])
def test_changed_reference_invalidates_persistent_checksum(tmp_path, monkeypatch, change):
    record = reference_record(tmp_path)
    before = allele(record)
    fasta = Path(record["run_config"]["reference_fasta"])
    fai = Path(str(fasta) + ".fai")
    if change in ("fasta", "same_size_mtime"):
        status = fasta.stat()
        fasta.write_bytes(fasta.read_bytes().replace(b"ACGT", b"ACGA"))
        if change == "same_size_mtime":
            os.utime(fasta, ns=(status.st_atime_ns, status.st_mtime_ns))
            assert fasta.stat().st_ctime_ns != status.st_ctime_ns
    elif change in ("fasta_replaced", "fai_replaced"):
        target = fasta if change == "fasta_replaced" else fai
        replacement = tmp_path / "replacement"
        replacement.write_bytes(target.read_bytes())
        os.replace(replacement, target)
    elif change == "fai":
        fai.write_text(fai.read_text() + "\n")
    elif change == "version":
        record["run_config"]["reference_version"] = "next-reference-version"
    else:
        other = tmp_path / "other"
        other.mkdir()
        record = reference_record(other)
    acmg_reference._checksum.cache_clear()
    tracked = Mock(wraps=indexer.sha256_file)
    monkeypatch.setattr(indexer, "sha256_file", tracked)
    after = allele(record)
    assert after["status"] == "RESOLVED"
    assert after["allele_ref"] == before["allele_ref"]
    assert tracked.call_count == 1
    if change in ("fasta", "same_size_mtime"):
        assert after["reference_provenance"]["digest"] != before["reference_provenance"]["digest"]


@pytest.mark.parametrize("damage", ["json", "schema", "digest", "permissions", "directory_permissions"])
def test_unusable_disk_cache_recomputes(tmp_path, monkeypatch, damage):
    record = reference_record(tmp_path)
    expected = allele(record)
    path, = validation._directory().glob("*.checksum.json")
    if damage == "json":
        path.write_text('{"partial":')
    elif damage in ("schema", "digest"):
        value = json.loads(path.read_text())
        value[damage] = "invalid"
        path.write_text(json.dumps(value))
    else:
        (path.parent if damage == "directory_permissions" else path).chmod(0o777)
    acmg_reference._checksum.cache_clear()
    tracked = Mock(wraps=indexer.sha256_file)
    monkeypatch.setattr(indexer, "sha256_file", tracked)
    assert allele(record) == expected
    assert tracked.call_count == 1


def test_optional_cache_write_failure_keeps_reference_verification(tmp_path, monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError("Read-only cache")
    monkeypatch.setattr(validation, "cache_checksum", denied)
    result = allele(reference_record(tmp_path))
    assert result["status"] == "RESOLVED"
    assert result["reference_provenance"]["digest"]["algorithm"] == "sha256"


def test_configured_expected_digest_is_checked_when_reusing_cache(tmp_path, monkeypatch):
    record = reference_record(tmp_path)
    allele(record)
    config = tmp_path / "references.json"
    config.write_text(json.dumps({"GRCh38": dict(
        fasta=record["run_config"]["reference_fasta"],
        version=record["run_config"]["reference_version"], sha256="0" * 64)}))
    monkeypatch.setenv("HELPER_ACMG_REFERENCE_CONFIG", str(config))
    monkeypatch.setattr(indexer, "sha256_file", lambda *args: pytest.fail("Unexpected hash"))
    assert "checksum mismatch" in allele(record)["reason"]
