"""Per-specialist tool selection, toggled by `QUORUM_USE_MOCK`.

This indirection lets the LangGraph agent builders stay unaware of whether
they're wired to real MCP servers or hardcoded mock tools. The CLI sets
`QUORUM_USE_MOCK=1` when `--mock` is passed; the pytest `test_debate_mock_mode`
test does the same so it can run offline without any API keys.

Current routing (Day 2):
- Tech: always `dummy_market.get_ohlcv` until a Freqtrade REST backend is
  reachable. `get_ohlcv_live` ships and is unit-tested, but flipping the
  default is a Day-3 change contingent on FREQTRADE_* env vars.
- News: `dummy_news.get_headlines` when mock, `omniwire.get_headlines_live`
  otherwise. Live is the default.
- Risk: always `dummy_risk.get_risk_caps` — the real risk model lands in
  Milestone 5.
"""

from __future__ import annotations

from .settings import get_settings
from .tools import (
    get_headlines,
    get_headlines_live,
    get_ohlcv,
    get_ohlcv_live,
    get_risk_caps,
)


def get_tech_tool():
    """Return the LangChain tool the Tech specialist should use.

    Setting ``QUORUM_TECH_LIVE=1`` alongside the ``FREQTRADE_*`` env vars
    flips the Tech agent to live candle data without touching agent code.
    """
    cfg = get_settings()
    if not cfg.quorum_use_mock and cfg.quorum_tech_live:
        return get_ohlcv_live
    return get_ohlcv


def get_news_tool():
    """Return the LangChain tool the News specialist should use."""
    if get_settings().quorum_use_mock:
        return get_headlines
    return get_headlines_live


def get_risk_tool():
    """Return the LangChain tool the Risk specialist should use."""
    return get_risk_caps
