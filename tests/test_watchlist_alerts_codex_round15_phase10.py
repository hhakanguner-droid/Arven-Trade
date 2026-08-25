"""Regression tests for Phase 10 Codex round 15 fixes."""

from datetime import datetime
from types import SimpleNamespace

import pytest

import tradingagents.alerts.service as alert_service
from tradingagents.alerts.phase10_hardening import install as install_phase10_hardening
from tradingagents.dataflows.kap.models import KapDisclosure, KapDisclosureResult


def _disclosure(subject: str, summary: str = "", *, disclosure_id: int = 1) -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 25, 9, 0),
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
def test_standalone_split_subject_survives_nonempty_summary():
    disclosure = _disclosure(
        "Bölünme",
        "Süreç takvimi açıklanmıştır.",
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "mna",
        90,
        "high",
    )


@pytest.mark.unit
def test_named_company_buyer_in_purchase_tender_is_not_mna():
    disclosure = _disclosure("ABC A.Ş.'nin Satın Alma İhalesi")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "commercial",
        85,
        "high",
    )


@pytest.mark.unit
def test_management_object_can_be_separated_from_devraldi_by_modifier():
    disclosure = _disclosure("İştirak yönetimini tamamen devraldı")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "governance",
        65,
        "low",
    )


@pytest.mark.unit
def test_possessive_property_right_is_not_physical_facility():
    disclosure = _disclosure("Üst Hakkımızın Tesisi")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "other",
        0,
        "low",
    )


@pytest.mark.unit
def test_company_possessor_does_not_override_debt_split_context():
    disclosure = _disclosure("Şirketin Kredi Borçlarının Bölünmesi")
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "financing",
        75,
        "medium",
    )


@pytest.mark.unit
def test_purchase_target_scan_stops_at_completed_procurement_object():
    disclosure = _disclosure(
        "Satın alınan makineler şirket tesisinde kullanılacaktır"
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "operations",
        80,
        "medium",
    )


@pytest.mark.unit
def test_unrelated_security_term_in_summary_does_not_suppress_facility():
    disclosure = _disclosure(
        "Güneş Enerjisi Tesisi",
        "Proje finansmanı için teminat görüşmeleri sürmektedir.",
    )
    assert alert_service.classify_kap_disclosure(disclosure) == (
        "operations",
        80,
        "medium",
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("ABC Enerji A.Ş.'nin Satın Alınması", ("mna", 90, "high")),
        ("İştirak paylarını tamamen devraldı", ("mna", 90, "high")),
        ("Üst Yapı Tesisi Hakkında", ("operations", 80, "medium")),
        ("Üretim şirketi iki şirkete bölündü", ("mna", 90, "high")),
        ("Satın Alınan Elektrik Dağıtım Şirketi", ("mna", 90, "high")),
    ],
)
def test_round15_fixes_preserve_prior_positive_semantics(subject, expected):
    assert alert_service.classify_kap_disclosure(_disclosure(subject)) == expected


class _RankingKapService:
    """Small fake that exercises the real caller-provided KAP selection key."""

    def __init__(self):
        self.raw = (
            SimpleNamespace(
                index=101,
                subject="Finansal Sonuçlar",
                summary="",
                disclosure_type="FR",
                is_corrective=False,
                publish_datetime=datetime(2026, 8, 24, 9, 0),
                company_name="Test Şirketi A.Ş.",
                url="https://www.kap.org.tr/tr/Bildirim/101",
                has_attachment=False,
            ),
            SimpleNamespace(
                index=102,
                subject="Şirket Paylarının Satın Alınması",
                summary="",
                disclosure_type="ODA",
                is_corrective=False,
                publish_datetime=datetime(2026, 8, 25, 8, 30),
                company_name="Test Şirketi A.Ş.",
                url="https://www.kap.org.tr/tr/Bildirim/102",
                has_attachment=False,
            ),
        )

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
        assert significance_key is not None
        selected = sorted(self.raw, key=significance_key, reverse=True)[
            :max_disclosures
        ]
        mapped = tuple(
            KapDisclosure(
                published_at=item.publish_datetime,
                company=item.company_name,
                ticker="THYAO",
                subject=item.subject,
                disclosure_type=item.disclosure_type,
                url=item.url,
                has_attachment=item.has_attachment,
                is_corrective=item.is_corrective,
                disclosure_id=item.index,
                summary=item.summary,
            )
            for item in selected
        )
        return KapDisclosureResult(
            status="ok",
            ticker=ticker,
            kap_ticker="THYAO",
            start_date=str(start_date),
            end_date=str(end_date),
            message="ok",
            disclosures=mapped,
            total_found=len(self.raw),
        )


@pytest.mark.unit
def test_seen_high_score_cannot_starve_newer_unseen_important_disclosure(tmp_path):
    watchlist = alert_service.WatchlistStore(
        tmp_path / "watchlist.json",
        seed_tickers=("THYAO.IS",),
    )
    state = alert_service.AlertStateStore(
        tmp_path / "alerts.json",
        history_limit=10,
        seen_limit=10,
    )
    # Yesterday's score-100 disclosure is already observed.
    assert state.claim(["KAP:101"], ()) == ()

    alerts = alert_service.KapWatchlistAlertService(
        watchlist,
        state,
        kap_service=_RankingKapService(),
        min_score=80,
        max_disclosures_per_ticker=1,
    )

    batch = alerts.check_watchlist(now=datetime(2026, 8, 25, 9, 0))

    assert [item.alert_id for item in batch.alerts] == ["KAP:102"]
    assert [item.title for item in batch.alerts] == [
        "Şirket Paylarının Satın Alınması"
    ]


@pytest.mark.unit
def test_explicit_round14_reinstall_reapplies_round15_layer():
    install_phase10_hardening(alert_service)

    assert (
        alert_service._satin_alma_is_acquisition._phase10_round15_version
        == "phase10-round15"
    )
    assert (
        alert_service.KapWatchlistAlertService.check_watchlist._phase10_round15_version
        == "phase10-round15"
    )
