"""Pure readers over the runner's jsonl artefacts.

Never raise mid-request: a malformed line is skipped, a missing file returns
an empty list or an empty-counter dict. The runner writes append-only, so a
partially-flushed last line is possible mid-read and must be tolerated.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import paths


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def read_debate_log(limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
    """Return the most recent ``limit`` debates, newest first, after ``offset``."""
    rows = _read_jsonl(paths.debate_log_path())
    rows.reverse()
    return rows[offset : offset + limit]


def read_debate_by_id(debate_id: str) -> dict[str, Any] | None:
    """Linear scan over the debate log for a ``{symbol}-{ts}`` identifier."""
    for row in _read_jsonl(paths.debate_log_path()):
        if f"{row.get('symbol')}-{row.get('ts')}" == debate_id:
            return row
    return None


def read_shapley_history(k: int = 10, limit: int = 100) -> list[dict[str, Any]]:
    """Return the tail of shapley_history.jsonl (up to ``limit`` rows).

    ``k`` is echoed back by the caller as the rolling-window size; it is not a
    filter on the returned rows.
    """
    rows = _read_jsonl(paths.shapley_history_path())
    return rows[-limit:]


def read_runner_metrics() -> dict[str, Any]:
    path = paths.runner_metrics_path()
    if not path.exists():
        return _empty_metrics()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _empty_metrics()


def tail_line(path: Path) -> str | None:
    """Return the last non-empty line in ``path``, or ``None`` if unavailable."""
    if not path.exists():
        return None
    last: str | None = None
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                last = stripped
    return last


def _empty_metrics() -> dict[str, Any]:
    return {
        "total": 0,
        "success": 0,
        "errors": 0,
        "rate_limit_errors": 0,
        "parse_failures": 0,
        "retries": 0,
        "pyth_gate_holds": 0,
        "jupiter_quotes_attached": 0,
        "dry_run_built": 0,
        "shapley_attached": 0,
        "success_rate": 0.0,
        "avg_latency": 0.0,
        "p95_latency": 0.0,
        "recent_errors": [],
    }


def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip())
