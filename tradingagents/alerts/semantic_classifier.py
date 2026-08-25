"""Stable facade for the consolidated Phase 10 KAP semantic engine."""

from __future__ import annotations

from typing import Iterable

from . import semantic_engine_v23_2 as _engine

IMPLEMENTATION_GENERATION = object()

normalize = _engine.normalize
tokens = _engine.tokens
segments = _engine.segments
satin_alma_is_acquisition = _engine.satin_alma_is_acquisition
devralma_has_acquisition_context = _engine.devralma_has_acquisition_context
tesis_is_operational = _engine.tesis_is_operational
term_matches = _engine.term_matches


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
