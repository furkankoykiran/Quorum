"""Hardcoded OHLCV payload for the Tech agent (Milestone 1 mock).

Replaced in Milestone 2 by a thin MCP client that calls
`furkankoykiran/freqtrade-mcp` over stdio.
"""

from __future__ import annotations

from langchain_core.tools import tool

# Plausible SOL/USDC daily candles, oversold-but-holding-support pattern.
_MOCK_CANDLES = [
    {"t": "2026-04-01", "o": 158.20, "h": 161.40, "l": 153.10, "c": 154.80, "v": 9_812_345},
    {"t": "2026-04-02", "o": 154.70, "h": 156.90, "l": 149.10, "c": 150.20, "v": 11_402_881},
    {"t": "2026-04-03", "o": 150.10, "h": 151.80, "l": 146.40, "c": 148.30, "v": 13_209_500},
    {"t": "2026-04-04", "o": 148.30, "h": 149.95, "l": 144.60, "c": 145.10, "v": 12_080_111},
    {"t": "2026-04-05", "o": 145.00, "h": 147.20, "l": 141.50, "c": 142.40, "v": 14_551_200},
    {"t": "2026-04-06", "o": 142.30, "h": 146.10, "l": 140.80, "c": 144.90, "v": 10_990_770},
    {"t": "2026-04-07", "o": 144.80, "h": 149.20, "l": 144.10, "c": 148.60, "v": 9_215_642},
]


@tool
def get_ohlcv(symbol: str) -> dict:
    """Return recent daily candles plus a headline RSI value for `symbol`.

    Args:
        symbol: Trading pair, e.g. "SOL/USDC".

    Returns:
        Dict with `symbol`, last 7 daily `candles`, and approximate `rsi_14`.
    """
    return {
        "symbol": symbol,
        "timeframe": "1d",
        "candles": _MOCK_CANDLES,
        "rsi_14": 28.4,
        "support_level": 142.0,
        "resistance_level": 158.0,
        "note": "Oversold by RSI, holding the $142 support after a -10% week.",
    }
