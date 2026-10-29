"""CLI for Task 27A.1. No population occurs without an explicit action."""
import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

from helper_next.core.acmg_mechanisms import MechanismEvidenceCache
from helper_next.core.acmg_mechanisms_bulk import BulkPopulation
from helper_next.core.acmg_sources import SourceManager
from helper_next.core.acmg_mechanism_store import MechanismStore
from helper_variants import gene_phenotype


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Expected a positive integer")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description="Populate the Mechanism Evidence Cache from synchronized local G2P/GenCC indexes")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--populate", action="store_true", help="Populate valid associations via the existing resolver")
    actions.add_argument("--dry-run", action="store_true", help="Enumerate and count associations without writing")
    actions.add_argument("--status", action="store_true", help="Read cache statistics and latest bulk progress without writing")
    parser.add_argument("--limit", type=positive, metavar="N", help="Maximum attempts in this invocation; the remaining plan is resumable")
    parser.add_argument("--resume", action="store_true", help="Resume the latest run, skipping completed associations")
    parser.add_argument("--refresh-stale", action="store_true", help="Select only existing obsolete matrices; do not populate missing matrices")
    parser.add_argument("--offline", action="store_true", help="Disable remote fetches, including when enabled by the environment")
    parser.add_argument("--source-db", type=Path, help="Existing gene-phenotype source index")
    parser.add_argument("--cache-db", type=Path, help="Mechanism cache (defaults to HELPER_MECHANISM_DB)")
    parser.add_argument("--report", type=Path, help="Write this invocation's structured report as JSON")
    parser.add_argument("--json", action="store_true", help="Print the structured report")
    parser.add_argument("--verbose", action="store_true", help="Log individual resolver and bulk progress events")
    args = parser.parse_args(argv)
    if not (args.populate or args.dry_run or args.status or args.resume):
        parser.error("Select --populate, --dry-run, --status or --resume")
    if args.status and (args.resume or args.limit or args.refresh_stale):
        parser.error("--status cannot be combined with processing options")
    if args.report and args.report.resolve() in {
            Path(args.source_db or gene_phenotype.cache_path()).resolve(),
            Path(args.cache_db or MechanismStore().path).resolve()}:
        parser.error("--report must not overwrite a source index or mechanism database")
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s", stream=sys.stderr)
    runner = None
    try:
        sources = SourceManager(gene_database=args.source_db, mechanism_fetch=False if args.offline else None)
        runner = BulkPopulation(MechanismEvidenceCache(sources, args.cache_db))
        report = runner.report() if args.status else runner.run(dry_run=args.dry_run, limit=args.limit,
            resume=args.resume, refresh_stale=args.refresh_stale, offline=args.offline)
        exit_code = 2 if report["status"] == "PREFLIGHT_FAILED" else 1 if report.get("errors") else 0
    except KeyboardInterrupt:
        report = runner.report() if runner else {"status": "INTERRUPTED"}
        exit_code = 130
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
        report = {"status": "ERROR", "error_code": type(exc).__name__, "message": str(exc)}
        exit_code = 3 if isinstance(exc, TimeoutError) else 2
    if args.report:
        try:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n")
        except OSError:
            report["report_error"] = "REPORT_COULD_NOT_BE_WRITTEN"
            exit_code = 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2))
    else:
        print("Status:", report["status"])
        for name in ("run_id", "source_records", "source_associations", "normalized_source_associations", "cross_source_associations", "unique_associations", "eligible", "to_process", "processed", "processed_in_invocation", "matrices_saved", "matrices_created", "matrices_updated", "matrices_with_direct_assertion", "matrices_context_only", "unresolved_associations", "mapping_ambiguous", "ambiguous_mapping_associations", "invalid_records", "errors", "sources_unavailable", "source_problems", "snapshots_created", "remaining", "dataset_versions", "elapsed_seconds", "message", "report_error"):
            if name in report:
                print(name + ":", report[name])
        if report.get("cache"):
            print("cache:", report["cache"])
        if report.get("index_stale"):
            print("Warning: source index is stale; no upstream synchronization was performed.")
        if report.get("invalid_records"):
            print("Warning: records without valid stable context were excluded; this is not an exhaustive population of every source record.")
        if report.get("dataset_versions"):
            print("Scope: local indexed data; upstream scientific releases/completeness are not attested.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
