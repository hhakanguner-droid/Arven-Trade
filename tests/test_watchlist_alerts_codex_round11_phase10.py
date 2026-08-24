"""Regression tests for Phase 10 Codex classifier round 11."""

from datetime import datetime

import pytest

from tradingagents.alerts.service import classify_kap_disclosure
from tradingagents.dataflows.kap.models import KapDisclosure


def _disclosure(subject: str, *, summary: str = "") -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 24, 15, 20),
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
        "Şirketin Dijital Devrimi",
        "Dijital Devrim Programı",
        "Devriye Güvenlik Hizmeti Alımı",
    ],
)
def test_devrim_and_devriye_do_not_match_mna_transfer(subject):
    assert classify_kap_disclosure(_disclosure(subject)) == ("other", 0, "low")


@pytest.mark.unit
@pytest.mark.parametrize(
    "subject",
    [
        "Pay Devri Hakkında",
        "Hisse Devredilmesi Hakkında",
        "İştirak Paylarının Devri",
    ],
)
def test_real_transfer_inflections_still_match_mna(subject):
    assert classify_kap_disclosure(_disclosure(subject)) == ("mna", 90, "high")


@pytest.mark.unit
def test_bolunmus_yol_is_not_a_corporate_split():
    assert classify_kap_disclosure(_disclosure("Bölünmüş Yol Yapım İşi İhalesi")) == (
        "commercial",
        85,
        "high",
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "subject",
    [
        "Şirketin Bölünmesi Hakkında",
        "Şirket Bölündü",
        "Kısmi Bölünme İşlemi",
    ],
)
def test_real_corporate_split_inflections_still_match_mna(subject):
    assert classify_kap_disclosure(_disclosure(subject)) == ("mna", 90, "high")


@pytest.mark.unit
@pytest.mark.parametrize(
    "subject",
    [
        "Şirket Varlıkları Üzerinde Rehin Tesis Edilmesi",
        "Taşınmazlar Üzerinde İpotek Tesis Edilmesi",
        "Teminat Tesis Edilmesine İlişkin Açıklama",
    ],
)
def test_legal_tesis_collocations_do_not_match_operations(subject):
    assert classify_kap_disclosure(_disclosure(subject)) == ("other", 0, "low")


@pytest.mark.unit
@pytest.mark.parametrize(
    "subject",
    [
        "Yeni Üretim Tesisi Yatırımı",
        "Yeni Tesis Kapasite Artışı",
        "Fabrika ve Tesis Yatırımları",
    ],
)
def test_physical_facility_context_still_matches_operations(subject):
    category, score, severity = classify_kap_disclosure(_disclosure(subject))
    assert category == "operations"
    assert score == 80
    assert severity == "medium"
