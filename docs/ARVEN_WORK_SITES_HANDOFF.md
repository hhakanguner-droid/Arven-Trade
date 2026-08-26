# ARVEN Trade — Phase 14 Work / Sites Handoff

## Purpose
Phase 14 prepares the repository and product contract for the existing ARVEN Trade PC + mobile PWA Site to be updated in ChatGPT Work / Sites and connected to the backend without exposing backend secrets in the browser. This phase moves the product from demo/prototype behavior to real end-user use.

## Canonical source
- Repository: `hhakanguner-droid/Arven-Trade`
- Production branch: `main`
- Phase 13 backend baseline commit: `44a72f6f64dcb249e7ff0c36ae5f51031e8dd881`
- Existing live Site: `https://arven-trade.hhakanguner.chatgpt.site/`
- The Work/Sites implementation must update that Site, not create a replacement Site.
- GitHub `main` remains the source of truth for backend/API behavior.

## Canonical visual references
Use these project assets as the visual source of truth. Preserve the ARVEN corporate language, layout hierarchy and dark/deep-blue product identity.

- `ARVEN_TRADE_PC_Mobil_PWA_Mockuplari.pdf`
- `ARVEN_TRADE_PC_Ana_Pano.png`
- `ARVEN_TRADE_PC_Hisse_Analizi.png`
- `ARVEN_TRADE_Mobil_PWA_Mockuplari.png`
- `ARVEN_TRADE_Splash_Mockup.png`
- `ARVEN_TRADE_Logo.png`

The first-load splash should follow the approved ARVEN splash mockup and approved transition timing. Do not replace the approved layout with a generic finance dashboard template.

## Product scope
ARVEN Trade is BIST/Türkiye focused. Foreign-market symbols are out of scope. Remove demo/sample financial and analysis data. When real data is absent, show explicit Turkish empty states instead of fake values.

The latest/current analyzed stock is the first and most prominent block on Ana Pano. Agent explanations and debate summaries are 3–5 complete Turkish sentences each.

## Phase 13 API surface
The backend contract is documented in `docs/ARVEN_WEB_API.md`.

Public liveness:
- `GET /healthz`

Authenticated API:
- `GET /api/v1/health`
- `POST /api/v1/analyses`
- `GET /api/v1/analyses/{job_id}`
- `GET /api/v1/history`
- `GET /api/v1/history/{analysis_id}`
- `GET /api/v1/compare/{ticker}`
- `GET /api/v1/performance`

## Existing watchlist / KAP backend capabilities
The repository already contains a persistent BIST `WatchlistStore`, KAP polling through `KapWatchlistAlertService`, persistent pending/history state, and real disclosure models carrying ticker, publication time, title, summary, official URL, category, severity/score, corrective status and attachment status.

These internal capabilities do **not** automatically mean that Phase 13 currently exposes public HTTP endpoints for watchlist mutation or a KAP feed. Work/Sites must not invent a client-only Phase 13 endpoint. Any new browser route must terminate at a real trusted server/backend implementation.

## Mandatory browser security boundary
The backend uses a Bearer token. That token must never be embedded in browser JavaScript, a PWA bundle, service worker, static environment file, localStorage, IndexedDB or client-visible HTML.

Preferred deployment:

`Browser/PWA -> same-origin Work/Sites BFF or reverse proxy -> ARVEN Trade backend API`

The BFF/reverse proxy owns:
- upstream backend URL,
- authorization token,
- upstream timeout/error normalization,
- server-only secret storage.

If Work/Sites cannot provide a secret-bearing server boundary, do not move the token into the client. Keep live connectivity explicitly pending rather than weakening security.

## Recommended browser-facing BFF routes
For the existing Phase 13 endpoints:
- `GET /api/arven/health` -> `GET /api/v1/health`
- `POST /api/arven/analyses` -> `POST /api/v1/analyses`
- `GET /api/arven/analyses/{job_id}` -> `GET /api/v1/analyses/{job_id}`
- `GET /api/arven/history` -> `GET /api/v1/history`
- `GET /api/arven/history/{analysis_id}` -> `GET /api/v1/history/{analysis_id}`
- `GET /api/arven/compare/{ticker}` -> `GET /api/v1/compare/{ticker}`
- `GET /api/arven/performance` -> `GET /api/v1/performance`

The proxy must forward `Idempotency-Key` for analysis submissions.

A future/Phase14 browser route such as `GET /api/arven/kap/disclosures` is allowed only after a real server/backend KAP feed is implemented. It is a product target, not permission to fabricate an upstream endpoint.

## Screen-to-API / data mapping
### PC Ana Pano
Use real backend data for service readiness, recent analyses and performance. The active/latest analyzed stock is first and most prominent. Functional watchlist add/remove is required. No demo fallback.

### PC Hisse Analizi
Flow:
1. User enters/selects a BIST ticker.
2. Start analysis.
3. Show `queued` -> `running`.
4. Poll until `succeeded` or `failed`.
5. Show final decision/rating.
6. Show agent cards, including KAP.
7. KAP card contains a 3–5 sentence ARVEN interpretation plus real source disclosure metadata/links when available.

The UI must distinguish the official KAP disclosure from the AI interpretation.

### KAP Açıklamaları — dedicated menu
Add **“KAP Açıklamaları”** as a primary product navigation destination on desktop and an appropriate mobile navigation/menu surface.

The screen is a chronological real-disclosure feed, grouped by calendar day, newest first. Each row/card should show, when available:
- publication date/time,
- BIST ticker,
- company name,
- disclosure title/subject,
- concise source summary,
- category,
- importance/severity/score,
- corrective disclosure marker,
- attachment marker,
- official KAP link.

Filters:
- date,
- ticker/company,
- category,
- importance/severity,
- quick scope for “Takip Listem” and “Analiz Ettiklerim” when supported.

Current truthful production scope is real disclosures for followed/watchlist and analyzed BIST tickers where backend data exists. Do not describe that as an all-BIST feed. A true all-listed-company feed requires a real market-wide ingestion/data-distribution source before it can be presented as such.

Never display demo KAP records. If the feed source is unavailable, show an explicit empty/unavailable state.

### Agent cards
Approved card concepts:
- Market
- Sentiment
- News
- KAP
- Fundamentals
- Trader
- Bull
- Bear
- Risk

Each explanation/decision is 3–5 sentences. Bull/Bear and other debates are 3–5 sentences per side/contribution. Do not render raw model chain-of-thought or dump the full graph state on the dashboard.

### History / Compare / Performance
Use the real Phase 13 endpoints. Do not fill empty screens with sample values.

## Analysis submission contract
Example browser payload:

```json
{
  "ticker": "THYAO",
  "trade_date": "2026-08-26",
  "estimated_cost_usd": 0.25
}
```

Use a stable client-generated `Idempotency-Key` for retry-safe analysis submission. Reusing a key with a different payload is a conflict and should be shown as an actionable error.

## UI state rules
- `queued`: analysis accepted, waiting to run.
- `running`: agents are processing.
- `succeeded`: show decision/rating and refresh history-derived cards.
- `failed`: show a concise safe error.
- HTTP 429: queue/capacity full; allow manual retry.
- HTTP 503: affected history/KAP surface is temporarily unavailable without pretending data exists.
- Never expose secrets or stack traces.

## Work/Sites implementation constraints
- Responsive PC + mobile PWA from one product codebase.
- Preserve approved ARVEN typography, spacing, cards, navigation and deep-blue visual language.
- Existing Site URL remains unchanged.
- No foreign-market UI.
- No demo values after live integration.
- No API secrets in frontend code.
- No fake KAP feed or fake all-BIST coverage claim.
- KAP appears both in Hisse Analizi and as the dedicated “KAP Açıklamaları” menu.

## Acceptance checklist
Phase 14 is accepted only when:
1. The existing ARVEN Trade Site is updated from the canonical mockups; no replacement Site is created.
2. Repository/source reference points to `hhakanguner-droid/Arven-Trade` and `main`.
3. Browser bundle contains no ARVEN backend token.
4. Health works through the trusted server boundary.
5. A BIST analysis can be submitted and reaches queued/running/succeeded or failed correctly.
6. Duplicate browser retry with the same idempotency key does not create duplicate analysis work.
7. History, compare and performance use real Phase 13 endpoints.
8. Watchlist add/remove is functional and persistent using an explicitly reported architecture.
9. KAP appears in stock analysis and as “KAP Açıklamaları”.
10. KAP feed is grouped by day and uses real disclosure data for its stated scope, with no demo items or false all-BIST claim.
11. Agent explanations/debates follow the requested 3–5 sentence format.
12. 429/503/network errors have explicit UI states.
13. PC and mobile smoke tests pass.
14. Live publish records the GitHub main SHA used.

## Synchronization rule
ChatGPT Sites publishing and GitHub are separate release surfaces. Treat GitHub `main` as canonical and record the exact GitHub commit SHA used for each Work/Sites publish. Do not claim automatic synchronization unless it has been verified in the actual Work/Sites project.
