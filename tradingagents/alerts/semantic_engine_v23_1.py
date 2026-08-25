"""Round 23.1 semantic compatibility corrections over the consolidated engine."""

from __future__ import annotations

import re
from typing import Iterable

from . import semantic_engine_v23 as _base


def normalize(value: str) -> str:
    return _base.normalize(value)


def tokens(value: str) -> list[str]:
    return _base.tokens(value)


def segments(*values: str) -> list[str]:
    return _base.segments(*values)


def _named_passive_company_target(text: str) -> bool:
    for segment in _base.segments(text):
        items = re.findall(r"\w+", segment)
        for index in range(len(items) - 1):
            if items[index] != "satin" or not items[index + 1].startswith("alin"):
                continue
            before = items[:index]
            if any(
                token.startswith(
                    ("sirketinin", "firmanin", "firmasinin", "ortakligin", "isletmenin")
                )
                for token in before
            ):
                return True
            if any(token in {"as", "ltd", "sti"} for token in before[-5:]) and any(
                token in {"in", "nin", "un", "nun"} for token in before[-4:]
            ):
                return True
    return False


def satin_alma_is_acquisition(text: str) -> bool:
    if _named_passive_company_target(text):
        return True
    return _base.satin_alma_is_acquisition(text)


def devralma_has_acquisition_context(text: str) -> bool:
    return _base.devralma_has_acquisition_context(text)


def tesis_is_operational(text: str) -> bool:
    return _base.tesis_is_operational(text)


def _ownership_ortaklik_matches(subject: str, summary: str) -> bool:
    for segment in _base.segments(subject, summary):
        items = re.findall(r"\w+", segment)
        if not any(item.startswith(("ortaklik", "ortaklig")) for item in items):
            continue
        if any(
            item.startswith(
                ("pay", "hisse", "sermaye", "hakim", "kontrol", "oran", "yapi", "degis")
            )
            for item in items
        ):
            return True
    return False


def term_matches(subject: str, summary: str, term: str) -> bool:
    needle = _base.normalize(term)
    if needle == "satin alma":
        return satin_alma_is_acquisition(f"{subject}. {summary}")
    if needle == "ortaklik":
        return _ownership_ortaklik_matches(subject, summary)
    return _base.term_matches(subject, summary, term)


def classify_event_fields(
    subject: str,
    summary: str,
    disclosure_type: str,
    is_corrective: bool,
    event_rules: Iterable[tuple[str, int, tuple[str, ...]]],
) -> tuple[str, int, str]:
    category = "other"
    score = 0
    if str(disclosure_type).upper() in {"FR", "FS"}:
        category, score = "financials", 100

    for candidate, weight, terms in event_rules:
        if weight <= score:
            continue
        if any(term_matches(subject, summary, term) for term in terms):
            category, score = candidate, weight

    if score < 80 and _base._procurement_operation(subject, summary):
        category, score = "operations", 80

    if is_corrective and score:
        score = min(100, score + 5)

    if score >= 95:
        severity = "critical"
    elif score >= 85:
        severity = "high"
    elif score >= 70:
        severity = "medium"
    else:
        severity = "low"
    return category, score, severity


def event_term_matches_compat(text: str, term: str) -> bool:
    return term_matches(text, "", term)
