"""Deterministic StateGraph wiring for the Quorum trading committee.

The debate runs as an explicit `StateGraph` with hard-coded sequential edges:

    START → tech → news → risk (Pyth-gated) → tally → jupiter_quote → END

Each specialist node spins up a short-lived `create_react_agent`, feeds it
the symbol, extracts the `FINAL: {...}` JSON tail, and appends one
`AgentTurn` to `state["transcript"]`. The risk node first runs a Pyth
Hermes staleness/confidence gate (Day 9): a failing gate skips the LLM
call and forces a HOLD with a gate-citing rationale. The tally node runs
the equal-weight vote rule. The post-tally `jupiter_quote_node` attaches
a fresh Jupiter route quote on BUY/SELL verdicts. Milestone 4 swaps the
tally node for an LLM-driven Shapley counterfactual.

This module deliberately does NOT use `langgraph-supervisor`'s LLM-routed
handoff pattern — during Milestone 1 we observed that non-Anthropic gateway
routing (e.g. Z.ai proxy) did not reliably follow a "consult all three"
instruction, so the graph has to force the ordering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langgraph.graph import END, START, StateGraph

from .agents import build_news_agent, build_risk_agent, build_tech_agent
from .state import AgentTurn, DebateState, PythGate, Vote
from .tools.jupiter_quote import SOL_MINT, USDC_MINT, quote_spot
from .tools.pyth_gate import check_pyth
from .vote import parse_final, tally

# Default notional for the post-tally Jupiter quote. 1 SOL mirrors what
# vault-swap.ts targets and matches the largest devnet vault holding.
_DEFAULT_QUOTE_AMOUNT_LAMPORTS = 1_000_000_000


@dataclass
class DebateResult:
    """Outcome of a single trading-committee debate."""

    symbol: str
    transcript: list[AgentTurn]
    votes: dict[str, Vote]
    final_decision: Vote
    pyth_price: dict[str, Any] | None = None
    pyth_gate: PythGate | None = None
    jupiter_quote: dict[str, Any] | None = None
    dry_run_signature: str | None = None
    raw_messages: list[BaseMessage] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "transcript": list(self.transcript),
            "votes": dict(self.votes),
            "final_decision": self.final_decision,
            "pyth_price": self.pyth_price,
            "pyth_gate": self.pyth_gate,
            "jupiter_quote": self.jupiter_quote,
            "dry_run_signature": self.dry_run_signature,
        }


def _build_model(model_name: str) -> BaseChatModel:
    """Build a LiteLLM-backed chat model for any `provider/model` id.

    Uses ``langchain_community.chat_models.ChatLiteLLM`` so the same code
    path works for DeepSeek, Anthropic, OpenAI, Gemini, etc. Provider is
    inferred from the prefix of ``model_name`` (e.g. ``deepseek/...`` or
    ``anthropic/...``). Per-provider API keys come from :mod:`settings`
    and are exposed as env vars for LiteLLM to pick up.
    """
    from langchain_litellm import ChatLiteLLM

    from .settings import get_settings

    cfg = get_settings()

    # LiteLLM reads provider keys from env vars. Surface whichever keys the
    # user has set so any provider in quorum_model works without extra wiring.
    import os

    if cfg.deepseek_api_key:
        os.environ.setdefault("DEEPSEEK_API_KEY", cfg.deepseek_api_key)
        os.environ.setdefault("DEEPSEEK_API_BASE", cfg.deepseek_api_base)
    if cfg.anthropic_api_key:
        os.environ.setdefault("ANTHROPIC_API_KEY", cfg.anthropic_api_key)
    if cfg.anthropic_base_url.strip():
        os.environ.setdefault("ANTHROPIC_API_BASE", cfg.anthropic_base_url)
    if cfg.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", cfg.openai_api_key)
    if cfg.gemini_api_key:
        os.environ.setdefault("GEMINI_API_KEY", cfg.gemini_api_key)

    return ChatLiteLLM(model=model_name, temperature=0.0)


def _last_ai_text(messages: list[BaseMessage]) -> str:
    """Return the last AIMessage content as a flat string, coalescing blocks."""
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        content = msg.content
        if isinstance(content, str):
            return content
        # Anthropic can return a list of content blocks — concatenate the text.
        parts: list[str] = []
        for block in content:  # type: ignore[union-attr]
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return ""


def _run_specialist(agent, symbol: str, agent_name: str) -> AgentTurn:
    """Invoke one specialist react agent and parse its FINAL: tail."""
    seed = {
        "role": "user",
        "content": f"Analyse {symbol}. Call your tool, then respond with the FINAL: JSON line.",
    }
    result = agent.invoke({"messages": [seed]})
    text = _last_ai_text(result.get("messages", []))
    parsed = parse_final(text)
    if parsed is None:
        # Record the failure as a HOLD with a diagnostic rationale so the tally
        # still has something to work with and downstream tests see it.
        return AgentTurn(
            agent=agent_name,
            vote="HOLD",
            rationale=f"[parse_failed] raw_tail={text[-200:]!r}",
        )
    return parsed


def _make_specialist_node(
    builder: Callable[[BaseChatModel], Any], agent_name: str, model: BaseChatModel
):
    """Return a graph-node function bound to `agent_name` and its builder."""
    agent = builder(model)

    def node(state: DebateState) -> dict[str, Any]:
        turn = _run_specialist(agent, state["symbol"], agent_name)
        return {"transcript": [turn]}

    node.__name__ = f"{agent_name}_node"
    return node


def _make_risk_node(model: BaseChatModel):
    """Risk specialist wrapped in a Pyth Hermes staleness/confidence gate.

    Gate fail (stale, wide conf, or subprocess error) → forced HOLD turn,
    LLM call skipped. Gate pass → run the LLM as normal and prepend the
    gate result to the rationale so the persisted log carries both.
    """
    agent = build_risk_agent(model)

    def node(state: DebateState) -> dict[str, Any]:
        gate = check_pyth(state["symbol"])
        gate_keys = ("price", "conf", "conf_pct", "staleness_s", "feed")
        pyth_price = {k: gate[k] for k in gate_keys if k in gate}

        if not gate["ok"]:
            staleness = gate.get("staleness_s")
            conf_pct = gate.get("conf_pct")
            staleness_str = f"{staleness}s" if staleness is not None else "?"
            conf_str = f"{conf_pct:.3f}%" if isinstance(conf_pct, (int, float)) else "?"
            turn = AgentTurn(
                agent="risk_agent",
                vote="HOLD",
                rationale=(
                    f"[pyth_gate:{gate['reason']} staleness={staleness_str} "
                    f"conf={conf_str}] forced HOLD; live LLM evaluation skipped."
                ),
            )
            return {
                "transcript": [turn],
                "pyth_price": pyth_price,
                "pyth_gate": gate["reason"],
            }

        turn = _run_specialist(agent, state["symbol"], "risk_agent")
        turn["rationale"] = (
            f"[pyth_gate:pass staleness={gate['staleness_s']}s "
            f"conf={gate['conf_pct']:.3f}%] {turn['rationale']}"
        )
        return {
            "transcript": [turn],
            "pyth_price": pyth_price,
            "pyth_gate": "pass",
        }

    node.__name__ = "risk_agent_node"
    return node


def _tally_node(state: DebateState) -> dict[str, Any]:
    transcript = state.get("transcript", [])
    votes = {turn["agent"]: turn["vote"] for turn in transcript}
    final_decision = tally(transcript)
    return {"votes": votes, "final_decision": final_decision}


def _jupiter_quote_node(state: DebateState) -> dict[str, Any]:
    """Attach a Jupiter route quote when the committee wants to trade.

    BUY/SELL → call ``quote_spot`` for SOL→USDC at 1 SOL notional. HOLD
    skips the call. Failures attach ``None`` and the runner metric stays
    flat — supervisor never raises here.
    """
    if state.get("final_decision") not in {"BUY", "SELL"}:
        return {"jupiter_quote": None}
    quote = quote_spot(SOL_MINT, USDC_MINT, _DEFAULT_QUOTE_AMOUNT_LAMPORTS)
    return {"jupiter_quote": quote}


def _build_workflow(model_name: str | None = None):
    from .settings import get_settings

    model = _build_model(model_name or get_settings().quorum_model)
    tech_node = _make_specialist_node(build_tech_agent, "tech_agent", model)
    news_node = _make_specialist_node(build_news_agent, "news_agent", model)
    risk_node = _make_risk_node(model)

    graph = StateGraph(DebateState)
    graph.add_node("tech_agent", tech_node)
    graph.add_node("news_agent", news_node)
    graph.add_node("risk_agent", risk_node)
    graph.add_node("tally", _tally_node)
    graph.add_node("jupiter_quote", _jupiter_quote_node)

    graph.add_edge(START, "tech_agent")
    graph.add_edge("tech_agent", "news_agent")
    graph.add_edge("news_agent", "risk_agent")
    graph.add_edge("risk_agent", "tally")
    graph.add_edge("tally", "jupiter_quote")
    graph.add_edge("jupiter_quote", END)

    return graph.compile()


def run_debate(
    symbol: str,
    thread_id: str = "default",
    model_name: str | None = None,
    verbose: bool = False,
) -> DebateResult:
    """Run one debate cycle and return a structured `DebateResult`.

    Args:
        symbol: Trading pair, e.g. "SOL/USDC".
        thread_id: LangGraph thread id for replay/persistence (Milestone 7).
        model_name: Override the LiteLLM `provider/model` id.
        verbose: When ``True``, stream each specialist turn to stderr with
            elapsed wall-clock timing as the debate progresses.
    """
    app = _build_workflow(model_name=model_name)
    init = {"symbol": symbol, "transcript": []}
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}

    if verbose:
        import sys
        import time

        state: dict[str, Any] = {"symbol": symbol, "transcript": [], "votes": {}}
        t0 = time.monotonic()
        for chunk in app.stream(init, config=config, stream_mode="updates"):
            elapsed = time.monotonic() - t0
            node_name = next(iter(chunk))
            update = chunk[node_name]
            if "transcript" in update:
                state["transcript"].extend(update["transcript"])
                for turn in update["transcript"]:
                    print(
                        f"  [{turn['agent']}] {turn['vote']}  ({elapsed:.1f}s)",
                        file=sys.stderr,
                    )
            if "votes" in update:
                state["votes"] = update["votes"]
            if "final_decision" in update:
                state["final_decision"] = update["final_decision"]
    else:
        state = app.invoke(init, config=config)

    transcript = list(state.get("transcript", []))
    votes = dict(state.get("votes", {}))
    final_decision = state.get("final_decision", tally(transcript))
    return DebateResult(
        symbol=symbol,
        transcript=transcript,
        votes=votes,
        final_decision=final_decision,
        pyth_price=state.get("pyth_price"),
        pyth_gate=state.get("pyth_gate"),
        jupiter_quote=state.get("jupiter_quote"),
        dry_run_signature=state.get("dry_run_signature"),
        raw_messages=[],
    )
