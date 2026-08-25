"""Stable Phase 10 hardening orchestration entry point.

The implementation that accumulated through Codex Round 14 lives in
``phase10_hardening_base``. This module intentionally stays tiny so reloading it
cannot silently discard later hardening layers: every explicit ``install`` call
reconstructs the same base -> Round 15 -> Round 16 -> Round 17 chain when repair
is needed.
"""

from __future__ import annotations

from typing import Any

from .phase10_hardening_base import install as _install_base

_ROUND17_VERSION = "phase10-round17"
_FOLLOWUP_FUNCTIONS = (
    "_satin_alma_is_acquisition",
    "_devralma_has_acquisition_context",
    "_tesis_is_operational",
    "_classify_event_fields",
)


def _round17_ready(service: Any) -> bool:
    return (
        all(
            getattr(getattr(service, name, None), "_phase10_round17_version", None)
            == _ROUND17_VERSION
            for name in _FOLLOWUP_FUNCTIONS
        )
        and getattr(
            getattr(service.KapWatchlistAlertService, "check_watchlist", None),
            "_phase10_round17_version",
            None,
        )
        == _ROUND17_VERSION
    )


def _unwrap_followups(function: Any) -> Any:
    """Return the pre-Round-15 function without stacking old follow-up wrappers."""
    current = function
    seen: set[int] = set()
    while id(current) not in seen:
        seen.add(id(current))
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
    if _round17_ready(service):
        service._PHASE10_HARDENING_CHAIN_INSTALLED = _ROUND17_VERSION
        return

    # A partial hot reload can leave old follow-up wrappers around only some
    # functions. Remove those wrappers first so repair never grows a wrapper
    # stack and the base installer sees a predictable surface.
    _reset_followup_layers(service)
    _install_base(service)

    # Lazy imports avoid circular import work while the alerts package itself is
    # being initialized, and resolve current installer functions after reloads.
    from .round15_hardening import install as install_round15
    from .round16_hardening import install as install_round16
    from .round17_hardening import install as install_round17

    install_round15(service)
    install_round16(service)
    install_round17(service)
    service._PHASE10_HARDENING_CHAIN_INSTALLED = _ROUND17_VERSION


# Round 15 predates the stable orchestrator and still contains a compatibility
# shim that wraps ``phase10_hardening.install`` unless this marker is present.
# Mark the stable entry point as already chained so legacy code cannot append a
# Round 15 install after Round 17 on repeated explicit calls.
install._phase10_round15_chain = True
