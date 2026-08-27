"""Asynchronous analysis orchestration for HTTP consumers."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any

from tradingagents.agents.utils.rating import parse_rating
from tradingagents.operations.security import redact_sensitive_text

from .jobs import AnalysisJobStore
from .presentation import history_card, history_detail
from .progress import ArvenJobProgressCallback


class HistoryUnavailable(RuntimeError):
    """Raised when the optional Phase 11 history store is unavailable."""


class AnalysisService:
    """Queue guarded graph runs without holding an HTTP connection open."""

    def __init__(
        self,
        runtime: Any,
        store: AnalysisJobStore,
        *,
        history_store: Any | None = None,
        max_workers: int = 1,
        max_pending_jobs: int = 100,
        max_terminal_jobs: int = 5000,
        recover_incomplete: bool = True,
        analysis_timeout_seconds: int = 900,
        stale_progress_seconds: int = 300,
        heartbeat_interval_seconds: int = 15,
    ):
        self.runtime = runtime
        self.store = store
        self.history_store = history_store
        self.max_pending_jobs = max(1, int(max_pending_jobs))
        self.max_terminal_jobs = max(1, int(max_terminal_jobs))
        self.analysis_timeout_seconds = max(1, int(analysis_timeout_seconds))
        self.stale_progress_seconds = max(1, int(stale_progress_seconds))
        self.heartbeat_interval_seconds = max(1, int(heartbeat_interval_seconds))
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, int(max_workers)),
            thread_name_prefix="arven-analysis",
        )
        self._progress_callback_lock = threading.Lock()
        self.store.prune_terminal(max_terminal_jobs=self.max_terminal_jobs)
        if recover_incomplete:
            for job_id in self.store.recover_incomplete():
                self._schedule(job_id)

    def _schedule(self, job_id: str) -> None:
        self._executor.submit(self._execute, job_id)

    def submit(
        self,
        ticker: str,
        trade_date: str,
        *,
        estimated_cost_usd: float | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        request = {
            "ticker": ticker,
            "trade_date": trade_date,
            "estimated_cost_usd": estimated_cost_usd,
        }
        job, created = self.store.create_or_get(
            request,
            idempotency_key=idempotency_key,
            max_pending_jobs=self.max_pending_jobs,
        )
        # Existing idempotent replays must not enqueue duplicate executor tasks.
        # A queued row created before a process crash is scheduled by startup recovery.
        if created:
            self._schedule(str(job["id"]))
        return job

    @staticmethod
    def _result_payload(result: Any) -> dict[str, Any]:
        """Preserve the PM decision while deriving its deterministic 5-tier rating."""
        decision = None
        rating_hint = None
        if isinstance(result, tuple) and len(result) >= 2:
            state, rating_hint = result[0], result[1]
            if isinstance(state, dict):
                decision = state.get("final_trade_decision")
            if decision is None:
                decision = rating_hint
        elif isinstance(result, dict) and "final_trade_decision" in result:
            decision = result["final_trade_decision"]
        else:
            decision = result

        decision_text = "" if decision is None else str(decision)
        rating_source = decision_text or ("" if rating_hint is None else str(rating_hint))
        return {
            "decision": decision_text,
            "rating": parse_rating(rating_source),
        }

    @contextmanager
    def _job_progress_callback(self, callback: ArvenJobProgressCallback):
        """Install a per-job graph callback only while the serialized runtime is active."""
        graph = getattr(self.runtime, "graph", None)
        propagator = getattr(graph, "propagator", None)
        if propagator is None or not hasattr(propagator, "callbacks"):
            yield
            return

        # ProductionRuntime already serializes graph runs. This lock additionally
        # prevents callback replacement when a custom service uses >1 executor worker.
        with self._progress_callback_lock:
            previous = list(getattr(propagator, "callbacks", []) or [])
            propagator.callbacks = [*previous, callback]
            try:
                yield
            finally:
                propagator.callbacks = previous

    def _watch_running_job(self, job_id: str, stop: threading.Event) -> None:
        """Heartbeat active execution and independently enforce progress/deadline guards."""
        while not stop.wait(self.heartbeat_interval_seconds):
            if self.store.expire_due(job_id):
                return
            if not self.store.heartbeat(job_id):
                return

    def _execute(self, job_id: str) -> None:
        if not self.store.claim(
            job_id,
            timeout_seconds=self.analysis_timeout_seconds,
            stale_progress_seconds=self.stale_progress_seconds,
        ):
            return
        job = self.store.get(job_id)
        if job is None:
            return

        stop_watchdog = threading.Event()
        watchdog = threading.Thread(
            target=self._watch_running_job,
            args=(job_id, stop_watchdog),
            name=f"arven-watchdog-{job_id[:8]}",
            daemon=True,
        )
        watchdog.start()

        progress = ArvenJobProgressCallback(
            self.store,
            job_id,
            stale_progress_seconds=self.stale_progress_seconds,
        )
        try:
            with self._job_progress_callback(progress):
                result = self.runtime.propagate(
                    job["ticker"],
                    job["trade_date"],
                    estimated_cost_usd=job["estimated_cost_usd"],
                )
        except Exception as exc:
            self.store.finish_failure(
                job_id,
                type(exc).__name__,
                redact_sensitive_text(exc),
            )
        else:
            self.store.finish_success(job_id, self._result_payload(result))
        finally:
            stop_watchdog.set()
            watchdog.join(timeout=max(1, self.heartbeat_interval_seconds + 1))
            self.store.prune_terminal(max_terminal_jobs=self.max_terminal_jobs)

    def get(self, job_id: str) -> dict[str, Any] | None:
        return self.store.get(job_id)

    def _history(self):
        if self.history_store is None:
            raise HistoryUnavailable("analysis history is unavailable")
        return self.history_store

    def list_history(self, ticker: str | None = None, *, limit: int = 50) -> list[dict[str, Any]]:
        records = self._history().list_analyses(ticker, limit=limit)
        return [history_card(record) for record in records]

    def get_history(self, analysis_id: int) -> dict[str, Any] | None:
        record = self._history().get_analysis(int(analysis_id))
        return history_detail(record) if record else None

    def compare_history(self, ticker: str, *, count: int = 2) -> list[dict[str, Any]]:
        records = self._history().compare_latest(ticker, count=count)
        return [history_card(record) for record in records]

    def performance_summary(self, ticker: str | None = None) -> dict[str, Any]:
        return self._history().performance_summary(ticker)

    def health(self) -> dict[str, Any]:
        runtime_health = self.runtime.health() if hasattr(self.runtime, "health") else {}
        return {
            "status": "ok",
            "runtime": runtime_health,
            "history": {"available": self.history_store is not None},
            "jobs": {
                **self.store.counts(),
                "max_pending": self.max_pending_jobs,
                "max_terminal": self.max_terminal_jobs,
            },
            "analysis_guard": {
                "timeout_seconds": self.analysis_timeout_seconds,
                "stale_progress_seconds": self.stale_progress_seconds,
                "heartbeat_interval_seconds": self.heartbeat_interval_seconds,
            },
        }

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=False)
