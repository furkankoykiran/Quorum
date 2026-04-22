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
# Day 12: Shapley counterfactual parser
# ---------------------------------------------------------------------------


def test_parse_shapley_final_extracts_weights_and_rationale():
    from apps.orchestrator.vote import parse_shapley_final

    text = (
        "Some counterfactual reasoning preamble here.\n"
        'FINAL: {"weights": {"tech_agent": 0.5, "news_agent": 0.3, '
        '"risk_agent": 0.2}, "rationale": "Tech carried the vote with RSI 28."}'
    )
    parsed = parse_shapley_final(text)
    assert parsed is not None
    weights, rationale = parsed
    assert weights == {"tech_agent": 0.5, "news_agent": 0.3, "risk_agent": 0.2}
    assert "Tech" in rationale
    # Floats retain dict shape — no silent string coercion.
    assert all(isinstance(v, float) for v in weights.values())


def test_parse_shapley_final_rejects_malformed_payloads():
    from apps.orchestrator.vote import parse_shapley_final

    # Missing marker → None.
    assert parse_shapley_final("no marker here") is None
    assert parse_shapley_final("") is None

    # Weights don't sum to ~1.0 (0.3+0.3+0.3 = 0.9) → None.
    bad_sum = (
        'FINAL: {"weights": {"tech_agent": 0.3, "news_agent": 0.3, '
        '"risk_agent": 0.3}, "rationale": "x"}'
    )
    assert parse_shapley_final(bad_sum) is None

    # Wrong agent key (tech vs tech_agent) → None.
    wrong_keys = (
        'FINAL: {"weights": {"tech": 0.5, "news_agent": 0.3, "risk_agent": 0.2}, "rationale": "x"}'
    )
    assert parse_shapley_final(wrong_keys) is None

    # Weight above 1.0 → None.
    out_of_range = (
        'FINAL: {"weights": {"tech_agent": 1.2, "news_agent": -0.1, '
        '"risk_agent": -0.1}, "rationale": "x"}'
    )
    assert parse_shapley_final(out_of_range) is None

    # Non-numeric weight → None.
    non_numeric = (
        'FINAL: {"weights": {"tech_agent": "0.5", "news_agent": 0.3, '
        '"risk_agent": 0.2}, "rationale": "x"}'
    )
    assert parse_shapley_final(non_numeric) is None

    # Empty rationale → None.
    empty_rationale = (
        'FINAL: {"weights": {"tech_agent": 0.5, "news_agent": 0.3, '
        '"risk_agent": 0.2}, "rationale": "   "}'
    )
    assert parse_shapley_final(empty_rationale) is None


# ---------------------------------------------------------------------------
# Day 13: multi-sample Shapley aggregation + rolling history
# ---------------------------------------------------------------------------


def _shapley_final(tech: float, news: float, risk: float, note: str = "x") -> str:
    return (
        f'FINAL: {{"weights": {{"tech_agent": {tech}, "news_agent": {news}, '
        f'"risk_agent": {risk}}}, "rationale": "{note}"}}'
    )


def test_aggregate_shapley_samples_averages_valid_ignores_invalid():
    from apps.orchestrator.vote import aggregate_shapley_samples

    samples = [
        _shapley_final(0.50, 0.30, 0.20, "tech carried"),
        _shapley_final(0.40, 0.40, 0.20, "news swung"),
        "garbage output with no FINAL line",
        'FINAL: {"weights": {"tech_agent": 2.0, "news_agent": -1.0, '
        '"risk_agent": 0.0}, "rationale": "bad"}',  # out of range — dropped
    ]
    out = aggregate_shapley_samples(samples)
    assert out is not None
    weights, rationale = out

    # Only the two valid samples should be averaged.
    assert abs(weights["tech_agent"] - 0.45) < 1e-3
    assert abs(weights["news_agent"] - 0.35) < 1e-3
    assert abs(weights["risk_agent"] - 0.20) < 1e-3
    assert abs(sum(weights.values()) - 1.0) < 1e-3

    # Rationale must carry the multi-sample tag + the accepted rationales.
    assert rationale.startswith("avg(n=2)")
    assert "tech carried" in rationale and "news swung" in rationale

    # Too few valid samples (need ≥ 2) → None so supervisor falls back.
    assert aggregate_shapley_samples([_shapley_final(0.5, 0.3, 0.2)]) is None


def test_aggregate_shapley_samples_rejects_outliers_and_renormalises():
    from apps.orchestrator.vote import aggregate_shapley_samples

    # Four samples where one is a tech-agent outlier (0.9 vs ~0.3 cluster).
    # Outlier-dropped tech mean is ~0.3 — close to the cluster.
    samples = [
        _shapley_final(0.30, 0.50, 0.20),
        _shapley_final(0.32, 0.48, 0.20),
        _shapley_final(0.30, 0.50, 0.20),
        _shapley_final(0.90, 0.05, 0.05),  # outlier across every agent
    ]
    out = aggregate_shapley_samples(samples)
    assert out is not None
    weights, _rationale = out

    # Tech cluster mean ~0.307 without the 0.90 outlier; keep it well under 0.5.
    assert weights["tech_agent"] < 0.5
    # Final weights sum to 1.0 within tolerance after renormalisation.
    assert abs(sum(weights.values()) - 1.0) < 1e-3
    # Floor enforced: no agent drops below 0.01.
    assert all(v >= 0.01 for v in weights.values())


def test_shapley_history_round_trip(tmp_path: Path):
    from apps.orchestrator.tools.shapley_history import append_weights, load_rolling_average

    path = tmp_path / "shapley_history.jsonl"

    # Empty history → equal weights (never None so payout path is safe).
    empty = load_rolling_average(k=3, path=path)
    assert set(empty.keys()) == {"tech_agent", "news_agent", "risk_agent"}
    assert all(abs(v - 1 / 3) < 1e-6 for v in empty.values())

    # Fewer than k lines → still the equal-weight fallback.
    append_weights({"tech_agent": 0.7, "news_agent": 0.2, "risk_agent": 0.1}, path=path)
    short = load_rolling_average(k=3, path=path)
    assert all(abs(v - 1 / 3) < 1e-6 for v in short.values())

    # Fill the window with three records; rolling average equals per-agent mean.
    append_weights({"tech_agent": 0.5, "news_agent": 0.3, "risk_agent": 0.2}, path=path)
    append_weights({"tech_agent": 0.3, "news_agent": 0.4, "risk_agent": 0.3}, path=path)
    avg = load_rolling_average(k=3, path=path)
    assert abs(avg["tech_agent"] - (0.7 + 0.5 + 0.3) / 3) < 1e-6
    assert abs(avg["news_agent"] - (0.2 + 0.3 + 0.4) / 3) < 1e-6
    assert abs(avg["risk_agent"] - (0.1 + 0.2 + 0.3) / 3) < 1e-6

    # Window=2 tails the last two records only (drops the 0.7 tech line).
    recent = load_rolling_average(k=2, path=path)
    assert abs(recent["tech_agent"] - (0.5 + 0.3) / 2) < 1e-6

    # Malformed line must be skipped without blowing up.
    with path.open("a", encoding="utf-8") as fh:
        fh.write("not-json\n")
    robust = load_rolling_average(k=3, path=path)
    # Window=3 now includes: {0.5,0.3,0.2}, {0.3,0.4,0.3}, and the junk line
    # (counted into the tail). Malformed line is silently dropped, so per-agent
    # means use the two surviving numeric rows.
    assert abs(robust["tech_agent"] - (0.5 + 0.3) / 2) < 1e-6


# ---------------------------------------------------------------------------
# Day 14: payout scaffold (Python bridge)
# ---------------------------------------------------------------------------


def test_build_payout_schedule_floors_and_routes_residual_to_operator_1():
    from apps.orchestrator.tools.payout import build_payout_schedule

    # Pick a total fee that floors unevenly across three agents: with weights
    # 0.40/0.35/0.25 × 1_000_003 = 400001.2, 350001.05, 250000.75 → floors
    # 400001, 350001, 250000 (sum 1_000_002) → residual 1 to operator-1.
    rolling = {"news_agent": 0.35, "risk_agent": 0.25, "tech_agent": 0.40}
    pubkeys = ["OP1_PUBKEY_STUB", "OP2_PUBKEY_STUB", "OP3_PUBKEY_STUB"]
    schedule = build_payout_schedule(rolling, pubkeys, 1_000_003)

    # Agents are sorted deterministically; the first sorted agent is the
    # residual sink regardless of which weight it carries.
    assert [e["agent"] for e in schedule["entries"]] == [
        "news_agent",
        "risk_agent",
        "tech_agent",
    ]
    assert schedule["residual_operator"] == "OP1_PUBKEY_STUB"
    assert schedule["residual_lamports"] == 1

    lamports_by_op = {e["operator"]: e["lamports"] for e in schedule["entries"]}
    assert lamports_by_op["OP1_PUBKEY_STUB"] == 350001 + 1  # floor + residual
    assert lamports_by_op["OP2_PUBKEY_STUB"] == 250000
    assert lamports_by_op["OP3_PUBKEY_STUB"] == 400001
    # Conservation: every lamport of the total fee is accounted for.
    assert sum(lamports_by_op.values()) == 1_000_003
    # The payload passed on stdin to payout.ts is keyed by pubkey and weight.
    assert schedule["payload"] == {
        "OP1_PUBKEY_STUB": 0.35,
        "OP2_PUBKEY_STUB": 0.25,
        "OP3_PUBKEY_STUB": 0.40,
    }

    # Too few pubkeys must fail fast before any lamport math.
    import pytest

    with pytest.raises(ValueError):
        build_payout_schedule(rolling, ["only-one"], 100)


def test_dry_run_payout_parses_subprocess_json(monkeypatch):
    """Mocked subprocess: dry_run_payout surfaces the last-line JSON payload."""
    import subprocess as _subprocess

    from apps.orchestrator.tools import payout as payout_module

    fake_stdout = (
        "[payout] mode=DRY-RUN  operators=2  fee=200 lamports  residual=0\n"
        '{"dry_run": true, "submit": false, "payout_live": false, '
        '"rpc_url": "http://127.0.0.1:18899", '
        '"schedule": [{"operator": "OP1", "weight": 0.5, "lamports": 100}, '
        '{"operator": "OP2", "weight": 0.5, "lamports": 100}], '
        '"total_fee_lamports": 200, "residual_lamports": 0, '
        '"residual_operator": "OP1"}\n'
    )
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["stdin"] = kwargs.get("input")
        return _subprocess.CompletedProcess(args=cmd, returncode=0, stdout=fake_stdout, stderr="")

    monkeypatch.setattr(payout_module.subprocess, "run", fake_run)

    schedule = {
        "payload": {"OP1": 0.5, "OP2": 0.5},
        "total_fee_lamports": 200,
    }
    result = payout_module.dry_run_payout(schedule)
    assert result is not None
    assert result["dry_run"] is True
    assert result["total_fee_lamports"] == 200
    assert len(result["schedule"]) == 2

    # The subprocess must have been invoked without --submit (no live path).
    assert "--submit" not in captured["cmd"]
    # Stdin must be the JSON payload keyed by pubkey, not the whole schedule.
    assert json.loads(captured["stdin"]) == {"OP1": 0.5, "OP2": 0.5}

    # Non-zero exit → None, no exception.
    def fake_fail(cmd, **kwargs):
        return _subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(payout_module.subprocess, "run", fake_fail)
    assert payout_module.dry_run_payout(schedule) is None


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
