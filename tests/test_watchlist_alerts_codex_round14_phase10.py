"""Regression tests for Phase 10 Codex round 14 findings."""

import json
from datetime import datetime

import pytest

import tradingagents.alerts.service as alert_service
from tradingagents.alerts.phase10_hardening import install
from tradingagents.dataflows.kap.models import KapDisclosure


def _disclosure(subject: str) -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 24, 17, 15),
        company="Test Şirketi A.Ş.",
        ticker="THYAO",
        subject=subject,
        disclosure_type="ODA",
        url="https://www.kap.org.tr/tr/Bildirim/1",
        has_attachment=False,
        is_corrective=False,
        disclosure_id=1,
        summary="",
    )


@pytest.mark.unit
@pytest.mark.parametrize("subject", ["Bölünme", "Bölünme İşlemleri"])
def test_explicit_generic_split_subjects_remain_mna(subject):
    assert alert_service.classify_kap_disclosure(_disclosure(subject)) == (
        "mna",
        90,
        "high",
    )


@pytest.mark.unit
def test_debt_split_is_still_financing_not_mna():
    assert alert_service.classify_kap_disclosure(
        _disclosure("Kredi Borçlarının İki Gruba Bölünmesi")
    ) == ("financing", 75, "medium")


@pytest.mark.unit
def test_hakkinda_does_not_turn_physical_facility_into_property_right():
    assert alert_service.classify_kap_disclosure(
        _disclosure("Üst Yapı Tesisi Hakkında")
    ) == ("operations", 80, "medium")


@pytest.mark.unit
@pytest.mark.parametrize(
    "subject",
    [
        "Üst Hakkı Tesis Edilmesi",
        "Geçit Hakkı Tesisi",
    ],
)
def test_real_property_right_creation_stays_outside_operations(subject):
    assert alert_service.classify_kap_disclosure(_disclosure(subject)) == (
        "other",
        0,
        "low",
    )


@pytest.mark.unit
def test_named_company_buyer_in_active_relative_clause_is_not_acquisition_target():
    assert alert_service.classify_kap_disclosure(
        _disclosure("ABC Enerji A.Ş.'nin satın aldığı makineler")
    ) == ("other", 0, "low")


@pytest.mark.unit
@pytest.mark.parametrize(
    "subject",
    [
        "ABC Enerji A.Ş.'nin Satın Alınması",
        "ABC A.Ş.'yi satın aldı",
    ],
)
def test_named_company_targets_still_match_acquisition(subject):
    assert alert_service.classify_kap_disclosure(_disclosure(subject)) == (
        "mna",
        90,
        "high",
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "subject",
    [
        "İştirak yönetimini devraldı",
        "Tesis yönetimini devraldı",
        "Yönetim görevini devraldı",
    ],
)
def test_explicit_management_object_outranks_nearby_entity_noun(subject):
    assert alert_service.classify_kap_disclosure(_disclosure(subject)) == (
        "governance",
        65,
        "low",
    )


@pytest.mark.unit
def test_real_entity_takeover_still_matches_mna():
    assert alert_service.classify_kap_disclosure(
        _disclosure("İştirak paylarını devraldı")
    ) == ("mna", 90, "high")


@pytest.mark.unit
@pytest.mark.parametrize(
    "subject",
    [
        "Pay Alım Satımına İlişkin Açıklama",
        "Pay Alım Satımı Hakkında",
        "Pay Alım-Satımının Bildirilmesi",
    ],
)
def test_pay_alim_satim_inflections_match_ownership(subject):
    assert alert_service.classify_kap_disclosure(_disclosure(subject)) == (
        "ownership",
        80,
        "medium",
    )


@pytest.mark.unit
def test_legacy_pending_already_in_history_is_removed_before_delivery(tmp_path):
    path = tmp_path / "alerts.json"
    payload = {
        "version": 2,
        "seen_ids": ["KAP:ISCTR.IS:123"],
        "pending": [
            {"alert_id": "KAP:ISBTR.IS:123", "severity": "high", "score": 90},
        ],
        "history": [
            {"alert_id": "KAP:ISCTR.IS:123", "severity": "high", "score": 90},
        ],
        "tracked_tickers": ["ISCTR.IS", "ISBTR.IS"],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    state = alert_service.AlertStateStore(path, history_limit=10, seen_limit=10)

    assert state.pending() == ()
    assert state.seen_ids() == ("KAP:123",)
    assert [item["alert_id"] for item in state.history()] == ["KAP:123"]

    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["pending"] == []
    assert [item["alert_id"] for item in persisted["history"]] == ["KAP:123"]


@pytest.mark.unit
def test_stale_module_flag_does_not_block_explicit_reinstall():
    patched_matcher = alert_service._event_term_matches
    patched_loader = alert_service.AlertStateStore._load_unlocked
    original_matcher = patched_matcher._phase10_original
    original_loader = patched_loader._phase10_original

    alert_service._event_term_matches = original_matcher
    alert_service.AlertStateStore._load_unlocked = original_loader
    alert_service._PHASE10_HARDENING_INSTALLED = True

    install(alert_service)

    assert alert_service._event_term_matches is not original_matcher
    assert alert_service.AlertStateStore._load_unlocked is not original_loader
    assert (
        alert_service._event_term_matches._phase10_hardening_version
        == "phase10-round14"
    )
    assert (
        alert_service.AlertStateStore._load_unlocked._phase10_hardening_version
        == "phase10-round14"
    )
