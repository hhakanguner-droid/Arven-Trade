"""Fail-fast credential validation for guarded production runtimes."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from tradingagents.llm_clients.api_key_env import PROVIDER_API_KEY_ENV, get_api_key_env

_KEY_OPTIONAL_PROVIDERS = {"ollama", "openai_compatible", "bedrock"}


class ProductionConfigurationError(RuntimeError):
    pass


def validate_provider_credentials(
    config: Mapping[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Validate the selected provider without ever returning the credential value."""
    provider = str(config.get("llm_provider") or "").strip().lower()
    if not provider:
        return {"provider": "", "credential_status": "not_applicable", "env_var": None}

    source = os.environ if environ is None else environ
    if provider not in PROVIDER_API_KEY_ENV:
        raise ProductionConfigurationError(
            f"Unknown LLM provider for production credential policy: {provider}"
        )

    env_var = get_api_key_env(provider)
    if provider == "bedrock":
        return {
            "provider": provider,
            "credential_status": "external_credential_chain",
            "env_var": None,
        }

    if provider in _KEY_OPTIONAL_PROVIDERS:
        configured = bool(env_var and str(source.get(env_var) or "").strip())
        return {
            "provider": provider,
            "credential_status": "configured" if configured else "optional",
            "env_var": env_var,
        }

    if not env_var:
        raise ProductionConfigurationError(
            f"No credential environment variable registered for provider: {provider}"
        )
    if not str(source.get(env_var) or "").strip():
        raise ProductionConfigurationError(
            f"Missing required production credential: set {env_var} for provider {provider}"
        )
    return {
        "provider": provider,
        "credential_status": "configured",
        "env_var": env_var,
    }
