"""Milestone 1 acceptance test for the Quorum trading committee.

Runs one full debate end-to-end and asserts:

1. The transcript contains a turn from every specialist (tech, news, risk).
2. Each turn carries a non-empty rationale, and the rationales are distinct.
3. The final decision is one of BUY / SELL / HOLD.
4. The vote tally matches the equal-weight rule used by `vote.tally`.

This test is gated on `ANTHROPIC_API_KEY` so it can be skipped in offline CI.
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


@pytest.mark.requires_llm
def test_debate_runs_end_to_end():
    from apps.orchestrator.supervisor import run_debate
    from apps.orchestrator.vote import tally

    result = run_debate("SOL/USDC", thread_id="test-1")

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
