"""Hardcoded headlines for the News agent (Milestone 1 mock).

Replaced in Milestone 2 by an MCP client that calls
`furkankoykiran/OmniWire-MCP`.
"""

from __future__ import annotations

from langchain_core.tools import tool

_MOCK_HEADLINES = [
    {
        "source": "Bloomberg",
        "ts": "2026-04-08T13:30:00Z",
        "title": "US March CPI prints 3.5% YoY, hotter than 3.4% consensus",
        "summary": (
            "March headline CPI surprised to the upside, the third hot print in a row. "
            "Two-year yields jumped 12bps; risk assets sold off into the close."
        ),
    },
    {
        "source": "CoinDesk",
        "ts": "2026-04-08T11:05:00Z",
        "title": "Solana DEX volumes hit 3-month high despite SOL pullback",
        "summary": (
            "Jupiter aggregator volume topped $4.2B in the last 24h — the highest "
            "since January — even as SOL traded below $150."
        ),
    },
    {
        "source": "The Block",
        "ts": "2026-04-08T08:42:00Z",
        "title": "Helius reports record validator participation on Solana mainnet",
        "summary": (
            "Active validator count hit a new ATH this week; stake distribution "
            "improved by 4% on the Nakamoto coefficient."
        ),
    },
]


@tool
def get_headlines(symbol: str) -> dict:
    """Return the latest macro + Solana-specific headlines relevant to `symbol`.

    Args:
        symbol: Trading pair, e.g. "SOL/USDC".

    Returns:
        Dict with `symbol` and a list of recent `headlines`.
    """
    return {
        "symbol": symbol,
        "headlines": _MOCK_HEADLINES,
    }
