"""Regression tests for the final Phase 10 Codex review findings."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from tradingagents.alerts.models import WatchlistAlert
from tradingagents.alerts.service import AlertStateStore, KapWatchlistAlertService, WatchlistStore
from tradingagents.dataflows.kap.models import KapDisclosure, KapDisclosureResult
from tradingagents.dataflows.kap.service import KapService


def _disclosure(disclosure_id: int, summary: str) -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 24, 10, 0),
        company="Test Şirketi A.Ş.",
        ticker="THYAO",
        subject="Genel Bilgilendirme",
        disclosure_type="ODA",
        url=f"https://www.kap.org.tr/tr/Bildirim/{disclosure_id}",
        has_attachment=False,
        is_corrective=False,
        disclosure_id=disclosure_id,
        summary=summary,
    )


def _result(
    ticker: str,
    disclosures: tuple[KapDisclosure, ...] = (),
    *,
    status: str = "ok",
) -> KapDisclosureResult:
    return KapDisclosureResult(
        status=status,
        ticker=ticker,
        kap_ticker=ticker.removesuffix(".IS"),
        start_date="2026-08-17",
        end_date="2026-08-24",
        message=status,
        disclosures=disclosures,
        total_found=len(disclosures),
    )


class FakeKapService:
    def __init__(self, results: dict[str, KapDisclosureResult]) -> None:
        self.results = results
        self.calls: list[dict] = []

    def get_disclosures(self, **kwargs):
        self.calls.append(kwargs)
        return self.results[kwargs["ticker"]]


@pytest.mark.unit
def test_claim_refreshes_observed_ids_before_seen_limit_trim(tmp_path):
    state = AlertStateStore(tmp_path / "alerts.json", seen_limit=2)
    first = ["KAP:THYAO.IS:1", "KAP:THYAO.IS:2"]
    rotated = ["KAP:THYAO.IS:3", "KAP:THYAO.IS:1"]

    state.claim(first, ())
    state.claim(rotated, ())

    assert state.seen_ids() == tuple(rotated)


@pytest.mark.unit
def test_alert_poll_uses_full_summary_for_late_keyword_classification(tmp_path):
    long_summary = ("x" * 650) + " temettü ödemesi yapılacaktır"
    disclosure = _disclosure(401, long_summary)
    fake = FakeKapService({"THYAO.IS": _result("THYAO.IS", (disclosure,))})
    service = KapWatchlistAlertService(
        WatchlistStore(tmp_path / "watchlist.json", ["THYAO.IS"]),
        AlertStateStore(tmp_path / "alerts.json", seen_limit=100),
        kap_service=fake,
        max_disclosures_per_ticker=100,
    )

    batch = service.check_watchlist(now=datetime(2026, 8, 24, 11, 0))

    assert [alert.disclosure_id for alert in batch.alerts] == [401]
    assert batch.alerts[0].category == "dividend"
    assert fake.calls[0]["summary_limit"] is None


@pytest.mark.unit
def test_kap_mapping_preserves_full_summary_when_limit_is_none():
    long_summary = ("x" * 650) + " yatırım"
    raw = SimpleNamespace(
        publish_datetime=datetime(2026, 8, 24, 10, 0),
        company_name="Test Şirketi A.Ş.",
        subject="Genel Bilgilendirme",
        disclosure_type="ODA",
        url="https://www.kap.org.tr/tr/Bildirim/402",
        has_attachment=False,
        is_corrective=False,
        index=402,
        summary=long_summary,
    )

    mapped = KapService._map_disclosure(None, raw, "THYAO", False, None)
    default_mapped = KapService._map_disclosure(None, raw, "THYAO", False)

    assert mapped.summary == long_summary
    assert len(default_mapped.summary) == 600


@pytest.mark.unit
def test_failed_ticker_does_not_consume_tracked_ticker_capacity(tmp_path):
    state_path = tmp_path / "alerts.json"
    watchlist = WatchlistStore(tmp_path / "watchlist.json")

    failed = FakeKapService({"FAKE.IS": _result("FAKE.IS", status="company_not_found")})
    failed_service = KapWatchlistAlertService(
        watchlist,
        AlertStateStore(state_path, seen_limit=1),
        kap_service=failed,
        max_disclosures_per_ticker=1,
    )
    failed_service.check_watchlist(["FAKE.IS"], now=datetime(2026, 8, 24, 11, 0))

    good_disclosure = _disclosure(403, "temettü")
    good = FakeKapService({"THYAO.IS": _result("THYAO.IS", (good_disclosure,))})
    good_service = KapWatchlistAlertService(
        watchlist,
        AlertStateStore(state_path, seen_limit=1),
        kap_service=good,
        max_disclosures_per_ticker=1,
    )

    batch = good_service.check_watchlist(["THYAO.IS"], now=datetime(2026, 8, 24, 11, 5))

    assert [alert.disclosure_id for alert in batch.alerts] == [403]


@pytest.mark.unit
def test_refresh_does_not_reclaim_still_observed_alert(tmp_path):
    state = AlertStateStore(tmp_path / "alerts.json", seen_limit=2)
    alert = WatchlistAlert(
        alert_id="KAP:THYAO.IS:1",
        source="KAP",
        ticker="THYAO.IS",
        published_at=datetime(2026, 8, 24, 10, 0),
        title="Temettü",
        summary="temettü",
        url="https://www.kap.org.tr/tr/Bildirim/1",
        category="dividend",
        severity="critical",
        score=95,
        disclosure_id=1,
    )

    state.claim(["KAP:THYAO.IS:1", "KAP:THYAO.IS:2"], (alert,))
    state.acknowledge([alert.alert_id])
    state.claim(["KAP:THYAO.IS:3", "KAP:THYAO.IS:1"], ())

    claimed = state.claim(["KAP:THYAO.IS:3", "KAP:THYAO.IS:1"], (alert,))
    assert claimed == ()
