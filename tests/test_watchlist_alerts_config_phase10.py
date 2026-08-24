"""Configuration edge cases for Phase 10 watchlist alerts."""

from datetime import datetime

import pytest

from tradingagents.alerts.service import AlertStateStore, KapWatchlistAlertService, WatchlistStore


class NeverCallKap:
    def get_disclosures(self, **kwargs):
        raise AssertionError("KAP must not be called while alerts are disabled")


@pytest.mark.unit
def test_disabled_alert_service_never_calls_kap(tmp_path):
    service = KapWatchlistAlertService(
        WatchlistStore(tmp_path / "watchlist.json", ["THYAO.IS"]),
        AlertStateStore(tmp_path / "alerts.json"),
        kap_service=NeverCallKap(),
        enabled=False,
    )

    batch = service.check_watchlist(now=datetime(2026, 8, 24, 11, 0))

    assert batch.alerts == ()
    assert len(batch.source_statuses) == 1
    assert batch.source_statuses[0].status == "disabled"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"lookback_days": 0}, "lookback_days"),
        ({"min_score": 101}, "min_score"),
        ({"max_disclosures_per_ticker": 101}, "max_disclosures_per_ticker"),
    ],
)
def test_invalid_alert_limits_fail_loudly(tmp_path, kwargs, message):
    with pytest.raises(ValueError, match=message):
        KapWatchlistAlertService(
            WatchlistStore(tmp_path / "watchlist.json"),
            AlertStateStore(tmp_path / "alerts.json"),
            **kwargs,
        )
