"""Regression tests for the final Phase 10 semantic/state hardening pass."""

import json
from datetime import datetime

import pytest

from tradingagents.alerts.service import AlertStateStore, classify_kap_disclosure
from tradingagents.dataflows.kap.models import KapDisclosure


def _disclosure(subject: str) -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 24, 16, 30),
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


@pytest.mark.unit
@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("Şirketimiz yönetim görevini devraldı", ("governance", 65, "low")),
        ("Yönetim görevini devraldı", ("governance", 65, "low")),
        ("İştirak paylarını devraldı", ("mna", 90, "high")),
    ],
)
def test_role_takeovers_do_not_become_acquisitions(subject, expected):
    assert classify_kap_disclosure(_disclosure(subject)) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("İki üretim şirketi birleşti", ("mna", 90, "high")),
        ("Şirket üretim hatlarını birleştirdi", ("operations", 80, "medium")),
        ("Üretim şirketi iki şirkete bölündü", ("mna", 90, "high")),
        ("Şirket üretim hattı ikiye bölündü", ("operations", 80, "medium")),
        ("Kredi Borçlarının İki Gruba Bölünmesi", ("financing", 75, "medium")),
        ("Kısmi Bölünme İşlemi", ("mna", 90, "high")),
    ],
)
def test_corporate_restructuring_requires_target_context(subject, expected):
    assert classify_kap_disclosure(_disclosure(subject)) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("Ürün Geri Alım Programı", ("other", 0, "low")),
        ("Tahvil Geri Alım Programı", ("financing", 75, "medium")),
        ("Geri Alım Programı", ("ownership", 90, "high")),
        ("Pay Geri Alım Programı", ("ownership", 90, "high")),
    ],
)
def test_repurchase_programs_distinguish_shares_products_and_debt(subject, expected):
    assert classify_kap_disclosure(_disclosure(subject)) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "subject",
    [
        "Varlığın Satın Alınması",
        "Ortaklığın Satın Alınması",
        "ABC Enerji A.Ş.'nin Satın Alınması",
        "Satın Alınan Elektrik Dağıtım Şirketi",
    ],
)
def test_acquisition_targets_survive_softening_and_sector_qualifiers(subject):
    assert classify_kap_disclosure(_disclosure(subject)) == ("mna", 90, "high")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("Elektrik Enerjisi Satın Alımı İhalesi", ("commercial", 85, "high")),
        ("Şirket yeni makine satın aldı", ("other", 0, "low")),
    ],
)
def test_procurement_stays_outside_mna(subject, expected):
    assert classify_kap_disclosure(_disclosure(subject)) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "subject",
    [
        "Üst Hakkı Tesis Edilmesi",
        "Geçit Hakkı Tesisi",
        "İpotek Tesis Edilmesi",
    ],
)
def test_property_right_creation_is_not_a_physical_facility(subject):
    assert classify_kap_disclosure(_disclosure(subject)) == ("other", 0, "low")


@pytest.mark.unit
@pytest.mark.parametrize(
    "subject",
    [
        "Hizmet İşletmesi Devri",
        "Hizmet Şirketinin Devri",
    ],
)
def test_hizmet_transfer_is_not_confused_with_speed(subject):
    assert classify_kap_disclosure(_disclosure(subject)) == ("mna", 90, "high")


@pytest.mark.unit
def test_rotational_speed_devir_remains_non_mna():
    assert classify_kap_disclosure(_disclosure("Tesis Motor Devir Hızı Hakkında")) == (
        "operations",
        80,
        "medium",
    )


@pytest.mark.unit
def test_legacy_pending_share_class_duplicates_are_canonicalized_before_delivery(tmp_path):
    path = tmp_path / "alerts.json"
    payload = {
        "version": 2,
        "seen_ids": ["KAP:ISCTR.IS:123"],
        "pending": [
            {"alert_id": "KAP:ISCTR.IS:123", "severity": "high", "score": 90},
            {"alert_id": "KAP:ISBTR.IS:123", "severity": "high", "score": 90},
        ],
        "history": [],
        "tracked_tickers": ["ISCTR.IS", "ISBTR.IS"],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    state = AlertStateStore(path, history_limit=10, seen_limit=10)
    pending = state.pending()

    assert len(pending) == 1
    assert pending[0]["alert_id"] == "KAP:123"
    assert state.seen_ids() == ("KAP:123",)

    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert [item["alert_id"] for item in persisted["pending"]] == ["KAP:123"]
