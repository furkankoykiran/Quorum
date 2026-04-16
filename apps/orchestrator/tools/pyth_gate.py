"""Pyth Hermes price gate used by the Risk specialist node.

Shells out to ``packages/solana-agent/src/check-price.ts`` so the Python
orchestrator and the on-chain TypeScript path agree on staleness, conf,
and feed selection. Fail-closed: any subprocess error → HOLD.

The TS script already exits 1 above ``--max-stale``. This wrapper layers
a confidence-percent policy on top (TS does not enforce it).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE_DIR = _PROJECT_ROOT / "packages" / "solana-agent"
_TS_SCRIPT = "src/check-price.ts"

_FEED_RE = re.compile(r"feed=([0-9a-f]+)")
_PRICE_RE = re.compile(r"price=\$([0-9.]+)\s+±\$([0-9.]+)")
_STALENESS_RE = re.compile(r"staleness=(-?\d+)s")


def _parse_stdout(stdout: str) -> dict[str, Any] | None:
    feed_m = _FEED_RE.search(stdout)
    price_m = _PRICE_RE.search(stdout)
    stale_m = _STALENESS_RE.search(stdout)
    if not (feed_m and price_m and stale_m):
        return None
    price = float(price_m.group(1))
    conf = float(price_m.group(2))
    if price <= 0:
        return None
    return {
        "feed": feed_m.group(1),
        "price": price,
        "conf": conf,
        "conf_pct": (conf / price) * 100.0,
        "staleness_s": int(stale_m.group(1)),
    }


def check_pyth(
    symbol: str,
    *,
    max_stale_s: int = 60,
    max_conf_pct: float = 1.0,
    timeout_s: int = 15,
    package_dir: Path | None = None,
) -> dict[str, Any]:
    """Run the TS Pyth reader and return a gate decision.

    Returns a dict with ``ok`` and ``reason`` always set. ``reason`` is one
    of ``pass``, ``hold_stale``, ``hold_wide_conf``, ``hold_error``. On
    success, the dict also carries ``price``, ``conf``, ``conf_pct``,
    ``staleness_s``, ``feed``.

    ``symbol`` is currently informational — the TS script defaults to
    SOL/USD. A future iteration can pass a symbol→feed-id map.
    """
    cwd = package_dir or _PACKAGE_DIR
    cmd = ["pnpm", "tsx", _TS_SCRIPT, "--max-stale", str(max_stale_s)]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        print(f"  [pyth_gate] subprocess error for {symbol}: {exc}", file=sys.stderr)
        return {"ok": False, "reason": "hold_error"}

    parsed = _parse_stdout(proc.stdout or "")
    # Non-zero exit on a parseable payload means staleness > max_stale_s.
    if proc.returncode != 0:
        if parsed is not None and parsed["staleness_s"] > max_stale_s:
            parsed.update({"ok": False, "reason": "hold_stale"})
            return parsed
        print(
            f"  [pyth_gate] non-zero exit {proc.returncode} for {symbol}: "
            f"{(proc.stderr or '').strip()[:200]}",
            file=sys.stderr,
        )
        return {"ok": False, "reason": "hold_error"}

    if parsed is None:
        print(
            f"  [pyth_gate] could not parse stdout for {symbol}: "
            f"{(proc.stdout or '').strip()[:200]}",
            file=sys.stderr,
        )
        return {"ok": False, "reason": "hold_error"}

    if parsed["conf_pct"] > max_conf_pct:
        parsed.update({"ok": False, "reason": "hold_wide_conf"})
        return parsed

    parsed.update({"ok": True, "reason": "pass"})
    return parsed
