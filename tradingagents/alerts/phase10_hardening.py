"""Stable Phase 10 hardening orchestration entry point.

The implementation accumulated through Codex Round 14 lives in
``phase10_hardening_base``. This module remains the single stable entry point:
every explicit ``install`` reconstructs the deterministic
base -> Round 15 -> Round 16 -> Round 17 -> Round 18 -> Round 19 -> Round 20
-> Round 21 chain whenever a loaded installer, extracted base implementation,
or installed closure has changed.
"""

from __future__ import annotations

from typing import Any

_ROUND21_VERSION = "phase10-round21"
_FOLLOWUP_FUNCTIONS = (
    "_satin_alma_is_acquisition",
    "_devralma_has_acquisition_context",
    "_tesis_is_operational",
    "_classify_event_fields",
)


def _current_phase10_base_install():
    from . import phase10_hardening_base

    return phase10_hardening_base.install


def _current_installers():
    from . import round15_hardening
    from . import round16_hardening
    from . import round17_hardening
    from . import round18_hardening
    from . import round19_hardening
    from . import round20_hardening
    from . import round21_hardening

    return (
        round15_hardening.install,
        round16_hardening.install,
        round17_hardening.install,
        round18_hardening.install,
        round19_hardening.install,
        round20_hardening.install,
        round21_hardening.install,
    )


def _current_base_installers():
    """Track extracted implementations as well as their stable wrappers."""
    from . import phase10_hardening_base
    from . import round17_hardening_base
    from . import round18_hardening_base
    from . import round19_hardening_base

    return (
        phase10_hardening_base.install,
        round17_hardening_base.install,
        round18_hardening_base.install,
        round19_hardening_base.install,
    )


def _current_installer_identities():
    return _current_installers() + _current_base_installers()


def _round21_ready(service: Any) -> bool:
    from . import round20_hardening
    from . import round21_hardening

    generation = round21_hardening.INSTALL_GENERATION
    wrappers_ready = all(
        getattr(getattr(service, name, None), "_phase10_round21_generation", None)
        is generation
        for name in (
            "_satin_alma_is_acquisition",
            "_devralma_has_acquisition_context",
            "_tesis_is_operational",
            "_classify_event_fields",
        )
    )
    if not wrappers_ready:
        return False

    # Round 21 does not need to wrap polling; keep Round 20's verified snapshot
    # wrapper current as part of chain readiness.
    current_check = getattr(service.KapWatchlistAlertService, "check_watchlist", None)
    if (
        getattr(current_check, "_phase10_round20_generation", None)
        is not round20_hardening.INSTALL_GENERATION
    ):
        return False

    installed = getattr(service, "_PHASE10_HARDENING_INSTALLER_IDENTITIES", None)
    current = _current_installer_identities()
    return (
        isinstance(installed, tuple)
        and len(installed) == len(current)
        and all(old is new for old, new in zip(installed, current))
    )


def _unwrap_followups(function: Any) -> Any:
    current = function
    seen: set[int] = set()
    while id(current) not in seen:
        seen.add(id(current))
        if hasattr(current, "_phase10_round21_original"):
            current = current._phase10_round21_original
            continue
        if hasattr(current, "_phase10_round20_original"):
            current = current._phase10_round20_original
            continue
        if hasattr(current, "_phase10_round19_original"):
            current = current._phase10_round19_original
            continue
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
        service.KapWatchlistAlertService.check_watchlist = _unwrap_followups(
            current_check
        )


def _set_compatibility_markers(service: Any) -> None:
    from . import round17_hardening
    from . import round18_hardening
    from . import round19_hardening

    functions = [
        getattr(service, "_satin_alma_is_acquisition", None),
        getattr(service, "_devralma_has_acquisition_context", None),
        getattr(service, "_tesis_is_operational", None),
        getattr(service.KapWatchlistAlertService, "check_watchlist", None),
    ]
    for function in functions:
        if function is None:
            continue
        function._phase10_round15_version = "phase10-round15"
        function._phase10_round16_version = "phase10-round16"
        function._phase10_round17_version = "phase10-round17"
        function._phase10_round17_generation = round17_hardening.INSTALL_GENERATION
        function._phase10_round18_version = "phase10-round18"
        function._phase10_round18_generation = round18_hardening.INSTALL_GENERATION
        function._phase10_round19_version = "phase10-round19"
        function._phase10_round19_generation = round19_hardening.INSTALL_GENERATION


def install(service: Any) -> None:
    """Install every Phase 10 hardening layer in deterministic order."""
    if _round21_ready(service):
        _set_compatibility_markers(service)
        service._PHASE10_HARDENING_CHAIN_INSTALLED = _ROUND21_VERSION
        return

    previous_rebuild_flag = getattr(
        service, "_PHASE10_HARDENING_REBUILD_IN_PROGRESS", None
    )
    service._PHASE10_HARDENING_REBUILD_IN_PROGRESS = True
    try:
        _reset_followup_layers(service)
        _current_phase10_base_install()(service)

        (
            install_round15,
            install_round16,
            install_round17,
            install_round18,
            install_round19,
            install_round20,
            install_round21,
        ) = _current_installers()
        install_round15(service)
        install_round16(service)
        install_round17(service)
        install_round18(service)
        install_round19(service)
        install_round20(service)
        install_round21(service)

        service._PHASE10_HARDENING_INSTALLER_IDENTITIES = (
            _current_installer_identities()
        )
        _set_compatibility_markers(service)
        service._PHASE10_HARDENING_CHAIN_INSTALLED = _ROUND21_VERSION
    finally:
        if previous_rebuild_flag is None:
            try:
                delattr(service, "_PHASE10_HARDENING_REBUILD_IN_PROGRESS")
            except AttributeError:
                pass
        else:
            service._PHASE10_HARDENING_REBUILD_IN_PROGRESS = previous_rebuild_flag


install._phase10_round15_chain = True
