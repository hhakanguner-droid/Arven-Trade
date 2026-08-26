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
