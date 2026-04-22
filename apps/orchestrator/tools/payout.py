"""Python bridge for the Shapley-weighted payout ix scaffold (Day 14).

Builds a deterministic payout schedule from the rolling-window Shapley
weights produced by the Day-13 graph node and shells out to
``payout.ts`` for a double-gated dry-run simulation. The bridge itself
never broadcasts — `dry_run_payout` invokes ``payout.ts`` without
``--submit`` regardless of the environment, so even an accidental
``QUORUM_PAYOUT_LIVE=1`` export in the runner has no effect.

The hook into the debate graph (post-Shapley) lands in Day 16.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE_DIR = _PROJECT_ROOT / "packages" / "solana-agent"
_TS_SCRIPT = "src/payout.ts"


def build_payout_schedule(
    rolling_weights: Mapping[str, float],
    operator_pubkeys: Sequence[str],
    total_fee_lamports: int,
) -> dict[str, Any]:
    """Map rolling Shapley weights to operator-pubkey lamports.

    Agents (``sorted(rolling_weights.keys())``) are zipped against
    ``operator_pubkeys`` in index order — the first sorted agent takes
    ``operator_pubkeys[0]`` (``operator-1`` by convention), and so on.
    The caller is responsible for supplying at least as many operator
    pubkeys as agents in ``rolling_weights``; extra pubkeys are ignored.

    Per-operator lamports are ``floor(weight × total_fee_lamports)``.
    The rounding residual (``total_fee_lamports - sum(floors)``) is
    added to ``operator-1`` so the payout is fully conservative and
    deterministic.
    """
    if total_fee_lamports < 0:
        raise ValueError("total_fee_lamports must be non-negative")
    agents = sorted(rolling_weights.keys())
    if not agents:
        raise ValueError("rolling_weights is empty")
    if len(operator_pubkeys) < len(agents):
        raise ValueError(
            f"Need at least {len(agents)} operator pubkeys, got {len(operator_pubkeys)}"
        )

    entries: list[dict[str, Any]] = []
    allocated = 0
    for agent, pubkey in zip(agents, operator_pubkeys):
        weight = float(rolling_weights[agent])
        if not 0.0 <= weight <= 1.0:
            raise ValueError(f"Weight for {agent} out of [0, 1]: {weight}")
        lamports = int(weight * total_fee_lamports)  # floor toward zero
        entries.append(
            {
                "agent": agent,
                "operator": pubkey,
                "weight": weight,
                "lamports": lamports,
            }
        )
        allocated += lamports

    residual = int(total_fee_lamports) - allocated
    if residual > 0:
        entries[0]["lamports"] += residual

    return {
        "entries": entries,
        "payload": {entry["operator"]: entry["weight"] for entry in entries},
        "total_fee_lamports": int(total_fee_lamports),
        "allocated_lamports": allocated + (residual if residual > 0 else 0),
        "residual_lamports": residual,
        "residual_operator": entries[0]["operator"],
    }


def dry_run_payout(
    schedule: Mapping[str, Any],
    *,
    timeout_s: int = 30,
    package_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Shell out to ``payout.ts`` in dry-run mode and return the parsed JSON.

    ``schedule`` is the dict returned by :func:`build_payout_schedule`.
    The TypeScript script reads ``schedule['payload']`` from stdin and
    ``schedule['total_fee_lamports']`` from ``--fee-lamports``; we do
    **not** pass ``--submit`` — the bridge is strictly read-only.

    On any subprocess failure (timeout, non-zero exit, unparseable
    stdout), returns ``None`` and logs to stderr; callers never raise
    mid-cycle.
    """
    cwd = package_dir or _PACKAGE_DIR
    payload = schedule.get("payload")
    total = schedule.get("total_fee_lamports")
    if not isinstance(payload, dict) or not isinstance(total, int):
        print("  [payout] invalid schedule passed to dry_run_payout", file=sys.stderr)
        return None

    stdin_text = json.dumps(payload)
    cmd = ["pnpm", "tsx", _TS_SCRIPT, "--fee-lamports", str(total)]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        print(f"  [payout] subprocess error: {exc}", file=sys.stderr)
        return None

    if proc.returncode != 0:
        print(
            f"  [payout] non-zero exit {proc.returncode}: {(proc.stderr or '').strip()[:200]}",
            file=sys.stderr,
        )
        return None

    stdout = (proc.stdout or "").strip().splitlines()
    if not stdout:
        print("  [payout] empty stdout — nothing to parse", file=sys.stderr)
        return None

    try:
        parsed = json.loads(stdout[-1])
    except json.JSONDecodeError as exc:
        print(
            f"  [payout] could not parse stdout: {exc}: {(proc.stdout or '').strip()[-200:]}",
            file=sys.stderr,
        )
        return None

    if not isinstance(parsed, dict) or parsed.get("dry_run") is not True:
        print(
            f"  [payout] unexpected payload shape: {str(parsed)[:200]}",
            file=sys.stderr,
        )
        return None
    return parsed
