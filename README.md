# Quorum

A multi-agent trading committee that debates every trade, votes, executes on Solana via Squads V4 multisig + Jupiter, and splits realized PnL through an LLM-driven Shapley attributor that pays operators on-chain.

Built for the [Canteen x Colosseum SWARM Hackathon](https://swarm.thecanteenapp.com/) (2026-04-06 to 2026-05-11). Targets RFB 04 (Emergent Agent Economies) and RFB 05 (Multi-Agent Orchestration with dynamic payment splitting).

## Architecture

```
Tech / News / Risk / Flow / Sentiment   <-- LangGraph specialist agents
              |
              v
         Supervisor (debate orchestrator + voter)
              |
              v
   Squads V4 multisig vault (USDC)
              |
              v
        Jupiter swap on Solana
              |
              v
  Shapley attributor (LLM counterfactual)
              |
              v
   On-chain payout ix --> operator wallets
```

N specialist LLM agents debate every trade in plain English, vote, execute on Solana via [Squads V4](https://docs.squads.so/main) + [Jupiter](https://jup.ag/), and split realized PnL through an LLM-driven [Shapley](https://en.wikipedia.org/wiki/Shapley_value) attributor. Good agents earn more, bad agents bleed stake -- emergent meritocracy with provable contribution.

## Prerequisites

| Tool | Version | Required for |
|------|---------|-------------|
| Python | >= 3.10 | Orchestrator |
| [uv](https://docs.astral.sh/uv/) | >= 0.10 | Python package management |
| Node.js | >= 20 | Solana agent |
| [pnpm](https://pnpm.io/) | >= 9 | Node package management |
| [Solana CLI](https://docs.solanalabs.com/cli/install) | >= 3.x | Keypair generation, devnet ops |
| [Freqtrade](https://www.freqtrade.io/) + [freqtrade-mcp](https://github.com/furkankoykiran/freqtrade-mcp) | Latest | Live Tech agent (optional) |
| [OmniWire-MCP](https://github.com/furkankoykiran/OmniWire-MCP) | Latest | Live News agent (optional) |

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/furkankoykiran/Quorum.git
cd Quorum

# 2. Install Python dependencies
uv sync

# 3. Configure environment
cp .env.example .env
# Edit .env -- set DEEPSEEK_API_KEY (default provider); swap QUORUM_MODEL
# to any LiteLLM-supported `provider/model` id for benchmarking
# (anthropic/..., openai/..., gemini/...).

# 4. Run a single debate in mock mode (no external services needed)
uv run python -m apps.orchestrator.cli debate --symbol SOL/USDT --mock

# 5. Run a single debate in live mode (requires MCP servers)
uv run python -m apps.orchestrator.cli debate --symbol SOL/USDT --verbose

# 6. Replay a saved transcript
uv run python -m apps.orchestrator.cli replay debate_runs/<file>.json

# 7. Run continuous 24/7 debate loop (every 5 minutes)
uv run python -m apps.orchestrator.cli run --symbol SOL/USDT --interval 300
```

## Solana Setup (Milestone 2+)

The Solana edge lives in `packages/solana-agent/`. It manages a 3-of-5 Squads V4 multisig on devnet.

```bash
# 1. Install Solana dependencies
cd packages/solana-agent
pnpm install

# 2. Generate operator keypairs (one-time)
mkdir -p ../../keys
for i in 1 2 3 4 5; do
  solana-keygen new --outfile ../../keys/operator-$i.json --no-bip39-passphrase --force
done

# 3. Fund operator-1 on devnet (needed for multisig creation)
solana airdrop 2 $(solana-keygen pubkey ../../keys/operator-1.json) --url devnet

# 4. Create the 3-of-5 multisig
pnpm tsx src/create-multisig.ts --url https://api.devnet.solana.com

# 5. Record the output PDAs in .env
#    SQUADS_MULTISIG_PDA=<multisig PDA from output>
#    SQUADS_VAULT_PDA=<vault PDA from output>
```

**Current devnet multisig:** [`CwmNKs3f4S6Ct8h3ATR2fwyXyNu3hEF8NCF9sePzVkVw`](https://explorer.solana.com/address/CwmNKs3f4S6Ct8h3ATR2fwyXyNu3hEF8NCF9sePzVkVw?cluster=devnet) (3-of-5 threshold, 5 operator members)

### Vault transaction round-trip

```bash
cd packages/solana-agent

# Inspect multisig state + vault balance
pnpm tsx src/check-multisig.ts --multisig CwmNKs3f4S6Ct8h3ATR2fwyXyNu3hEF8NCF9sePzVkVw

# Fund the vault once (operator-1 pays)
solana transfer FLjG8WcMod7386qhXFV4hSnwx1BzZukSupmD99FmtegC 0.5 \
  --from ../../keys/operator-1.json --url devnet --allow-unfunded-recipient \
  --fee-payer ../../keys/operator-1.json

# Run the full lifecycle: create -> propose -> approve x3 -> execute
pnpm tsx src/vault-transaction.ts --multisig CwmNKs3f4S6Ct8h3ATR2fwyXyNu3hEF8NCF9sePzVkVw
```

`vault-transaction.ts` wraps a `SystemProgram.transfer` from the vault PDA in a Squads V4 `vaultTransactionCreate`, opens a proposal, collects 3 of 5 approvals (operator-1 pays fees for all three so operators 2+ don't need devnet SOL), executes, and verifies the recipient balance delta on-chain. The round-trip emits six Solana Explorer links — see PR #14 for a live devnet trace.

### SPL token round-trip

The vault can also hold and transfer SPL tokens through the same Squads V4 multisig lifecycle.

```bash
cd packages/solana-agent

# 1. Create a mock-USDC mint (6 decimals, 1M supply to operator-1)
pnpm tsx src/create-mint.ts
# Prints the mint pubkey — record it for subsequent commands

# 2. Check vault SPL balance for a given mint
pnpm tsx src/check-multisig.ts \
  --multisig CwmNKs3f4S6Ct8h3ATR2fwyXyNu3hEF8NCF9sePzVkVw \
  --mint <mint-pubkey>

# 3. Run the full SPL lifecycle: fund vault -> create -> propose -> approve x3 -> execute
pnpm tsx src/vault-spl-transaction.ts \
  --multisig CwmNKs3f4S6Ct8h3ATR2fwyXyNu3hEF8NCF9sePzVkVw \
  --mint <mint-pubkey>
```

**Current devnet mint:** [`6iZ7Z8w1y2zhzRagvWCcQdqRG6KEBLxrjVrWHdpNBKMT`](https://explorer.solana.com/address/6iZ7Z8w1y2zhzRagvWCcQdqRG6KEBLxrjVrWHdpNBKMT?cluster=devnet) (mock-USDC, 6 decimals, operator-1 has mint authority)

`vault-spl-transaction.ts` creates the vault's associated token account if needed, funds it from operator-1, builds an SPL `createTransferInstruction` wrapped in the Squads `vaultTransactionCreate` → `proposalCreate` → `proposalApprove × 3` → `vaultTransactionExecute` lifecycle, and verifies the recipient ATA balance delta on-chain.

## CLI Reference

### `debate` -- Run a single trading-committee debate

```
uv run python -m apps.orchestrator.cli debate [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--symbol` | `SOL/USDC` | Trading pair to debate |
| `--mock` | off | Use offline dummy tools instead of live MCP servers |
| `--verbose` | off | Stream each specialist turn with wall-clock timing |
| `--no-save` | off | Skip writing JSON transcript to `debate_runs/` |
| `--thread-id` | auto | LangGraph thread ID |

### `replay` -- Replay a saved debate transcript

```
uv run python -m apps.orchestrator.cli replay <path-to-transcript.json>
```

### `run` -- Continuous debate loop with metrics

```
uv run python -m apps.orchestrator.cli run [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--symbol` | `SOL/USDT` | Trading pair to debate |
| `--interval` | `300` | Seconds between debates |
| `--max-runs` | `0` | Stop after N runs (0 = unlimited) |
| `--verbose` | off | Stream each specialist turn |

Metrics are persisted to `data/runner_metrics.json` (success rate, avg latency, p95, parse failures).

## Live MCP Wiring

| Agent | Tool | Source | Status |
|-------|------|--------|--------|
| Tech | `get_ohlcv_live` | [freqtrade-mcp](https://github.com/furkankoykiran/freqtrade-mcp) -- Binance OHLCV + RSI + support/resistance | live |
| News | `get_headlines_live` | [OmniWire-MCP](https://github.com/furkankoykiran/OmniWire-MCP) -- CoinDesk, The Block, Bloomberg, Decrypt | live |
| Risk | `get_risk_caps` | Hardcoded trade envelope (position caps, slippage, kill switch) | mock (Milestone 5) |

Toggle with `QUORUM_USE_MOCK=1` (all dummy) or `QUORUM_TECH_LIVE=1` (live Tech agent). Config is centralised in `apps/orchestrator/settings.py` via [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).

## Configuration

All configuration lives in `.env` (never committed). Copy from `.env.example`:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key for all agents |
| `ANTHROPIC_BASE_URL` | No | Custom API proxy endpoint |
| `QUORUM_MODEL` | No | Model override (default: `claude-sonnet-4-6`) |
| `QUORUM_USE_MOCK` | No | `1` to force all agents to offline dummy tools |
| `QUORUM_TECH_LIVE` | No | `1` to enable live Freqtrade Tech agent |
| `RSS_FEEDS` | No | OmniWire feed config JSON |
| `FREQTRADE_API_URL` | No | Freqtrade REST API endpoint |
| `FREQTRADE_USERNAME` | No | Freqtrade API username |
| `FREQTRADE_PASSWORD` | No | Freqtrade API password |
| `SOLANA_RPC_URL` | No | Solana RPC (default: devnet) |
| `SOLANA_PRIVATE_KEY` | No | Base58 operator keypair (Milestone 2+) |
| `SQUADS_MULTISIG_PDA` | No | Squads V4 multisig address (Milestone 2+) |
| `SQUADS_VAULT_PDA` | No | Squads V4 vault address (Milestone 2+) |
| `HELIUS_API_KEY` | No | Helius API key (Milestone 5+) |

## Deployment

```bash
# Install as a systemd service (runs debates every 5 minutes)
sudo bash deploy/install.sh

# Check status
systemctl status quorum-runner
cat data/runner_metrics.json

# Stop and remove
sudo bash deploy/uninstall.sh
```

## Tests

```bash
# Offline CI suite (no API keys needed, ~2s)
uv run pytest tests/test_offline.py -v

# Full LLM debate scenarios (needs ANTHROPIC_API_KEY)
uv run pytest tests/test_debate_scenarios.py -v

# Live MCP smoke tests (needs running Freqtrade + OmniWire)
uv run pytest tests/test_mcp_clients.py -v -m requires_mcp

# TypeScript typecheck
cd packages/solana-agent && pnpm typecheck
```

## Repo Layout

```
apps/orchestrator/       Python LangGraph supervisor + specialist agents
  agents.py              Tech, News, Risk specialist agent definitions
  graph.py               StateGraph wiring (START -> agents -> tally -> END)
  settings.py            Centralised pydantic-settings configuration
  cli.py                 CLI entrypoint (debate, replay, run)
  runner.py              Continuous debate runner with metrics
  mcp_clients.py         MCP server client wrappers
  tool_registry.py       Live/mock tool selection per agent
  tally.py               Vote parsing and majority tally
  persistence.py         JSON transcript persistence

packages/solana-agent/   TypeScript Solana edge
  src/create-multisig.ts       Squads V4 3-of-5 multisig initialization
  src/create-mint.ts           Mock-USDC SPL mint bootstrap (6 decimals)
  src/check-multisig.ts        Read-only multisig + SPL balance utility
  src/vault-transaction.ts     SOL vault tx lifecycle (create -> propose -> approve x3 -> execute)
  src/vault-spl-transaction.ts SPL token vault tx lifecycle
  src/index.ts                 Package entrypoint

tests/                   pytest suite
  test_offline.py        8 offline CI tests (vote, persistence, tools, replay)
  test_debate.py         Live + mock LLM debate integration tests
  test_debate_scenarios.py  Parametrised multi-symbol mock debates
  test_mcp_clients.py    MCP server smoke tests

deploy/                  systemd service + install/uninstall scripts
configs/                 OmniWire RSS feed config
```

## Roadmap

| Milestone | Days | Status |
|-----------|------|--------|
| 1. LangGraph supervisor + live Tech/News MCP + CLI + continuous runner | 1-3 | done |
| 2. Squads V4 multisig on devnet | 4-7 | in progress |
| 3. Jupiter swap via solana-agent-kit v2 | 8-12 | pending |
| 4. Shapley attributor + on-chain payout ix | 13-17 | pending |
| 5. Flow + Sentiment agents, 7-day devnet paper trade | 18-22 | pending |
| 6. Mainnet cutover (3 operators, $150 USDC vault) | 23-26 | pending |
| 7. Demo dashboard + Arweave transcript pinning | 27-30 | pending |
| 8. Submission video + judge demo | 31-33 | pending |

## License

[MIT](LICENSE)
