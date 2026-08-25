"""Closeout regressions for the final Phase 10 review findings."""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

import tradingagents.alerts.service as alert_service
from tradingagents.dataflows.kap.models import KapDisclosure
from tradingagents.dataflows.kap.service import _select_significant


def _disclosure(subject: str, summary: str = "", *, disclosure_id: int = 1) -> KapDisclosure:
    return KapDisclosure(
        published_at=datetime(2026, 8, 25, 17, 30),
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
    ("subject", "summary", "expected"),
    [
        ("Şirket iPhone'u Devraldı", "", ("other", 0, "low")),
        ("Şirket X'i Devraldı", "", ("mna", 90, "high")),
        ("Esas Sözleşme Tadili", "Distribütörlük sözleşmesinin ilgili maddeleri güncellendi", ("commercial", 85, "high")),
        ("Esas Sözleşme Tadili", "Franchise sözleşmesinin ilgili maddeleri güncellendi", ("commercial", 85, "high")),
        ("Ekmek geri alım programı", "Şirket pay geri alım programı başlattı", ("ownership", 90, "high")),
        ("Makine şirket için satın alındı", "ABC şirketini satın aldı", ("mna", 90, "high")),
        ("Satın aldığımız makinenin kurulduğu şirketle iş ilişkisi", "", ("commercial", 80, "medium")),
        ("ABC Şirketi'nin Satın Alma İhalesi", "", ("commercial", 85, "high")),
        ("ABC firmasının Satın Alma İhalesi", "", ("commercial", 85, "high")),
        ("ABC Holding'in Satın Alma İhalesi", "", ("commercial", 85, "high")),
    ],
)
def test_closeout_semantic_regressions(subject, summary, expected):
    assert alert_service.classify_kap_disclosure(_disclosure(subject, summary)) == expected


@pytest.mark.unit
def test_kap_selector_prefers_unseen_actionable_record_inside_tight_freshness_cap():
    now = datetime(2026, 8, 25, 17, 30)
    seen_newer = SimpleNamespace(publish_datetime=now)
    unseen_older = SimpleNamespace(publish_datetime=now - timedelta(minutes=1))

    priorities = {
        id(seen_newer): (False, True, 3, now.timestamp(), 90),
        id(unseen_older): (True, True, 3, (now - timedelta(minutes=1)).timestamp(), 90),
    }

    selected = _select_significant(
        [seen_newer, unseen_older],
        1,
        significance_key=lambda item: priorities[id(item)],
    )
    assert selected == [unseen_older]
