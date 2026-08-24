"""Phase 9 tests for ARVEN Trade's BIST-specific market-data contract."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    resolve_instrument_identity,
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_balance_sheet,
    get_fundamentals,
)
from tradingagents.dataflows import interface
from tradingagents.dataflows.bist import (
    BIST_BENCHMARK,
    BIST_CURRENCY,
    BIST_EXCHANGE_NAME,
    build_bist_market_context,
    is_bist_yahoo_symbol,
    normalize_bist_yahoo_symbol,
    resolve_bist_benchmark,
)
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.kap.service import normalize_bist_ticker_for_kap
from tradingagents.dataflows.y_finance import get_YFin_data_online
from tradingagents.graph.trading_graph import TradingAgentsGraph


@pytest.mark.unit
@pytest.mark.parametrize("ticker", ["THYAO.IS", "ASELS.IS", "TUPRS.IS"])
def test_bist_yahoo_symbols_are_recognized(ticker):
    assert is_bist_yahoo_symbol(ticker)
    assert normalize_bist_yahoo_symbol(ticker.lower()) == ticker


@pytest.mark.unit
def test_non_bist_symbol_is_not_recognized():
    assert not is_bist_yahoo_symbol("AAPL")


@pytest.mark.unit
def test_bare_ticker_is_never_auto_converted_to_is_suffix():
    assert not is_bist_yahoo_symbol("THYAO")
    with pytest.raises(ValueError, match="not a BIST Yahoo ticker"):
        normalize_bist_yahoo_symbol("THYAO")


@pytest.mark.unit
def test_bist_instrument_context_contains_deterministic_market_metadata():
    context = build_instrument_context(
        "THYAO.IS",
        "stock",
        {
            "company_name": "Türk Hava Yolları A.O.",
            "exchange": "IST",
            "currency": "TRY",
            "country": "Türkiye",
        },
    )
    assert "THYAO.IS" in context
    assert BIST_EXCHANGE_NAME in context
    assert BIST_CURRENCY in context
    assert BIST_BENCHMARK in context
    assert "Preserve the terminal `.IS` suffix" in context


@pytest.mark.unit
def test_bist_context_is_added_even_when_yahoo_identity_is_unavailable():
    context = build_instrument_context("ASELS.IS")
    assert BIST_EXCHANGE_NAME in context
    assert BIST_CURRENCY in context
    assert BIST_BENCHMARK in context


@pytest.mark.unit
def test_resolved_identity_keeps_currency_financial_currency_and_country():
    resolve_instrument_identity.cache_clear()
    with patch("tradingagents.agents.utils.agent_utils.yf.Ticker") as mock:
        mock.return_value.info = {
            "longName": "Türk Hava Yolları A.O.",
            "exchange": "IST",
            "currency": "TRY",
            "financialCurrency": "TRY",
            "country": "Türkiye",
        }
        identity = resolve_instrument_identity("THYAO.IS")
    mock.assert_called_once_with("THYAO.IS")
    assert identity["currency"] == "TRY"
    assert identity["financial_currency"] == "TRY"
    assert identity["country"] == "Türkiye"


@pytest.mark.unit
@pytest.mark.parametrize("ticker", ["THYAO.IS", "ASELS.IS", "TUPRS.IS"])
def test_bist_benchmark_is_xu100(ticker):
    graph = object.__new__(TradingAgentsGraph)
    graph.config = {
        "benchmark_ticker": None,
        "benchmark_map": {".IS": "^XU100", "": "SPY"},
    }
    assert graph._resolve_benchmark(ticker) == "^XU100"
    assert graph._resolve_benchmark(ticker) != "SPY"


@pytest.mark.unit
def test_bist_context_uses_explicit_benchmark_override():
    config = {
        "benchmark_ticker": "^CUSTOM",
        "benchmark_map": {".IS": "^XU100", "": "SPY"},
    }
    assert resolve_bist_benchmark("THYAO.IS", config) == "^CUSTOM"
    with patch("tradingagents.dataflows.config.get_config", return_value=config):
        context = build_bist_market_context("THYAO.IS")
    assert "Benchmark: ^CUSTOM" in context
    assert "Benchmark: ^XU100" not in context


@pytest.mark.unit
def test_bist_context_uses_custom_is_benchmark_map_entry():
    config = {
        "benchmark_ticker": None,
        "benchmark_map": {".IS": "XU030.IS", "": "SPY"},
    }
    assert resolve_bist_benchmark("ASELS.IS", config) == "XU030.IS"
    with patch("tradingagents.dataflows.config.get_config", return_value=config):
        context = build_bist_market_context("ASELS.IS")
    assert "Benchmark: XU030.IS" in context


@pytest.mark.unit
def test_market_data_call_preserves_is_suffix(monkeypatch):
    seen_symbols: list[str] = []

    class FakeTicker:
        def __init__(self, symbol):
            seen_symbols.append(symbol)

        def history(self, **kwargs):
            return pd.DataFrame(
                {
                    "Open": [300.0],
                    "High": [305.0],
                    "Low": [298.0],
                    "Close": [304.0],
                    "Volume": [1_000_000],
                },
                index=pd.DatetimeIndex(["2026-08-20"]),
            )

    monkeypatch.setattr("tradingagents.dataflows.y_finance.yf.Ticker", FakeTicker)
    monkeypatch.setattr(
        "tradingagents.dataflows.y_finance._assert_ohlcv_not_stale",
        lambda *args, **kwargs: None,
    )

    report = get_YFin_data_online("thyao.is", "2026-08-20", "2026-08-20")
    assert seen_symbols == ["THYAO.IS"]
    assert "THYAO.IS" in report


@pytest.mark.unit
def test_historical_bist_snapshot_fundamentals_are_blocked_before_vendor_call():
    with patch(
        "tradingagents.agents.utils.fundamental_data_tools.route_to_vendor"
    ) as route:
        result = get_fundamentals.invoke(
            {"ticker": "THYAO.IS", "curr_date": "2000-01-01"}
        )
    route.assert_not_called()
    assert result.startswith("POINT_IN_TIME_DATA_UNAVAILABLE")
    assert "Do not estimate or fabricate values" in result


@pytest.mark.unit
def test_historical_bist_statement_is_blocked_when_filing_time_is_not_verifiable():
    with patch(
        "tradingagents.agents.utils.fundamental_data_tools.route_to_vendor"
    ) as route:
        result = get_balance_sheet.invoke(
            {
                "ticker": "ASELS.IS",
                "freq": "quarterly",
                "curr_date": "2000-01-01",
            }
        )
    route.assert_not_called()
    assert result.startswith("POINT_IN_TIME_DATA_UNAVAILABLE")
    assert "KAP disclosures" in result


@pytest.mark.unit
def test_missing_bist_statement_date_fails_closed_before_vendor_call():
    with patch(
        "tradingagents.agents.utils.fundamental_data_tools.route_to_vendor"
    ) as route:
        result = get_balance_sheet.invoke(
            {"ticker": "THYAO.IS", "freq": "quarterly"}
        )
    route.assert_not_called()
    assert result.startswith("ANALYSIS_DATE_REQUIRED")
    assert "vendor was not called" in result.lower()


@pytest.mark.unit
@pytest.mark.parametrize("bad_date", ["", "2026-08-20T10:00:00", "20-08-2026", "not-a-date"])
def test_malformed_bist_analysis_date_returns_sentinel_not_exception(bad_date):
    with patch(
        "tradingagents.agents.utils.fundamental_data_tools.route_to_vendor"
    ) as route:
        result = get_fundamentals.invoke(
            {"ticker": "ASELS.IS", "curr_date": bad_date}
        )
    route.assert_not_called()
    assert result.startswith("INVALID_ANALYSIS_DATE")
    assert "Do not estimate or fabricate values" in result


@pytest.mark.unit
def test_current_bist_fundamental_result_is_labeled_with_try_and_benchmark():
    with patch(
        "tradingagents.agents.utils.fundamental_data_tools.route_to_vendor",
        return_value="# Company Fundamentals\nName: Example",
    ):
        result = get_fundamentals.invoke(
            {"ticker": "TUPRS.IS", "curr_date": date.today().isoformat()}
        )
    assert BIST_EXCHANGE_NAME in result
    assert BIST_CURRENCY in result
    assert BIST_BENCHMARK in result
    assert "# Company Fundamentals" in result


@pytest.mark.unit
@pytest.mark.parametrize(
    ("yahoo_ticker", "kap_ticker"),
    [("THYAO.IS", "THYAO"), ("ASELS.IS", "ASELS"), ("TUPRS.IS", "TUPRS")],
)
def test_bist_symbol_contract_remains_compatible_with_kap(yahoo_ticker, kap_ticker):
    assert normalize_bist_yahoo_symbol(yahoo_ticker) == yahoo_ticker
    assert normalize_bist_ticker_for_kap(yahoo_ticker) == kap_ticker


@pytest.mark.unit
def test_missing_bist_market_data_returns_no_data_sentinel_not_fabricated_numbers(monkeypatch):
    def no_data(*args, **kwargs):
        raise NoMarketDataError(
            "THYAO.IS",
            "THYAO.IS",
            "latest row is stale or unavailable",
        )

    monkeypatch.setattr(interface, "get_vendor", lambda category, method=None: "yfinance")
    monkeypatch.setitem(interface.VENDOR_METHODS["get_stock_data"], "yfinance", no_data)

    result = interface.route_to_vendor(
        "get_stock_data", "THYAO.IS", "2026-08-19", "2026-08-20"
    )
    assert result.startswith("NO_DATA_AVAILABLE")
    assert "Do not estimate or fabricate values" in result
    assert "THYAO.IS" in result
