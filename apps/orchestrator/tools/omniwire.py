"""Live News tool backed by the `omniwire-mcp` stdio MCP server.

This replaces `dummy_news.get_headlines` when `QUORUM_USE_MOCK` is unset.
The return shape is kept identical to the dummy tool so the News agent's
prompt contract (`FINAL: {...}` JSON) does not need to change.

Design notes:
- We filter by the base currency of the symbol (e.g. "SOL" for "SOL/USDC")
  so the headlines are at least loosely on-topic. OmniWire's `fetch-news`
  tool does a string-contains match server-side.
- We cap at 5 headlines and truncate each summary to ~200 chars. This keeps
  the tool result well under the Z.ai gateway's tool-payload budget we
  observed on Day 1 (~300-token ceiling before truncation bites).
- If the MCP call fails or returns an unparseable payload, we raise a
  RuntimeError so the Day-2 mock-mode fallback is an explicit operator
  decision (`--mock`), not a silent degradation.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from ..mcp_client import call_tool

_MAX_HEADLINES = 5
_MAX_SUMMARY_CHARS = 200


def _base_symbol(symbol: str) -> str:
    """Return the base currency of a trading pair, e.g. 'SOL/USDC' -> 'SOL'."""
    return symbol.split("/", 1)[0].strip().upper() if "/" in symbol else symbol.strip().upper()


def _truncate(text: str, limit: int = _MAX_SUMMARY_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _coerce_items(payload: Any) -> list[dict[str, Any]]:
    """Normalise fetch-news payloads to a flat list of item dicts.

    OmniWire may return a bare list, or an object with `items`/`articles`/
    `results`. We try each shape and fall back to an empty list.
    """
    if isinstance(payload, list):
        return [i for i in payload if isinstance(i, dict)]
    if isinstance(payload, dict):
        for key in ("items", "articles", "results", "data", "headlines"):
            value = payload.get(key)
            if isinstance(value, list):
                return [i for i in value if isinstance(i, dict)]
    return []


def _normalise_headline(item: dict[str, Any]) -> dict[str, str]:
    """Normalise a single OmniWire item into Quorum's headline shape."""
    source = (
        item.get("source")
        or item.get("sourceName")
        or item.get("sourceId")
        or item.get("feed")
        or "unknown"
    )
    if isinstance(source, dict):
        source = source.get("name") or source.get("id") or "unknown"
    ts = (
        item.get("ts")
        or item.get("publishedAt")
        or item.get("published")
        or item.get("pubDate")
        or item.get("isoDate")
        or ""
    )
    title = item.get("title") or item.get("headline") or ""
    summary_raw = (
        item.get("summary")
        or item.get("description")
        or item.get("contentSnippet")
        or item.get("content")
        or ""
    )
    return {
        "source": str(source),
        "ts": str(ts),
        "title": str(title).strip(),
        "summary": _truncate(str(summary_raw)),
    }


@tool
def get_headlines_live(symbol: str) -> dict:
    """Return the latest macro and crypto headlines relevant to `symbol`.

    Calls the `fetch-news` tool on the `omniwire-mcp` server over stdio,
    filters server-side by the base currency (e.g. "SOL" for "SOL/USDC"),
    and returns up to 5 normalised headlines.

    Args:
        symbol: Trading pair, e.g. "SOL/USDC".

    Returns:
        Dict with `symbol` and a list of recent `headlines`
        (each `source`, `ts`, `title`, `summary`).
    """
    raw = call_tool(
        "omniwire",
        "fetch-news",
        {"filter": _base_symbol(symbol), "limit": _MAX_HEADLINES},
    )
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"omniwire.fetch-news returned non-JSON payload: {raw[:200]!r}") from exc
    items = _coerce_items(payload)[:_MAX_HEADLINES]
    return {
        "symbol": symbol,
        "headlines": [_normalise_headline(i) for i in items],
    }
