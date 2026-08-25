"""Regression tests for Phase 10 Codex Round 18 fixes."""

from __future__ import annotations

import importlib
from datetime import datetime

import pytest

import tradingagents.alerts.service as alert_service
from tradingagents.dataflows.kap.models import KapDisclosure, KapDisclosureResult


def _disclosure(subject: str, summary: str = "", *, disclosure_id: int = 1) -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 25, 10, 30),
        company="Test Şirketi A.Ş.",
        ticker="THYAO",
        subject=subject,
        disclosure_type="ODA",
        url=f"https://www.kap.org.tr/tr/Bildirim/{disclosure_id}",
        has_attachment=False,
        is_corrective=False,
        disclosure_id=disclosure_id,
        summary=summary,
    )


@pytest.mark.unit
def test_transfer_target_before_board_decision_adjunct_remains_mna():
    disclosure = _disclosure("Bağlı ortaklığı yönetim kurulu kararıyla devraldı")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "mna",
        90,
        "high",
    )


@pytest.mark.unit
def test_property_right_creation_allows_intervening_modifier():
    disclosure = _disclosure("Kullanım hakkının yeniden tesisi")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "other",
        0,
        "low",
    )


@pytest.mark.unit
def test_sector_company_possessor_without_usage_verb_is_acquisition():
    disclosure = _disclosure("Satın alınan enerji şirketinin üretim tesisleri")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "mna",
        90,
        "high",
    )


@pytest.mark.unit
def test_procurement_clause_does_not_hide_later_acquisition_clause():
    disclosure = _disclosure(
        "Şirketin satın aldığı makineler ve satın aldığı bağlı ortaklık"
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "mna",
        90,
        "high",
    )


@pytest.mark.unit
def test_active_perfect_company_buyer_is_procurement_not_mna():
    disclosure = _disclosure("ABC Şirketi'nin satın almış olduğu makineler")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "operations",
        80,
        "medium",
    )


@pytest.mark.unit
def test_passive_takeover_scans_full_target_phrase_without_token_cap():
    disclosure = _disclosure(
        "Devralınacak olan halka açık ve yabancı sermayeli anonim şirket"
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "mna",
        90,
        "high",
    )


@pytest.mark.unit
def test_round18_keeps_prior_governance_and_property_right_boundaries():
    cases = {
        "İştirak yönetimini bağlı ortaklığı adına devraldı": (
            "governance",
            65,
            "low",
        ),
        "Kullanım hakkı bulunan maden tesisi": (
            "operations",
            80,
            "medium",
        ),
        "Kullanım Hakkı Tesisi": ("other", 0, "low"),
        "Satın alınan elektrik şirketin yeni tesislerinde kullanılacaktır": (
            "operations",
            80,
            "medium",
        ),
    }
    for subject, expected in cases.items():
        assert alert_service.classify_kap_disclosure(_disclosure(subject)) == expected


class _TwoTickerWindowKapService:
    def __init__(self, counts: dict[str, int]) -> None:
        self.counts = counts

    def get_disclosures(
        self,
        ticker,
        start_date=None,
        end_date=None,
        max_disclosures=10,
        *,
        lookback_days=30,
        include_attachments=True,
        significance_key=None,
        summary_limit=600,
    ):
        del lookback_days, include_attachments, summary_limit
        assert significance_key is not None
        count = self.counts[str(ticker)]
        ticker_code = str(ticker).removesuffix(".IS")
        company = f"{ticker_code} Test A.Ş."
        base = 1000 if ticker_code == "THYAO" else 2000
        disclosures = tuple(
            KapDisclosure(
                published_at=datetime(2026, 8, 25, 9, offset),
                company=company,
                ticker=ticker_code,
                subject="Finansal Sonuçlar",
                disclosure_type="FR",
                url=f"https://www.kap.org.tr/tr/Bildirim/{base + offset}",
                has_attachment=False,
                is_corrective=False,
                disclosure_id=base + offset,
                summary="",
            )
            for offset in range(count)
        )
        return KapDisclosureResult(
            status="ok",
            ticker=ticker,
            kap_ticker=ticker_code,
            start_date=str(start_date),
            end_date=str(end_date),
            message="ok",
            disclosures=disclosures[:max_disclosures],
            total_found=count,
        )


@pytest.mark.unit
def test_all_successful_windows_refresh_before_aggregate_capacity_validation(tmp_path):
    watchlist_path = tmp_path / "watchlist.json"
    state_path = tmp_path / "alerts.json"
    tickers = ("THYAO.IS", "ASELS.IS")

    first = alert_service.KapWatchlistAlertService(
        alert_service.WatchlistStore(watchlist_path, seed_tickers=tickers),
        alert_service.AlertStateStore(
            state_path,
            history_limit=10,
            seen_limit=6,
        ),
        kap_service=_TwoTickerWindowKapService(
            {"THYAO.IS": 3, "ASELS.IS": 3}
        ),
        min_score=80,
        max_disclosures_per_ticker=1,
    )
    first.check_watchlist(now=datetime(2026, 8, 25, 10, 0))

    restarted = alert_service.KapWatchlistAlertService(
        alert_service.WatchlistStore(watchlist_path),
        alert_service.AlertStateStore(
            state_path,
            history_limit=10,
            seen_limit=2,
        ),
        kap_service=_TwoTickerWindowKapService(
            {"THYAO.IS": 1, "ASELS.IS": 1}
        ),
        min_score=80,
        max_disclosures_per_ticker=1,
    )

    # Both stale 3-item windows must be refreshed to 1 before aggregate capacity
    # is checked, otherwise the first ticker would be rejected against the stale
    # peak of the second ticker and the poll could never recover.
    restarted.check_watchlist(now=datetime(2026, 8, 25, 10, 5))


@pytest.mark.unit
def test_reloading_round17_installer_forces_stable_chain_rebuild():
    phase10 = importlib.import_module("tradingagents.alerts.phase10_hardening")
    round17 = importlib.import_module("tradingagents.alerts.round17_hardening")
    round18 = importlib.import_module("tradingagents.alerts.round18_hardening")

    phase10.install(alert_service)
    old_round17_install = round17.install
    round17 = importlib.reload(round17)
    assert round17.install is not old_round17_install

    phase10.install(alert_service)

    installed = alert_service._PHASE10_HARDENING_INSTALLER_IDENTITIES
    assert installed[2] is round17.install
    assert (
        alert_service._satin_alma_is_acquisition._phase10_round18_generation
        is round18.INSTALL_GENERATION
    )


@pytest.mark.unit
def test_reloading_round18_module_replaces_stale_round18_closures():
    phase10 = importlib.import_module("tradingagents.alerts.phase10_hardening")
    round18 = importlib.import_module("tradingagents.alerts.round18_hardening")

    phase10.install(alert_service)
    old_generation = round18.INSTALL_GENERATION
    round18 = importlib.reload(round18)
    assert round18.INSTALL_GENERATION is not old_generation

    phase10.install(alert_service)

    assert (
        alert_service._satin_alma_is_acquisition._phase10_round18_generation
        is round18.INSTALL_GENERATION
    )
    assert (
        alert_service.KapWatchlistAlertService.check_watchlist._phase10_round18_generation
        is round18.INSTALL_GENERATION
    )
