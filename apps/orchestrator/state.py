"""Shared state for the Quorum trading-committee debate.

The debate runs as an explicit `StateGraph` with deterministic sequential
edges: tech → news → risk (Pyth-gated) → tally → jupiter_quote → dry_run.
Each specialist node appends one `AgentTurn` to `transcript`; the `tally`
node fills `votes` and `final_decision`. Milestone 4 will replace the
equal-weight tally with an LLM-driven Shapley counterfactual node.

`pyth_price` / `pyth_gate` are written by the risk node (Day 9). The
post-tally `jupiter_quote_node` attaches `jupiter_quote` for BUY/SELL
verdicts; the `dry_run_node` attaches `dry_run_signature` (Day 10) when
``QUORUM_LIVE`` is unset.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, Optional, TypedDict

Vote = Literal["BUY", "SELL", "HOLD"]
PythGate = Literal["pass", "hold_stale", "hold_wide_conf", "hold_error"]


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
    pyth_price: dict[str, Any]
    pyth_gate: PythGate
    jupiter_quote: Optional[dict[str, Any]]
    dry_run_signature: Optional[str]
