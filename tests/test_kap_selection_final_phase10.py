"""Final Phase 10 regressions for bounded KAP disclosure selection."""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from tradingagents.dataflows.kap.service import _select_significant


def _item(name: str, minutes_ago: int):
    return SimpleNamespace(
        name=name,
        publish_datetime=datetime(2026, 8, 25, 18, 0) - timedelta(minutes=minutes_ago),
    )


@pytest.mark.unit
def test_limit_one_prefers_newest_actionable_over_newest_zero_score():
    newest_zero = _item("newest-zero", 0)
    actionable = _item("actionable", 1)
    scores = {"newest-zero": 0, "actionable": 90}

    selected = _select_significant(
        [newest_zero, actionable],
        1,
        lambda item: (scores[item.name], item.publish_datetime),
    )

    assert [item.name for item in selected] == ["actionable"]


@pytest.mark.unit
def test_limit_one_prefers_newer_actionable_over_older_higher_score():
    newer = _item("newer-90", 0)
    older = _item("older-100", 60)
    scores = {"newer-90": 90, "older-100": 100}

    selected = _select_significant(
        [older, newer],
        1,
        lambda item: (scores[item.name], item.publish_datetime),
    )

    assert [item.name for item in selected] == ["newer-90"]


@pytest.mark.unit
def test_all_zero_score_window_falls_back_to_newest_record():
    newest = _item("newest", 0)
    older = _item("older", 15)

    selected = _select_significant(
        [older, newest],
        1,
        lambda item: (0, item.publish_datetime),
    )

    assert [item.name for item in selected] == ["newest"]
