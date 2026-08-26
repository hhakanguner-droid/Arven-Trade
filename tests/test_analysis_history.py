import sqlite3

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
        benchmark_ticker="^XU100",
        benchmark_entry_price=10950.0,
    )

    row = store.get_analysis(analysis_id)
    assert row["ticker"] == "THYAO.IS"
    assert row["rating"] == "Buy"
    assert row["signal"] == "BUY"
    assert row["entry_price"] == 321.5
    assert row["benchmark_ticker"] == "^XU100"
    assert row["benchmark_entry_price"] == 10950.0
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
    assert summary["horizons"][0]["alpha_positive_rate"] == 1.0


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


def test_compare_latest_honors_requested_count(tmp_path):
    store = AnalysisHistoryStore(tmp_path / "history.db")
    for trade_date in ("2026-08-20", "2026-08-24", "2026-08-26"):
        store.record_analysis(
            ticker="GARAN.IS",
            trade_date=trade_date,
            final_decision="Rating: Hold",
            state=_state("Rating: Hold"),
        )

    latest = store.compare_latest("GARAN.IS", count=1)

    assert len(latest) == 1
    assert latest[0]["trade_date"] == "2026-08-26"


def test_idempotent_refresh_does_not_erase_existing_snapshots(tmp_path):
    store = AnalysisHistoryStore(tmp_path / "history.db")
    analysis_id = store.record_analysis(
        ticker="THYAO.IS",
        trade_date="2026-08-26",
        final_decision="Rating: Buy",
        state=_state(),
        entry_price=321.5,
        benchmark_ticker="^XU100",
        benchmark_entry_price=11000.0,
    )
    refreshed = store.record_analysis(
        ticker="THYAO.IS",
        trade_date="2026-08-26",
        final_decision="Rating: Hold",
        state=_state("Rating: Hold"),
        entry_price=None,
        benchmark_ticker=None,
        benchmark_entry_price=None,
    )

    assert refreshed == analysis_id
    row = store.get_analysis(analysis_id)
    assert row["entry_price"] == 321.5
    assert row["benchmark_ticker"] == "^XU100"
    assert row["benchmark_entry_price"] == 11000.0


def test_pending_analyses_returns_oldest_rows_missing_requested_horizons(tmp_path):
    store = AnalysisHistoryStore(tmp_path / "history.db")
    older = store.record_analysis(
        ticker="THYAO.IS",
        trade_date="2026-08-20",
        final_decision="Rating: Buy",
        state=_state(),
    )
    newer = store.record_analysis(
        ticker="THYAO.IS",
        trade_date="2026-08-22",
        final_decision="Rating: Hold",
        state=_state("Rating: Hold"),
    )
    store.record_performance(older, [PerformancePoint(1, 0.01, 0.0)])

    pending = store.pending_analyses((1, 5, 20), ticker="THYAO.IS")

    assert [row["id"] for row in pending] == [older, newer]
    assert [p["horizon_days"] for p in pending[0]["performance"]] == [1]


def test_pending_analyses_retries_horizon_with_missing_alpha(tmp_path):
    store = AnalysisHistoryStore(tmp_path / "history.db")
    analysis_id = store.record_analysis(
        ticker="THYAO.IS",
        trade_date="2026-08-20",
        final_decision="Rating: Buy",
        state=_state(),
    )
    store.record_performance(
        analysis_id,
        [
            PerformancePoint(1, 0.01, None),
            PerformancePoint(5, 0.02, 0.01),
            PerformancePoint(20, 0.03, 0.01),
        ],
    )

    pending = store.pending_analyses((1, 5, 20), ticker="THYAO.IS")

    assert [row["id"] for row in pending] == [analysis_id]


def test_update_price_snapshots_only_fills_missing_values(tmp_path):
    store = AnalysisHistoryStore(tmp_path / "history.db")
    analysis_id = store.record_analysis(
        ticker="ASELS.IS",
        trade_date="2026-08-20",
        final_decision="Rating: Hold",
        state=_state("Rating: Hold"),
    )

    store.update_price_snapshots(
        analysis_id,
        entry_price=101.25,
        benchmark_ticker="^XU100",
        benchmark_entry_price=10800.0,
    )
    store.update_price_snapshots(
        analysis_id,
        entry_price=999.0,
        benchmark_ticker="SPY",
        benchmark_entry_price=99999.0,
    )

    row = store.get_analysis(analysis_id)
    assert row["entry_price"] == 101.25
    assert row["benchmark_ticker"] == "^XU100"
    assert row["benchmark_entry_price"] == 10800.0


def test_idempotent_refresh_preserves_original_created_at(tmp_path):
    store = AnalysisHistoryStore(tmp_path / "history.db")
    analysis_id = store.record_analysis(
        ticker="KCHOL.IS",
        trade_date="2026-08-20",
        final_decision="Rating: Hold",
        state=_state("Rating: Hold"),
    )
    created_at = store.get_analysis(analysis_id)["created_at"]

    store.record_analysis(
        ticker="KCHOL.IS",
        trade_date="2026-08-20",
        final_decision="Rating: Overweight",
        state=_state("Rating: Overweight"),
        entry_price=200.0,
    )

    assert store.get_analysis(analysis_id)["created_at"] == created_at


def test_v1_database_migrates_to_benchmark_snapshot_columns(tmp_path):
    path = tmp_path / "history-v1.db"
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            created_at TEXT NOT NULL,
            rating TEXT NOT NULL,
            signal TEXT,
            entry_price REAL,
            final_decision TEXT NOT NULL,
            state_json TEXT NOT NULL,
            UNIQUE(ticker, trade_date)
        );
        CREATE TABLE performance (
            analysis_id INTEGER NOT NULL,
            horizon_days INTEGER NOT NULL,
            measured_at TEXT NOT NULL,
            raw_return REAL NOT NULL,
            benchmark_return REAL,
            alpha_return REAL,
            PRIMARY KEY (analysis_id, horizon_days)
        );
        """
    )
    db.commit()
    db.close()

    store = AnalysisHistoryStore(path)
    analysis_id = store.record_analysis(
        ticker="THYAO.IS",
        trade_date="2026-08-26",
        final_decision="Rating: Buy",
        state=_state(),
        benchmark_ticker="^XU100",
        benchmark_entry_price=11000.0,
    )

    row = store.get_analysis(analysis_id)
    assert row["benchmark_ticker"] == "^XU100"
    assert row["benchmark_entry_price"] == 11000.0
    with sqlite3.connect(path) as check:
        version = check.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]
    assert version == "2"
