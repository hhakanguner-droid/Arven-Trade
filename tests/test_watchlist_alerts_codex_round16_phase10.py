"""Regression tests for Phase 10 Codex Round 16 fixes."""

from __future__ import annotations

import importlib
from datetime import datetime
from types import SimpleNamespace

import pytest

import tradingagents.alerts.service as alert_service
from tradingagents.dataflows.kap.models import KapDisclosure, KapDisclosureResult


def _disclosure(subject: str, summary: str = "", *, disclosure_id: int = 1) -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 25, 9, 0),
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
def test_inflected_company_buyer_in_active_purchase_is_not_mna():
    disclosure = _disclosure(
        "ABC Şirketi'nin satın aldığı makineler üretimde kullanılacaktır"
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "operations",
        80,
        "medium",
    )


@pytest.mark.unit
def test_subject_corporate_split_is_not_suppressed_by_debt_in_summary():
    disclosure = _disclosure(
        "Şirketin Bölünmesi",
        "Kredi borçları devredilecektir.",
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "mna",
        90,
        "high",
    )


@pytest.mark.unit
def test_management_object_outranks_entity_words_in_intervening_adjunct():
    disclosure = _disclosure(
        "İştirak yönetimini bağlı ortaklığı adına devraldı"
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "governance",
        65,
        "low",
    )


@pytest.mark.unit
@pytest.mark.parametrize("subject", ["Kullanım Hakkı Tesisi", "Önalım Hakkı Tesisi"])
def test_productive_property_right_construction_is_not_physical_facility(subject):
    assert alert_service.classify_kap_disclosure(_disclosure(subject)) == (
        "other",
        0,
        "low",
    )


@pytest.mark.unit
def test_sector_word_can_be_completed_procurement_object():
    disclosure = _disclosure(
        "Satın alınan elektrik şirket tesislerinde kullanılacaktır"
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "operations",
        80,
        "medium",
    )


@pytest.mark.unit
@pytest.mark.parametrize("subject", ["Devralınacak Şirket", "Devralınan Firma"])
def test_passive_devralin_accepts_following_company_target(subject):
    assert alert_service.classify_kap_disclosure(_disclosure(subject)) == (
        "mna",
        90,
        "high",
    )


@pytest.mark.unit
def test_stable_phase10_entry_reinstalls_round16_after_module_and_service_reload():
    phase10 = importlib.import_module("tradingagents.alerts.phase10_hardening")
    phase10 = importlib.reload(phase10)
    importlib.reload(alert_service)

    phase10.install(alert_service)

    assert (
        alert_service._satin_alma_is_acquisition._phase10_round16_version
        == "phase10-round16"
    )
    assert (
        alert_service.KapWatchlistAlertService.check_watchlist._phase10_round16_version
        == "phase10-round16"
    )


class _RotatingKapService:
    def __init__(self) -> None:
        self.raw = tuple(
            SimpleNamespace(
                index=100 + offset,
                subject="Finansal Sonuçlar",
                summary="",
                disclosure_type="FR",
                is_corrective=False,
                publish_datetime=datetime(2026, 8, 25, 9, offset),
                company_name="Test Şirketi A.Ş.",
                url=f"https://www.kap.org.tr/tr/Bildirim/{100 + offset}",
                has_attachment=False,
            )
            for offset in range(3)
        )

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
        assert significance_key is not None
        selected = sorted(self.raw, key=significance_key, reverse=True)[
            :max_disclosures
        ]
        mapped = tuple(
            KapDisclosure(
                published_at=item.publish_datetime,
                company=item.company_name,
                ticker="THYAO",
                subject=item.subject,
                disclosure_type=item.disclosure_type,
                url=item.url,
                has_attachment=item.has_attachment,
                is_corrective=item.is_corrective,
                disclosure_id=item.index,
                summary=item.summary,
            )
            for item in selected
        )
        return KapDisclosureResult(
            status="ok",
            ticker=ticker,
            kap_ticker="THYAO",
            start_date=str(start_date),
            end_date=str(end_date),
            message="ok",
            disclosures=mapped,
            total_found=len(self.raw),
        )


@pytest.mark.unit
def test_unseen_first_poll_requires_durable_capacity_for_all_reachable_ids(tmp_path):
    service = alert_service.KapWatchlistAlertService(
        alert_service.WatchlistStore(
            tmp_path / "watchlist.json",
            seed_tickers=("THYAO.IS",),
        ),
        alert_service.AlertStateStore(
            tmp_path / "alerts.json",
            history_limit=1,
            seen_limit=1,
        ),
        kap_service=_RotatingKapService(),
        min_score=80,
        max_disclosures_per_ticker=1,
    )

    with pytest.raises(ValueError, match="reachable through unseen-first polling"):
        service.check_watchlist(now=datetime(2026, 8, 25, 9, 0))


@pytest.mark.unit
def test_round16_capacity_requirement_persists_across_service_restart(tmp_path):
    watchlist_path = tmp_path / "watchlist.json"
    state_path = tmp_path / "alerts.json"
    first = alert_service.KapWatchlistAlertService(
        alert_service.WatchlistStore(watchlist_path, seed_tickers=("THYAO.IS",)),
        alert_service.AlertStateStore(state_path, history_limit=1, seen_limit=3),
        kap_service=_RotatingKapService(),
        min_score=80,
        max_disclosures_per_ticker=1,
    )
    first.check_watchlist(now=datetime(2026, 8, 25, 9, 0))

    restarted = alert_service.KapWatchlistAlertService(
        alert_service.WatchlistStore(watchlist_path),
        alert_service.AlertStateStore(state_path, history_limit=1, seen_limit=2),
        kap_service=_RotatingKapService(),
        min_score=80,
        max_disclosures_per_ticker=1,
    )
    with pytest.raises(ValueError, match="reachable through unseen-first polling"):
        restarted.check_watchlist(now=datetime(2026, 8, 25, 9, 5))


@pytest.mark.unit
def test_round16_keeps_round15_positive_sector_target_case():
    disclosure = _disclosure("Satın Alınan Elektrik Dağıtım Şirketi")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "mna",
        90,
        "high",
    )
