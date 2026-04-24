"""Live debate feed over WebSocket.

Polls ``debate_log.jsonl`` every 2s, pushes a ``DebateSummary`` payload when the
last line's timestamp changes, and emits a ``{"type":"ping"}`` heartbeat every
10s to keep proxies awake. No server-side fan-out; each client has its own
poll loop.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .. import paths, readers

router = APIRouter(tags=["live"])

POLL_INTERVAL_S = 2.0
HEARTBEAT_INTERVAL_S = 10.0


def _summary_payload(row: dict[str, Any]) -> dict[str, Any]:
    shapley = row.get("shapley_weights") or {}
    top_agent = None
    if isinstance(shapley, dict) and shapley:
        top_agent = max(shapley, key=lambda k: shapley.get(k, 0.0))
    return {
        "type": "debate",
        "debate_id": f"{row.get('symbol')}-{row.get('ts')}",
        "symbol": row.get("symbol"),
        "ts": row.get("ts"),
        "final_decision": row.get("final_decision"),
        "votes": row.get("votes", {}),
        "pyth_gate": row.get("pyth_gate"),
        "shapley_top_agent": top_agent,
    }


def _read_last_row() -> dict[str, Any] | None:
    line = readers.tail_line(paths.debate_log_path())
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


@router.websocket("/live/debates")
async def live_debates(ws: WebSocket) -> None:
    await ws.accept()
    last_ts: str | None = None
    last_ping = time.monotonic()
    try:
        while True:
            row = _read_last_row()
            if row is not None:
                row_ts = row.get("ts")
                if row_ts and row_ts != last_ts:
                    await ws.send_json(_summary_payload(row))
                    last_ts = row_ts
            now = time.monotonic()
            if now - last_ping >= HEARTBEAT_INTERVAL_S:
                await ws.send_json({"type": "ping", "mono": now})
                last_ping = now
            await asyncio.sleep(POLL_INTERVAL_S)
    except WebSocketDisconnect:
        return
