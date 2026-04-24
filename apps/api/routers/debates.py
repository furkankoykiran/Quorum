"""Debate listing + detail endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from .. import readers
from ..models import DebateDetail, DebateSummary

router = APIRouter(tags=["debates"])


def _summarise(row: dict[str, Any]) -> DebateSummary:
    shapley = row.get("shapley_weights") or {}
    top_agent: str | None = None
    if isinstance(shapley, dict) and shapley:
        top_agent = max(shapley, key=lambda k: shapley.get(k, 0.0))
    return DebateSummary(
        debate_id=f"{row.get('symbol')}-{row.get('ts')}",
        symbol=row.get("symbol", ""),
        ts=row.get("ts", ""),
        final_decision=row.get("final_decision", ""),
        votes=row.get("votes", {}),
        pyth_gate=row.get("pyth_gate"),
        shapley_top_agent=top_agent,
    )


@router.get("/debates/recent", response_model=list[DebateSummary])
def recent_debates(limit: int = Query(20, ge=1, le=200)) -> list[DebateSummary]:
    rows = readers.read_debate_log(limit=limit)
    return [_summarise(row) for row in rows]


@router.get("/debates/{debate_id}", response_model=DebateDetail)
def debate_detail(debate_id: str) -> DebateDetail:
    row = readers.read_debate_by_id(debate_id)
    if row is None:
        raise HTTPException(status_code=404, detail="debate not found")
    summary = _summarise(row)
    return DebateDetail(
        **summary.model_dump(),
        transcript=row.get("transcript", []),
        pyth_price=row.get("pyth_price"),
        jupiter_quote=row.get("jupiter_quote"),
        dry_run_signature=row.get("dry_run_signature"),
        shapley_weights=row.get("shapley_weights"),
        shapley_rationale=row.get("shapley_rationale"),
        shapley_rolling_weights=row.get("shapley_rolling_weights"),
    )
