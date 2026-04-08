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

- [apps/orchestrator/](apps/orchestrator/) — Python LangGraph supervisor + specialist agents (Milestone 1+)
- [packages/solana-agent/](packages/solana-agent/) — TypeScript Solana edge: `solana-agent-kit` v2 + `@sqds/multisig` (Milestone 2+)
- [tests/](tests/) — pytest suite
- [docs/](docs/) — architecture notes

## Quick start (Milestone 1)

```bash
# 1. install Python deps with uv
uv sync

# 2. configure
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY=sk-ant-...

# 3. run a debate from the CLI
uv run python -m apps.orchestrator.cli debate --symbol SOL/USDC

# 4. run the acceptance test
uv run pytest tests/test_debate.py -v
```

## Status

| Milestone | Days | Status |
|---|---|---|
| 1. LangGraph supervisor + 3 dummy specialists + acceptance test | 1–3 | in progress |
| 2. Squads V4 multisig on devnet | 4–7 | pending |
| 3. Jupiter swap via solana-agent-kit v2 | 8–12 | pending |
| 4. Shapley attributor + on-chain payout ix | 13–17 | pending |
| 5. Flow + Sentiment agents, 7-day devnet paper trade | 18–22 | pending |
| 6. Mainnet cutover (3 operators, $150 USDC vault) | 23–26 | pending |
| 7. Demo dashboard + Arweave transcript pinning | 27–30 | pending |
| 8. Submission video + judge demo | 31–33 | pending |

## License

[MIT](LICENSE)
