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


def _legal_designator_pattern() -> str:
    # ``normalize`` transliterates Turkish letters but intentionally preserves
    # punctuation, so both ``A.Ş.`` -> ``a.s.`` and punctuation-free ``as``
    # forms must remain valid at this compatibility boundary.
    return r"(?:a\.?s\.?|ltd\.?\s+sti\.?)"


def _final_purchase_guard(subject: str, summary: str) -> bool | None:
    text = normalize(f"{subject}. {summary}")
    legal = _legal_designator_pattern()

    # A beneficiary introduced by ``için`` is not the passive acquisition
    # target when an explicit procurement object precedes that phrase.
    beneficiary = re.search(
        r"\b(?:makine|ekipman|hammadde|malzeme|urun|yazilim|elektrik|enerji)\w*\s+"
        r"(?:sirket|firma|ortaklik|isletme)\w*(?:\s+\w+){0,3}\s+icin\s+satin\s+alin\w*",
        text,
    )
    if beneficiary:
        return False

    # A legal-company genitive heading followed by ``satın alma ihalesi`` is
    # procurement by that company, not acquisition of the company itself.
    if re.search(
        rf"\b\w+(?:\s+\w+){{0,3}}\s+{legal}['’]?\w*\s+satin\s+alma\s+ihale\w*",
        text,
    ):
        return False

    # Preserve a legal-name passive target when a later company-valued phrase
    # is explicitly marked as the purchasing agent.
    legal_agent = re.search(
        rf"\b\w+(?:\s+\w+){{0,3}}\s+{legal}\s+"
        r"(?:\w+\s+){0,3}(?:sirket|firma|ortaklik|isletme)\w*\s+tarafindan\s+"
        r"(?:\w+\s+){0,3}satin\s+alin\w*",
        text,
    )
    if legal_agent:
        return True

    # Compatibility positives that are structurally company-target noun
    # phrases but are intentionally conservative in the role parser.
    if re.search(
        r"\bsatin\s+aldig\w*(?:\s+\w+){0,6}\s+kurul\w*\s+"
        r"(?:sirket|firma|ortaklik|isletme)\w*\b",
        text,
    ):
        return True
    if re.search(
        r"\bsatin\s+alin\w*\s+(?:elektrik|enerji)\w*\s+dagitim\w*\s+"
        r"(?:sirket|firma|ortaklik|isletme)\w*\b",
        text,
    ):
        return True
    return None


def _final_devralma_guard(subject: str, summary: str) -> bool | None:
    text = normalize(f"{subject}. {summary}")
    # Proper-name accusatives keep their apostrophe in normalized raw text even
    # though tokenization splits them. With a company actor in the same clause,
    # ``Şirket X'i Devraldı`` is an explicit acquisition target.
    if re.search(
        r"\b(?:sirket|firma|ortaklik|isletme)\w*\s+"
        r"[a-z0-9]+\s*['’]\s*(?:i|yi|u|yu)\s+devral\w*\b",
        text,
    ):
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


def _articles_shorthand_reference(subject: str, summary: str) -> bool:
    """Identify generic summary references back to an articles subject."""
    if not re.search(r"\b(?:esas|ana)\s+sozlesme\w*", normalize(subject)):
        return False
    text = normalize(summary)
    if re.search(
        r"\b(?:tedarik|hizmet|kredi|lisans|kira|satis|satim|alim|isbirligi|dagitim)\w*\s+sozlesme\w*",
        text,
    ):
        return False
    return bool(re.search(r"\bsozlesme\w*(?:\s+\w+){0,5}\s+madde\w*", text))


def satin_alma_is_acquisition(text: str) -> bool:
    guarded = _final_purchase_guard(text, "")
    if guarded is not None:
        return guarded
    return _engine.satin_alma_is_acquisition(text)


def devralma_has_acquisition_context(text: str) -> bool:
    guarded = _final_devralma_guard(text, "")
    if guarded is not None:
        return guarded
    return _engine.devralma_has_acquisition_context(text)


def tesis_is_operational(text: str) -> bool:
    return _engine.tesis_is_operational(text)


def term_matches(subject: str, summary: str, term: str) -> bool:
    normalized_term = normalize(term)
    if normalized_term == "satin alma":
        guarded = _final_purchase_guard(subject, summary)
        if guarded is not None:
            return guarded
    if normalized_term == "devralma":
        guarded = _final_devralma_guard(subject, summary)
        if guarded is not None:
            return guarded
    if normalized_term in {"geri alim", "pay geri alim"}:
        guarded = _final_repurchase_guard(subject, summary)
        if guarded is not None:
            return guarded
    if normalized_term == "sozlesme":
        if _independent_commercial_contract(subject, summary):
            return True
        if _articles_shorthand_reference(subject, summary):
            return False
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

    repurchase_guard = _final_repurchase_guard(subject, summary)
    articles_shorthand = _articles_shorthand_reference(subject, summary)

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
            # Explicit negative guards are authoritative. The fallback exists
            # for compatibility but must not resurrect the exact semantic class
            # that a final guard deliberately rejected.
            if repurchase_guard is False and base_category == "ownership":
                base_score = -1
            if articles_shorthand and base_category == "commercial":
                base_score = -1
            if base_score > score:
                category, score = base_category, base_score
    if is_corrective and score:
        score = min(100, score + 5)
    severity = "critical" if score >= 95 else "high" if score >= 85 else "medium" if score >= 70 else "low"
    return category, score, severity


def event_term_matches_compat(text: str, term: str) -> bool:
    return term_matches(text, "", term)
