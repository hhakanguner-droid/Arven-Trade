"""Regression tests for Phase 10 Codex classifier round 10."""

from datetime import datetime

import pytest

from tradingagents.alerts.service import classify_kap_disclosure
from tradingagents.dataflows.kap.models import KapDisclosure


def _disclosure(subject: str, *, summary: str = "") -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 24, 14, 30),
        company="Test Şirketi A.Ş.",
        ticker="THYAO",
        subject=subject,
        disclosure_type="ODA",
        url="https://www.kap.org.tr/tr/Bildirim/1",
        has_attachment=False,
        is_corrective=False,
        disclosure_id=1,
        summary=summary,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "subject",
    [
        "Şirket X'i Satın Aldı",
        "Şirket X'i Satın Alacak",
        "Şirket X'i Satın Alıyor",
        "Şirket X'in Satın Alındığına İlişkin Açıklama",
    ],
)
def test_active_acquisition_inflections_match_mna(subject):
    assert classify_kap_disclosure(_disclosure(subject)) == ("mna", 90, "high")


@pytest.mark.unit
def test_articles_amendment_summary_cannot_reactivate_commercial_contract_rule():
    disclosure = _disclosure(
        "Esas Sözleşme Tadili",
        summary="Sözleşmenin 6. maddesi tadil edilmiştir.",
    )
    assert classify_kap_disclosure(disclosure) == ("other", 0, "low")

    disclosure = _disclosure(
        "Şirket Ana Sözleşmesinin Tadili",
        summary="Sözleşmenin ilgili maddeleri güncellenmiştir.",
    )
    assert classify_kap_disclosure(disclosure) == ("other", 0, "low")


@pytest.mark.unit
def test_generic_governance_devir_is_not_mna():
    assert classify_kap_disclosure(_disclosure("Yönetim Yetki Devri")) == (
        "governance",
        65,
        "low",
    )
    assert classify_kap_disclosure(_disclosure("Görev Devri")) == ("other", 0, "low")


@pytest.mark.unit
@pytest.mark.parametrize(
    "subject",
    [
        "Pay Devri Hakkında",
        "Hisse Devri Hakkında",
        "Şirket Varlık Devri",
        "İşletme Devri",
        "İştirak Paylarının Devri",
    ],
)
def test_contextual_devir_still_matches_mna(subject):
    assert classify_kap_disclosure(_disclosure(subject)) == ("mna", 90, "high")
