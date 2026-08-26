# ChatGPT Work / Sites Prompt — ARVEN Trade Phase 14

Create/update the ARVEN Trade live PC + mobile PWA using the canonical GitHub repository and the approved ARVEN Trade visual mockups.

## Canonical sources
GitHub repository: `hhakanguner-droid/Arven-Trade`

Production source branch: `main`

Backend/API contract: `docs/ARVEN_WEB_API.md`

Work/Sites handoff contract: `docs/ARVEN_WORK_SITES_HANDOFF.md`

Machine-readable site contract: `work-sites/site-contract.json`

Use these visual files as the design source of truth:
- `ARVEN_TRADE_PC_Mobil_PWA_Mockuplari.pdf`
- `ARVEN_TRADE_PC_Ana_Pano.png`
- `ARVEN_TRADE_PC_Hisse_Analizi.png`
- `ARVEN_TRADE_Mobil_PWA_Mockuplari.png`
- `ARVEN_TRADE_Splash_Mockup.png`
- `ARVEN_TRADE_Logo.png`

Do not replace the approved ARVEN design with a generic trading template. Preserve the dark/deep-blue corporate visual language, card hierarchy, navigation and approved responsive PC/mobile compositions.

## Product behavior
ARVEN Trade is BIST/Türkiye focused. Do not add foreign exchanges or foreign-stock workflows.

The main product should expose concise AI-agent conclusions, not long raw model transcripts. Use short cards for Market, Sentiment, News, KAP, Fundamentals, Trader, Bull, Bear and Risk. Full evidence belongs in explicit detail drill-down.

On first load use the approved ARVEN splash design and approved transition behavior from the supplied mockup/brief.

## Live integration architecture
Do not put `TRADINGAGENTS_API_TOKEN` or any backend secret into browser code, public environment variables, localStorage, IndexedDB, the PWA service worker or static HTML.

Use a same-origin server-side BFF/reverse proxy:

`Browser -> Work/Sites same-origin server boundary -> ARVEN Trade Phase 13 API`

The server-side boundary stores:
- the ARVEN backend base URL,
- the Phase 13 Bearer token,
- upstream timeout/error handling.

Browser-facing routes should follow the Phase 14 contract under `/api/arven/*` and proxy to the authenticated `/api/v1/*` backend endpoints.

If this Sites environment cannot provide a server-side secret-bearing BFF/reverse proxy, do not weaken security by moving the token into the client. Build the complete UI against the Phase 14 contract, mark live backend connectivity as pending, and report that server-side proxy capability is the blocking requirement.

## Required flows
1. Ana Pano
   - Service readiness.
   - Recent analyses.
   - Performance summary.
   - No fake/demo financial values when live backend is unavailable.

2. Hisse Analizi
   - Accept BIST ticker.
   - Submit analysis with `POST /api/arven/analyses`.
   - Generate and preserve a stable `Idempotency-Key` for retry of the same user action.
   - Show `queued`, then `running`, then `succeeded` or `failed`.
   - Poll `/api/arven/analyses/{job_id}`.
   - On success show short decision/rating immediately and refresh matching history/agent cards.

3. Geçmiş
   - Use `/api/arven/history`.
   - Use `/api/arven/history/{analysis_id}` for drill-down.

4. Karşılaştırma
   - Use `/api/arven/compare/{ticker}`.

5. Performans
   - Use `/api/arven/performance` and optional ticker filter.

## Error UX
Provide explicit, calm Turkish UI states for:
- 401/403 authentication boundary issue,
- 404 record missing,
- 409 idempotency conflict,
- 429 queue/capacity full,
- 503 history temporarily unavailable,
- network timeout,
- backend 5xx.

Never show backend stack traces or secrets.

## PWA/desktop requirements
- Responsive single product for desktop and mobile.
- Installable PWA behavior where supported.
- Preserve the approved PC main dashboard and stock analysis hierarchy.
- Preserve the approved mobile navigation/composition.
- Loading and polling states must not freeze navigation.
- Back navigation must work on mobile/detail views.

## Release bookkeeping
For every publish, record the exact GitHub `main` SHA the Sites build was synchronized from. Do not claim that GitHub automatically updates the live site unless that behavior has been explicitly verified in this Work/Sites project.

## Completion report
When finished, report only:
1. GitHub repo/branch/SHA used.
2. Whether the Work/Sites project directly imported repo code or created a separate workspace copy.
3. Whether server-side BFF/reverse proxy secret storage is available and configured.
4. Which real Phase 13 endpoints are connected.
5. Which endpoints/screens remain mocked or blocked, if any.
6. Whether GitHub-to-live-site synchronization is automatic or manual.
7. The live site URL and the Git SHA currently represented by that live publish.
