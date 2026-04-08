"""Live Tech tool backed by the `freqtrade-mcp` stdio MCP server.

Shipped on Day 2 but **not wired into the Tech agent yet** — the Quorum
host machine has no running Freqtrade REST API, so the MCP server would
401 on every call. Once `FREQTRADE_API_URL`, `FREQTRADE_USERNAME`, and
`FREQTRADE_PASSWORD` are present in the environment, flipping the Tech
agent from dummy_market to this tool is a one-line change in
`tool_registry.get_tech_tool()`.

Return shape mirrors `dummy_market.get_ohlcv` so the Tech agent prompt
contract does not change when the flip happens:

    {
        "symbol":          "SOL/USDC",
        "timeframe":       "1d",
        "candles":         [{"t","o","h","l","c","v"}, ...],
        "rsi_14":          <float or None>,
        "support_level":   <float or None>,
        "resistance_level":<float or None>,
        "note":            "<short synthesis>",
    }

RSI / support / resistance are computed client-side from the raw OHLCV
payload because `freqtrade-mcp`'s `get_market_data` returns candles only.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from ..mcp_client import call_tool

_DEFAULT_TIMEFRAME = "1d"
_DEFAULT_LIMIT = 30


def _rsi(closes: list[float], period: int = 14) -> float | None:
    """Classic Wilder RSI over the last `period` closes. Returns None if short."""
    if len(closes) <= period:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    avg_gain = gains / period
    avg_loss = losses / period
    for i in range(period + 1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def _coerce_candles(payload: Any) -> list[dict[str, Any]]:
    """Extract a flat list of candle dicts from the raw MCP payload.

    Freqtrade returns OHLCV either as a list of arrays
    `[[ts, open, high, low, close, volume], ...]` or as a dict with a
    `data` field that contains the same. We tolerate both.
    """
    rows: list[list[Any]] = []
    if isinstance(payload, dict):
        for key in ("data", "candles", "ohlcv"):
            value = payload.get(key)
            if isinstance(value, list):
                rows = value
                break
    elif isinstance(payload, list):
        rows = payload

    candles: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, list) and len(row) >= 6:
            candles.append(
                {
                    "t": row[0],
                    "o": float(row[1]),
                    "h": float(row[2]),
                    "l": float(row[3]),
                    "c": float(row[4]),
                    "v": float(row[5]),
                }
            )
        elif isinstance(row, dict):
            candles.append(
                {
                    "t": row.get("t") or row.get("date") or row.get("timestamp"),
                    "o": float(row.get("o") or row.get("open") or 0.0),
                    "h": float(row.get("h") or row.get("high") or 0.0),
                    "l": float(row.get("l") or row.get("low") or 0.0),
                    "c": float(row.get("c") or row.get("close") or 0.0),
                    "v": float(row.get("v") or row.get("volume") or 0.0),
                }
            )
    return candles


@tool
def get_ohlcv_live(symbol: str) -> dict:
    """Return recent daily candles plus derived indicators for `symbol`.

    Calls `get_market_data` on the `freqtrade-mcp` server over stdio.
    Requires a reachable Freqtrade REST API (`FREQTRADE_API_URL`,
    `FREQTRADE_USERNAME`, `FREQTRADE_PASSWORD` in the environment).

    Args:
        symbol: Trading pair, e.g. "SOL/USDC".

    Returns:
        Dict with `symbol`, `timeframe`, `candles`, and derived
        `rsi_14`, `support_level`, `resistance_level`, `note`.
    """
    raw = call_tool(
        "freqtrade",
        "get_market_data",
        {"pair": symbol, "timeframe": _DEFAULT_TIMEFRAME, "limit": _DEFAULT_LIMIT},
    )
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"freqtrade.get_market_data returned non-JSON payload: {raw[:200]!r}"
        ) from exc

    candles = _coerce_candles(payload)
    if not candles:
        raise RuntimeError(f"freqtrade.get_market_data returned no candles for {symbol!r}")

    closes = [c["c"] for c in candles]
    lows = [c["l"] for c in candles]
    highs = [c["h"] for c in candles]
    rsi_14 = _rsi(closes)
    support = round(min(lows), 4)
    resistance = round(max(highs), 4)
    note = (
        f"{len(candles)} {_DEFAULT_TIMEFRAME} candles. "
        f"Last close {closes[-1]:.4f}, range {support}-{resistance}."
    )

    return {
        "symbol": symbol,
        "timeframe": _DEFAULT_TIMEFRAME,
        # Cap the candles we pass downstream to the last 7 so the Z.ai
        # gateway does not choke on a 30-row payload — the indicators are
        # already summarised above.
        "candles": candles[-7:],
        "rsi_14": rsi_14,
        "support_level": support,
        "resistance_level": resistance,
        "note": note,
    }
