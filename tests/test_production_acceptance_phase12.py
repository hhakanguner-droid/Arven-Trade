import io
import logging
import threading
import time
from pathlib import Path

import pytest

from tradingagents.operations import (
    CostBudgetExceeded,
    OperationalGuard,
    OperationalPolicy,
    OperationalPolicyError,
    OperationalStateError,
    ProductionRuntime,
    create_production_runtime,
    install_secret_redaction,
    prune_files,
)


class _Graph:
    def __init__(self, root):
        self.config = {
            "data_cache_dir": str(root / "cache"),
            "results_dir": str(root / "results"),
        }
        self.calls = []

    def propagate(self, company_name, trade_date, asset_type="stock"):
        self.calls.append((company_name, trade_date, asset_type))
        return {"ticker": company_name}


def test_cost_budget_rejection_prevents_graph_and_rolls_back_rate_slot(tmp_path):
    graph = _Graph(tmp_path)
    state_dir = tmp_path / "ops"
    rejecting = OperationalGuard(
        state_dir,
        OperationalPolicy(
            max_runs_per_minute=1,
            daily_cost_limit_usd=0.1,
            estimated_run_cost_usd=0.2,
        ),
    )
    runtime = ProductionRuntime(graph, state_dir=state_dir, guard=rejecting)

    with pytest.raises(CostBudgetExceeded):
        runtime.propagate("THYAO.IS", "2026-08-26")
    assert graph.calls == []

    accepting = OperationalGuard(
        state_dir,
        OperationalPolicy(
            max_runs_per_minute=1,
            daily_cost_limit_usd=1.0,
            estimated_run_cost_usd=0.05,
        ),
    )
    accepted_runtime = ProductionRuntime(graph, state_dir=state_dir, guard=accepting)
    accepted_runtime.propagate("THYAO.IS", "2026-08-26")
    assert len(graph.calls) == 1


def test_caller_cannot_undercut_configured_cost_floor(tmp_path):
    guard = OperationalGuard(
        tmp_path,
        OperationalPolicy(daily_cost_limit_usd=1.0, estimated_run_cost_usd=0.4),
    )

    result = guard.before_run(estimated_cost_usd=0.01)

    assert result["estimated_cost_usd"] == pytest.approx(0.4)
    assert result["daily_spend_usd"] == pytest.approx(0.4)


def test_enabled_budget_without_positive_estimate_fails_closed(tmp_path):
    guard = OperationalGuard(
        tmp_path,
        OperationalPolicy(daily_cost_limit_usd=1.0, estimated_run_cost_usd=0.0),
    )

    with pytest.raises(OperationalPolicyError, match="positive per-run cost estimate"):
        guard.before_run()


def test_corrupt_cost_state_fails_closed_before_graph(tmp_path):
    graph = _Graph(tmp_path)
    state_dir = tmp_path / "ops"
    state_dir.mkdir()
    (state_dir / "daily_cost.json").write_text("{not-json", encoding="utf-8")
    guard = OperationalGuard(
        state_dir,
        OperationalPolicy(daily_cost_limit_usd=1.0, estimated_run_cost_usd=0.1),
    )
    runtime = ProductionRuntime(graph, state_dir=state_dir, guard=guard)

    with pytest.raises(OperationalStateError, match="Corrupt operational state"):
        runtime.propagate("ASELS.IS", "2026-08-26")
    assert graph.calls == []


def test_corrupt_rate_state_fails_closed_before_graph(tmp_path):
    graph = _Graph(tmp_path)
    state_dir = tmp_path / "ops"
    state_dir.mkdir()
    (state_dir / "run_rate.json").write_text(
        '{"timestamps": ["broken"]}',
        encoding="utf-8",
    )
    guard = OperationalGuard(
        state_dir,
        OperationalPolicy(max_runs_per_minute=2),
    )
    runtime = ProductionRuntime(graph, state_dir=state_dir, guard=guard)

    with pytest.raises(OperationalStateError, match="Invalid run-rate timestamp"):
        runtime.propagate("TUPRS.IS", "2026-08-26")
    assert graph.calls == []


def test_runtime_error_logging_redacts_environment_secret(tmp_path, monkeypatch, caplog):
    secret = "sk-production-secret-value-123456"
    monkeypatch.setenv("OPENAI_API_KEY", secret)

    class BrokenGraph(_Graph):
        def propagate(self, company_name, trade_date, asset_type="stock"):
            raise RuntimeError(f"provider rejected key {secret}")

    runtime = ProductionRuntime(BrokenGraph(tmp_path), state_dir=tmp_path / "ops")
    caplog.set_level(logging.ERROR)

    with pytest.raises(RuntimeError):
        runtime.propagate("THYAO.IS", "2026-08-26")

    assert secret not in caplog.text
    assert "[REDACTED]" in caplog.text


def test_retention_never_follows_or_deletes_symlink_target(tmp_path):
    outside = tmp_path / "outside.log"
    outside.write_text("keep", encoding="utf-8")
    root = tmp_path / "results"
    root.mkdir()
    link = root / "outside-link.log"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable on this platform")

    deleted = prune_files(root, retention_days=1, max_files=1, now=10_000_000.0)

    assert deleted == []
    assert link.is_symlink()
    assert outside.read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_non_finite_environment_cost_policy_is_rejected(monkeypatch, value):
    monkeypatch.setenv("TRADINGAGENTS_DAILY_COST_LIMIT_USD", value)

    with pytest.raises(OperationalPolicyError, match="finite number"):
        OperationalPolicy.from_env()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_per_run_estimate_is_rejected(tmp_path, value):
    guard = OperationalGuard(
        tmp_path,
        OperationalPolicy(daily_cost_limit_usd=1.0, estimated_run_cost_usd=0.1),
    )

    with pytest.raises(OperationalPolicyError, match="finite number"):
        guard.before_run(estimated_cost_usd=value)


def test_non_finite_persisted_spend_fails_closed(tmp_path):
    state_dir = tmp_path / "ops"
    state_dir.mkdir()
    (state_dir / "daily_cost.json").write_text(
        '{"day": "2026-08-26", "spent_usd": NaN}',
        encoding="utf-8",
    )
    guard = OperationalGuard(
        state_dir,
        OperationalPolicy(daily_cost_limit_usd=1.0, estimated_run_cost_usd=0.1),
    )

    with pytest.raises(OperationalStateError, match="Non-finite cost state"):
        guard.cost_ledger.current_spend(day="2026-08-26")


def test_structured_logging_extra_secret_is_redacted(monkeypatch):
    secret = "sk-structured-secret-value-123456"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    install_secret_redaction()

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(api_key)s"))
    logger = logging.Logger("phase12-structured")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    logger.info("request", extra={"api_key": secret})

    output = stream.getvalue()
    assert secret not in output
    assert "[REDACTED]" in output


def test_positional_graph_config_is_the_config_validated(monkeypatch, tmp_path):
    import tradingagents.graph.trading_graph as graph_module

    class FakeGraph:
        def __init__(
            self,
            selected_analysts=("market",),
            debug=False,
            config=None,
            callbacks=None,
        ):
            del selected_analysts, debug, callbacks
            self.config = config or {}

        def propagate(self, company_name, trade_date, asset_type="stock"):
            return company_name, trade_date, asset_type

    monkeypatch.setattr(graph_module, "TradingAgentsGraph", FakeGraph)
    config = {
        "llm_provider": "ollama",
        "data_cache_dir": str(tmp_path / "cache"),
        "results_dir": str(tmp_path / "results"),
    }

    runtime = create_production_runtime(("market",), False, config)

    assert runtime.graph.config is config
    assert runtime.credential_status["provider"] == "ollama"


def test_runtime_serializes_shared_graph_execution(tmp_path):
    class StatefulGraph(_Graph):
        def __init__(self, root):
            super().__init__(root)
            self._counter_lock = threading.Lock()
            self.active = 0
            self.max_active = 0

        def propagate(self, company_name, trade_date, asset_type="stock"):
            with self._counter_lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            time.sleep(0.05)
            with self._counter_lock:
                self.active -= 1
            return company_name

    graph = StatefulGraph(tmp_path)
    runtime = ProductionRuntime(graph, state_dir=tmp_path / "ops")
    start = threading.Barrier(3)

    def run(ticker):
        start.wait()
        runtime.propagate(ticker, "2026-08-26")

    threads = [
        threading.Thread(target=run, args=("THYAO.IS",)),
        threading.Thread(target=run, args=("ASELS.IS",)),
    ]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join(timeout=2)

    assert all(not thread.is_alive() for thread in threads)
    assert graph.max_active == 1


def test_retention_permission_error_is_best_effort(monkeypatch, tmp_path):
    root = tmp_path / "results"
    root.mkdir()
    victim = root / "locked.log"
    victim.write_text("keep", encoding="utf-8")
    original_unlink = Path.unlink

    def blocked_unlink(path, *args, **kwargs):
        if path == victim:
            raise PermissionError("locked")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", blocked_unlink)

    deleted = prune_files(root, retention_days=1, now=10_000_000.0)

    assert deleted == []
    assert victim.exists()
