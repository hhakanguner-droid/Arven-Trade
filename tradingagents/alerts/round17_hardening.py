"""Stable Round 17 compatibility entry point.

The original Round 17 implementation is preserved in
``round17_hardening_base``.  This lightweight wrapper gives Round 17 a reload
identity and, when newer Phase 10 layers are already active, routes direct
installer calls through the stable Phase 10 orchestrator so an older round can
never become the outermost layer after a hot reload.
"""

from __future__ import annotations

from typing import Any

from .round17_hardening_base import install as _install_base


_HARDENING_VERSION = "phase10-round17"
INSTALL_GENERATION = object()


def _retag(service: Any) -> None:
    functions = (
        getattr(service, "_satin_alma_is_acquisition", None),
        getattr(service, "_devralma_has_acquisition_context", None),
        getattr(service, "_tesis_is_operational", None),
        getattr(service, "_classify_event_fields", None),
        getattr(service.KapWatchlistAlertService, "check_watchlist", None),
    )
    for function in functions:
        if function is None:
            continue
        if getattr(function, "_phase10_round17_version", None) == _HARDENING_VERSION:
            function._phase10_round17_generation = INSTALL_GENERATION


def _newer_chain_active(service: Any) -> bool:
    chain = getattr(service, "_PHASE10_HARDENING_CHAIN_INSTALLED", None)
    if chain in {"phase10-round18", "phase10-round19"}:
        return True
    current = getattr(service, "_satin_alma_is_acquisition", None)
    return (
        getattr(current, "_phase10_round18_generation", None) is not None
        or getattr(current, "_phase10_round19_generation", None) is not None
    )


def install(service: Any) -> None:
    """Install Round 17 without allowing it to displace newer hardening layers."""
    rebuilding = bool(
        getattr(service, "_PHASE10_HARDENING_REBUILD_IN_PROGRESS", False)
    )
    if not rebuilding and _newer_chain_active(service):
        from . import phase10_hardening

        phase10_hardening.install(service)
        return

    _install_base(service)
    _retag(service)
    service._PHASE10_ROUND17_HARDENING_INSTALLED = _HARDENING_VERSION
