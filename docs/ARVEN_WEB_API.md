# ARVEN Trade Web API — Phase 13

Phase 13 exposes the guarded Phase 12 production runtime to the ARVEN PC/PWA layer without keeping a browser request open for the full multi-agent analysis.

## Install and run

```bash
pip install ".[web]"
export TRADINGAGENTS_API_TOKEN="replace-with-a-long-random-secret-at-least-32-chars"
python -m tradingagents.service
```

Default bind is `127.0.0.1:8000`. Override with `TRADINGAGENTS_API_HOST` and `TRADINGAGENTS_API_PORT`.

Authentication is fail-closed: `/api/v1/*` requires `Authorization: Bearer <token>`. Production tokens must be at least 32 characters. Only `/healthz` is public and deliberately returns no runtime details. For local development only, authentication can be explicitly disabled with `TRADINGAGENTS_API_AUTH_DISABLED=true`.

**Production browser rule:** `TRADINGAGENTS_API_TOKEN` is a backend/operator secret. Never embed it in a PWA JavaScript bundle, service worker, public environment variable, or static site configuration. A browser-facing deployment should terminate TLS and user/session authentication at a same-origin server/BFF or trusted reverse proxy, then call this API from the protected server side. The built-in Bearer token is suitable for trusted server-to-server/operator access, not as a secret shipped to an untrusted browser. Keep the API on `127.0.0.1` behind that boundary whenever possible.

## Endpoints

- `GET /healthz` — minimal process liveness.
- `GET /api/v1/health` — authenticated operational readiness, history availability and queue counts.
- `POST /api/v1/analyses` — submit a BIST analysis and receive a persistent job immediately.
- `GET /api/v1/analyses/{job_id}` — poll queued/running/succeeded/failed state.
- `GET /api/v1/history?ticker=THYAO&limit=50` — compact PWA-ready Phase 11 analysis cards.
- `GET /api/v1/history/{analysis_id}` — detailed stored analysis and agent evidence.
- `GET /api/v1/compare/THYAO?count=2` — latest analyses for deterministic side-by-side comparison.
- `GET /api/v1/performance?ticker=THYAO` — realized raw/benchmark/alpha performance summary.
- `GET /api/v1/market` — FX, parity, BIST index and commodity snapshot for the Piyasalar view.
- `GET /api/v1/price-history/THYAO?range=1A` — chart-ready close-price series plus period/52-week stats for a chosen ticker.

Example request:

```json
{
  "ticker": "THYAO",
  "trade_date": "2026-08-26",
  "estimated_cost_usd": 0.25
}
```

Bare BIST tickers are normalized to `.IS`; foreign suffixes are rejected. Future trade dates and non-finite/negative cost estimates are rejected before a job is created. The same BIST normalization is applied to history, compare and performance queries.

For retry-safe clients or reverse proxies, send a stable `Idempotency-Key`. Reusing the key for the identical request returns the same job; reusing it for different input returns HTTP 409. Blank/whitespace-only keys are treated as absent.

## PWA history payloads

History list/compare endpoints intentionally do not dump the entire long-form graph state into dashboard requests. They return bounded deterministic cards with rating, signal, entry/benchmark metadata, performance points, a compact final-decision summary and short Market/Sentiment/News/KAP/Fundamentals/Trader/Bull/Bear/Risk snippets when those fields exist.

`GET /api/v1/history/{analysis_id}` is the explicit drill-down surface and includes the stored Phase 11 state plus the full final decision. If Phase 11 history is disabled or its store cannot be opened, analysis submission remains available while history endpoints return HTTP 503 and `/api/v1/health` reports `history.available=false`.

A completed analysis job preserves the Portfolio Manager's full `final_trade_decision` together with its deterministic five-tier rating. The API does not replace that decision with the short rating returned by the legacy graph tuple.

## Market data (Piyasalar)

`GET /api/v1/market` returns FX rates (USD/EUR/GBP/CHF against TRY), cross parities (EUR/USD, GBP/USD, USD/JPY), the BIST 100/30/Bankacılık/Sınai indices and commodities (ons/gram altın, gümüş, Brent petrol) as one snapshot:

```json
{
  "checked_at": "2026-09-03T09:14:00+00:00",
  "quotes": [
    {"symbol": "USDTRY", "label": "Amerikan Doları", "group": "fx", "price": 34.241, "change_pct": 0.38, "currency": "TRY"}
  ],
  "errors": []
}
```

Each instrument is fetched independently: a delisted or rate-limited symbol lands in `errors` (with the Yahoo ticker and message) rather than failing the whole snapshot, mirroring the watchlist alert service's per-source status pattern. Gram Altın has no direct Turkish-market feed on Yahoo Finance, so it is derived from the ons altın (USD) quote and USDTRY rather than invented.

`GET /api/v1/price-history/{ticker}?range=1A` returns a close-price series for a chart plus period and 52-week stats. `range` is one of `1G` (1 day, 5‑minute bars), `1H` (5 trading days, 15‑minute bars), `1A` (1 month, daily), `6A` (6 months, daily), `1Y` (1 year, daily) or `5Y` (5 years, weekly); the same BIST ticker normalization used elsewhere in this API applies. A ticker with no rows for the requested range returns HTTP 404.

## Queue bounds and persistence

Job metadata is stored in SQLite at `<production-state-dir>/web_jobs.db` by default, or `TRADINGAGENTS_API_JOB_DB`. Interrupted `running` jobs are requeued on service startup. SQLite claim semantics prevent the same queued job from being executed twice by one service instance.

The pending queue is bounded by `TRADINGAGENTS_API_MAX_PENDING_JOBS` (default `100`). The count includes both queued and running work; a new distinct request receives HTTP 429 when the queue is full. Idempotent replays of an existing request still return the existing job and do not consume extra capacity or enqueue duplicate executor work.

Terminal job rows are bounded by `TRADINGAGENTS_API_MAX_TERMINAL_JOBS` (default `5000`). Older succeeded/failed API job rows are pruned; the Phase 11 analysis-history database remains the durable analysis/performance record and is not affected by this API queue retention.

The API worker submits to `ProductionRuntime`, so Phase 12 rate limits, cost budget, credential validation, secret redaction, retention and shared-graph serialization remain in force. The caller-provided `estimated_cost_usd` cannot lower a configured Phase 12 per-run estimate because the guard uses the maximum of the configured and requested values.

## Browser origin policy

CORS is disabled unless `TRADINGAGENTS_API_CORS_ORIGINS` is explicitly set to a comma-separated allow-list. Same-origin deployment is preferred for the ARVEN PWA. CORS is not an authentication mechanism and does not make a browser-embedded Bearer token secret.

The built-in launcher intentionally uses one Uvicorn worker because the service owns a local SQLite queue and a stateful production runtime. Horizontal scaling should use a shared external queue/lease model rather than pointing multiple independent workers at the same local job database.
