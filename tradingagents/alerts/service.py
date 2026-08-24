"""Persistent watchlist and KAP alert service for ARVEN Trade.

The service is deliberately UI-agnostic: CLI, web, PWA, or a scheduler can call
``check_watchlist`` and deliver the returned notification payload however they
choose. KAP failures are represented as source statuses and never fabricated
into alerts.
"""

from __future__ import annotations

import errno
import json
import os
import re
import tempfile
import time
import unicodedata
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytz

from tradingagents.dataflows.bist import is_bist_yahoo_symbol, normalize_bist_yahoo_symbol
from tradingagents.dataflows.kap.models import KapDisclosure
from tradingagents.dataflows.kap.service import KapService

from .models import AlertCategory, AlertSeverity, AlertSourceStatus, WatchlistAlert, WatchlistAlertBatch

_EVENT_RULES: tuple[tuple[AlertCategory, int, tuple[str, ...]], ...] = (
    ("financials", 100, ("finansal rapor", "finansal sonuç", "bilanço", "gelir tablosu")),
    ("dividend", 95, ("kar payı", "temettü", "kâr payı")),
    ("capital", 95, ("sermaye artır", "bedelli", "bedelsiz", "sermaye azalt")),
    ("mna", 90, ("birleşme", "bölünme", "satın alma", "devralma", "devir")),
    ("ownership", 90, ("geri alım", "pay geri alım")),
    ("commercial", 85, ("ihale", "sözleşme", "iş ilişkisi", "sipariş")),
    ("legal", 85, ("dava", "ceza", "soruşturma", "yaptırım", "faaliyet durdur")),
    ("operations", 80, ("yatırım", "kapasite", "üretim", "fabrika", "tesis")),
    (
        "ownership",
        80,
        ("pay satışı", "pay alımı", "pay alım satım", "ortaklık", "hakim ortak"),
    ),
    ("financing", 75, ("borçlanma", "finansman", "kredi", "tahvil", "bono")),
    ("governance", 65, ("yönetim", "genel müdür", "yönetici", "bağımsız üye")),
)

_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
_ISTANBUL_TZ = pytz.timezone("Europe/Istanbul")
_STATE_VERSION = 2
_ALERT_SUMMARY_LIMIT = 600
_STRONG_TRANSFER_CONTEXT_STEMS = ("pay", "hisse", "varlik", "isletme", "istirak", "tesis")
_GOVERNANCE_TRANSFER_STEMS = ("yonetim", "yetki", "gorev", "sorumluluk", "imza")


def _normalize_event_text(value: str) -> str:
    """Normalize Turkish casing/diacritics for deterministic keyword matching."""
    folded = value.casefold().replace("ı", "i")
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", folded)
        if not unicodedata.combining(char)
    )


def _token_has_stem(token: str, stems: tuple[str, ...]) -> bool:
    return any(token.startswith(stem) for stem in stems)


def _is_devir_token(token: str) -> bool:
    """Match transfer noun/verb inflections without matching operational 'devreye'."""
    return token.startswith(("devir", "devri", "devred", "devret"))


def _devir_has_acquisition_context(text: str) -> bool:
    """Treat devir as M&A only near share/asset/business/company context."""
    tokens = re.findall(r"\w+", text)
    for index, token in enumerate(tokens):
        if not _is_devir_token(token):
            continue
        nearby = tokens[max(0, index - 3) : index] + tokens[index + 1 : index + 4]
        if any(_token_has_stem(item, _STRONG_TRANSFER_CONTEXT_STEMS) for item in nearby):
            return True
        if any(_token_has_stem(item, _GOVERNANCE_TRANSFER_STEMS) for item in nearby):
            continue
        if any(item.startswith("sirket") for item in nearby):
            return True
    return False


def _is_articles_of_association_context(text: str) -> bool:
    """Identify Ana/Esas Sözleşme disclosures so later shorthand stays excluded."""
    return re.search(r"(?<!\w)(?:esas|ana)\s+sozlesme\w*", text) is not None


def _event_term_matches(text: str, term: str) -> bool:
    """Match alert terms while avoiding known Turkish substring false positives."""
    normalized = _normalize_event_text(term)
    if normalized == "yatirim":
        # Keep Turkish inflections such as "yatırımı"/"yatırımlar" while
        # excluding the distinct investor stem "yatırımcı...".
        return re.search(r"(?<!\w)yatirim(?!ci)", text) is not None
    if normalized == "ceza":
        # Match the legal noun and common inflections, but not the country name
        # "Cezayir" which otherwise contains the raw substring "ceza".
        accepted_tokens = {
            "ceza",
            "cezai",
            "cezasi",
            "cezasina",
            "cezasini",
            "cezasinda",
            "cezasindan",
            "cezasinin",
            "cezanin",
            "cezaya",
            "cezayi",
            "cezada",
            "cezadan",
            "cezalar",
            "cezalari",
            "cezalarina",
            "cezalarini",
            "cezalarinda",
            "cezalarindan",
            "cezalarin",
        }
        return any(
            token in accepted_tokens or token.startswith("cezalandir")
            for token in re.findall(r"\w+", text)
        )
    if normalized == "birlesme":
        # Cover birleşme/birleşti/birleşiyor/etc., but not "Birleşik" place names.
        return re.search(r"(?<!\w)birles(?!ik)\w*", text) is not None
    if normalized == "bolunme":
        return re.search(r"(?<!\w)bolun\w*", text) is not None
    if normalized == "satin alma":
        # "satın" already supplies strong acquisition context, so accept noun,
        # passive and active verb inflections: alma/alımı/alınması/aldı/alacak/alıyor/etc.
        return re.search(r"(?<!\w)satin\s+al\w*", text) is not None
    if normalized == "devralma":
        return re.search(r"(?<!\w)devral\w*", text) is not None
    if normalized == "devir":
        return _devir_has_acquisition_context(text)
    if normalized == "sozlesme":
        # Once the disclosure identifies Ana/Esas Sözleşme (articles of association),
        # later shorthand such as "Sözleşmenin 6. maddesi" must not reactivate a
        # commercial-contract alert.
        if _is_articles_of_association_context(text):
            return False
        return re.search(r"(?<!\w)sozlesme\w*", text) is not None
    if normalized == "pay alim satim":
        # KAP commonly uses both spaced and hyphenated forms.
        return re.search(r"(?<!\w)pay\s+alim(?:\s*-\s*|\s+)satim(?!\w)", text) is not None
    return normalized in text


def _classify_event_fields(
    subject: str,
    summary: str,
    disclosure_type: str,
    is_corrective: bool,
) -> tuple[AlertCategory, int, AlertSeverity]:
    text = _normalize_event_text(f"{subject} {summary}")
    category: AlertCategory = "other"
    score = 0

    if disclosure_type.upper() in {"FR", "FS"}:
        category, score = "financials", 100

    for candidate, weight, terms in _EVENT_RULES:
        if weight <= score:
            continue
        if any(_event_term_matches(text, term) for term in terms):
            category, score = candidate, weight

    if is_corrective and score:
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


def classify_kap_disclosure(disclosure: KapDisclosure) -> tuple[AlertCategory, int, AlertSeverity]:
    """Classify one KAP disclosure into a deterministic alert category/severity."""
    return _classify_event_fields(
        disclosure.subject,
        disclosure.summary,
        disclosure.disclosure_type,
        disclosure.is_corrective,
    )


def _alert_significance_key(disclosure: object) -> tuple[int, datetime]:
    """Rank raw kap-client disclosures with the same rules used by alerts."""
    _, score, _ = _classify_event_fields(
        str(getattr(disclosure, "subject", "")),
        str(getattr(disclosure, "summary", "")),
        str(getattr(disclosure, "disclosure_type", "")),
        bool(getattr(disclosure, "is_corrective", False)),
    )
    published_at = getattr(disclosure, "publish_datetime", None)
    if not isinstance(published_at, datetime):
        published_at = datetime.min
    return score, published_at


def _bounded_alert_summary(value: str, limit: int = _ALERT_SUMMARY_LIMIT) -> str:
    """Bound persisted/delivered alert summaries while classification keeps full text."""
    if len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    return f"{value[: limit - 3].rstrip()}..."


def _alert_dict_priority(item: Mapping[str, Any]) -> tuple[int, int, str]:
    severity = str(item.get("severity", "low"))
    try:
        score = int(item.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    published_at = str(item.get("published_at", ""))
    return _SEVERITY_RANK.get(severity, -1), score, published_at


def _market_datetime(value: datetime | None) -> datetime:
    """Return a datetime anchored to the Borsa Istanbul calendar."""
    if value is None:
        return datetime.now(_ISTANBUL_TZ)
    if value.tzinfo is None:
        return _ISTANBUL_TZ.localize(value)
    return value.astimezone(_ISTANBUL_TZ)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomically replace a JSON file without sharing a fixed temporary path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
            tmp_path = Path(handle.name)
        os.replace(tmp_path, path)
        tmp_path = None
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass


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


@contextmanager
def _exclusive_file_lock(path: Path) -> Iterator[None]:
    """Acquire a blocking inter-process lock using only the standard library."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if os.name == "nt":  # pragma: no cover - Windows-only branch
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()

            while True:
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                        raise
                    time.sleep(0.1)

            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class WatchlistStore:
    """Small JSON-backed BIST watchlist with canonical ``.IS`` symbols."""

    def __init__(self, path: str | Path, seed_tickers: Iterable[str] = ()) -> None:
        self.path = Path(path).expanduser()
        self.seed_tickers = tuple(seed_tickers)
        self.lock_path = self.path.with_name(f"{self.path.name}.lock")

    def list(self) -> tuple[str, ...]:
        with _exclusive_file_lock(self.lock_path):
            return tuple(self._list_unlocked())

    def add(self, ticker: str) -> bool:
        canonical = normalize_bist_yahoo_symbol(ticker)
        with _exclusive_file_lock(self.lock_path):
            tickers = self._list_unlocked()
            if canonical in tickers:
                return False
            tickers.append(canonical)
            self._save_unlocked(tickers)
            return True

    def remove(self, ticker: str) -> bool:
        canonical = normalize_bist_yahoo_symbol(ticker)
        with _exclusive_file_lock(self.lock_path):
            tickers = self._list_unlocked()
            if canonical not in tickers:
                return False
            tickers.remove(canonical)
            self._save_unlocked(tickers)
            return True

    def replace(self, tickers: Iterable[str]) -> tuple[str, ...]:
        validated = self._validated_unique(tickers, strict=True)
        with _exclusive_file_lock(self.lock_path):
            self._save_unlocked(validated)
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

    def _list_unlocked(self) -> list[str]:
        payload = _read_json_object(self.path)
        if payload is None:
            tickers = self._validated_unique(self.seed_tickers)
            self._save_unlocked(tickers)
            return tickers
        if payload.get("version") != 1 or "tickers" not in payload:
            raise ValueError(f"invalid watchlist schema: {self.path}")
        raw = payload["tickers"]
        if not isinstance(raw, list):
            raise ValueError(f"watchlist tickers must be a JSON list: {self.path}")
        return self._validated_unique(raw, strict=True)

    def _save_unlocked(self, tickers: Iterable[str]) -> None:
        _atomic_write_json(self.path, {"version": 1, "tickers": list(tickers)})


class AlertStateStore:
    """Persistent discovery de-duplication, retryable outbox, and alert history."""

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
        self.lock_path = self.path.with_name(f"{self.path.name}.lock")

    @contextmanager
    def locked(self) -> Iterator[None]:
        """Serialize state mutations across workers."""
        with _exclusive_file_lock(self.lock_path):
            yield

    def seen_ids(self) -> tuple[str, ...]:
        with self.locked():
            payload = self._load_unlocked()
            return tuple(payload["seen_ids"])

    def pending(self) -> tuple[dict[str, Any], ...]:
        """Return alerts waiting for downstream delivery acknowledgement."""
        with self.locked():
            payload = self._load_unlocked()
            return tuple(dict(item) for item in payload["pending"])

    def history(self) -> tuple[dict[str, Any], ...]:
        with self.locked():
            payload = self._load_unlocked()
            return tuple(dict(item) for item in payload["history"])

    def ensure_capacity(
        self,
        tickers: Iterable[str],
        per_ticker_cap: int,
        *,
        active_tickers: Iterable[str] | None = None,
    ) -> None:
        """Register successful tickers and optionally retire inactive watchlist symbols."""
        canonical = WatchlistStore._validated_unique(tickers, strict=True)
        active = (
            None
            if active_tickers is None
            else set(WatchlistStore._validated_unique(active_tickers, strict=True))
        )
        if per_ticker_cap < 1:
            raise ValueError("per_ticker_cap must be positive")
        with self.locked():
            payload = self._load_unlocked()
            tracked = list(payload["tracked_tickers"])
            if active is not None:
                tracked = [ticker for ticker in tracked if ticker in active]
            for ticker in canonical:
                if ticker not in tracked:
                    tracked.append(ticker)
            required = len(tracked) * int(per_ticker_cap)
            if self.seen_limit < required:
                raise ValueError(
                    "alert_seen_limit must be at least tracked_ticker_count * "
                    "kap_alert_max_disclosures to prevent duplicate alerts"
                )
            if tracked != payload["tracked_tickers"]:
                payload["tracked_tickers"] = tracked
                self._save_unlocked(payload)

    def claim(
        self,
        seen_ids: Iterable[str],
        alerts: Iterable[WatchlistAlert],
    ) -> tuple[WatchlistAlert, ...]:
        """Atomically claim newly discovered alerts into the retryable outbox."""
        observed = list(dict.fromkeys(str(alert_id) for alert_id in seen_ids))
        candidates = tuple(alerts)
        with self.locked():
            payload = self._load_unlocked()
            seen = list(payload["seen_ids"])
            previously_seen = set(seen)
            pending = list(payload["pending"])
            pending_ids = {
                str(item["alert_id"])
                for item in pending
                if isinstance(item, dict) and "alert_id" in item
            }
            history_ids = {
                str(item["alert_id"])
                for item in payload["history"]
                if isinstance(item, dict) and isinstance(item.get("alert_id"), str)
            }

            claimed: list[WatchlistAlert] = []
            for alert in candidates:
                if (
                    alert.alert_id in previously_seen
                    or alert.alert_id in pending_ids
                    or alert.alert_id in history_ids
                ):
                    continue
                pending.append(alert.to_dict())
                pending_ids.add(alert.alert_id)
                claimed.append(alert)

            if observed:
                observed_set = set(observed)
                seen = [alert_id for alert_id in seen if alert_id not in observed_set]
                seen.extend(observed)

            if len(seen) > self.seen_limit:
                seen = seen[-self.seen_limit :]

            payload["seen_ids"] = seen
            payload["pending"] = pending
            self._save_unlocked(payload)
            return tuple(claimed)

    def acknowledge(self, alert_ids: Iterable[str]) -> int:
        """Mark pending alerts delivered and move them into bounded history."""
        requested = {str(alert_id) for alert_id in alert_ids}
        if not requested:
            return 0

        with self.locked():
            payload = self._load_unlocked()
            pending = list(payload["pending"])
            delivered = [
                item
                for item in pending
                if isinstance(item, dict) and str(item.get("alert_id")) in requested
            ]
            if not delivered:
                return 0

            payload["pending"] = [
                item
                for item in pending
                if not (isinstance(item, dict) and str(item.get("alert_id")) in requested)
            ]

            history = list(payload["history"])
            existing_history_ids = {
                str(item.get("alert_id"))
                for item in history
                if isinstance(item, dict) and item.get("alert_id") is not None
            }
            for item in delivered:
                alert_id = str(item["alert_id"])
                if alert_id not in existing_history_ids:
                    history.append(item)
                    existing_history_ids.add(alert_id)

            history.sort(key=_alert_dict_priority, reverse=True)
            payload["history"] = history[: self.history_limit]
            self._save_unlocked(payload)
            return len(delivered)

    def _empty(self) -> dict[str, Any]:
        return {
            "version": _STATE_VERSION,
            "seen_ids": [],
            "pending": [],
            "history": [],
            "tracked_tickers": [],
        }

    def _load_unlocked(self) -> dict[str, Any]:
        payload = _read_json_object(self.path)
        if payload is None:
            return self._empty()

        version = payload.get("version")
        if version == 1:
            if "seen_ids" not in payload or "history" not in payload:
                raise ValueError(f"invalid alert state schema: {self.path}")
            seen = payload["seen_ids"]
            history = payload["history"]
            if not isinstance(seen, list) or not all(isinstance(item, str) for item in seen):
                raise ValueError(f"alert seen_ids must be a JSON string list: {self.path}")
            if not isinstance(history, list) or not all(isinstance(item, dict) for item in history):
                raise ValueError(f"alert history must be a JSON object list: {self.path}")
            tracked: list[str] = []
            for alert_id in seen:
                parts = alert_id.split(":", 2)
                if len(parts) == 3 and parts[0] == "KAP" and is_bist_yahoo_symbol(parts[1]):
                    if parts[1] not in tracked:
                        tracked.append(parts[1])
            return {
                "version": _STATE_VERSION,
                "seen_ids": list(seen),
                "pending": [],
                "history": list(history),
                "tracked_tickers": tracked,
            }

        if version != _STATE_VERSION:
            raise ValueError(f"unsupported alert state version: {self.path}")

        required = {"seen_ids", "pending", "history", "tracked_tickers"}
        if not required.issubset(payload):
            raise ValueError(f"invalid alert state schema: {self.path}")

        seen = payload["seen_ids"]
        pending = payload["pending"]
        history = payload["history"]
        tracked = payload["tracked_tickers"]

        if not isinstance(seen, list) or not all(isinstance(item, str) for item in seen):
            raise ValueError(f"alert seen_ids must be a JSON string list: {self.path}")
        if not isinstance(pending, list) or not all(isinstance(item, dict) for item in pending):
            raise ValueError(f"alert pending must be a JSON object list: {self.path}")
        if not all(isinstance(item.get("alert_id"), str) for item in pending):
            raise ValueError(f"alert pending entries require alert_id: {self.path}")
        if not isinstance(history, list) or not all(isinstance(item, dict) for item in history):
            raise ValueError(f"alert history must be a JSON object list: {self.path}")
        if not isinstance(tracked, list) or not all(isinstance(item, str) for item in tracked):
            raise ValueError(f"alert tracked_tickers must be a JSON string list: {self.path}")
        if not all(is_bist_yahoo_symbol(item) for item in tracked):
            raise ValueError(f"alert tracked_tickers contains a non-BIST symbol: {self.path}")

        return {
            "version": _STATE_VERSION,
            "seen_ids": list(seen),
            "pending": list(pending),
            "history": list(history),
            "tracked_tickers": list(tracked),
        }

    def _save_unlocked(self, payload: Mapping[str, Any]) -> None:
        normalized = {
            "version": _STATE_VERSION,
            "seen_ids": list(payload["seen_ids"]),
            "pending": list(payload["pending"]),
            "history": list(payload["history"]),
            "tracked_tickers": list(payload["tracked_tickers"]),
        }
        _atomic_write_json(self.path, normalized)


class KapWatchlistAlertService:
    """Poll KAP for watched BIST equities and emit only newly claimed important events."""

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
        checked_at = _market_datetime(now)
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
        if tickers is None:
            persisted_watchlist = self.watchlist.list()
            requested = persisted_watchlist
            active_tickers: Iterable[str] | None = persisted_watchlist
        else:
            requested = tuple(tickers)
            active_tickers = None
        canonical_tickers = WatchlistStore._validated_unique(requested, strict=True)

        candidate_alerts: list[WatchlistAlert] = []
        observed_ids: list[str] = []
        statuses: list[AlertSourceStatus] = []
        successful_tickers: list[str] = []

        for ticker in canonical_tickers:
            result = self.kap_service.get_disclosures(
                ticker=ticker,
                start_date=start,
                end_date=end,
                max_disclosures=self.max_disclosures_per_ticker,
                include_attachments=False,
                significance_key=_alert_significance_key,
                summary_limit=None,
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

            successful_tickers.append(ticker)
            for disclosure in result.disclosures:
                alert_id = f"KAP:{ticker}:{disclosure.disclosure_id}"
                observed_ids.append(alert_id)
                category, score, severity = classify_kap_disclosure(disclosure)
                if score < self.min_score:
                    continue
                candidate_alerts.append(
                    WatchlistAlert(
                        alert_id=alert_id,
                        source="KAP",
                        ticker=ticker,
                        published_at=disclosure.published_at,
                        title=disclosure.subject,
                        summary=_bounded_alert_summary(disclosure.summary),
                        url=disclosure.url,
                        category=category,
                        severity=severity,
                        score=score,
                        disclosure_id=disclosure.disclosure_id,
                        is_corrective=disclosure.is_corrective,
                        has_attachment=disclosure.has_attachment,
                    )
                )

        self.state.ensure_capacity(
            successful_tickers,
            self.max_disclosures_per_ticker,
            active_tickers=active_tickers,
        )
        candidate_alerts.sort(
            key=lambda item: (
                _SEVERITY_RANK[item.severity],
                item.score,
                item.published_at.isoformat(),
            ),
            reverse=True,
        )
        claimed_alerts = self.state.claim(observed_ids, candidate_alerts)

        return WatchlistAlertBatch(
            checked_at=checked_at,
            alerts=claimed_alerts,
            source_statuses=tuple(statuses),
        )

    def pending_alerts(self) -> tuple[dict[str, Any], ...]:
        """Expose the retryable outbox for failed or deferred deliveries."""
        return self.state.pending()

    def acknowledge_alerts(self, alert_ids: Iterable[str]) -> int:
        """Acknowledge successful downstream delivery of pending alerts."""
        return self.state.acknowledge(alert_ids)


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
