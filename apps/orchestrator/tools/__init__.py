"""Specialist tools.

Milestone 1 ships fully synchronous, hardcoded mock tools so the supervisor
loop can be exercised without any network access. Milestone 2 swaps these for
real MCP clients (`freqtrade-mcp`, `OmniWire-MCP`).
"""

from .dummy_market import get_ohlcv
from .dummy_news import get_headlines
from .dummy_risk import get_risk_caps

__all__ = ["get_ohlcv", "get_headlines", "get_risk_caps"]
