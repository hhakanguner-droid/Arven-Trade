"""Compatibility facade for the role-aware Phase 10 KAP semantic parser.

Round 23.2 used to contain the grammar heuristics directly. The active semantic
core lives in ``semantic_role_parser`` and resolves roles structurally as
clause -> predicate -> agent/vendor -> object -> event decision. Keeping this
module as a thin facade preserves imports while the small guards below protect
final exact-head ambiguities at the public semantic boundary.
"""
from __future__ import annotations

import re
from typing import Iterable

from . import semantic_role_parser as _engine

IMPLEMENTATION_GENERATION = object()


def normalize(value: str) -> str:
    return _engine.normalize(value)


def tokens(value: str) -> list[str]:
    return _engine.tokens(value)


def segments(*values: str) -> list[str]:
    return _engine.segments(*values)


def _final_purchase_guard(subject: str, summary: str) -> bool | None:
    text = normalize(f"{subject}. {summary}")

    # A beneficiary introduced by ``için`` is not the passive acquisition
    # target when an explicit procurement object precedes that phrase.
    beneficiary = re.search(
        r"\b(?:makine|ekipman|hammadde|malzeme|urun|yazilim|elektrik|enerji)\w*\s+"
        r"(?:sirket|firma|ortaklik|isletme)\w*(?:\s+\w+){0,3}\s+icin\s+satin\s+alin\w*",
        text,
    )
    if beneficiary:
        return False

    # Preserve a legal-name passive target when a *later* company-valued phrase
    # is explicitly marked as the purchasing agent.
    legal_agent = re.search(
        r"\b\w+(?:\s+\w+){0,3}\s+(?:as|ltd\s+sti)\s+"
        r"(?:\w+\s+){0,3}(?:sirket|firma|ortaklik|isletme)\w*\s+tarafindan\s+"
        r"(?:\w+\s+){0,3}satin\s+alin\w*",
        text,
    )
    if legal_agent:
        return True
    return None


def _final_repurchase_guard(subject: str, summary: str) -> bool | None:
    text = normalize(f"{subject}. {summary}")
    # ``ekmek``/``yemek`` are nouns despite sharing the Turkish infinitive
    # suffix shape. They must remain explicit product objects.
    if re.search(r"\b(?:ekmek|yemek)\s+geri\s+alim\w*\s+program\w*", text):
        return False
    return None


def _independent_commercial_contract(subject: str, summary: str) -> bool:
    if not re.search(r"\b(?:esas|ana)\s+sozlesme\w*", normalize(subject)):
        return False
    text = normalize(summary)
    # A numbered article of an independently named commercial agreement is
    # still a commercial-contract event; the articles-of-association exclusion
    # must not leak across contract identities.
    return bool(re.search(
        r"\b(?:tedarik|hizmet|kredi|lisans|kira|satis|satim|alim|isbirligi|dagitim)\w*\s+"
        r"sozlesme\w*(?:\s+\w+){0,5}\s+\d+\s+(?:sayili|numarali|nci|inci|uncu)?\s*madde\w*",
        text,
    ))


def satin_alma_is_acquisition(text: str) -> bool:
    guarded = _final_purchase_guard(text, "")
    if guarded is not None:
        return guarded
    return _engine.satin_alma_is_acquisition(text)


def devralma_has_acquisition_context(text: str) -> bool:
    return _engine.devralma_has_acquisition_context(text)


def tesis_is_operational(text: str) -> bool:
    return _engine.tesis_is_operational(text)


def term_matches(subject: str, summary: str, term: str) -> bool:
    normalized_term = normalize(term)
    if normalized_term == "satin alma":
        guarded = _final_purchase_guard(subject, summary)
        if guarded is not None:
            return guarded
    if normalized_term in {"geri alim", "pay geri alim"}:
        guarded = _final_repurchase_guard(subject, summary)
        if guarded is not None:
            return guarded
    if normalized_term == "sozlesme" and _independent_commercial_contract(subject, summary):
        return True
    return _engine.term_matches(subject, summary, term)


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
    if score < 80:
        purchase_guard = _final_purchase_guard(subject, summary)
        if purchase_guard is False and re.search(
            r"\b(?:makine|ekipman|hammadde|malzeme|urun|yazilim|elektrik|enerji)\w*",
            normalize(f"{subject}. {summary}"),
        ):
            category, score = "operations", 80
        else:
            base_category, base_score, _ = _engine.classify_event_fields(
                subject,
                summary,
                disclosure_type,
                False,
                event_rules,
            )
            if base_score > score:
                category, score = base_category, base_score
    if is_corrective and score:
        score = min(100, score + 5)
    severity = "critical" if score >= 95 else "high" if score >= 85 else "medium" if score >= 70 else "low"
    return category, score, severity


def event_term_matches_compat(text: str, term: str) -> bool:
    return term_matches(text, "", term)
