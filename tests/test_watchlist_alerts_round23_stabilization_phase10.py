"""Round 23 root-cause stabilization regressions for Phase 10 semantics."""

from __future__ import annotations

import importlib
from datetime import datetime

import pytest

import tradingagents.alerts.service as alert_service
from tradingagents.dataflows.kap.models import KapDisclosure


def _disclosure(subject: str, summary: str = "", *, disclosure_id: int = 1) -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 25, 12, 45),
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
        ("ABC Şirketini satın aldı", ("mna", 90, "high")),
        ("ABC firmasını satın aldı", ("mna", 90, "high")),
        ("ABC Enerji A.Ş.'nin Satın Alınması", ("mna", 90, "high")),
        ("ABC Şirketi ihalede satın aldı, enerji şirketi fiyatları açıkladı", ("commercial", 85, "high")),
        ("Paylar üzerinde intifa hakkının bedelsiz tesisi", ("other", 0, "low")),
        ("Kullanım hakkına konu olacak yeni tesis kurulacaktır", ("operations", 80, "medium")),
        ("Şirket üretim hatlarını birleştirdi", ("operations", 80, "medium")),
        ("Şirket Yönetim Yetki Devri", ("governance", 65, "low")),
        ("Tesis Motor Devir Hızı Hakkında", ("operations", 80, "medium")),
        ("Elektrik Enerjisi Satın Alımı İhalesi Şirket Tarafından Sonuçlandırıldı", ("commercial", 85, "high")),
        ("Şirket devralındı", ("mna", 90, "high")),
        ("İştirak Paylarının Devralınması", ("mna", 90, "high")),
        ("İştirak yönetimini bağlı ortaklığı adına devraldı", ("governance", 65, "low")),
        ("Geri Alım Programı", ("ownership", 90, "high")),
        ("Kısmi Bölünme İşlemi", ("mna", 90, "high")),
        ("Tesis yönetimini devraldı", ("governance", 65, "low")),
        ("Ortaklık çalışanları için eğitim", ("other", 0, "low")),
        ("Ortaklık hakkında genel bilgilendirme", ("other", 0, "low")),
    ],
)
def test_round23_exact_semantic_regressions(subject, expected):
    assert alert_service.classify_kap_disclosure(_disclosure(subject)) == expected


@pytest.mark.unit
def test_articles_amendment_does_not_hide_independent_commercial_contract():
    disclosure = _disclosure(
        "Esas Sözleşme Tadili",
        "Yeni tedarik sözleşmesi imzalandı",
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "commercial",
        85,
        "high",
    )


@pytest.mark.unit
@pytest.mark.parametrize("module_name", ["round20_hardening", "round21_hardening"])
def test_reloaded_old_installer_cannot_displace_consolidated_semantics(module_name):
    phase10 = importlib.import_module("tradingagents.alerts.phase10_hardening")
    round22 = importlib.import_module("tradingagents.alerts.round22_consolidation")
    older = importlib.import_module(f"tradingagents.alerts.{module_name}")

    phase10.install(alert_service)
    old_install = older.install
    older = importlib.reload(older)
    assert older.install is not old_install

    older.install(alert_service)

    assert alert_service._PHASE10_HARDENING_CHAIN_INSTALLED == "phase10-round22"
    assert (
        alert_service._satin_alma_is_acquisition._phase10_round22_generation
        is round22.INSTALL_GENERATION
    )


@pytest.mark.unit
def test_round23_engine_preserves_round22_convergence_examples():
    cases = {
        "Satın alınan makineler şirket tesisinde kullanılacaktır": ("operations", 80, "medium"),
        "Bölünmüş Yol Yapım İşi İhalesi": ("commercial", 85, "high"),
        "Satın alınan enerji şirketinin ürettiği elektrik tesislerimizde kullanılacaktır": ("mna", 90, "high"),
        "Bağlı ortaklığı yönetim kurulu kararıyla devraldı": ("mna", 90, "high"),
        "Kullanım hakkının bedelsiz olarak tesisi": ("other", 0, "low"),
        "Pay Geri Alım İşlemleri": ("ownership", 90, "high"),
    }
    for subject, expected in cases.items():
        assert alert_service.classify_kap_disclosure(_disclosure(subject)) == expected
