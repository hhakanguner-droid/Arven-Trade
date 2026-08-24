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


def _disclosure(subject: str) -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 24, 12, 0),
        company="Test Şirketi A.Ş.",
        ticker="THYAO",
        subject=subject,
        disclosure_type="ODA",
        url="https://www.kap.org.tr/tr/Bildirim/1",
        has_attachment=False,
        is_corrective=False,
        disclosure_id=1,
        summary="",
    )


class FakeKapService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def get_disclosures(self, **kwargs):
        self.calls.append(kwargs)
        ticker = kwargs["ticker"]
        return KapDisclosureResult(
            status="ok",
            ticker=ticker,
            kap_ticker=ticker.removesuffix(".IS"),
            start_date="2026-08-17",
            end_date="2026-08-24",
            message="0 kayıt",
            disclosures=(),
            total_found=0,
        )


@pytest.mark.unit
def test_explicit_ticker_poll_does_not_read_corrupt_persisted_watchlist(tmp_path):
    watchlist_path = tmp_path / "watchlist.json"
    watchlist_path.write_text("{}", encoding="utf-8")
    fake = FakeKapService()
    service = KapWatchlistAlertService(
        WatchlistStore(watchlist_path),
        AlertStateStore(tmp_path / "alerts.json"),
        kap_service=fake,
    )

    batch = service.check_watchlist(["THYAO.IS"], now=datetime(2026, 8, 24, 12, 0))

    assert batch.alerts == ()
    assert [status.status for status in batch.source_statuses] == ["ok"]
    assert [call["ticker"] for call in fake.calls] == ["THYAO.IS"]


@pytest.mark.unit
def test_articles_of_association_are_not_commercial_contract_alerts():
    assert classify_kap_disclosure(_disclosure("Esas Sözleşme Tadili")) == ("other", 0, "low")
    assert classify_kap_disclosure(_disclosure("Şirket Esas Sözleşmesinin Tadili")) == (
        "other",
        0,
        "low",
    )


@pytest.mark.unit
def test_real_commercial_contract_inflections_still_match():
    assert classify_kap_disclosure(_disclosure("Yeni Tedarik Sözleşmesi İmzalanması")) == (
        "commercial",
        85,
        "high",
    )
