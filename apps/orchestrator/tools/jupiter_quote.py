"""Jupiter lite-api quote helper.

Pure REST GET against ``https://lite-api.jup.ag/swap/v1/quote`` — no
keys, no signing. Caller-friendly: returns ``None`` on any error and
logs to stderr instead of raising.

The orchestrator uses this after the tally node to attach a fresh
quote to the debate state on BUY/SELL verdicts. Day 10 will feed the
quote into ``vault-swap-dry.ts`` for a read-only mainnet simulation.
"""

from __future__ import annotations

import sys
from typing import Any

import httpx

# Mainnet mints — same constants ``vault-swap.ts`` uses.
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

JUP_QUOTE_URL = "https://lite-api.jup.ag/swap/v1/quote"


def quote_spot(
    input_mint: str,
    output_mint: str,
    amount_raw: int,
    *,
    slippage_bps: int = 50,
    timeout_s: float = 10.0,
) -> dict[str, Any] | None:
    """Fetch a Jupiter quote. Returns the JSON dict or ``None`` on error."""
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount_raw),
        "slippageBps": str(slippage_bps),
    }
    try:
        resp = httpx.get(JUP_QUOTE_URL, params=params, timeout=timeout_s)
    except httpx.HTTPError as exc:
        print(f"  [jupiter_quote] network error: {exc}", file=sys.stderr)
        return None

    if resp.status_code != 200:
        print(
            f"  [jupiter_quote] http {resp.status_code}: {resp.text[:200]}",
            file=sys.stderr,
        )
        return None

    try:
        body = resp.json()
    except ValueError as exc:
        print(f"  [jupiter_quote] non-json response: {exc}", file=sys.stderr)
        return None

    if not isinstance(body, dict) or "outAmount" not in body:
        print(
            f"  [jupiter_quote] unexpected payload shape: {str(body)[:200]}",
            file=sys.stderr,
        )
        return None

    return body
