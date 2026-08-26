"""SQLite-backed analysis history and performance tracking for Phase 11.

The store is intentionally stdlib-only and independent from the UI layer. It
persists completed analyses, allows chronological comparisons, and stores
multiple realized-performance horizons without changing existing memory-log
behaviour.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from tradingagents.agents.utils.rating import parse_rating


@dataclass(frozen=True)
class PerformancePoint:
    horizon_days: int
    raw_return: float
    benchmark_return: float | None = None

    @property
    def alpha_return(self) -> float | None:
        if self.benchmark_return is None:
            return None
        return self.raw_return - self.benchmark_return


class AnalysisHistoryStore:
    """Durable analysis history with deterministic SQLite schema migrations."""

    SCHEMA_VERSION = 2

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS analyses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    rating TEXT NOT NULL,
                    signal TEXT,
                    entry_price REAL,
                    benchmark_ticker TEXT,
                    benchmark_entry_price REAL,
                    final_decision TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    UNIQUE(ticker, trade_date)
                );

                CREATE INDEX IF NOT EXISTS idx_analyses_ticker_date
                    ON analyses(ticker, trade_date DESC);

                CREATE TABLE IF NOT EXISTS performance (
                    analysis_id INTEGER NOT NULL,
                    horizon_days INTEGER NOT NULL,
                    measured_at TEXT NOT NULL,
                    raw_return REAL NOT NULL,
                    benchmark_return REAL,
                    alpha_return REAL,
                    PRIMARY KEY (analysis_id, horizon_days),
                    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
                );
                """
            )

            # v2 stores the benchmark identity and its entry snapshot so later
            # backfills can use the exact prices observed when the analysis was
            # created (important for analyses run while a session is still open).
            columns = {
                str(row["name"])
                for row in db.execute("PRAGMA table_info(analyses)").fetchall()
            }
            if "benchmark_ticker" not in columns:
                db.execute("ALTER TABLE analyses ADD COLUMN benchmark_ticker TEXT")
            if "benchmark_entry_price" not in columns:
                db.execute("ALTER TABLE analyses ADD COLUMN benchmark_entry_price REAL")

            db.execute(
                "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(self.SCHEMA_VERSION),),
            )

    @staticmethod
    def _safe_state(state: dict[str, Any]) -> dict[str, Any]:
        """Return the persisted subset while retaining analyst/agent evidence."""
        keys = (
            "company_of_interest",
            "trade_date",
            "market_report",
            "sentiment_report",
            "news_report",
            "kap_report",
            "fundamentals_report",
            "investment_debate_state",
            "investment_plan",
            "trader_investment_plan",
            "risk_debate_state",
            "final_trade_decision",
        )
        return {key: state.get(key) for key in keys if key in state}

    def record_analysis(
        self,
        *,
        ticker: str,
        trade_date: str,
        final_decision: str,
        state: dict[str, Any],
        signal: str | None = None,
        entry_price: float | None = None,
        benchmark_ticker: str | None = None,
        benchmark_entry_price: float | None = None,
    ) -> int:
        """Insert or refresh one ticker/date analysis and return its stable id."""
        rating = parse_rating(final_decision)
        payload = json.dumps(
            self._safe_state(state),
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO analyses(
                    ticker, trade_date, created_at, rating, signal, entry_price,
                    benchmark_ticker, benchmark_entry_price, final_decision, state_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, trade_date) DO UPDATE SET
                    rating=excluded.rating,
                    signal=excluded.signal,
                    entry_price=COALESCE(analyses.entry_price, excluded.entry_price),
                    benchmark_ticker=COALESCE(
                        analyses.benchmark_ticker, excluded.benchmark_ticker
                    ),
                    benchmark_entry_price=COALESCE(
                        analyses.benchmark_entry_price, excluded.benchmark_entry_price
                    ),
                    final_decision=excluded.final_decision,
                    state_json=excluded.state_json
                """,
                (
                    ticker,
                    str(trade_date),
                    now,
                    rating,
                    signal,
                    entry_price,
                    benchmark_ticker,
                    benchmark_entry_price,
                    final_decision,
                    payload,
                ),
            )
            row = db.execute(
                "SELECT id FROM analyses WHERE ticker=? AND trade_date=?",
                (ticker, str(trade_date)),
            ).fetchone()
            return int(row["id"])

    def update_price_snapshots(
        self,
        analysis_id: int,
        *,
        entry_price: float | None = None,
        benchmark_ticker: str | None = None,
        benchmark_entry_price: float | None = None,
    ) -> None:
        """Fill missing stock/benchmark snapshots without changing a decision."""
        assignments: list[str] = []
        params: list[Any] = []
        if entry_price is not None:
            assignments.append("entry_price=COALESCE(entry_price, ?)")
            params.append(float(entry_price))
        if benchmark_ticker:
            assignments.append("benchmark_ticker=COALESCE(benchmark_ticker, ?)")
            params.append(str(benchmark_ticker))
        if benchmark_entry_price is not None:
            assignments.append(
                "benchmark_entry_price=COALESCE(benchmark_entry_price, ?)"
            )
            params.append(float(benchmark_entry_price))
        if not assignments:
            return
        params.append(int(analysis_id))
        with self._connect() as db:
            db.execute(
                f"UPDATE analyses SET {', '.join(assignments)} WHERE id=?",
                params,
            )

    def update_entry_price(self, analysis_id: int, entry_price: float) -> None:
        """Backwards-compatible helper for callers that only fill stock price."""
        self.update_price_snapshots(analysis_id, entry_price=entry_price)

    def record_performance(
        self,
        analysis_id: int,
        points: Iterable[PerformancePoint],
        *,
        measured_at: str | None = None,
    ) -> None:
        stamp = measured_at or datetime.now(timezone.utc).isoformat()
        rows = []
        for point in points:
            rows.append(
                (
                    analysis_id,
                    int(point.horizon_days),
                    stamp,
                    float(point.raw_return),
                    (
                        None
                        if point.benchmark_return is None
                        else float(point.benchmark_return)
                    ),
                    None if point.alpha_return is None else float(point.alpha_return),
                )
            )
        if not rows:
            return
        with self._connect() as db:
            db.executemany(
                """
                INSERT INTO performance(
                    analysis_id, horizon_days, measured_at, raw_return,
                    benchmark_return, alpha_return
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(analysis_id, horizon_days) DO UPDATE SET
                    measured_at=excluded.measured_at,
                    raw_return=excluded.raw_return,
                    benchmark_return=excluded.benchmark_return,
                    alpha_return=excluded.alpha_return
                """,
                rows,
            )

    def list_analyses(
        self,
        ticker: str | None = None,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        sql = "SELECT * FROM analyses"
        params: list[Any] = []
        if ticker:
            sql += " WHERE ticker=?"
            params.append(ticker)
        sql += " ORDER BY trade_date DESC, id DESC LIMIT ?"
        params.append(limit)
        with self._connect() as db:
            rows = db.execute(sql, params).fetchall()
            return [self._analysis_dict(db, row) for row in rows]

    def pending_analyses(
        self,
        horizons: Iterable[int],
        *,
        ticker: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return analyses missing a requested raw/benchmark/alpha horizon, oldest first."""
        horizon_values = tuple(
            sorted({int(value) for value in horizons if int(value) > 0})
        )
        if not horizon_values:
            return []

        limit = max(1, min(int(limit), 1000))
        placeholders = ",".join("?" for _ in horizon_values)
        where = ""
        params: list[Any] = list(horizon_values)
        if ticker:
            where = "WHERE a.ticker=?"
            params.append(ticker)
        required = len(horizon_values)
        params.extend([required, required, limit])

        sql = f"""
            SELECT a.id
            FROM analyses a
            LEFT JOIN performance p
              ON p.analysis_id=a.id
             AND p.horizon_days IN ({placeholders})
            {where}
            GROUP BY a.id
            HAVING COUNT(DISTINCT p.horizon_days) < ?
                OR COUNT(
                    DISTINCT CASE
                        WHEN p.benchmark_return IS NOT NULL
                         AND p.alpha_return IS NOT NULL
                        THEN p.horizon_days
                    END
                ) < ?
            ORDER BY a.trade_date ASC, a.id ASC
            LIMIT ?
        """
        with self._connect() as db:
            ids = db.execute(sql, params).fetchall()
            results = []
            for id_row in ids:
                row = db.execute(
                    "SELECT * FROM analyses WHERE id=?",
                    (id_row["id"],),
                ).fetchone()
                if row:
                    results.append(self._analysis_dict(db, row))
            return results

    def get_analysis(self, analysis_id: int) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM analyses WHERE id=?",
                (analysis_id,),
            ).fetchone()
            return self._analysis_dict(db, row) if row else None

    def compare_latest(
        self,
        ticker: str,
        *,
        count: int = 2,
    ) -> list[dict[str, Any]]:
        count = max(1, min(int(count), 1000))
        return self.list_analyses(ticker, limit=count)

    def performance_summary(self, ticker: str | None = None) -> dict[str, Any]:
        where = ""
        params: tuple[Any, ...] = ()
        if ticker:
            where = "WHERE a.ticker=?"
            params = (ticker,)
        with self._connect() as db:
            rows = db.execute(
                f"""
                SELECT p.horizon_days,
                       COUNT(*) AS samples,
                       AVG(p.raw_return) AS avg_raw_return,
                       AVG(p.benchmark_return) AS avg_benchmark_return,
                       AVG(p.alpha_return) AS avg_alpha_return,
                       AVG(CASE WHEN p.raw_return > 0 THEN 1.0 ELSE 0.0 END)
                           AS positive_rate,
                       AVG(
                           CASE
                               WHEN p.alpha_return IS NULL THEN NULL
                               WHEN p.alpha_return > 0 THEN 1.0
                               ELSE 0.0
                           END
                       ) AS alpha_positive_rate
                FROM performance p
                JOIN analyses a ON a.id=p.analysis_id
                {where}
                GROUP BY p.horizon_days
                ORDER BY p.horizon_days
                """,
                params,
            ).fetchall()
            return {
                "ticker": ticker,
                "horizons": [dict(row) for row in rows],
            }

    @staticmethod
    def _analysis_dict(
        db: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> dict[str, Any]:
        result = dict(row)
        result["state"] = json.loads(result.pop("state_json"))
        perf = db.execute(
            "SELECT horizon_days, measured_at, raw_return, benchmark_return, alpha_return "
            "FROM performance WHERE analysis_id=? ORDER BY horizon_days",
            (row["id"],),
        ).fetchall()
        result["performance"] = [dict(item) for item in perf]
        return result
