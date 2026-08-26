"""Stable Phase 10 hardening orchestration entry point.

Round 22 is the convergence point for Phase 10. Earlier rounds still provide
state/polling/migration hardening, but all Turkish event semantics are replaced
at the outer edge by one consolidated sentence-aware classifier.

Every explicit ``install`` reconstructs the deterministic chain whenever a
loaded installer, extracted base implementation, or semantic implementation
generation changes.
"""

from __future__ import annotations

from typing import Any

_ROUND22_VERSION = "phase10-round22"
_FOLLOWUP_FUNCTIONS = (
    "_satin_alma_is_acquisition",
    "_devralma_has_acquisition_context",
    "_tesis_is_operational",
    "_event_term_matches",
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
    from . import round22_consolidation

    return (
        round15_hardening.install,
        round16_hardening.install,
        round17_hardening.install,
        round18_hardening.install,
        round19_hardening.install,
        round20_hardening.install,
        round21_hardening.install,
        round22_consolidation.install,
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
    from . import semantic_classifier

    return (
        _current_installers()
        + _current_base_installers()
        + (semantic_classifier.IMPLEMENTATION_GENERATION,)
    )


def _round22_ready(service: Any) -> bool:
    from . import round20_hardening
    from . import round22_consolidation
    from . import semantic_classifier

    generation = round22_consolidation.INSTALL_GENERATION
    semantic_generation = semantic_classifier.IMPLEMENTATION_GENERATION
    wrappers_ready = all(
        getattr(getattr(service, name, None), "_phase10_round22_generation", None)
        is generation
        and getattr(
            getattr(service, name, None),
            "_phase10_round22_semantics_generation",
            None,
        )
        is semantic_generation
        for name in _FOLLOWUP_FUNCTIONS
    )
    if not wrappers_ready:
        return False

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
        if hasattr(current, "_phase10_round22_original"):
            current = current._phase10_round22_original
            continue
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
    """Make direct old-round installers recognize the current outer chain."""
    from . import round17_hardening
    from . import round18_hardening
    from . import round19_hardening
    from . import round20_hardening
    from . import round21_hardening

    functions = [
        getattr(service, "_satin_alma_is_acquisition", None),
        getattr(service, "_devralma_has_acquisition_context", None),
        getattr(service, "_tesis_is_operational", None),
        getattr(service, "_classify_event_fields", None),
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

        function._phase10_round20_version = "phase10-round20"
        function._phase10_round20_generation = round20_hardening.INSTALL_GENERATION

        function._phase10_round21_version = "phase10-round21"
        function._phase10_round21_generation = round21_hardening.INSTALL_GENERATION


def install(service: Any) -> None:
    """Install every Phase 10 hardening layer in deterministic order."""
    if _round22_ready(service):
        _set_compatibility_markers(service)
        service._PHASE10_HARDENING_CHAIN_INSTALLED = _ROUND22_VERSION
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
            install_round22,
        ) = _current_installers()

        install_round15(service)
        install_round16(service)
        install_round17(service)
        install_round18(service)
        install_round19(service)
        install_round20(service)
        install_round21(service)
        install_round22(service)

        service._PHASE10_HARDENING_INSTALLER_IDENTITIES = (
            _current_installer_identities()
        )
        _set_compatibility_markers(service)
        service._PHASE10_HARDENING_CHAIN_INSTALLED = _ROUND22_VERSION
    finally:
        if previous_rebuild_flag is None:
            try:
                delattr(service, "_PHASE10_HARDENING_REBUILD_IN_PROGRESS")
            except AttributeError:
                pass
        else:
            service._PHASE10_HARDENING_REBUILD_IN_PROGRESS = previous_rebuild_flag


install._phase10_round15_chain = True
