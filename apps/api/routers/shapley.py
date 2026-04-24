"""Shapley leaderboard + history endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from .. import readers
from ..models import ShapleyHistoryResponse, ShapleyWeights

router = APIRouter(tags=["shapley"])


@router.get("/shapley/leaderboard", response_model=ShapleyWeights)
def shapley_leaderboard() -> ShapleyWeights:
    rows = readers.read_shapley_history(limit=1)
    if not rows:
        return ShapleyWeights(ts=None, weights={})
    latest = rows[-1]
    return ShapleyWeights(ts=latest.get("ts"), weights=latest.get("weights", {}))


@router.get("/shapley/history", response_model=ShapleyHistoryResponse)
def shapley_history(
    k: int = Query(10, ge=1, le=100),
    limit: int = Query(100, ge=1, le=1000),
) -> ShapleyHistoryResponse:
    rows = readers.read_shapley_history(k=k, limit=limit)
    points = [ShapleyWeights(ts=row.get("ts"), weights=row.get("weights", {})) for row in rows]
    return ShapleyHistoryResponse(k=k, points=points)
