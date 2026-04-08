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
    import importlib

    # Mock mode: news agent must receive the dummy headlines tool.
    monkeypatch.setenv("QUORUM_USE_MOCK", "1")
    monkeypatch.delenv("QUORUM_TECH_LIVE", raising=False)
    from apps.orchestrator import tool_registry

    importlib.reload(tool_registry)  # re-read env
    assert tool_registry.get_news_tool().name == "get_headlines"
    assert tool_registry.get_tech_tool().name == "get_ohlcv"
    assert tool_registry.get_risk_tool().name == "get_risk_caps"


def test_tool_registry_defaults_to_live_news(monkeypatch):
    import importlib

    monkeypatch.delenv("QUORUM_USE_MOCK", raising=False)
    monkeypatch.delenv("QUORUM_TECH_LIVE", raising=False)
    from apps.orchestrator import tool_registry

    importlib.reload(tool_registry)
    assert tool_registry.get_news_tool().name == "get_headlines_live"
    # Tech stays on dummy by default until QUORUM_TECH_LIVE=1.
    assert tool_registry.get_tech_tool().name == "get_ohlcv"
