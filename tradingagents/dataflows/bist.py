"""Borsa Istanbul (BIST) market metadata and symbol helpers.

This module centralizes ARVEN Trade's BIST-specific conventions without
changing the generic symbol normalization used by TradingAgents. Bare equity
tickers are intentionally not converted to Yahoo's ``.IS`` form because that
would make global symbols ambiguous.
"""

from __future__ import annotations

import re

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
