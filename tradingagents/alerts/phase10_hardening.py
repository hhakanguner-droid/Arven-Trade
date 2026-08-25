"""Stable Phase 10 hardening orchestration entry point.

The implementation accumulated through Codex Round 14 lives in
``phase10_hardening_base``.  This module remains the single stable entry point:
every explicit ``install`` reconstructs the deterministic
base -> Round 15 -> Round 16 -> Round 17 -> Round 18 chain whenever any loaded
installer module or installed closure has changed.
"""

from __future__ import annotations

from typing import Any

from .phase10_hardening_base import install as _install_base

_ROUND18_VERSION = "phase10-round18"
_FOLLOWUP_FUNCTIONS = (
    "_satin_alma_is_acquisition",
    "_devralma_has_acquisition_context",
    "_tesis_is_operational",
    "_classify_event_fields",
)


def _current_installers():
    # Import modules lazily so reloads are visible through their current install
    # function objects rather than through stale aliases captured at import time.
    from . import round15_hardening
    from . import round16_hardening
    from . import round17_hardening
    from . import round18_hardening

    return (
        round15_hardening.install,
        round16_hardening.install,
        round17_hardening.install,
        round18_hardening.install,
    )


def _round18_ready(service: Any) -> bool:
    from . import round18_hardening

    generation = round18_hardening.INSTALL_GENERATION
    wrappers_ready = (
        all(
            getattr(getattr(service, name, None), "_phase10_round18_generation", None)
            is generation
            for name in (
                "_satin_alma_is_acquisition",
                "_devralma_has_acquisition_context",
                "_tesis_is_operational",
            )
        )
        and getattr(
            getattr(service.KapWatchlistAlertService, "check_watchlist", None),
            "_phase10_round18_generation",
            None,
        )
        is generation
    )
    if not wrappers_ready:
        return False

    installed = getattr(service, "_PHASE10_HARDENING_INSTALLER_IDENTITIES", None)
    current = _current_installers()
    return (
        isinstance(installed, tuple)
        and len(installed) == len(current)
        and all(old is new for old, new in zip(installed, current))
    )


def _unwrap_followups(function: Any) -> Any:
    """Return the pre-follow-up function without stacking stale wrappers."""
    current = function
    seen: set[int] = set()
    while id(current) not in seen:
        seen.add(id(current))
        if hasattr(current, "_phase10_round18_original"):
            current = current._phase10_round18_original
            continue
        if hasattr(current, "_phase10_round17_original"):
            current = current._phase10_round17_original
            continue
        if hasattr(current, "_phase10_round16_original"):
            current = current._phase10_round16_original
            continue
        if hasattr(current, "_phase10_round15_original"):
            current = current._phase10_round15_original
            continue
        break
    return current


def _reset_followup_layers(service: Any) -> None:
    for name in _FOLLOWUP_FUNCTIONS:
        current = getattr(service, name, None)
        if current is not None:
            setattr(service, name, _unwrap_followups(current))

    current_check = getattr(service.KapWatchlistAlertService, "check_watchlist", None)
    if current_check is not None:
        service.KapWatchlistAlertService.check_watchlist = _unwrap_followups(current_check)


def install(service: Any) -> None:
    """Install every Phase 10 hardening layer in deterministic order."""
    if _round18_ready(service):
        service._PHASE10_HARDENING_CHAIN_INSTALLED = _ROUND18_VERSION
        return

    # A partial hot reload can leave old follow-up wrappers around only some
    # functions. Remove them before rebuilding so no stale closure or wrapper
    # stack survives a module update.
    _reset_followup_layers(service)
    _install_base(service)

    install_round15, install_round16, install_round17, install_round18 = (
        _current_installers()
    )
    install_round15(service)
    install_round16(service)
    install_round17(service)
    install_round18(service)

    service._PHASE10_HARDENING_INSTALLER_IDENTITIES = (
        install_round15,
        install_round16,
        install_round17,
        install_round18,
    )
    service._PHASE10_HARDENING_CHAIN_INSTALLED = _ROUND18_VERSION


# Round 15 predates the stable orchestrator and contains a compatibility shim
# that wraps ``phase10_hardening.install`` unless this marker is present. Keep
# the public stable entry point protected from that legacy mutation.
install._phase10_round15_chain = True
