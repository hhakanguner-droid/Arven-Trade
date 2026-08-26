"""Round 23.2 root-cause regression matrix for Phase 10 KAP semantics."""

from __future__ import annotations

from datetime import datetime

import pytest

import tradingagents.alerts.service as alert_service
from tradingagents.dataflows.kap.models import KapDisclosure


def _disclosure(subject: str, summary: str = "", *, disclosure_id: int = 1) -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 25, 13, 30),
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
        ("ABC Şirketinin makineleri satın alındı", ("operations", 80, "medium")),
        ("Makine şirket tarafından satın alındı", ("operations", 80, "medium")),
        ("Makine şirket tarafından devralındı", ("operations", 80, "medium")),
        (
            "Paylar üzerinde intifa hakkının bedelsiz tesisi için işlemler yapılacaktır",
            ("other", 0, "low"),
        ),
        ("Şirket üretim hatlarının birleştirilmesi", ("operations", 80, "medium")),
        ("Müşterilere bedelsiz hizmet sağlanacaktır", ("other", 0, "low")),
        ("Bölünmüş dosya arşivi hakkında", ("other", 0, "low")),
        ("Bölünmüş veri seti yayınlandı", ("other", 0, "low")),
        ("Şirketin Yönetim Yetki Devri", ("governance", 65, "low")),
        (
            "ABC Şirketi ihalede satın aldı ve enerji şirketi fiyatları yükseldi",
            ("commercial", 85, "high"),
        ),
        ("Ortaklığın satışı", ("ownership", 80, "medium")),
        ("ABC Şirketini Satın Alma Kararı", ("mna", 90, "high")),
        ("ABC firmasını satın alma işlemi", ("mna", 90, "high")),
        ("Varlığı satın alma kararı", ("mna", 90, "high")),
        ("Satın Alma: ABC Şirketi", ("mna", 90, "high")),
        ("Devralma: ABC Şirketi", ("mna", 90, "high")),
        ("Devir: ABC Şirketi", ("mna", 90, "high")),
        ("Gayrimenkul geri alım hakkı", ("other", 0, "low")),
        ("Geri alım taahhüdü", ("other", 0, "low")),
        ("Geri Alım Programı", ("ownership", 90, "high")),
    ],
)
def test_round23_2_exact_codex_regressions(subject, expected):
    assert alert_service.classify_kap_disclosure(_disclosure(subject)) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        (
            "Devralınacak olan halka açık ve yabancı sermayeli anonim şirket",
            ("mna", 90, "high"),
        ),
        ("ABC şirketinin enerji iştiraki satın alındı", ("mna", 90, "high")),
        (
            "Kullanım hakkı bulunan yeni tesis kiraya verildi",
            ("operations", 80, "medium"),
        ),
        ("Şirket yeni makine satın aldı", ("other", 0, "low")),
        (
            "Şirket üretim hattı ve depoları birleştirdi",
            ("operations", 80, "medium"),
        ),
        ("Ortaklığın ürün satışı", ("other", 0, "low")),
        ("Gayrimenkul Devri", ("mna", 90, "high")),
        ("Marka Devri", ("mna", 90, "high")),
        ("Portföy Devri", ("mna", 90, "high")),
        ("Fabrika Devri", ("mna", 90, "high")),
        ("Tesis Devri", ("mna", 90, "high")),
        ("Bedelli artırım kararı", ("capital", 95, "critical")),
        ("Bedelsiz artırım kararı", ("capital", 95, "critical")),
        ("Bedelli artırıma katılım", ("capital", 95, "critical")),
        (
            "Tahvil ihracı ve pay geri alım programı",
            ("ownership", 90, "high"),
        ),
    ],
)
def test_round23_2_latest_exact_head_regressions(subject, expected):
    assert alert_service.classify_kap_disclosure(_disclosure(subject)) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        (
            "ABC şirketinin enerji iştiraki tarafından makine satın alındı",
            ("operations", 80, "medium"),
        ),
        (
            "Kullanım hakkı yenilendi ve yeni tesis kurulacaktır",
            ("operations", 80, "medium"),
        ),
        (
            "Müşterilere bedelsiz hizmet verilecek ve fiyatlar artırılacaktır",
            ("other", 0, "low"),
        ),
        (
            "Şirketlerin depoları birleşme sonrasında kullanılacaktır",
            ("mna", 90, "high"),
        ),
        ("Portföy devir hızı yükseldi", ("other", 0, "low")),
        ("Pay ihracı ve ürün geri alım programı", ("other", 0, "low")),
        (
            "Satın alacak olduğumuz ve Türkiye'de kurulu şirket",
            ("mna", 90, "high"),
        ),
        ("ABC firması satın alma departmanı kurdu", ("other", 0, "low")),
        ("Ortaklığın tamamının satışı", ("ownership", 80, "medium")),
        ("Ortaklığın planlanan satışı", ("ownership", 80, "medium")),
        ("Makine Satın Alımı", ("operations", 80, "medium")),
        ("Yeni ekipman satın alımı", ("operations", 80, "medium")),
        ("Hammadde satın alma kararı", ("operations", 80, "medium")),
    ],
)
def test_round23_2_current_review_root_regressions(subject, expected):
    assert alert_service.classify_kap_disclosure(_disclosure(subject)) == expected


@pytest.mark.unit
def test_articles_suppression_is_local_to_articles_segment():
    disclosure = _disclosure(
        "Esas Sözleşme Tadili",
        "Sözleşme feshedildi",
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "commercial",
        85,
        "high",
    )


@pytest.mark.unit
def test_articles_reference_still_does_not_reactivate_commercial_rule():
    disclosure = _disclosure(
        "Esas Sözleşme Tadili",
        "Sözleşmenin 6. maddesi tadil edilmiştir",
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "other",
        0,
        "low",
    )


@pytest.mark.unit
def test_independent_contract_amendment_remains_commercial_under_articles_subject():
    disclosure = _disclosure(
        "Esas Sözleşme Tadili",
        "Tedarik sözleşmesi tadil edildi",
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "commercial",
        85,
        "high",
    )


@pytest.mark.unit
def test_round23_2_preserves_consolidated_positive_and_negative_boundaries():
    cases = {
        "Satın alınan makineler şirket tesisinde kullanılacaktır": (
            "operations",
            80,
            "medium",
        ),
        "Satın alınan enerji şirketinin ürettiği elektrik tesislerimizde kullanılacaktır": (
            "mna",
            90,
            "high",
        ),
        "Bağlı ortaklığı yönetim kurulu kararıyla devraldı": (
            "mna",
            90,
            "high",
        ),
        "İştirak yönetimini bağlı ortaklığı adına devraldı": (
            "governance",
            65,
            "low",
        ),
        "Kullanım hakkının bedelsiz olarak tesisi": ("other", 0, "low"),
        "Kullanım hakkı bulunan maden tesisi": (
            "operations",
            80,
            "medium",
        ),
        "Kullanım hakkı yenilendi. Yeni tesis kurulacaktır": (
            "operations",
            80,
            "medium",
        ),
        "ABC Enerji A.Ş.'nin Satın Alınması": ("mna", 90, "high"),
        "ABC Şirketi'nin satın aldığı yeni üretim makineleri": (
            "operations",
            80,
            "medium",
        ),
        "Şirket satın aldığı makineleri kullandı ve bağlı ortaklığı satın aldı": (
            "mna",
            90,
            "high",
        ),
        "Payları şirket adına devraldı": ("mna", 90, "high"),
        "Tesis edilen kullanım hakkı": ("other", 0, "low"),
        "Kullanım hakkına konu olacak yeni tesis kurulacaktır": (
            "operations",
            80,
            "medium",
        ),
        "Şirket üretim hatlarını birleştirdi": (
            "operations",
            80,
            "medium",
        ),
        "Kısmi Bölünme İşlemi": ("mna", 90, "high"),
        "ABC A.Ş.'nin Bölünmesi": ("mna", 90, "high"),
        "Ürün Geri Alım Programı": ("other", 0, "low"),
        "Tahvil Geri Alım Programı": ("financing", 75, "medium"),
        "Ortaklık çalışanları için eğitim": ("other", 0, "low"),
    }
    for subject, expected in cases.items():
        assert alert_service.classify_kap_disclosure(_disclosure(subject)) == expected
