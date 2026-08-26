import logging
import os
import sys

import pytest

from tradingagents.operations import (
    CostBudgetExceeded,
    DailyCostLedger,
    OperationalGuard,
    RateLimitExceeded,
    RunRateLimiter,
    SecretRedactionFilter,
    prune_files,
    redact_sensitive_text,
)
from tradingagents.operations.guard import OperationalPolicy


def test_redacts_environment_secret_and_common_token_shapes():
    environ = {"OPENAI_API_KEY": "sk-project-super-secret-12345"}
    text = "key=sk-project-super-secret-12345 bearer abcdefghijklmnop"

    redacted = redact_sensitive_text(text, environ=environ)

    assert "super-secret" not in redacted
    assert "abcdefghijklmnop" not in redacted
    assert redacted.count("[REDACTED]") >= 2


def test_logging_filter_redacts_formatted_args():
    record = logging.LogRecord(
        "arven",
        logging.INFO,
        __file__,
        1,
        "token=%s",
        ("very-secret-token-value",),
        None,
    )
    SecretRedactionFilter({"SERVICE_TOKEN": "very-secret-token-value"}).filter(record)

    assert record.getMessage() == "token=[REDACTED]"


def test_logging_filter_redacts_exception_traceback():
    secret = "sk-traceback-secret-value-12345"
    try:
        raise RuntimeError(f"provider rejected {secret}")
    except RuntimeError:
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        "provider",
        logging.ERROR,
        __file__,
        1,
        "request failed",
        (),
        exc_info,
    )
    SecretRedactionFilter({"PROVIDER_API_KEY": secret}).filter(record)

    assert record.exc_text is not None
    assert secret not in record.exc_text
    assert "[REDACTED]" in record.exc_text


def test_persistent_run_limiter_blocks_and_then_recovers(tmp_path):
    limiter = RunRateLimiter(tmp_path / "rate.json", max_runs=2, window_seconds=60)
    limiter.acquire(now=100.0)
    limiter.acquire(now=110.0)

    with pytest.raises(RateLimitExceeded) as exc_info:
        limiter.acquire(now=120.0)
    assert exc_info.value.retry_after_seconds == pytest.approx(40.0)

    limiter.acquire(now=161.0)


def test_daily_cost_ledger_persists_and_blocks_budget(tmp_path):
    path = tmp_path / "cost.json"
    ledger = DailyCostLedger(path, daily_limit_usd=1.0)
    assert ledger.reserve(0.4, day="2026-08-26") == pytest.approx(0.4)

    reopened = DailyCostLedger(path, daily_limit_usd=1.0)
    assert reopened.reserve(0.5, day="2026-08-26") == pytest.approx(0.9)
    with pytest.raises(CostBudgetExceeded):
        reopened.reserve(0.11, day="2026-08-26")
    assert reopened.current_spend(day="2026-08-27") == 0.0


def test_operational_guard_combines_rate_and_budget(tmp_path):
    policy = OperationalPolicy(
        max_runs_per_minute=1,
        daily_cost_limit_usd=1.0,
        estimated_run_cost_usd=0.25,
    )
    guard = OperationalGuard(tmp_path, policy)
    result = guard.before_run()

    assert result["estimated_cost_usd"] == pytest.approx(0.25)
    assert result["daily_spend_usd"] == pytest.approx(0.25)
    with pytest.raises(RateLimitExceeded):
        guard.before_run()


def test_operational_policy_reads_environment(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_MAX_RUNS_PER_MINUTE", "7")
    monkeypatch.setenv("TRADINGAGENTS_DAILY_COST_LIMIT_USD", "3.5")
    monkeypatch.setenv("TRADINGAGENTS_ESTIMATED_RUN_COST_USD", "0.2")

    policy = OperationalPolicy.from_env()

    assert policy.max_runs_per_minute == 7
    assert policy.daily_cost_limit_usd == pytest.approx(3.5)
    assert policy.estimated_run_cost_usd == pytest.approx(0.2)


def test_retention_prunes_old_and_excess_files_without_following_symlinks(tmp_path):
    root = tmp_path / "logs"
    root.mkdir()
    old = root / "old.log"
    mid = root / "mid.log"
    new = root / "new.log"
    for path in (old, mid, new):
        path.write_text(path.name, encoding="utf-8")
    os.utime(old, (100.0, 100.0))
    os.utime(mid, (200.0, 200.0))
    os.utime(new, (300.0, 300.0))

    deleted = prune_files(root, retention_days=0, max_files=2, now=400.0)

    assert old in deleted
    assert not old.exists()
    assert mid.exists() and new.exists()


def test_disabled_limits_are_non_blocking(tmp_path):
    guard = OperationalGuard(tmp_path, OperationalPolicy())

    for _ in range(20):
        result = guard.before_run()
        assert result["daily_spend_usd"] == 0.0
