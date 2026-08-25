"""Stable Round 18 compatibility entry point.

The original Round 18 implementation is preserved in
``round18_hardening_base``. Direct installer calls are routed through the
latest stable Phase 10 chain whenever a newer layer is already active, so a
hot reload cannot place Round 18 above Round 19/20.
"""

from __future__ import annotations

from typing import Any

from .round18_hardening_base import install as _install_base

_HARDENING_VERSION = "phase10-round18"
INSTALL_GENERATION = object()


def _retag(service: Any) -> None:
    functions = (
        getattr(service, "_satin_alma_is_acquisition", None),
        getattr(service, "_devralma_has_acquisition_context", None),
        getattr(service, "_tesis_is_operational", None),
        getattr(service.KapWatchlistAlertService, "check_watchlist", None),
    )
    for function in functions:
        if function is None:
            continue
        if getattr(function, "_phase10_round18_version", None) == _HARDENING_VERSION:
            function._phase10_round18_generation = INSTALL_GENERATION


def _newer_chain_active(service: Any) -> bool:
    chain = getattr(service, "_PHASE10_HARDENING_CHAIN_INSTALLED", None)
    if chain in {"phase10-round19", "phase10-round20"}:
        return True
    current = getattr(service, "_satin_alma_is_acquisition", None)
    return (
        getattr(current, "_phase10_round19_generation", None) is not None
        or getattr(current, "_phase10_round20_generation", None) is not None
    )


def install(service: Any) -> None:
    """Install Round 18 without allowing it to displace newer hardening layers."""
    rebuilding = bool(
        getattr(service, "_PHASE10_HARDENING_REBUILD_IN_PROGRESS", False)
    )
    if not rebuilding and _newer_chain_active(service):
        from . import phase10_hardening

        phase10_hardening.install(service)
        return

    _install_base(service)
    _retag(service)
    service._PHASE10_ROUND18_HARDENING_INSTALLED = _HARDENING_VERSION
