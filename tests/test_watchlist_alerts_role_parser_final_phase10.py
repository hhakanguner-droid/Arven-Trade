"""Final exact-head regressions for the Phase 10 role-aware KAP parser."""
from __future__ import annotations

from datetime import datetime

import pytest

import tradingagents.alerts.service as alert_service
from tradingagents.dataflows.kap.models import KapDisclosure


def _disclosure(subject: str, *, disclosure_id: int = 99001) -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 25, 17, 30),
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


@pytest.mark.unit
@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("Dosyalar firmama devredildi", ("other", 0, "low")),
        ("Dosyalar ortaklığıma devredildi", ("other", 0, "low")),
        ("Dosyalar işletmeme devredildi", ("other", 0, "low")),
        ("Dosyalar şirketime devredildi", ("other", 0, "low")),
        ("Devraldı mevcut krediler dahil ABC şirketini", ("mna", 90, "high")),
        ("Devraldı mevcut hasarlar dahil ABC şirketini", ("mna", 90, "high")),
        ("ABC Holding yıllar sonra bölündü", ("mna", 90, "high")),
        ("ABC Holding aylar sonra bölündü", ("mna", 90, "high")),
        ("ABC Holding seneler sonra bölündü", ("mna", 90, "high")),
        ("Ürünü kapsayacak bir şekilde planlanan geri alım programı", ("other", 0, "low")),
        ("Şirket departmanlarının birleşmesi", ("other", 0, "low")),
        ("Şirket ekipleri birleşti", ("other", 0, "low")),
        ("İki üretim şirketi birleşti", ("mna", 90, "high")),
        ("Ortaklığın dün yapılan satışı", ("ownership", 80, "medium")),
        ("Ortaklığın gerçekleştirilen satışı", ("ownership", 80, "medium")),
        ("Şirket iPhone'u satın aldı", ("other", 0, "low")),
        ("Şirket Model X'i satın aldı", ("other", 0, "low")),
        ("Veri paylaşımı devredildi", ("other", 0, "low")),
        ("Dosya paylaşımı devredildi", ("other", 0, "low")),
        ("ABC şirketini, tüm varlıklarıyla birlikte, satın aldı", ("mna", 90, "high")),
        ("Şirket ABC'yi satın aldı", ("mna", 90, "high")),
        ("Şirket XYZ'yi satın aldı", ("mna", 90, "high")),
    ],
)
def test_final_exact_head_role_bindings(subject, expected):
    assert alert_service.classify_kap_disclosure(_disclosure(subject)) == expected
