# ChatGPT Work / Sites Prompt — ARVEN Trade Phase 14

Update the **existing** ARVEN Trade live PC + mobile PWA. **Do not create a new Site.** The target live site is:

`https://arven-trade.hhakanguner.chatgpt.site/`

The goal of this phase is to move ARVEN Trade from demo/prototype behavior to a real end-user production experience, using the canonical GitHub repository, the Phase 13 API, and the approved ARVEN Trade visual mockups.

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

Do not replace the approved ARVEN design with a generic trading template. Preserve the dark/deep-blue corporate visual language, card hierarchy, navigation and approved responsive PC/mobile compositions. This is the first real end-user release; visual refinements can later evolve as v2/v3, but this phase must prioritize working production behavior over cosmetic experimentation.

## Product mode: production, not demo
ARVEN Trade is BIST/Türkiye focused. Do not add foreign exchanges or foreign-stock workflows.

Remove all demo/sample/placeholder portfolio, ticker, performance, analysis, agent-decision and dashboard values from the current live site. Do not leave any visible demo badges, mock balances, fake prices, fake performance numbers, example tickers presented as if they were live, or sample analysis history.

If the real backend has no data yet, show a clean Turkish empty state such as “Henüz analiz yok” / “Takip listesi boş” instead of fabricating values.

Do not silently fall back to fake data when the backend is unavailable. Show the proper unavailable/error state.

## Ana Pano priority
The **currently selected / most recently analyzed stock must be the most prominent item on the dashboard and must appear first at the top of the main content area**.

For the active/latest analysis, make the following immediately visible without scrolling:
- ticker / company identifier,
- analysis status,
- final ARVEN decision / signal,
- short decision summary,
- analysis date/time,
- access to the stock detail / analysis screen.

The user should never have to search the dashboard to understand **which stock was analyzed**. Secondary widgets such as recent analyses, performance and service status come after this active/latest analysis block.

## Takip Listesi must be functional
The current Site does not allow stocks to be added to the watchlist. Fix this.

Users must be able to:
- add a BIST stock to the watchlist,
- remove a stock from the watchlist,
- see a clear confirmation/state change immediately,
- open a watched stock and start/view its analysis,
- retain the watchlist across page navigation and normal PWA reloads according to the available persistent storage/backend architecture.

Do not ship a watchlist UI whose add button is decorative or non-functional. If the current Phase 13 backend does not yet expose a dedicated persistent watchlist endpoint, implement the safest available persistence layer inside the Work/Sites product boundary and explicitly report that persistence architecture in the completion report; do not fabricate a backend endpoint that does not exist.

## Agent output length and readability
The main product should expose concise AI-agent conclusions, not raw model transcripts.

For each relevant agent card — Market, Sentiment, News, KAP, Fundamentals, Trader and Risk — show the agent’s explanation/decision in **3 to 5 complete sentences**. The text must be concise, understandable Turkish, focused on the decision rationale and the most important evidence. Do not reduce meaningful agent reasoning to a one-line label, and do not dump long raw chain/model transcripts.

Bull/Bear and other agent debates must also be visible to the user in a compact form. **Each side / debate contribution should be summarized in 3 to 5 sentences** so the user can understand the disagreement, evidence and conclusion without reading a long transcript.

Preserve the distinction between:
- individual agent view,
- bull/bear debate,
- risk assessment,
- final portfolio/trader decision.

Full stored evidence may remain available only in an explicit detail drill-down where the backend contract provides it.

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
   - Latest/current analyzed stock is the first and most prominent block.
   - Service readiness.
   - Real recent analyses.
   - Real performance summary.
   - Functional watchlist with add/remove behavior.
   - No fake/demo financial values when real data is absent or backend is unavailable.

2. Hisse Analizi
   - Accept BIST ticker.
   - Submit analysis with `POST /api/arven/analyses`.
   - Generate and preserve a stable `Idempotency-Key` for retry of the same user action.
   - Show `queued`, then `running`, then `succeeded` or `failed`.
   - Poll `/api/arven/analyses/{job_id}`.
   - On success show final decision/rating immediately.
   - Show agent explanations in 3–5 sentences each.
   - Show bull/bear / relevant debate summaries in 3–5 sentences per side/contribution.
   - Refresh matching history/agent cards after completion.

3. Geçmiş
   - Use `/api/arven/history`.
   - Use `/api/arven/history/{analysis_id}` for drill-down.
   - Never populate the history screen with demo analyses.

4. Karşılaştırma
   - Use `/api/arven/compare/{ticker}`.
   - Show only real stored analyses.

5. Performans
   - Use `/api/arven/performance` and optional ticker filter.
   - If no real performance history exists yet, show a clean empty state rather than sample percentages/charts.

6. Takip Listesi
   - Add BIST ticker.
   - Remove BIST ticker.
   - Prevent duplicate entries.
   - Provide a clear empty state.
   - Allow direct transition from a watched ticker to analysis/detail.
   - Persist safely using the available product/server architecture; do not expose secrets and do not invent nonexistent Phase 13 endpoints.

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
- Existing live Site URL must remain the same after publish.

## Release bookkeeping
For every publish, record the exact GitHub `main` SHA the Sites build was synchronized from. Do not claim that GitHub automatically updates the live site unless that behavior has been explicitly verified in this Work/Sites project.

This release is the transition from demo/prototype to **real end-user use**. Do not call the live product “demo” after this publish. Future visual/feature revisions may be labeled v2/v3 if needed, but the current publish must be usable as the real ARVEN Trade product.

## Completion report
When finished, report only:
1. GitHub repo/branch/SHA used.
2. Confirmation that the existing Site `https://arven-trade.hhakanguner.chatgpt.site/` was updated and no replacement Site was created.
3. Whether the Work/Sites project directly imported repo code or created a separate workspace copy.
4. Whether server-side BFF/reverse proxy secret storage is available and configured.
5. Which real Phase 13 endpoints are connected.
6. How the watchlist add/remove persistence is implemented.
7. Confirmation that demo/sample values were removed, including any screen where removal could not be completed.
8. Confirmation that the active/latest analyzed stock is the first prominent dashboard block.
9. Confirmation that agent explanations and debate summaries are shown in the requested 3–5 sentence format.
10. Which endpoints/screens remain mocked or blocked, if any.
11. Whether GitHub-to-live-site synchronization is automatic or manual.
12. The live site URL and the Git SHA currently represented by that live publish.
