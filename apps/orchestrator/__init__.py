"""Quorum orchestrator: LangGraph supervisor for the trading committee debate."""

from .supervisor import run_debate, DebateResult

__all__ = ["run_debate", "DebateResult"]
