"""Focused closure regressions for the latest Round 23.2 Codex review."""

from __future__ import annotations

from datetime import datetime

import pytest

import tradingagents.alerts.service as alert_service
from tradingagents.dataflows.kap.models import KapDisclosure


def _disclosure(subject: str, summary: str = "", *, disclosure_id: int = 1) -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 25, 14, 20),
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
        (
            "ABC şirketinin enerji iştiraki aracılığıyla makine satın alındı",
            ("operations", 80, "medium"),
        ),
        (
            "ABC şirketi ihalede satın aldı ve enerji şirketi iflas etti",
            ("commercial", 85, "high"),
        ),
        (
            "Kullanım hakkı sona erdi ve yeni tesis inşa edilecektir",
            ("operations", 80, "medium"),
        ),
        ("Bedelsiz kullanım süresi artırılacaktır", ("other", 0, "low")),
        ("Bedelsiz hizmet limiti artırılacaktır", ("other", 0, "low")),
        (
            "Şirket depoları için bağlı ortaklıklarını birleştirdi",
            ("mna", 90, "high"),
        ),
        ("Ürün için geri alım programı", ("other", 0, "low")),
        (
            "Satın aldığımız ve Türkiye'de kurulmuş şirket",
            ("mna", 90, "high"),
        ),
        ("ABC firması satın alma müdürlüğü", ("other", 0, "low")),
        ("Ortaklığın gayrimenkul satışı", ("other", 0, "low")),
        ("Ortaklığın taşınmaz satışı", ("other", 0, "low")),
        ("Portföy devir adedi arttı", ("other", 0, "low")),
        ("Portföy devir sayısı yükseldi", ("other", 0, "low")),
        (
            "Makine satın alımı için ABC şirketi ile sözleşme imzalandı",
            ("commercial", 85, "high"),
        ),
        (
            "Hammadde satın alımı ABC şirketinden yapılacaktır",
            ("operations", 80, "medium"),
        ),
    ],
)
def test_round23_2_latest_review_closure(subject, expected):
    assert alert_service.classify_kap_disclosure(_disclosure(subject)) == expected


@pytest.mark.unit
def test_contract_first_commercial_clause_is_not_articles_reference():
    disclosure = _disclosure(
        "Esas Sözleşme Tadili",
        "Sözleşmenin tedarik maddesi tadil edildi",
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "commercial",
        85,
        "high",
    )


@pytest.mark.unit
def test_numbered_articles_reference_remains_suppressed():
    disclosure = _disclosure(
        "Esas Sözleşme Tadili",
        "Sözleşmenin 6. maddesi tadil edilmiştir",
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "other",
        0,
        "low",
    )
