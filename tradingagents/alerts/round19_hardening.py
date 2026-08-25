"""Stable Round 19 compatibility entry point.

The original Round 19 implementation is preserved in
``round19_hardening_base``. This lightweight wrapper gives Round 19 a reload
identity and, when newer Phase 10 layers are already active, routes direct
installer calls through the stable Phase 10 orchestrator so an older round can
never become the outermost layer after a hot reload.
"""

from __future__ import annotations

from typing import Any

_HARDENING_VERSION = "phase10-round19"
INSTALL_GENERATION = object()


def _current_base_install():
    from . import round19_hardening_base

    return round19_hardening_base.install


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
        if getattr(function, "_phase10_round19_version", None) == _HARDENING_VERSION:
            function._phase10_round19_generation = INSTALL_GENERATION


def _newer_chain_active(service: Any) -> bool:
    chain = getattr(service, "_PHASE10_HARDENING_CHAIN_INSTALLED", None)
    if chain in {"phase10-round20", "phase10-round21"}:
        return True
    current = getattr(service, "_satin_alma_is_acquisition", None)
    return any(
        getattr(current, f"_phase10_round{round_no}_generation", None) is not None
        for round_no in (20, 21)
    )


def install(service: Any) -> None:
    """Install Round 19 without allowing it to displace newer hardening layers."""
    rebuilding = bool(
        getattr(service, "_PHASE10_HARDENING_REBUILD_IN_PROGRESS", False)
    )
    if not rebuilding and _newer_chain_active(service):
        from . import phase10_hardening

        phase10_hardening.install(service)
        return

    _current_base_install()(service)
    _retag(service)
    service._PHASE10_ROUND19_HARDENING_INSTALLED = _HARDENING_VERSION
