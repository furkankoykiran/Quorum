# Security Policy

Quorum is under active development for the Canteen × Colosseum SWARM hackathon. Milestones 2 and beyond will manage real USDC on a Squads V4 multisig on Solana — so responsible disclosure matters to us.

## Supported versions

Only the current `main` branch is supported. There are no tagged releases yet; every fix lands in `main`.

## Reporting a vulnerability

**Do not open a public GitHub issue for security problems.** Instead, email:

- **furkankoykiran@gmail.com**

with the following details:

1. A clear description of the vulnerability.
2. Steps to reproduce, or a proof-of-concept.
3. The affected commit SHA or `main` at the time of discovery.
4. Any known impact — e.g. does it put vault funds at risk, leak secrets, or enable unauthorized trade execution?

You will get an acknowledgement within 72 hours. We will work with you on a fix, credit you in the changelog unless you prefer to stay anonymous, and coordinate disclosure once the fix is merged.

## In-scope issues

- Anything that could move or drain funds from the Squads V4 multisig (Milestone 2+).
- Unauthorized trade execution via the LangGraph orchestrator.
- Prompt-injection paths that allow an MCP tool result to change the voting outcome in an unauthorized way.
- Leakage of secrets (`ANTHROPIC_API_KEY`, `SOLANA_PRIVATE_KEY`, `FREQTRADE_PASSWORD`, etc.) via logs, transcripts, or error messages.
- Supply-chain issues in `pyproject.toml` / `uv.lock` / `package.json` / `package-lock.json`.

## Out of scope

- Vulnerabilities in third-party MCP servers (`freqtrade-mcp`, `OmniWire-MCP`) — report those directly at their own repositories.
- Vulnerabilities that require an already-compromised operator key.
- Rate-limit or DOS attacks against public RPC providers.

## Operational safety rails

- `main` is branch-protected: no direct pushes, no force pushes, no branch deletions.
- Secrets never live in the repository. `.env` is gitignored; `.env.example` is the only template committed.
- Transcripts persisted to `debate_runs/*.json` are gitignored and do not leave the host unless explicitly shared.
- Mainnet deployments (Milestone 6+) are always preceded by a minimum 7-day devnet soak.
