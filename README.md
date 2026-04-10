# Quorum

A multi-agent trading committee with Shapley-attributed on-chain payouts.

Built for the [Canteen × Colosseum SWARM Hackathon](https://swarm.thecanteenapp.com/) (2026-04-06 → 2026-05-11). Targets RFB 04 (Emergent Agent Economies) and RFB 05 (Multi-Agent Orchestration with dynamic payment splitting).

## What it does

N specialist LLM agents (Tech, News, Risk — and later Flow + Sentiment) **debate** every trade in plain English, vote, execute on Solana via [Squads V4](https://docs.squads.so/main) + [Jupiter](https://jup.ag/), and split realized PnL through an LLM-driven [Shapley](https://en.wikipedia.org/wiki/Shapley_value) attributor that pays operators on-chain. Good agents earn more, bad agents bleed stake — emergent meritocracy with provable contribution.

## Architecture

```
Tech / News / Risk / Flow / Sentiment   ← LangGraph specialist agents
              │
              ▼
         Supervisor (debate orchestrator + voter)
              │
              ▼
   Squads V4 multisig vault (USDC)
              │
              ▼
        Jupiter swap on Solana
              │
              ▼
  Shapley attributor (LLM counterfactual)
              │
              ▼
   On-chain payout ix → operator wallets
```

## Repo layout

- [apps/orchestrator/](apps/orchestrator/) — Python LangGraph supervisor + specialist agents
- [packages/solana-agent/](packages/solana-agent/) — TypeScript Solana edge: `solana-agent-kit` v2 + `@sqds/multisig` (Milestone 2+)
- [tests/](tests/) — pytest suite (8 offline CI tests + LLM integration + MCP smoke tests)
- [deploy/](deploy/) — systemd service + install/uninstall scripts
- [configs/](configs/) — OmniWire RSS feed config (CoinDesk, The Block, Bloomberg, Decrypt)

## Quick start

```bash
# Install Python deps
uv sync

# Configure
cp .env.example .env
# edit .env — set ANTHROPIC_API_KEY (required), rest has sane defaults

# Run a single debate (mock mode — no MCP servers needed)
uv run python -m apps.orchestrator.cli debate --symbol SOL/USDT --mock

# Run a single debate (live — real Binance candles + crypto news)
uv run python -m apps.orchestrator.cli debate --symbol SOL/USDT --verbose

# Replay a saved transcript
uv run python -m apps.orchestrator.cli replay debate_runs/<file>.json

# Run continuous 24/7 debate loop (every 5 minutes, with metrics)
uv run python -m apps.orchestrator.cli run --symbol SOL/USDT --interval 300
```

## Live MCP wiring

| Agent | Tool | Source | Status |
|---|---|---|---|
| Tech | `get_ohlcv_live` | [freqtrade-mcp](https://github.com/furkankoykiran/freqtrade-mcp) → Binance OHLCV + RSI + support/resistance | live |
| News | `get_headlines_live` | [OmniWire-MCP](https://github.com/furkankoykiran/OmniWire-MCP) → CoinDesk, The Block, Bloomberg, Decrypt | live |
| Risk | `get_risk_caps` | Hardcoded trade envelope (position caps, slippage, kill switch) | mock (Milestone 5) |

Toggle with `QUORUM_USE_MOCK=1` (all dummy) or `QUORUM_TECH_LIVE=1` (live Tech agent). Config is centralised in `apps/orchestrator/settings.py` via [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).

## Deployment

```bash
# Install as a systemd service (runs debates every 5 minutes)
sudo bash deploy/install.sh

# Check status
systemctl status quorum-runner
cat data/runner_metrics.json

# Stop
sudo bash deploy/uninstall.sh
```

## Tests

```bash
# Offline CI suite (no API keys needed, ~2s)
uv run pytest tests/test_offline.py -v

# Live MCP smoke tests (needs running Freqtrade + OmniWire)
uv run pytest tests/test_mcp_clients.py -v -m requires_mcp

# Full LLM debate scenarios (needs ANTHROPIC_API_KEY)
uv run pytest tests/test_debate_scenarios.py -v
```

## Status

| Milestone | Days | Status |
|---|---|---|
| 1. LangGraph supervisor + live Tech/News MCP + CLI + continuous runner | 1–3 | done |
| 2. Squads V4 multisig on devnet | 4–7 | in progress |
| 3. Jupiter swap via solana-agent-kit v2 | 8–12 | pending |
| 4. Shapley attributor + on-chain payout ix | 13–17 | pending |
| 5. Flow + Sentiment agents, 7-day devnet paper trade | 18–22 | pending |
| 6. Mainnet cutover (3 operators, $150 USDC vault) | 23–26 | pending |
| 7. Demo dashboard + Arweave transcript pinning | 27–30 | pending |
| 8. Submission video + judge demo | 31–33 | pending |

## License

[MIT](LICENSE)
