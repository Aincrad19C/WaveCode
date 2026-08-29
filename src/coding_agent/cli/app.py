"""CLI entry point: argparse, wiring, exit codes (docs/09 §5, docs/08 §6)."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from coding_agent import __version__
from coding_agent.cli.branding import CLI_NAME, GLYPH_WAVE, PRODUCT_NAME

EXIT_OK = 0
EXIT_CRASH = 1
EXIT_CONFIG = 2
EXIT_AUTH = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=CLI_NAME,
        description=f"{PRODUCT_NAME}: a from-scratch CLI coding agent",
    )
    parser.add_argument("-V", "--version", action="version", version=f"{CLI_NAME} {__version__}")
    parser.add_argument("--workdir", type=Path, default=None, help="workspace root (default cwd)")
    parser.add_argument("--model", default=None, help="model id")
    parser.add_argument("--think", action="store_true", help="enable thinking mode")
    parser.add_argument("--no-stream", action="store_true", help="disable SSE streaming")
    parser.add_argument("--verbose", action="store_true", help="debug logging")
    parser.add_argument("--max-turns", type=int, default=None, help="max LLM calls per task")
    parser.add_argument("--timeout", type=float, default=None, help="wall clock limit (s)")

    sub = parser.add_subparsers(dest="command")
    run = sub.add_parser("run", help="one-shot task, then exit")
    run.add_argument("task", help="task text, or '-' to read from stdin")
    sub.add_parser("repl", help="interactive session (default)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else list(argv))

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # Imports deferred so `--help` / `--version` stay instant.
    from rich.console import Console

    from coding_agent.app.bootstrap import build_session, load_settings
    from coding_agent.app.jsonl_sink import JsonlLogSink
    from coding_agent.cli.renderer import RichEventSink
    from coding_agent.cli.repl import Repl
    from coding_agent.cli.theme import THEME
    from coding_agent.errors import ConfigError

    settings = load_settings()
    overrides: dict = {}
    if args.workdir is not None:
        overrides["workdir"] = args.workdir
    if args.model is not None:
        overrides["deepseek_model"] = args.model
    if args.think:
        overrides["thinking"] = True
    if args.no_stream:
        overrides["stream"] = False
    if args.max_turns is not None:
        overrides["max_turns"] = args.max_turns
    if args.timeout is not None:
        overrides["max_wallclock_s"] = args.timeout
    if overrides:
        settings = settings.model_copy(update=overrides)

    console = Console(theme=THEME, highlight=False)
    use_tui = args.command != "run" and console.is_terminal and sys.stdin.isatty()

    try:
        log_sink = JsonlLogSink(settings.workdir / settings.log_dir)
        if use_tui:
            from coding_agent.cli.renderer import TuiEventSink
            from coding_agent.cli.view import ChatView

            view = ChatView()
            ui_sink = TuiEventSink(view)
        else:
            ui_sink = RichEventSink(console)
            view = None
        session = build_session(settings, sinks=[ui_sink, log_sink])
    except ConfigError as exc:
        console.print(f"[error]{GLYPH_WAVE} 配置错误：{exc}[/error]")
        return EXIT_CONFIG

    try:
        if args.command == "run":
            task = sys.stdin.read() if args.task == "-" else args.task
            session.start()
            session.ask(task)
        elif use_tui and view is not None:
            from coding_agent.cli.tui import OceanTui

            return OceanTui(session, console, settings, view).run()
        else:
            return Repl(session, console, settings).run()
    except KeyboardInterrupt:
        console.print("[warn]已取消。[/warn]")
        return EXIT_OK
    finally:
        log_sink.close()

    if session.loop.state.cancelled:
        return EXIT_OK
    if getattr(session.loop, "last_end_reason", "") == "auth":
        return EXIT_AUTH
    return EXIT_OK
