# ARVEN Trade — Phase 14 Work / Sites Handoff

## Purpose
Phase 14 prepares the repository and product contract for the ARVEN Trade PC + mobile PWA to be built in ChatGPT Work / Sites and connected to the Phase 13 backend without exposing backend secrets in the browser.

## Canonical source
- Repository: `hhakanguner-droid/Arven-Trade`
- Production branch: `main`
- Phase 13 backend baseline commit: `44a72f6f64dcb249e7ff0c36ae5f51031e8dd881`
- The Work/Sites implementation must treat GitHub `main` as the source of truth for backend/API behavior.

## Canonical visual references
Use these project assets as the visual source of truth. Preserve the ARVEN corporate language, layout hierarchy and dark/deep-blue product identity.

- `ARVEN_TRADE_PC_Mobil_PWA_Mockuplari.pdf`
- `ARVEN_TRADE_PC_Ana_Pano.png`
- `ARVEN_TRADE_PC_Hisse_Analizi.png`
- `ARVEN_TRADE_Mobil_PWA_Mockuplari.png`
- `ARVEN_TRADE_Splash_Mockup.png`
- `ARVEN_TRADE_Logo.png`

The first-load splash should follow the approved ARVEN splash mockup and use the approved transition timing from the product brief. Do not replace the approved layout with a generic finance dashboard template.

## Product scope
ARVEN Trade is BIST/Türkiye focused. Foreign-market symbols are out of product scope for this UI. The interface should emphasize concise decisions and short agent summaries rather than dumping long LLM transcripts into the dashboard.

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

## Mandatory browser security boundary
The Phase 13 service uses a Bearer token. That token must never be embedded in browser JavaScript, a PWA bundle, service worker, static environment file, localStorage, IndexedDB or client-visible HTML.

Preferred deployment:

`Browser/PWA -> same-origin Work/Sites BFF or reverse proxy -> ARVEN Trade Phase 13 API`

The BFF/reverse proxy owns:
- upstream backend URL,
- `Authorization: Bearer <TRADINGAGENTS_API_TOKEN>`,
- upstream timeout/error normalization,
- server-only secret storage.

The browser should call only same-origin routes. If the selected Work/Sites hosting path cannot provide a server-side BFF/reverse proxy with secret storage, the live backend connection must not be faked by moving the token into the client. In that case build the UI against the contract and keep live integration explicitly pending until a server-side proxy is available.

## Recommended browser-facing BFF routes
These routes are a frontend convention and may be implemented by the Work/Sites server layer while mapping one-to-one onto Phase 13 upstream routes:

- `GET /api/arven/health` -> `GET /api/v1/health`
- `POST /api/arven/analyses` -> `POST /api/v1/analyses`
- `GET /api/arven/analyses/{job_id}` -> `GET /api/v1/analyses/{job_id}`
- `GET /api/arven/history` -> `GET /api/v1/history`
- `GET /api/arven/history/{analysis_id}` -> `GET /api/v1/history/{analysis_id}`
- `GET /api/arven/compare/{ticker}` -> `GET /api/v1/compare/{ticker}`
- `GET /api/arven/performance` -> `GET /api/v1/performance`

The proxy must forward `Idempotency-Key` for analysis submissions.

## Screen-to-API mapping
### PC Ana Pano
Use:
- `/api/arven/health` for service readiness,
- `/api/arven/history?limit=...` for recent analyses,
- `/api/arven/performance` for aggregate performance cards.

Do not display demo financial data when the backend is unavailable. Show an explicit unavailable/empty state.

### PC Hisse Analizi
Flow:
1. User enters/selects a BIST ticker.
2. `POST /api/arven/analyses` starts the analysis.
3. Show `queued` -> `running` state.
4. Poll `GET /api/arven/analyses/{job_id}` until `succeeded` or `failed`.
5. On success, show the short decision/rating immediately.
6. Use the latest matching history record for full agent cards and performance context when available.

The UI must have dedicated states for HTTP 401/403, 404, 409, 429, 503, network timeout and generic 5xx.

### Agent cards
Use Phase 13 compact history payloads. Approved short-card concepts include:
- Market
- Sentiment
- News
- KAP
- Fundamentals
- Trader
- Bull
- Bear
- Risk

Do not render raw full graph state on the main dashboard. Full stored state belongs only in explicit analysis-detail drill-down.

### History / Compare / Performance
Use:
- `/api/arven/history`
- `/api/arven/history/{analysis_id}`
- `/api/arven/compare/{ticker}`
- `/api/arven/performance?ticker=...`

## Analysis submission contract
Example browser payload:

```json
{
  "ticker": "THYAO",
  "trade_date": "2026-08-26",
  "estimated_cost_usd": 0.25
}
```

Use a stable client-generated `Idempotency-Key` for retry-safe analysis submission. Reusing a key with a different payload is a conflict and should be shown as an actionable error, not silently retried.

## UI state rules
- `queued`: analysis accepted, waiting to run.
- `running`: agents are processing.
- `succeeded`: show decision/rating and refresh history-derived cards.
- `failed`: show a concise safe error; never expose backend secrets or raw stack traces.
- HTTP 429: explain that the analysis queue/capacity is currently full and allow manual retry.
- HTTP 503 on history: analysis may still work; history should show a separate unavailable state.

## Work/Sites implementation constraints
- Responsive PC + mobile PWA from one product codebase.
- Preserve approved ARVEN typography, spacing, cards, navigation and deep-blue visual language from the canonical mockups.
- No foreign-market UI.
- No demo values after live integration is enabled.
- No API secrets in frontend code.
- No direct browser call to authenticated Phase 13 backend unless the request is terminated by a trusted same-origin server boundary that injects the secret server-side.
- Keep long-form agent evidence behind drill-down; dashboard copy stays short.

## Acceptance checklist
Phase 14 is accepted only when:
1. Work/Sites is built from the canonical mockups.
2. Repository/source reference points to `hhakanguner-droid/Arven-Trade` and `main`.
3. Browser bundle contains no ARVEN backend token.
4. Health works through the server-side boundary.
5. A BIST analysis can be submitted and reaches queued/running/succeeded or failed correctly.
6. Duplicate browser retry with the same idempotency key does not create duplicate analysis work.
7. History, compare and performance screens use Phase 13 endpoints.
8. 429/503/network errors have explicit UI states.
9. PC and mobile smoke tests pass.
10. Live site version records the GitHub main commit it was synchronized from so future drift is auditable.

## Synchronization rule
ChatGPT Sites publishing and GitHub are separate release surfaces. Treat GitHub `main` as the canonical code/backend source, and record the exact GitHub commit SHA used for each Work/Sites publish. Do not claim automatic synchronization unless the actual Work/Sites project has been verified to provide it.
