"""Bootstrap command-line interface."""

import argparse
from collections.abc import Sequence

from youtube_factory import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser without executing application logic."""
    parser = argparse.ArgumentParser(prog="youtube-factory", description="YouTube Factory CLI")
    parser.add_argument("--version", action="version", version=__version__)
    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser("status", help="Show bootstrap readiness.")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Run the minimal bootstrap CLI."""
    args = build_parser().parse_args(argv)
    if args.command == "status":
        print("youtube-factory bootstrap ready")
