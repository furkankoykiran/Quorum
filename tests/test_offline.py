"""Fast offline unit tests that never spawn an LLM or an MCP subprocess.

This is the suite CI runs. Every assertion here must stay deterministic and
zero-network so the gate is trustworthy without secrets.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# vote.parse_final + tally
# ---------------------------------------------------------------------------


def test_parse_final_extracts_structured_tail():
    from apps.orchestrator.vote import parse_final

    text = (
        "Some preamble and reasoning here.\n"
        'FINAL: {"agent": "tech_agent", "vote": "BUY", "rationale": "RSI 28 oversold"}'
    )
    turn = parse_final(text)
    assert turn is not None
    assert turn["agent"] == "tech_agent"
    assert turn["vote"] == "BUY"
    assert turn["rationale"] == "RSI 28 oversold"


def test_parse_final_rejects_missing_marker():
    from apps.orchestrator.vote import parse_final

    assert parse_final("no marker here") is None
    assert parse_final("") is None


def test_parse_final_rejects_invalid_vote():
    from apps.orchestrator.vote import parse_final

    bad = 'FINAL: {"agent": "tech_agent", "vote": "MAYBE", "rationale": "x"}'
    assert parse_final(bad) is None


def test_tally_majority_with_tiebreak():
    from apps.orchestrator.vote import tally

    # Clear majority.
    turns = [
        {"agent": "tech_agent", "vote": "BUY", "rationale": "a"},
        {"agent": "news_agent", "vote": "BUY", "rationale": "b"},
        {"agent": "risk_agent", "vote": "HOLD", "rationale": "c"},
    ]
    assert tally(turns) == "BUY"

    # Tie between BUY and SELL should fall through to BUY.
    tie = [
        {"agent": "a", "vote": "BUY", "rationale": "x"},
        {"agent": "b", "vote": "SELL", "rationale": "y"},
    ]
    assert tally(tie) == "BUY"

    # Empty returns HOLD.
    assert tally([]) == "HOLD"


# ---------------------------------------------------------------------------
# persistence.save_debate
# ---------------------------------------------------------------------------


@dataclass
class _StubResult:
    symbol: str
    transcript: list
    votes: dict
    final_decision: str

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "transcript": list(self.transcript),
            "votes": dict(self.votes),
            "final_decision": self.final_decision,
        }


def test_save_debate_writes_json_file(tmp_path: Path):
    from apps.orchestrator.persistence import save_debate

    result = _StubResult(
        symbol="SOL/USDC",
        transcript=[
            {"agent": "tech_agent", "vote": "BUY", "rationale": "oversold"},
            {"agent": "news_agent", "vote": "SELL", "rationale": "hot cpi"},
            {"agent": "risk_agent", "vote": "HOLD", "rationale": "caps"},
        ],
        votes={"tech_agent": "BUY", "news_agent": "SELL", "risk_agent": "HOLD"},
        final_decision="BUY",
    )
    path = save_debate(result, run_dir=tmp_path)

    assert path.exists()
    assert path.parent == tmp_path
    assert path.suffix == ".json"
    assert "SOL-USDC" in path.name
    assert ":" not in path.name  # colons must be stripped for Windows safety

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["symbol"] == "SOL/USDC"
    assert payload["final_decision"] == "BUY"
    assert len(payload["transcript"]) == 3


# ---------------------------------------------------------------------------
# tool_registry selector
# ---------------------------------------------------------------------------


def test_tool_registry_respects_mock_flag(monkeypatch):
    from apps.orchestrator.settings import Settings
    from apps.orchestrator.tool_registry import get_news_tool, get_risk_tool, get_tech_tool

    mock_settings = Settings(quorum_use_mock=True, quorum_tech_live=False, _env_file=None)
    monkeypatch.setattr(
        "apps.orchestrator.tool_registry.get_settings",
        lambda: mock_settings,
    )

    assert get_news_tool().name == "get_headlines"
    assert get_tech_tool().name == "get_ohlcv"
    assert get_risk_tool().name == "get_risk_caps"


def test_tool_registry_defaults_to_live_news(monkeypatch):
    from apps.orchestrator.settings import Settings
    from apps.orchestrator.tool_registry import get_news_tool, get_tech_tool

    default_settings = Settings(quorum_use_mock=False, quorum_tech_live=False, _env_file=None)
    monkeypatch.setattr(
        "apps.orchestrator.tool_registry.get_settings",
        lambda: default_settings,
    )

    assert get_news_tool().name == "get_headlines_live"
    # Tech stays on dummy by default until QUORUM_TECH_LIVE=1.
    assert get_tech_tool().name == "get_ohlcv"


# ---------------------------------------------------------------------------
# replay.replay_debate
# ---------------------------------------------------------------------------


def test_replay_debate_prints_transcript(tmp_path: Path):
    """replay_debate loads a JSON file and prints the cinematic output."""
    import io

    from apps.orchestrator.replay import replay_debate

    debate_json = {
        "symbol": "SOL/USDT",
        "transcript": [
            {"agent": "tech_agent", "vote": "BUY", "rationale": "RSI oversold"},
            {"agent": "news_agent", "vote": "HOLD", "rationale": "mixed signals"},
            {"agent": "risk_agent", "vote": "HOLD", "rationale": "caps ok"},
        ],
        "votes": {"tech_agent": "BUY", "news_agent": "HOLD", "risk_agent": "HOLD"},
        "final_decision": "HOLD",
    }
    json_path = tmp_path / "test_debate.json"
    json_path.write_text(json.dumps(debate_json), encoding="utf-8")

    buf = io.StringIO()
    rc = replay_debate(json_path, delay=0, stream=buf)
    output = buf.getvalue()

    assert rc == 0
    assert "QUORUM REPLAY" in output
    assert "SOL/USDT" in output
    assert "tech_agent" in output
    assert "news_agent" in output
    assert "risk_agent" in output
    assert "FINAL DECISION: HOLD" in output


# ---------------------------------------------------------------------------
# Day 9: Pyth gate + Jupiter quote
# ---------------------------------------------------------------------------


def test_pyth_gate_holds_on_subprocess_error(monkeypatch):
    """Subprocess timeout / OSError → fail-closed HOLD with reason hold_error."""
    import subprocess

    from apps.orchestrator.tools import pyth_gate

    def boom(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="pnpm tsx check-price.ts", timeout=5)

    monkeypatch.setattr(pyth_gate.subprocess, "run", boom)
    result = pyth_gate.check_pyth("SOL/USDT")
    assert result["ok"] is False
    assert result["reason"] == "hold_error"


def test_pyth_gate_holds_on_wide_confidence(monkeypatch):
    """conf_pct above the policy threshold → HOLD with reason hold_wide_conf."""
    from apps.orchestrator.tools import pyth_gate

    fake_stdout = (
        "feed=ef0d8b6fda2ceba4   endpoint=https://hermes.pyth.network\n"
        "price=$100.0000  ±$5.0000 (1σ)\n"
        "published=2026-04-16T10:00:00.000Z  staleness=2s\n"
    )

    class _Proc:
        returncode = 0
        stdout = fake_stdout
        stderr = ""

    monkeypatch.setattr(pyth_gate.subprocess, "run", lambda *a, **kw: _Proc())
    result = pyth_gate.check_pyth("SOL/USDT", max_conf_pct=1.0)
    assert result["ok"] is False
    assert result["reason"] == "hold_wide_conf"
    assert result["staleness_s"] == 2
    assert result["conf_pct"] == 5.0


def test_jupiter_quote_attaches_response(monkeypatch):
    """Mocked httpx.get returns a canned Jupiter payload; quote_spot returns it."""
    from apps.orchestrator.tools import jupiter_quote

    canned = {
        "inputMint": jupiter_quote.SOL_MINT,
        "outputMint": jupiter_quote.USDC_MINT,
        "inAmount": "1000000000",
        "outAmount": "84970000",
        "routePlan": [{"swapInfo": {"label": "Raydium"}}],
    }

    class _Resp:
        status_code = 200

        def json(self):
            return canned

    monkeypatch.setattr(
        jupiter_quote.httpx,
        "get",
        lambda *a, **kw: _Resp(),
    )
    out = jupiter_quote.quote_spot(jupiter_quote.SOL_MINT, jupiter_quote.USDC_MINT, 1_000_000_000)
    assert out is not None
    assert out["outAmount"] == "84970000"
    assert out["routePlan"][0]["swapInfo"]["label"] == "Raydium"


# ---------------------------------------------------------------------------
# Day 10: dry-run hook
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Day 11: fork-swap evidence parser
# ---------------------------------------------------------------------------


def test_fork_evidence_parser_round_trip(tmp_path: Path):
    """A well-formed payload round-trips through parse_evidence and the
    Squads-round-trip helper returns True when all five sigs are present
    even if the execute step failed (fork-side ALT gap is expected)."""
    from apps.orchestrator.tools.fork_evidence import (
        ForkEvidenceError,
        load_evidence,
        parse_evidence,
        squads_round_trip_ok,
    )

    good = {
        "ts_start": "2026-04-17T12:21:00Z",
        "ts_end": "2026-04-17T12:21:24Z",
        "fork_rpc": "http://127.0.0.1:18899",
        "multisig_pda": "CqQL1fkyb6oiWrpG7xnTGrraMU1P9HTiY38wwvJYfBWp",
        "vault_pda": "WQUMkUKY5Zq95FHgnrJkY3DkN2BZ9dbcTKEHYUcc1fc",
        "amount_sol": 0.1,
        "jupiter_quote_out_raw": "8826346",
        "vault_before": {"sol_lamports": 2_000_000_000, "usdc_raw": "0"},
        "vault_after": {"sol_lamports": 2_000_000_000, "usdc_raw": "0"},
        "signatures": {
            "vault_transaction_create": "sig_create",
            "proposal_create": "sig_propose",
            "proposal_approve_1": "sig_a1",
            "proposal_approve_2": "sig_a2",
            "proposal_approve_3": "sig_a3",
            "vault_transaction_execute": "",
        },
        "execute": {"ok": False, "error": "Address lookup table account ... not found"},
    }

    parsed = parse_evidence(good)
    assert parsed["multisig_pda"] == good["multisig_pda"]
    assert squads_round_trip_ok(parsed) is True

    # File round-trip.
    path = tmp_path / "fork-swap-evidence-test.json"
    path.write_text(json.dumps(good), encoding="utf-8")
    loaded = load_evidence(path)
    assert loaded["execute"]["ok"] is False

    # Missing a required top-level field fails closed.
    bad_missing = {k: v for k, v in good.items() if k != "signatures"}
    try:
        parse_evidence(bad_missing)
    except ForkEvidenceError as exc:
        assert "signatures" in str(exc)
    else:
        raise AssertionError("parse_evidence should have raised")

    # squads_round_trip_ok returns False when one approve slot is empty.
    missing_approve = {
        **good,
        "signatures": {**good["signatures"], "proposal_approve_2": ""},
    }
    assert squads_round_trip_ok(missing_approve) is False


def test_dry_run_attaches_signature(monkeypatch):
    """Mocked subprocess returns a v0 message; simulate_vault_swap derives sig."""
    import subprocess as _subprocess

    from apps.orchestrator.tools import dry_run

    fake_stdout = (
        '{"simulated": true, "err": null, "compute_units": 12345, '
        '"logs_tail": ["log a", "log b"], "tx_message_b64": "AAAA", '
        '"quote_out_amount": "100", "quote_route_hops": 1}\n'
    )

    def fake_run(*_args, **_kwargs):
        return _subprocess.CompletedProcess(args=_args, returncode=0, stdout=fake_stdout, stderr="")

    monkeypatch.setattr(dry_run.subprocess, "run", fake_run)
    payload = dry_run.simulate_vault_swap(
        "So11111111111111111111111111111111111111112",
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        1_000_000_000,
    )
    assert payload is not None
    assert payload["tx_message_b64"] == "AAAA"
    assert payload["signature"].startswith("sim:")
    assert payload["signature"] == dry_run.derive_dry_run_signature(payload)
