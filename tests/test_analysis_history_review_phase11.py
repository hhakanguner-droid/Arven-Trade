from datetime import date

import pytest

from tradingagents.graph.setup import GraphSetup
from tradingagents.history import AnalysisHistoryTracker


def _config(tmp_path):
    return {
        "analysis_history_enabled": True,
        "analysis_history_path": str(tmp_path / "history.db"),
        "analysis_history_horizons": (1, 5, 20),
        "analysis_history_resolve_limit": 10,
        "benchmark_ticker": None,
        "benchmark_map": {".IS": "^XU100", "": "SPY"},
    }


def test_final_node_persists_current_analysis_before_backfill(tmp_path):
    tracker = AnalysisHistoryTracker(_config(tmp_path), history_loader=lambda *_: [])
    calls = []

    def final_node(state):
        return {"final_trade_decision": "Rating: Hold"}

    def record_completed(state):
        calls.append(("record", state["final_trade_decision"]))
        return 42

    def resolve_pending(ticker, *, exclude_analysis_id=None):
        calls.append(("resolve", ticker, exclude_analysis_id))
        return 0

    tracker.record_completed = record_completed
    tracker.resolve_pending = resolve_pending

    wrapped = tracker.wrap_final_node(final_node)
    result = wrapped(
        {
            "company_of_interest": "THYAO.IS",
            "trade_date": "2026-08-26",
        }
    )

    assert result == {"final_trade_decision": "Rating: Hold"}
    assert calls == [
        ("record", "Rating: Hold"),
        ("resolve", "THYAO.IS", 42),
    ]


def test_same_day_rerun_reuses_original_benchmark_and_entry_snapshots(tmp_path):
    calls = []
    stock = [
        (date(2026, 8, 3), 100.0),
        (date(2026, 8, 4), 110.0),
    ]
    bist = [
        (date(2026, 8, 3), 200.0),
        (date(2026, 8, 4), 209.0),
    ]
    spy = [
        (date(2026, 8, 3), 500.0),
        (date(2026, 8, 4), 550.0),
    ]

    def loader(symbol, start, end):
        calls.append(symbol)
        if symbol == "^XU100":
            return bist
        if symbol == "SPY":
            return spy
        return stock

    config = _config(tmp_path)
    config["analysis_history_horizons"] = (1,)
    tracker = AnalysisHistoryTracker(config, history_loader=loader)
    analysis_id = tracker.store.record_analysis(
        ticker="THYAO.IS",
        trade_date="2026-08-03",
        final_decision="Rating: Buy",
        state={
            "company_of_interest": "THYAO.IS",
            "trade_date": "2026-08-03",
            "final_trade_decision": "Rating: Buy",
        },
        entry_price=95.0,
        benchmark_ticker="^XU100",
        benchmark_entry_price=190.0,
    )

    # Simulate a later config change before the same ticker/date is rerun.
    tracker.config["benchmark_ticker"] = "SPY"
    tracker.record_completed(
        {
            "company_of_interest": "THYAO.IS",
            "trade_date": "2026-08-03",
            "final_trade_decision": "Rating: Hold",
        }
    )

    row = tracker.store.get_analysis(analysis_id)
    assert calls == ["THYAO.IS", "^XU100"]
    assert row["rating"] == "Hold"
    assert row["entry_price"] == 95.0
    assert row["benchmark_ticker"] == "^XU100"
    assert row["benchmark_entry_price"] == 190.0
    point = row["performance"][0]
    assert point["raw_return"] == pytest.approx(110.0 / 95.0 - 1.0)
    assert point["benchmark_return"] == pytest.approx(209.0 / 190.0 - 1.0)


def test_graph_setup_prefers_explicit_instance_history_config(tmp_path):
    config = _config(tmp_path)
    config["analysis_history_enabled"] = False

    setup = GraphSetup(None, None, {}, None, config=config)

    assert setup.analysis_history.enabled is False
