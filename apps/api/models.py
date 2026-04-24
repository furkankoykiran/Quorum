"""Pydantic response models for the Observatory API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow")


class TranscriptTurn(_Base):
    agent: str
    vote: str
    rationale: str


class PythBlock(_Base):
    price: float
    conf: float
    conf_pct: float | None = None
    staleness_s: int | float | None = None
    feed: str | None = None


class DebateSummary(_Base):
    debate_id: str
    symbol: str
    ts: str
    final_decision: str
    votes: dict[str, str]
    pyth_gate: str | None = None
    shapley_top_agent: str | None = None


class DebateDetail(DebateSummary):
    transcript: list[TranscriptTurn]
    pyth_price: PythBlock | None = None
    jupiter_quote: dict[str, Any] | None = None
    dry_run_signature: str | None = None
    shapley_weights: dict[str, float] | None = None
    shapley_rationale: str | None = None
    shapley_rolling_weights: dict[str, float] | None = None


class ShapleyWeights(_Base):
    ts: str | None = None
    weights: dict[str, float]


class ShapleyHistoryResponse(_Base):
    k: int
    points: list[ShapleyWeights]


class RunnerMetricsResponse(_Base):
    total: int
    success: int
    errors: int
    rate_limit_errors: int
    parse_failures: int
    retries: int
    pyth_gate_holds: int
    jupiter_quotes_attached: int
    dry_run_built: int
    shapley_attached: int
    success_rate: float
    avg_latency: float
    p95_latency: float
    recent_errors: list[dict[str, Any]] = []


class StatsResponse(_Base):
    total: int
    success: int
    errors: int
    parse_failures: int
    pyth_gate_holds: int
    shapley_attached: int
    jupiter_quotes_attached: int
    dry_run_built: int
    success_rate: float
    avg_latency: float
    p95_latency: float
    debates_count: int
    shapley_rows: int
    tests_passing: int
    git_sha: str | None = None


class PayoutLatestResponse(_Base):
    payout: dict[str, Any] | None = None
    message: str
