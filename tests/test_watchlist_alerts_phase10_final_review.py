"""Regression tests for the final Phase 10 Codex review findings."""

from __future__ import annotations

from datetime import datetime

import pytz
import pytest

from tradingagents.alerts.service import (
    AlertStateStore,
    KapWatchlistAlertService,
    WatchlistStore,
    _market_datetime,
    classify_kap_disclosure,
)
from tradingagents.dataflows.kap.models import KapDisclosure, KapDisclosureResult


def _disclosure(disclosure_id: int, subject: str) -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 24, 10, 0),
        company="Test Şirketi A.Ş.",
        ticker="THYAO",
        subject=subject,
        disclosure_type="ODA",
        url=f"https://www.kap.org.tr/tr/Bildirim/{disclosure_id}",
        has_attachment=False,
        is_corrective=False,
        disclosure_id=disclosure_id,
        summary="",
    )


class FakeKapService:
    def __init__(self, results: dict[str, KapDisclosureResult]):
        self.results = results

    def get_disclosures(self, **kwargs):
        return self.results[kwargs["ticker"]]


def _ok(ticker: str, disclosure_id: int) -> KapDisclosureResult:
    disclosure = _disclosure(disclosure_id, "Genel Bilgilendirme")
    return KapDisclosureResult(
        status="ok",
        ticker=ticker,
        kap_ticker=ticker.removesuffix(".IS"),
        start_date="2026-08-17",
        end_date="2026-08-24",
        message="1 kayıt",
        disclosures=(disclosure,),
        total_found=1,
    )


@pytest.mark.unit
def test_market_datetime_uses_existing_pytz_dependency_for_istanbul_timezone():
    market_time = _market_datetime(datetime(2026, 8, 24, 12, 0))

    assert market_time.tzinfo is not None
    assert str(market_time.tzinfo) == "Europe/Istanbul"
    assert market_time.utcoffset() == pytz.timezone("Europe/Istanbul").utcoffset(market_time.replace(tzinfo=None))


@pytest.mark.unit
def test_share_repurchase_is_classified_as_important_ownership_event():
    disclosure = _disclosure(701, "Pay Geri Alım İşlemleri")

    category, score, severity = classify_kap_disclosure(disclosure)

    assert category == "ownership"
    assert score == 90
    assert severity == "high"


@pytest.mark.unit
def test_full_watchlist_poll_retires_removed_tickers_from_capacity(tmp_path):
    watchlist = WatchlistStore(tmp_path / "watchlist.json")
    watchlist.replace(["THYAO.IS"])
    state = AlertStateStore(tmp_path / "alerts.json", seen_limit=1)
    service = KapWatchlistAlertService(
        watchlist,
        state,
        kap_service=FakeKapService(
            {
                "THYAO.IS": _ok("THYAO.IS", 801),
                "ASELS.IS": _ok("ASELS.IS", 802),
            }
        ),
        max_disclosures_per_ticker=1,
    )

    service.check_watchlist(now=datetime(2026, 8, 24, 12, 0))
    watchlist.replace(["ASELS.IS"])

    # If THYAO.IS were never retired, this second successful ticker would
    # require capacity for two tickers and raise with seen_limit=1.
    service.check_watchlist(now=datetime(2026, 8, 24, 12, 5))

    assert state._load_unlocked()["tracked_tickers"] == ["ASELS.IS"]
