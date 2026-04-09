"""Centralised configuration via pydantic-settings.

Replaces scattered ``os.getenv()`` calls with a single validated
``Settings`` instance. Reads from ``.env`` automatically — no need to
call ``load_dotenv()`` before importing.

Usage::

    from apps.orchestrator.settings import settings

    model = settings.quorum_model
    if settings.quorum_tech_live:
        ...
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Quorum orchestrator configuration.

    Every field maps 1-to-1 to an environment variable with the same
    uppercased name (e.g. ``quorum_model`` ↔ ``QUORUM_MODEL``).
    """

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    # --- Milestone 1: orchestrator ---
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key for the LLM agents.",
    )
    anthropic_base_url: str = Field(
        default="",
        description="Custom Anthropic API endpoint (proxy/gateway). Blank = default.",
    )
    quorum_model: str = Field(
        default="claude-sonnet-4-6",
        description="LLM model id for every specialist agent.",
    )
    quorum_use_mock: bool = Field(
        default=False,
        description="Force offline dummy tools for every specialist.",
    )
    quorum_tech_live: bool = Field(
        default=False,
        description="Enable live freqtrade-mcp for the Tech agent.",
    )

    # --- MCP servers ---
    rss_feeds: str = Field(
        default="",
        description="OmniWire feed config JSON. Auto-loaded from configs/ when blank.",
    )
    omniwire_mcp_entry: str = Field(
        default="/root/OmniWire-MCP/dist/index.js",
        description="Path to the OmniWire MCP server entrypoint.",
    )
    freqtrade_mcp_entry: str = Field(
        default="/root/freqtrade-mcp/build/index.js",
        description="Path to the freqtrade-mcp server entrypoint.",
    )

    # --- Freqtrade backend ---
    freqtrade_api_url: str = Field(
        default="http://127.0.0.1:8080",
        description="Freqtrade REST API base URL.",
    )
    freqtrade_username: str = Field(
        default="Freqtrader",
        description="Freqtrade REST API username.",
    )
    freqtrade_password: str = Field(
        default="",
        description="Freqtrade REST API password.",
    )

    # --- Milestone 2+: Solana edge ---
    solana_rpc_url: str = Field(
        default="https://api.devnet.solana.com",
        description="Solana RPC endpoint.",
    )
    solana_private_key: str = Field(
        default="",
        description="Base58 Solana keypair secret (devnet only).",
    )
    helius_api_key: str = Field(
        default="",
        description="Helius API key for on-chain enrichment (Milestone 5).",
    )

    # --- Logging ---
    log_level: Optional[str] = Field(
        default=None,
        description="Log level forwarded to MCP server subprocesses.",
    )

    @model_validator(mode="after")
    def _resolve_mcp_entries(self) -> "Settings":
        """Treat empty MCP entry paths as unset so defaults apply."""
        if not self.omniwire_mcp_entry.strip():
            self.omniwire_mcp_entry = "/root/OmniWire-MCP/dist/index.js"
        if not self.freqtrade_mcp_entry.strip():
            self.freqtrade_mcp_entry = "/root/freqtrade-mcp/build/index.js"
        return self

    @property
    def rss_feeds_resolved(self) -> str:
        """Return RSS_FEEDS value, auto-loading crypto config when blank."""
        if self.rss_feeds.strip():
            return self.rss_feeds
        config = _PROJECT_ROOT / "configs" / "omniwire_feeds.json"
        if config.exists():
            return config.read_text(encoding="utf-8")
        return ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()
