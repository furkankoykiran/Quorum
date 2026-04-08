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

import os

from .tools import (
    get_headlines,
    get_headlines_live,
    get_ohlcv,
    get_ohlcv_live,
    get_risk_caps,
)


def _is_mock() -> bool:
    """True when the orchestrator should use offline mock tools only."""
    value = os.environ.get("QUORUM_USE_MOCK", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def get_tech_tool():
    """Return the LangChain tool the Tech specialist should use.

    Day 2 keeps this on `dummy_market.get_ohlcv` because this machine has
    no running Freqtrade REST API. Setting `QUORUM_TECH_LIVE=1` alongside
    the FREQTRADE_* env vars flips it without touching the agent code.
    """
    if not _is_mock() and os.environ.get("QUORUM_TECH_LIVE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return get_ohlcv_live
    return get_ohlcv


def get_news_tool():
    """Return the LangChain tool the News specialist should use."""
    if _is_mock():
        return get_headlines
    return get_headlines_live


def get_risk_tool():
    """Return the LangChain tool the Risk specialist should use."""
    return get_risk_caps
