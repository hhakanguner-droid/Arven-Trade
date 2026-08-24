"""Phase 10 tests for persistent BIST watchlists and KAP event alerts."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from tradingagents.alerts.models import WatchlistAlert
from tradingagents.alerts.service import (
    AlertStateStore,
    KapWatchlistAlertService,
    WatchlistStore,
    classify_kap_disclosure,
    create_watchlist_alert_service,
)
from tradingagents.dataflows.kap.models import KapDisclosure, KapDisclosureResult


def _disclosure(
    disclosure_id: int,
    subject: str,
    *,
    summary: str = "",
    disclosure_type: str = "ODA",
    corrective: bool = False,
    published_at: datetime | None = None,
) -> KapDisclosure:
    return KapDisclosure(
        published_at=published_at or datetime(2026, 8, 24, 9, 30),
        company="Test Şirketi A.Ş.",
        ticker="THYAO",
        subject=subject,
        disclosure_type=disclosure_type,
        url=f"https://www.kap.org.tr/tr/Bildirim/{disclosure_id}",
        has_attachment=False,
        is_corrective=corrective,
        disclosure_id=disclosure_id,
        summary=summary,
    )


def _alert(disclosure_id: int, title: str, severity: str, score: int) -> WatchlistAlert:
    return WatchlistAlert(
        alert_id=f"KAP:THYAO.IS:{disclosure_id}",
        source="KAP",
        ticker="THYAO.IS",
        published_at=datetime(2026, 8, 24, 9, disclosure_id % 60),
        title=title,
        summary="",
        url=f"https://www.kap.org.tr/tr/Bildirim/{disclosure_id}",
        category="financials" if severity == "critical" else "operations",
        severity=severity,
        score=score,
        disclosure_id=disclosure_id,
    )


class FakeKapService:
    def __init__(self, results: dict[str, KapDisclosureResult]):
        self.results = results
        self.calls: list[dict] = []

    def get_disclosures(self, **kwargs):
        self.calls.append(kwargs)
        return self.results[kwargs["ticker"]]


def _ok_result(ticker: str, disclosures: tuple[KapDisclosure, ...]) -> KapDisclosureResult:
    return KapDisclosureResult(
        status="ok",
        ticker=ticker,
        kap_ticker=ticker.removesuffix(".IS"),
        start_date="2026-08-17",
        end_date="2026-08-24",
        message=f"{len(disclosures)} kayıt",
        disclosures=disclosures,
        total_found=len(disclosures),
    )


@pytest.mark.unit
def test_watchlist_seeds_canonical_bist_tickers_and_persists(tmp_path):
    path = tmp_path / "watchlist.json"
    store = WatchlistStore(path, ["thyao.is", "ASELS.IS", "AAPL", "THYAO.IS"])

    assert store.list() == ("THYAO.IS", "ASELS.IS")
    assert WatchlistStore(path).list() == ("THYAO.IS", "ASELS.IS")


@pytest.mark.unit
def test_watchlist_add_remove_and_rejects_non_bist_symbols(tmp_path):
    store = WatchlistStore(tmp_path / "watchlist.json")

    assert store.add("thyao.is") is True
    assert store.add("THYAO.IS") is False
    assert store.list() == ("THYAO.IS",)
    assert store.remove("THYAO.IS") is True
    assert store.remove("THYAO.IS") is False

    with pytest.raises(ValueError, match="not a BIST Yahoo ticker"):
        store.add("THYAO")
    with pytest.raises(ValueError, match="not a BIST Yahoo ticker"):
        store.add("AAPL")


@pytest.mark.unit
def test_watchlist_concurrent_adds_do_not_lose_updates(tmp_path):
    store = WatchlistStore(tmp_path / "watchlist.json")
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(store.add, ["THYAO.IS", "ASELS.IS"]))

    assert results == [True, True]
    assert set(store.list()) == {"THYAO.IS", "ASELS.IS"}


@pytest.mark.unit
def test_watchlist_replace_fails_closed_on_invalid_member(tmp_path):
    store = WatchlistStore(tmp_path / "watchlist.json")
    with pytest.raises(ValueError, match="watchlist only accepts"):
        store.replace(["THYAO.IS", "AAPL"])
    assert not store.path.exists()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("disclosure", "category", "score", "severity"),
    [
        (_disclosure(1, "Finansal Rapor", disclosure_type="FR"), "financials", 100, "critical"),
        (_disclosure(2, "Kar Payı Dağıtım İşlemlerine İlişkin Bildirim"), "dividend", 95, "critical"),
        (_disclosure(3, "Yeni İhale ve Sözleşme Hakkında"), "commercial", 85, "high"),
        (_disclosure(4, "Kapasite Artışı Yatırımı"), "operations", 80, "medium"),
        (_disclosure(5, "Genel Bilgilendirme"), "other", 0, "low"),
    ],
)
def test_kap_disclosure_classifier(disclosure, category, score, severity):
    assert classify_kap_disclosure(disclosure) == (category, score, severity)


@pytest.mark.unit
def test_corrective_disclosure_increases_non_max_score():
    disclosure = _disclosure(6, "Yeni İhale Sonucu", corrective=True)
    assert classify_kap_disclosure(disclosure) == ("commercial", 90, "high")


@pytest.mark.unit
def test_alert_service_emits_only_new_important_events_and_uses_retryable_outbox(tmp_path):
    important = _disclosure(101, "Kar Payı Dağıtımı")
    routine = _disclosure(102, "Genel Bilgilendirme")
    fake = FakeKapService({"THYAO.IS": _ok_result("THYAO.IS", (important, routine))})
    watchlist = WatchlistStore(tmp_path / "watchlist.json", ["THYAO.IS"])
    state = AlertStateStore(tmp_path / "alerts.json")
    service = KapWatchlistAlertService(
        watchlist,
        state,
        kap_service=fake,
        lookback_days=7,
        min_score=80,
    )

    first = service.check_watchlist(now=datetime(2026, 8, 24, 11, 0))
    second = service.check_watchlist(now=datetime(2026, 8, 24, 11, 5))

    assert [alert.disclosure_id for alert in first.alerts] == [101]
    assert first.alerts[0].ticker == "THYAO.IS"
    assert first.alerts[0].source == "KAP"
    assert first.alerts[0].severity == "critical"
    assert second.alerts == ()
    assert set(state.seen_ids()) == {"KAP:THYAO.IS:101", "KAP:THYAO.IS:102"}
    assert [item["alert_id"] for item in state.pending()] == ["KAP:THYAO.IS:101"]
    assert state.history() == ()
    assert service.acknowledge_alerts(["KAP:THYAO.IS:101"]) == 1
    assert state.pending() == ()
    assert len(state.history()) == 1
    assert len(fake.calls) == 2
    assert fake.calls[0]["include_attachments"] is False
    assert callable(fake.calls[0]["significance_key"])


@pytest.mark.unit
def test_pending_outbox_survives_restart_until_acknowledged(tmp_path):
    disclosure = _disclosure(111, "Temettü Ödemesi")
    result = _ok_result("THYAO.IS", (disclosure,))
    watchlist_path = tmp_path / "watchlist.json"
    state_path = tmp_path / "alerts.json"

    first = KapWatchlistAlertService(
        WatchlistStore(watchlist_path, ["THYAO.IS"]),
        AlertStateStore(state_path),
        kap_service=FakeKapService({"THYAO.IS": result}),
    )
    assert len(first.check_watchlist(now=datetime(2026, 8, 24, 10, 0)).alerts) == 1

    restarted = KapWatchlistAlertService(
        WatchlistStore(watchlist_path),
        AlertStateStore(state_path),
        kap_service=FakeKapService({"THYAO.IS": result}),
    )
    assert restarted.check_watchlist(now=datetime(2026, 8, 24, 10, 5)).alerts == ()
    assert [item["alert_id"] for item in restarted.pending_alerts()] == ["KAP:THYAO.IS:111"]
    assert restarted.acknowledge_alerts(["KAP:THYAO.IS:111"]) == 1
    assert restarted.pending_alerts() == ()


@pytest.mark.unit
def test_alert_service_uses_borsa_istanbul_calendar_for_aware_utc_time(tmp_path):
    disclosure = _disclosure(151, "Temettü Ödemesi")
    fake = FakeKapService({"THYAO.IS": _ok_result("THYAO.IS", (disclosure,))})
    service = KapWatchlistAlertService(
        WatchlistStore(tmp_path / "watchlist.json", ["THYAO.IS"]),
        AlertStateStore(tmp_path / "alerts.json"),
        kap_service=fake,
    )

    batch = service.check_watchlist(now=datetime(2026, 8, 23, 21, 30, tzinfo=timezone.utc))

    assert batch.checked_at.date().isoformat() == "2026-08-24"
    assert str(batch.checked_at.tzinfo) == "Europe/Istanbul"
    assert fake.calls[0]["end_date"].isoformat() == "2026-08-24"


@pytest.mark.unit
def test_alert_dedup_survives_service_restart(tmp_path):
    disclosure = _disclosure(201, "Bedelsiz Sermaye Artırımı")
    result = _ok_result("ASELS.IS", (disclosure,))
    watchlist_path = tmp_path / "watchlist.json"
    state_path = tmp_path / "alerts.json"

    first = KapWatchlistAlertService(
        WatchlistStore(watchlist_path, ["ASELS.IS"]),
        AlertStateStore(state_path),
        kap_service=FakeKapService({"ASELS.IS": result}),
    )
    assert len(first.check_watchlist(now=datetime(2026, 8, 24, 10, 0)).alerts) == 1

    restarted = KapWatchlistAlertService(
        WatchlistStore(watchlist_path),
        AlertStateStore(state_path),
        kap_service=FakeKapService({"ASELS.IS": result}),
    )
    assert restarted.check_watchlist(now=datetime(2026, 8, 24, 10, 5)).alerts == ()


@pytest.mark.unit
def test_seen_capacity_must_cover_one_full_poll_across_watchlist(tmp_path):
    fake = FakeKapService(
        {
            "THYAO.IS": _ok_result("THYAO.IS", ()),
            "ASELS.IS": _ok_result("ASELS.IS", ()),
        }
    )
    service = KapWatchlistAlertService(
        WatchlistStore(tmp_path / "watchlist.json", ["THYAO.IS", "ASELS.IS"]),
        AlertStateStore(tmp_path / "alerts.json", seen_limit=150),
        kap_service=fake,
        max_disclosures_per_ticker=100,
    )

    with pytest.raises(ValueError, match="alert_seen_limit"):
        service.check_watchlist(now=datetime(2026, 8, 24, 11, 0))
    assert fake.calls == []


@pytest.mark.unit
def test_seen_capacity_tracks_tickers_across_subset_polls(tmp_path):
    fake = FakeKapService(
        {
            "THYAO.IS": _ok_result("THYAO.IS", ()),
            "ASELS.IS": _ok_result("ASELS.IS", ()),
        }
    )
    service = KapWatchlistAlertService(
        WatchlistStore(tmp_path / "watchlist.json"),
        AlertStateStore(tmp_path / "alerts.json", seen_limit=1),
        kap_service=fake,
        max_disclosures_per_ticker=1,
    )

    service.check_watchlist(tickers=["THYAO.IS"], now=datetime(2026, 8, 24, 11, 0))
    with pytest.raises(ValueError, match="alert_seen_limit"):
        service.check_watchlist(tickers=["ASELS.IS"], now=datetime(2026, 8, 24, 11, 5))
    assert len(fake.calls) == 1


@pytest.mark.unit
def test_kap_unavailable_is_status_not_fabricated_alert(tmp_path):
    unavailable = KapDisclosureResult(
        status="unavailable",
        ticker="TUPRS.IS",
        kap_ticker="TUPRS",
        start_date="2026-08-17",
        end_date="2026-08-24",
        message="KAP verisi geçici olarak alınamadı.",
    )
    service = KapWatchlistAlertService(
        WatchlistStore(tmp_path / "watchlist.json", ["TUPRS.IS"]),
        AlertStateStore(tmp_path / "alerts.json"),
        kap_service=FakeKapService({"TUPRS.IS": unavailable}),
    )

    batch = service.check_watchlist(now=datetime(2026, 8, 24, 11, 0))
    assert batch.alerts == ()
    assert batch.source_statuses[0].status == "unavailable"
    assert "geçici" in batch.source_statuses[0].message


@pytest.mark.unit
def test_alerts_are_sorted_by_severity_then_score(tmp_path):
    medium = _disclosure(301, "Kapasite Artışı")
    critical = _disclosure(302, "Temettü Ödemesi")
    high = _disclosure(303, "Yeni Sözleşme")
    service = KapWatchlistAlertService(
        WatchlistStore(tmp_path / "watchlist.json", ["THYAO.IS"]),
        AlertStateStore(tmp_path / "alerts.json"),
        kap_service=FakeKapService(
            {"THYAO.IS": _ok_result("THYAO.IS", (medium, critical, high))}
        ),
    )
    batch = service.check_watchlist(now=datetime(2026, 8, 24, 11, 0))
    assert [alert.disclosure_id for alert in batch.alerts] == [302, 303, 301]


@pytest.mark.unit
def test_history_limit_keeps_highest_priority_delivered_alerts(tmp_path):
    state = AlertStateStore(tmp_path / "alerts.json", history_limit=1, seen_limit=10)
    medium = _alert(401, "Kapasite Artışı", "medium", 80)
    critical = _alert(402, "Finansal Sonuçlar", "critical", 100)

    claimed = state.claim([medium.alert_id, critical.alert_id], [medium, critical])
    assert {alert.alert_id for alert in claimed} == {medium.alert_id, critical.alert_id}
    assert state.acknowledge([medium.alert_id, critical.alert_id]) == 2

    history = state.history()
    assert len(history) == 1
    assert history[0]["alert_id"] == critical.alert_id


@pytest.mark.unit
def test_corrupt_alert_state_fails_closed_instead_of_realerting_everything(tmp_path):
    state_path = tmp_path / "alerts.json"
    state_path.write_text("{broken", encoding="utf-8")
    state = AlertStateStore(state_path)
    with pytest.raises(ValueError, match="invalid JSON state file"):
        state.seen_ids()


@pytest.mark.unit
def test_semantically_corrupt_alert_state_missing_fields_fails_closed(tmp_path):
    state_path = tmp_path / "alerts.json"
    state_path.write_text('{"version": 2}', encoding="utf-8")
    state = AlertStateStore(state_path)
    with pytest.raises(ValueError, match="invalid alert state schema"):
        state.seen_ids()


@pytest.mark.unit
def test_factory_uses_phase10_config_paths_and_limits(tmp_path):
    config = {
        "watchlist_path": str(tmp_path / "watchlist.json"),
        "alert_state_path": str(tmp_path / "alerts.json"),
        "default_tickers": ["THYAO.IS"],
        "alert_history_limit": 12,
        "alert_seen_limit": 100,
        "kap_timeout_seconds": 1.5,
        "kap_alert_lookback_days": 9,
        "kap_alert_min_score": 85,
        "kap_alert_max_disclosures": 50,
        "kap_alerts_enabled": True,
    }
    service = create_watchlist_alert_service(config)
    assert service.watchlist.list() == ("THYAO.IS",)
    assert service.state.history_limit == 12
    assert service.state.seen_limit == 100
    assert service.lookback_days == 9
    assert service.min_score == 85
    assert service.max_disclosures_per_ticker == 50
