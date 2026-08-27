import sqlite3
from datetime import datetime, timezone

from tradingagents.service.jobs import AnalysisJobStore
from tradingagents.service.progress import ArvenJobProgressCallback


def _request():
    return {
        "ticker": "GARAN.IS",
        "trade_date": "2026-08-27",
        "estimated_cost_usd": 0.25,
    }


def test_legacy_job_db_gets_additive_progress_columns(tmp_path):
    path = tmp_path / "jobs.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE analysis_jobs (
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

    AnalysisJobStore(path)
    with sqlite3.connect(path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(analysis_jobs)")}
    assert {
        "current_agent",
        "progress_percent",
        "completed_agents_json",
        "heartbeat_at",
        "progress_at",
        "started_at",
        "deadline_at",
        "stale_after_at",
    } <= columns


def test_job_exposes_truthful_agent_progress(tmp_path):
    store = AnalysisJobStore(tmp_path / "jobs.db")
    job, created = store.create_or_get(_request())
    assert created is True
    assert store.claim(job["id"], timeout_seconds=900, stale_progress_seconds=300)

    assert store.update_progress(
        job["id"],
        current_agent="Haber Analisti",
        completed_agents=["Piyasa Analisti", "Duyarlılık Analisti"],
        progress_percent=22,
        stale_progress_seconds=300,
    )
    current = store.get(job["id"])
    assert current["status"] == "running"
    assert current["progress"]["current_agent"] == "Haber Analisti"
    assert current["progress"]["percent"] == 22
    assert current["progress"]["completed_agents"] == [
        "Piyasa Analisti",
        "Duyarlılık Analisti",
    ]
    states = {item["name"]: item["status"] for item in current["progress"]["agents"]}
    assert states["Piyasa Analisti"] == "completed"
    assert states["Duyarlılık Analisti"] == "completed"
    assert states["Haber Analisti"] == "running"
    assert current["progress"]["heartbeat_at"]
    assert current["progress"]["progress_at"]


def test_stale_progress_auto_fails_instead_of_staying_running(tmp_path):
    store = AnalysisJobStore(tmp_path / "jobs.db")
    job, _created = store.create_or_get(_request())
    assert store.claim(job["id"], timeout_seconds=900, stale_progress_seconds=300)

    past = "2000-01-01T00:00:00+00:00"
    future = "2999-01-01T00:00:00+00:00"
    with sqlite3.connect(store.path) as conn:
        conn.execute(
            "UPDATE analysis_jobs SET stale_after_at = ?, deadline_at = ? WHERE id = ?",
            (past, future, job["id"]),
        )

    expired = store.get(job["id"])
    assert expired["status"] == "failed"
    assert expired["error"] == {
        "type": "AnalysisStalled",
        "message": "Analiz ilerlemesi zaman aşımına uğradı.",
    }


def test_hard_deadline_auto_fails_even_with_recent_heartbeat(tmp_path):
    store = AnalysisJobStore(tmp_path / "jobs.db")
    job, _created = store.create_or_get(_request())
    assert store.claim(job["id"], timeout_seconds=900, stale_progress_seconds=300)

    now = datetime.now(timezone.utc).isoformat()
    past = "2000-01-01T00:00:00+00:00"
    future = "2999-01-01T00:00:00+00:00"
    with sqlite3.connect(store.path) as conn:
        conn.execute(
            """
            UPDATE analysis_jobs
            SET deadline_at = ?, stale_after_at = ?, heartbeat_at = ?
            WHERE id = ?
            """,
            (past, future, now, job["id"]),
        )

    expired = store.get(job["id"])
    assert expired["status"] == "failed"
    assert expired["error"]["type"] == "AnalysisTimeout"


def test_progress_callback_maps_real_langgraph_nodes_to_locked_arven_agents(tmp_path):
    store = AnalysisJobStore(tmp_path / "jobs.db")
    job, _created = store.create_or_get(_request())
    assert store.claim(job["id"], timeout_seconds=900, stale_progress_seconds=300)
    callback = ArvenJobProgressCallback(store, job["id"])

    callback.on_chain_start(
        {},
        {},
        run_id="market-run",
        metadata={"langgraph_node": "Market Analyst"},
    )
    assert store.get(job["id"])["progress"]["current_agent"] == "Piyasa Analisti"

    callback.on_chain_start(
        {},
        {},
        run_id="market-clear",
        metadata={"langgraph_node": "Msg Clear Market"},
    )
    after_market = store.get(job["id"])["progress"]
    assert "Piyasa Analisti" in after_market["completed_agents"]

    callback.on_chain_start(
        {},
        {},
        run_id="bull-run",
        metadata={"langgraph_node": "Bull Researcher"},
    )
    assert store.get(job["id"])["progress"]["current_agent"] == "Boğa Görüş Araştırmacısı"

    callback.on_chain_start(
        {},
        {},
        run_id="manager-run",
        metadata={"langgraph_node": "Research Manager"},
    )
    debate = store.get(job["id"])["progress"]["completed_agents"]
    assert "Boğa Görüş Araştırmacısı" in debate
    assert "Ayı Görüş Araştırmacısı" in debate

    callback.on_chain_start(
        {},
        {},
        run_id="trader-run",
        metadata={"langgraph_node": "Trader"},
    )
    assert store.get(job["id"])["progress"]["current_agent"] == "İşlem (Trader) Ajanı"

    callback.on_chain_start(
        {},
        {},
        run_id="risk-run",
        metadata={"langgraph_node": "Aggressive Analyst"},
    )
    risk = store.get(job["id"])["progress"]
    assert "İşlem (Trader) Ajanı" in risk["completed_agents"]
    assert risk["current_agent"] == "Risk Yöneticisi"


def test_terminal_write_cannot_be_overwritten_after_timeout(tmp_path):
    store = AnalysisJobStore(tmp_path / "jobs.db")
    job, _created = store.create_or_get(_request())
    assert store.claim(job["id"], timeout_seconds=900, stale_progress_seconds=300)
    with sqlite3.connect(store.path) as conn:
        conn.execute(
            "UPDATE analysis_jobs SET deadline_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", job["id"]),
        )

    assert store.get(job["id"])["status"] == "failed"
    store.finish_success(job["id"], {"decision": "late", "rating": "Buy"})
    final = store.get(job["id"])
    assert final["status"] == "failed"
    assert final["result"] is None
    assert final["error"]["type"] == "AnalysisTimeout"
