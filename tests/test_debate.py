"""Milestone 1 acceptance tests for the Quorum trading committee.

Two flavours:

* `test_debate_runs_end_to_end` — live LLM gateway run, gated on
  `ANTHROPIC_API_KEY`. Uses whatever tool routing the environment says
  (live News + mock Tech by default on Day 2).
* `test_debate_mock_mode` — forces `QUORUM_USE_MOCK=1` so every specialist
  runs against the dummy tools. Still needs an LLM (the specialists are
  LangGraph react agents), so it's also gated on `ANTHROPIC_API_KEY`, but
  it does not touch any MCP subprocess or external network besides the LLM.
"""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set; skipping live LLM test.",
)


def _assert_valid_debate(result) -> None:
    """Shared assertions both debate tests apply to the result."""
    from apps.orchestrator.vote import tally

    # 1. All three specialists must speak.
    agent_names = {turn["agent"] for turn in result.transcript}
    assert agent_names == {"tech_agent", "news_agent", "risk_agent"}, (
        f"Expected all three specialists, got {agent_names}. Raw transcript: {result.transcript}"
    )

    # 2. Each rationale must be non-empty and rationales must be distinct.
    rationales = [turn["rationale"].strip() for turn in result.transcript]
    assert all(rationales), "Found an empty rationale."
    assert len(set(rationales)) == 3, "Rationales should be distinct across specialists."

    # 3. Final decision is in the allowed set.
    assert result.final_decision in {"BUY", "SELL", "HOLD"}

    # 4. Tally matches the equal-weight rule.
    expected = tally(result.transcript)
    assert result.final_decision == expected


@pytest.mark.requires_llm
def test_debate_runs_end_to_end():
    from apps.orchestrator.supervisor import run_debate

    result = run_debate("SOL/USDC", thread_id="test-live")
    _assert_valid_debate(result)


@pytest.mark.requires_llm
def test_debate_mock_mode(monkeypatch):
    """Full debate with every specialist forced onto the dummy tools.

    This is the offline happy path: no MCP subprocess, no external HTTP
    except the LLM call itself. Catches regressions in the tool_registry
    selector and keeps the `--mock` CLI flag honest.
    """
    monkeypatch.setenv("QUORUM_USE_MOCK", "1")

    # Import AFTER setting the env var so the tool registry sees the flag.
    from apps.orchestrator.supervisor import run_debate

    result = run_debate("SOL/USDC", thread_id="test-mock")
    _assert_valid_debate(result)
