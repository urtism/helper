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

    args = parser.parse_args()

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
