"""Read-only Jupiter swap simulation via vault-swap-dry.ts.

Subprocess-calls the TypeScript dry-run script with the supplied mints +
notional. Returns the parsed JSON payload (or ``None`` on any failure).
The supervisor uses this when the committee votes BUY/SELL and
``QUORUM_LIVE`` is unset, so the runner produces a per-cycle dry-run
signature without ever broadcasting.

The TS path quotes Jupiter, builds the swap instruction set, and asks
mainnet RPC to ``simulateTransaction`` with sigVerify=false and
replaceRecentBlockhash=true. No keypair is loaded.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE_DIR = _PROJECT_ROOT / "packages" / "solana-agent"
_TS_SCRIPT = "src/vault-swap-dry.ts"


def derive_dry_run_signature(payload: dict[str, Any]) -> str:
    """Compact identifier for the dry-run, derived from the v0 message."""
    msg_b64 = payload.get("tx_message_b64") or ""
    digest = hashlib.sha256(msg_b64.encode("utf-8")).hexdigest()[:16]
    return f"sim:{digest}"


def simulate_vault_swap(
    input_mint: str,
    output_mint: str,
    amount_raw: int,
    *,
    slippage_bps: int = 50,
    rpc_url: str | None = None,
    timeout_s: int = 60,
    package_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Run vault-swap-dry.ts and return the parsed JSON payload.

    On any subprocess error, non-zero exit, or unparseable stdout the
    function returns ``None`` and logs to stderr — supervisor never
    raises mid-debate.
    """
    cwd = package_dir or _PACKAGE_DIR
    cmd = [
        "pnpm",
        "tsx",
        _TS_SCRIPT,
        "--input-mint",
        input_mint,
        "--output-mint",
        output_mint,
        "--amount-raw",
        str(amount_raw),
        "--slippage",
        str(slippage_bps),
    ]
    if rpc_url:
        cmd.extend(["--rpc-url", rpc_url])

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
        print(f"  [dry_run] subprocess error: {exc}", file=sys.stderr)
        return None

    if proc.returncode != 0:
        print(
            f"  [dry_run] non-zero exit {proc.returncode}: {(proc.stderr or '').strip()[:200]}",
            file=sys.stderr,
        )
        return None

    last_line = (proc.stdout or "").strip().splitlines()[-1:] or [""]
    try:
        payload = json.loads(last_line[0])
    except json.JSONDecodeError as exc:
        print(
            f"  [dry_run] could not parse stdout: {exc}: {(proc.stdout or '').strip()[-200:]}",
            file=sys.stderr,
        )
        return None

    if not isinstance(payload, dict) or "tx_message_b64" not in payload:
        print(
            f"  [dry_run] unexpected payload shape: {str(payload)[:200]}",
            file=sys.stderr,
        )
        return None

    payload["signature"] = derive_dry_run_signature(payload)
    return payload
