"""Regression tests for Phase 10 Codex Round 17 fixes."""

from __future__ import annotations

import importlib
from datetime import datetime

import pytest

import tradingagents.alerts.service as alert_service
from tradingagents.dataflows.kap.models import KapDisclosure, KapDisclosureResult


def _disclosure(subject: str, summary: str = "", *, disclosure_id: int = 1) -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 25, 10, 0),
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
def test_repeated_stable_install_keeps_round17_outermost():
    phase10 = importlib.import_module("tradingagents.alerts.phase10_hardening")
    phase10 = importlib.reload(phase10)

    phase10.install(alert_service)
    phase10.install(alert_service)

    assert (
        alert_service._satin_alma_is_acquisition._phase10_round17_version
        == "phase10-round17"
    )
    assert (
        alert_service.KapWatchlistAlertService.check_watchlist._phase10_round17_version
        == "phase10-round17"
    )
    assert alert_service.classify_kap_disclosure(
        _disclosure("ABC Şirketi'nin satın aldığı makineler")
    ) == ("operations", 80, "medium")


@pytest.mark.unit
def test_active_company_buyer_scan_reaches_procurement_object_after_modifiers():
    disclosure = _disclosure(
        "ABC Şirketi'nin satın aldığı yeni üretim makineleri"
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "operations",
        80,
        "medium",
    )


@pytest.mark.unit
def test_sector_procurement_survives_usage_clause_modifiers():
    disclosure = _disclosure(
        "Satın alınan elektrik şirketin yeni tesislerinde kullanılacaktır"
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "operations",
        80,
        "medium",
    )


@pytest.mark.unit
def test_governance_adjunct_does_not_hide_real_transfer_object():
    disclosure = _disclosure(
        "Yönetim kurulu kararıyla bağlı ortaklığı devraldı"
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "mna",
        90,
        "high",
    )


@pytest.mark.unit
def test_property_right_nearby_does_not_suppress_physical_facility():
    disclosure = _disclosure("Kullanım hakkı bulunan maden tesisi")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "operations",
        80,
        "medium",
    )


@pytest.mark.unit
def test_named_company_possessor_is_corporate_split_evidence():
    disclosure = _disclosure("ABC A.Ş.'nin Bölünmesi")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "mna",
        90,
        "high",
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "subject",
    [
        "Devralınan halka açık şirket",
        "Devralınacak olan yabancı şirket",
    ],
)
def test_passive_devralin_scans_through_target_modifiers(subject):
    assert alert_service.classify_kap_disclosure(_disclosure(subject)) == (
        "mna",
        90,
        "high",
    )


class _WindowKapService:
    def __init__(self, count: int, *, company: str = "Test Şirketi A.Ş.") -> None:
        self.count = count
        self.company = company

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
        available = tuple(
            KapDisclosure(
                published_at=datetime(2026, 8, 25, 9, offset),
                company=self.company,
                ticker=str(ticker).removesuffix(".IS"),
                subject="Finansal Sonuçlar",
                disclosure_type="FR",
                url=f"https://www.kap.org.tr/tr/Bildirim/{500 + offset}",
                has_attachment=False,
                is_corrective=False,
                disclosure_id=500 + offset,
                summary="",
            )
            for offset in range(self.count)
        )
        return KapDisclosureResult(
            status="ok",
            ticker=ticker,
            kap_ticker="TEST",
            start_date=str(start_date),
            end_date=str(end_date),
            message="ok",
            disclosures=available[:max_disclosures],
            total_found=self.count,
        )


@pytest.mark.unit
def test_expired_window_peak_releases_seen_capacity_after_restart(tmp_path):
    watchlist_path = tmp_path / "watchlist.json"
    state_path = tmp_path / "alerts.json"

    first = alert_service.KapWatchlistAlertService(
        alert_service.WatchlistStore(
            watchlist_path,
            seed_tickers=("THYAO.IS",),
        ),
        alert_service.AlertStateStore(
            state_path,
            history_limit=1,
            seen_limit=3,
        ),
        kap_service=_WindowKapService(3),
        min_score=80,
        max_disclosures_per_ticker=1,
    )
    first.check_watchlist(now=datetime(2026, 8, 25, 10, 0))

    restarted = alert_service.KapWatchlistAlertService(
        alert_service.WatchlistStore(watchlist_path),
        alert_service.AlertStateStore(
            state_path,
            history_limit=1,
            seen_limit=2,
        ),
        kap_service=_WindowKapService(1),
        min_score=80,
        max_disclosures_per_ticker=1,
    )

    # The current lookback contains one reachable disclosure, so the old peak
    # of three must not permanently force seen_limit >= 3.
    restarted.check_watchlist(now=datetime(2026, 8, 25, 10, 5))


class _ShareClassKapService:
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
        disclosures = tuple(
            KapDisclosure(
                published_at=datetime(2026, 8, 25, 9, offset),
                company="Türkiye İş Bankası A.Ş.",
                ticker=str(ticker).removesuffix(".IS"),
                subject="Finansal Sonuçlar",
                disclosure_type="FR",
                url=f"https://www.kap.org.tr/tr/Bildirim/{700 + offset}",
                has_attachment=False,
                is_corrective=False,
                disclosure_id=700 + offset,
                summary="",
            )
            for offset in range(2)
        )
        return KapDisclosureResult(
            status="ok",
            ticker=ticker,
            kap_ticker="ISCTR",
            start_date=str(start_date),
            end_date=str(end_date),
            message="ok",
            disclosures=disclosures[:max_disclosures],
            total_found=2,
        )


@pytest.mark.unit
def test_capacity_counts_shared_company_disclosures_once_across_share_classes(tmp_path):
    service = alert_service.KapWatchlistAlertService(
        alert_service.WatchlistStore(
            tmp_path / "watchlist.json",
            seed_tickers=("ISCTR.IS", "ISBTR.IS"),
        ),
        alert_service.AlertStateStore(
            tmp_path / "alerts.json",
            history_limit=10,
            seen_limit=2,
        ),
        kap_service=_ShareClassKapService(),
        min_score=80,
        max_disclosures_per_ticker=2,
    )

    batch = service.check_watchlist(now=datetime(2026, 8, 25, 10, 0))

    assert len(batch.alerts) == 2
    assert {item.alert_id for item in batch.alerts} == {"KAP:700", "KAP:701"}


@pytest.mark.unit
def test_round17_preserves_round16_and_round15_positive_cases():
    cases = {
        "Satın Alınan Elektrik Dağıtım Şirketi": ("mna", 90, "high"),
        "İştirak yönetimini bağlı ortaklığı adına devraldı": (
            "governance",
            65,
            "low",
        ),
        "Kullanım Hakkı Tesisi": ("other", 0, "low"),
        "Şirketin Kredi Borçlarının Bölünmesi": ("financing", 75, "medium"),
    }
    for subject, expected in cases.items():
        assert alert_service.classify_kap_disclosure(_disclosure(subject)) == expected
