"""Parser for Day 11 fork-swap evidence files.

The `fork-swap-evidence.sh` script writes one JSON file per run under
`data/fork-swap-evidence-<ts>.json`. The orchestrator does not consume these
files at runtime — they are manual artefacts used by the PR body and the
audit log — but we keep a tiny schema-validating loader here so the format
is pinned by a unit test and any future orchestrator hook can reuse it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REQUIRED_TOP_LEVEL = (
    "ts_start",
    "ts_end",
    "fork_rpc",
    "multisig_pda",
    "vault_pda",
    "amount_sol",
    "jupiter_quote_out_raw",
    "vault_before",
    "vault_after",
    "signatures",
    "execute",
)

_REQUIRED_BALANCE_KEYS = ("sol_lamports", "usdc_raw")

_REQUIRED_SIGNATURE_KEYS = (
    "vault_transaction_create",
    "proposal_create",
    "proposal_approve_1",
    "proposal_approve_2",
    "proposal_approve_3",
    "vault_transaction_execute",
)


class ForkEvidenceError(ValueError):
    """Raised when an evidence payload is missing a required field."""


def parse_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate the evidence payload shape and return it unchanged.

    Raises `ForkEvidenceError` if any required field is missing. The caller
    is expected to treat the returned dict as read-only.
    """
    missing = [k for k in _REQUIRED_TOP_LEVEL if k not in payload]
    if missing:
        raise ForkEvidenceError(f"missing top-level fields: {sorted(missing)}")

    for side in ("vault_before", "vault_after"):
        bucket = payload[side]
        if not isinstance(bucket, dict):
            raise ForkEvidenceError(f"{side} must be a dict")
        missing_bal = [k for k in _REQUIRED_BALANCE_KEYS if k not in bucket]
        if missing_bal:
            raise ForkEvidenceError(f"{side} missing balance fields: {sorted(missing_bal)}")

    signatures = payload["signatures"]
    if not isinstance(signatures, dict):
        raise ForkEvidenceError("signatures must be a dict")
    missing_sig = [k for k in _REQUIRED_SIGNATURE_KEYS if k not in signatures]
    if missing_sig:
        raise ForkEvidenceError(f"signatures missing fields: {sorted(missing_sig)}")

    execute = payload["execute"]
    if not isinstance(execute, dict) or "ok" not in execute:
        raise ForkEvidenceError("execute block must have an 'ok' flag")

    return payload


def load_evidence(path: Path) -> dict[str, Any]:
    """Load and validate a fork-swap evidence JSON file."""
    raw = path.read_text(encoding="utf-8")
    return parse_evidence(json.loads(raw))


def squads_round_trip_ok(payload: dict[str, Any]) -> bool:
    """Return True when all five Squads signatures landed.

    The execute step may still have failed (fork lacks Jupiter AMM
    accounts); this helper just certifies the multisig propose/approve
    pipeline worked end-to-end, which is what Day 11 captures as proof.
    """
    sigs = payload["signatures"]
    return all(
        sigs.get(k)
        for k in (
            "vault_transaction_create",
            "proposal_create",
            "proposal_approve_1",
            "proposal_approve_2",
            "proposal_approve_3",
        )
    )
