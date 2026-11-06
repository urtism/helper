"""Measure offline ClinVar lookups against an explicitly selected snapshot.

Run from the repository root with PYTHONPATH=helper_next/src. No downloads.
The sample contains up to 5,000 distinct queryable alleles per assembly.
"""
import argparse
import json
import random
import statistics
import time
from pathlib import Path

from helper_variants.clinvar_local import ClinVarLocal


def measure(operation, repeats):
    durations = []
    for _ in range(repeats):
        started = time.perf_counter()
        operation()
        durations.append(time.perf_counter() - started)
    return {"repeats": repeats, "median_seconds": statistics.median(durations),
            "min_seconds": min(durations), "max_seconds": max(durations)}


def benchmark(database=None, repeats=5):
    with ClinVarLocal(database) as reader:
        queries = []
        for assembly in ("GRCh37", "GRCh38"):
            queries.extend(tuple(row) for row in reader.connection.execute("""
                SELECT DISTINCT assembly,chromosome,position,reference,alternate
                FROM genomic_positions WHERE match_status='queryable' AND assembly=?
                ORDER BY chromosome,position,reference,alternate LIMIT 5000""", (assembly,)))
        if not queries:
            raise ValueError("No queryable alleles in this snapshot")
        random.Random(4).shuffle(queries)
        results = reader.lookup_batch(queries)
        variation_id = results[0]["matches"][0]["variation_id"]
        output = {"snapshot_id": reader.release()["snapshot_id"], "database": str(reader.path),
                  "database_bytes": reader.path.stat().st_size, "sample_alleles": len(queries),
                  "method": "Warm filesystem cache; first 5000 distinct indexed alleles per assembly, shuffled with seed 4; includes identity qualification and result construction, excludes submissions",
                  "single_lookup": measure(lambda: reader.lookup(*queries[0]), 100),
                  "aggregate": measure(lambda: reader.aggregate(variation_id), 100), "batches": {}}
        for size in (100, 1000, 10000):
            if len(queries) < size:
                output["batches"][str(size)] = {"skipped": "Insufficient distinct alleles"}
                continue
            answers = reader.lookup_batch(queries[:size])
            statuses = {status: sum(r["status"] == status for r in answers) for status in {r["status"] for r in answers}}
            output["batches"][str(size)] = dict(measure(lambda: reader.lookup_batch(queries[:size]), repeats), statuses=statuses)
        return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    result = benchmark(args.database, args.repeats)
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
