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

Remove all demo/sample/placeholder portfolio, ticker, performance, analysis, agent-decision and dashboard values from the current live site. Do not leave any visible demo badges, mock balances, fake prices, fake performance numbers, example tickers presented as if they were live, sample analysis history, or fake KAP disclosures.

If the real backend has no data yet, show a clean Turkish empty state such as “Henüz analiz yok”, “Takip listesi boş” or “Henüz KAP açıklaması yok” instead of fabricating values.

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

## KAP must exist in two product surfaces
KAP is not only an analysis card. Add a dedicated primary navigation item named **“KAP Açıklamaları”** while also keeping KAP inside each stock analysis.

### A. KAP inside Hisse Analizi
For the stock being analyzed:
- keep a dedicated KAP agent/card,
- show the KAP agent interpretation in **3 to 5 complete Turkish sentences**,
- show the latest real KAP disclosures used/relevant to that analysis when available,
- make the source disclosure title/subject, publication date/time and official KAP link accessible,
- clearly distinguish the source disclosure from ARVEN’s interpretation of it.

Do not invent a KAP event or claim that a disclosure affected the analysis unless it exists in the real KAP data returned by the backend/history.

### B. Dedicated “KAP Açıklamaları” menu
Create a standalone chronological KAP feed. It should let the user answer: **“Bugün / bu günlerde hangi takip edilen veya analiz edilen şirket hangi KAP açıklamasını yaptı?”**

The feed must:
- group disclosures **day by day**, newest day first and newest disclosure first inside each day,
- show publication date/time,
- show ticker and company name when available,
- show disclosure title/subject,
- show concise source summary,
- show category and importance/severity when the backend provides them,
- show corrective-disclosure and attachment indicators when available,
- provide a link/action to open the official KAP source,
- support filters for date, ticker/company, category and importance/severity,
- include quick views for “Takip Listem” and “Analiz Ettiklerim” when those scopes are available,
- have a clean empty/unavailable state and **never populate itself with demo KAP items**.

The repository already contains real KAP/watchlist alert primitives and persisted alert history. Use real backend data for the feed when exposed. The current production-safe scope is disclosures for **watchlist/followed and analyzed BIST tickers**. Do not label that as an all-BIST market-wide stream if the backend does not actually provide all listed-company disclosures.

A browser-facing route such as `GET /api/arven/kap/disclosures` may be used **only when a real server/backend route is implemented behind it**. Do not invent a Phase 13 upstream endpoint in client code. If an all-BIST firehose is later required, treat it as a separate backend/data-distribution capability and report it as pending until a real market-wide source exists.

## Locked AI agent names and icons
The following **nine agent names and icons are approved and locked for this release**. Do not rename, translate differently, replace with English visible titles, reorder casually, or substitute the icons with initials such as M / S / N / F / B / R / T.

Use these exact visible names and pictograms:
1. **Piyasa Analisti** — rising market/chart icon.
2. **Duyarlılık Analisti** — smiley/sentiment face icon.
3. **Haber Analisti** — newspaper/news icon.
4. **Temel Analist** — pie-chart/financial fundamentals icon.
5. **KAP Araştırmacısı** — KAP document + megaphone/announcement icon.
6. **Boğa Görüş Araştırmacısı** — bull-head icon, green emphasis.
7. **Ayı Görüş Araştırmacısı** — bear-head icon, red emphasis.
8. **Risk Yöneticisi** — shield/check icon.
9. **İşlem (Trader) Ajanı** — target + arrow icon.

Visual rules for these icons:
- Replace the current blue-circle initials with actual pictogram icons.
- Use the approved rounded light-blue icon container style from the accepted mockup.
- Keep a consistent vector/pictogram family and visual weight across all nine agents.
- Default icons use ARVEN blue; Boğa uses green emphasis; Ayı uses red emphasis; Risk remains blue; Trader may use blue/violet emphasis.
- Names must remain Turkish exactly as written above. `Trader` is kept only inside the approved visible label **“İşlem (Trader) Ajanı”**.
- These names/icons are a **canonical UI identity lock** for Phase 14. Future v2/v3 cosmetic work may refine rendering quality but must not change the identity without explicit approval.

## Agent output length and readability
The main product should expose concise AI-agent conclusions, not raw model transcripts.

For each relevant agent card — Piyasa Analisti, Duyarlılık Analisti, Haber Analisti, KAP Araştırmacısı, Temel Analist, Boğa Görüş Araştırmacısı, Ayı Görüş Araştırmacısı, Risk Yöneticisi and İşlem (Trader) Ajanı — show the agent’s explanation/decision in **3 to 5 complete sentences**. The text must be concise, understandable Turkish, focused on the decision rationale and the most important evidence. Do not reduce meaningful agent reasoning to a one-line label, and do not dump long raw chain/model transcripts.

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

`Browser -> Work/Sites same-origin server boundary -> ARVEN Trade backend API`

The server-side boundary stores:
- the ARVEN backend base URL,
- the backend Bearer token,
- upstream timeout/error handling.

Browser-facing routes should follow the Phase 14 contract under `/api/arven/*` and proxy only to real authenticated backend endpoints.

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
   - Show all nine locked agent identities with the approved Turkish names/icons where their result is available.
   - Show agent explanations in 3–5 sentences each.
   - Show KAP agent interpretation in 3–5 sentences plus the real disclosure sources used/relevant when available.
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
   - Persist safely using the available product/server architecture; do not expose secrets and do not invent nonexistent backend endpoints.

7. KAP Açıklamaları
   - Dedicated primary navigation item.
   - Day-by-day chronological real disclosure feed.
   - Scope at minimum to followed/watchlist and analyzed BIST tickers where real backend data exists.
   - Date/ticker/category/importance filters.
   - Official KAP source link and source metadata.
   - No fake all-market claim and no demo disclosures.

## Error UX
Provide explicit, calm Turkish UI states for:
- 401/403 authentication boundary issue,
- 404 record missing,
- 409 idempotency conflict,
- 429 queue/capacity full,
- 503 history/KAP source temporarily unavailable,
- network timeout,
- backend 5xx.

Never show backend stack traces or secrets.

## PWA/desktop requirements
- Responsive single product for desktop and mobile.
- Installable PWA behavior where supported.
- Preserve the approved PC main dashboard and stock analysis hierarchy.
- Preserve the approved mobile navigation/composition.
- Add “KAP Açıklamaları” to desktop navigation and an appropriate mobile navigation/menu surface without breaking the approved composition.
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
5. Which real backend endpoints are connected.
6. How the watchlist add/remove persistence is implemented.
7. Confirmation that demo/sample values were removed, including any screen where removal could not be completed.
8. Confirmation that the active/latest analyzed stock is the first prominent dashboard block.
9. Confirmation that all nine locked agent names/icons are implemented exactly and that agent explanations/debate summaries are shown in the requested 3–5 sentence format.
10. Confirmation that KAP appears both in stock analysis and as a separate “KAP Açıklamaları” menu, including the actual data scope feeding that menu.
11. Which endpoints/screens remain mocked or blocked, if any.
12. Whether GitHub-to-live-site synchronization is automatic or manual.
13. The live site URL and the Git SHA currently represented by that live publish.
