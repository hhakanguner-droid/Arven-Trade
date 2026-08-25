"""Finite Phase 10 closeout gate for the last accepted Codex findings."""
from __future__ import annotations

from datetime import datetime

import pytest

import tradingagents.alerts.service as alert_service
from tradingagents.dataflows.kap.models import KapDisclosure


def _d(subject: str, summary: str = "") -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 25, 21, 0),
        company="Test Şirketi A.Ş.",
        ticker="THYAO",
        subject=subject,
        disclosure_type="ODA",
        url="https://www.kap.org.tr/tr/Bildirim/999001",
        has_attachment=False,
        is_corrective=False,
        disclosure_id=999001,
        summary=summary,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("subject", "summary", "expected"),
    [
        ("Şirket IPHONE'u Devraldı", "", ("other", 0, "low")),
        ("Esas Sözleşme Tadili", "Franchise Ana Sözleşmesinin ilgili maddeleri güncellendi", ("commercial", 85, "high")),
        ("Esas Sözleşme Tadili", "Şirketimizin Ana Sözleşmesinin ilgili maddeleri güncellendi", ("other", 0, "low")),
        ("Ana Sözleşme Tadili", "Ortaklığımızın Ana Sözleşmesinin ilgili maddeleri güncellendi", ("other", 0, "low")),
        ("Şirket ürün geri alım programı başlattı", "", ("other", 0, "low")),
        ("Ekmek geri alım programı sona erdi", "Şirket geri alım programı başlattı", ("ownership", 90, "high")),
        ("Makine şirket için satın alındı. ABC şirketini satın aldı", "", ("mna", 90, "high")),
        ("Satın aldığımız sunucunun kurulduğu şirketle iş ilişkisi", "", ("commercial", 80, "medium")),
        ("Satın aldığımız dün kurulmuş şirket", "", ("mna", 90, "high")),
        ("ABC A.S. XYZ sirketi tarafindan satin alindi", "", ("mna", 90, "high")),
        ("ABC Ltd. Sti. XYZ sirketi tarafindan satin alindi", "", ("mna", 90, "high")),
        ("ABC Şirketi'nin Yeni Satın Alma İhalesi", "", ("commercial", 85, "high")),
    ],
)
def test_phase10_finite_closeout_gate(subject, summary, expected):
    assert alert_service.classify_kap_disclosure(_d(subject, summary)) == expected


@pytest.mark.unit
def test_existing_short_ticker_devralma_compatibility_is_preserved():
    assert alert_service.classify_kap_disclosure(_d("Şirket X'i Devraldı")) == ("mna", 90, "high")
