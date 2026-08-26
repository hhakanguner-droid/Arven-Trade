"""Minimal command interface for ARVEN Trade Phase 10 watchlist alerts.

Examples:
    python -m tradingagents.alerts list
    python -m tradingagents.alerts add THYAO.IS
    python -m tradingagents.alerts check --json
    python -m tradingagents.alerts pending --json
    python -m tradingagents.alerts ack KAP:THYAO.IS:123456
"""

from __future__ import annotations

import argparse
import json

from .service import create_watchlist_alert_service


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tradingagents.alerts")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="List watched BIST tickers")

    add = subparsers.add_parser("add", help="Add a Yahoo BIST .IS ticker")
    add.add_argument("ticker")

    remove = subparsers.add_parser("remove", help="Remove a watched ticker")
    remove.add_argument("ticker")

    check = subparsers.add_parser("check", help="Check KAP for new important events")
    check.add_argument("--json", action="store_true", dest="as_json")

    pending = subparsers.add_parser("pending", help="Show alerts waiting for delivery acknowledgement")
    pending.add_argument("--json", action="store_true", dest="as_json")

    ack = subparsers.add_parser("ack", help="Acknowledge successfully delivered alert IDs")
    ack.add_argument("alert_ids", nargs="+")

    history = subparsers.add_parser("history", help="Show delivered alert history")
    history.add_argument("--json", action="store_true", dest="as_json")
    return parser


def _check_exit_code(batch) -> int:
    statuses = tuple(batch.source_statuses)
    if not statuses:
        return 0
    if any(status.status == "ok" for status in statuses):
        return 0
    if all(status.status == "disabled" for status in statuses):
        return 0
    return 1


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    service = create_watchlist_alert_service()

    if args.command == "list":
        for ticker in service.watchlist.list():
            print(ticker)
        return 0

    if args.command == "add":
        changed = service.watchlist.add(args.ticker)
        print("added" if changed else "already-watched")
        return 0

    if args.command == "remove":
        changed = service.watchlist.remove(args.ticker)
        print("removed" if changed else "not-watched")
        return 0

    if args.command == "check":
        batch = service.check_watchlist()
        exit_code = _check_exit_code(batch)
        if args.as_json:
            print(json.dumps(batch.to_dict(), ensure_ascii=False, indent=2))
            return exit_code
        if not batch.alerts:
            print("Yeni önemli KAP bildirimi yok.")
        for alert in batch.alerts:
            print(
                f"[{alert.severity.upper()}] {alert.ticker} | "
                f"{alert.category} | {alert.title} | {alert.url}"
            )
        for status in batch.source_statuses:
            if status.status != "ok":
                print(f"[{status.source}:{status.ticker}] {status.status}: {status.message}")
        return exit_code

    if args.command == "pending":
        pending_alerts = service.pending_alerts()
        if args.as_json:
            print(json.dumps(pending_alerts, ensure_ascii=False, indent=2))
            return 0
        for item in pending_alerts:
            print(
                f"[{str(item.get('severity', '')).upper()}] "
                f"{item.get('ticker', '')} | {item.get('title', '')} | {item.get('alert_id', '')}"
            )
        return 0

    if args.command == "ack":
        acknowledged = service.acknowledge_alerts(args.alert_ids)
        print(f"acknowledged:{acknowledged}")
        return 0

    if args.command == "history":
        history = service.state.history()
        if args.as_json:
            print(json.dumps(history, ensure_ascii=False, indent=2))
            return 0
        for item in history:
            print(
                f"[{str(item.get('severity', '')).upper()}] "
                f"{item.get('ticker', '')} | {item.get('title', '')}"
            )
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
