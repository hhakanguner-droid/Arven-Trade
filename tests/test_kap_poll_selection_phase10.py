"""Regression coverage for bounded KAP disclosure selection in Phase 10."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from tradingagents.dataflows.kap.service import _select_significant


@dataclass
class _RawDisclosure:
    index: int
    publish_datetime: datetime
    score: int


def _score(item: object) -> tuple[int, datetime]:
    disclosure = item
    return disclosure.score, disclosure.publish_datetime  # type: ignore[attr-defined]


@pytest.mark.unit
def test_newer_disclosure_is_not_starved_by_older_higher_score_at_limit_one():
    now = datetime(2026, 8, 25, 18, 0)
    older_critical = _RawDisclosure(1, now - timedelta(days=1), 100)
    newer_high = _RawDisclosure(2, now, 90)

    selected = _select_significant(
        [older_critical, newer_high],
        1,
        significance_key=_score,
    )

    assert [item.index for item in selected] == [2]


@pytest.mark.unit
def test_bounded_selection_reserves_recent_slots_then_fills_by_significance():
    now = datetime(2026, 8, 25, 18, 0)
    items = [
        _RawDisclosure(1, now - timedelta(days=4), 100),
        _RawDisclosure(2, now - timedelta(days=3), 99),
        _RawDisclosure(3, now - timedelta(days=2), 98),
        _RawDisclosure(4, now - timedelta(days=1), 10),
        _RawDisclosure(5, now, 5),
    ]

    selected = _select_significant(items, 4, significance_key=_score)

    # Two newest records guarantee discovery progress; the remaining slots
    # preserve the strongest significance-ranked records.
    assert {item.index for item in selected} == {1, 2, 4, 5}
    assert [item.index for item in selected] == [5, 4, 2, 1]
