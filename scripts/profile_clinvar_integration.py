"""Reproducible CACHE-05.1 profiling; clinical indices are copied, never written.

Run each timing repetition in a fresh process. OS caches are not flushed.
The profile phase adds instrumentation and must not be used for speed ratios.
"""
import argparse
from collections import Counter
from contextlib import ExitStack
import cProfile
import hashlib
import importlib.util
import json
from pathlib import Path
import pstats
import resource
import shutil
import socket
import sqlite3
import tempfile
import time
from unittest.mock import patch

from benchmark_clinvar_integration import benchmark, fingerprint
from helper_next.core import acmg_reference, biological_identity
from helper_variants import clinvar, clinvar_adapter, clinvar_local, indexer, query
from helper_variants.clinvar_adapter import LocalEvidence


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def outputs(database):
    """Hash every evidence, score and row in global order; include page-200 cost."""
    database = Path(database).resolve(strict=True)
    before = fingerprint(database)
    if Path(str(database) + "-wal").exists():
        raise RuntimeError("Use a quiescent index without WAL")
    with tempfile.TemporaryDirectory(prefix="helper-profile-") as directory:
        copied = Path(directory) / "variants.sqlite"
        shutil.copyfile(database, copied)
        with sqlite3.connect(copied) as db:
            alleles = db.execute("SELECT reference_build,chromosome,position,reference,alternate FROM variants ORDER BY id").fetchall()
            samples = [row[0] for row in db.execute("SELECT id FROM samples ORDER BY id")]
            record = json.loads(db.execute("SELECT metadata_json FROM runs ORDER BY id LIMIT 1").fetchone()[0])
        query._PRIORITY_ORDER_CACHE.clear()
        start = time.perf_counter()
        first = query.list_variants(copied, samples[0], limit=200, record=record)
        first_seconds = time.perf_counter() - start
        start = time.perf_counter()
        from fastapi.encoders import jsonable_encoder
        encoded = json.dumps(jsonable_encoder(first), ensure_ascii=False, separators=(",", ":"))
        serialization = time.perf_counter() - start
        start = time.perf_counter()
        next_page = query.list_variants(copied, samples[0], limit=200, record=record,
                                        cursor=first["next_cursor"])
        next_seconds = time.perf_counter() - start
        query._PRIORITY_ORDER_CACHE.clear()
        start = time.perf_counter()
        warm_first = query.list_variants(copied, samples[0], limit=200, record=record)
        warm_first_seconds = time.perf_counter() - start
        assert warm_first == first
        start = time.perf_counter()
        with LocalEvidence() as source:
            evidence = source.batch(alleles, record=record)
        warm_batch_seconds = time.perf_counter() - start
        pages = []
        for sample in samples:
            items, cursor = [], None
            while True:
                page = query.list_variants(copied, sample, cursor=cursor, limit=500, record=record)
                items.extend(page["items"])
                cursor = page["next_cursor"]
                if cursor is None:
                    break
            pages.append(dict(sample_id=sample, items=items))
        assert fingerprint(database) == before
        return dict(evidence_digest=digest(evidence), ordered_items_digest=digest(pages),
                    first_page_digest=digest(first), next_page_digest=digest(next_page),
                    first_page_seconds=first_seconds, next_page_seconds=next_seconds,
                    warm_first_page_seconds=warm_first_seconds, warm_batch_seconds=warm_batch_seconds,
                    serialization_seconds=serialization, response_bytes=len(encoded.encode()),
                    row_count=sum(len(page["items"]) for page in pages),
                    first_page_size=len(first["items"]))


def profile(database, destination):
    times, counts = Counter(), Counter()

    def timed(name, function):
        def wrapped(*args, **kwargs):
            started = time.perf_counter()
            counts[name] += 1
            try:
                return function(*args, **kwargs)
            finally:
                times[name] += time.perf_counter() - started
        return wrapped

    class Cursor(sqlite3.Cursor):
        def execute(self, sql, *args):
            self.category = ("sql_matching" if "JOIN genomic_positions" in sql else
                             "sql_aggregates" if "FROM classifications" in sql or "FROM variants WHERE variation_id" in sql else
                             "sql_manifest" if "FROM metadata" in sql else
                             "sql_submission_counts" if "FROM submissions" in sql else "sql_index_other")
            return timed(self.category, super().execute)(sql, *args)

        def fetchone(self):
            return timed(self.category + "_rows", super().fetchone)()

        def fetchall(self):
            return timed(self.category + "_rows", super().fetchall)()

        def __next__(self):
            return timed(self.category + "_rows", super().__next__)()

    class Connection(sqlite3.Connection):
        def execute(self, sql, *args):
            return self.cursor(factory=Cursor).execute(sql, *args)

    connect = sqlite3.connect
    def profiled_connect(*args, **kwargs):
        kwargs.setdefault("factory", Connection)
        return connect(*args, **kwargs)

    methods = [
        (clinvar_local.ClinVarLocal, "__init__", "clinvar_open_inclusive"),
        (clinvar_local.ClinVarLocal, "release", "manifest"),
        (acmg_reference, "reference_record", "reference_metadata"),
        (indexer, "open_reference", "open_reference"),
        (indexer, "normalize_allele", "normalization"),
        (biological_identity, "_allele_contig", "contig_qualification"),
        (biological_identity, "_result", "ga2_result_digest"),
        (biological_identity, "allele_refs", "allele_refs_inclusive"),
        (LocalEvidence, "_adapt", "adapter_conversion"),
        (query, "_compact_variant", "variant_construction_inclusive"),
        (query, "_sort_priority", "priority_sort"),
        (query, "_filter_priority", "priority_filter"),
    ]
    profiler = cProfile.Profile()
    with ExitStack() as stack:
        stack.enter_context(patch.object(sqlite3, "connect", profiled_connect))
        for obj, name, label in methods:
            stack.enter_context(patch.object(obj, name, timed(label, getattr(obj, name))))
        profiler.enable()
        result = benchmark(database)
        profiler.disable()
    profiler.dump_stats(str(destination.with_suffix(".pstats")))
    stats = pstats.Stats(profiler)
    top = sorted((dict(file=key[0], line=key[1], name=key[2], calls=value[1],
                       self_seconds=value[2], cumulative_seconds=value[3])
                  for key, value in stats.stats.items()), key=lambda row: row["cumulative_seconds"], reverse=True)[:80]
    return dict(scenario=result, phases={name: dict(calls=counts[name], seconds=seconds)
                                         for name, seconds in times.items()}, top=top)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--mode", choices=("measure", "profile", "outputs"), required=True)
    parser.add_argument("--baseline-source", help="Saved source root: restore only the three pre-optimization functions")
    args = parser.parse_args()
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    http_calls = []
    def forbidden(*args, **kwargs):
        http_calls.append(1)
        raise AssertionError("Unexpected HTTP/network access")
    with ExitStack() as stack:
        stack.enter_context(patch.object(socket, "create_connection", forbidden))
        stack.enter_context(patch.object(clinvar, "_request", forbidden))
        stack.enter_context(patch.object(clinvar_local, "urlopen", forbidden))
        if args.baseline_source:
            def load(name, relative):
                spec = importlib.util.spec_from_file_location(name, Path(args.baseline_source) / relative)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module
            old_reference = load("baseline_reference", "helper_next/core/acmg_reference.py")
            old_identity = load("baseline_identity", "helper_next/core/biological_identity.py")
            old_local = load("baseline_local", "helper_variants/clinvar_local.py")
            # Both old call sites must share the same existing checksum LRU.
            old_reference._checksum = acmg_reference._checksum
            stack.enter_context(patch.object(acmg_reference, "verify", old_reference.verify))
            stack.enter_context(patch.object(biological_identity, "allele_refs", old_identity.allele_refs))
            stack.enter_context(patch.object(clinvar_local.ClinVarLocal, "lookup_batch", old_local.ClinVarLocal.lookup_batch))
        result = (benchmark(args.database) if args.mode == "measure" else
                  outputs(args.database) if args.mode == "outputs" else
                  profile(args.database, destination))
    result.update(peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  network_attempts=len(http_calls), mode=args.mode,
                  baseline_functions_restored=bool(args.baseline_source),
                  shared_source_digests={module.__name__: hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
                                         for module in (clinvar_adapter, query)})
    destination.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key not in {"top", "phases"}}, indent=2))


if __name__ == "__main__":
    main()
