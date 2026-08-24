"""Configuration edge cases for Phase 10 watchlist alerts."""

import importlib
import os
from datetime import datetime

import pytest

import tradingagents.alerts.__main__ as alert_cli
from tradingagents.alerts.models import AlertSourceStatus, WatchlistAlertBatch
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


@pytest.mark.unit
def test_empty_phase10_path_env_vars_fall_back_to_defaults(monkeypatch):
    import tradingagents.default_config as default_config

    monkeypatch.setenv("TRADINGAGENTS_WATCHLIST_PATH", "")
    monkeypatch.setenv("TRADINGAGENTS_ALERT_STATE_PATH", "")
    reloaded = importlib.reload(default_config)

    home = os.path.join(os.path.expanduser("~"), ".tradingagents")
    assert reloaded.DEFAULT_CONFIG["watchlist_path"] == os.path.join(home, "watchlist.json")
    assert reloaded.DEFAULT_CONFIG["alert_state_path"] == os.path.join(
        home, "alerts", "kap_alerts.json"
    )


@pytest.mark.unit
def test_cli_check_returns_failure_when_every_kap_source_fails(monkeypatch, capsys):
    batch = WatchlistAlertBatch(
        checked_at=datetime(2026, 8, 24, 11, 0),
        source_statuses=(
            AlertSourceStatus(
                ticker="THYAO.IS",
                source="KAP",
                status="unavailable",
                message="KAP geçici olarak kullanılamıyor.",
            ),
        ),
    )

    class FakeService:
        def check_watchlist(self):
            return batch

    monkeypatch.setattr(alert_cli, "create_watchlist_alert_service", lambda: FakeService())

    assert alert_cli.main(["check", "--json"]) == 1
    assert '"status": "unavailable"' in capsys.readouterr().out


@pytest.mark.unit
def test_cli_disabled_check_is_not_reported_as_failure(monkeypatch):
    batch = WatchlistAlertBatch(
        checked_at=datetime(2026, 8, 24, 11, 0),
        source_statuses=(
            AlertSourceStatus(
                ticker="*",
                source="KAP",
                status="disabled",
                message="disabled",
            ),
        ),
    )

    class FakeService:
        def check_watchlist(self):
            return batch

    monkeypatch.setattr(alert_cli, "create_watchlist_alert_service", lambda: FakeService())
    assert alert_cli.main(["check", "--json"]) == 0
