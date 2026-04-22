"""Persistence for Shapley weights across debate cycles.

Day 13 introduces a rolling-window average over the last K successful
Shapley aggregations — the signal each individual LLM call emits is
noisy, and operator payout downstream should settle against a smoothed
distribution rather than a single cycle's verdict.

One JSON line is appended per successful aggregation to
``data/shapley_history.jsonl`` (the ``data/`` directory is gitignored).
``load_rolling_average`` tails the last K lines and returns the mean
weight per agent; when fewer than K lines exist, it returns an
equal-weight distribution so the payout path never sees ``None``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from ..vote import DEFAULT_SPECIALIST_AGENTS

_DEFAULT_HISTORY_PATH = Path("data/shapley_history.jsonl")


def _equal_weights(agents: frozenset[str] = DEFAULT_SPECIALIST_AGENTS) -> dict[str, float]:
    """Uniform distribution over the registered specialist agents."""
    even = 1.0 / len(agents)
    return {agent: even for agent in agents}


def append_weights(
    weights: Mapping[str, float],
    *,
    path: Path | str = _DEFAULT_HISTORY_PATH,
    ts: str | None = None,
) -> Path:
    """Append a single ``{ts, weights}`` line to the jsonl history.

    Creates the parent directory if it doesn't already exist. Returns
    the resolved path so callers can assert against it in tests.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": ts or datetime.now(timezone.utc).isoformat(),
        "weights": {str(k): float(v) for k, v in weights.items()},
    }
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")
    return target


def load_rolling_average(
    k: int = 10,
    *,
    path: Path | str = _DEFAULT_HISTORY_PATH,
    agents: frozenset[str] = DEFAULT_SPECIALIST_AGENTS,
) -> dict[str, float]:
    """Return the mean weight per agent across the last ``k`` history lines.

    When the file is missing or has fewer than ``k`` lines, returns an
    equal-weight distribution. Malformed lines are silently skipped — a
    garbled write should never blow up the debate cycle. When every
    surviving line is missing an agent key, that agent inherits the
    equal-weight fallback so the return value always covers every agent.
    """
    target = Path(path)
    fallback = _equal_weights(agents)
    if k <= 0 or not target.exists():
        return fallback

    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return fallback

    tail = lines[-k:]
    if len(tail) < k:
        return fallback

    sums: dict[str, float] = {agent: 0.0 for agent in agents}
    counts: dict[str, int] = {agent: 0 for agent in agents}
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        weights = payload.get("weights")
        if not isinstance(weights, dict):
            continue
        for agent in agents:
            raw = weights.get(agent)
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                sums[agent] += float(raw)
                counts[agent] += 1

    result: dict[str, float] = {}
    for agent in agents:
        if counts[agent] == 0:
            result[agent] = fallback[agent]
        else:
            result[agent] = round(sums[agent] / counts[agent], 6)
    return result
