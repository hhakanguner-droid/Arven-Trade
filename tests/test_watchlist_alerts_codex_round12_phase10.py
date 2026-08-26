"""Regression tests for Phase 10 Codex round 12 and proactive semantic hardening."""

import json
from datetime import datetime

import pytest

from tradingagents.alerts.service import (
    AlertStateStore,
    KapWatchlistAlertService,
    WatchlistStore,
    classify_kap_disclosure,
)
from tradingagents.dataflows.kap.models import KapDisclosure, KapDisclosureResult


def _disclosure(subject: str, *, disclosure_id: int = 12345, summary: str = "") -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 24, 15, 30),
        company="Test Şirketi A.Ş.",
        ticker="ISCTR",
        subject=subject,
        disclosure_type="ODA",
        url=f"https://www.kap.org.tr/tr/Bildirim/{disclosure_id}",
        has_attachment=False,
        is_corrective=False,
        disclosure_id=disclosure_id,
        summary=summary,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("Şirket iki ayrı şirkete bölünmüştür", ("mna", 90, "high")),
        ("Bölünmüş Yol Yapım İşi İhalesi", ("commercial", 85, "high")),
        ("Şirket üretim hattı ikiye bölündü", ("operations", 80, "medium")),
        ("İki şirket birleştirildi", ("mna", 90, "high")),
        ("Üretim Hatlarının Birleştirilmesi", ("operations", 80, "medium")),
        ("Şirket üretim hatlarını birleştirdi", ("operations", 80, "medium")),
    ],
)
def test_corporate_restructuring_is_separated_from_operational_wording(subject, expected):
    assert classify_kap_disclosure(_disclosure(subject)) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "subject",
    [
        "Şirket Varlıkları Üzerinde Rehin Tesis Edilmesi",
        "Tesis Edilen İpotekler Hakkında",
        "Teminat Tesis Edilmesine İlişkin Açıklama",
    ],
)
def test_security_interest_tesis_wording_is_not_a_facility_alert(subject):
    assert classify_kap_disclosure(_disclosure(subject)) == ("other", 0, "low")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("Elektrik Enerjisi Satın Alımı İhalesi", ("commercial", 85, "high")),
        (
            "Elektrik Enerjisi Satın Alımı İhalesi Şirket Tarafından Sonuçlandırıldı",
            ("commercial", 85, "high"),
        ),
        ("Şirket yeni makine satın aldı", ("other", 0, "low")),
        ("Şirket satın aldı", ("other", 0, "low")),
        ("Şirket Satın Alımı", ("mna", 90, "high")),
        ("Şirket Satın Alma İşlemi", ("mna", 90, "high")),
        ("Şirket satın alındı", ("mna", 90, "high")),
        ("Payların Satın Alınması", ("mna", 90, "high")),
        ("Elektrik Dağıtım Şirketinin Satın Alınması", ("mna", 90, "high")),
        ("Şirket ABC'yi satın aldı", ("mna", 90, "high")),
        ("ABC A.Ş.'yi satın aldı", ("mna", 90, "high")),
        ("Satın Alınan Şirket Hakkında", ("mna", 90, "high")),
    ],
)
def test_purchase_wording_requires_an_acquisition_target(subject, expected):
    assert classify_kap_disclosure(_disclosure(subject)) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("Yönetim Görevini Devraldı", ("governance", 65, "low")),
        ("Şirket devraldı", ("other", 0, "low")),
        ("Şirket devralındı", ("mna", 90, "high")),
        ("Şirket X'i Devraldı", ("mna", 90, "high")),
        ("İştirak Paylarının Devralınması", ("mna", 90, "high")),
        ("Tesis Motor Devir Hızı Hakkında", ("operations", 80, "medium")),
        ("Pay Devri Hakkında", ("mna", 90, "high")),
        ("Pay Geri Alındı", ("ownership", 90, "high")),
        ("Geri Alım Programı", ("ownership", 90, "high")),
        ("Ürün Geri Alındı", ("other", 0, "low")),
        ("Ürün Geri Alım Programı", ("other", 0, "low")),
    ],
)
def test_transfer_and_repurchase_semantics_avoid_neighboring_false_positives(subject, expected):
    assert classify_kap_disclosure(_disclosure(subject)) == expected


class _SharedCompanyKapService:
    def get_disclosures(self, *, ticker, start_date, end_date, **kwargs):
        disclosure = _disclosure("Temettü Dağıtımı", disclosure_id=12345)
        return KapDisclosureResult(
            status="ok",
            ticker=ticker,
            kap_ticker="ISCTR",
            start_date=str(start_date),
            end_date=str(end_date),
            message="ok",
            disclosures=(disclosure,),
            total_found=1,
        )


def _service(tmp_path, *, state_payload=None):
    watchlist = WatchlistStore(tmp_path / "watchlist.json")
    state_path = tmp_path / "alerts.json"
    if state_payload is not None:
        state_path.write_text(json.dumps(state_payload), encoding="utf-8")
    state = AlertStateStore(state_path, history_limit=10, seen_limit=10)
    return KapWatchlistAlertService(
        watchlist,
        state,
        kap_service=_SharedCompanyKapService(),
        max_disclosures_per_ticker=1,
    )


@pytest.mark.unit
def test_same_kap_disclosure_is_deduplicated_across_share_classes(tmp_path):
    service = _service(tmp_path)

    first = service.check_watchlist(
        ["ISCTR.IS", "ISBTR.IS"],
        now=datetime(2026, 8, 24, 15, 30),
    )
    assert len(first.alerts) == 1
    assert first.alerts[0].alert_id == "KAP:12345"
    assert len(service.pending_alerts()) == 1

    second = service.check_watchlist(
        ["ISBTR.IS", "ISCTR.IS"],
        now=datetime(2026, 8, 24, 15, 31),
    )
    assert second.alerts == ()


@pytest.mark.unit
def test_legacy_ticker_scoped_seen_id_suppresses_new_company_level_id(tmp_path):
    service = _service(
        tmp_path,
        state_payload={
            "version": 2,
            "seen_ids": ["KAP:ISCTR.IS:12345"],
            "pending": [],
            "history": [],
            "tracked_tickers": ["ISCTR.IS"],
        },
    )

    batch = service.check_watchlist(
        ["ISBTR.IS"],
        now=datetime(2026, 8, 24, 15, 32),
    )
    assert batch.alerts == ()
    assert "KAP:12345" in service.state.seen_ids()
