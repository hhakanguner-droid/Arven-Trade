"""Persistent watchlist and KAP alert service for ARVEN Trade.

The service is deliberately UI-agnostic: CLI, web, PWA, or a scheduler can call
``check_watchlist`` and deliver the returned notification payload however they
choose. KAP failures are represented as source statuses and never fabricated
into alerts.
"""

from __future__ import annotations

import json
import os
import unicodedata
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from tradingagents.dataflows.bist import is_bist_yahoo_symbol, normalize_bist_yahoo_symbol
from tradingagents.dataflows.kap.models import KapDisclosure
from tradingagents.dataflows.kap.service import KapService

from .models import AlertCategory, AlertSeverity, AlertSourceStatus, WatchlistAlert, WatchlistAlertBatch

_EVENT_RULES: tuple[tuple[AlertCategory, int, tuple[str, ...]], ...] = (
    ("financials", 100, ("finansal rapor", "finansal sonuç", "bilanço", "gelir tablosu")),
    ("dividend", 95, ("kar payı", "temettü", "kâr payı")),
    ("capital", 95, ("sermaye artır", "bedelli", "bedelsiz", "sermaye azalt")),
    ("mna", 90, ("birleşme", "bölünme", "satın alma", "devralma", "devir")),
    ("commercial", 85, ("ihale", "sözleşme", "iş ilişkisi", "sipariş")),
    ("legal", 85, ("dava", "ceza", "soruşturma", "yaptırım", "faaliyet durdur")),
    ("operations", 80, ("yatırım", "kapasite", "üretim", "fabrika", "tesis")),
    ("ownership", 80, ("pay satışı", "pay alımı", "ortaklık", "hakim ortak")),
    ("financing", 75, ("borçlanma", "finansman", "kredi", "tahvil", "bono")),
    ("governance", 65, ("yönetim", "genel müdür", "yönetici", "bağımsız üye")),
)

_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _normalize_event_text(value: str) -> str:
    """Normalize Turkish casing/diacritics for deterministic keyword matching."""
    folded = value.casefold().replace("ı", "i")
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", folded)
        if not unicodedata.combining(char)
    )


def classify_kap_disclosure(disclosure: KapDisclosure) -> tuple[AlertCategory, int, AlertSeverity]:
    """Classify one KAP disclosure into a deterministic alert category/severity."""
    text = _normalize_event_text(f"{disclosure.subject} {disclosure.summary}")
    category: AlertCategory = "other"
    score = 0

    if disclosure.disclosure_type.upper() in {"FR", "FS"}:
        category, score = "financials", 100

    for candidate, weight, terms in _EVENT_RULES:
        if weight <= score:
            continue
        if any(_normalize_event_text(term) in text for term in terms):
            category, score = candidate, weight

    if disclosure.is_corrective and score:
        score = min(100, score + 5)

    if score >= 95:
        severity: AlertSeverity = "critical"
    elif score >= 85:
        severity = "high"
    elif score >= 70:
        severity = "medium"
    else:
        severity = "low"
    return category, score, severity


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON state file: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"state file must contain a JSON object: {path}")
    return payload


class WatchlistStore:
    """Small JSON-backed BIST watchlist with canonical ``.IS`` symbols."""

    def __init__(self, path: str | Path, seed_tickers: Iterable[str] = ()) -> None:
        self.path = Path(path).expanduser()
        self.seed_tickers = tuple(seed_tickers)

    def list(self) -> tuple[str, ...]:
        payload = _read_json_object(self.path)
        if payload is None:
            tickers = self._validated_unique(self.seed_tickers)
            self._save(tickers)
            return tuple(tickers)
        raw = payload.get("tickers", [])
        if not isinstance(raw, list):
            raise ValueError(f"watchlist tickers must be a JSON list: {self.path}")
        return tuple(self._validated_unique(raw, strict=True))

    def add(self, ticker: str) -> bool:
        canonical = normalize_bist_yahoo_symbol(ticker)
        tickers = list(self.list())
        if canonical in tickers:
            return False
        tickers.append(canonical)
        self._save(tickers)
        return True

    def remove(self, ticker: str) -> bool:
        canonical = normalize_bist_yahoo_symbol(ticker)
        tickers = list(self.list())
        if canonical not in tickers:
            return False
        tickers.remove(canonical)
        self._save(tickers)
        return True

    def replace(self, tickers: Iterable[str]) -> tuple[str, ...]:
        validated = self._validated_unique(tickers, strict=True)
        self._save(validated)
        return tuple(validated)

    @staticmethod
    def _validated_unique(tickers: Iterable[Any], *, strict: bool = False) -> list[str]:
        result: list[str] = []
        for ticker in tickers:
            if not is_bist_yahoo_symbol(ticker):
                if strict:
                    raise ValueError(f"watchlist only accepts Yahoo BIST .IS tickers: {ticker!r}")
                continue
            canonical = normalize_bist_yahoo_symbol(ticker)
            if canonical not in result:
                result.append(canonical)
        return result

    def _save(self, tickers: Iterable[str]) -> None:
        _atomic_write_json(self.path, {"version": 1, "tickers": list(tickers)})


class AlertStateStore:
    """Persistent de-duplication state and bounded alert history."""

    def __init__(
        self,
        path: str | Path,
        *,
        history_limit: int = 500,
        seen_limit: int = 5000,
    ) -> None:
        if history_limit < 1 or seen_limit < 1:
            raise ValueError("alert state limits must be positive")
        self.path = Path(path).expanduser()
        self.history_limit = int(history_limit)
        self.seen_limit = int(seen_limit)

    def seen_ids(self) -> tuple[str, ...]:
        payload = self._load()
        return tuple(payload["seen_ids"])

    def history(self) -> tuple[dict[str, Any], ...]:
        payload = self._load()
        return tuple(payload["history"])

    def record(self, seen_ids: Iterable[str], alerts: Iterable[WatchlistAlert]) -> None:
        payload = self._load()
        seen = list(payload["seen_ids"])
        for alert_id in seen_ids:
            if alert_id not in seen:
                seen.append(alert_id)
        seen = seen[-self.seen_limit :]

        history = list(payload["history"])
        existing_history_ids = {
            item.get("alert_id") for item in history if isinstance(item, dict)
        }
        for alert in alerts:
            if alert.alert_id not in existing_history_ids:
                history.append(alert.to_dict())
                existing_history_ids.add(alert.alert_id)
        history = history[-self.history_limit :]
        _atomic_write_json(
            self.path,
            {"version": 1, "seen_ids": seen, "history": history},
        )

    def _load(self) -> dict[str, Any]:
        payload = _read_json_object(self.path)
        if payload is None:
            return {"version": 1, "seen_ids": [], "history": []}
        seen = payload.get("seen_ids", [])
        history = payload.get("history", [])
        if not isinstance(seen, list) or not all(isinstance(item, str) for item in seen):
            raise ValueError(f"alert seen_ids must be a JSON string list: {self.path}")
        if not isinstance(history, list) or not all(isinstance(item, dict) for item in history):
            raise ValueError(f"alert history must be a JSON object list: {self.path}")
        return {"version": 1, "seen_ids": seen, "history": history}


class KapWatchlistAlertService:
    """Poll KAP for watched BIST equities and emit only new important events."""

    def __init__(
        self,
        watchlist: WatchlistStore,
        state: AlertStateStore,
        *,
        kap_service: KapService | None = None,
        enabled: bool = True,
        lookback_days: int = 7,
        min_score: int = 80,
        max_disclosures_per_ticker: int = 100,
    ) -> None:
        if not 1 <= int(lookback_days) <= 3650:
            raise ValueError("lookback_days must be between 1 and 3650")
        if not 0 <= int(min_score) <= 100:
            raise ValueError("min_score must be between 0 and 100")
        if not 1 <= int(max_disclosures_per_ticker) <= 100:
            raise ValueError("max_disclosures_per_ticker must be between 1 and 100")
        self.watchlist = watchlist
        self.state = state
        self.kap_service = kap_service or KapService()
        self.enabled = bool(enabled)
        self.lookback_days = int(lookback_days)
        self.min_score = int(min_score)
        self.max_disclosures_per_ticker = int(max_disclosures_per_ticker)

    def check_watchlist(
        self,
        tickers: Iterable[str] | None = None,
        *,
        now: datetime | None = None,
    ) -> WatchlistAlertBatch:
        checked_at = now or datetime.now()
        if not self.enabled:
            return WatchlistAlertBatch(
                checked_at=checked_at,
                source_statuses=(
                    AlertSourceStatus(
                        ticker="*",
                        source="KAP",
                        status="disabled",
                        message="KAP watchlist alerts are disabled by configuration.",
                    ),
                ),
            )

        end = checked_at.date()
        start = end - timedelta(days=self.lookback_days)
        requested = self.watchlist.list() if tickers is None else tuple(tickers)
        canonical_tickers = WatchlistStore._validated_unique(requested, strict=True)
        already_seen = set(self.state.seen_ids())

        new_alerts: list[WatchlistAlert] = []
        observed_ids: list[str] = []
        statuses: list[AlertSourceStatus] = []

        for ticker in canonical_tickers:
            result = self.kap_service.get_disclosures(
                ticker=ticker,
                start_date=start,
                end_date=end,
                max_disclosures=self.max_disclosures_per_ticker,
                include_attachments=False,
            )
            statuses.append(
                AlertSourceStatus(
                    ticker=ticker,
                    source="KAP",
                    status=result.status,
                    message=result.message,
                )
            )
            if not result.available:
                continue

            for disclosure in result.disclosures:
                alert_id = f"KAP:{ticker}:{disclosure.disclosure_id}"
                observed_ids.append(alert_id)
                category, score, severity = classify_kap_disclosure(disclosure)
                if score < self.min_score or alert_id in already_seen:
                    continue
                new_alerts.append(
                    WatchlistAlert(
                        alert_id=alert_id,
                        source="KAP",
                        ticker=ticker,
                        published_at=disclosure.published_at,
                        title=disclosure.subject,
                        summary=disclosure.summary,
                        url=disclosure.url,
                        category=category,
                        severity=severity,
                        score=score,
                        disclosure_id=disclosure.disclosure_id,
                        is_corrective=disclosure.is_corrective,
                        has_attachment=disclosure.has_attachment,
                    )
                )

        new_alerts.sort(
            key=lambda item: (
                _SEVERITY_RANK[item.severity],
                item.score,
                item.published_at.isoformat(),
            ),
            reverse=True,
        )
        self.state.record(observed_ids, new_alerts)
        return WatchlistAlertBatch(
            checked_at=checked_at,
            alerts=tuple(new_alerts),
            source_statuses=tuple(statuses),
        )


def create_watchlist_alert_service(config: Mapping[str, Any] | None = None) -> KapWatchlistAlertService:
    """Build the Phase 10 service from the active TradingAgents configuration."""
    if config is None:
        from tradingagents.dataflows.config import get_config

        config = get_config()

    watchlist = WatchlistStore(
        config["watchlist_path"],
        seed_tickers=config.get("default_tickers", ()),
    )
    state = AlertStateStore(
        config["alert_state_path"],
        history_limit=int(config.get("alert_history_limit", 500)),
        seen_limit=int(config.get("alert_seen_limit", 5000)),
    )
    return KapWatchlistAlertService(
        watchlist,
        state,
        kap_service=KapService(timeout=float(config.get("kap_timeout_seconds", 15.0))),
        enabled=bool(config.get("kap_alerts_enabled", True)),
        lookback_days=int(config.get("kap_alert_lookback_days", 7)),
        min_score=int(config.get("kap_alert_min_score", 80)),
        max_disclosures_per_ticker=int(config.get("kap_alert_max_disclosures", 100)),
    )
