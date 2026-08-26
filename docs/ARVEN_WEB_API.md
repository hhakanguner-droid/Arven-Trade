# ARVEN Trade Web API — Phase 13

Phase 13 exposes the guarded Phase 12 production runtime to the ARVEN PC/PWA layer without keeping a browser request open for the full multi-agent analysis.

## Install and run

```bash
pip install ".[web]"
export TRADINGAGENTS_API_TOKEN="replace-with-a-long-random-secret"
python -m tradingagents.service
```

Default bind is `127.0.0.1:8000`. Override with `TRADINGAGENTS_API_HOST` and `TRADINGAGENTS_API_PORT`.

Authentication is fail-closed: `/api/v1/*` requires `Authorization: Bearer <token>`. Only `/healthz` is public and deliberately returns no runtime details. For local development only, authentication can be explicitly disabled with `TRADINGAGENTS_API_AUTH_DISABLED=true`.

## Endpoints

- `GET /healthz` — minimal process liveness.
- `GET /api/v1/health` — authenticated operational readiness and queue counts.
- `POST /api/v1/analyses` — submit a BIST analysis and receive a persistent job immediately.
- `GET /api/v1/analyses/{job_id}` — poll queued/running/succeeded/failed state.

Example request:

```json
{
  "ticker": "THYAO",
  "trade_date": "2026-08-26",
  "estimated_cost_usd": 0.25
}
```

Bare BIST tickers are normalized to `.IS`; foreign suffixes are rejected. Future trade dates and non-finite/negative cost estimates are rejected before a job is created.

For retries from browsers or reverse proxies, send a stable `Idempotency-Key`. Reusing the key for the identical request returns the same job; reusing it for different input returns HTTP 409.

## Persistence and restart behavior

Job metadata is stored in SQLite at `<production-state-dir>/web_jobs.db` by default, or `TRADINGAGENTS_API_JOB_DB`. Interrupted `running` jobs are requeued on service startup. SQLite claim semantics prevent the same queued job from being executed twice by one service instance.

The API worker submits to `ProductionRuntime`, so Phase 12 rate limits, cost budget, credential validation, secret redaction, retention and shared-graph serialization remain in force.

## Browser origin policy

CORS is disabled unless `TRADINGAGENTS_API_CORS_ORIGINS` is explicitly set to a comma-separated allow-list. Same-origin deployment is preferred for the ARVEN PWA.
