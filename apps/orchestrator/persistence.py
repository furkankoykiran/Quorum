"""Local JSON transcript persistence for debate runs.

Writes one `DebateResult` per run to `debate_runs/<iso>_<symbol>.json`.
This is the Day-2/3 placeholder for Milestone 7's Arweave pinning — same
JSON shape, different storage backend later.

`debate_runs/` is already excluded from version control by `.gitignore`
so each local run leaves artefacts without polluting commits.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid a circular import at runtime
    from .supervisor import DebateResult


def _safe_symbol(symbol: str) -> str:
    """Make a symbol safe for use as a filename fragment on any OS."""
    return symbol.replace("/", "-").replace(":", "-").strip()


def _timestamp() -> str:
    """Return a UTC ISO timestamp with colons stripped (Windows-friendly)."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return now.isoformat().replace(":", "-")


def save_debate(result: "DebateResult", run_dir: Path | str = "debate_runs") -> Path:
    """Persist one debate result as indented JSON. Returns the written path."""
    directory = Path(run_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{_timestamp()}_{_safe_symbol(result.symbol)}.json"
    payload = result.to_dict()
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def append_debate_log(
    result: "DebateResult", jsonl_path: Path | str = "data/debate_log.jsonl"
) -> Path:
    """Append one JSON line per debate to a flat log file.

    The log is the long-running record consumed by metrics dashboards and
    the weekly Colosseum video script. Per-debate JSON in `debate_runs/`
    is for replay; this jsonl is for time-series scanning.
    """
    path = Path(jsonl_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict()
    payload["ts"] = datetime.now(timezone.utc).isoformat()
    line = json.dumps(payload, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return path
