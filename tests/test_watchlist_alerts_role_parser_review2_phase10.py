"""Focused regressions for the second role-parser exact-head review."""
from __future__ import annotations

from datetime import datetime

import pytest

import tradingagents.alerts.service as alert_service
from tradingagents.dataflows.kap.models import KapDisclosure


def _disclosure(subject: str, summary: str = "", *, disclosure_id: int = 1) -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 25, 15, 15),
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


@pytest.mark.unit
@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("ABC firmasını yatırım bankası aracılığıyla satın aldı", ("mna", 90, "high")),
        (
            "ABC şirketi ihalede satın aldı ve teknoloji firması toplantıya katıldılar",
            ("commercial", 85, "high"),
        ),
        ("Bedelsiz sermaye artırımı ve intifa hakkı tesisi", ("capital", 95, "critical")),
        ("ABC A.Ş. satın alındı", ("mna", 90, "high")),
        ("Tesis yönetimini devralırken portföyü güncelledi", ("governance", 65, "low")),
        ("ABC Holding bölündü", ("mna", 90, "high")),
        ("Dosyalar ABC şirketine devredildi", ("other", 0, "low")),
        ("Yeni tesis kurulumu tamamlandı", ("operations", 80, "medium")),
    ],
)
def test_latest_role_parser_review_findings(subject, expected):
    assert alert_service.classify_kap_disclosure(_disclosure(subject)) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "summary",
    [
        "Sözleşmenin 6'ncı maddesi tadil edilmiştir",
        "Sözleşmenin 6 numaralı maddesi tadil edilmiştir",
    ],
)
def test_articles_reference_accepts_ordinal_and_numbered_forms(summary):
    assert alert_service.classify_kap_disclosure(
        _disclosure("Esas Sözleşme Tadili", summary)
    ) == ("other", 0, "low")
