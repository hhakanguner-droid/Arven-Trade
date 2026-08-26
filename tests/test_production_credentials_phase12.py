import pytest

from tradingagents.operations import (
    OperationalGuard,
    OperationalPolicy,
    ProductionConfigurationError,
    ProductionRuntime,
    RetentionPolicy,
    validate_provider_credentials,
)


def test_hosted_provider_requires_registered_key():
    with pytest.raises(ProductionConfigurationError, match="OPENAI_API_KEY"):
        validate_provider_credentials({"llm_provider": "openai"}, environ={})


def test_credential_status_never_returns_secret_value():
    secret = "sk-do-not-return-this-value"
    status = validate_provider_credentials(
        {"llm_provider": "openai"},
        environ={"OPENAI_API_KEY": secret},
    )

    assert status == {
        "provider": "openai",
        "credential_status": "configured",
        "env_var": "OPENAI_API_KEY",
    }
    assert secret not in repr(status)


def test_local_and_external_chain_providers_do_not_require_single_key():
    ollama = validate_provider_credentials({"llm_provider": "ollama"}, environ={})
    bedrock = validate_provider_credentials({"llm_provider": "bedrock"}, environ={})

    assert ollama["credential_status"] == "optional"
    assert bedrock["credential_status"] == "external_credential_chain"


def test_unknown_provider_fails_closed():
    with pytest.raises(ProductionConfigurationError, match="Unknown LLM provider"):
        validate_provider_credentials({"llm_provider": "mystery-provider"}, environ={})


def test_runtime_health_is_secret_free(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-health-value")

    class Graph:
        config = {
            "llm_provider": "openai",
            "data_cache_dir": str(tmp_path),
            "results_dir": str(tmp_path / "results"),
        }

    guard = OperationalGuard(
        tmp_path / "ops",
        OperationalPolicy(max_runs_per_minute=5, daily_cost_limit_usd=2.0),
    )
    runtime = ProductionRuntime(
        Graph(),
        state_dir=tmp_path / "ops",
        guard=guard,
        retention=RetentionPolicy(results_retention_days=30, results_max_files=100),
    )

    health = runtime.health()

    assert health["credential"]["credential_status"] == "configured"
    assert health["rate_limit"]["enabled"] is True
    assert health["cost_budget"]["enabled"] is True
    assert health["retention"]["enabled"] is True
    assert "sk-secret-health-value" not in repr(health)
