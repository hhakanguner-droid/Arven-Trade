"""Round 20 polling compatibility for the consolidated Phase 10 chain.

Round 23 no longer needs Round 20's historical semantic wrappers.  The only
Round 20 behavior that remains architecturally relevant is the watchlist
snapshot/disabled-service polling guard.  Keeping this module small also makes
direct hot-reloaded installs safe: when a newer consolidated chain is already
active, the call is routed back through the stable orchestrator instead of
wrapping over the newest semantics.
"""

from __future__ import annotations

import copy
from typing import Any

_HARDENING_VERSION = "phase10-round20"
INSTALL_GENERATION = object()


def _mark(function: Any, *, original: Any | None = None) -> Any:
    function._phase10_round20_version = _HARDENING_VERSION
    function._phase10_round20_generation = INSTALL_GENERATION
    if original is not None:
        function._phase10_round20_original = original
    return function


def _is_installed(function: Any) -> bool:
    return (
        getattr(function, "_phase10_round20_version", None) == _HARDENING_VERSION
        and getattr(function, "_phase10_round20_generation", None)
        is INSTALL_GENERATION
    )


def _newer_chain_active(service: Any) -> bool:
    chain = str(getattr(service, "_PHASE10_HARDENING_CHAIN_INSTALLED", ""))
    return chain.startswith("phase10-round2") and chain != _HARDENING_VERSION


def install(service: Any) -> None:
    """Install the Round 20 polling guard without displacing newer semantics."""
    if (
        _newer_chain_active(service)
        and not getattr(service, "_PHASE10_HARDENING_REBUILD_IN_PROGRESS", False)
    ):
        from . import phase10_hardening

        phase10_hardening.install(service)
        return

    current = getattr(service.KapWatchlistAlertService, "check_watchlist", None)
    if _is_installed(current):
        service._PHASE10_ROUND20_HARDENING_INSTALLED = _HARDENING_VERSION
        return

    previous_check = getattr(
        current,
        "_phase10_round20_original",
        current,
    )
    disabled_check = getattr(
        previous_check,
        "_phase10_round19_original",
        previous_check,
    )

    class _SnapshotWatchlist:
        def __init__(self, wrapped: Any, snapshot: tuple[str, ...]) -> None:
            self._wrapped = wrapped
            self._snapshot = snapshot

        def __getattr__(self, name: str) -> Any:
            return getattr(self._wrapped, name)

        def list(self):
            return self._snapshot

    def _check_watchlist(self: Any, tickers=None, *, now=None):
        if not self.enabled:
            return disabled_check(self, tickers, now=now)
        if tickers is not None:
            return previous_check(self, tickers, now=now)

        requested = tuple(self.watchlist.list())
        shadow = copy.copy(self)
        shadow.watchlist = _SnapshotWatchlist(self.watchlist, requested)
        return previous_check(shadow, None, now=now)

    service.KapWatchlistAlertService.check_watchlist = _mark(
        _check_watchlist,
        original=previous_check,
    )
    service._PHASE10_ROUND20_HARDENING_INSTALLED = _HARDENING_VERSION
