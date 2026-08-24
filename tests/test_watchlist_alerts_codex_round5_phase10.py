"""Regression tests for the final Phase 10 Codex review findings."""

from datetime import datetime

import pytest

from tradingagents.alerts.models import WatchlistAlert
from tradingagents.alerts.service import AlertStateStore, classify_kap_disclosure
from tradingagents.dataflows.kap.models import KapDisclosure


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


def _alert(ticker: str, disclosure_id: int) -> WatchlistAlert:
    return WatchlistAlert(
        alert_id=f"KAP:{ticker}:{disclosure_id}",
        source="KAP",
        ticker=ticker,
        published_at=datetime(2026, 8, 24, 12, 0),
        title="Finansal Sonuçlar",
        summary="",
        url=f"https://www.kap.org.tr/tr/Bildirim/{disclosure_id}",
        category="financials",
        severity="critical",
        score=100,
        disclosure_id=disclosure_id,
    )


@pytest.mark.unit
def test_investor_presentation_is_not_misclassified_as_investment_event():
    assert classify_kap_disclosure(_disclosure("Yatırımcı Sunumu")) == ("other", 0, "low")
    assert classify_kap_disclosure(_disclosure("Yatırımcılarımız İçin Bilgilendirme")) == (
        "other",
        0,
        "low",
    )


@pytest.mark.unit
def test_investment_inflections_still_match_operations_event():
    assert classify_kap_disclosure(_disclosure("Yeni Yatırımı Hakkında")) == (
        "operations",
        80,
        "medium",
    )
    assert classify_kap_disclosure(_disclosure("Yeni Yatırımlar Hakkında")) == (
        "operations",
        80,
        "medium",
    )


@pytest.mark.unit
def test_delivered_history_prevents_reclaim_after_seen_id_eviction(tmp_path):
    state = AlertStateStore(tmp_path / "alerts.json", history_limit=10, seen_limit=1)
    first = _alert("THYAO.IS", 1)
    second = _alert("ASELS.IS", 2)

    assert state.claim([first.alert_id], [first]) == (first,)
    assert state.acknowledge([first.alert_id]) == 1
    assert state.claim([second.alert_id], [second]) == (second,)
    assert state.seen_ids() == (second.alert_id,)

    # A retained delivered record must remain deduplicated even after seen_ids evicts it.
    assert state.claim([first.alert_id], [first]) == ()
    assert {item["alert_id"] for item in state.history()} == {first.alert_id}
