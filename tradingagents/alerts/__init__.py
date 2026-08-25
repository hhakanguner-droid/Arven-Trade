"""ARVEN Trade watchlist and notification primitives."""

from . import service as _service
from .models import AlertSourceStatus, WatchlistAlert, WatchlistAlertBatch
from .phase10_hardening import install as _install_phase10_hardening
from .round15_hardening import install as _install_round15_hardening

_install_phase10_hardening(_service)
_install_round15_hardening(_service)

AlertStateStore = _service.AlertStateStore
KapWatchlistAlertService = _service.KapWatchlistAlertService
WatchlistStore = _service.WatchlistStore
classify_kap_disclosure = _service.classify_kap_disclosure
create_watchlist_alert_service = _service.create_watchlist_alert_service

__all__ = [
    "AlertSourceStatus",
    "AlertStateStore",
    "KapWatchlistAlertService",
    "WatchlistAlert",
    "WatchlistAlertBatch",
    "WatchlistStore",
    "classify_kap_disclosure",
    "create_watchlist_alert_service",
]
