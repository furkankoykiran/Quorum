"""Replay a saved debate transcript with cinematic formatting.

Loads a JSON file from ``debate_runs/`` and re-prints it to stdout,
matching the visual style of the debate CLI but with optional per-turn
delays for Loom screen recordings.  This is the Day-3 stub for
Milestone 7's Arweave-backed transcript viewer.

Usage:
    uv run python -m apps.orchestrator.cli replay debate_runs/<file>.json
    uv run python -m apps.orchestrator.cli replay debate_runs/<file>.json --delay 2.0
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import TextIO


def replay_debate(path: Path, *, delay: float = 1.0, stream: TextIO | None = None) -> int:
    """Load and replay a debate transcript.

    Args:
        path: Path to a debate JSON file.
        delay: Seconds to pause between specialist turns (0 = instant).
        stream: Output stream (defaults to ``sys.stdout``).

    Returns:
        0 on success, non-zero on error.
    """
    out = stream or sys.stdout
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 1

    payload = json.loads(path.read_text(encoding="utf-8"))
    symbol = payload.get("symbol", "UNKNOWN")
    transcript = payload.get("transcript", [])
    votes = payload.get("votes", {})
    final_decision = payload.get("final_decision", "N/A")

    print("=" * 72, file=out)
    print(f"  QUORUM REPLAY  |  symbol: {symbol}", file=out)
    print(f"  source: {path.name}", file=out)
    print("=" * 72, file=out)

    for i, turn in enumerate(transcript):
        if i > 0 and delay > 0:
            time.sleep(delay)
        print("", file=out)
        print(f"[{turn['agent']}]  vote: {turn['vote']}", file=out)
        print(f"  rationale: {turn['rationale']}", file=out)

    if delay > 0:
        time.sleep(delay)
    print("", file=out)
    print("-" * 72, file=out)
    print(f"  TALLY: {json.dumps(votes, indent=None)}", file=out)
    print(f"  FINAL DECISION: {final_decision}", file=out)
    print("=" * 72, file=out)
    return 0
