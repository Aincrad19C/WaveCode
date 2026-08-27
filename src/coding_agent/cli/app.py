"""CLI entry. Agent REPL lands later; --help / --version must work now."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from coding_agent import __version__
from coding_agent.cli.branding import CLI_NAME, PRODUCT_NAME


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=CLI_NAME,
        description=f"{PRODUCT_NAME}: a from-scratch CLI coding agent for DeepSeek",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"{CLI_NAME} {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = sys.argv[1:] if argv is None else list(argv)
    if not args:
        parser.print_help()
        return 0
    parser.parse_args(args)
    return 0
