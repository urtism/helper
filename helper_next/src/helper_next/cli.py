import argparse

import uvicorn


def main():
    parser = argparse.ArgumentParser(prog="helper-next")
    subparsers = parser.add_subparsers(dest="command")

    serve = subparsers.add_parser("serve", help="Run the local Helper Next server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--reload", action="store_true")

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

    parser.print_help()
