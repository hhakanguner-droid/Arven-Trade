import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from tradingagents.service.api import create_app
from tradingagents.service.core import AnalysisService
from tradingagents.service.jobs import AnalysisJobStore


class _Runtime:
    def __init__(self, *, error=None):
        self.error = error
        self.calls = []

    def health(self):
        return {"credential": {"credential_status": "configured"}}

    def propagate(self, ticker, trade_date, asset_type="stock", *, estimated_cost_usd=None):
        self.calls.append((ticker, trade_date, asset_type, estimated_cost_usd))
        if self.error:
            raise self.error
        return ({"company_of_interest": ticker}, "Rating: Buy. Görünüm pozitif.")


class _BlockingRuntime(_Runtime):
    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def propagate(self, ticker, trade_date, asset_type="stock", *, estimated_cost_usd=None):
        self.calls.append((ticker, trade_date, asset_type, estimated_cost_usd))
        self.started.set()
        if not self.release.wait(timeout=5):
            raise RuntimeError("test worker timed out")
        return ({"company_of_interest": ticker}, "Rating: Hold")


def _client(
    tmp_path,
    runtime=None,
    *,
    token=None,
    auth_disabled=True,
    max_pending_jobs=100,
    max_terminal_jobs=5000,
):
    runtime = runtime or _Runtime()
    service = AnalysisService(
        runtime,
        AnalysisJobStore(tmp_path / "jobs.db"),
        max_pending_jobs=max_pending_jobs,
        max_terminal_jobs=max_terminal_jobs,
        recover_incomplete=False,
    )
    app = create_app(
        service,
        api_token=token,
        auth_disabled=auth_disabled,
    )
    return TestClient(app), service, runtime


def _wait_for_terminal(client, job_id, headers=None):
    for _ in range(100):
        response = client.get(f"/api/v1/analyses/{job_id}", headers=headers or {})
        assert response.status_code == 200
        job = response.json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.01)
    raise AssertionError("analysis job did not finish")


def test_public_liveness_is_minimal(tmp_path):
    client, service, _runtime = _client(tmp_path)
    try:
        assert client.get("/healthz").json() == {"status": "ok"}
    finally:
        service.close()


def test_api_auth_fails_closed_for_bad_token(tmp_path):
    token = "phase13-test-token-0123456789abcdef"
    client, service, _runtime = _client(
        tmp_path,
        token=token,
        auth_disabled=False,
    )
    try:
        assert client.get("/api/v1/health").status_code == 401
        response = client.get(
            "/api/v1/health",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
    finally:
        service.close()


def test_api_rejects_short_production_token(tmp_path):
    service = AnalysisService(
        _Runtime(),
        AnalysisJobStore(tmp_path / "jobs.db"),
        recover_incomplete=False,
    )
    try:
        with pytest.raises(RuntimeError, match="at least 32"):
            create_app(service, api_token="too-short", auth_disabled=False)
    finally:
        service.close()


def test_submit_normalizes_bist_ticker_and_finishes_async(tmp_path):
    client, service, runtime = _client(tmp_path)
    try:
        response = client.post(
            "/api/v1/analyses",
            json={"ticker": "thyao", "trade_date": "2026-08-26"},
        )
        assert response.status_code == 202
        job = _wait_for_terminal(client, response.json()["id"])
        assert job["status"] == "succeeded"
        assert job["ticker"] == "THYAO.IS"
        assert job["result"]["rating"] == "Buy"
        assert runtime.calls[0][0] == "THYAO.IS"
    finally:
        service.close()


def test_rejects_non_bist_suffix(tmp_path):
    client, service, _runtime = _client(tmp_path)
    try:
        response = client.post(
            "/api/v1/analyses",
            json={"ticker": "AAPL.US", "trade_date": "2026-08-26"},
        )
        assert response.status_code == 422
    finally:
        service.close()


def test_rejects_future_trade_date(tmp_path):
    client, service, _runtime = _client(tmp_path)
    tomorrow = datetime.now(ZoneInfo("Europe/Istanbul")).date() + timedelta(days=1)
    try:
        response = client.post(
            "/api/v1/analyses",
            json={"ticker": "ASELS", "trade_date": tomorrow.isoformat()},
        )
        assert response.status_code == 422
    finally:
        service.close()


def test_idempotency_reuses_same_job_and_rejects_payload_change(tmp_path):
    client, service, _runtime = _client(tmp_path)
    headers = {"Idempotency-Key": "same-analysis"}
    request = {"ticker": "THYAO", "trade_date": "2026-08-26"}
    try:
        first = client.post("/api/v1/analyses", json=request, headers=headers)
        second = client.post("/api/v1/analyses", json=request, headers=headers)
        assert first.status_code == second.status_code == 202
        assert first.json()["id"] == second.json()["id"]

        conflict = client.post(
            "/api/v1/analyses",
            json={"ticker": "ASELS", "trade_date": "2026-08-26"},
            headers=headers,
        )
        assert conflict.status_code == 409
    finally:
        service.close()


def test_pending_queue_is_bounded_and_returns_429(tmp_path):
    runtime = _BlockingRuntime()
    client, service, _runtime = _client(
        tmp_path,
        runtime,
        max_pending_jobs=1,
    )
    try:
        first = client.post(
            "/api/v1/analyses",
            json={"ticker": "THYAO", "trade_date": "2026-08-26"},
        )
        assert first.status_code == 202
        assert runtime.started.wait(timeout=1)

        second = client.post(
            "/api/v1/analyses",
            json={"ticker": "ASELS", "trade_date": "2026-08-26"},
        )
        assert second.status_code == 429
        assert "queue is full" in second.json()["detail"]
    finally:
        runtime.release.set()
        service.close()


def test_terminal_job_history_is_bounded(tmp_path):
    store = AnalysisJobStore(tmp_path / "jobs.db")
    for index in range(3):
        job, _created = store.create_or_get(
            {
                "ticker": f"TEST{index}.IS",
                "trade_date": "2026-08-26",
                "estimated_cost_usd": None,
            },
            max_pending_jobs=10,
        )
        assert store.claim(job["id"])
        store.finish_success(job["id"], {"decision": "ok", "rating": "Hold"})

    assert store.prune_terminal(max_terminal_jobs=2) == 1
    assert store.counts()["succeeded"] == 2


def test_failure_response_redacts_environment_secret(tmp_path, monkeypatch):
    secret = "sk-phase13-provider-secret-123456"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    runtime = _Runtime(error=RuntimeError(f"provider rejected {secret}"))
    client, service, _runtime = _client(tmp_path, runtime)
    try:
        response = client.post(
            "/api/v1/analyses",
            json={"ticker": "TUPRS", "trade_date": "2026-08-26"},
        )
        job = _wait_for_terminal(client, response.json()["id"])
        assert job["status"] == "failed"
        assert secret not in str(job["error"])
        assert "[REDACTED]" in job["error"]["message"]
    finally:
        service.close()


def test_health_exposes_queue_counts_only_on_authenticated_surface(tmp_path):
    client, service, _runtime = _client(tmp_path)
    try:
        health = client.get("/api/v1/health").json()
        assert health["status"] == "ok"
        assert health["jobs"] == {
            "queued": 0,
            "running": 0,
            "succeeded": 0,
            "failed": 0,
            "max_pending": 100,
            "max_terminal": 5000,
        }
    finally:
        service.close()
