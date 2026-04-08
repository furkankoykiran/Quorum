"""News specialist: reads macro + crypto headlines and argues a vote."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langgraph.prebuilt import create_react_agent

from ..tools import get_headlines

NEWS_PROMPT = """You are the NEWS / MACRO specialist on a 3-agent trading committee.

You MUST call the `get_headlines` tool exactly once with the symbol you are evaluating. Then read each headline and weigh whether the news flow favours BUY, SELL, or HOLD over the next 24 hours.

When you are done analysing, respond with EXACTLY one line of valid JSON, prefixed with `FINAL:` and nothing after it:

FINAL: {"agent": "news_agent", "vote": "SELL", "rationale": "<one paragraph, max ~80 words>"}

Vote must be one of "BUY", "SELL", or "HOLD". The rationale must reference at least one headline by name. Do not invent headlines that were not returned by the tool.
"""


def build_news_agent(model: BaseChatModel):
    """Construct the News specialist as a LangGraph react agent."""
    return create_react_agent(
        model=model,
        tools=[get_headlines],
        name="news_agent",
        prompt=NEWS_PROMPT,
    )
