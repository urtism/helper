"""CACHE-05.2: fresh-process page/output comparison with full-hash counters.

Run once per process, with a previously validated manifest directory or an
empty directory. Reuses CACHE-05.1's read-only source checks and temporary copy.
"""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import time
from unittest.mock import patch

from profile_clinvar_integration import outputs
from helper_next.core import acmg_reference, biological_identity
from helper_variants import clinvar, clinvar_adapter, clinvar_local, indexer, query


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--manifest-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--baseline-source", help="Trusted CACHE-05.2 before-source root (two original reference/identity modules)")
    args = parser.parse_args()
    os.environ["HELPER_REFERENCE_VALIDATION_DIR"] = args.manifest_dir
    http, hashes = [], []
    sha256_file = indexer.sha256_file

    def counted(path):
        start = time.perf_counter()
        try:
            return sha256_file(path)
        finally:
            hashes.append(time.perf_counter() - start)

    def forbidden(*a, **kw):
        http.append(1)
        raise AssertionError("Unexpected network access")

    with ExitStack() as stack:
        for obj, name in ((socket.socket, "connect"), (socket, "create_connection"),
                          (clinvar, "_request"), (clinvar_local, "urlopen")):
            stack.enter_context(patch.object(obj, name, forbidden))
        stack.enter_context(patch.object(indexer, "sha256_file", counted))
        if args.baseline_source:
            def load(name, relative):
                spec = importlib.util.spec_from_file_location(name, Path(args.baseline_source) / relative)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module
            reference = load("cache052_reference_before", "helper_next/core/acmg_reference.py")
            identity = load("cache052_identity_before", "helper_next/core/biological_identity.py")
            reference._checksum = acmg_reference._checksum
            stack.enter_context(patch.object(acmg_reference, "verify", reference.verify))
            stack.enter_context(patch.object(biological_identity, "allele_refs", identity.allele_refs))
        with clinvar_local.ClinVarLocal() as source:
            snapshot = source.release()["snapshot_id"]
        result = outputs(args.database)
    result.update(snapshot_id=snapshot, full_checksum_calls=len(hashes), full_checksum_seconds=sum(hashes),
                  network_attempts=len(http), baseline=bool(args.baseline_source),
                  shared_source_digests={module.__name__: hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
                                         for module in (clinvar_adapter, query)})
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
