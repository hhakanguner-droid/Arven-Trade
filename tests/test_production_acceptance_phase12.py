import logging

import pytest

from tradingagents.operations import (
    CostBudgetExceeded,
    OperationalGuard,
    OperationalPolicy,
    OperationalPolicyError,
    OperationalStateError,
    ProductionRuntime,
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

    # The rejected run must not consume the only rate slot.
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
    (state_dir / "run_rate.json").write_text('{"timestamps": ["broken"]}', encoding="utf-8")
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
