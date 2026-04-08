"""News specialist: reads macro + crypto headlines and argues a vote."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langgraph.prebuilt import create_react_agent

from ..tool_registry import get_news_tool

NEWS_PROMPT = """You are the NEWS / MACRO specialist on a 3-agent trading committee.

You MUST call your headlines tool exactly once with the symbol you are evaluating. Then read each headline and weigh whether the news flow favours BUY, SELL, or HOLD over the next 24 hours.

When you are done analysing, respond with EXACTLY one line of valid JSON, prefixed with `FINAL:` and nothing after it:

FINAL: {"agent": "news_agent", "vote": "SELL", "rationale": "<one paragraph, max ~80 words>"}

Vote must be one of "BUY", "SELL", or "HOLD". The rationale must reference at least one headline by name. Do not invent headlines that were not returned by the tool.
"""


def build_news_agent(model: BaseChatModel):
    """Construct the News specialist as a LangGraph react agent.

    Tool selection is deferred to `tool_registry` so `QUORUM_USE_MOCK=1`
    swaps in `dummy_news` for offline CI and the `--mock` CLI flag.
    """
    return create_react_agent(
        model=model,
        tools=[get_news_tool()],
        name="news_agent",
        prompt=NEWS_PROMPT,
    )
