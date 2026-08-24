from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.bist import (
    build_bist_market_context,
    historical_bist_fundamentals_guard,
    is_bist_yahoo_symbol,
)
from tradingagents.dataflows.interface import route_to_vendor


def _with_bist_context(ticker: str, result: str) -> str:
    """Prefix BIST fundamental results with deterministic market metadata."""
    if not is_bist_yahoo_symbol(ticker):
        return result
    return f"# {build_bist_market_context(ticker)}\n\n{result}"


def _historical_guard(ticker: str, curr_date: str | None) -> str | None:
    """Prevent current Yahoo snapshots from leaking into historical BIST runs."""
    return historical_bist_fundamentals_guard(ticker, curr_date)


@tool
def get_fundamentals(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """
    Retrieve comprehensive fundamental data for a given ticker symbol.
    Uses the configured fundamental_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing comprehensive fundamental data
    """
    guard = _historical_guard(ticker, curr_date)
    if guard:
        return guard
    return _with_bist_context(
        ticker,
        route_to_vendor("get_fundamentals", ticker, curr_date),
    )


@tool
def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve balance sheet data for a given ticker symbol.
    Uses the configured fundamental_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing balance sheet data
    """
    guard = _historical_guard(ticker, curr_date)
    if guard:
        return guard
    return _with_bist_context(
        ticker,
        route_to_vendor("get_balance_sheet", ticker, freq, curr_date),
    )


@tool
def get_cashflow(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve cash flow statement data for a given ticker symbol.
    Uses the configured fundamental_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing cash flow statement data
    """
    guard = _historical_guard(ticker, curr_date)
    if guard:
        return guard
    return _with_bist_context(
        ticker,
        route_to_vendor("get_cashflow", ticker, freq, curr_date),
    )


@tool
def get_income_statement(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve income statement data for a given ticker symbol.
    Uses the configured fundamental_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing income statement data
    """
    guard = _historical_guard(ticker, curr_date)
    if guard:
        return guard
    return _with_bist_context(
        ticker,
        route_to_vendor("get_income_statement", ticker, freq, curr_date),
    )
