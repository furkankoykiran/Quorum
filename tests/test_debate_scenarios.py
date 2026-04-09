"""Parametrised debate scenario tests over multiple symbols.

All tests force ``QUORUM_USE_MOCK=1`` so they run without MCP subprocesses
but still exercise the full LLM debate pipeline.  Gated on ``requires_llm``
because the specialists are LangGraph react agents that need an LLM call.

Run locally with:
    uv run pytest tests/test_debate_scenarios.py -v -m requires_llm
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
    """Shared assertions: all three specialists, distinct rationales, valid tally."""
    from apps.orchestrator.vote import tally

    agent_names = {turn["agent"] for turn in result.transcript}
    assert agent_names == {"tech_agent", "news_agent", "risk_agent"}, (
        f"Expected all three specialists, got {agent_names}."
    )

    rationales = [turn["rationale"].strip() for turn in result.transcript]
    assert all(rationales), "Found an empty rationale."
    assert len(set(rationales)) == 3, "Rationales should be distinct across specialists."

    assert result.final_decision in {"BUY", "SELL", "HOLD"}

    expected = tally(result.transcript)
    assert result.final_decision == expected


@pytest.mark.requires_llm
@pytest.mark.parametrize("symbol", ["SOL/USDT", "BTC/USDT"])
def test_debate_scenario_mock(symbol, monkeypatch):
    """Full mock-mode debate for ``symbol`` — validates the pipeline end-to-end."""
    monkeypatch.setenv("QUORUM_USE_MOCK", "1")

    from apps.orchestrator.supervisor import run_debate

    result = run_debate(symbol, thread_id=f"test-scenario-{symbol}")
    _assert_valid_debate(result)
