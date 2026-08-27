# ARVEN Trade — Single Provider Stall Semantics Hotfix

## Incident evidence

Live browser test on 2026-08-27 for `AKBNK.IS` produced the following job facts:

- job id: `8a93ac7cd0544c88a34fd921c5efd889`
- status while observed: `running`
- current UI agent: `Piyasa Analisti`
- progress percent: `1`
- `started_at`: `2026-08-27T13:50:11.148Z`
- `progress_at`: `2026-08-27T13:50:11.148Z`
- `heartbeat_at`: `2026-08-27T13:50:26.113Z`
- `stale_after_at`: `2026-08-27T13:55:11.148Z`
- `deadline_at`: `2026-08-27T14:05:11.148Z`

This proves the execution can remain live (heartbeat advances) while no genuine intermediate agent boundary is produced. Under the Version 17 single-provider full-analysis architecture, the fixed 300-second progress-stall lease can therefore kill a healthy long-running provider execution.

## Root cause

Version 17 restored a single long provider/model call for the full analysis. `AnalysisStalled` still assumes that genuine intermediate agent progress must occur within 300 seconds.

Those two assumptions are incompatible.

A live provider execution must not be failed merely because `progress_at` did not change while the provider is still authoritatively `queued`/`in_progress`/running.

## Non-negotiable rule

Do not change Version 17 provider/model/parser/result semantics.

Do not split the single provider call into stage calls.

Do not merely increase 300 seconds to another arbitrary stall threshold.

Fix the decision rule.

## Required execution-mode semantics

For `single_provider_full_analysis` (or equivalent execution mode):

- `stale_after_at` must be `NULL`/disabled for failure decisions, OR the stall watchdog must explicitly skip `AnalysisStalled` for this mode while authoritative provider/durable execution is still live.
- `heartbeat_at` and reconciliation timestamps remain liveness/diagnostic signals only.
- `progress_at` is not required to advance during the long provider call.
- `AnalysisTimeout` hard deadline remains authoritative. Current production target remains 900 seconds unless a separate approved contract changes it.
- If the provider/durable execution reports a real terminal failure, fail the job with the provider-safe mapped error.
- If provider execution is genuinely missing/unrecoverable, use the appropriate interrupted/durable-execution failure semantics; do not mislabel it as `AnalysisStalled` merely because 300 seconds elapsed.

## UI truthfulness

Under the single-provider full-analysis mode, the UI must not claim that one of the nine ARVEN agents is independently running unless there is genuine server/provider evidence for that agent boundary.

While the single provider execution is running and there is no trustworthy intermediate boundary, show a neutral truthful state such as:

- `ARVEN analiz motoru çalışıyor`
- overall job `running`
- hard-timeout remaining/elapsed time if desired

The nine agent cards may remain `Bekliyor` until genuine evidence exists. Do not fabricate `%11 -> %22 -> ...` progress with timers.

After a successful accepted full-analysis result is available, map the validated result to the nine agent outputs and mark the genuinely completed analysis components as completed.

## Preserve existing protections

Keep:

- Version 17 single `gpt-5-mini` + `web_search` full-analysis behavior
- strict full-analysis schema
- 12000 output budget
- safe JSON-fence normalization
- durable/restart-resilience implementation from the restart hotfix
- late-write protection
- terminal no-requeue
- hard timeout (`AnalysisTimeout`)
- provider/durable cancellation on real terminal timeout where supported
- D1 progress/event tables
- fail-open telemetry

## AKBNK acceptance test

Use a fresh real browser-triggered AKBNK job after deployment.

Required:

1. `queued -> running`.
2. Single provider/durable execution id created exactly once.
3. If the provider remains `in_progress` beyond 300 seconds, job must remain `running`; it must NOT become `AnalysisStalled` solely because `progress_at` is old.
4. No duplicate provider execution after polling/restart/reconciliation.
5. If the provider completes before the hard deadline, final job must become `succeeded` and render the normal analysis result.
6. If the hard deadline is actually exceeded, `failed / AnalysisTimeout` is correct.

## Regression tests

Also verify:

- one normal ARTMS or THYAO full analysis succeeds
- deliberate runtime restart preserves the same durable execution id and continues the job
- late-write cannot overwrite a terminal record
- terminal job is not requeued
- no maintenance/debug endpoint remains
- history/watchlist/KAP records are unaffected

## Required final report

Return only:

- new Sites version/deploy SHA
- exact execution mode used for AKBNK
- whether `stale_after_at` was disabled/null or skipped by mode
- AKBNK provider/durable execution id
- AKBNK status at >300 seconds if the run lasts that long
- AKBNK final status
- normal ARTMS/THYAO final status
- deliberate restart result + same execution id proof
- hard-timeout test result
- late-write/no-requeue result
- live URL
