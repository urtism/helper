"""Offline CACHE-05 benchmark on a temporary copy of an indexed run.

Never opens the clinical index for writing. Refuses active WAL files and checks
source bytes/metadata before and after the measurement. No dataset downloads.
"""
import argparse
from collections import Counter
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import shutil
import socket
import sqlite3
import tempfile
import time
from unittest.mock import patch

from helper_variants import clinvar, clinvar_local, query
from helper_variants.clinvar_adapter import LocalEvidence


def fingerprint(path):
    status = path.stat()
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return status.st_size, status.st_mtime_ns, digest


def benchmark(database):
    database = Path(database).resolve(strict=True)
    if Path(str(database) + "-wal").exists():
        raise RuntimeError("Use a quiescent index without an active WAL")
    before = fingerprint(database)
    http_calls = []

    def forbidden(*args, **kwargs):
        http_calls.append(str(args[0]) if args else "network")
        raise AssertionError("Unexpected network request")

    with tempfile.TemporaryDirectory(prefix="helper-cache05-") as directory, ExitStack() as stack:
        copied = Path(directory) / "variants.sqlite"
        shutil.copyfile(database, copied)
        if fingerprint(database) != before or Path(str(database) + "-wal").exists():
            raise RuntimeError("Clinical index changed while copying")
        for module, name in ((socket, "create_connection"), (clinvar, "_request"),
                             (clinvar_local, "urlopen")):
            stack.enter_context(patch.object(module, name, forbidden))
        with sqlite3.connect(copied) as db:
            alleles = db.execute("SELECT reference_build,chromosome,position,reference,alternate FROM variants ORDER BY id").fetchall()
            samples = [row[0] for row in db.execute("SELECT id FROM samples ORDER BY id")]
            record = json.loads(db.execute("SELECT metadata_json FROM runs ORDER BY id LIMIT 1").fetchone()[0])
        start = time.perf_counter()
        with LocalEvidence() as source:
            evidence = source.batch(alleles, record=record)
            snapshot = source.snapshot_id
        acquisition_seconds = time.perf_counter() - start
        states = Counter(row["matching_status"] for row in evidence)
        classified = sum(bool(row["classifications"]) for row in evidence)
        timings = Counter()

        def timed(name, function):
            def wrapped(*args, **kwargs):
                started = time.perf_counter()
                try:
                    return function(*args, **kwargs)
                finally:
                    timings[name] += time.perf_counter() - started
            return wrapped

        stack.enter_context(patch.object(query, "score_variant", timed("priority_seconds", query.score_variant)))
        stack.enter_context(patch.object(query, "apply_clinvar_evidence", timed("priority_seconds", query.apply_clinvar_evidence)))
        stack.enter_context(patch.object(LocalEvidence, "batch", timed("list_acquisition_seconds", LocalEvidence.batch)))
        summaries = []
        start = time.perf_counter()
        for sample in samples:
            # The first priority request computes the whole sample, before limit=1.
            page = query.list_variants(copied, sample, limit=1, record=record)
            assert page["clinvar_snapshot_id"] == snapshot
            summaries.append(dict(sample_id=sample, first_page_size=len(page["items"])))
        list_seconds = time.perf_counter() - start
        result = dict(variants=len(alleles), samples=len(samples), snapshot_id=snapshot,
                      matching_counts={state: states[state] for state in (
                          "FOUND", "NOT_FOUND", "UNRESOLVED", "AMBIGUOUS", "ERROR")},
                      germline_classified=classified, acquisition_seconds=acquisition_seconds,
                      list_seconds=list_seconds, **timings, http_calls=len(http_calls),
                      source_index_unchanged=fingerprint(database) == before,
                      method="Temporary index copy; all sample priorities computed before pagination")
        if not result["source_index_unchanged"] or Path(str(database) + "-wal").exists():
            raise RuntimeError("Clinical index changed during benchmark")
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = benchmark(args.database)
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
