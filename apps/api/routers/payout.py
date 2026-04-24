"""Payout ledger — placeholder until the graph hook lands Day 22."""

from __future__ import annotations

from fastapi import APIRouter

from ..models import PayoutLatestResponse

router = APIRouter(tags=["payout"])


@router.get("/payout/latest", response_model=PayoutLatestResponse)
def payout_latest() -> PayoutLatestResponse:
    return PayoutLatestResponse(
        payout=None,
        message="payout node lands Day 22",
    )
