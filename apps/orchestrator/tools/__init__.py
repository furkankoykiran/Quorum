"""Specialist tools.

Both mock and live variants live here and are selected at agent-build time
by `apps.orchestrator.tool_registry` based on the `QUORUM_USE_MOCK` env var.

- `dummy_*` tools are hardcoded payloads, safe for offline CI and the
  `--mock` CLI flag.
- `get_headlines_live` calls `omniwire-mcp` over stdio.
- `get_ohlcv_live` calls `freqtrade-mcp` over stdio (gated on a live
  Freqtrade REST backend; not wired by default on Day 2).
"""

from .dummy_market import get_ohlcv
from .dummy_news import get_headlines
from .dummy_risk import get_risk_caps
from .freqtrade import get_ohlcv_live
from .omniwire import get_headlines_live

__all__ = [
    "get_ohlcv",
    "get_headlines",
    "get_risk_caps",
    "get_headlines_live",
    "get_ohlcv_live",
]
