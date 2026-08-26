import json
from pathlib import Path

from tradingagents.service.api import create_app

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "work-sites" / "site-contract.json"


class _Service:
    def close(self):
        return None

    def health(self):
        return {"status": "ok"}

    def submit(self, *args, **kwargs):
        return {"id": "job", "status": "queued"}

    def get(self, _job_id):
        return {"id": "job", "status": "queued"}

    def list_history(self, *_args, **_kwargs):
        return []

    def get_history(self, _analysis_id):
        return None

    def compare_history(self, *_args, **_kwargs):
        return []

    def performance_summary(self, *_args, **_kwargs):
        return {"horizons": []}


def _contract():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_phase14_contract_points_to_canonical_repo_and_main():
    contract = _contract()
    assert contract["phase"] == 14
    assert contract["repository"] == "hhakanguner-droid/Arven-Trade"
    assert contract["production_branch"] == "main"
    assert contract["backend_contract_phase"] == 13


def test_phase14_forbids_browser_bearer_secret_storage():
    security = _contract()["security"]
    assert security["browser_bearer_token_allowed"] is False
    assert security["same_origin_server_boundary_required"] is True
    forbidden = set(security["client_secret_storage_forbidden"])
    assert {"javascript_bundle", "service_worker", "localStorage", "indexedDB"} <= forbidden


def test_phase14_upstream_contract_matches_phase13_fastapi_routes():
    contract = _contract()
    app = create_app(_Service(), auth_disabled=True)
    actual = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method in {"GET", "POST"}
    }
    required = {
        (item["method"], item["path"])
        for item in contract["upstream"]["authenticated"]
    }
    assert required <= actual
    assert ("GET", "/healthz") in actual


def test_phase14_analysis_and_error_states_are_explicit():
    contract = _contract()
    assert contract["analysis_states"] == ["queued", "running", "succeeded", "failed"]
    assert {401, 403, 404, 409, 429, 500, 503} <= set(contract["required_error_states"])


def test_phase14_kap_is_both_analysis_card_and_daily_menu_without_fake_market_feed():
    kap = _contract()["kap_feed"]
    assert kap["menu_label"] == "KAP Açıklamaları"
    assert kap["required"] is True
    assert kap["analysis_card_required"] is True
    assert kap["chronological_menu_required"] is True
    assert kap["group_by_day"] is True
    assert kap["newest_first"] is True
    assert {"watchlist_tickers", "analyzed_tickers"} <= set(kap["current_real_scope"])
    assert kap["browser_route_requires_real_upstream"] is True
    assert kap["market_wide_all_bist_requires_backend_feed"] is True
    assert kap["must_not_fake_market_wide_feed"] is True
    assert kap["must_not_show_demo_disclosures"] is True
    assert {"published_at", "ticker", "company", "title_or_subject", "summary", "official_url"} <= set(
        kap["required_fields"]
    )


def test_phase14_release_bookkeeping_does_not_assume_auto_sync():
    release = _contract()["release"]
    assert release["record_synced_git_sha"] is True
    assert release["automatic_git_to_sites_sync_assumed"] is False
