"""Turkish IPO (halka arz) calendar vendor.

Feeds the ARVEN Trade "Halka Arz" view. There is no official free API for
this — KAP and Borsa Istanbul publish individual disclosures/prospectuses,
not a browsable market-wide calendar — so this scrapes the two public,
crawler-permitting listing pages of halkaarztakvimi.com.tr (its own
robots.txt explicitly allows AI/search crawlers) and, on demand, the
per-company detail page for financial fields.

Two-stage by design: ``get_ipo_calendar`` hits only the two list pages (fast,
2 requests, enough for the list/card view); ``get_ipo_detail`` fetches one
company's page only when its card is opened. This avoids fetching a detail
page per list item on every calendar load.

Field availability differs by company and offering stage: an early-stage
filing has no price yet, a spin-off (e.g. a "denge fiyatı" listing) may never
have a fixed offer price, and the source itself is inconsistent about decimal
separators across companies. ``offer_price`` is therefore kept as the raw
text the site shows rather than parsed into a float, and every detail field
is optional.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

import requests
from parsel import Selector

from .errors import NoMarketDataError

IpoGroup = Literal["pending", "completed"]

_BASE_URL = "https://www.halkaarztakvimi.com.tr"
_LIST_URLS: dict[IpoGroup, str] = {
    "pending": f"{_BASE_URL}/onay-bekleyen-halka-arzlar/",
    "completed": f"{_BASE_URL}/guncel-halka-arzlar/",
}
_HEADERS = {
    "User-Agent": "ARVEN-TRADE/1.0 (+https://github.com/hhakanguner-droid/Arven-Trade)",
    "Accept": "text/html",
}
_REQUEST_TIMEOUT = 20

_SLUG_FROM_URL = re.compile(rf"^{re.escape(_BASE_URL)}/([a-z0-9]+(?:-[a-z0-9]+)*)/?$")
IPO_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class IpoListing:
    slug: str
    name: str
    url: str
    group: IpoGroup
    published_at: str | None
    summary: str | None

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "name": self.name,
            "url": self.url,
            "group": self.group,
            "published_at": self.published_at,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class IpoDetail:
    slug: str
    name: str
    url: str
    status: str | None
    sector: str | None
    intermediary: str | None
    ticker: str | None
    offer_price: str | None
    subscription_dates: str | None
    market_tier: str | None
    allocation_method: str | None

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "name": self.name,
            "url": self.url,
            "status": self.status,
            "sector": self.sector,
            "intermediary": self.intermediary,
            "ticker": self.ticker,
            "offer_price": self.offer_price,
            "subscription_dates": self.subscription_dates,
            "market_tier": self.market_tier,
            "allocation_method": self.allocation_method,
        }


def _fetch_html(url: str) -> str:
    response = requests.get(url, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text


def _slug_from_url(url: str) -> str | None:
    match = _SLUG_FROM_URL.match(url.strip())
    return match.group(1) if match else None


def _joined_text(fragments: list[str]) -> str | None:
    text = "".join(fragment.strip() for fragment in fragments).strip()
    return text or None


def _parse_listing_page(html: str, group: IpoGroup) -> list[IpoListing]:
    """Parse the primary grid listing, ignoring the theme's cross-category sidebar widgets.

    ``article.listing-item-grid`` is the page's own primary content template;
    the sidebar's "recent posts" widgets reuse similar class names
    (``listing-item-thumbnail``) but belong to a different category, so
    scoping to the grid variant is what keeps this from mixing groups.
    """
    listings: list[IpoListing] = []
    for article in Selector(text=html).css("article.listing-item-grid"):
        link = article.css(".title a.post-url::attr(href)").get()
        name = article.css(".title a.post-url::text").get()
        if not link or not name:
            continue
        slug = _slug_from_url(link)
        if not slug:
            continue
        published_at = article.css("time.post-published::attr(datetime)").get()
        summary = _joined_text(article.css(".post-summary::text").getall())
        listings.append(
            IpoListing(
                slug=slug,
                name=name.strip(),
                url=link,
                group=group,
                published_at=published_at,
                summary=summary,
            )
        )
    return listings


def get_ipo_calendar() -> dict:
    """Fetch the pending and completed IPO lists.

    Each list fails independently — a source outage for one group still
    returns the other, with the failure recorded in ``errors``.
    """
    listings: list[dict] = []
    errors: list[dict] = []
    for group, url in _LIST_URLS.items():
        try:
            html = _fetch_html(url)
        except Exception as exc:  # noqa: BLE001 - vendor failure funnels into `errors`
            errors.append({"group": group, "url": url, "message": str(exc)})
            continue
        listings.extend(item.to_dict() for item in _parse_listing_page(html, group))

    return {"listings": listings, "errors": errors}


def get_ipo_detail(slug: str) -> dict:
    """Fetch one company's detail page.

    Raises ``NoMarketDataError`` when the slug does not resolve to a company
    page (deleted/renamed listing, or a slug that never existed).
    """
    if not IPO_SLUG_PATTERN.fullmatch(slug):
        raise ValueError(f"not a valid IPO slug: {slug!r}")

    url = f"{_BASE_URL}/{slug}/"
    html = _fetch_html(url)
    selector = Selector(text=html)

    name = selector.css("h1.single-post-title::text").get()
    if not name:
        raise NoMarketDataError(slug, slug, "company page not found")

    status = _joined_text(selector.css(".post-subtitle strong::text").getall())

    detay1_fields: dict[str, str] = {}
    for row in selector.css(".detay1 .flex1"):
        spans = [s.strip() for s in row.css("span::text").getall() if s.strip()]
        if len(spans) >= 2:
            detay1_fields[spans[0].rstrip(":")] = spans[1]

    flexiskod_fields: dict[str, str] = {}
    for block in selector.css(".flexiskod"):
        label = _joined_text(block.css("div:nth-child(1)::text").getall())
        value = _joined_text(block.css("div:nth-child(2) ::text").getall())
        if label and value:
            flexiskod_fields[label] = value

    return IpoDetail(
        slug=slug,
        name=name.strip(),
        url=url,
        status=status,
        sector=detay1_fields.get("Faaliyet Alanı"),
        intermediary=detay1_fields.get("Aracı Kurum"),
        ticker=flexiskod_fields.get("İşlem Kodu"),
        offer_price=flexiskod_fields.get("Halka Arz Fiyatı"),
        subscription_dates=flexiskod_fields.get("Talep Toplama Tarihleri"),
        market_tier=flexiskod_fields.get("Pazar"),
        allocation_method=flexiskod_fields.get("Dağıtım Şekli"),
    ).to_dict()
