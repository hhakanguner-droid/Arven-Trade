"""Persistent job state for the ARVEN Trade web API."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_TERMINAL = {"succeeded", "failed"}
_ARVEN_AGENT_NAMES = (
    "Piyasa Analisti",
    "Duyarlılık Analisti",
    "Haber Analisti",
    "Temel Analist",
    "KAP Araştırmacısı",
    "Boğa Görüş Araştırmacısı",
    "Ayı Görüş Araştırmacısı",
    "Risk Yöneticisi",
    "İşlem (Trader) Ajanı",
)


class IdempotencyConflict(RuntimeError):
    """Raised when an idempotency key is reused for a different request."""


class QueueCapacityExceeded(RuntimeError):
    """Raised when the bounded pending-job queue is full."""


class AnalysisJobStore:
    """Small SQLite-backed queue/status store safe across API restarts."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @staticmethod
    def _now_dt() -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    def _now(cls) -> str:
        return cls._now_dt().isoformat()

    @staticmethod
    def _iso_after(now: datetime, seconds: int) -> str:
        return (now + timedelta(seconds=max(1, int(seconds)))).isoformat()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    @staticmethod
    def _ensure_columns(conn: sqlite3.Connection) -> None:
        """Apply additive progress columns to legacy Phase 13 job databases."""
        existing = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(analysis_jobs)").fetchall()
        }
        migrations = {
            "current_agent": "ALTER TABLE analysis_jobs ADD COLUMN current_agent TEXT",
            "progress_percent": (
                "ALTER TABLE analysis_jobs ADD COLUMN progress_percent INTEGER NOT NULL DEFAULT 0"
            ),
            "completed_agents_json": (
                "ALTER TABLE analysis_jobs ADD COLUMN completed_agents_json "
                "TEXT NOT NULL DEFAULT '[]'"
            ),
            "heartbeat_at": "ALTER TABLE analysis_jobs ADD COLUMN heartbeat_at TEXT",
            "progress_at": "ALTER TABLE analysis_jobs ADD COLUMN progress_at TEXT",
            "started_at": "ALTER TABLE analysis_jobs ADD COLUMN started_at TEXT",
            "deadline_at": "ALTER TABLE analysis_jobs ADD COLUMN deadline_at TEXT",
            "stale_after_at": "ALTER TABLE analysis_jobs ADD COLUMN stale_after_at TEXT",
        }
        for column, sql in migrations.items():
            if column not in existing:
                conn.execute(sql)

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
                    updated_at TEXT NOT NULL,
                    current_agent TEXT,
                    progress_percent INTEGER NOT NULL DEFAULT 0,
                    completed_agents_json TEXT NOT NULL DEFAULT '[]',
                    heartbeat_at TEXT,
                    progress_at TEXT,
                    started_at TEXT,
                    deadline_at TEXT,
                    stale_after_at TEXT
                )
                """
            )
            self._ensure_columns(conn)
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
    def _completed_agents(row: sqlite3.Row) -> list[str]:
        raw = row["completed_agents_json"]
        if not raw:
            return []
        try:
            value = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item) in _ARVEN_AGENT_NAMES]

    @classmethod
    def _progress_payload(cls, row: sqlite3.Row) -> dict[str, Any]:
        completed = cls._completed_agents(row)
        current = row["current_agent"]
        states = []
        for name in _ARVEN_AGENT_NAMES:
            if name in completed:
                state = "completed"
            elif current == name and row["status"] == "running":
                state = "running"
            else:
                state = "waiting"
            states.append({"name": name, "status": state})
        return {
            "current_agent": current,
            "percent": max(0, min(100, int(row["progress_percent"] or 0))),
            "completed_agents": completed,
            "heartbeat_at": row["heartbeat_at"],
            "progress_at": row["progress_at"],
            "started_at": row["started_at"],
            "deadline_at": row["deadline_at"],
            "stale_after_at": row["stale_after_at"],
            "agents": states,
        }

    @classmethod
    def _row(cls, row: sqlite3.Row | None) -> dict[str, Any] | None:
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
            "progress": cls._progress_payload(row),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create_or_get(
        self,
        request: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        max_pending_jobs: int = 100,
    ) -> tuple[dict[str, Any], bool]:
        """Atomically deduplicate and enqueue one request within a bounded queue."""
        request_hash = self._request_hash(request)
        job_id = uuid.uuid4().hex
        now = self._now()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if idempotency_key:
                existing = conn.execute(
                    "SELECT * FROM analysis_jobs WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if existing is not None:
                    if existing["request_hash"] != request_hash:
                        raise IdempotencyConflict(
                            "Idempotency-Key was already used for a different analysis request"
                        )
                    conn.commit()
                    return self._row(existing), False  # type: ignore[return-value]

            if max_pending_jobs > 0:
                pending = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM analysis_jobs "
                        "WHERE status IN ('queued', 'running')"
                    ).fetchone()[0]
                )
                if pending >= int(max_pending_jobs):
                    raise QueueCapacityExceeded(
                        f"ARVEN analysis queue is full ({pending}/{int(max_pending_jobs)})"
                    )

            conn.execute(
                """
                INSERT INTO analysis_jobs (
                    id, idempotency_key, request_hash, ticker, trade_date,
                    estimated_cost_usd, status, progress_percent,
                    completed_agents_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'queued', 0, '[]', ?, ?)
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
            created = conn.execute(
                "SELECT * FROM analysis_jobs WHERE id = ?", (job_id,)
            ).fetchone()
            conn.commit()
        return self._row(created), True  # type: ignore[return-value]

    def _expire_if_due(self, job_id: str) -> bool:
        """Fail a running job whose hard deadline or progress lease has expired."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status, deadline_at, stale_after_at FROM analysis_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if row is None or row["status"] != "running":
                return False

            now_dt = self._now_dt()
            deadline_raw = row["deadline_at"]
            stale_raw = row["stale_after_at"]

            def parse(value: str | None) -> datetime | None:
                if not value:
                    return None
                try:
                    parsed = datetime.fromisoformat(value)
                except ValueError:
                    return None
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)

            deadline = parse(deadline_raw)
            stale_after = parse(stale_raw)
            error_type = None
            message = None
            guard_column = None
            guard_value = None
            if deadline is not None and now_dt >= deadline:
                error_type = "AnalysisTimeout"
                message = "Analiz maksimum çalışma süresini aştı."
                guard_column = "deadline_at"
                guard_value = deadline_raw
            elif stale_after is not None and now_dt >= stale_after:
                error_type = "AnalysisStalled"
                message = "Analiz ilerlemesi zaman aşımına uğradı."
                guard_column = "stale_after_at"
                guard_value = stale_raw

            if error_type is None or guard_column is None:
                return False

            cursor = conn.execute(
                f"""
                UPDATE analysis_jobs
                SET status = 'failed', result_json = NULL, error_type = ?,
                    error_message = ?, current_agent = NULL, updated_at = ?
                WHERE id = ? AND status = 'running' AND {guard_column} = ?
                """,
                (error_type, message, self._now(), job_id, guard_value),
            )
            return cursor.rowcount == 1

    def get(self, job_id: str) -> dict[str, Any] | None:
        self._expire_if_due(job_id)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM analysis_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return self._row(row)

    def claim(
        self,
        job_id: str,
        *,
        timeout_seconds: int = 900,
        stale_progress_seconds: int = 300,
    ) -> bool:
        now_dt = self._now_dt()
        now = now_dt.isoformat()
        deadline = self._iso_after(now_dt, timeout_seconds)
        stale_after = self._iso_after(now_dt, stale_progress_seconds)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE analysis_jobs
                SET status = 'running', current_agent = 'Hazırlanıyor',
                    progress_percent = CASE WHEN progress_percent < 1 THEN 1 ELSE progress_percent END,
                    heartbeat_at = ?, progress_at = ?, started_at = COALESCE(started_at, ?),
                    deadline_at = ?, stale_after_at = ?, updated_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (now, now, now, deadline, stale_after, now, job_id),
            )
        return cursor.rowcount == 1

    def heartbeat(self, job_id: str) -> bool:
        """Record liveness without extending the progress-stall deadline."""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE analysis_jobs SET heartbeat_at = ? WHERE id = ? AND status = 'running'",
                (self._now(), job_id),
            )
        return cursor.rowcount == 1

    def update_progress(
        self,
        job_id: str,
        *,
        current_agent: str | None,
        completed_agents: list[str] | tuple[str, ...],
        progress_percent: int,
        stale_progress_seconds: int = 300,
    ) -> bool:
        """Persist truthful agent-stage progress and renew only the progress lease."""
        completed = []
        for name in completed_agents:
            name = str(name)
            if name in _ARVEN_AGENT_NAMES and name not in completed:
                completed.append(name)
        current = str(current_agent) if current_agent in _ARVEN_AGENT_NAMES else None
        percent = max(0, min(99, int(progress_percent)))
        now_dt = self._now_dt()
        now = now_dt.isoformat()
        stale_after = self._iso_after(now_dt, stale_progress_seconds)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE analysis_jobs
                SET current_agent = ?, completed_agents_json = ?, progress_percent = ?,
                    heartbeat_at = ?, progress_at = ?, stale_after_at = ?, updated_at = ?
                WHERE id = ? AND status = 'running'
                """,
                (
                    current,
                    json.dumps(completed, ensure_ascii=False),
                    percent,
                    now,
                    now,
                    stale_after,
                    now,
                    job_id,
                ),
            )
        return cursor.rowcount == 1

    def expire_due(self, job_id: str) -> bool:
        return self._expire_if_due(job_id)

    def finish_success(self, job_id: str, result: dict[str, Any]) -> None:
        payload = json.dumps(result, ensure_ascii=False, sort_keys=True)
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE analysis_jobs
                SET status = 'succeeded', result_json = ?, error_type = NULL,
                    error_message = NULL, current_agent = NULL, progress_percent = 100,
                    completed_agents_json = ?, heartbeat_at = ?, progress_at = ?,
                    stale_after_at = NULL, updated_at = ?
                WHERE id = ? AND status = 'running'
                """,
                (
                    payload,
                    json.dumps(list(_ARVEN_AGENT_NAMES), ensure_ascii=False),
                    now,
                    now,
                    now,
                    job_id,
                ),
            )

    def finish_failure(self, job_id: str, error_type: str, message: str) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE analysis_jobs
                SET status = 'failed', result_json = NULL, error_type = ?,
                    error_message = ?, current_agent = NULL, heartbeat_at = ?,
                    stale_after_at = NULL, updated_at = ?
                WHERE id = ? AND status = 'running'
                """,
                (error_type[:120], message[:1000], now, now, job_id),
            )

    def recover_incomplete(self) -> list[str]:
        """Requeue interrupted work and return all queued job ids oldest first."""
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE analysis_jobs
                SET status = 'queued', current_agent = NULL, progress_percent = 0,
                    completed_agents_json = '[]', heartbeat_at = NULL, progress_at = NULL,
                    started_at = NULL, deadline_at = NULL, stale_after_at = NULL,
                    updated_at = ?
                WHERE status = 'running'
                """,
                (now,),
            )
            rows = conn.execute(
                "SELECT id FROM analysis_jobs WHERE status = 'queued' ORDER BY created_at"
            ).fetchall()
        return [str(row["id"]) for row in rows]

    def prune_terminal(self, *, max_terminal_jobs: int = 5000) -> int:
        """Keep only the newest bounded set of succeeded/failed job records."""
        if max_terminal_jobs <= 0:
            return 0
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id FROM analysis_jobs
                WHERE status IN ('succeeded', 'failed')
                ORDER BY updated_at DESC, id DESC
                LIMIT -1 OFFSET ?
                """,
                (int(max_terminal_jobs),),
            ).fetchall()
            ids = [str(row["id"]) for row in rows]
            if ids:
                conn.executemany(
                    "DELETE FROM analysis_jobs WHERE id = ?",
                    [(job_id,) for job_id in ids],
                )
        return len(ids)

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
