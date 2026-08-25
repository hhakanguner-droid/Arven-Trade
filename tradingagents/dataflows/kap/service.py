"""KAP adapter used by tools and API consumers.

All kap-client specifics live here so the agent graph remains independent from
the third-party client and KAP outages degrade to typed results.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta

import httpx
from kap_client import CompanyNotFoundError, Kap, KapError, RateLimitError

from .models import KapAttachment, KapDisclosure, KapDisclosureResult

logger = logging.getLogger(__name__)

_BIST_YAHOO_SYMBOL = re.compile(r"^(?P<ticker>[A-Z][A-Z0-9]{1,9})\.IS$")
_KAP_LISTED_COMPANIES_URL = "https://www.kap.org.tr/tr/api/company/items/IGS/A"
_KAP_HEADERS = {
    "Accept": "application/json",
    "Referer": "https://www.kap.org.tr/",
    "User-Agent": "ARVEN-TRADE/1.0",
}
_SIGNIFICANCE_TERMS = {
    "finansal rapor": 100,
    "finansal sonuç": 100,
    "kar payı": 95,
    "temettü": 95,
    "sermaye artır": 95,
    "bedelli": 95,
    "bedelsiz": 90,
    "geri alım": 90,
    "birleşme": 90,
    "bölünme": 90,
    "satın alma": 90,
    "ihale": 85,
    "sözleşme": 85,
    "iş ilişkisi": 80,
    "yatırım": 80,
    "kapasite": 80,
    "borçlanma": 75,
    "finansman": 75,
    "kredi": 70,
    "dava": 85,
    "ceza": 90,
    "faaliyet durdur": 95,
    "üretim": 75,
    "derecelendirme": 70,
    "yönetim": 65,
    "pay satışı": 80,
    "ortaklık": 70,
}


def normalize_bist_ticker_for_kap(ticker: str) -> str:
    """Return KAP's bare ticker for a validated Yahoo BIST equity symbol.

    Only a terminal ``.IS`` exchange suffix is accepted. This avoids treating
    arbitrary foreign symbols containing the characters ``IS`` as BIST stocks.
    """
    if not isinstance(ticker, str):
        raise TypeError("ticker must be a string")
    normalized = ticker.strip().upper()
    match = _BIST_YAHOO_SYMBOL.fullmatch(normalized)
    if match is None:
        raise ValueError(f"not a BIST Yahoo ticker: {ticker!r}")
    return match.group("ticker")


def is_bist_ticker(ticker: object) -> bool:
    try:
        normalize_bist_ticker_for_kap(ticker)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return True


def _date_string(value: str | date | datetime | None, fallback: date) -> str:
    if value is None:
        return fallback.isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    parsed = date.fromisoformat(value)
    return parsed.isoformat()


def _significance(disclosure) -> tuple[int, datetime]:
    text = f"{disclosure.subject} {disclosure.summary}".casefold()
    score = max((weight for term, weight in _SIGNIFICANCE_TERMS.items() if term in text), default=0)
    if disclosure.disclosure_type.upper() in {"FR", "FS"}:
        score = max(score, 100)
    if disclosure.is_corrective:
        score += 10
    return score, disclosure.publish_datetime


def _select_significant(
    disclosures: Iterable,
    limit: int,
    significance_key: Callable[[object], tuple[int, datetime]] | None = None,
) -> list:
    """Select a bounded mix of fresh actionable and significant disclosures.

    The bounded set must satisfy two competing Phase 10 requirements:
    older high-score records must not permanently starve newer actionable IDs,
    and a newest score-zero record must not consume the only slot while a real
    alert is present. Therefore the freshness quota is drawn from records with
    positive significance first. Remaining capacity is filled by significance;
    only when the whole window is non-actionable do we fall back to pure recency.
    """
    items = list(disclosures)
    if not items:
        return []

    key = significance_key or _significance
    scored = [(item, key(item)) for item in items]
    actionable = [pair for pair in scored if pair[1][0] > 0]

    if not actionable:
        return sorted(items, key=lambda item: item.publish_datetime, reverse=True)[:limit]

    newest_actionable = sorted(
        actionable,
        key=lambda pair: pair[0].publish_datetime,
        reverse=True,
    )
    recent_quota = min(limit, max(1, (limit + 1) // 2))
    selected = [item for item, _ in newest_actionable[:recent_quota]]
    selected_identity = {id(item) for item in selected}

    if len(selected) < limit:
        remaining = [pair for pair in scored if id(pair[0]) not in selected_identity]
        ranked = sorted(remaining, key=lambda pair: pair[1], reverse=True)
        selected.extend(item for item, _ in ranked[: limit - len(selected)])

    return sorted(selected, key=lambda item: item.publish_datetime, reverse=True)


class KapService:
    """Single synchronous adapter around :class:`kap_client.Kap`."""

    def __init__(
        self,
        timeout: float = 15.0,
        client_factory: Callable[..., Kap] = Kap,
        company_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        self.timeout = timeout
        self.client_factory = client_factory
        self.company_resolver = company_resolver or self._resolve_company_oid

    def get_disclosures(
        self,
        ticker: str,
        start_date: str | date | datetime | None = None,
        end_date: str | date | datetime | None = None,
        max_disclosures: int = 10,
        *,
        lookback_days: int = 30,
        include_attachments: bool = True,
        significance_key: Callable[[object], tuple[int, datetime]] | None = None,
        summary_limit: int | None = 600,
    ) -> KapDisclosureResult:
        today = date.today()
        end = _date_string(end_date, today)
        if isinstance(lookback_days, bool) or not 1 <= int(lookback_days) <= 3650:
            raise ValueError("lookback_days must be between 1 and 3650")
        start = _date_string(
            start_date,
            date.fromisoformat(end) - timedelta(days=int(lookback_days)),
        )
        if date.fromisoformat(start) > date.fromisoformat(end):
            raise ValueError("start_date must not be after end_date")
        if isinstance(max_disclosures, bool) or not 1 <= int(max_disclosures) <= 100:
            raise ValueError("max_disclosures must be between 1 and 100")
        if summary_limit is not None:
            if isinstance(summary_limit, bool) or int(summary_limit) < 1:
                raise ValueError("summary_limit must be a positive integer or None")
            summary_limit = int(summary_limit)
        limit = int(max_disclosures)

        try:
            kap_ticker = normalize_bist_ticker_for_kap(ticker)
        except (TypeError, ValueError):
            return KapDisclosureResult(
                status="not_bist",
                ticker=str(ticker),
                kap_ticker=None,
                start_date=start,
                end_date=end,
                message="KAP analizi yalnızca .IS uzantılı BIST hisseleri için uygulanır.",
            )

        try:
            with self.client_factory(timeout=self.timeout) as client:
                try:
                    company_oid = client.find_company(kap_ticker).oid
                except CompanyNotFoundError:
                    company_oid = self.company_resolver(kap_ticker)
                    if company_oid is None:
                        raise
                raw = client.fetch_disclosures(company_oid, start, end)
                selected = _select_significant(raw, limit, significance_key)
                mapped = tuple(
                    self._map_disclosure(
                        client,
                        item,
                        kap_ticker,
                        include_attachments,
                        summary_limit,
                    )
                    for item in selected
                )
            return KapDisclosureResult(
                status="ok",
                ticker=ticker.upper(),
                kap_ticker=kap_ticker,
                start_date=start,
                end_date=end,
                message=(
                    f"{len(raw)} KAP bildirimi bulundu; yatırım açısından en ilgili "
                    f"{len(mapped)} kayıt aktarıldı."
                ),
                disclosures=mapped,
                total_found=len(raw),
            )
        except CompanyNotFoundError:
            return self._failure(
                "company_not_found", ticker, kap_ticker, start, end,
                "KAP şirket kaydında bu BIST kodu bulunamadı.",
            )
        except RateLimitError as exc:
            detail = f" Yeniden deneme süresi: {exc.retry_after:.0f} sn." if exc.retry_after else ""
            return self._failure(
                "rate_limited", ticker, kap_ticker, start, end,
                f"KAP erişim limiti aşıldı.{detail} Analiz diğer verilerle devam edebilir.",
            )
        except (httpx.TimeoutException, TimeoutError):
            return self._failure(
                "timeout", ticker, kap_ticker, start, end,
                "KAP isteği zaman aşımına uğradı. Analiz diğer verilerle devam edebilir.",
            )
        except KapError as exc:
            logger.warning("KAP client failed for %s: %s", ticker, exc)
            return self._failure(
                "unavailable", ticker, kap_ticker, start, end,
                "KAP verisi geçici olarak alınamadı. Analiz diğer verilerle devam edebilir.",
            )
        except Exception as exc:  # noqa: BLE001 - KAP must never abort the graph
            logger.warning("Unexpected KAP failure for %s: %s", ticker, exc)
            return self._failure(
                "unavailable", ticker, kap_ticker, start, end,
                "KAP verisi geçici olarak alınamadı. Analiz diğer verilerle devam edebilir.",
            )

    @staticmethod
    def _map_disclosure(
        client,
        item,
        ticker: str,
        include_attachments: bool,
        summary_limit: int | None = 600,
    ) -> KapDisclosure:
        attachments: tuple[KapAttachment, ...] = ()
        if include_attachments and item.has_attachment:
            try:
                attachments = tuple(
                    KapAttachment(filename=attachment.filename, url=attachment.url)
                    for attachment in client.fetch_attachments(item.index)[:5]
                )
            except Exception as exc:  # noqa: BLE001 - metadata enrichment is optional
                logger.info("KAP attachment metadata unavailable for %s: %s", item.index, exc)
        summary = item.summary if summary_limit is None else item.summary[:summary_limit]
        return KapDisclosure(
            published_at=item.publish_datetime,
            company=item.company_name,
            ticker=ticker,
            subject=item.subject,
            disclosure_type=item.disclosure_type,
            url=item.url,
            has_attachment=item.has_attachment,
            is_corrective=item.is_corrective,
            disclosure_id=item.index,
            summary=summary,
            attachments=attachments,
        )

    def _resolve_company_oid(self, ticker: str) -> str | None:
        """Resolve current KAP IGS schema when kap-client's legacy list misses it."""
        with httpx.Client(
            timeout=self.timeout,
            headers=_KAP_HEADERS,
            follow_redirects=True,
        ) as client:
            response = client.get(_KAP_LISTED_COMPANIES_URL)
            response.raise_for_status()
            payload = response.json()
        rows = payload if isinstance(payload, list) else payload.get("data", [])
        if not isinstance(rows, list) or not rows:
            raise KapError("KAP listed-company registry returned no rows")
        for row in rows:
            codes = str(row.get("stockCode") or row.get("stockCodes") or "")
            if ticker in {code.strip().upper() for code in codes.split(",")}:
                oid = row.get("mkkMemberOid") or row.get("memberOid")
                return str(oid) if oid else None
        return None

    @staticmethod
    def _failure(status, ticker, kap_ticker, start, end, message) -> KapDisclosureResult:
        return KapDisclosureResult(
            status=status,
            ticker=ticker,
            kap_ticker=kap_ticker,
            start_date=start,
            end_date=end,
            message=message,
        )
