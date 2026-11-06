"""Reference identity checks using HELPER's existing FASTA reader/normalizer."""
import json
import os
from functools import lru_cache
from pathlib import Path

from helper_variants import indexer
from helper_next.core import reference_validation


def reference_record(assembly, record=None):
    config_path = os.environ.get("HELPER_ACMG_REFERENCE_CONFIG")
    if config_path:
        declarations = json.loads(Path(config_path).read_text())
        if assembly in declarations:
            config = declarations[assembly]
            if not config.get("version") or not config.get("fasta"):
                raise ValueError("Reference configuration requires fasta and explicit version")
            return {"run_config": {"reference_fasta": config["fasta"], "reference_version": config["version"]}}, config
    return record or {}, {}


@lru_cache(maxsize=8)
def _checksum(path, size, mtime_ns, ctime_ns, device=None, inode=None):
    return indexer.sha256_file(path)


def reference_checksum(fasta, assembly, selected, config):
    state = reference_validation.reference_state(fasta)
    version = reference_validation.reference_version(assembly, selected, config)
    receipt = reference_validation.reusable_manifest(assembly, version, state, config.get("sha256"))
    if receipt is not None:
        return receipt["digest"]["value"]
    checksum = reference_validation.cached_checksum(assembly, version, state)
    if checksum is not None:
        if reference_validation.reference_state(fasta) != state:
            raise ValueError("Reference FASTA or .fai changed during checksum verification")
        return checksum
    info = state["fasta"]
    checksum = _checksum(info["path"], info["size"], info["mtime_ns"], info["ctime_ns"], info["device"], info["inode"])
    if reference_validation.reference_state(fasta) != state:
        raise ValueError("Reference FASTA or .fai changed during checksum verification")
    try:
        reference_validation.cache_checksum(assembly, version, state, checksum)
    except (OSError, ValueError):
        # The optional disk cache must not fail a completed reference check.
        pass
    return checksum


def verify(identity, record=None, *, _reference=None, checksum_reference=True):
    if _reference is None:
        selected, config = reference_record(identity["assembly"], record)
        fasta = indexer.open_reference(selected, identity["assembly"])
    else:
        selected, config, fasta = (_reference[key] for key in ("selected", "config", "fasta"))
    if fasta is None:
        if config:
            raise ValueError("Configured uncompressed reference FASTA or .fai is unavailable")
        return None
    try:
        if not checksum_reference:
            checksum = None
        elif _reference is None:
            checksum = reference_checksum(fasta, identity["assembly"], selected, config)
        else:
            checksum = _reference["metadata"]["digest"]["value"]
        if checksum_reference and config.get("sha256") and config["sha256"] != checksum:
            raise ValueError("Configured reference FASTA checksum mismatch")
        observed = fasta.sequence(identity["chromosome"], identity["position"], len(identity["reference"]))
        if observed.upper() != identity["reference"]:
            raise ValueError("Selected variant REF does not match the declared assembly reference")
        normalized = indexer.normalize_allele(identity["position"], identity["reference"], identity["alternate"], identity["chromosome"], fasta)
        if normalized != (identity["position"], identity["reference"], identity["alternate"]):
            raise ValueError("Selected allele is not reference-normalized; rebuild its source index with the configured reference")
        result = {"identifier": "reference-sha256-" + checksum if checksum else None,
                "version": str(config.get("version") or selected.get("run_config", {}).get("reference_version") or identity["assembly"]),
                "digest": {"algorithm": "sha256", "value": checksum} if checksum else None}
        if not checksum_reference:
            result["checksum_status"] = "NOT_CHECKED"
        return result
    finally:
        if _reference is None:
            fasta.close()
