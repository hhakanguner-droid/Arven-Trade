"""Stable Phase 10 hardening orchestration entry point.

The implementation that accumulated through Codex Round 14 lives in
``phase10_hardening_base``.  This module intentionally stays tiny so reloading
it cannot silently discard later hardening layers: every explicit ``install``
call deterministically reapplies the base, Round 15, and Round 16 installers.
"""

from __future__ import annotations

from typing import Any

from .phase10_hardening_base import install as _install_base


def install(service: Any) -> None:
    """Install every Phase 10 hardening layer in deterministic order."""
    _install_base(service)

    # Lazy imports avoid circular import work while the alerts package itself is
    # being initialized, and ensure module reloads always resolve the current
    # installer functions rather than stale function objects.
    from .round15_hardening import install as install_round15
    from .round16_hardening import install as install_round16

    install_round15(service)
    install_round16(service)
