"""Regression tests for the latest Phase 10 Codex review findings."""

from datetime import datetime

import pytest

from tradingagents.alerts.service import (
    AlertStateStore,
    KapWatchlistAlertService,
    WatchlistStore,
    classify_kap_disclosure,
)
from tradingagents.dataflows.kap.models import KapDisclosure, KapDisclosureResult


def _disclosure(
    subject: str,
    *,
    summary: str = "",
    disclosure_id: int = 1,
) -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 24, 12, 0),
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


class FakeKapService:
    def __init__(self, disclosure: KapDisclosure) -> None:
        self.disclosure = disclosure

    def get_disclosures(self, **kwargs) -> KapDisclosureResult:
        ticker = kwargs["ticker"]
        return KapDisclosureResult(
            status="ok",
            ticker=ticker,
            kap_ticker=ticker.removesuffix(".IS"),
            start_date="2026-08-17",
            end_date="2026-08-24",
            message="1 kayıt",
            disclosures=(self.disclosure,),
            total_found=1,
        )


@pytest.mark.unit
def test_ana_sozlesme_amendments_are_not_commercial_contract_alerts():
    assert classify_kap_disclosure(_disclosure("Ana Sözleşme Tadili")) == ("other", 0, "low")
    assert classify_kap_disclosure(_disclosure("Şirket Ana Sözleşmesinin Tadili")) == (
        "other",
        0,
        "low",
    )
    assert classify_kap_disclosure(_disclosure("Yeni Tedarik Sözleşmesi İmzalanması")) == (
        "commercial",
        85,
        "high",
    )


@pytest.mark.unit
def test_acquisition_inflections_match_mna_events():
    assert classify_kap_disclosure(_disclosure("Şirket Satın Alımı")) == (
        "mna",
        90,
        "high",
    )
    assert classify_kap_disclosure(_disclosure("Payların Satın Alınması")) == (
        "mna",
        90,
        "high",
    )
    assert classify_kap_disclosure(_disclosure("Şirket Satın Alma İşlemi")) == (
        "mna",
        90,
        "high",
    )


@pytest.mark.unit
def test_full_summary_classifies_but_alert_and_outbox_summary_are_bounded(tmp_path):
    long_summary = ("x" * 700) + " temettü dağıtım kararı"
    disclosure = _disclosure(
        "Genel Bilgilendirme",
        summary=long_summary,
        disclosure_id=77,
    )
    service = KapWatchlistAlertService(
        WatchlistStore(tmp_path / "watchlist.json"),
        AlertStateStore(tmp_path / "alerts.json"),
        kap_service=FakeKapService(disclosure),
        min_score=80,
    )

    batch = service.check_watchlist(["THYAO.IS"], now=datetime(2026, 8, 24, 12, 30))

    assert len(batch.alerts) == 1
    assert batch.alerts[0].category == "dividend"
    assert batch.alerts[0].score == 95
    assert len(batch.alerts[0].summary) <= 600
    assert batch.alerts[0].summary.endswith("...")

    pending = service.pending_alerts()
    assert len(pending) == 1
    assert len(pending[0]["summary"]) <= 600
    assert pending[0]["summary"] == batch.alerts[0].summary
