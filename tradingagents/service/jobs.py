"""Persistent job state for the ARVEN Trade web API."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_TERMINAL = {"succeeded", "failed"}


class IdempotencyConflict(RuntimeError):
    """Raised when an idempotency key is reused for a different request."""


class AnalysisJobStore:
    """Small SQLite-backed queue/status store safe across API restarts."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_jobs (
                    id TEXT PRIMARY KEY,
                    idempotency_key TEXT UNIQUE,
                    request_hash TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    estimated_cost_usd REAL,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    error_type TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_analysis_jobs_status_created "
                "ON analysis_jobs(status, created_at)"
            )

    @staticmethod
    def _request_hash(request: dict[str, Any]) -> str:
        encoded = json.dumps(
            request,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = json.loads(row["result_json"]) if row["result_json"] else None
        error = None
        if row["error_type"] or row["error_message"]:
            error = {
                "type": row["error_type"] or "AnalysisError",
                "message": row["error_message"] or "Analysis failed",
            }
        return {
            "id": row["id"],
            "idempotency_key": row["idempotency_key"],
            "ticker": row["ticker"],
            "trade_date": row["trade_date"],
            "estimated_cost_usd": row["estimated_cost_usd"],
            "status": row["status"],
            "result": result,
            "error": error,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create_or_get(
        self,
        request: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        request_hash = self._request_hash(request)
        job_id = uuid.uuid4().hex
        now = self._now()
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO analysis_jobs (
                        id, idempotency_key, request_hash, ticker, trade_date,
                        estimated_cost_usd, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?)
                    """,
                    (
                        job_id,
                        idempotency_key,
                        request_hash,
                        request["ticker"],
                        request["trade_date"],
                        request.get("estimated_cost_usd"),
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError:
                if not idempotency_key:
                    raise
                existing = conn.execute(
                    "SELECT * FROM analysis_jobs WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if existing is None:
                    raise
                if existing["request_hash"] != request_hash:
                    raise IdempotencyConflict(
                        "Idempotency-Key was already used for a different analysis request"
                    ) from None
                return self._row(existing), False  # type: ignore[return-value]
            created = conn.execute(
                "SELECT * FROM analysis_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return self._row(created), True  # type: ignore[return-value]

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM analysis_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return self._row(row)

    def claim(self, job_id: str) -> bool:
        now = self._now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE analysis_jobs
                SET status = 'running', updated_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (now, job_id),
            )
        return cursor.rowcount == 1

    def finish_success(self, job_id: str, result: dict[str, Any]) -> None:
        payload = json.dumps(result, ensure_ascii=False, sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE analysis_jobs
                SET status = 'succeeded', result_json = ?, error_type = NULL,
                    error_message = NULL, updated_at = ?
                WHERE id = ? AND status = 'running'
                """,
                (payload, self._now(), job_id),
            )

    def finish_failure(self, job_id: str, error_type: str, message: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE analysis_jobs
                SET status = 'failed', result_json = NULL, error_type = ?,
                    error_message = ?, updated_at = ?
                WHERE id = ? AND status = 'running'
                """,
                (error_type[:120], message[:1000], self._now(), job_id),
            )

    def recover_incomplete(self) -> list[str]:
        """Requeue interrupted work and return all queued job ids oldest first."""
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE analysis_jobs SET status = 'queued', updated_at = ? "
                "WHERE status = 'running'",
                (now,),
            )
            rows = conn.execute(
                "SELECT id FROM analysis_jobs WHERE status = 'queued' ORDER BY created_at"
            ).fetchall()
        return [str(row["id"]) for row in rows]

    def counts(self) -> dict[str, int]:
        values = {"queued": 0, "running": 0, "succeeded": 0, "failed": 0}
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS count FROM analysis_jobs GROUP BY status"
            ).fetchall()
        for row in rows:
            status = str(row["status"])
            if status in values:
                values[status] = int(row["count"])
        return values

    @staticmethod
    def is_terminal(job: dict[str, Any]) -> bool:
        return str(job.get("status")) in _TERMINAL
