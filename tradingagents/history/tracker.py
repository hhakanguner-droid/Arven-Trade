"""Runtime integration for Phase 11 analysis history and performance tracking.

The tracker is deliberately additive and fail-open: a history/database/market-data
problem must never make the core TradingAgents analysis fail.  The final
Portfolio Manager node is wrapped so both normal ``invoke`` runs and the
interactive streaming CLI persist the exact same completed state.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import yfinance as yf

from tradingagents.agents.utils.rating import parse_rating
from tradingagents.dataflows.symbol_utils import normalize_symbol

from .store import AnalysisHistoryStore, PerformancePoint

logger = logging.getLogger(__name__)

DEFAULT_HORIZONS = (1, 5, 20)
HistoryLoader = Callable[[str, date, date], Sequence[tuple[date, float]]]


class AnalysisHistoryTracker:
    """Record completed analyses and opportunistically resolve realized returns."""

    def __init__(
        self,
        config: dict[str, Any],
        *,
        store: AnalysisHistoryStore | None = None,
        history_loader: HistoryLoader | None = None,
    ):
        self.config = config
        self.enabled = bool(config.get("analysis_history_enabled", True))
        configured_horizons = config.get("analysis_history_horizons", DEFAULT_HORIZONS)
        self.horizons = tuple(
            sorted({int(value) for value in configured_horizons if int(value) > 0})
        )
        if not self.horizons:
            self.horizons = DEFAULT_HORIZONS
        self.resolve_limit = max(1, int(config.get("analysis_history_resolve_limit", 10)))
        self.history_loader = history_loader or self._default_history_loader

        if not self.enabled:
            self.store = store
            return

        path = config.get("analysis_history_path") or (
            Path.home() / ".tradingagents" / "history" / "analysis_history.db"
        )
        try:
            self.store = store or AnalysisHistoryStore(path)
        except Exception as exc:
            # History is an additive feature. A read-only home directory or a
            # damaged SQLite file must not prevent the trading graph from starting.
            logger.warning("Analysis history disabled because the store could not open: %s", exc)
            self.enabled = False
            self.store = store

    def wrap_final_node(self, node):
        """Wrap the final graph node without changing its returned state delta.

        ``GraphSetup`` installs this around Portfolio Manager.  Because both the
        programmatic graph and the interactive CLI traverse that same final node,
        persistence cannot silently diverge between entry points.
        """
        if not self.enabled:
            return node

        @wraps(node)
        def wrapped(state):
            result = node(state)
            if not isinstance(result, dict):
                return result

            merged = dict(state) if isinstance(state, dict) else {}
            merged.update(result)
            ticker = str(merged.get("company_of_interest") or "").strip()

            # Persist the just-completed decision before any older backfill work.
            # This keeps the new analysis durable even if a market-data call stalls
            # or the process is interrupted during opportunistic backfill.
            analysis_id = self.record_completed(merged)
            if ticker:
                self.resolve_pending(ticker, exclude_analysis_id=analysis_id)
            return result

        return wrapped

    # Public query surface for future API/PWA callers.
    def list_analyses(self, ticker: str | None = None, *, limit: int = 50):
        if not self.enabled or self.store is None:
            return []
        return self.store.list_analyses(ticker, limit=limit)

    def compare_latest(self, ticker: str, *, count: int = 2):
        if not self.enabled or self.store is None:
            return []
        return self.store.compare_latest(ticker, count=count)

    def performance_summary(self, ticker: str | None = None):
        if not self.enabled or self.store is None:
            return {"ticker": ticker, "horizons": []}
        return self.store.performance_summary(ticker)

    def record_completed(self, final_state: dict[str, Any]) -> int | None:
        """Persist one completed graph state; failures never break the analysis run."""
        if not self.enabled or self.store is None:
            return None

        ticker = str(final_state.get("company_of_interest") or "").strip()
        trade_date = str(final_state.get("trade_date") or "").strip()
        decision = str(final_state.get("final_trade_decision") or "").strip()
        if not ticker or not trade_date or not decision:
            return None

        signal = parse_rating(decision)
        benchmark_ticker = self._resolve_benchmark(ticker)
        try:
            # Persist the decision first. Market data is allowed to be unavailable
            # or temporarily broken without losing the analysis itself.
            analysis_id = self.store.record_analysis(
                ticker=ticker,
                trade_date=trade_date,
                final_decision=decision,
                state=final_state,
                signal=signal,
                entry_price=None,
                benchmark_ticker=benchmark_ticker,
                benchmark_entry_price=None,
            )
        except Exception as exc:
            logger.warning(
                "Could not persist analysis history for %s on %s: %s",
                ticker,
                trade_date,
                exc,
            )
            return None

        try:
            entry_price, benchmark_entry_price, points = self._resolve_prices(
                ticker,
                trade_date,
                self.horizons,
                benchmark_ticker=benchmark_ticker,
            )
            self.store.update_price_snapshots(
                analysis_id,
                entry_price=entry_price,
                benchmark_ticker=benchmark_ticker,
                benchmark_entry_price=benchmark_entry_price,
            )
            if points:
                self.store.record_performance(analysis_id, points)
        except Exception as exc:
            logger.warning(
                "Analysis history saved for %s on %s, but price/performance resolution failed: %s",
                ticker,
                trade_date,
                exc,
            )
        return analysis_id

    def resolve_pending(
        self,
        ticker: str | None = None,
        *,
        exclude_analysis_id: int | None = None,
    ) -> int:
        """Fill missing 1/5/20-session outcomes, oldest pending analyses first.

        Pending rows are grouped by stock and the benchmark identity captured at
        analysis time. One stock fetch and one benchmark fetch are reused inside
        each group. Stored entry snapshots are used as return denominators so an
        intraday analysis cannot later drift to the session's final close.
        """
        if not self.enabled or self.store is None:
            return 0

        fetch_limit = self.resolve_limit + (1 if exclude_analysis_id is not None else 0)
        try:
            pending = self.store.pending_analyses(
                self.horizons,
                ticker=ticker,
                limit=fetch_limit,
            )
        except Exception as exc:
            logger.warning("Could not read pending analysis history: %s", exc)
            return 0

        if exclude_analysis_id is not None:
            excluded = int(exclude_analysis_id)
            pending = [row for row in pending if int(row.get("id", -1)) != excluded]
        pending = pending[: self.resolve_limit]
        if not pending:
            return 0

        updated = 0
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in pending:
            group_ticker = str(row["ticker"])
            benchmark = str(
                row.get("benchmark_ticker") or self._resolve_benchmark(group_ticker)
            )
            groups.setdefault((group_ticker, benchmark), []).append(row)

        for (group_ticker, benchmark), rows in groups.items():
            try:
                trade_days = [self._parse_trade_day(row["trade_date"]) for row in rows]
                start = min(trade_days) - timedelta(days=10)
                # Asking through today is enough: future dates simply have no bars yet.
                end = max(date.today(), max(trade_days)) + timedelta(days=1)
                stock_series = self._load_series(normalize_symbol(group_ticker), start, end)

                benchmark_series: list[tuple[date, float]] = []
                try:
                    benchmark_series = self._load_series(benchmark, start, end)
                except Exception as exc:
                    logger.warning("Benchmark history unavailable for %s: %s", benchmark, exc)

                for row in rows:
                    completed = {
                        int(item["horizon_days"])
                        for item in row.get("performance", [])
                        if item.get("benchmark_return") is not None
                        and item.get("alpha_return") is not None
                    }
                    missing = tuple(h for h in self.horizons if h not in completed)
                    if not missing:
                        continue
                    entry_price, benchmark_entry_price, points = self._points_from_series(
                        row["trade_date"],
                        missing,
                        stock_series,
                        benchmark_series,
                        entry_price_override=row.get("entry_price"),
                        benchmark_entry_price_override=row.get("benchmark_entry_price"),
                    )
                    self.store.update_price_snapshots(
                        row["id"],
                        entry_price=entry_price,
                        benchmark_ticker=benchmark,
                        benchmark_entry_price=benchmark_entry_price,
                    )
                    if points:
                        self.store.record_performance(row["id"], points)
                        updated += len(points)
            except Exception as exc:
                logger.warning(
                    "Could not resolve history performance for %s vs %s: %s",
                    group_ticker,
                    benchmark,
                    exc,
                )
        return updated

    def _resolve_prices(
        self,
        ticker: str,
        trade_date: str,
        horizons: Iterable[int],
        *,
        benchmark_ticker: str | None = None,
        entry_price_override: float | None = None,
        benchmark_entry_price_override: float | None = None,
    ) -> tuple[float | None, float | None, list[PerformancePoint]]:
        trade_day = self._parse_trade_day(trade_date)
        horizon_values = tuple(sorted({int(value) for value in horizons if int(value) > 0}))
        max_horizon = max(horizon_values, default=0)

        # Look backwards so weekend/holiday analyses anchor to the last known
        # close, never to a future session.  The forward buffer is intentionally
        # generous for exchange holidays.
        start = trade_day - timedelta(days=10)
        end = trade_day + timedelta(days=max(14, max_horizon * 3 + 14))
        stock_series = self._load_series(normalize_symbol(ticker), start, end)

        benchmark_series: list[tuple[date, float]] = []
        benchmark = benchmark_ticker or self._resolve_benchmark(ticker)
        try:
            benchmark_series = self._load_series(benchmark, start, end)
        except Exception as exc:
            logger.warning("Benchmark history unavailable for %s: %s", benchmark, exc)

        return self._points_from_series(
            trade_date,
            horizon_values,
            stock_series,
            benchmark_series,
            entry_price_override=entry_price_override,
            benchmark_entry_price_override=benchmark_entry_price_override,
        )

    def _points_from_series(
        self,
        trade_date: str,
        horizons: Iterable[int],
        stock_series: Sequence[tuple[date, float]],
        benchmark_series: Sequence[tuple[date, float]],
        *,
        entry_price_override: float | None = None,
        benchmark_entry_price_override: float | None = None,
    ) -> tuple[float | None, float | None, list[PerformancePoint]]:
        trade_day = self._parse_trade_day(trade_date)
        horizon_values = tuple(sorted({int(value) for value in horizons if int(value) > 0}))
        stock_base = self._baseline_index(stock_series, trade_day)
        if stock_base is None:
            return None, None, []

        observed_entry = stock_series[stock_base][1]
        entry_price = self._positive_override(entry_price_override, observed_entry)
        benchmark_base = self._baseline_index(benchmark_series, trade_day)
        observed_benchmark_entry = (
            benchmark_series[benchmark_base][1] if benchmark_base is not None else None
        )
        benchmark_entry_price = self._positive_override(
            benchmark_entry_price_override,
            observed_benchmark_entry,
        )
        benchmark_by_day = dict(benchmark_series)

        points: list[PerformancePoint] = []
        for horizon in horizon_values:
            stock_target = stock_base + horizon
            if stock_target >= len(stock_series):
                continue

            target_day, target_close = stock_series[stock_target]
            raw_return = target_close / entry_price - 1.0
            benchmark_return = None
            if benchmark_entry_price is not None:
                benchmark_target_close = benchmark_by_day.get(target_day)
                if benchmark_target_close is not None:
                    benchmark_return = benchmark_target_close / benchmark_entry_price - 1.0

            points.append(
                PerformancePoint(
                    horizon_days=horizon,
                    raw_return=raw_return,
                    benchmark_return=benchmark_return,
                )
            )

        return entry_price, benchmark_entry_price, points

    def _load_series(self, symbol: str, start: date, end: date) -> list[tuple[date, float]]:
        return self._normalize_series(list(self.history_loader(symbol, start, end)))

    def _resolve_benchmark(self, ticker: str) -> str:
        explicit = self.config.get("benchmark_ticker")
        if explicit:
            return str(explicit)
        benchmark_map = self.config.get("benchmark_map", {})
        ticker_upper = ticker.upper()
        for suffix, benchmark in benchmark_map.items():
            if suffix and ticker_upper.endswith(str(suffix).upper()):
                return str(benchmark)
        return str(benchmark_map.get("", "SPY"))

    @staticmethod
    def _positive_override(value: float | None, fallback: float | None) -> float | None:
        if value is not None:
            numeric = float(value)
            if numeric > 0:
                return numeric
        if fallback is None:
            return None
        numeric = float(fallback)
        return numeric if numeric > 0 else None

    @staticmethod
    def _parse_trade_day(value: str) -> date:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()

    @staticmethod
    def _normalize_series(
        values: Sequence[tuple[date, float]],
    ) -> list[tuple[date, float]]:
        by_day: dict[date, float] = {}
        for raw_day, raw_close in values:
            if isinstance(raw_day, datetime):
                day = raw_day.date()
            elif isinstance(raw_day, date):
                day = raw_day
            else:
                day = datetime.fromisoformat(str(raw_day)[:10]).date()
            close = float(raw_close)
            if close > 0:
                by_day[day] = close
        return sorted(by_day.items(), key=lambda item: item[0])

    @staticmethod
    def _baseline_index(series: Sequence[tuple[date, float]], trade_day: date) -> int | None:
        candidate = None
        for index, (session_day, _close) in enumerate(series):
            if session_day <= trade_day:
                candidate = index
            else:
                break
        return candidate

    @staticmethod
    def _default_history_loader(
        symbol: str,
        start: date,
        end: date,
    ) -> Sequence[tuple[date, float]]:
        frame = yf.Ticker(symbol).history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
        )
        if frame is None or frame.empty or "Close" not in frame:
            return []

        rows: list[tuple[date, float]] = []
        for index, value in frame["Close"].dropna().items():
            session_day = (
                index.date() if hasattr(index, "date") else date.fromisoformat(str(index)[:10])
            )
            rows.append((session_day, float(value)))
        return rows
