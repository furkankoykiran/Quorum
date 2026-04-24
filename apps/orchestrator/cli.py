"""Command-line entry point for the Quorum orchestrator.

Usage:
    uv run python -m apps.orchestrator.cli debate --symbol SOL/USDC
    uv run python -m apps.orchestrator.cli debate --symbol SOL/USDC --mock
    uv run python -m apps.orchestrator.cli debate --symbol SOL/USDT --verbose
    uv run python -m apps.orchestrator.cli replay debate_runs/<file>.json
    uv run python -m apps.orchestrator.cli replay debate_runs/<file>.json --delay 2.0
    uv run python -m apps.orchestrator.cli run --interval 300 --symbol SOL/USDT

Runs a single debate cycle (or continuous loop), pretty-prints the
transcript + tally to stdout, and dumps the result as JSON into
``debate_runs/`` for Loom footage and Milestone 7 Arweave pinning.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def _format_result(result) -> str:
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append(f"  QUORUM DEBATE  |  symbol: {result.symbol}")
    lines.append("=" * 72)
    for turn in result.transcript:
        lines.append("")
        lines.append(f"[{turn['agent']}]  vote: {turn['vote']}")
        lines.append(f"  rationale: {turn['rationale']}")
    lines.append("")
    lines.append("-" * 72)
    lines.append(f"  TALLY: {json.dumps(result.votes, indent=None)}")
    lines.append(f"  FINAL DECISION: {result.final_decision}")
    lines.append("=" * 72)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quorum", description="Quorum trading committee CLI.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    debate = sub.add_parser("debate", help="Run a single trading-committee debate.")
    debate.add_argument("--symbol", default="SOL/USDC", help="Trading pair (default: SOL/USDC).")
    debate.add_argument("--thread-id", default="cli-1", help="LangGraph thread id.")
    debate.add_argument(
        "--mock",
        action="store_true",
        help="Use offline dummy tools instead of live MCP servers.",
    )
    debate.add_argument(
        "--no-save",
        action="store_true",
        help="Skip writing the JSON transcript to debate_runs/.",
    )
    debate.add_argument(
        "--verbose",
        action="store_true",
        help="Stream each specialist turn as it lands with wall-clock timing.",
    )

    replay_cmd = sub.add_parser("replay", help="Replay a saved debate transcript.")
    replay_cmd.add_argument("file", help="Path to a debate JSON file.")
    replay_cmd.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds between specialist turns (default: 1.0, 0 = instant).",
    )

    run_cmd = sub.add_parser("run", help="Continuous debate loop with metrics.")
    run_cmd.add_argument("--symbol", default="SOL/USDT", help="Trading pair (default: SOL/USDT).")
    run_cmd.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Seconds between debates (default: 300).",
    )
    run_cmd.add_argument(
        "--max-runs",
        type=int,
        default=0,
        help="Stop after N runs (default: 0 = unlimited).",
    )
    run_cmd.add_argument(
        "--verbose",
        action="store_true",
        help="Stream each specialist turn as it lands.",
    )

    api_cmd = sub.add_parser("api", help="Serve the read-only Observatory API.")
    api_cmd.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1).")
    api_cmd.add_argument("--port", type=int, default=8081, help="Bind port (default: 8081).")
    api_cmd.add_argument("--reload", action="store_true", help="Enable uvicorn auto-reload.")

    args = parser.parse_args(argv)

    if args.cmd == "debate":
        # Set QUORUM_USE_MOCK before settings are first read so
        # pydantic-settings picks it up during construction.
        if args.mock:
            os.environ["QUORUM_USE_MOCK"] = "1"

        from .persistence import append_debate_log, save_debate
        from .supervisor import run_debate

        result = run_debate(args.symbol, thread_id=args.thread_id, verbose=args.verbose)
        print(_format_result(result))

        if not result.transcript:
            print("ERROR: no specialist turns were parsed from the debate.", file=sys.stderr)
            return 2

        if not args.no_save:
            path = save_debate(result)
            print(f"\n  transcript saved to: {path}")
            log_path = append_debate_log(result)
            print(f"  appended to: {log_path}")
        return 0

    if args.cmd == "replay":
        from pathlib import Path

        from .replay import replay_debate

        return replay_debate(Path(args.file), delay=args.delay)

    if args.cmd == "run":
        from .runner import run_continuous

        run_continuous(
            symbol=args.symbol,
            interval=args.interval,
            max_runs=args.max_runs,
            verbose=args.verbose,
        )
        return 0

    if args.cmd == "api":
        import uvicorn

        uvicorn.run(
            "apps.api.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
