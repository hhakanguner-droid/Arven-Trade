"""Borsa Istanbul (BIST) market metadata and symbol helpers.

This module centralizes ARVEN Trade's BIST-specific conventions without
changing the generic symbol normalization used by TradingAgents. Bare equity
tickers are intentionally not converted to Yahoo's ``.IS`` form because that
would make global symbols ambiguous.
"""

from __future__ import annotations

import re
from datetime import date, datetime

BIST_YAHOO_SUFFIX = ".IS"
BIST_BENCHMARK = "^XU100"
BIST_CURRENCY = "TRY"
BIST_EXCHANGE_NAME = "Borsa Istanbul"
BIST_COUNTRY = "Türkiye"

_BIST_YAHOO_SYMBOL = re.compile(r"^[A-Z][A-Z0-9]{1,9}\.IS$")


def normalize_bist_yahoo_symbol(symbol: str) -> str:
    """Return a validated, canonical Yahoo BIST equity symbol.

    Only symbols that already carry the terminal ``.IS`` suffix are accepted.
    The helper never appends ``.IS`` to a bare ticker.
    """
    if not isinstance(symbol, str):
        raise TypeError("symbol must be a string")

    normalized = symbol.strip().upper()
    if _BIST_YAHOO_SYMBOL.fullmatch(normalized) is None:
        raise ValueError(f"not a BIST Yahoo ticker: {symbol!r}")
    return normalized


def is_bist_yahoo_symbol(symbol: object) -> bool:
    """Return whether *symbol* is a valid Yahoo-form BIST equity ticker."""
    try:
        normalize_bist_yahoo_symbol(symbol)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return True


def build_bist_market_context(symbol: str) -> str:
    """Return deterministic market metadata for a validated BIST symbol."""
    canonical = normalize_bist_yahoo_symbol(symbol)
    return (
        f"BIST market context: Yahoo ticker: {canonical}; "
        f"Exchange: {BIST_EXCHANGE_NAME}; Currency: {BIST_CURRENCY}; "
        f"Country: {BIST_COUNTRY}; Benchmark: BIST 100 ({BIST_BENCHMARK}). "
        "Preserve the terminal `.IS` suffix in every market-data tool call."
    )


def is_historical_analysis_date(
    curr_date: str | date | datetime | None,
    *,
    today: date | None = None,
) -> bool:
    """Return whether *curr_date* is before the real current calendar date."""
    if curr_date is None:
        return False
    if isinstance(curr_date, datetime):
        requested = curr_date.date()
    elif isinstance(curr_date, date):
        requested = curr_date
    else:
        requested = date.fromisoformat(str(curr_date))
    return requested < (today or date.today())


def historical_bist_fundamentals_guard(
    ticker: str,
    curr_date: str | date | datetime | None,
) -> str | None:
    """Block current Yahoo snapshots from leaking into historical BIST runs.

    Yahoo's ``Ticker.info`` is a current snapshot, while its financial-statement
    tables expose fiscal-period columns but do not reliably expose the filing
    publication timestamp needed for point-in-time backtests. For a historical
    BIST run we therefore prefer an explicit sentinel over look-ahead bias.
    """
    if not is_bist_yahoo_symbol(ticker) or not is_historical_analysis_date(curr_date):
        return None
    canonical = normalize_bist_yahoo_symbol(ticker)
    return (
        "POINT_IN_TIME_DATA_UNAVAILABLE: Historical BIST fundamentals for "
        f"{canonical} on {curr_date} are not served from Yahoo Finance current "
        "snapshots or statement tables because their true publication-time "
        "availability cannot be guaranteed. Use KAP disclosures or another "
        "verified point-in-time source. Do not estimate or fabricate values."
    )
