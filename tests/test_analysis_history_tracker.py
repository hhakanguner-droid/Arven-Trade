from datetime import date, timedelta

import pytest

from tradingagents.history import AnalysisHistoryStore, AnalysisHistoryTracker


def _business_series(start: date, sessions: int, first: float, step: float):
    rows = []
    day = start
    value = first
    while len(rows) < sessions:
        if day.weekday() < 5:
            rows.append((day, value))
            value += step
        day += timedelta(days=1)
    return rows


def _config(tmp_path):
    return {
        "analysis_history_enabled": True,
        "analysis_history_path": str(tmp_path / "history.db"),
        "analysis_history_horizons": (1, 5, 20),
        "analysis_history_resolve_limit": 10,
        "benchmark_ticker": None,
        "benchmark_map": {".IS": "^XU100", "": "SPY"},
    }


def test_weekend_analysis_anchors_to_last_session_and_uses_bist100(tmp_path):
    calls = []
    stock = [
        (date(2026, 8, 21), 100.0),  # Friday baseline
        (date(2026, 8, 24), 110.0),  # Monday = 1 trading session later
    ]
    benchmark = [
        (date(2026, 8, 21), 200.0),
        (date(2026, 8, 24), 202.0),
    ]

    def loader(symbol, start, end):
        calls.append(symbol)
        return benchmark if symbol == "^XU100" else stock

    tracker = AnalysisHistoryTracker(_config(tmp_path), history_loader=loader)
    entry, points = tracker._resolve_prices("THYAO.IS", "2026-08-23", (1,))

    assert entry == 100.0
    assert calls == ["THYAO.IS", "^XU100"]
    assert points[0].raw_return == pytest.approx(0.10)
    assert points[0].benchmark_return == pytest.approx(0.01)
    assert points[0].alpha_return == pytest.approx(0.09)


def test_resolves_1_5_20_trading_session_performance(tmp_path):
    stock = _business_series(date(2026, 8, 3), 25, 100.0, 2.0)
    benchmark = _business_series(date(2026, 8, 3), 25, 200.0, 1.0)

    def loader(symbol, start, end):
        return benchmark if symbol == "^XU100" else stock

    tracker = AnalysisHistoryTracker(_config(tmp_path), history_loader=loader)
    entry, points = tracker._resolve_prices("ASELS.IS", "2026-08-03", (1, 5, 20))

    assert entry == 100.0
    assert [point.horizon_days for point in points] == [1, 5, 20]
    assert points[0].raw_return == pytest.approx(0.02)
    assert points[1].raw_return == pytest.approx(0.10)
    assert points[2].raw_return == pytest.approx(0.40)
    assert points[2].benchmark_return is not None


def test_pending_backfill_reuses_one_stock_and_one_benchmark_fetch(tmp_path):
    calls = []
    stock = _business_series(date(2026, 7, 1), 45, 100.0, 1.0)
    benchmark = _business_series(date(2026, 7, 1), 45, 200.0, 0.5)

    def loader(symbol, start, end):
        calls.append(symbol)
        return benchmark if symbol == "^XU100" else stock

    config = _config(tmp_path)
    store = AnalysisHistoryStore(config["analysis_history_path"])
    for trade_date in ("2026-07-01", "2026-07-02"):
        store.record_analysis(
            ticker="THYAO.IS",
            trade_date=trade_date,
            final_decision="Rating: Buy",
            state={
                "company_of_interest": "THYAO.IS",
                "trade_date": trade_date,
                "final_trade_decision": "Rating: Buy",
            },
        )

    tracker = AnalysisHistoryTracker(config, store=store, history_loader=loader)
    updated = tracker.resolve_pending("THYAO.IS")

    assert updated == 6
    assert calls == ["THYAO.IS", "^XU100"]
    assert all(len(row["performance"]) == 3 for row in store.list_analyses("THYAO.IS"))


def test_final_node_wrapper_records_completed_state_without_changing_result(tmp_path):
    stock = _business_series(date(2026, 8, 3), 3, 100.0, 1.0)
    benchmark = _business_series(date(2026, 8, 3), 3, 200.0, 1.0)

    def loader(symbol, start, end):
        return benchmark if symbol == "^XU100" else stock

    tracker = AnalysisHistoryTracker(_config(tmp_path), history_loader=loader)

    def final_node(state):
        return {
            "final_trade_decision": "Rating: Buy\nEvidence",
            "risk_debate_state": {"judge_decision": "Rating: Buy"},
        }

    wrapped = tracker.wrap_final_node(final_node)
    result = wrapped(
        {
            "company_of_interest": "THYAO.IS",
            "trade_date": "2026-08-03",
            "market_report": "market",
            "kap_report": "kap",
        }
    )

    assert result["final_trade_decision"].startswith("Rating: Buy")
    rows = tracker.list_analyses("THYAO.IS")
    assert len(rows) == 1
    assert rows[0]["rating"] == "Buy"
    assert rows[0]["state"]["kap_report"] == "kap"


def test_disabled_history_returns_original_final_node(tmp_path):
    config = _config(tmp_path)
    config["analysis_history_enabled"] = False
    tracker = AnalysisHistoryTracker(config)

    def final_node(state):
        return {"final_trade_decision": "Rating: Hold"}

    assert tracker.wrap_final_node(final_node) is final_node
    assert tracker.list_analyses("THYAO.IS") == []


def test_market_data_failure_does_not_lose_completed_analysis(tmp_path):
    def loader(symbol, start, end):
        raise RuntimeError("market feed down")

    tracker = AnalysisHistoryTracker(_config(tmp_path), history_loader=loader)
    analysis_id = tracker.record_completed(
        {
            "company_of_interest": "THYAO.IS",
            "trade_date": "2026-08-26",
            "market_report": "market",
            "final_trade_decision": "Rating: Hold\nWait",
        }
    )

    assert analysis_id is not None
    rows = tracker.list_analyses("THYAO.IS")
    assert len(rows) == 1
    assert rows[0]["rating"] == "Hold"
    assert rows[0]["entry_price"] is None
    assert rows[0]["performance"] == []


def test_backfill_repairs_alpha_after_transient_benchmark_failure(tmp_path):
    stock = _business_series(date(2026, 8, 3), 25, 100.0, 1.0)
    benchmark = _business_series(date(2026, 8, 3), 25, 200.0, 0.5)
    benchmark_available = False

    def loader(symbol, start, end):
        if symbol == "^XU100":
            if not benchmark_available:
                raise RuntimeError("benchmark temporarily unavailable")
            return benchmark
        return stock

    config = _config(tmp_path)
    tracker = AnalysisHistoryTracker(config, history_loader=loader)
    analysis_id = tracker.record_completed(
        {
            "company_of_interest": "THYAO.IS",
            "trade_date": "2026-08-03",
            "final_trade_decision": "Rating: Buy",
        }
    )

    first = tracker.store.get_analysis(analysis_id)
    assert len(first["performance"]) == 3
    assert all(item["alpha_return"] is None for item in first["performance"])

    benchmark_available = True
    updated = tracker.resolve_pending("THYAO.IS")
    repaired = tracker.store.get_analysis(analysis_id)

    assert updated == 3
    assert all(item["benchmark_return"] is not None for item in repaired["performance"])
    assert all(item["alpha_return"] is not None for item in repaired["performance"])


def test_store_open_failure_disables_history_instead_of_breaking_graph_init(tmp_path, monkeypatch):
    class FailingStore:
        def __init__(self, path):
            raise OSError("read-only filesystem")

    monkeypatch.setattr("tradingagents.history.tracker.AnalysisHistoryStore", FailingStore)
    tracker = AnalysisHistoryTracker(_config(tmp_path))

    assert tracker.enabled is False
    assert tracker.store is None
