"""Vote tally for the trading committee.

Milestone 1 uses equal weights for the tally itself. Milestone 4 (kicked
off Day 12) adds an LLM-driven Shapley counterfactual parser — see
``parse_shapley_final`` — whose weights are emitted for operator payout
attribution while the binary BUY/SELL/HOLD tally stays equal-weight for
now.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Iterable

from .state import AgentTurn, Vote

_FINAL_RE = re.compile(r"FINAL:\s*(\{.*\})\s*$", re.MULTILINE | re.DOTALL)

DEFAULT_SPECIALIST_AGENTS = frozenset({"tech_agent", "news_agent", "risk_agent"})
SHAPLEY_WEIGHT_TOLERANCE = 1e-3


def parse_final(message_text: str) -> AgentTurn | None:
    """Extract the structured `FINAL: {...}` JSON tail from an agent's reply.

    Returns None if the marker is missing or the JSON cannot be parsed.
    """
    if not message_text:
        return None
    match = _FINAL_RE.search(message_text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    agent = payload.get("agent")
    vote = payload.get("vote")
    rationale = payload.get("rationale")
    if not agent or vote not in ("BUY", "SELL", "HOLD") or not rationale:
        return None
    return AgentTurn(agent=agent, vote=vote, rationale=rationale)


def parse_shapley_final(
    message_text: str,
    *,
    agents: frozenset[str] = DEFAULT_SPECIALIST_AGENTS,
    tolerance: float = SHAPLEY_WEIGHT_TOLERANCE,
) -> tuple[dict[str, float], str] | None:
    """Extract the Shapley FINAL line emitted by ``shapley_agent``.

    Returns ``(weights, rationale)`` when parsing succeeds or ``None`` on
    any of: missing marker, JSON parse failure, missing/malformed keys,
    weight keys that don't match ``agents``, non-numeric or out-of-range
    weights, or weights that don't sum to ~1.0 within ``tolerance``.
    """
    if not message_text:
        return None
    match = _FINAL_RE.search(message_text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None

    weights = payload.get("weights")
    rationale = payload.get("rationale")
    if not isinstance(weights, dict) or not isinstance(rationale, str):
        return None
    if not rationale.strip():
        return None
    if set(weights.keys()) != set(agents):
        return None

    numeric: dict[str, float] = {}
    for key, value in weights.items():
        if isinstance(value, bool):  # bool is an int subclass; reject explicitly
            return None
        if not isinstance(value, (int, float)):
            return None
        numeric[key] = float(value)

    if not all(0.0 <= v <= 1.0 for v in numeric.values()):
        return None
    if abs(sum(numeric.values()) - 1.0) > tolerance:
        return None

    return numeric, rationale.strip()


def tally(turns: Iterable[AgentTurn]) -> Vote:
    """Equal-weight majority vote across the supplied turns.

    Tie-break order: BUY > SELL > HOLD (favour action over inaction; this is
    deliberately revisited in Milestone 4 once Shapley weights exist).
    """
    counts: Counter[Vote] = Counter()
    for turn in turns:
        counts[turn["vote"]] += 1
    if not counts:
        return "HOLD"
    top = counts.most_common()
    top_count = top[0][1]
    leaders = {vote for vote, count in top if count == top_count}
    for preferred in ("BUY", "SELL", "HOLD"):
        if preferred in leaders:
            return preferred  # type: ignore[return-value]
    return "HOLD"
