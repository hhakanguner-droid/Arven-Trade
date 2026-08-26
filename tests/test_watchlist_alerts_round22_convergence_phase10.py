"""Convergence regression matrix for Phase 10 Round 22."""

from __future__ import annotations

import importlib
from datetime import datetime

import pytest

import tradingagents.alerts.service as alert_service
from tradingagents.dataflows.kap.models import KapDisclosure


def _disclosure(subject: str, summary: str = "", *, disclosure_id: int = 1) -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 25, 12, 0),
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
        ("Bağlı ortaklık ihalede satın aldı bugün. Enerji fiyatları açıklandı", ("commercial", 85, "high")),
        ("Liman tesisi üzerinde ipotek hakkı bulunmaktadır", ("operations", 80, "medium")),
        ("Bağlı ortaklık ihalede satın aldı bugün ve bağlı ortaklığı satın aldı", ("mna", 90, "high")),
        ("Devralınan makine üretimde kullanılacaktır. Devralınan yazılım şirketimizde kullanılacaktır", ("operations", 80, "medium")),
        ("ABC Şirketi ihalede satın aldı bugün", ("commercial", 85, "high")),
        ("Şirket ABC'yi satın aldı", ("mna", 90, "high")),
        ("Makineler üreten şirket satın alındı", ("mna", 90, "high")),
        ("Tesis edilen kullanım hakkı", ("other", 0, "low")),
        ("Tesis edilecek kullanım hakkı", ("other", 0, "low")),
        ("Satın alınan yenilenebilir enerji, şirketimizin üretmiş olduğu elektrik ile birlikte kullanılacaktır", ("operations", 80, "medium")),
        ("Devralınan makine şirketimizin yeni tesisinde kullanılacaktır", ("operations", 80, "medium")),
        ("Satın alınan makineler üreten şirket", ("mna", 90, "high")),
        ("Kullanım hakkı yenilendi. Yeni tesis kurulacaktır", ("operations", 80, "medium")),
        ("Satın alınan enerji, şirketimizin üretmiş olduğu elektrik ile birlikte kullanılacaktır", ("operations", 80, "medium")),
        ("Kullanım hakkı kapsamındaki liman tesisi", ("operations", 80, "medium")),
        ("Devralınan makineler şirketimizin yeni tesisinde kullanılacaktır", ("operations", 80, "medium")),
        ("Kullanım hakkının bedelsiz olarak tesisi", ("other", 0, "low")),
        ("Satın alınan yazılım şirketimizde kullanılacaktır", ("operations", 80, "medium")),
        ("Kullanım hakkı sona erdi. Yeni tesis kurulacaktır", ("operations", 80, "medium")),
        ("Bağlı ortaklık ihalede satın aldı", ("commercial", 85, "high")),
        ("Satın alınan endüstriyel makineler üreticisi şirket", ("mna", 90, "high")),
        ("Satın alınan enerji şirketinin üretmiş olduğu elektrik tesislerimizde kullanılacaktır", ("mna", 90, "high")),
        ("Kullanım hakkının anlaşma kapsamında yeniden tesisi", ("other", 0, "low")),
        ("Satın alınan yazılım şirketi", ("mna", 90, "high")),
        ("Satın alınan makine üreticisi şirket", ("mna", 90, "high")),
        ("Satın alınan enerji şirketinin ürettiği elektrik tesislerimizde kullanılacaktır", ("mna", 90, "high")),
        ("Payları şirket adına devraldı", ("mna", 90, "high")),
        ("İştirak yönetim kurulunu devraldı", ("governance", 65, "low")),
        ("Bağlı ortaklığı yönetim kurulu kararıyla devraldı", ("mna", 90, "high")),
        ("Kullanım hakkının yeniden tesisi", ("other", 0, "low")),
        ("Satın alınan enerji şirketinin üretim tesisleri", ("mna", 90, "high")),
        ("Şirketin satın aldığı makineler ve satın aldığı bağlı ortaklık", ("mna", 90, "high")),
        ("ABC Şirketi'nin satın almış olduğu makineler", ("operations", 80, "medium")),
        ("Devralınacak olan halka açık ve yabancı sermayeli anonim şirket", ("mna", 90, "high")),
        ("ABC Şirketi'nin satın aldığı yeni üretim makineleri", ("operations", 80, "medium")),
        ("Satın alınan elektrik şirketin yeni tesislerinde kullanılacaktır", ("operations", 80, "medium")),
        ("Yönetim kurulu kararıyla bağlı ortaklığı devraldı", ("mna", 90, "high")),
        ("Kullanım hakkı bulunan maden tesisi", ("operations", 80, "medium")),
        ("ABC A.Ş.'nin Bölünmesi", ("mna", 90, "high")),
        ("Devralınan halka açık şirket", ("mna", 90, "high")),
        ("Devralınacak olan yabancı şirket", ("mna", 90, "high")),
        ("Bölünme", ("mna", 90, "high")),
        ("Bölünme İşlemleri", ("mna", 90, "high")),
        ("ABC A.Ş.'nin Satın Alma İhalesi", ("commercial", 85, "high")),
        ("İştirak yönetimini tamamen devraldı", ("governance", 65, "low")),
        ("Üst Hakkımızın Tesisi", ("other", 0, "low")),
        ("Şirketin Kredi Borçlarının Bölünmesi", ("financing", 75, "medium")),
        ("Satın alınan makineler şirket tesisinde kullanılacaktır", ("operations", 80, "medium")),
        ("Güneş Enerjisi Tesisi", ("operations", 80, "medium")),
        ("Pay Alım Satımına İlişkin Açıklama", ("ownership", 80, "medium")),
        ("Pay Alım Satımı Hakkında", ("ownership", 80, "medium")),
        ("Pay Alım-Satımının Bildirilmesi", ("ownership", 80, "medium")),
        ("Hizmet İşletmesi Devri", ("mna", 90, "high")),
        ("Hizmet Şirketinin Devri", ("mna", 90, "high")),
        ("Şirketin Dijital Devrimi", ("other", 0, "low")),
        ("Üretim şirketi iki şirkete bölündü", ("mna", 90, "high")),
        ("İki üretim şirketi birleşti", ("mna", 90, "high")),
        ("Ürün Geri Alım Programı", ("other", 0, "low")),
        ("Tahvil Geri Alım Programı", ("financing", 75, "medium")),
        ("Varlığın Satın Alınması", ("mna", 90, "high")),
        ("Ortaklığın Satın Alınması", ("mna", 90, "high")),
        ("Satın Alınan Elektrik Dağıtım Şirketi", ("mna", 90, "high")),
        ("Kredi Borçlarının İki Gruba Bölünmesi", ("financing", 75, "medium")),
        ("Üst Hakkı Tesis Edilmesi", ("other", 0, "low")),
        ("Geçit Hakkı Tesisi", ("other", 0, "low")),
        ("Şirket Varlıkları Üzerinde Rehin Tesis Edilmesi", ("other", 0, "low")),
        ("Tesis Edilen İpotekler Hakkında", ("other", 0, "low")),
        ("Üst Yapı Tesisi Hakkında", ("operations", 80, "medium")),
        ("Elektrik Enerjisi Satın Alımı İhalesi", ("commercial", 85, "high")),
        ("Üretim Hatlarının Birleştirilmesi", ("operations", 80, "medium")),
        ("Bölünmüş Yol Yapım İşi İhalesi", ("commercial", 85, "high")),
        ("Şirket X'i satın aldı", ("mna", 90, "high")),
        ("Şirket X'i satın alacak", ("mna", 90, "high")),
        ("Şirket X'i satın alıyor", ("mna", 90, "high")),
        ("Yatırımcı Sunumu", ("other", 0, "low")),
        ("Cezayir'de yeni proje", ("other", 0, "low")),
        ("Esas Sözleşme Tadili", ("other", 0, "low")),
        ("Ana Sözleşme Tadili", ("other", 0, "low")),
        ("Şirket Ana Sözleşmesinin Tadili", ("other", 0, "low")),
        ("Pay Geri Alım İşlemleri", ("ownership", 90, "high")),
        ("Dosyanın Bölünmesi", ("other", 0, "low")),
        ("İpotekli liman tesisi", ("operations", 80, "medium")),
        ("Şirket ABC A.Ş.'yi satın aldı", ("mna", 90, "high")),
    ],
)
def test_consolidated_semantic_matrix(subject, expected):
    assert alert_service.classify_kap_disclosure(_disclosure(subject)) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("subject", "summary", "expected"),
    [
        ("Bölünme", "Süreç takvimi açıklanmıştır", ("mna", 90, "high")),
        ("Şirketin Bölünmesi", "Kredi borçları devredilecektir", ("mna", 90, "high")),
        ("Güneş Enerjisi Tesisi", "Proje finansmanı için teminat görüşmeleri sürmektedir", ("operations", 80, "medium")),
        ("Esas Sözleşme Tadili", "Sözleşmenin 6. maddesi tadil edilmiştir", ("other", 0, "low")),
        ("Kullanım hakkının yeniden tesisi", "Bedelsiz pay dağıtımı yapılacaktır", ("capital", 95, "critical")),
        ("Kullanım hakkının bedelsiz olarak tesisi", "Bedelsiz pay dağıtımı yapılacaktır", ("capital", 95, "critical")),
    ],
)
def test_subject_summary_boundaries(subject, summary, expected):
    assert alert_service.classify_kap_disclosure(_disclosure(subject, summary)) == expected


@pytest.mark.unit
def test_round22_semantics_are_outermost_and_non_nested():
    phase10 = importlib.import_module("tradingagents.alerts.phase10_hardening")
    round22 = importlib.import_module("tradingagents.alerts.round22_consolidation")
    semantics = importlib.import_module("tradingagents.alerts.semantic_classifier")

    phase10.install(alert_service)

    assert alert_service._PHASE10_HARDENING_CHAIN_INSTALLED == "phase10-round22"
    assert alert_service._satin_alma_is_acquisition._phase10_round22_generation is round22.INSTALL_GENERATION
    assert alert_service._satin_alma_is_acquisition._phase10_round22_semantics_generation is semantics.IMPLEMENTATION_GENERATION


@pytest.mark.unit
@pytest.mark.parametrize("module_name", ["round20_hardening", "round21_hardening"])
def test_direct_older_installer_does_not_displace_round22(module_name):
    phase10 = importlib.import_module("tradingagents.alerts.phase10_hardening")
    older = importlib.import_module(f"tradingagents.alerts.{module_name}")
    round22 = importlib.import_module("tradingagents.alerts.round22_consolidation")

    phase10.install(alert_service)
    older.install(alert_service)

    assert alert_service._PHASE10_HARDENING_CHAIN_INSTALLED == "phase10-round22"
    assert alert_service._satin_alma_is_acquisition._phase10_round22_generation is round22.INSTALL_GENERATION


@pytest.mark.unit
def test_semantic_module_reload_forces_round22_rebuild():
    phase10 = importlib.import_module("tradingagents.alerts.phase10_hardening")
    semantics = importlib.import_module("tradingagents.alerts.semantic_classifier")

    phase10.install(alert_service)
    old_generation = semantics.IMPLEMENTATION_GENERATION
    semantics = importlib.reload(semantics)
    assert semantics.IMPLEMENTATION_GENERATION is not old_generation

    phase10.install(alert_service)

    assert alert_service._satin_alma_is_acquisition._phase10_round22_semantics_generation is semantics.IMPLEMENTATION_GENERATION
    assert alert_service._PHASE10_HARDENING_CHAIN_INSTALLED == "phase10-round22"
