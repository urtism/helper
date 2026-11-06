import argparse

import uvicorn

from helper_next.core.nextflow import (
    ValidationError,
    build_nextflow_run_config,
    load_json_file,
    manifest_rows,
    validate_nextflow_inputs,
    write_manifest,
    write_run_config,
)


def main():
    parser = argparse.ArgumentParser(prog="helper-next")
    subparsers = parser.add_subparsers(dest="command")

    serve = subparsers.add_parser("serve", help="Run the local Helper Next server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--reload", action="store_true")

    manifest = subparsers.add_parser("nextflow-manifest", help="Build a Nextflow manifest from Helper JSON files")
    manifest.add_argument("--samplesheet", required=True, help="Helper samplesheet JSON")
    manifest.add_argument("--pipeline", required=True, help="Helper pipeline JSON")
    manifest.add_argument("--tools", required=True, help="Helper tools JSON")
    manifest.add_argument("--out", required=True, help="Output TSV manifest path")
    manifest.add_argument("--run-config", help="Optional output JSON summary for Nextflow launchers")
    manifest.add_argument("--entry-step", help="Samplesheet step to use as Nextflow input")
    manifest.add_argument("--workflow", help="Comma-separated subset of pipeline steps to enable")

    reference = subparsers.add_parser("reference-verify", help="Validate configured FASTA/FAI and record a local manifest")
    reference.add_argument("--assembly", required=True, help="GRCh37/hg19 or GRCh38/hg38")
    reference.add_argument("--record", help="Existing run/reference record JSON (otherwise use HELPER_ACMG_REFERENCE_CONFIG)")
    reference.add_argument("--managed-immutable", action="store_true", help="Attest that reference files are managed as immutable; enable later metadata reuse")
    reference.add_argument("--force", action="store_true", help="Always rescan FASTA/FAI")
    reference.add_argument("--check", action="store_true", help="Check manifest reuse without hashing FASTA; fail if validation is required")

    constraint = subparsers.add_parser("gnomad-constraint-import", help="Import an explicitly downloaded official v4.1.2 TSV into Gene-Phenotype")
    constraint.add_argument("--file", required=True)
    constraint.add_argument("--database")
    constraint.add_argument("--confirm", action="store_true", help="Confirm the file is the official v4.1.2 dataset and authorize its persistent import")
    enrichment = subparsers.add_parser("gnomad-enrich", help="Retrieve/cache v4.1.1 frequencies for every unique indexed run allele")
    enrichment.add_argument("--record", required=True, help="Existing run record JSON")
    enrichment.add_argument("--database", help="Optional existing run SQLite path")
    enrichment.add_argument("--confirm", action="store_true", help="Authorize remote retrieval and persistent cache enrichment")

    args = parser.parse_args()

    if args.command in ("gnomad-constraint-import", "gnomad-enrich"):
        import json
        if not args.confirm:
            parser.error("This persistent operation requires --confirm")
        try:
            if args.command == "gnomad-constraint-import":
                from helper_variants.gnomad_constraint import import_tsv
                result = import_tsv(args.file, args.database, confirmed=True)
            else:
                from helper_variants.gnomad_enrichment import enrich_run
                result = enrich_run(load_json_file(args.record), database=args.database)
        except (OSError, ValueError, RuntimeError) as exc:
            parser.exit(1, f"gnomAD operation failed: {exc}\n")
        print(json.dumps(result, sort_keys=True, indent=2))
        if result.get("status") in ("partial", "failed"):
            parser.exit(1)
        return

    if args.command == "reference-verify":
        import json
        from helper_next.core.reference_validation import validate_reference
        if args.check and args.force:
            parser.error("--check and --force are mutually exclusive")
        try:
            result = validate_reference(args.assembly, load_json_file(args.record) if args.record else None,
                                        managed_immutable=args.managed_immutable, force=args.force, check=args.check)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            parser.exit(1, "Reference validation failed: {}\n".format(exc))
        print(json.dumps(result, sort_keys=True, indent=2))
        return

    if args.command == "serve":
        uvicorn.run(
            "helper_next.api.app:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
        return

    if args.command == "nextflow-manifest":
        samplesheet = load_json_file(args.samplesheet)
        pipeline_config = load_json_file(args.pipeline)
        tools_config = load_json_file(args.tools)
        try:
            validate_nextflow_inputs(
                samplesheet,
                pipeline_config,
                tools_config,
                entry_step=args.entry_step,
                requested_workflow=args.workflow,
            )
        except ValidationError as exc:
            parser.error("Invalid Nextflow inputs:\n{}".format(exc))
        rows = manifest_rows(samplesheet, args.entry_step)
        manifest_path = write_manifest(rows, args.out)
        print("Wrote Nextflow manifest: {}".format(manifest_path))
        if args.run_config:
            run_config = build_nextflow_run_config(
                samplesheet,
                pipeline_config,
                tools_config,
                entry_step=args.entry_step,
                requested_workflow=args.workflow,
            )
            run_config_path = write_run_config(run_config, args.run_config)
            print("Wrote Nextflow run config: {}".format(run_config_path))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
