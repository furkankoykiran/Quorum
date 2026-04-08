"""Live smoke tests for the Quorum MCP stdio clients.

These tests spawn real MCP server subprocesses and make one tool call each.
They're gated behind the `requires_mcp` marker so offline CI skips them;
run locally with:

    uv run pytest tests/test_mcp_clients.py -v -m requires_mcp

OmniWire is exercised unconditionally when the marker is selected — it just
needs `RSS_FEEDS` in the environment (point at `configs/omniwire_feeds.json`).
Freqtrade is auto-skipped unless `FREQTRADE_API_URL` + `FREQTRADE_PASSWORD`
are set, because this repo's host machine has no Freqtrade REST API running.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.requires_mcp


def _ensure_rss_feeds_env() -> None:
    """Load the committed feed config into RSS_FEEDS if the user didn't."""
    if os.environ.get("RSS_FEEDS"):
        return
    config_path = Path(__file__).resolve().parents[1] / "configs" / "omniwire_feeds.json"
    if not config_path.exists():
        pytest.skip(f"missing {config_path}")
    os.environ["RSS_FEEDS"] = config_path.read_text(encoding="utf-8")


def test_omniwire_fetch_news_smoke():
    """Spawn omniwire-mcp, call fetch-news, assert we got at least one item."""
    _ensure_rss_feeds_env()
    from apps.orchestrator.mcp_client import call_tool

    raw = call_tool("omniwire", "fetch-news", {"limit": 3})
    assert raw, "omniwire returned an empty payload"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:  # pragma: no cover — diagnostic only
        pytest.fail(f"omniwire payload was not JSON: {raw[:200]!r} ({exc})")

    # Accept either a bare list or a dict with an items-like key.
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = (
            payload.get("items")
            or payload.get("articles")
            or payload.get("results")
            or payload.get("data")
            or []
        )
    else:  # pragma: no cover — diagnostic only
        pytest.fail(f"unexpected omniwire payload shape: {type(payload).__name__}")

    assert len(items) >= 1, f"expected at least one news item, got {items!r}"


def test_omniwire_tool_returns_quorum_shape():
    """End-to-end: the LangChain tool itself returns the Quorum headline shape."""
    _ensure_rss_feeds_env()
    from apps.orchestrator.tools.omniwire import get_headlines_live

    result = get_headlines_live.invoke({"symbol": "SOL/USDC"})
    assert isinstance(result, dict)
    assert result.get("symbol") == "SOL/USDC"
    assert isinstance(result.get("headlines"), list)
    assert result["headlines"], "expected at least one headline from OmniWire"
    first = result["headlines"][0]
    for key in ("source", "ts", "title", "summary"):
        assert key in first, f"missing key {key!r} in normalised headline"


@pytest.mark.skipif(
    not (os.environ.get("FREQTRADE_API_URL") and os.environ.get("FREQTRADE_PASSWORD")),
    reason="FREQTRADE_API_URL / FREQTRADE_PASSWORD not set; no live Freqtrade backend.",
)
def test_freqtrade_get_market_data_smoke():
    """Only runs when the host has a live Freqtrade REST backend configured."""
    from apps.orchestrator.mcp_client import call_tool

    raw = call_tool(
        "freqtrade",
        "get_market_data",
        {"pair": "BTC/USDT", "timeframe": "1h", "limit": 5},
    )
    assert raw, "freqtrade returned an empty payload"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:  # pragma: no cover
        pytest.fail(f"freqtrade payload was not JSON: {raw[:200]!r} ({exc})")
    assert payload, "expected a non-empty payload from get_market_data"
