"""Hardcoded risk caps for the Risk agent (Milestone 1 mock).

Milestone 4 will replace this with a real risk model that consumes Pyth prices
via `HermesClient` plus the multisig vault balance.
"""

from __future__ import annotations

from langchain_core.tools import tool


@tool
def get_risk_caps(symbol: str) -> dict:
    """Return the per-trade risk envelope for `symbol`.

    Args:
        symbol: Trading pair, e.g. "SOL/USDC".

    Returns:
        Dict with `symbol`, `max_position_usdc`, `max_slippage_bps`,
        `max_daily_trades`, and a vault snapshot.
    """
    return {
        "symbol": symbol,
        "max_position_usdc": 25,
        "max_slippage_bps": 100,  # 1.0%
        "max_daily_trades": 4,
        "vault_balance_usdc": 150,
        "open_exposure_usdc": 0,
        "kill_switch_active": False,
    }
