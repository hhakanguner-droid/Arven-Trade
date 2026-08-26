"""Persistent run-rate and cost-budget guardrails for production execution."""

from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class RateLimitExceeded(RuntimeError):
    def __init__(self, retry_after_seconds: float):
        self.retry_after_seconds = max(0.0, float(retry_after_seconds))
        super().__init__(
            f"ARVEN run rate limit exceeded; retry after {self.retry_after_seconds:.1f}s"
        )


class CostBudgetExceeded(RuntimeError):
    pass


@contextmanager
def _state_lock(path: Path, *, timeout_seconds: float = 5.0):
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    fd = None
    while fd is None:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
                if age > max(30.0, timeout_seconds * 4):
                    lock_path.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for operational state lock: {lock_path}")
            time.sleep(0.05)
    try:
        yield
    finally:
        os.close(fd)
        lock_path.unlink(missing_ok=True)


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(default)
    return value if isinstance(value, dict) else dict(default)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


class RunRateLimiter:
    """Cross-process sliding-window limiter backed by a tiny JSON state file."""

    def __init__(self, path: str | Path, max_runs: int, window_seconds: float = 60.0):
        self.path = Path(path).expanduser()
        self.max_runs = max(0, int(max_runs))
        self.window_seconds = max(1.0, float(window_seconds))

    def acquire(self, *, now: float | None = None) -> None:
        if self.max_runs <= 0:
            return
        timestamp = time.time() if now is None else float(now)
        cutoff = timestamp - self.window_seconds
        with _state_lock(self.path):
            state = _read_json(self.path, {"timestamps": []})
            values = []
            for raw in state.get("timestamps", []):
                try:
                    observed = float(raw)
                except (TypeError, ValueError):
                    continue
                if observed > cutoff and observed <= timestamp + 1.0:
                    values.append(observed)
            values.sort()
            if len(values) >= self.max_runs:
                retry_after = self.window_seconds - (timestamp - values[0])
                raise RateLimitExceeded(retry_after)
            values.append(timestamp)
            _write_json(self.path, {"timestamps": values})


class DailyCostLedger:
    """Persistent daily USD budget ledger; a non-positive limit disables blocking."""

    def __init__(self, path: str | Path, daily_limit_usd: float):
        self.path = Path(path).expanduser()
        self.daily_limit_usd = max(0.0, float(daily_limit_usd))

    def reserve(self, amount_usd: float, *, day: str | None = None) -> float:
        amount = float(amount_usd)
        if amount < 0:
            raise ValueError("amount_usd must be >= 0")
        if amount == 0:
            return self.current_spend(day=day)
        current_day = day or datetime.now(timezone.utc).date().isoformat()
        with _state_lock(self.path):
            state = _read_json(self.path, {"day": current_day, "spent_usd": 0.0})
            spent = float(state.get("spent_usd", 0.0)) if state.get("day") == current_day else 0.0
            projected = spent + amount
            if self.daily_limit_usd > 0 and projected > self.daily_limit_usd + 1e-12:
                raise CostBudgetExceeded(
                    f"ARVEN daily cost budget exceeded: ${projected:.4f} > "
                    f"${self.daily_limit_usd:.4f}"
                )
            _write_json(self.path, {"day": current_day, "spent_usd": projected})
            return projected

    def current_spend(self, *, day: str | None = None) -> float:
        current_day = day or datetime.now(timezone.utc).date().isoformat()
        state = _read_json(self.path, {"day": current_day, "spent_usd": 0.0})
        if state.get("day") != current_day:
            return 0.0
        try:
            return max(0.0, float(state.get("spent_usd", 0.0)))
        except (TypeError, ValueError):
            return 0.0


@dataclass(frozen=True)
class OperationalPolicy:
    max_runs_per_minute: int = 0
    daily_cost_limit_usd: float = 0.0
    estimated_run_cost_usd: float = 0.0

    @classmethod
    def from_env(cls) -> "OperationalPolicy":
        return cls(
            max_runs_per_minute=max(
                0, int(os.getenv("TRADINGAGENTS_MAX_RUNS_PER_MINUTE", "0"))
            ),
            daily_cost_limit_usd=max(
                0.0, float(os.getenv("TRADINGAGENTS_DAILY_COST_LIMIT_USD", "0"))
            ),
            estimated_run_cost_usd=max(
                0.0, float(os.getenv("TRADINGAGENTS_ESTIMATED_RUN_COST_USD", "0"))
            ),
        )


class OperationalGuard:
    """Single pre-run gate used by production entry points."""

    def __init__(self, state_dir: str | Path, policy: OperationalPolicy):
        root = Path(state_dir).expanduser()
        self.policy = policy
        self.rate_limiter = RunRateLimiter(
            root / "run_rate.json",
            policy.max_runs_per_minute,
            60.0,
        )
        self.cost_ledger = DailyCostLedger(
            root / "daily_cost.json",
            policy.daily_cost_limit_usd,
        )

    @classmethod
    def from_env(cls, state_dir: str | Path) -> "OperationalGuard":
        return cls(state_dir, OperationalPolicy.from_env())

    def before_run(self, *, estimated_cost_usd: float | None = None) -> dict[str, float]:
        self.rate_limiter.acquire()
        estimate = (
            self.policy.estimated_run_cost_usd
            if estimated_cost_usd is None
            else max(0.0, float(estimated_cost_usd))
        )
        spend = self.cost_ledger.reserve(estimate)
        return {"estimated_cost_usd": estimate, "daily_spend_usd": spend}
