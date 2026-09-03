"""Market overview vendor: FX, parities, BIST indices and commodities.

Feeds the ARVEN Trade "Piyasalar" view. Every instrument is fetched
independently through the shared ``yf_retry`` wrapper so one delisted or
rate-limited symbol becomes a per-instrument entry in ``errors`` instead of
failing the whole snapshot — the same fail-open shape the watchlist alert
service uses for its KAP sources.

Gram Altın has no direct Yahoo Finance feed for the Turkish domestic market,
so it is derived from the ons altın (XAUUSD, USD/troy-ounce) quote and the
USDTRY rate rather than invented outright.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

import yfinance as yf

from .bist import BIST_BENCHMARK
from .errors import NoMarketDataError
from .stockstats_utils import yf_retry

MarketGroup = Literal["fx", "parity", "index", "commodity", "crypto"]

# Grams per troy ounce; used to derive Gram Altın from the ons altın (USD) quote.
_GRAM_PER_TROY_OUNCE = 31.1034768

_RANGE_TO_PERIOD_INTERVAL: dict[str, tuple[str, str]] = {
    "1G": ("1d", "5m"),
    "1H": ("5d", "15m"),
    "1A": ("1mo", "1d"),
    "6A": ("6mo", "1d"),
    "1Y": ("1y", "1d"),
    "5Y": ("5y", "1wk"),
}

# symbol, label, group, Yahoo ticker, quote currency.
_INSTRUMENTS: tuple[tuple[str, str, MarketGroup, str, str], ...] = (
    ("USDTRY", "Amerikan Doları", "fx", "USDTRY=X", "TRY"),
    ("EURTRY", "Euro", "fx", "EURTRY=X", "TRY"),
    ("GBPTRY", "İngiliz Sterlini", "fx", "GBPTRY=X", "TRY"),
    ("CHFTRY", "İsviçre Frangı", "fx", "CHFTRY=X", "TRY"),
    ("EURUSD", "Euro / Dolar", "parity", "EURUSD=X", "USD"),
    ("GBPUSD", "Sterlin / Dolar", "parity", "GBPUSD=X", "USD"),
    ("USDJPY", "Dolar / Yen", "parity", "USDJPY=X", "JPY"),
    ("XU100", "BIST 100", "index", BIST_BENCHMARK, "TRY"),
    ("XU030", "BIST 30", "index", "XU030.IS", "TRY"),
    ("XBANK", "BIST Bankacılık", "index", "XBANK.IS", "TRY"),
    ("XUSIN", "BIST Sınai", "index", "XUSIN.IS", "TRY"),
    ("XAUUSD", "Ons Altın", "commodity", "GC=F", "USD"),
    ("XAGUSD", "Gümüş", "commodity", "SI=F", "USD"),
    ("BRENT", "Brent Petrol", "commodity", "BZ=F", "USD"),
    ("BTCUSDT", "Bitcoin", "crypto", "BTC-USD", "USD"),
    ("ETHUSDT", "Ethereum", "crypto", "ETH-USD", "USD"),
)


@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    label: str
    group: MarketGroup
    price: float
    change_pct: float
    currency: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "label": self.label,
            "group": self.group,
            "price": round(self.price, 4),
            "change_pct": round(self.change_pct, 2),
            "currency": self.currency,
        }


def _fetch_quote(yahoo_ticker: str) -> tuple[float, float]:
    """Return (last_close, change_pct) from the two most recent daily closes."""
    ticker = yf.Ticker(yahoo_ticker)
    data = yf_retry(lambda: ticker.history(period="5d", interval="1d"))
    closes = data["Close"].dropna() if not data.empty else data
    if closes.empty:
        raise NoMarketDataError(yahoo_ticker, yahoo_ticker, "no close prices returned")
    last = float(closes.iloc[-1])
    previous = float(closes.iloc[-2]) if len(closes) >= 2 else last
    change_pct = ((last - previous) / previous * 100) if previous else 0.0
    return last, change_pct


def get_market_snapshot(groups: tuple[MarketGroup, ...] | None = None) -> dict:
    """Fetch a live FX/parity/index/commodity/crypto snapshot.

    ``groups`` restricts the result to a subset (e.g. ``("fx", "index")``);
    omit it for the full Piyasalar snapshot. Each instrument fails on its own;
    a snapshot with partial ``errors`` is still returned rather than raised.
    """
    wanted = set(groups) if groups else None
    quotes: list[dict] = []
    errors: list[dict] = []
    gold_inputs: dict[str, float] = {}

    for symbol, label, group, yahoo_ticker, currency in _INSTRUMENTS:
        if wanted and group not in wanted:
            continue
        try:
            price, change_pct = _fetch_quote(yahoo_ticker)
        except Exception as exc:  # noqa: BLE001 - every vendor failure funnels into `errors`
            errors.append({"symbol": symbol, "yahoo_ticker": yahoo_ticker, "message": str(exc)})
            continue
        quotes.append(MarketQuote(symbol, label, group, price, change_pct, currency).to_dict())
        if symbol == "XAUUSD":
            gold_inputs["ons_usd"] = price
            gold_inputs["ons_change_pct"] = change_pct
        elif symbol == "USDTRY":
            gold_inputs["usdtry"] = price

    if (not wanted or "commodity" in wanted) and {"ons_usd", "usdtry"} <= gold_inputs.keys():
        gram_try = gold_inputs["ons_usd"] * gold_inputs["usdtry"] / _GRAM_PER_TROY_OUNCE
        quotes.append(
            {
                "symbol": "GRAMALTIN",
                "label": "Gram Altın",
                "group": "commodity",
                "price": round(gram_try, 2),
                "change_pct": round(gold_inputs["ons_change_pct"], 2),
                "currency": "TRY",
            }
        )

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "quotes": quotes,
        "errors": errors,
    }


def get_price_history(symbol: str, range_key: str = "1A") -> dict:
    """Return a chart-ready close-price series plus period/52-week stats.

    ``symbol`` must already be a canonical Yahoo ticker (BIST tickers carry
    the ``.IS`` suffix); callers normalize the user-supplied ticker before
    reaching this function, matching every other endpoint in this service.
    """
    if range_key not in _RANGE_TO_PERIOD_INTERVAL:
        raise ValueError(f"range must be one of {sorted(_RANGE_TO_PERIOD_INTERVAL)}")

    period, interval = _RANGE_TO_PERIOD_INTERVAL[range_key]
    ticker = yf.Ticker(symbol)
    data = yf_retry(lambda: ticker.history(period=period, interval=interval))
    if data.empty:
        raise NoMarketDataError(symbol, symbol, f"no rows for range {range_key}")
    if data.index.tz is not None:
        data.index = data.index.tz_localize(None)

    closes = data["Close"].dropna()
    if closes.empty:
        raise NoMarketDataError(symbol, symbol, f"no close prices for range {range_key}")

    points = [
        {"t": index.isoformat(), "close": round(float(value), 4)}
        for index, value in closes.items()
    ]
    first_close = float(closes.iloc[0])
    last_close = float(closes.iloc[-1])
    period_change_pct = ((last_close - first_close) / first_close * 100) if first_close else 0.0

    fifty_two_week = None
    try:
        yearly = yf_retry(lambda: ticker.history(period="1y", interval="1d"))
        if not yearly.empty:
            fifty_two_week = {
                "high": round(float(yearly["High"].max()), 4),
                "low": round(float(yearly["Low"].min()), 4),
            }
    except Exception:  # noqa: BLE001 - 52-week stats are supplementary, never fatal
        fifty_two_week = None

    return {
        "symbol": symbol,
        "range": range_key,
        "points": points,
        "last_price": round(last_close, 4),
        "period_change_pct": round(period_change_pct, 2),
        "fifty_two_week": fifty_two_week,
    }
