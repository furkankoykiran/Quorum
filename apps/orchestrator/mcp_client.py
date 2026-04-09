"""Synchronous stdio MCP client wrapper for the Quorum orchestrator.

This module exposes a tiny `call_tool(server, tool, arguments)` helper that:

1. Looks up `server` in a small registry (`omniwire`, `freqtrade`).
2. Spawns the MCP server over stdio using the official `mcp` Python SDK.
3. Calls one tool and returns the flattened text content as a string.
4. Tears the subprocess down when the call returns.

One subprocess per call is deliberately simple for Milestone 1 — latency is
tolerable for a debate that fires the tool once per specialist per run, and
the teardown path prevents orphan Node processes if the orchestrator crashes
mid-debate. Upgrade to a per-process singleton session only if the Day 2
Loom recording proves spawn cost is eating the demo tempo.

Environment variables for each server are read from the current process
environment at call time, so `.env` loaded by the CLI propagates cleanly
without needing to re-parse here.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .settings import get_settings


def _build_omniwire_params() -> StdioServerParameters:
    """Build stdio params for the OmniWire MCP server."""
    cfg = get_settings()
    env = _inherit_env()
    feeds = cfg.rss_feeds_resolved
    if feeds:
        env["RSS_FEEDS"] = feeds
    if cfg.log_level:
        env["LOG_LEVEL"] = cfg.log_level
    return StdioServerParameters(command="node", args=[cfg.omniwire_mcp_entry], env=env)


def _build_freqtrade_params() -> StdioServerParameters:
    """Build stdio params for the freqtrade MCP server."""
    cfg = get_settings()
    env = _inherit_env()
    if cfg.freqtrade_api_url:
        env["FREQTRADE_API_URL"] = cfg.freqtrade_api_url
    if cfg.freqtrade_username:
        env["FREQTRADE_USERNAME"] = cfg.freqtrade_username
    if cfg.freqtrade_password:
        env["FREQTRADE_PASSWORD"] = cfg.freqtrade_password
    return StdioServerParameters(command="node", args=[cfg.freqtrade_mcp_entry], env=env)


def _inherit_env() -> dict[str, str]:
    """Forward PATH/HOME/NODE_PATH so node can resolve binaries."""
    env: dict[str, str] = {}
    for key in ("PATH", "HOME", "NODE_PATH"):
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    return env


_PARAM_BUILDERS: dict[str, Any] = {
    "omniwire": _build_omniwire_params,
    "freqtrade": _build_freqtrade_params,
}


def _flatten_content(content: Any) -> str:
    """Collapse an MCP tool result content list into a single string.

    The SDK returns a list of content blocks (`TextContent`, `ImageContent`,
    etc.). Quorum only consumes text, so we concatenate every `.text`
    attribute we find and ignore the rest.
    """
    if content is None:
        return ""
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts)


async def _call_tool_async(server: str, tool: str, arguments: dict[str, Any]) -> str:
    builder = _PARAM_BUILDERS.get(server)
    if builder is None:
        raise KeyError(f"Unknown MCP server: {server!r}. Known: {sorted(_PARAM_BUILDERS)}")
    params = builder()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments=arguments)
            if getattr(result, "isError", False):
                raise RuntimeError(
                    f"MCP tool {server}.{tool} returned error: {_flatten_content(result.content)!r}"
                )
            return _flatten_content(result.content)


def call_tool(server: str, tool: str, arguments: dict[str, Any] | None = None) -> str:
    """Call one tool on one MCP server and return the text content.

    Args:
        server: Registry key, one of "omniwire" or "freqtrade".
        tool: MCP tool name as advertised by the server.
        arguments: JSON-serialisable argument dict (optional).

    Returns:
        The concatenated text of the tool's content blocks.

    Raises:
        KeyError: if `server` is not registered.
        RuntimeError: if the MCP server reports an error result.
    """
    coro = _call_tool_async(server, tool, arguments or {})
    try:
        asyncio.get_running_loop()
        # Already inside an event loop (e.g. pytest-asyncio). Spin up a
        # background thread so we don't nest asyncio.run() calls.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        # No running loop — safe to use asyncio.run() directly.
        return asyncio.run(coro)
