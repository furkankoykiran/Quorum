"""Command-line entry point for the Quorum orchestrator.

Usage:
    uv run python -m apps.orchestrator.cli debate --symbol SOL/USDC

Loads environment variables from `.env`, runs a single debate cycle, and
prints the transcript + tally to stdout. This is the script we record for
Loom demos and the SWARM `update-product` submission.
"""

from __future__ import annotations

import argparse
import json
import sys

from dotenv import load_dotenv

from .supervisor import run_debate


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
    load_dotenv()
    parser = argparse.ArgumentParser(prog="quorum", description="Quorum trading committee CLI.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    debate = sub.add_parser("debate", help="Run a single trading-committee debate.")
    debate.add_argument("--symbol", default="SOL/USDC", help="Trading pair (default: SOL/USDC).")
    debate.add_argument("--thread-id", default="cli-1", help="LangGraph thread id.")

    args = parser.parse_args(argv)

    if args.cmd == "debate":
        result = run_debate(args.symbol, thread_id=args.thread_id)
        print(_format_result(result))
        if not result.transcript:
            print("ERROR: no specialist turns were parsed from the debate.", file=sys.stderr)
            return 2
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
