"""graphspec command line: validate | render | diff | trace | scaffold | serve."""

from __future__ import annotations

import argparse
import sys

DEFAULT_FILE = "./graphspec.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="graphspec",
        description="Declare, render, validate, diff, trace and scaffold agent-graph topologies.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="check a graph against the format rules")
    p.add_argument("file", nargs="?", default=DEFAULT_FILE)
    p.add_argument("--strict", action="store_true", help="promote warnings to errors")
    p.add_argument("--target", choices=["claude"], help="also warn about advisory fields for this scaffold target")

    p = sub.add_parser("render", help="emit Graphviz DOT (or SVG/PNG via dot)")
    p.add_argument("file", nargs="?", default=DEFAULT_FILE)
    p.add_argument("--format", choices=["dot", "svg", "png"], default="dot")

    p = sub.add_parser("diff", help="semantic diff of two graph files")
    p.add_argument("old")
    p.add_argument("new")
    p.add_argument("--format", choices=["text", "markdown"], default="text")

    p = sub.add_parser("trace", help="overlay real OTLP executions on the declared graph")
    p.add_argument("file", nargs="?", default=DEFAULT_FILE)
    p.add_argument("--otlp", required=True, help="OTLP JSON file or collector endpoint")
    p.add_argument("--session", help="filter spans to one session.id")

    p = sub.add_parser("scaffold", help="generate Claude Code artifacts from the graph")
    p.add_argument("file", nargs="?", default=DEFAULT_FILE)
    p.add_argument("--out", default=".")
    p.add_argument("--force", action="store_true", help="overwrite existing files")
    p.add_argument("--target", choices=["claude"], default="claude")

    p = sub.add_parser("serve", help="local editor with live render and validation")
    p.add_argument("file", nargs="?", default=DEFAULT_FILE)
    p.add_argument("--port", type=int, default=8321)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        from graphspec.validate import run
        return run(args.file, strict=args.strict, target=args.target)
    if args.command == "render":
        from graphspec.render import run
        return run(args.file, fmt=args.format)
    if args.command == "diff":
        from graphspec.diff import run
        return run(args.old, args.new, fmt=args.format)
    if args.command == "trace":
        from graphspec.trace.cli import run
        return run(args.file, otlp=args.otlp, session=args.session)
    if args.command == "scaffold":
        from graphspec.scaffold import run
        return run(args.file, out=args.out, force=args.force, target=args.target)
    if args.command == "serve":
        from graphspec.serve import run
        return run(args.file, port=args.port)
    return 2


if __name__ == "__main__":
    sys.exit(main())
