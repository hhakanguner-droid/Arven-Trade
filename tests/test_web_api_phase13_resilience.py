from concurrent.futures import ThreadPoolExecutor
import time

from fastapi.testclient import TestClient
import pytest

from tradingagents.service.api import create_app
from tradingagents.service.core import AnalysisService
from tradingagents.service.jobs import AnalysisJobStore, QueueCapacityExceeded


class _Runtime:
    def __init__(self):
        self.calls = []

    def health(self):
        return {"credential": {"credential_status": "configured"}}

    def propagate(self, ticker, trade_date, asset_type="stock", *, estimated_cost_usd=None):
        self.calls.append((ticker, trade_date, asset_type, estimated_cost_usd))
        return ({"company_of_interest": ticker}, "Rating: Hold. Recovery complete.")


def _request(ticker="THYAO.IS"):
    return {
        "ticker": ticker,
        "trade_date": "2026-08-26",
        "estimated_cost_usd": None,
    }


def test_concurrent_idempotent_enqueues_collapse_to_one_job(tmp_path):
    store = AnalysisJobStore(tmp_path / "jobs.db")

    def submit_once(_index):
        return store.create_or_get(
            _request(),
            idempotency_key="phase13-concurrent-key",
            max_pending_jobs=100,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(submit_once, range(16)))

    job_ids = {job["id"] for job, _created in results}
    created_count = sum(1 for _job, created in results if created)
    assert len(job_ids) == 1
    assert created_count == 1
    assert store.counts()["queued"] == 1


def test_idempotent_replay_bypasses_full_queue_without_duplicate_work(tmp_path):
    store = AnalysisJobStore(tmp_path / "jobs.db")
    first, created = store.create_or_get(
        _request(),
        idempotency_key="stable-request",
        max_pending_jobs=1,
    )
    assert created is True
    assert store.claim(first["id"])

    replay, replay_created = store.create_or_get(
        _request(),
        idempotency_key="stable-request",
        max_pending_jobs=1,
    )
    assert replay_created is False
    assert replay["id"] == first["id"]

    with pytest.raises(QueueCapacityExceeded):
        store.create_or_get(
            _request("ASELS.IS"),
            idempotency_key="different-request",
            max_pending_jobs=1,
        )


def test_restart_requeues_interrupted_running_job_and_finishes(tmp_path):
    store = AnalysisJobStore(tmp_path / "jobs.db")
    job, created = store.create_or_get(
        _request(),
        idempotency_key="restart-safe",
        max_pending_jobs=10,
    )
    assert created is True
    assert store.claim(job["id"])
    assert store.get(job["id"])["status"] == "running"

    runtime = _Runtime()
    service = AnalysisService(runtime, store, recover_incomplete=True)
    try:
        for _ in range(200):
            recovered = store.get(job["id"])
            if recovered and recovered["status"] == "succeeded":
                break
            time.sleep(0.01)
        else:
            raise AssertionError("recovered job did not finish")

        assert len(runtime.calls) == 1
        assert runtime.calls[0][0] == "THYAO.IS"
        assert store.get(job["id"])["result"]["rating"] == "Hold"
    finally:
        service.close()


def test_all_private_api_surfaces_require_bearer_auth(tmp_path):
    token = "phase13-private-route-token-0123456789"
    service = AnalysisService(
        _Runtime(),
        AnalysisJobStore(tmp_path / "jobs.db"),
        recover_incomplete=False,
    )
    client = TestClient(create_app(service, api_token=token, auth_disabled=False))
    try:
        requests = [
            ("get", "/api/v1/health", None),
            ("get", "/api/v1/history", None),
            ("get", "/api/v1/history/1", None),
            ("get", "/api/v1/compare/THYAO", None),
            ("get", "/api/v1/performance", None),
            (
                "post",
                "/api/v1/analyses",
                {"ticker": "THYAO", "trade_date": "2026-08-26"},
            ),
        ]
        for method, path, payload in requests:
            response = getattr(client, method)(path, json=payload) if payload else getattr(client, method)(path)
            assert response.status_code == 401, path

        authorized = client.get(
            "/api/v1/health",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert authorized.status_code == 200
    finally:
        service.close()
