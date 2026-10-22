"""Reference identity checks using HELPER's existing FASTA reader/normalizer."""
import json
import os
from functools import lru_cache
from pathlib import Path

from helper_variants import indexer


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
def _checksum(path, size, mtime_ns, ctime_ns):
    return indexer.sha256_file(path)


def verify(identity, record=None):
    selected, config = reference_record(identity["assembly"], record)
    fasta = indexer.open_reference(selected, identity["assembly"])
    if fasta is None:
        if config:
            raise ValueError("Configured uncompressed reference FASTA or .fai is unavailable")
        return None
    try:
        stat = fasta.path.stat()
        checksum = _checksum(str(fasta.path.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        if config.get("sha256") and config["sha256"] != checksum:
            raise ValueError("Configured reference FASTA checksum mismatch")
        observed = fasta.sequence(identity["chromosome"], identity["position"], len(identity["reference"]))
        if observed.upper() != identity["reference"]:
            raise ValueError("Selected variant REF does not match the declared assembly reference")
        normalized = indexer.normalize_allele(identity["position"], identity["reference"], identity["alternate"], identity["chromosome"], fasta)
        if normalized != (identity["position"], identity["reference"], identity["alternate"]):
            raise ValueError("Selected allele is not reference-normalized; rebuild its source index with the configured reference")
        return {"identifier": "reference-sha256-" + checksum,
                "version": str(config.get("version") or selected.get("run_config", {}).get("reference_version") or identity["assembly"]),
                "digest": {"algorithm": "sha256", "value": checksum}}
    finally:
        fasta.close()
