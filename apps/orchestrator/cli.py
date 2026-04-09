"""Command-line entry point for the Quorum orchestrator.

Usage:
    uv run python -m apps.orchestrator.cli debate --symbol SOL/USDC
    uv run python -m apps.orchestrator.cli debate --symbol SOL/USDC --mock
    uv run python -m apps.orchestrator.cli debate --symbol SOL/USDT --verbose
    uv run python -m apps.orchestrator.cli replay debate_runs/<file>.json
    uv run python -m apps.orchestrator.cli replay debate_runs/<file>.json --delay 2.0

Loads environment variables from `.env`, runs a single debate cycle, pretty
prints the transcript + tally to stdout, and dumps the result as JSON into
`debate_runs/` for Loom footage and Milestone 7 Arweave pinning. This
script is the source of the SWARM `update-product` Loom recording.
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

    args = parser.parse_args(argv)

    if args.cmd == "debate":
        # Set QUORUM_USE_MOCK before settings are first read so
        # pydantic-settings picks it up during construction.
        if args.mock:
            os.environ["QUORUM_USE_MOCK"] = "1"

        from .persistence import save_debate
        from .supervisor import run_debate

        result = run_debate(args.symbol, thread_id=args.thread_id, verbose=args.verbose)
        print(_format_result(result))

        if not result.transcript:
            print("ERROR: no specialist turns were parsed from the debate.", file=sys.stderr)
            return 2

        if not args.no_save:
            path = save_debate(result)
            print(f"\n  transcript saved to: {path}")
        return 0

    if args.cmd == "replay":
        from pathlib import Path

        from .replay import replay_debate

        return replay_debate(Path(args.file), delay=args.delay)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
