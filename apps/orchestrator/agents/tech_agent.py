"""Tech specialist: reads OHLCV and argues a vote."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langgraph.prebuilt import create_react_agent

from ..tool_registry import get_tech_tool

TECH_PROMPT = """You are the TECHNICAL ANALYSIS specialist on a 3-agent trading committee.

You MUST call your OHLCV tool exactly once with the symbol you are evaluating. Then read the candles and indicators (RSI, support, resistance, volume) and reason out loud about whether the chart structure favours BUY, SELL, or HOLD.

When you are done analysing, respond with EXACTLY one line of valid JSON, prefixed with `FINAL:` and nothing after it:

FINAL: {"agent": "tech_agent", "vote": "BUY", "rationale": "<one paragraph, max ~80 words>"}

Vote must be one of "BUY", "SELL", or "HOLD". The rationale must cite specific numbers you saw in the candles or indicators. Do not pad with disclaimers.
"""


def build_tech_agent(model: BaseChatModel):
    """Construct the Tech specialist as a LangGraph react agent.

    Tool selection is deferred to the `tool_registry` so the `--mock` CLI
    flag (and the offline mock-mode pytest) can swap in `dummy_market` at
    build time without touching this module.
    """
    return create_react_agent(
        model=model,
        tools=[get_tech_tool()],
        name="tech_agent",
        prompt=TECH_PROMPT,
    )
