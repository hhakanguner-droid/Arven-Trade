import os

import pytest

from tradingagents.operations import ProductionRuntime, RetentionPolicy


class _Guard:
    def __init__(self):
        self.calls = []

    def before_run(self, *, estimated_cost_usd=None):
        self.calls.append(estimated_cost_usd)
        return {
            "estimated_cost_usd": float(estimated_cost_usd or 0.0),
            "daily_spend_usd": float(estimated_cost_usd or 0.0),
        }


class _Graph:
    def __init__(self, results_dir):
        self.config = {"results_dir": str(results_dir), "data_cache_dir": str(results_dir)}
        self.calls = []

    def propagate(self, company_name, trade_date, asset_type="stock"):
        self.calls.append((company_name, trade_date, asset_type))
        return {"ticker": company_name, "date": trade_date}


def test_runtime_enforces_guard_before_graph(tmp_path):
    guard = _Guard()
    graph = _Graph(tmp_path)
    runtime = ProductionRuntime(graph, guard=guard, state_dir=tmp_path / "ops")

    result = runtime.propagate("THYAO.IS", "2026-08-26", estimated_cost_usd=0.3)

    assert guard.calls == [0.3]
    assert graph.calls == [("THYAO.IS", "2026-08-26", "stock")]
    assert result["ticker"] == "THYAO.IS"


def test_runtime_applies_configured_retention(tmp_path):
    results = tmp_path / "results"
    results.mkdir()
    old = results / "old.log"
    old.write_text("old", encoding="utf-8")
    os.utime(old, (100.0, 100.0))

    guard = _Guard()
    runtime = ProductionRuntime(
        _Graph(results),
        guard=guard,
        retention=RetentionPolicy(results_retention_days=1, results_max_files=0),
    )
    runtime.propagate("ASELS.IS", "2026-08-26")

    assert not old.exists()


def test_runtime_propagates_graph_errors(tmp_path):
    class BrokenGraph(_Graph):
        def propagate(self, company_name, trade_date, asset_type="stock"):
            raise RuntimeError("provider failed")

    runtime = ProductionRuntime(BrokenGraph(tmp_path), guard=_Guard())

    with pytest.raises(RuntimeError, match="provider failed"):
        runtime.propagate("TUPRS.IS", "2026-08-26")


def test_retention_policy_reads_environment(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_RESULTS_RETENTION_DAYS", "30")
    monkeypatch.setenv("TRADINGAGENTS_RESULTS_MAX_FILES", "2500")

    policy = RetentionPolicy.from_env()

    assert policy.results_retention_days == 30
    assert policy.results_max_files == 2500
