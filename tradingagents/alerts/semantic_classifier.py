"""Compatibility facade for the consolidated Phase 10 semantic engine.

Round 23 keeps this import path stable while moving the actual Turkish KAP
semantics into ``semantic_engine_v23``.  The facade owns a per-load generation
identity so hot reloads still force the stable Phase 10 orchestrator to rebuild
the outer semantic wrappers.
"""

from __future__ import annotations

from typing import Iterable

from . import semantic_engine_v23 as _engine

IMPLEMENTATION_GENERATION = object()


def normalize(value: str) -> str:
    return _engine.normalize(value)


def tokens(value: str) -> list[str]:
    return _engine.tokens(value)


def segments(*values: str) -> list[str]:
    return _engine.segments(*values)


def satin_alma_is_acquisition(text: str) -> bool:
    return _engine.satin_alma_is_acquisition(text)


def devralma_has_acquisition_context(text: str) -> bool:
    return _engine.devralma_has_acquisition_context(text)


def tesis_is_operational(text: str) -> bool:
    return _engine.tesis_is_operational(text)


def term_matches(subject: str, summary: str, term: str) -> bool:
    return _engine.term_matches(subject, summary, term)


def classify_event_fields(
    subject: str,
    summary: str,
    disclosure_type: str,
    is_corrective: bool,
    event_rules: Iterable[tuple[str, int, tuple[str, ...]]],
) -> tuple[str, int, str]:
    return _engine.classify_event_fields(
        subject,
        summary,
        disclosure_type,
        is_corrective,
        event_rules,
    )


def event_term_matches_compat(text: str, term: str) -> bool:
    return _engine.event_term_matches_compat(text, term)
