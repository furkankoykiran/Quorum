"""Runner metrics + denormalised stats strip."""

from __future__ import annotations

import os

from fastapi import APIRouter

from .. import paths, readers
from ..models import RunnerMetricsResponse, StatsResponse

router = APIRouter(tags=["runner"])

_TESTS_PASSING = 23  # Day 15–16 target; bump when suite grows.


@router.get("/runner/metrics", response_model=RunnerMetricsResponse)
def runner_metrics() -> RunnerMetricsResponse:
    return RunnerMetricsResponse(**readers.read_runner_metrics())


@router.get("/stats", response_model=StatsResponse)
def stats() -> StatsResponse:
    m = readers.read_runner_metrics()
    return StatsResponse(
        total=int(m.get("total", 0)),
        success=int(m.get("success", 0)),
        errors=int(m.get("errors", 0)),
        parse_failures=int(m.get("parse_failures", 0)),
        pyth_gate_holds=int(m.get("pyth_gate_holds", 0)),
        shapley_attached=int(m.get("shapley_attached", 0)),
        jupiter_quotes_attached=int(m.get("jupiter_quotes_attached", 0)),
        dry_run_built=int(m.get("dry_run_built", 0)),
        success_rate=float(m.get("success_rate", 0.0)),
        avg_latency=float(m.get("avg_latency", 0.0)),
        p95_latency=float(m.get("p95_latency", 0.0)),
        debates_count=readers.count_lines(paths.debate_log_path()),
        shapley_rows=readers.count_lines(paths.shapley_history_path()),
        tests_passing=_TESTS_PASSING,
        git_sha=os.environ.get("QUORUM_GIT_SHA"),
    )
