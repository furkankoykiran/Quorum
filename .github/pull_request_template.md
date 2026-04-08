## Summary

<!-- 1-3 sentences. What does this PR change and why. -->

## Changes

<!-- Bullet list of the concrete changes. One bullet per logical unit. -->

-
-

## Test plan

<!-- Copy the commands you ran locally. Tick them off as they pass. -->

- [ ] `uvx ruff check .`
- [ ] `uv run pytest tests/test_offline.py -v`
- [ ] `uv run pytest tests/test_debate.py::test_debate_mock_mode -v` (if orchestrator touched)
- [ ] `uv run python -m apps.orchestrator.cli debate --symbol SOL/USDC --mock` (if CLI touched)
- [ ] Other: _______

## Screenshots or transcripts

<!-- Drop CLI output, debate transcript JSON, or demo screenshots here when relevant. -->

## Related issues

<!-- Closes #123, related to #456 -->

## Checklist

- [ ] I read [CONTRIBUTING.md](.github/CONTRIBUTING.md) and followed the commit hygiene rules.
- [ ] Commit subjects are conventional (`feat|fix|docs|chore|refactor|test|ci(<scope>): <summary>`).
- [ ] No AI/LLM attribution anywhere (no `Co-Authored-By: Claude …`, no "Generated with …").
- [ ] No secrets, API keys, or private keys are committed.
- [ ] CI is green or I have a specific reason why it cannot be.
- [ ] I added or updated tests for behaviour changes (or explained why none are needed).
