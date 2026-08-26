"""Regression tests for Phase 10 Codex Round 19 fixes."""

from __future__ import annotations

import importlib
from datetime import datetime

import pytest

import tradingagents.alerts.service as alert_service
from tradingagents.dataflows.kap.models import KapDisclosure, KapDisclosureResult


def _disclosure(subject: str, summary: str = "", *, disclosure_id: int = 1) -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 25, 10, 40),
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
    "subject",
    [
        "Satın alınan yazılım şirketi",
        "Satın alınan makine üreticisi şirket",
    ],
)
def test_procurement_looking_industry_nouns_can_modify_acquired_company(subject):
    assert alert_service.classify_kap_disclosure(_disclosure(subject)) == (
        "mna",
        90,
        "high",
    )


@pytest.mark.unit
def test_usage_verb_for_later_commodity_does_not_demote_acquired_energy_company():
    disclosure = _disclosure(
        "Satın alınan enerji şirketinin ürettiği elektrik "
        "tesislerimizde kullanılacaktır"
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "mna",
        90,
        "high",
    )


@pytest.mark.unit
def test_property_right_creation_accepts_productive_adverbial_modifiers():
    disclosure = _disclosure("Kullanım hakkının bedelsiz olarak tesisi")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "other",
        0,
        "low",
    )


@pytest.mark.unit
def test_passive_takeover_stops_at_completed_procurement_object():
    disclosure = _disclosure(
        "Devralınan makineler şirketimizin yeni tesisinde kullanılacaktır"
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "operations",
        80,
        "medium",
    )


@pytest.mark.unit
def test_later_purchase_clause_recognizes_preverbal_transfer_object():
    disclosure = _disclosure(
        "Şirket satın aldığı makineleri kullandı ve bağlı ortaklığı satın aldı"
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "mna",
        90,
        "high",
    )


@pytest.mark.unit
def test_transfer_object_before_separate_actor_adjunct_remains_mna():
    disclosure = _disclosure("Payları şirket adına devraldı")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "mna",
        90,
        "high",
    )


@pytest.mark.unit
def test_management_board_is_governance_object_without_decision_morphology():
    disclosure = _disclosure("İştirak yönetim kurulunu devraldı")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "governance",
        65,
        "low",
    )


@pytest.mark.unit
def test_direct_round17_reload_routes_back_through_latest_stable_chain():
    phase10 = importlib.import_module("tradingagents.alerts.phase10_hardening")
    round17 = importlib.import_module("tradingagents.alerts.round17_hardening")
    round19 = importlib.import_module("tradingagents.alerts.round19_hardening")

    phase10.install(alert_service)
    old_install = round17.install
    round17 = importlib.reload(round17)
    assert round17.install is not old_install

    round17.install(alert_service)

    assert alert_service._PHASE10_HARDENING_CHAIN_INSTALLED == "phase10-round22"
    assert alert_service._PHASE10_HARDENING_INSTALLER_IDENTITIES[2] is round17.install
    assert (
        alert_service._satin_alma_is_acquisition._phase10_round19_generation
        is round19.INSTALL_GENERATION
    )
    assert alert_service.classify_kap_disclosure(
        _disclosure("Satın alınan yazılım şirketi")
    ) == ("mna", 90, "high")


class _FlappingWatchlist:
    def __init__(self) -> None:
        self.calls = 0

    def list(self):
        self.calls += 1
        if self.calls == 1:
            return ("THYAO.IS",)
        return ("ASELS.IS",)


class _RecordingKap:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_disclosures(
        self,
        ticker,
        start_date=None,
        end_date=None,
        max_disclosures=10,
        *,
        lookback_days=30,
        include_attachments=True,
        significance_key=None,
        summary_limit=600,
    ):
        del lookback_days, include_attachments, summary_limit
        assert significance_key is not None
        self.calls.append(str(ticker))
        code = str(ticker).removesuffix(".IS")
        disclosure = KapDisclosure(
            published_at=datetime(2026, 8, 25, 10, 0),
            company=f"{code} Test A.Ş.",
            ticker=code,
            subject="Finansal Sonuçlar",
            disclosure_type="FR",
            url="https://www.kap.org.tr/tr/Bildirim/999",
            has_attachment=False,
            is_corrective=False,
            disclosure_id=999,
            summary="",
        )
        return KapDisclosureResult(
            status="ok",
            ticker=ticker,
            kap_ticker=code,
            start_date=str(start_date),
            end_date=str(end_date),
            message="ok",
            disclosures=(disclosure,),
            total_found=1,
        )


@pytest.mark.unit
def test_full_watchlist_poll_uses_one_snapshot_for_poll_and_capacity(tmp_path):
    watchlist = _FlappingWatchlist()
    kap = _RecordingKap()
    service = alert_service.KapWatchlistAlertService(
        watchlist,
        alert_service.AlertStateStore(
            tmp_path / "alerts.json",
            history_limit=10,
            seen_limit=10,
        ),
        kap_service=kap,
        min_score=80,
        max_disclosures_per_ticker=1,
    )

    service.check_watchlist(now=datetime(2026, 8, 25, 10, 45))

    assert watchlist.calls == 1
    assert kap.calls == ["THYAO.IS"]


@pytest.mark.unit
def test_round19_preserves_round18_regression_boundaries():
    cases = {
        "Satın alınan elektrik şirketin yeni tesislerinde kullanılacaktır": (
            "operations",
            80,
            "medium",
        ),
        "Satın alınan enerji şirketinin üretim tesisleri": (
            "mna",
            90,
            "high",
        ),
        "Kullanım hakkı bulunan maden tesisi": (
            "operations",
            80,
            "medium",
        ),
        "Kullanım hakkının yeniden tesisi": ("other", 0, "low"),
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
