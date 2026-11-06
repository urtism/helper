"""Cheap validators for browser detail reuse; never scan reference contents."""
import hashlib
import json
import os
import time
from pathlib import Path

from helper_next.core import acmg_reference
from helper_prioritization import RULESET_VERSION
from helper_variants import clinvar_local, clingen_vcep_local, gene_phenotype, gnomad_frequency, liftover


def file_revision(path):
    """Include WAL commits and file replacement, not just main-file mtime."""
    path = Path(path).expanduser().absolute()
    states = []
    for candidate in (path, Path(str(path) + "-wal")):
        try:
            stat = candidate.stat()
            state = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        except FileNotFoundError:
            state = None
        states.append((str(candidate.resolve()), state))
    return states


def detail_etag(database, record, identity, sample_id, variant_id, *, compact=False,
                submissions_limit=100, submissions_offset=0, scoring_version=None):
    assembly = identity["reference_build"]
    selected, config = acmg_reference.reference_record(assembly, record)
    candidates = [selected.get("run_config", {}).get("reference_fasta"),
                  selected.get("tools_config", {}).get(assembly, {}).get("fasta")]
    paths = [database, clinvar_local.database_path(), clingen_vcep_local.database_path(),
             gene_phenotype.cache_path(), gnomad_frequency.cache_path(), liftover.cache_path()]
    config_path = os.environ.get("HELPER_ACMG_REFERENCE_CONFIG")
    if config_path:
        paths.append(config_path)
    for candidate in candidates:
        if candidate:
            paths.extend((candidate, str(candidate) + ".fai"))
    # Freshness labels may change with time even without a database write.
    token = dict(format="helper-detail-revision-1", files=[file_revision(path) for path in paths],
                 record=record, reference_config=config, ruleset=RULESET_VERSION,
                 sample=sample_id, variant=variant_id, compact=compact,
                 limit=submissions_limit, offset=submissions_offset, scoring_version=scoring_version,
                 freshness_window=int(time.time() // 60))
    return 'W/"' + hashlib.sha256(json.dumps(token, sort_keys=True, default=str).encode()).hexdigest() + '"'
