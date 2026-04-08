"""Vote tally for the trading committee.

Milestone 1 uses equal weights. Milestone 4 swaps in Shapley-weighted votes
once we have enough debate history to compute counterfactuals.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Iterable

from .state import AgentTurn, Vote

_FINAL_RE = re.compile(r"FINAL:\s*(\{.*\})\s*$", re.MULTILINE | re.DOTALL)


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
