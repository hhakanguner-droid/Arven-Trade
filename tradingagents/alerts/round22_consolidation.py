"""Round 22 Phase 10 semantic consolidation.

This is deliberately not another grammatical patch layer.  Earlier Phase 10
rounds remain installed for state, polling, migration, capacity, and hot-reload
behavior, but the final semantic entry points are replaced by one consolidated
sentence-aware classifier from ``semantic_classifier``.

The replacement is intentionally non-nested: every semantic decision flows
through one implementation rather than falling back through Round 15..21
closures.  That prevents a negative decision in the newest grammar from being
overridden by an older matcher.
"""

from __future__ import annotations

from typing import Any

from . import semantic_classifier as semantics

_HARDENING_VERSION = "phase10-round22"
INSTALL_GENERATION = object()


def _mark(function: Any, *, original: Any | None = None) -> Any:
    function._phase10_round22_version = _HARDENING_VERSION
    function._phase10_round22_generation = INSTALL_GENERATION
    function._phase10_round22_semantics_generation = (
        semantics.IMPLEMENTATION_GENERATION
    )
    if original is not None:
        function._phase10_round22_original = original
    return function


def _is_installed(function: Any) -> bool:
    return (
        getattr(function, "_phase10_round22_version", None)
        == _HARDENING_VERSION
        and getattr(function, "_phase10_round22_generation", None)
        is INSTALL_GENERATION
        and getattr(function, "_phase10_round22_semantics_generation", None)
        is semantics.IMPLEMENTATION_GENERATION
    )


def install(service: Any) -> None:
    """Install the consolidated Phase 10 semantic layer idempotently."""
    required = (
        getattr(service, "_satin_alma_is_acquisition", None),
        getattr(service, "_devralma_has_acquisition_context", None),
        getattr(service, "_tesis_is_operational", None),
        getattr(service, "_event_term_matches", None),
        getattr(service, "_classify_event_fields", None),
    )
    if all(_is_installed(function) for function in required):
        service._PHASE10_ROUND22_HARDENING_INSTALLED = _HARDENING_VERSION
        return

    previous_purchase = getattr(
        service._satin_alma_is_acquisition,
        "_phase10_round22_original",
        service._satin_alma_is_acquisition,
    )
    previous_devralma = getattr(
        service._devralma_has_acquisition_context,
        "_phase10_round22_original",
        service._devralma_has_acquisition_context,
    )
    previous_tesis = getattr(
        service._tesis_is_operational,
        "_phase10_round22_original",
        service._tesis_is_operational,
    )
    previous_term_match = getattr(
        service._event_term_matches,
        "_phase10_round22_original",
        service._event_term_matches,
    )
    previous_classify = getattr(
        service._classify_event_fields,
        "_phase10_round22_original",
        service._classify_event_fields,
    )

    def _satin_alma_is_acquisition(text: str) -> bool:
        return semantics.satin_alma_is_acquisition(text)

    def _devralma_has_acquisition_context(text: str) -> bool:
        return semantics.devralma_has_acquisition_context(text)

    def _tesis_is_operational(text: str) -> bool:
        return semantics.tesis_is_operational(text)

    def _event_term_matches(text: str, term: str) -> bool:
        return semantics.event_term_matches_compat(text, term)

    def _classify_event_fields(
        subject: str,
        summary: str,
        disclosure_type: str,
        is_corrective: bool,
    ):
        return semantics.classify_event_fields(
            subject,
            summary,
            disclosure_type,
            is_corrective,
            service._EVENT_RULES,
        )

    service._satin_alma_is_acquisition = _mark(
        _satin_alma_is_acquisition,
        original=previous_purchase,
    )
    service._devralma_has_acquisition_context = _mark(
        _devralma_has_acquisition_context,
        original=previous_devralma,
    )
    service._tesis_is_operational = _mark(
        _tesis_is_operational,
        original=previous_tesis,
    )
    service._event_term_matches = _mark(
        _event_term_matches,
        original=previous_term_match,
    )
    service._classify_event_fields = _mark(
        _classify_event_fields,
        original=previous_classify,
    )
    service._PHASE10_ROUND22_HARDENING_INSTALLED = _HARDENING_VERSION
