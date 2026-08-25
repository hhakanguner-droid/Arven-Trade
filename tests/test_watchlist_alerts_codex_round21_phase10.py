"""Regression tests for Phase 10 Codex Round 21 fixes."""

from __future__ import annotations

import importlib
from datetime import datetime

import pytest

import tradingagents.alerts.service as alert_service
from tradingagents.dataflows.kap.models import KapDisclosure


def _disclosure(subject: str, summary: str = "", *, disclosure_id: int = 1) -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 25, 11, 0),
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
def test_singular_passive_procurement_object_does_not_leak_to_mna():
    disclosure = _disclosure(
        "Devralınan makine şirketimizin yeni tesisinde kullanılacaktır"
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "operations",
        80,
        "medium",
    )


@pytest.mark.unit
def test_bare_company_buyer_stays_buyer_with_trailing_adverb():
    disclosure = _disclosure("Bağlı ortaklık ihalede satın aldı bugün")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "commercial",
        85,
        "high",
    )


@pytest.mark.unit
def test_participial_producer_modifier_reaches_company_target():
    disclosure = _disclosure("Satın alınan makineler üreten şirket")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "mna",
        90,
        "high",
    )


@pytest.mark.unit
def test_right_scan_respects_raw_sentence_boundary_after_renewal():
    disclosure = _disclosure("Kullanım hakkı yenilendi. Yeni tesis kurulacaktır")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "operations",
        80,
        "medium",
    )


@pytest.mark.unit
def test_legal_price_neutralization_is_scoped_to_right_creation_clause():
    disclosure = _disclosure(
        "Kullanım hakkının bedelsiz olarak tesisi. "
        "Bedelsiz pay dağıtımı yapılacaktır"
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "capital",
        95,
        "critical",
    )


@pytest.mark.unit
def test_speaker_company_relative_clause_does_not_turn_commodity_purchase_into_mna():
    disclosure = _disclosure(
        "Satın alınan enerji, şirketimizin üretmiş olduğu elektrik ile "
        "birlikte kullanılacaktır"
    )
    category, score, _severity = alert_service.classify_kap_disclosure(disclosure)
    assert (category, score) != ("mna", 90)


@pytest.mark.unit
def test_existing_right_governing_port_facility_does_not_suppress_operations():
    disclosure = _disclosure("Kullanım hakkı kapsamındaki liman tesisi")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "operations",
        80,
        "medium",
    )


@pytest.mark.unit
def test_reloaded_round18_base_is_part_of_phase10_readiness_identity():
    phase10 = importlib.import_module("tradingagents.alerts.phase10_hardening")
    round18 = importlib.import_module("tradingagents.alerts.round18_hardening")
    round18_base = importlib.import_module(
        "tradingagents.alerts.round18_hardening_base"
    )

    phase10.install(alert_service)
    old_base_install = round18_base.install
    round18_base = importlib.reload(round18_base)
    assert round18_base.install is not old_base_install

    round18.install(alert_service)

    assert alert_service._PHASE10_HARDENING_CHAIN_INSTALLED == "phase10-round21"
    assert round18_base.install in alert_service._PHASE10_HARDENING_INSTALLER_IDENTITIES


@pytest.mark.unit
def test_reloaded_round19_base_is_part_of_phase10_readiness_identity():
    phase10 = importlib.import_module("tradingagents.alerts.phase10_hardening")
    round19 = importlib.import_module("tradingagents.alerts.round19_hardening")
    round19_base = importlib.import_module(
        "tradingagents.alerts.round19_hardening_base"
    )

    phase10.install(alert_service)
    old_base_install = round19_base.install
    round19_base = importlib.reload(round19_base)
    assert round19_base.install is not old_base_install

    round19.install(alert_service)

    assert alert_service._PHASE10_HARDENING_CHAIN_INSTALLED == "phase10-round21"
    assert round19_base.install in alert_service._PHASE10_HARDENING_INSTALLER_IDENTITIES


@pytest.mark.unit
def test_round21_preserves_round20_and_prior_boundaries():
    cases = {
        "Devralınan makineler şirketimizin yeni tesisinde kullanılacaktır": (
            "operations",
            80,
            "medium",
        ),
        "Kullanım hakkının bedelsiz olarak tesisi": ("other", 0, "low"),
        "Satın alınan yazılım şirketimizde kullanılacaktır": (
            "operations",
            80,
            "medium",
        ),
        "Satın alınan endüstriyel makineler üreticisi şirket": (
            "mna",
            90,
            "high",
        ),
        "Satın alınan enerji şirketinin üretmiş olduğu elektrik "
        "tesislerimizde kullanılacaktır": ("mna", 90, "high"),
        "Kullanım hakkının anlaşma kapsamında yeniden tesisi": (
            "other",
            0,
            "low",
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
    }
    for subject, expected in cases.items():
        assert alert_service.classify_kap_disclosure(_disclosure(subject)) == expected
