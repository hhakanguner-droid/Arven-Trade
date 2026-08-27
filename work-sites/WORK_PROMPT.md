# ChatGPT Work / Sites Prompt — ARVEN Trade Phase 14

Update the **existing** ARVEN Trade Site. **Do not create a new Site.** Keep the same production URL:

`https://arven-trade.hhakanguner.chatgpt.site/`

This phase moves ARVEN Trade from demo/prototype behavior to a real BIST-focused end-user product.

## Canonical sources
- GitHub repository: `hhakanguner-droid/Arven-Trade`
- Production/backend behavior source: `main`
- Phase 13 behavior contract: `docs/ARVEN_WEB_API.md`
- Work/Sites handoff: `docs/ARVEN_WORK_SITES_HANDOFF.md`
- Machine-readable contract: `work-sites/site-contract.json`
- Phase 14 instructions: this file

Use these visual sources as canonical:
- `ARVEN_TRADE_PC_Mobil_PWA_Mockuplari.pdf`
- `ARVEN_TRADE_PC_Ana_Pano.png`
- `ARVEN_TRADE_PC_Hisse_Analizi.png`
- `ARVEN_TRADE_Mobil_PWA_Mockuplari.png`
- `ARVEN_TRADE_Splash_Mockup.png`
- `ARVEN_TRADE_Logo.png`

Preserve the approved ARVEN dark/deep-blue visual language, hierarchy and responsive PC/mobile composition. Future v2/v3 releases can refine cosmetics; this release prioritizes correct production behavior.

## Deployment architecture — Sites is the host
**Do not require or ask for a separately deployed Phase 13 HTTPS backend merely to run this Site. Do not ask for `TRADINGAGENTS_API_TOKEN` for Site-to-itself calls.**

The existing ChatGPT Site is the default full-stack hosting/runtime surface for Phase 14:

`Browser/PWA -> same-origin Sites server routes -> Sites-hosted application logic + durable storage`

Treat the Phase 13 Python FastAPI service as the **behavioral/reference contract** for validation, states, idempotency, errors, history, comparison, performance and safety semantics. It does not have to exist as a separately hosted HTTP service for the default Sites deployment.

Implement browser-facing `/api/arven/*` routes as real **server-side Sites routes**. Never fake network success or populate demo data.

If the Python runtime/modules cannot execute directly in the supported Sites runtime, adapt/port the required behavior to a Sites-compatible server implementation, preferably TypeScript/JavaScript. Preserve the Phase 13 semantics rather than copying only the UI. Reuse the repository’s prompts, business rules, rating logic, BIST validation, KAP semantics and agent identities as source material where compatible.

Use Sites-hosted durable storage:
- **D1** for watchlist, analysis jobs/status, idempotency records, analysis history/results, performance metadata and KAP feed metadata that must survive visits.
- **R2 only when actual object/file storage is required.**

Use **Sites hosted environment variables/secrets** only for genuine third-party/provider credentials required by the server-side implementation. Keep provider secrets out of prompts, Git, browser code, HTML, service workers, localStorage and IndexedDB. First inspect the existing Site’s configured hosted secrets. Ask the user only if a genuinely required provider credential is missing; do not invent a new internal API token requirement.

If a specific original Python/background-service behavior is unsupported by the Sites runtime, implement the closest truthful runtime-compatible server/job pattern. Do not simulate `queued/running/succeeded/failed` with timers or fake results. Report the exact unsupported capability only if it genuinely blocks that feature after attempting a Sites-native implementation.

## Product mode: production, not demo
ARVEN Trade is BIST/Türkiye focused. Do not add foreign exchanges.

Remove all demo/sample/placeholder portfolio, ticker, performance, analysis, agent-decision, dashboard and KAP values. If real data is absent, show clean Turkish states such as `Henüz analiz yok`, `Takip listesi boş` or `Henüz KAP açıklaması yok`. Never silently fall back to fake data.

## Ana Pano
The currently selected / most recently analyzed stock must be the first and most prominent content block. Without scrolling show ticker/company, analysis status, final ARVEN decision/signal, short decision summary, analysis date/time and access to detail.

Secondary widgets such as history, performance, service readiness and watchlist follow after it.

## Takip Listesi
Watchlist is a real product feature, not a decorative control. Users must be able to add/remove BIST tickers, prevent duplicates, see immediate state changes, open a watched ticker for analysis, and retain the list across normal navigation/reloads. Persist it in Sites-hosted D1 unless an already-configured durable Sites store is demonstrably better.

## Locked AI agent names and icons
These nine identities are approved and locked. Do not show English titles or blue initial-letter avatars.

1. **Piyasa Analisti** — rising chart icon.
2. **Duyarlılık Analisti** — smiley/sentiment icon.
3. **Haber Analisti** — newspaper icon.
4. **Temel Analist** — pie-chart/fundamentals icon.
5. **KAP Araştırmacısı** — KAP document + megaphone icon.
6. **Boğa Görüş Araştırmacısı** — bull-head icon, green emphasis.
7. **Ayı Görüş Araştırmacısı** — bear-head icon, red emphasis.
8. **Risk Yöneticisi** — shield/check icon.
9. **İşlem (Trader) Ajanı** — target + arrow icon.

Use the approved rounded light-blue icon container and a consistent vector family. Default tone is ARVEN blue; Boğa green; Ayı red; Risk blue; Trader blue/violet.

Each relevant agent explanation/decision must be **3–5 complete Turkish sentences**. Bull/Bear and other debate contributions must also be **3–5 sentences per side/contribution**. Show concise reasoning and evidence, not raw model transcripts or chain-of-thought.

## Analysis flow
Implement the same product behavior represented by Phase 13:
- accept and normalize a BIST ticker,
- reject foreign-market symbols and invalid/future dates,
- start analysis through `POST /api/arven/analyses`,
- use a stable `Idempotency-Key` for the same user action,
- expose truthful `queued -> running -> succeeded | failed` state transitions,
- poll `GET /api/arven/analyses/{job_id}` when appropriate,
- persist completed results/history in D1,
- show final rating/decision plus the nine agent surfaces where results exist,
- preserve bounded, safe error handling and no secret/stack-trace exposure.

The `/api/arven/*` paths are same-origin Sites server routes. Their semantics should mirror the Phase 13 `/api/v1/*` reference contract; they are **not required to proxy to an external Phase 13 server**.

Required product routes/surfaces:
- `/api/arven/health`
- `/api/arven/analyses`
- `/api/arven/analyses/{job_id}`
- `/api/arven/history`
- `/api/arven/history/{analysis_id}`
- `/api/arven/compare/{ticker}`
- `/api/arven/performance`
- real server-backed watchlist operations
- real server-backed `/api/arven/kap/disclosures` when the KAP menu is enabled

## KAP in two surfaces
KAP must appear both inside stock analysis and as a dedicated primary navigation item named **`KAP Açıklamaları`**.

### KAP inside Hisse Analizi
Show the KAP Araştırmacısı interpretation in 3–5 Turkish sentences and, when available, the real source disclosure metadata: title/subject, publication date/time and official KAP link. Clearly distinguish the official disclosure from ARVEN’s interpretation. Never claim a KAP event affected an analysis unless real source data supports it.

### KAP Açıklamaları menu
Create a chronological real-disclosure feed grouped day by day, newest day and newest disclosure first. Show when available: date/time, ticker, company, title/subject, concise source summary, category, importance/severity/score, corrective marker, attachment marker and official KAP link.

Filters: date, ticker/company, category and importance/severity. Include `Takip Listem` and `Analiz Ettiklerim` quick scopes where supported.

Use the repository’s existing KAP/watchlist concepts to implement the Sites server-side feed. Current truthful scope is followed/watchlist and analyzed BIST tickers where real data exists. Do not call it an all-BIST feed unless a real market-wide feed is actually implemented. Never show demo KAP records.

## History / compare / performance
Use real persisted D1 data and the Phase 13 behavior contract for these surfaces. Empty history/performance must remain empty; do not draw sample percentages or charts.

## Error UX
Provide clear Turkish UI states for 401/403 where relevant, 404, 409, 429, 503, network/provider timeout and safe generic 5xx. Never expose secrets or raw stack traces.

## PWA / desktop
- One responsive PC + mobile product.
- Preserve approved navigation/composition.
- Add `KAP Açıklamaları` to desktop and mobile navigation appropriately.
- Loading/analysis work must not freeze navigation.
- Back navigation must work on mobile/detail views.
- Existing production Site URL must remain unchanged.

## Release and publishing
This is an update to the existing Site. Do not create a replacement Site and do not redirect to a new production URL.

Use the existing Sites project and its hosting. Save a reviewable version first, record the exact Git SHA/source state represented by that version, run production build/smoke checks, then deploy the approved version to the **same existing Site URL**.

GitHub and Sites are separate release surfaces; do not claim automatic Git-to-live synchronization unless verified.

## Completion report
When finished report only:
1. GitHub repo/branch/SHA and Sites source SHA used.
2. Confirmation the existing Site was updated, with no replacement Site.
3. Confirmation that Sites itself hosts the full-stack application and whether any runtime adapter/port was needed.
4. D1/R2 bindings actually used.
5. Any genuinely required hosted provider secrets; confirm that no `TRADINGAGENTS_API_TOKEN` was required for same-Site calls.
6. Which `/api/arven/*` server routes are real and connected.
7. Watchlist persistence architecture.
8. Confirmation all demo/sample values are removed.
9. Confirmation latest analyzed stock is first/prominent.
10. Confirmation all nine locked names/icons and 3–5 sentence agent/debate format are implemented.
11. Confirmation KAP exists in analysis and the `KAP Açıklamaları` menu, with truthful data scope.
12. Any feature genuinely blocked by a Sites runtime limitation, with the exact limitation.
13. Production build/smoke-test result.
14. Live URL and saved/deployed version SHA.
