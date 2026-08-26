"""Guarded production runtime wrapper for ARVEN Trade graph execution."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .guard import CostBudgetExceeded, OperationalGuard, RateLimitExceeded
from .retention import prune_files
from .security import redact_sensitive_text

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetentionPolicy:
    results_retention_days: int = 0
    results_max_files: int = 0

    @classmethod
    def from_env(cls) -> "RetentionPolicy":
        return cls(
            results_retention_days=max(
                0, int(os.getenv("TRADINGAGENTS_RESULTS_RETENTION_DAYS", "0"))
            ),
            results_max_files=max(
                0, int(os.getenv("TRADINGAGENTS_RESULTS_MAX_FILES", "0"))
            ),
        )


class ProductionRuntime:
    """Apply production guardrails around an existing TradingAgentsGraph instance."""

    def __init__(
        self,
        graph: Any,
        *,
        state_dir: str | Path | None = None,
        guard: OperationalGuard | None = None,
        retention: RetentionPolicy | None = None,
    ):
        self.graph = graph
        config = getattr(graph, "config", {}) or {}
        default_state_dir = Path(config.get("data_cache_dir") or ".") / "operations"
        self.state_dir = Path(state_dir or default_state_dir).expanduser()
        self.guard = guard or OperationalGuard.from_env(self.state_dir)
        self.retention = retention or RetentionPolicy.from_env()

    def _apply_retention(self) -> list[Path]:
        config = getattr(self.graph, "config", {}) or {}
        results_dir = config.get("results_dir")
        if not results_dir:
            return []
        return prune_files(
            results_dir,
            retention_days=self.retention.results_retention_days,
            max_files=self.retention.results_max_files,
        )

    def propagate(
        self,
        company_name: str,
        trade_date: str,
        asset_type: str = "stock",
        *,
        estimated_cost_usd: float | None = None,
    ):
        """Run one guarded analysis; operational policy failures are fail-closed."""
        guard_state = self.guard.before_run(estimated_cost_usd=estimated_cost_usd)
        deleted = self._apply_retention()
        logger.info(
            "ARVEN production run start ticker=%s trade_date=%s estimated_cost_usd=%.4f "
            "daily_spend_usd=%.4f pruned_files=%d",
            company_name,
            trade_date,
            guard_state["estimated_cost_usd"],
            guard_state["daily_spend_usd"],
            len(deleted),
        )
        try:
            result = self.graph.propagate(company_name, trade_date, asset_type=asset_type)
        except (RateLimitExceeded, CostBudgetExceeded):
            raise
        except Exception as exc:
            logger.error(
                "ARVEN production run failed ticker=%s trade_date=%s error_type=%s message=%s",
                company_name,
                trade_date,
                type(exc).__name__,
                redact_sensitive_text(exc),
            )
            raise
        logger.info(
            "ARVEN production run success ticker=%s trade_date=%s",
            company_name,
            trade_date,
        )
        return result


def create_production_runtime(*args, state_dir: str | Path | None = None, **kwargs) -> ProductionRuntime:
    """Create the canonical guarded runtime while keeping core graph compatibility."""
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = TradingAgentsGraph(*args, **kwargs)
    return ProductionRuntime(graph, state_dir=state_dir)
