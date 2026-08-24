"""Borsa Istanbul (BIST) market metadata and symbol helpers.

This module centralizes ARVEN Trade's BIST-specific conventions without
changing the generic symbol normalization used by TradingAgents. Bare equity
tickers are intentionally not converted to Yahoo's ``.IS`` form because that
would make global symbols ambiguous.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Mapping, Any

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


def resolve_bist_benchmark(
    symbol: str,
    config: Mapping[str, Any] | None = None,
) -> str:
    """Resolve the active benchmark using the graph's configuration rules.

    ``benchmark_ticker`` overrides the suffix map. Otherwise the first matching
    non-empty suffix from ``benchmark_map`` is used, with the empty suffix as
    final fallback. This mirrors ``TradingAgentsGraph._resolve_benchmark`` so
    prompts and realized-alpha calculations cannot advertise different indices.
    """
    canonical = normalize_bist_yahoo_symbol(symbol)
    if config is None:
        from .config import get_config

        config = get_config()

    explicit = config.get("benchmark_ticker")
    if explicit:
        return str(explicit)

    benchmark_map = config.get("benchmark_map", {})
    if isinstance(benchmark_map, Mapping):
        for suffix, benchmark in benchmark_map.items():
            if suffix and canonical.endswith(str(suffix).upper()):
                return str(benchmark)
        fallback = benchmark_map.get("")
        if fallback:
            return str(fallback)

    return BIST_BENCHMARK


def build_bist_market_context(symbol: str) -> str:
    """Return deterministic market metadata for a validated BIST symbol."""
    canonical = normalize_bist_yahoo_symbol(symbol)
    benchmark = resolve_bist_benchmark(canonical)
    return (
        f"BIST market context: Yahoo ticker: {canonical}; "
        f"Exchange: {BIST_EXCHANGE_NAME}; Currency: {BIST_CURRENCY}; "
        f"Country: {BIST_COUNTRY}; Benchmark: {benchmark}. "
        "Preserve the terminal `.IS` suffix in every market-data tool call."
    )


def _parse_analysis_date(
    curr_date: str | date | datetime | None,
) -> tuple[date | None, str | None]:
    """Parse the workflow analysis date without letting tool input crash a run."""
    if curr_date is None:
        return None, "missing"
    if isinstance(curr_date, datetime):
        return curr_date.date(), None
    if isinstance(curr_date, date):
        return curr_date, None
    if not isinstance(curr_date, str) or not curr_date.strip():
        return None, "invalid"
    try:
        return date.fromisoformat(curr_date.strip()), None
    except ValueError:
        return None, "invalid"


def is_historical_analysis_date(
    curr_date: str | date | datetime | None,
    *,
    today: date | None = None,
) -> bool:
    """Return whether *curr_date* is a valid date before the real current date.

    Missing or malformed values return ``False`` here; callers that must fail
    closed should use :func:`historical_bist_fundamentals_guard`, which emits a
    tool-readable sentinel for those cases.
    """
    requested, error = _parse_analysis_date(curr_date)
    return error is None and requested is not None and requested < (today or date.today())


def historical_bist_fundamentals_guard(
    ticker: str,
    curr_date: str | date | datetime | None,
) -> str | None:
    """Block unsafe Yahoo snapshots from BIST point-in-time analysis.

    Yahoo's ``Ticker.info`` is a current snapshot, while its financial-statement
    tables expose fiscal-period columns but do not reliably expose the filing
    publication timestamp needed for point-in-time backtests. Missing or invalid
    workflow dates therefore fail closed for BIST calls, and historical dates
    return an explicit sentinel instead of allowing look-ahead bias.
    """
    if not is_bist_yahoo_symbol(ticker):
        return None

    canonical = normalize_bist_yahoo_symbol(ticker)
    requested, error = _parse_analysis_date(curr_date)

    if error == "missing":
        return (
            "ANALYSIS_DATE_REQUIRED: BIST fundamental and financial-statement "
            f"requests for {canonical} require the workflow analysis date in "
            "YYYY-MM-DD format. The vendor was not called. Do not estimate or "
            "fabricate values."
        )
    if error == "invalid":
        return (
            "INVALID_ANALYSIS_DATE: BIST fundamental and financial-statement "
            f"requests for {canonical} require curr_date in YYYY-MM-DD format; "
            f"received {curr_date!r}. The vendor was not called. Do not estimate "
            "or fabricate values."
        )

    if requested is None or requested >= date.today():
        return None

    return (
        "POINT_IN_TIME_DATA_UNAVAILABLE: Historical BIST fundamentals for "
        f"{canonical} on {requested.isoformat()} are not served from Yahoo Finance "
        "current snapshots or statement tables because their true publication-time "
        "availability cannot be guaranteed. Use KAP disclosures or another "
        "verified point-in-time source. Do not estimate or fabricate values."
    )
