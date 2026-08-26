# ARVEN Trade — Production Runtime

Phase 12 adds a guarded production entry point without changing the existing research/library API.
Production services should construct ARVEN through `create_production_runtime()` rather than calling
`TradingAgentsGraph.propagate()` directly.

```python
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.operations import create_production_runtime

config = DEFAULT_CONFIG.copy()
runtime = create_production_runtime(config=config)

print(runtime.health())
state, decision = runtime.propagate("THYAO.IS", "2026-08-26")
```

## Operational controls

All controls are opt-in. Non-positive values disable the corresponding limit so local development
keeps the existing behavior.

- `TRADINGAGENTS_MAX_RUNS_PER_MINUTE`: rolling 60-second analysis-start limit.
- `TRADINGAGENTS_DAILY_COST_LIMIT_USD`: fail-closed daily cost budget.
- `TRADINGAGENTS_ESTIMATED_RUN_COST_USD`: minimum amount reserved for every production run.
- `TRADINGAGENTS_RESULTS_RETENTION_DAYS`: delete result files older than this many days.
- `TRADINGAGENTS_RESULTS_MAX_FILES`: keep at most this many regular result files.

If a daily budget is enabled, a positive per-run estimate is required. A caller may provide a larger
`estimated_cost_usd` for a specific run, but cannot undercut the configured estimate floor.

## Security behavior

Hosted LLM providers are validated against the repository's canonical provider/API-key mapping before
LLM construction. Missing credentials fail fast. Local Ollama and key-optional OpenAI-compatible
endpoints remain supported; Bedrock uses its external AWS credential chain.

The production runtime installs process-wide log-record redaction before graph construction. Values
from environment variables whose names identify API keys, tokens, secrets, passwords, or private keys
are masked, together with common bearer/API-key token shapes. `runtime.health()` never returns secret
values.

## State safety

Rate and cost ledgers use inter-process lock files plus atomic `fsync` + `os.replace` writes. Existing
but corrupt operational state fails closed rather than silently resetting limits. If the cost gate
rejects a run after reserving a rate slot, that rate reservation is rolled back.

Operational state is stored below `<data_cache_dir>/operations` by default. Retention never follows
symlinks and never deletes files outside the configured results root.

## Resilience

Phase 12 complements the existing retry and checkpoint/resume controls rather than replacing them.
Use `TRADINGAGENTS_LLM_MAX_RETRIES` for provider retry budget and enable checkpointing when production
runs must resume from the last successful LangGraph node after interruption.

## Health / preflight

`runtime.health()` returns a secret-free readiness snapshot with credential status, rate-limit policy,
daily budget/spend, retention settings, and operational state directory. Production service startup
should expose or inspect this snapshot before accepting analysis jobs.
