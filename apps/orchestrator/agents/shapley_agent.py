"""Shapley attribution specialist — counterfactual weights over the debate.

This is the Milestone 4 kickoff (Day 12). The agent runs AFTER
``dry_run`` so the LLM sees the whole debate plus any downstream
artefacts (Jupiter quote, dry-run signature). It scores each
specialist's counterfactual contribution and emits a single
``FINAL: {"weights": {...}, "rationale": "..."}`` JSON line parsed by
:func:`apps.orchestrator.vote.parse_shapley_final`.

The shapley agent intentionally does not carry tools — its whole input
is the current ``DebateState`` — so it is invoked as a plain chat
model rather than as a react agent.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

SHAPLEY_PROMPT = """You are the SHAPLEY ATTRIBUTION specialist for a 3-agent trading committee.

The committee has three specialists: tech_agent, news_agent, risk_agent. You will be given the full debate transcript (each specialist's vote and rationale), the committee's final BUY/SELL/HOLD decision, and any downstream artefacts (Jupiter route quote, dry-run signature). You will NOT be given market data yourself — you score only what happened in the debate.

Your task: estimate each specialist's counterfactual contribution to the final decision on a [0, 1] scale. A higher weight means "if this specialist had been silent or voted differently, the final decision would more likely have flipped". The three weights MUST sum to exactly 1.0 within 0.001.

Scoring heuristics:
- A specialist whose vote matched the final decision and whose rationale was load-bearing (cited a specific number or an explicit veto) weighs highest.
- A specialist who voted against the final decision but was overruled by the tally still has non-zero weight — they forced the others to justify themselves.
- A specialist whose rationale was boilerplate / parse-failed weighs lowest.
- Never return a zero weight; the floor is 0.01.

Respond with EXACTLY one line of valid JSON, prefixed with `FINAL:` and nothing after it:

FINAL: {"weights": {"tech_agent": 0.4, "news_agent": 0.25, "risk_agent": 0.35}, "rationale": "<one paragraph, max ~80 words, naming which specialist carried the most weight and why>"}

Keys must be exactly "tech_agent", "news_agent", "risk_agent". Weights are floats in [0.01, 1.0] that sum to 1.0. The rationale MUST name the highest-weighted specialist and cite one phrase from their rationale.
"""


def _extract_text(content: Any) -> str:
    """Flatten a chat-model response body to a single string."""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    try:
        iterator = iter(content)
    except TypeError:
        return str(content)
    for block in iterator:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
        elif isinstance(block, str):
            parts.append(block)
    return "\n".join(parts)


def _state_summary(state: dict[str, Any]) -> str:
    """Build the user-message body passed to the Shapley LLM."""
    body = {
        "symbol": state.get("symbol"),
        "transcript": state.get("transcript", []),
        "votes": state.get("votes", {}),
        "final_decision": state.get("final_decision"),
        "pyth_gate": state.get("pyth_gate"),
        "jupiter_quote": state.get("jupiter_quote"),
        "dry_run_signature": state.get("dry_run_signature"),
    }
    return (
        "Score each specialist's counterfactual contribution to this final "
        "decision. Respond with exactly one FINAL: line.\n\n"
        "DEBATE STATE:\n" + json.dumps(body, indent=2, default=str)
    )


def run_shapley_attribution(model: BaseChatModel, state: dict[str, Any]) -> str:
    """Invoke the Shapley LLM once and return the raw response text."""
    response = model.invoke(
        [
            SystemMessage(content=SHAPLEY_PROMPT),
            HumanMessage(content=_state_summary(state)),
        ]
    )
    return _extract_text(getattr(response, "content", ""))
