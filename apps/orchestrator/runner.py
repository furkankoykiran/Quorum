"""Continuous debate runner — runs debates on a loop and tracks metrics.

Designed to run 24/7 in the background so we can find bugs, measure
latency, and observe agent behaviour over time.

Usage:
    # Run every 5 minutes, default symbol:
    uv run python -m apps.orchestrator.cli run --interval 300

    # Run every 2 minutes on BTC/USDT:
    uv run python -m apps.orchestrator.cli run --interval 120 --symbol BTC/USDT
"""

from __future__ import annotations

import json
import signal
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .persistence import append_debate_log, save_debate
from .supervisor import DebateResult, run_debate

# Retry configuration for transient (rate-limit) failures
_MAX_RETRIES = 3
_INITIAL_BACKOFF_S = 30  # 30s → 90s → 270s (×3 geometric)


def _is_pyth_gate_hold(result: DebateResult) -> bool:
    if (result.pyth_gate or "").startswith("hold_"):
        return True
    return any(
        t["agent"] == "risk_agent" and t["rationale"].startswith("[pyth_gate:hold_")
        for t in result.transcript
    )


def _is_rate_limit(exc: BaseException) -> bool:
    """Return True if *exc* is a rate-limit error (possibly wrapped in ExceptionGroup).

    LangGraph's internal asyncio.TaskGroup wraps 429 RateLimitErrors in an
    ExceptionGroup on Python ≥3.11. We unwrap one level and check the message.
    """
    msg = str(exc).lower()
    if "rate limit" in msg or "429" in msg or "rate_limit" in msg:
        return True
    # ExceptionGroup is only available on Python ≥3.11
    import builtins

    eg_type = getattr(builtins, "ExceptionGroup", None)
    if eg_type is not None and isinstance(exc, eg_type):
        return any(_is_rate_limit(sub) for sub in exc.exceptions)  # type: ignore[union-attr]
    return False


def _classify_error(exc: Exception) -> str:
    """Return a short category tag for metrics."""
    if _is_rate_limit(exc):
        return "rate_limit"
    return "other"


@dataclass
class RunnerMetrics:
    """Tracks success/failure rates and latencies across debate runs."""

    total: int = 0
    success: int = 0
    errors: int = 0
    rate_limit_errors: int = 0
    parse_failures: int = 0
    retries: int = 0
    pyth_gate_holds: int = 0
    jupiter_quotes_attached: int = 0
    dry_run_built: int = 0
    shapley_attached: int = 0
    latencies: list[float] = field(default_factory=list)
    error_log: list[dict] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return (self.success / self.total * 100) if self.total else 0.0

    @property
    def avg_latency(self) -> float:
        return (sum(self.latencies) / len(self.latencies)) if self.latencies else 0.0

    @property
    def p95_latency(self) -> float:
        if not self.latencies:
            return 0.0
        s = sorted(self.latencies)
        idx = int(len(s) * 0.95)
        return s[min(idx, len(s) - 1)]

    def record_success(self, result: DebateResult, elapsed: float) -> None:
        self.total += 1
        self.latencies.append(elapsed)
        has_parse_fail = any("[parse_failed]" in t["rationale"] for t in result.transcript)
        if has_parse_fail:
            self.parse_failures += 1
        if result.transcript and not has_parse_fail:
            self.success += 1
        else:
            self.errors += 1
        if _is_pyth_gate_hold(result):
            self.pyth_gate_holds += 1
        if isinstance(result.jupiter_quote, dict):
            self.jupiter_quotes_attached += 1
        if result.dry_run_signature:
            self.dry_run_built += 1
        if (
            isinstance(result.shapley_weights, dict)
            and result.shapley_weights
            and not (result.shapley_rationale or "").startswith("[shapley_")
        ):
            self.shapley_attached += 1

    def record_error(self, error: Exception, elapsed: float) -> None:
        self.total += 1
        self.errors += 1
        category = _classify_error(error)
        if category == "rate_limit":
            self.rate_limit_errors += 1
        self.latencies.append(elapsed)
        self.error_log.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "error": str(error),
                "type": type(error).__name__,
                "category": category,
            }
        )

    def summary(self) -> str:
        lines = [
            f"  runs: {self.total}  |  ok: {self.success}  |  errors: {self.errors}"
            f"  (rate_limit: {self.rate_limit_errors})"
            f"  |  parse_fail: {self.parse_failures}  |  retries: {self.retries}",
            f"  pyth_holds: {self.pyth_gate_holds}"
            f"  |  jup_quotes: {self.jupiter_quotes_attached}"
            f"  |  dry_runs: {self.dry_run_built}"
            f"  |  shapley: {self.shapley_attached}",
            f"  success rate: {self.success_rate:.1f}%",
            f"  latency avg: {self.avg_latency:.1f}s  |  p95: {self.p95_latency:.1f}s",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "success": self.success,
            "errors": self.errors,
            "rate_limit_errors": self.rate_limit_errors,
            "parse_failures": self.parse_failures,
            "retries": self.retries,
            "pyth_gate_holds": self.pyth_gate_holds,
            "jupiter_quotes_attached": self.jupiter_quotes_attached,
            "dry_run_built": self.dry_run_built,
            "shapley_attached": self.shapley_attached,
            "success_rate": round(self.success_rate, 2),
            "avg_latency": round(self.avg_latency, 2),
            "p95_latency": round(self.p95_latency, 2),
            "recent_errors": self.error_log[-5:],
        }


_STOP = False


def _handle_signal(signum, frame):
    global _STOP  # noqa: PLW0603
    _STOP = True
    # Avoid print in signal handler - can cause reentrant calls


def run_continuous(
    symbol: str = "SOL/USDT",
    interval: int = 300,
    max_runs: int = 0,
    verbose: bool = False,
) -> RunnerMetrics:
    """Run debates in a loop, collecting metrics.

    Args:
        symbol: Trading pair.
        interval: Seconds between debate starts.
        max_runs: Stop after this many runs (0 = unlimited).
        verbose: Stream specialist turns as they land.

    Returns:
        Accumulated metrics when the loop exits.
    """
    global _STOP  # noqa: PLW0603
    _STOP = False
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    metrics = RunnerMetrics()
    metrics_path = Path("data/runner_metrics.json")
    metrics_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"  [runner] starting continuous loop — {symbol} every {interval}s", file=sys.stderr)
    print("  [runner] press Ctrl+C to stop gracefully\n", file=sys.stderr)

    while not _STOP:
        run_num = metrics.total + 1
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"  [{ts}] run #{run_num} ...", end="", file=sys.stderr, flush=True)

        t0 = time.monotonic()
        result = None
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            if _STOP:
                break
            try:
                result = run_debate(symbol, thread_id=f"runner-{run_num}", verbose=verbose)
                break
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1 and _is_rate_limit(exc):
                    backoff = _INITIAL_BACKOFF_S * (3**attempt)
                    metrics.retries += 1
                    print(
                        f"  rate-limited (attempt {attempt + 1}/{_MAX_RETRIES}),"
                        f" retrying in {backoff}s...",
                        end="",
                        file=sys.stderr,
                        flush=True,
                    )
                    for _ in range(backoff):
                        if _STOP:
                            break
                        time.sleep(1)
                else:
                    break  # non-retryable or final attempt

        elapsed = time.monotonic() - t0
        if result is not None:
            metrics.record_success(result, elapsed)
            save_debate(result)
            try:
                append_debate_log(result)
            except OSError as log_exc:
                print(
                    f"  [runner] warn: debate_log append failed: {log_exc}",
                    file=sys.stderr,
                )
            print(
                f"  {result.final_decision}  ({elapsed:.1f}s)"
                f"  [{metrics.success}/{metrics.total} ok]",
                file=sys.stderr,
            )
        elif last_exc is not None:
            metrics.record_error(last_exc, elapsed)
            print(f"  ERROR: {last_exc}  ({elapsed:.1f}s)", file=sys.stderr)
            print(f"  ERROR TYPE: {type(last_exc).__name__}", file=sys.stderr)
            print(f"  ERROR REPR: {repr(last_exc)}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

        # Persist metrics after every run
        metrics_path.write_text(json.dumps(metrics.to_dict(), indent=2), encoding="utf-8")

        if max_runs and metrics.total >= max_runs:
            break
        if _STOP:
            break

        # Sleep in small increments so Ctrl+C is responsive
        for _ in range(interval):
            if _STOP:
                break
            time.sleep(1)

    print(f"\n  [runner] stopped after {metrics.total} runs.", file=sys.stderr)
    print(metrics.summary(), file=sys.stderr)
    return metrics
