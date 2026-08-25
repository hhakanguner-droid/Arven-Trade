"""Regression tests for Phase 10 Codex Round 20 fixes."""

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
def test_passive_procurement_does_not_fall_back_to_older_takeover_matcher():
    disclosure = _disclosure(
        "Devralınan makineler şirketimizin yeni tesisinde kullanılacaktır"
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "operations",
        80,
        "medium",
    )


@pytest.mark.unit
def test_legal_right_bedelsiz_modifier_does_not_trigger_capital_rule():
    disclosure = _disclosure("Kullanım hakkının bedelsiz olarak tesisi")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "other",
        0,
        "low",
    )


@pytest.mark.unit
def test_locative_company_usage_does_not_turn_software_procurement_into_mna():
    disclosure = _disclosure("Satın alınan yazılım şirketimizde kullanılacaktır")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "operations",
        80,
        "medium",
    )


@pytest.mark.unit
def test_right_scan_stops_at_completed_predicate_before_new_facility():
    disclosure = _disclosure("Kullanım hakkı sona erdi. Yeni tesis kurulacaktır")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "operations",
        80,
        "medium",
    )


@pytest.mark.unit
def test_preverbal_bare_company_buyer_is_not_treated_as_purchase_object():
    disclosure = _disclosure("Bağlı ortaklık ihalede satın aldı")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "commercial",
        85,
        "high",
    )


@pytest.mark.unit
def test_plural_industry_modifier_can_lead_to_explicit_company_target():
    disclosure = _disclosure("Satın alınan endüstriyel makineler üreticisi şirket")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "mna",
        90,
        "high",
    )


@pytest.mark.unit
def test_productive_relative_production_clause_preserves_energy_company_acquisition():
    disclosure = _disclosure(
        "Satın alınan enerji şirketinin üretmiş olduğu elektrik "
        "tesislerimizde kullanılacaktır"
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "mna",
        90,
        "high",
    )


@pytest.mark.unit
def test_legal_framing_modifiers_are_allowed_inside_right_creation_phrase():
    disclosure = _disclosure("Kullanım hakkının anlaşma kapsamında yeniden tesisi")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "other",
        0,
        "low",
    )


@pytest.mark.unit
def test_reloaded_round18_direct_install_routes_through_latest_chain():
    phase10 = importlib.import_module("tradingagents.alerts.phase10_hardening")
    round18 = importlib.import_module("tradingagents.alerts.round18_hardening")
    round22 = importlib.import_module("tradingagents.alerts.round22_consolidation")

    phase10.install(alert_service)
    old_install = round18.install
    round18 = importlib.reload(round18)
    assert round18.install is not old_install

    round18.install(alert_service)

    assert alert_service._PHASE10_HARDENING_CHAIN_INSTALLED == "phase10-round22"
    assert alert_service._PHASE10_HARDENING_INSTALLER_IDENTITIES[3] is round18.install
    assert (
        alert_service._satin_alma_is_acquisition._phase10_round22_generation
        is round22.INSTALL_GENERATION
    )


@pytest.mark.unit
def test_reloaded_round19_direct_install_routes_through_latest_chain():
    phase10 = importlib.import_module("tradingagents.alerts.phase10_hardening")
    round19 = importlib.import_module("tradingagents.alerts.round19_hardening")
    round22 = importlib.import_module("tradingagents.alerts.round22_consolidation")

    phase10.install(alert_service)
    old_install = round19.install
    round19 = importlib.reload(round19)
    assert round19.install is not old_install

    round19.install(alert_service)

    assert alert_service._PHASE10_HARDENING_CHAIN_INSTALLED == "phase10-round22"
    assert alert_service._PHASE10_HARDENING_INSTALLER_IDENTITIES[4] is round19.install
    assert (
        alert_service._satin_alma_is_acquisition._phase10_round22_generation
        is round22.INSTALL_GENERATION
    )


class _ExplodingWatchlist:
    def list(self):
        raise AssertionError("disabled service must not read watchlist")


@pytest.mark.unit
def test_disabled_alert_service_does_not_read_watchlist(tmp_path):
    service = alert_service.KapWatchlistAlertService(
        _ExplodingWatchlist(),
        alert_service.AlertStateStore(
            tmp_path / "alerts.json",
            history_limit=10,
            seen_limit=10,
        ),
        enabled=False,
    )

    batch = service.check_watchlist(now=datetime(2026, 8, 25, 11, 5))
    assert batch.alerts == ()


@pytest.mark.unit
def test_round20_preserves_prior_positive_and_negative_boundaries():
    cases = {
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
        "Kullanım hakkı bulunan maden tesisi": (
            "operations",
            80,
            "medium",
        ),
        "Kullanım hakkının yeniden tesisi": ("other", 0, "low"),
        "Satın alınan enerji şirketinin üretim tesisleri": (
            "mna",
            90,
            "high",
        ),
        "Satın alınan elektrik şirketin yeni tesislerinde kullanılacaktır": (
            "operations",
            80,
            "medium",
        ),
        "Şirket satın aldığı makineleri kullandı ve bağlı ortaklığı satın aldı": (
            "mna",
            90,
            "high",
        ),
    }
    for subject, expected in cases.items():
        assert alert_service.classify_kap_disclosure(_disclosure(subject)) == expected
