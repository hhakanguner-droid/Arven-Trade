# ARVEN Trade — Sites Version 17 Restart-Resilience Hotfix

## Incident

Live Sites Version 17 (`7b46b5407c9777c35bd255e7e08b0fa0a06baec4`) restored the working analysis/provider semantics and passed ARTMS + THYAO production smoke, but a real browser-triggered METEN analysis failed immediately after starting because the Sites server restarted.

Observed live UI on 2026-08-27:

- ticker: `METEN`
- job reached `running`
- progress displayed `%1`
- no genuine next stage was reached
- final status: `failed`
- user-safe error message: `Analiz sunucu yeniden başlatıldığı için kesildi.`

This is not the prior `ProviderOutputInvalid` regression. It is a runtime-lifecycle / durability defect: a `202 Accepted` analysis must not depend on the lifetime of one in-memory Sites server process.

## Non-negotiable release rule

Do not publish another version until a real browser-started analysis survives a deliberate Sites server/runtime restart and still reaches a correct terminal result (preferably `succeeded`) without creating a duplicate provider execution.

## Preserve Version 17 analysis semantics exactly

Version 17 is now the behavioral baseline for the analysis engine. Do **not** reintroduce the Version 10 stage-provider regression.

Preserve exactly:

- single provider/model analysis semantics restored from Version 9
- model: the same `gpt-5-mini` path used by Version 17
- `web_search` behavior
- strict full-analysis schema
- output budget `12000`
- safe JSON-fence normalization
- Version 17 output acceptance/parsing/normalization
- Version 17 final analysis assembly
- existing KAP/history/watchlist behavior

Do not split the provider analysis back into nine independent stage prompts merely to gain durability.

## Preserve Version 17 safety/progress features

Keep:

- D1 progress columns
- `analysis_progress_events`
- nine ARVEN agent progress UI
- heartbeat vs progress separation
- `AnalysisStalled`
- `AnalysisTimeout`
- late-write protection
- terminal-job no-requeue
- polling stop on terminal state
- fail-open progress telemetry

## Root architectural correction

A request returning `202 Accepted` must persist enough durable execution identity/state before returning so execution can continue or be reconciled after the current Sites process disappears.

**Forbidden architecture:**

`POST /api/arven/analyses -> create D1 row -> spawn Promise/setTimeout/in-memory background task -> return 202`

Any equivalent process-local fire-and-forget execution is invalid for production.

### Preferred implementation order

1. If Sites provides a native durable queue/workflow/job primitive, use it. Persist the durable execution/job id in D1 before returning `202`.
2. If the provider call itself is OpenAI Responses API and Sites has no durable worker primitive, use OpenAI Responses background execution (`background: true`) for the long provider operation. Persist the returned provider response id in D1 before returning `202`; later requests/reconciliation retrieve the same response by id rather than creating a new one. OpenAI Responses background mode is specifically designed for polling long-running responses and is independent of the original Sites request process.
3. Do not use an in-memory executor as the source of truth.

The implementation may use another genuinely durable platform primitive if available, but Work must state exactly what primitive owns execution after `202` is returned.

## D1 durable execution fields

Additive migration only. Preserve all existing records.

Add fields as appropriate:

- `execution_mode` (`sites_durable` / `provider_background` or equivalent)
- `execution_id` / `provider_response_id`
- `execution_generation` or unpredictable lease token
- `execution_created_at`
- `last_reconciled_at`
- `restart_count` (diagnostic only; not a decision source)

Provider/durable execution identifiers must remain server-side and must not expose secrets.

## Start transaction semantics

When a new analysis is accepted:

1. validate ticker/request/idempotency
2. create/claim exact D1 job
3. start durable execution exactly once
4. persist durable execution id + lease/generation atomically enough that retries cannot create a second provider execution
5. only then return `202`

If step 3 succeeds but persisting the execution id fails, reconcile using the same idempotency key/provider metadata rather than blindly starting another paid execution.

## Reconciliation after server restart

On any later `GET /api/arven/analyses/{job_id}` (and optionally a native scheduled reconciler):

- read D1 job
- if terminal, return terminal state and never restart anything
- if `running` and a durable execution id exists, query/resume/reconcile **that same execution**
- if provider says queued/in_progress, keep job running and update heartbeat/reconciliation timestamps
- if provider says completed, parse using Version 17 parser and atomically write success if the same lease/generation still owns the job
- if provider says failed/cancelled/incomplete, map to a safe terminal error
- if no durable execution id exists for a legacy interrupted job, use `AnalysisInterrupted`; do not create a duplicate execution unless an explicit safe-resume rule proves no provider work exists

A Sites process restart by itself must never convert a valid durable in-progress job to `failed`.

## Timeout/stall rules under durable execution

Keep `AnalysisStalled` and `AnalysisTimeout`, but timeout enforcement must cancel the durable/provider execution where supported.

- heartbeat/reconciliation is liveness only
- it must not fabricate agent progress
- `progress_at` changes only on genuine progress evidence
- hard deadline remains authoritative
- late completion after timeout must not overwrite terminal `failed`

If using OpenAI Responses background mode, cancel the response on hard timeout/stall when supported, then preserve the terminal D1 lease guard.

## Truthful nine-agent progress

Do not fabricate a nine-agent sequence to make the UI look busy.

Keep the Version 17 progress event mechanism only if the events are based on genuine server/provider execution evidence and survive restart because they are persisted in D1.

If the single provider execution cannot expose a trustworthy intermediate agent boundary during a restart window, the UI may temporarily show the last known genuine stage plus `Analiz motoru çalışıyor` rather than inventing additional completed agents. Truth is more important than smooth animation.

After execution completes, all genuinely completed agent outputs may transition to completed based on the accepted Version 17 full-analysis result.

## Deployment/restart drain

In addition to durable execution, deployment must not unnecessarily corrupt active jobs:

- before/while deploying, do not mark every `running` record failed
- process shutdown may stop local pollers, but durable execution continues externally
- new runtime reconciles existing durable `running` jobs from D1
- terminal jobs remain terminal

## Required restart regression test

A local/synthetic test is insufficient. Run this against the real live Site runtime.

1. Start a real analysis from the public browser path using a fresh BIST ticker.
2. Confirm `queued -> running` and persist the durable execution id.
3. While provider execution is actually in progress, deliberately trigger a Sites server/runtime restart/redeploy/recycle that would have killed the METEN job.
4. After restart, poll the same `job_id`.
5. Confirm it still references the same execution id/generation.
6. Confirm no second provider execution was created.
7. Confirm the job proceeds to terminal status; target is `succeeded`.
8. Confirm final analysis result is displayed normally.

Also run one normal no-restart analysis.

## Existing regression suite must stay green

Re-run:

- ARTMS or THYAO successful full analysis
- `AnalysisStalled`
- `AnalysisTimeout`
- timeout late-write guard
- terminal no-requeue
- no maintenance/debug endpoint
- history/watchlist/KAP unaffected

## User-facing error behavior

`Analiz sunucu yeniden başlatıldığı için kesildi.` may remain only for **legacy/non-durable jobs that truly cannot be reconciled**.

For new jobs after this hotfix, a normal Sites process restart should be invisible to the user except perhaps a brief `Bağlantı yeniden kuruluyor`/poll retry state. It must not terminate the analysis.

## Existing live site only

Update only:

`https://arven-trade.hhakanguner.chatgpt.site/`

Do not create a replacement site.

## Required final report

Return only:

- new Sites version + deploy SHA
- exact cause of the METEN server restart (deployment recycle, runtime eviction, crash, etc.)
- execution primitive chosen (`Sites durable ...` or provider background mode)
- D1 durable execution fields added
- deliberate restart test ticker/job id
- before/after restart same execution id proof
- duplicate provider execution count (must be 0 additional)
- restart test final status
- normal analysis final status
- stall timeout result
- hard timeout result
- late-write/no-requeue result
- live URL
