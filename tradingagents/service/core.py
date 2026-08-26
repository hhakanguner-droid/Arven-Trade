"""Asynchronous analysis orchestration for HTTP consumers."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from tradingagents.agents.utils.rating import parse_rating
from tradingagents.operations.security import redact_sensitive_text

from .jobs import AnalysisJobStore


class AnalysisService:
    """Queue guarded graph runs without holding an HTTP connection open."""

    def __init__(
        self,
        runtime: Any,
        store: AnalysisJobStore,
        *,
        max_workers: int = 1,
        recover_incomplete: bool = True,
    ):
        self.runtime = runtime
        self.store = store
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, int(max_workers)),
            thread_name_prefix="arven-analysis",
        )
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
        )
        if created or job["status"] == "queued":
            self._schedule(str(job["id"]))
        return job

    @staticmethod
    def _result_payload(result: Any) -> dict[str, Any]:
        if isinstance(result, tuple) and len(result) >= 2:
            decision = result[1]
        elif isinstance(result, dict) and "final_trade_decision" in result:
            decision = result["final_trade_decision"]
        else:
            decision = result
        decision_text = "" if decision is None else str(decision)
        return {
            "decision": decision_text,
            "rating": parse_rating(decision_text),
        }

    def _execute(self, job_id: str) -> None:
        if not self.store.claim(job_id):
            return
        job = self.store.get(job_id)
        if job is None:
            return
        try:
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
            return
        self.store.finish_success(job_id, self._result_payload(result))

    def get(self, job_id: str) -> dict[str, Any] | None:
        return self.store.get(job_id)

    def health(self) -> dict[str, Any]:
        runtime_health = self.runtime.health() if hasattr(self.runtime, "health") else {}
        return {
            "status": "ok",
            "runtime": runtime_health,
            "jobs": self.store.counts(),
        }

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=False)
