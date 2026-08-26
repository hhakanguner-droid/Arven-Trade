from tradingagents.history.store import AnalysisHistoryStore, PerformancePoint


def _state(decision="Rating: Buy"):
    return {
        "company_of_interest": "THYAO.IS",
        "trade_date": "2026-08-26",
        "market_report": "market",
        "kap_report": "kap",
        "final_trade_decision": decision,
    }


def test_records_and_reads_analysis(tmp_path):
    store = AnalysisHistoryStore(tmp_path / "history.db")
    analysis_id = store.record_analysis(
        ticker="THYAO.IS",
        trade_date="2026-08-26",
        final_decision="Rating: Buy\nStrong setup",
        state=_state(),
        signal="BUY",
        entry_price=321.5,
    )

    row = store.get_analysis(analysis_id)
    assert row["ticker"] == "THYAO.IS"
    assert row["rating"] == "Buy"
    assert row["signal"] == "BUY"
    assert row["entry_price"] == 321.5
    assert row["state"]["kap_report"] == "kap"


def test_same_ticker_date_is_idempotent(tmp_path):
    store = AnalysisHistoryStore(tmp_path / "history.db")
    first = store.record_analysis(
        ticker="ASELS.IS",
        trade_date="2026-08-26",
        final_decision="Rating: Hold",
        state=_state("Rating: Hold"),
    )
    second = store.record_analysis(
        ticker="ASELS.IS",
        trade_date="2026-08-26",
        final_decision="Rating: Sell",
        state=_state("Rating: Sell"),
    )

    assert first == second
    rows = store.list_analyses("ASELS.IS")
    assert len(rows) == 1
    assert rows[0]["rating"] == "Sell"


def test_performance_horizons_and_summary(tmp_path):
    store = AnalysisHistoryStore(tmp_path / "history.db")
    analysis_id = store.record_analysis(
        ticker="TUPRS.IS",
        trade_date="2026-08-20",
        final_decision="Rating: Buy",
        state=_state(),
    )
    store.record_performance(
        analysis_id,
        [
            PerformancePoint(1, 0.02, 0.01),
            PerformancePoint(5, -0.01, -0.03),
            PerformancePoint(20, 0.10, 0.04),
        ],
        measured_at="2026-08-26T00:00:00+00:00",
    )

    row = store.get_analysis(analysis_id)
    assert [p["horizon_days"] for p in row["performance"]] == [1, 5, 20]
    assert row["performance"][0]["alpha_return"] == 0.01

    summary = store.performance_summary("TUPRS.IS")
    assert [h["horizon_days"] for h in summary["horizons"]] == [1, 5, 20]
    assert summary["horizons"][0]["samples"] == 1
    assert summary["horizons"][0]["positive_rate"] == 1.0


def test_compare_latest_orders_newest_first(tmp_path):
    store = AnalysisHistoryStore(tmp_path / "history.db")
    for date, rating in [
        ("2026-08-20", "Hold"),
        ("2026-08-24", "Overweight"),
        ("2026-08-26", "Buy"),
    ]:
        store.record_analysis(
            ticker="GARAN.IS",
            trade_date=date,
            final_decision=f"Rating: {rating}",
            state=_state(f"Rating: {rating}"),
        )

    latest = store.compare_latest("GARAN.IS")
    assert [item["trade_date"] for item in latest] == ["2026-08-26", "2026-08-24"]
