"""Round 21 compatibility shim for the consolidated Phase 10 chain.

Round 21's historical semantic wrappers are superseded by the single Round 23
semantic engine.  This module intentionally performs no semantic wrapping.
Direct calls after a hot reload are routed through the stable orchestrator so
an older installer can never displace the consolidated outer layer.
"""

from __future__ import annotations

from typing import Any

_HARDENING_VERSION = "phase10-round21"
INSTALL_GENERATION = object()


def _newer_chain_active(service: Any) -> bool:
    chain = str(getattr(service, "_PHASE10_HARDENING_CHAIN_INSTALLED", ""))
    return chain.startswith("phase10-round2") and chain != _HARDENING_VERSION


def install(service: Any) -> None:
    """Preserve the newest chain; otherwise mark Round 21 as installed."""
    if (
        _newer_chain_active(service)
        and not getattr(service, "_PHASE10_HARDENING_REBUILD_IN_PROGRESS", False)
    ):
        from . import phase10_hardening

        phase10_hardening.install(service)
        return

    service._PHASE10_ROUND21_HARDENING_INSTALLED = _HARDENING_VERSION
