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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@dataclass(frozen=True)
class _ServerSpec:
    """Static definition of how to launch one MCP server over stdio."""

    command: str
    args: list[str]
    env_keys: tuple[str, ...] = field(default_factory=tuple)


# Resolve the built MCP server entrypoints from env vars so paths are
# configurable per machine. Defaults target the sibling clones the Day 2
# plan assumes live at /root/freqtrade-mcp and /root/OmniWire-MCP.
_FREQTRADE_MCP_ENTRY = (
    os.getenv("FREQTRADE_MCP_ENTRY", "").strip() or "/root/freqtrade-mcp/build/index.js"
)
_OMNIWIRE_MCP_ENTRY = (
    os.getenv("OMNIWIRE_MCP_ENTRY", "").strip() or "/root/OmniWire-MCP/dist/index.js"
)

_SERVERS: dict[str, _ServerSpec] = {
    # OmniWire-MCP runs from the sibling clone at OMNIWIRE_MCP_ENTRY. Its
    # npm publish name is @furkankoykiran/omniwire-mcp, not `omniwire-mcp`,
    # so we avoid `npx` ambiguity and point Node directly at the built
    # dist/index.js. `RSS_FEEDS` is required by the server; LOG_LEVEL is
    # optional and forwarded when the user sets one.
    "omniwire": _ServerSpec(
        command="node",
        args=[_OMNIWIRE_MCP_ENTRY],
        env_keys=("RSS_FEEDS", "LOG_LEVEL"),
    ),
    # freqtrade-mcp is consumed from the sibling clone at FREQTRADE_MCP_ENTRY.
    # Every tool call requires a live Freqtrade REST API, so the Day 2 tech
    # agent stays on dummy_market until those env vars are populated.
    "freqtrade": _ServerSpec(
        command="node",
        args=[_FREQTRADE_MCP_ENTRY],
        env_keys=("FREQTRADE_API_URL", "FREQTRADE_USERNAME", "FREQTRADE_PASSWORD"),
    ),
}


def _build_params(spec: _ServerSpec) -> StdioServerParameters:
    """Assemble StdioServerParameters, forwarding only the env keys we allow.

    We pass an explicit env dict (not `None`) so the subprocess inherits a
    predictable environment. PATH/HOME are forwarded so `npx` and `node` can
    resolve binaries and caches on any machine.
    """
    env: dict[str, str] = {}
    for key in ("PATH", "HOME", "NODE_PATH"):
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    for key in spec.env_keys:
        value = os.environ.get(key, "").strip()
        if value:
            env[key] = value
    # Auto-load the committed crypto feed config for OmniWire when
    # RSS_FEEDS is absent or empty — avoids getting generic tech news.
    if "RSS_FEEDS" in spec.env_keys and "RSS_FEEDS" not in env:
        _config = Path(__file__).resolve().parents[2] / "configs" / "omniwire_feeds.json"
        if _config.exists():
            env["RSS_FEEDS"] = _config.read_text(encoding="utf-8")
    return StdioServerParameters(command=spec.command, args=list(spec.args), env=env)


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
    spec = _SERVERS.get(server)
    if spec is None:
        raise KeyError(f"Unknown MCP server: {server!r}. Known: {sorted(_SERVERS)}")
    params = _build_params(spec)
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
