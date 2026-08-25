"""Regression matrix for the role-aware Phase 10 KAP semantic parser."""
from __future__ import annotations

from datetime import datetime

import pytest

import tradingagents.alerts.service as alert_service
from tradingagents.dataflows.kap.models import KapDisclosure


def _disclosure(subject: str, summary: str = "", *, disclosure_id: int = 1) -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 25, 14, 30),
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
        ("ABC A.Ş.'nin iştiraki aracılığıyla makine satın alındı", ("operations", 80, "medium")),
        ("ABC şirketi ihalede satın aldı ve enerji şirketiyle görüştük", ("commercial", 85, "high")),
        ("Bedelsiz hizmet pay sahiplerine sunulacaktır", ("other", 0, "low")),
        ("Şirket üretim hatlarını yeni yazılım ile birleştirdi", ("operations", 80, "medium")),
        ("Ürüne yönelik geri alım programı", ("other", 0, "low")),
        ("Kullandığımız yöntemle satın aldığımız ve hizmet sağladığımız şirket", ("mna", 90, "high")),
        ("ABC Enerji A.Ş.'nin satın alma müdürlüğü", ("other", 0, "low")),
        ("Ortaklığın arsa satışı", ("other", 0, "low")),
        ("Portföy devir işlem adedi arttı", ("other", 0, "low")),
        ("Makine satın alımı ABC şirketiyle yapılacaktır", ("operations", 80, "medium")),
        ("Şirket üretim hattı ikiye bölündü", ("operations", 80, "medium")),
        ("Şirket Satın Alımı", ("mna", 90, "high")),
        ("Şirket Satın Alma İşlemi", ("mna", 90, "high")),
        ("Motor fabrikası devri", ("mna", 90, "high")),
        ("ABC Motor A.Ş. paylarının devri", ("mna", 90, "high")),
        ("Yönetim Kurulu marka devri kararı aldı", ("mna", 90, "high")),
        ("Ortaklık çalışanlarının ücret oranı değişti", ("other", 0, "low")),
    ],
)
def test_role_parser_closes_latest_exact_head_findings(subject, expected):
    assert alert_service.classify_kap_disclosure(_disclosure(subject)) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("ABC şirketinin enerji iştiraki aracılığıyla makine satın alındı", ("operations", 80, "medium")),
        ("ABC şirketi ihalede satın aldı ve enerji şirketi iflas etti", ("commercial", 85, "high")),
        ("Bedelsiz kullanım süresi artırılacaktır", ("other", 0, "low")),
        ("Şirket depoları için bağlı ortaklıklarını birleştirdi", ("mna", 90, "high")),
        ("Ürün için geri alım programı", ("other", 0, "low")),
        ("Satın aldığımız ve Türkiye'de kurulmuş şirket", ("mna", 90, "high")),
        ("ABC firması satın alma müdürlüğü", ("other", 0, "low")),
        ("Ortaklığın gayrimenkul satışı", ("other", 0, "low")),
        ("Portföy devir adedi arttı", ("other", 0, "low")),
        ("Hammadde satın alımı ABC şirketinden yapılacaktır", ("operations", 80, "medium")),
        ("ABC şirketinin enerji iştiraki satın alındı", ("mna", 90, "high")),
        ("ABC Şirketinin makineleri satın alındı", ("operations", 80, "medium")),
        ("Makine şirket tarafından satın alındı", ("operations", 80, "medium")),
        ("Makine şirket tarafından devralındı", ("operations", 80, "medium")),
        ("Kullanım hakkı bulunan yeni tesis kiraya verildi", ("operations", 80, "medium")),
        ("Kullanım hakkı yenilendi ve yeni tesis kurulacaktır", ("operations", 80, "medium")),
        ("Şirket üretim hatlarının birleştirilmesi", ("operations", 80, "medium")),
        ("Şirketlerin depoları birleşme sonrasında kullanılacaktır", ("mna", 90, "high")),
        ("Pay ihracı ve ürün geri alım programı", ("other", 0, "low")),
        ("Tahvil ihracı ve pay geri alım programı", ("ownership", 90, "high")),
        ("Gayrimenkul geri alım hakkı", ("other", 0, "low")),
        ("Geri Alım Programı", ("ownership", 90, "high")),
        ("Ortaklığın satışı", ("ownership", 80, "medium")),
        ("Ortaklığın tamamının satışı", ("ownership", 80, "medium")),
        ("Makine Satın Alımı", ("operations", 80, "medium")),
        ("Şirket yeni makine satın aldı", ("other", 0, "low")),
        ("ABC Şirketi'nin satın aldığı makineler", ("operations", 80, "medium")),
        ("ABC Enerji A.Ş.'nin satın aldığı makineler", ("other", 0, "low")),
        ("Satın alınan enerji şirketinin ürettiği elektrik tesislerimizde kullanılacaktır", ("mna", 90, "high")),
        ("Devralınacak olan halka açık ve yabancı sermayeli anonim şirket", ("mna", 90, "high")),
        ("Bağlı ortaklığı yönetim kurulu kararıyla devraldı", ("mna", 90, "high")),
        ("İştirak yönetimini bağlı ortaklığı adına devraldı", ("governance", 65, "low")),
        ("Tesis yönetimini devraldı", ("governance", 65, "low")),
        ("Kullanım hakkının bedelsiz olarak tesisi", ("other", 0, "low")),
        ("Kısmi Bölünme İşlemi", ("mna", 90, "high")),
        ("Bölünmüş dosya arşivi hakkında", ("other", 0, "low")),
        ("Şirketin Kredi Borçlarının Bölünmesi", ("financing", 75, "medium")),
        ("Gayrimenkul Devri", ("mna", 90, "high")),
        ("Bedelli artırım kararı", ("capital", 95, "critical")),
    ],
)
def test_role_parser_preserves_prior_regression_contract(subject, expected):
    assert alert_service.classify_kap_disclosure(_disclosure(subject)) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        ("Sözleşmenin 6. maddesi tadil edilmiştir", ("other", 0, "low")),
        ("Tedarik sözleşmesi tadil edildi", ("commercial", 85, "high")),
        ("Sözleşmenin tedarik maddesi tadil edildi", ("commercial", 85, "high")),
        ("Sözleşmenin tedarik maddesi 2 kez tadil edildi", ("commercial", 85, "high")),
    ],
)
def test_articles_reference_is_structural_not_clause_wide(summary, expected):
    disclosure = _disclosure("Esas Sözleşme Tadili", summary)
    assert alert_service.classify_kap_disclosure(disclosure) == expected
