"""Command-line queries and backfill for the Phase 11 analysis history database."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tradingagents.default_config import DEFAULT_CONFIG

from .store import AnalysisHistoryStore
from .tracker import AnalysisHistoryTracker


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _default_db_path() -> str:
    return str(
        DEFAULT_CONFIG.get(
            "analysis_history_path",
            str(Path.home() / ".tradingagents" / "history" / "analysis_history.db"),
        )
    )


def _add_db_argument(parser: argparse.ArgumentParser, *, subcommand: bool = False) -> None:
    # argparse normally accepts global options only before the subcommand. Add
    # the same option to each subparser with a suppressed default so both of
    # these work without one silently overriding the other:
    #   history --db X list
    #   history list --db X
    default = argparse.SUPPRESS if subcommand else _default_db_path()
    parser.add_argument(
        "--db",
        default=default,
        help="SQLite history database path.",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tradingagents.history",
        description="Query ARVEN/TradingAgents analysis history and realized performance.",
    )
    _add_db_argument(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List stored analyses.")
    _add_db_argument(list_parser, subcommand=True)
    list_parser.add_argument("--ticker")
    list_parser.add_argument("--limit", type=int, default=20)

    compare_parser = subparsers.add_parser(
        "compare",
        help="Return the most recent analyses for one ticker.",
    )
    _add_db_argument(compare_parser, subcommand=True)
    compare_parser.add_argument("--ticker", required=True)
    compare_parser.add_argument("--count", type=int, default=2)

    perf_parser = subparsers.add_parser(
        "performance",
        help="Summarize realized 1/5/20-session performance.",
    )
    _add_db_argument(perf_parser, subcommand=True)
    perf_parser.add_argument("--ticker")

    resolve_parser = subparsers.add_parser(
        "resolve",
        help="Backfill missing realized-performance horizons using market data.",
    )
    _add_db_argument(resolve_parser, subcommand=True)
    resolve_parser.add_argument("--ticker")
    resolve_parser.add_argument("--limit", type=int, default=10)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    store = AnalysisHistoryStore(Path(args.db))

    if args.command == "list":
        payload = store.list_analyses(args.ticker, limit=args.limit)
    elif args.command == "compare":
        payload = store.compare_latest(args.ticker, count=args.count)
    elif args.command == "performance":
        payload = store.performance_summary(args.ticker)
    else:
        config = DEFAULT_CONFIG.copy()
        config["analysis_history_enabled"] = True
        config["analysis_history_path"] = str(args.db)
        config["analysis_history_resolve_limit"] = max(1, args.limit)
        tracker = AnalysisHistoryTracker(config, store=store)
        payload = {
            "ticker": args.ticker,
            "updated_performance_points": tracker.resolve_pending(args.ticker),
        }

    print(_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
