# Contributing to Quorum

Thanks for wanting to help. Quorum is a multi-agent trading committee built for the Canteen × Colosseum SWARM hackathon — we move fast, keep history clean, and expect every change to be reviewable.

## Before you start

- Read the [README](../README.md) for an architectural overview.
- Check open [issues](https://github.com/furkankoykiran/Quorum/issues) and [pull requests](https://github.com/furkankoykiran/Quorum/pulls) — someone may already be working on the same thing.
- For non-trivial changes, open an issue first to agree on the approach before you write code.

## Local setup

```bash
git clone https://github.com/furkankoykiran/Quorum.git
cd Quorum
cp .env.example .env            # fill in ANTHROPIC_API_KEY at minimum
uv sync                         # installs the orchestrator and dev deps
uv run pytest tests/test_offline.py -v   # fast offline tests
```

To run the full live stack you also need the sibling MCP servers cloned next to Quorum:

```bash
# OmniWire-MCP (real headlines for the News agent)
cd .. && git clone https://github.com/furkankoykiran/OmniWire-MCP.git
cd OmniWire-MCP && npm install && npm run build

# freqtrade-mcp (real OHLCV for the Tech agent — requires a running Freqtrade REST API)
cd .. && git clone https://github.com/furkankoykiran/freqtrade-mcp.git
cd freqtrade-mcp && npm install && npm run build
```

Then back in Quorum:

```bash
export RSS_FEEDS="$(cat configs/omniwire_feeds.json)"
uv run python -m apps.orchestrator.cli debate --symbol SOL/USDC
```

## Branching and commit hygiene

- **Never push directly to `main`.** Open a pull request against `main`; it will be squash-merged after review.
- Branch names: `feat/<slug>`, `fix/<slug>`, `chore/<slug>`, `docs/<slug>`, `ci/<slug>`, `test/<slug>`.
- **One logical change per commit.** When touching multiple files for independent reasons, use separate commits.
- Conventional commit subjects: `<type>(<scope>): <summary>` — types are `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `ci`.
  - Examples:
    - `feat(orchestrator): add freqtrade mcp stdio client`
    - `fix(cli): stop swallowing empty transcript errors`
    - `test(orchestrator): cover mock-mode debate path`
- Explain the **why** in the commit message body when it is not obvious from the diff.
- **No AI/LLM attribution** anywhere — commits, PR descriptions, issue comments. No `Co-Authored-By: Claude …`, no "Generated with …", no "Assisted by AI".

## Pull requests

- Title: `<type>(<scope>): <summary>` or a short descriptive phrase under 70 characters.
- Description: fill in the PR template — what changed, why, how to test, what is intentionally out of scope.
- CI must be green before merge — run `uvx ruff check .` and `uv run pytest tests/test_offline.py` locally first.
- If your change touches orchestrator behaviour, include or update a test under `tests/`.
- PRs are squash-merged. Keep the squash title and body meaningful — reviewers will copy them verbatim.

## Running tests

```bash
# Offline fast lane (no LLM, no MCP subprocess) — this is what CI runs.
uv run pytest tests/test_offline.py -v

# Full mock-mode debate (needs ANTHROPIC_API_KEY).
uv run pytest tests/test_debate.py::test_debate_mock_mode -v

# Live gateway regression (needs ANTHROPIC_API_KEY).
uv run pytest tests/test_debate.py::test_debate_runs_end_to_end -v

# Real MCP subprocess spawn (needs RSS_FEEDS + cloned OmniWire-MCP/freqtrade-mcp).
export RSS_FEEDS="$(cat configs/omniwire_feeds.json)"
uv run pytest tests/test_mcp_clients.py -v -m requires_mcp
```

Tests are gated with pytest markers:

- `requires_llm` — needs `ANTHROPIC_API_KEY`, skipped otherwise.
- `requires_mcp` — spawns a real MCP subprocess, skipped without `-m requires_mcp`.

## Code style

- Python is formatted with `ruff` (config in `pyproject.toml`, line length 100).
- Run `uvx ruff check . --fix` before pushing.
- Type annotations are required for new public functions; prefer `from __future__ import annotations` at the top of modules.
- No emojis in source, tests, docs, PRs, or commits unless you are specifically asked for one.

## Reporting bugs and requesting features

- Use the issue templates under `.github/ISSUE_TEMPLATE/`.
- Bug reports must include a reproduction — ideally a failing test or the exact CLI invocation and error output.
- Feature requests should motivate the change from a user perspective first, implementation details second.

## Security

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities privately. **Do not open public issues for security problems.**

## Code of conduct

By participating in this project you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).
