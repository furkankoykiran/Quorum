"""Data-directory resolver for the Observatory API.

The runner writes ``debate_log.jsonl``, ``shapley_history.jsonl`` and
``runner_metrics.json`` into a data directory that defaults to ``<repo>/data``.
Tests monkeypatch :data:`DATA_DIR` to point at ``tmp_path``; production uses
the default or the ``QUORUM_DATA_DIR`` environment variable.
"""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR: Path = Path(os.environ.get("QUORUM_DATA_DIR") or (_REPO_ROOT / "data"))


def debate_log_path() -> Path:
    return DATA_DIR / "debate_log.jsonl"


def shapley_history_path() -> Path:
    return DATA_DIR / "shapley_history.jsonl"


def runner_metrics_path() -> Path:
    return DATA_DIR / "runner_metrics.json"
