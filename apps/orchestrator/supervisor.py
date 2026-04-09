"""Deterministic StateGraph wiring for the Quorum trading committee.

The debate runs as an explicit `StateGraph` with hard-coded sequential edges:

    START → tech_node → news_node → risk_node → tally_node → END

Each specialist node spins up a short-lived `create_react_agent`, feeds it
the symbol, extracts the `FINAL: {...}` JSON tail, and appends one
`AgentTurn` to `state["transcript"]`. The tally node runs the equal-weight
vote rule. Milestone 4 swaps the tally node for an LLM-driven Shapley
counterfactual that yields weighted scores.

This module deliberately does NOT use `langgraph-supervisor`'s LLM-routed
handoff pattern — during Milestone 1 we observed that non-Anthropic gateway
routing (e.g. Z.ai proxy) did not reliably follow a "consult all three"
instruction, so the graph has to force the ordering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langgraph.graph import END, START, StateGraph

from .agents import build_news_agent, build_risk_agent, build_tech_agent
from .state import AgentTurn, DebateState, Vote
from .vote import parse_final, tally


@dataclass
class DebateResult:
    """Outcome of a single trading-committee debate."""

    symbol: str
    transcript: list[AgentTurn]
    votes: dict[str, Vote]
    final_decision: Vote
    raw_messages: list[BaseMessage] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "transcript": list(self.transcript),
            "votes": dict(self.votes),
            "final_decision": self.final_decision,
        }


def _build_model(model_name: str) -> ChatAnthropic:
    """Build a ChatAnthropic client, honouring optional ANTHROPIC_BASE_URL.

    If `ANTHROPIC_BASE_URL` is set (e.g. a proxy or gateway), we wire it
    through the `anthropic_api_url` kwarg. Otherwise langchain-anthropic
    falls back to the public Anthropic endpoint.
    """
    from .settings import get_settings

    cfg = get_settings()
    kwargs: dict[str, Any] = {
        "model": model_name,
        "temperature": 0.0,
        "anthropic_api_key": cfg.anthropic_api_key,
    }
    if cfg.anthropic_base_url.strip():
        kwargs["anthropic_api_url"] = cfg.anthropic_base_url
    return ChatAnthropic(**kwargs)


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


def _tally_node(state: DebateState) -> dict[str, Any]:
    transcript = state.get("transcript", [])
    votes = {turn["agent"]: turn["vote"] for turn in transcript}
    final_decision = tally(transcript)
    return {"votes": votes, "final_decision": final_decision}


def _build_workflow(model_name: str | None = None):
    from .settings import get_settings

    model = _build_model(model_name or get_settings().quorum_model)
    tech_node = _make_specialist_node(build_tech_agent, "tech_agent", model)
    news_node = _make_specialist_node(build_news_agent, "news_agent", model)
    risk_node = _make_specialist_node(build_risk_agent, "risk_agent", model)

    graph = StateGraph(DebateState)
    graph.add_node("tech_agent", tech_node)
    graph.add_node("news_agent", news_node)
    graph.add_node("risk_agent", risk_node)
    graph.add_node("tally", _tally_node)

    graph.add_edge(START, "tech_agent")
    graph.add_edge("tech_agent", "news_agent")
    graph.add_edge("news_agent", "risk_agent")
    graph.add_edge("risk_agent", "tally")
    graph.add_edge("tally", END)

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
        model_name: Override the Anthropic model id.
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
        raw_messages=[],
    )
