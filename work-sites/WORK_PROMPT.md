# ChatGPT Work / Sites Prompt — ARVEN Trade Phase 15

Update the **existing** ARVEN Trade Site. **Do not create a new Site.** Keep the same production URL:

`https://arven-trade.hhakanguner.chatgpt.site/`

This phase adds two new sections: **Piyasalar** (market overview + price history chart) and **Halka Arz** (Turkish IPO calendar).

## Canonical sources
- GitHub repository: `hhakanguner-droid/Arven-Trade`
- Production/backend behavior source: `main`
- Behavior contract: `docs/ARVEN_WEB_API.md` (now includes "Market data (Piyasalar)" and "IPO calendar (Halka Arz)" sections)
- Work/Sites handoff: `docs/ARVEN_WORK_SITES_HANDOFF.md`
- Machine-readable contract: `work-sites/site-contract.json` (now includes `markets` and `ipo_calendar` sections — read these first)
- Phase 15 instructions: this file

## Deployment architecture — unchanged from Phase 14
Sites remains the full-stack host. Implement `/api/arven/market`, `/api/arven/price-history/{ticker}`, `/api/arven/ipo-calendar` and `/api/arven/ipo-calendar/{slug}` as real same-origin Sites server routes. Treat the Phase 13 Python FastAPI endpoints as the behavioral reference, not something that needs a separately deployed backend. Use D1 for any caching; do not require `TRADINGAGENTS_API_TOKEN` for Site-to-itself calls.

## New sidebar items
Add two items to the left nav, in this order relative to the existing menu:
Ana Pano, Hisse Analizi, Geçmiş, Karşılaştırma, Performans, Takip Listem, KAP Açıklamaları, **Piyasalar** (new), **Halka Arz** (new).

## Piyasalar page
Calls `/api/arven/market` and `/api/arven/price-history/{ticker}`.
1. Page header: "Piyasalar" title, subtitle, current date.
2. A dark, horizontally auto-scrolling ticker tape (pauses on hover) showing the highest-priority instruments (USD/TRY, EUR/TRY, BIST100, ons altın, gram altın, Brent, BTC) — value + colored up/down indicator.
3. A responsive card grid, one card per instrument group from the snapshot (`fx`, `parity`, `index`, `commodity`, `crypto`). FX cards show alış/satış; index cards show a small trend sparkline.
4. A full-width "Hisse Geçmişi" panel below the grid: a ticker search/select (default: user's last-analyzed or first watchlist stock), quick-select chips from the user's watchlist, a stat row (current price, daily change %, period change % for the active range, 52-week high/low), range tabs (1G/1H/1A/6A/1Y/5Y), and a filled line chart with a highlighted endpoint.

Never fabricate a quote or chart point when a specific instrument's backend call failed — render that one row/instrument as unavailable, keep rendering the rest of the page.

## Halka Arz page
Calls `/api/arven/ipo-calendar` for the list, `/api/arven/ipo-calendar/{slug}` per company (lazily, when a card is opened — do not eagerly fetch every company's detail on page load).

Two sections, grouped by the API's `group` field:
- **"Onay Bekleyen Halka Arzlar"** (`pending`)
- **"Tamamlanmış Halka Arzlar"** (`completed`)

Each a responsive grid of compact cards: company name, summary/status, published date from the list call; ticker, offer price, subscription dates, market tier and allocation method from the detail call, shown only for the fields that call actually returned. `offer_price` is raw source text (the source itself is inconsistent about decimal separators) — display as-is, never reparse it as a number.

This is third-party editorial content, not an official regulator feed — add a small "kaynak" note (see `docs/ARVEN_WEB_API.md`), and never fabricate a listing or a detail field that the API didn't return.

## Do not
- Do not require or ask for a separately deployed backend for either page.
- Do not fake data on a failed source call — surface the gap plainly (omit the row, a small inline note), never a stale or invented number.
