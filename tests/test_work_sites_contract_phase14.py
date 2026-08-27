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
    assert contract["existing_site_url"] == "https://arven-trade.hhakanguner.chatgpt.site/"


def test_phase14_sites_is_the_hosted_fullstack_runtime():
    deployment = _contract()["deployment"]
    assert deployment["mode"] == "sites_hosted_fullstack"
    assert deployment["update_existing_site"] is True
    assert deployment["create_replacement_site"] is False
    assert deployment["separate_backend_deployment_required"] is False
    assert deployment["external_phase13_https_url_required"] is False
    assert deployment["tradingagents_api_token_required_for_sites_local_calls"] is False
    assert deployment["phase13_api_is_behavioral_contract"] is True
    assert deployment["sites_server_routes_required"] is True
    assert deployment["durable_storage"] == "D1"
    assert deployment["hosted_secrets_supported"] is True
    assert deployment["ask_user_only_for_genuinely_missing_provider_secret"] is True
    assert deployment["deploy_to_existing_url"] is True


def test_phase14_forbids_browser_secret_storage_but_not_sites_local_calls():
    security = _contract()["security"]
    assert security["browser_bearer_token_allowed"] is False
    assert security["same_origin_server_boundary_required"] is True
    assert security["sites_local_server_calls_need_internal_bearer_token"] is False
    assert security["provider_secrets_location"] == "Sites hosted secrets"
    forbidden = set(security["client_secret_storage_forbidden"])
    assert {"javascript_bundle", "service_worker", "localStorage", "indexedDB"} <= forbidden


def test_phase14_phase13_behavior_contract_matches_fastapi_reference_routes():
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
        for item in contract["phase13_behavior_contract"]["reference_routes"]
    }
    assert required <= actual
    assert ("GET", "/healthz") in actual
    assert all(item["implementation"] == "sites_server_route" for item in contract["browser_routes"])


def test_phase14_analysis_and_error_states_are_explicit():
    contract = _contract()
    assert contract["analysis_states"] == ["queued", "running", "succeeded", "failed"]
    assert {401, 403, 404, 409, 429, 500, 503} <= set(contract["required_error_states"])


def test_phase14_agent_names_and_icons_are_locked_for_sites():
    lock = _contract()["agent_identity_lock"]
    assert lock["locked"] is True
    assert lock["language"] == "tr"
    assert lock["replace_initial_letters_with_icons"] is True
    assert lock["allow_visible_english_agent_titles"] is False

    expected = [
        ("market", "Piyasa Analisti", "rising_chart"),
        ("sentiment", "Duyarlılık Analisti", "smiley_face"),
        ("news", "Haber Analisti", "newspaper"),
        ("fundamentals", "Temel Analist", "pie_chart"),
        ("kap", "KAP Araştırmacısı", "kap_document_megaphone"),
        ("bull", "Boğa Görüş Araştırmacısı", "bull_head"),
        ("bear", "Ayı Görüş Araştırmacısı", "bear_head"),
        ("risk", "Risk Yöneticisi", "shield_check"),
        ("trader", "İşlem (Trader) Ajanı", "target_arrow"),
    ]
    actual = [(item["key"], item["name"], item["icon"]) for item in lock["agents"]]
    assert actual == expected

    style = lock["icon_style"]
    assert style["container"] == "rounded_light_blue_square"
    assert style["bull_tone"] == "green"
    assert style["bear_tone"] == "red"
    assert style["consistent_vector_pictograms"] is True


def test_phase14_kap_is_real_sites_server_feed_without_external_backend_requirement():
    kap = _contract()["kap_feed"]
    assert kap["menu_label"] == "KAP Açıklamaları"
    assert kap["required"] is True
    assert kap["analysis_card_required"] is True
    assert kap["chronological_menu_required"] is True
    assert kap["group_by_day"] is True
    assert kap["newest_first"] is True
    assert {"watchlist_tickers", "analyzed_tickers"} <= set(kap["current_real_scope"])
    assert kap["browser_route_requires_real_server_implementation"] is True
    assert kap["external_upstream_required"] is False
    assert kap["market_wide_all_bist_requires_real_feed"] is True
    assert kap["must_not_fake_market_wide_feed"] is True
    assert kap["must_not_show_demo_disclosures"] is True
    assert {"published_at", "ticker", "company", "title_or_subject", "summary", "official_url"} <= set(
        kap["required_fields"]
    )


def test_phase14_release_bookkeeping_does_not_assume_auto_sync():
    release = _contract()["release"]
    assert release["record_synced_git_sha"] is True
    assert release["automatic_git_to_sites_sync_assumed"] is False
