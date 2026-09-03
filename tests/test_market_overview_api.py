"""Tests for the market overview vendor and its FastAPI endpoints."""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from tradingagents.dataflows import market_overview
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.service.api import create_app


def _frame(closes, highs=None, lows=None):
    index = pd.date_range("2026-08-01", periods=len(closes), freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "Open": closes,
            "High": highs or closes,
            "Low": lows or closes,
            "Close": closes,
            "Volume": [1000] * len(closes),
        },
        index=index,
    )


class _FakeTicker:
    """Stands in for yfinance.Ticker, keyed by the symbol it was built with.

    ``.history()`` ignores period/interval and always returns the same frame
    for a symbol; that is enough to exercise the vendor's aggregation, error
    isolation and 52-week logic without hitting the network.
    """

    _HISTORY = {
        "USDTRY=X": _frame([34.10, 34.24]),
        "EURTRY=X": _frame([37.80, 37.98]),
        "GBPTRY=X": _frame([44.10, 44.05]),
        "CHFTRY=X": _frame([38.50, 38.72]),
        "EURUSD=X": _frame([1.111, 1.110]),
        "GBPUSD=X": _frame([1.291, 1.290]),
        "USDJPY=X": _frame([149.4, 149.8]),
        "^XU100": _frame([10700.0, 10842.15]),
        "XU030.IS": _frame([11080.0, 11205.80]),
        "XBANK.IS": _frame([14650.0, 14930.40]),
        "XUSIN.IS": _frame([22150.0, 22104.60]),
        "GC=F": _frame([3391.0, 3412.50]),
        "SI=F": _frame([41.47, 41.86]),
        "BZ=F": _frame([78.60, 78.42]),
        "BTC-USD": _frame([94500.0, 96450.0]),
        "ETH-USD": _frame([4060.0, 4128.0]),
        "ARTMS.IS": _frame(
            [39.20, 39.80, 40.60, 41.85],
            highs=[39.5, 40.1, 41.0, 42.4],
            lows=[38.9, 39.4, 40.2, 41.5],
        ),
        "DELISTED.IS": pd.DataFrame(),
    }

    def __init__(self, symbol):
        self.symbol = symbol

    def history(self, period=None, interval=None):
        return self._HISTORY.get(self.symbol, pd.DataFrame())


@pytest.fixture(autouse=True)
def _fake_yfinance(monkeypatch):
    monkeypatch.setattr(market_overview.yf, "Ticker", _FakeTicker)


def test_get_market_snapshot_covers_every_group_and_derives_gram_altin():
    snapshot = market_overview.get_market_snapshot()
    by_symbol = {q["symbol"]: q for q in snapshot["quotes"]}

    assert not snapshot["errors"]
    assert by_symbol["USDTRY"]["price"] == pytest.approx(34.24)
    # The API rounds change_pct to 2 decimals, so compare against that same
    # rounded value rather than the unrounded ratio.
    assert by_symbol["USDTRY"]["change_pct"] == round((34.24 - 34.10) / 34.10 * 100, 2)
    assert by_symbol["XU100"]["group"] == "index"
    assert by_symbol["BTCUSDT"]["currency"] == "USD"

    gram = by_symbol["GRAMALTIN"]
    expected_gram_try = 3412.50 * 34.24 / 31.1034768
    assert gram["price"] == pytest.approx(round(expected_gram_try, 2))
    assert gram["currency"] == "TRY"


def test_get_market_snapshot_group_filter_excludes_other_groups():
    snapshot = market_overview.get_market_snapshot(groups=("fx",))
    symbols = {q["symbol"] for q in snapshot["quotes"]}
    assert symbols == {"USDTRY", "EURTRY", "GBPTRY", "CHFTRY"}


def test_get_market_snapshot_reports_a_missing_instrument_without_failing_others(
    monkeypatch,
):
    monkeypatch.setitem(_FakeTicker._HISTORY, "USDTRY=X", pd.DataFrame())
    snapshot = market_overview.get_market_snapshot()
    assert any(err["symbol"] == "USDTRY" for err in snapshot["errors"])
    assert any(q["symbol"] == "EURTRY" for q in snapshot["quotes"])
    # USDTRY failed, so the gram altın derivation (needs USDTRY) is skipped too.
    assert all(q["symbol"] != "GRAMALTIN" for q in snapshot["quotes"])


def test_get_price_history_returns_points_and_period_change():
    result = market_overview.get_price_history("ARTMS.IS", "1A")
    assert result["symbol"] == "ARTMS.IS"
    assert result["range"] == "1A"
    assert len(result["points"]) == 4
    assert result["last_price"] == pytest.approx(41.85)
    assert result["period_change_pct"] == pytest.approx(
        (41.85 - 39.20) / 39.20 * 100, rel=1e-3
    )
    assert result["fifty_two_week"] == {"high": 42.4, "low": 38.9}


def test_get_price_history_rejects_unknown_range():
    with pytest.raises(ValueError):
        market_overview.get_price_history("ARTMS.IS", "3A")


def test_get_price_history_raises_no_market_data_for_empty_symbol():
    with pytest.raises(NoMarketDataError):
        market_overview.get_price_history("DELISTED.IS", "1A")


class _Service:
    def close(self):
        return None

    def health(self):
        return {"status": "ok"}


def _client():
    return TestClient(create_app(_Service(), auth_disabled=True))


def test_market_endpoint_returns_snapshot():
    response = _client().get("/api/v1/market")
    assert response.status_code == 200
    body = response.json()
    assert "quotes" in body and "errors" in body
    assert any(q["symbol"] == "USDTRY" for q in body["quotes"])


def test_price_history_endpoint_normalizes_bare_ticker_and_defaults_range():
    response = _client().get("/api/v1/price-history/ARTMS")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "ARTMS.IS"
    assert body["range"] == "1A"


def test_price_history_endpoint_rejects_unknown_range():
    response = _client().get("/api/v1/price-history/ARTMS?range=3A")
    assert response.status_code == 422


def test_price_history_endpoint_maps_missing_symbol_to_404():
    response = _client().get("/api/v1/price-history/DELISTED?range=1A")
    assert response.status_code == 404
