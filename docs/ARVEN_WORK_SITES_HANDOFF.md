# ARVEN Trade — Phase 14 Work / Sites Handoff

## Purpose
Phase 14 updates the **existing** ARVEN Trade PC + mobile PWA Site and moves it from demo/prototype behavior to real end-user use.

Existing production Site:
`https://arven-trade.hhakanguner.chatgpt.site/`

Do not create a replacement Site.

## Canonical source
- Repository: `hhakanguner-droid/Arven-Trade`
- Production branch: `main`
- Phase 13 backend behavior baseline: `44a72f6f64dcb249e7ff0c36ae5f51031e8dd881`
- Phase 13 reference contract: `docs/ARVEN_WEB_API.md`
- Phase 14 machine contract: `work-sites/site-contract.json`
- Phase 14 Work instructions: `work-sites/WORK_PROMPT.md`

GitHub `main` is the canonical source for backend/business behavior. The Phase 14 branch defines how that behavior is adapted into the Sites product.

## Hosting decision
ChatGPT Sites is the default hosting/runtime surface for this release. A separately deployed Phase 13 HTTPS service is **not a prerequisite** for the existing Site to run.

Default architecture:

`Browser/PWA -> same-origin Sites server routes -> Sites-hosted application logic -> Sites durable storage / external providers as needed`

The Python Phase 13 API is a **behavioral reference contract**. Its HTTP endpoints do not have to be hosted elsewhere merely so Sites can proxy to them.

Work/Sites should implement `/api/arven/*` as real same-origin server routes. If the original Python runtime is incompatible with the Sites runtime, adapt/port the necessary behavior to a Sites-compatible server implementation, preferably TypeScript/JavaScript, while preserving validation, idempotency, job states, errors, history, comparison, performance, BIST scope, KAP semantics and decision logic.

Do not simulate unsupported behavior. If a specific runtime capability truly cannot be implemented in Sites, report the exact blocker after attempting a Sites-native solution.

## Storage
Use Sites-hosted durable storage for product state:
- D1: watchlist, job/status records, idempotency, analysis history/results, performance metadata, KAP feed metadata.
- R2: only for files/objects when genuinely needed.

The Site should remember user-visible product records across visits. Temporary presentation state does not need durable storage.

## Secrets
Do not embed any provider credential or backend token in browser JavaScript, static HTML, service worker, localStorage, IndexedDB or public configuration.

For Site-local `/api/arven/*` calls, do **not** require `TRADINGAGENTS_API_TOKEN`; the browser is calling same-origin Sites server code, not an external Phase 13 service.

Use Sites hosted environment values/secrets only for genuine server-side provider credentials that the implementation actually needs. Inspect existing Site configuration first. Ask the user only for a genuinely missing provider credential.

## Canonical visuals
Preserve these visual references:
- `ARVEN_TRADE_PC_Mobil_PWA_Mockuplari.pdf`
- `ARVEN_TRADE_PC_Ana_Pano.png`
- `ARVEN_TRADE_PC_Hisse_Analizi.png`
- `ARVEN_TRADE_Mobil_PWA_Mockuplari.png`
- `ARVEN_TRADE_Splash_Mockup.png`
- `ARVEN_TRADE_Logo.png`

Preserve the dark/deep-blue ARVEN identity, card hierarchy, navigation and responsive PC/mobile composition.

## Production product rules
ARVEN Trade is BIST/Türkiye focused. Remove demo/sample/fake portfolio, ticker, performance, analysis, agent-decision, dashboard and KAP values. When no real data exists, show explicit Turkish empty states rather than fabricated values.

The latest/current analyzed stock must be the first and most prominent Ana Pano block.

Watchlist add/remove must be real and durable.

Analysis must expose truthful `queued -> running -> succeeded | failed` states and stable retry idempotency.

History, compare and performance must use real persisted records only.

## Locked agent UI identity
The visible identities are fixed:
- Piyasa Analisti — rising chart.
- Duyarlılık Analisti — sentiment/smiley.
- Haber Analisti — newspaper.
- Temel Analist — pie chart.
- KAP Araştırmacısı — document + megaphone.
- Boğa Görüş Araştırmacısı — bull head, green.
- Ayı Görüş Araştırmacısı — bear head, red.
- Risk Yöneticisi — shield/check.
- İşlem (Trader) Ajanı — target + arrow.

Do not use blue initial-letter avatars or visible English agent titles. Each agent explanation is 3–5 complete Turkish sentences. Bull/Bear and other debates are 3–5 sentences per side/contribution. Do not expose raw chain-of-thought.

## KAP
KAP appears in two surfaces:

### Hisse Analizi
Show KAP Araştırmacısı interpretation in 3–5 Turkish sentences and real disclosure source metadata/official links when available. Separate the official disclosure from ARVEN interpretation.

### KAP Açıklamaları
Dedicated primary menu. Real chronological feed grouped by day, newest first. Show real publication time, ticker/company, title/subject, concise source summary, category/importance where available, corrective/attachment flags and official KAP link.

Filters: date, ticker/company, category, importance/severity. Support `Takip Listem` and `Analiz Ettiklerim` scopes when possible.

Current truthful scope is real followed/watchlist and analyzed BIST tickers where data exists. Do not claim all-BIST coverage without a real market-wide feed. Never use demo disclosures.

## Sites server route behavior
Browser routes are Sites server routes whose semantics mirror the Phase 13 reference contract:
- `GET /api/arven/health`
- `POST /api/arven/analyses`
- `GET /api/arven/analyses/{job_id}`
- `GET /api/arven/history`
- `GET /api/arven/history/{analysis_id}`
- `GET /api/arven/compare/{ticker}`
- `GET /api/arven/performance`
- real watchlist server operations
- `GET /api/arven/kap/disclosures` backed by real server-side KAP implementation

These routes do not need an external Phase 13 URL in the default Sites-hosted architecture.

## Acceptance checklist
Phase 14 is accepted only when:
1. Existing ARVEN Trade Site is updated; no replacement Site is created.
2. Sites is the full-stack hosting surface unless a specific proven runtime blocker requires another supported architecture.
3. No external Phase 13 URL or `TRADINGAGENTS_API_TOKEN` is required solely for Site-local calls.
4. Browser bundle contains no secrets.
5. D1 provides durable state for product data that must survive visits.
6. A real BIST analysis reaches truthful queued/running/succeeded or failed states.
7. Same-action retries do not duplicate analysis work.
8. Watchlist add/remove is functional and persistent.
9. History, compare and performance use real records.
10. KAP exists in analysis and as `KAP Açıklamaları`, with no fake data or false all-BIST claim.
11. Nine locked Turkish agent identities/icons are exact and explanations/debates follow the 3–5 sentence rule.
12. 429/503/provider/network errors have safe UI states.
13. PC/mobile smoke tests pass.
14. A saved Sites version records the source Git SHA before deployment.
15. The approved version is deployed to the same existing production URL.

## Synchronization
GitHub and Sites are separate release surfaces. Record the exact Git SHA/source state used by each saved/deployed Site version. Do not assume automatic Git-to-live synchronization unless explicitly verified.
