"""Shared state for the Quorum trading-committee debate.

The debate runs as an explicit `StateGraph` with deterministic sequential
edges: tech → news → risk → tally. Each specialist node appends one
`AgentTurn` to `transcript`; the `tally` node fills `votes` and
`final_decision`. Milestone 4 will replace the equal-weight tally with an
LLM-driven Shapley counterfactual node.
"""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

Vote = Literal["BUY", "SELL", "HOLD"]


class AgentTurn(TypedDict):
    """One specialist's contribution to the debate transcript."""

    agent: str
    vote: Vote
    rationale: str


class DebateState(TypedDict, total=False):
    """LangGraph state shared across the debate pipeline.

    `transcript` uses `operator.add` so each specialist can return a
    one-element list and LangGraph concatenates them. `votes` and
    `final_decision` are written once by the tally node.
    """

    symbol: str
    transcript: Annotated[list[AgentTurn], operator.add]
    votes: dict[str, Vote]
    final_decision: Vote
