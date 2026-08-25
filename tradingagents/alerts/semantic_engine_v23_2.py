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
    protected: list[str] = []
    for value in values:
        text = str(value or "")
        text = re.sub(r"\bA\.S\.", "AS", text, flags=re.IGNORECASE)
        text = re.sub(r"\bLtd\.\s+Sti\.", "Ltd Sti", text, flags=re.IGNORECASE)
        protected.append(text)
    return _engine.segments(*protected)


def _legal_designator_pattern() -> str:
    return r"(?:a\.?s\.?|ltd\.?\s+sti\.?)"


def _is_procurement_token(token: str) -> bool:
    checker = getattr(_engine, "_procure", None)
    if callable(checker):
        return bool(checker(token))
    prefixes = getattr(_engine, "_PROCURE", ())
    return bool(prefixes and token.startswith(prefixes))


def _is_product_repurchase_token(token: str) -> bool:
    if token.startswith(("ekmek", "yemek")):
        return True
    prefixes = getattr(_engine, "_PRODUCT", ())
    return bool(prefixes and token.startswith(prefixes))


def _contains_procurement_object(value: str) -> bool:
    return any(_is_procurement_token(token) for token in tokens(value))


def _contains_product_repurchase_object(value: str) -> bool:
    return any(_is_product_repurchase_token(token) for token in tokens(value))


def _explicit_purchase_target(value: str) -> bool:
    text = normalize(value)
    if re.search(
        r"\b(?:sirketini|firmayi|firmasini|ortakligi|isletmeyi|istiraki|istirakini|"
        r"payi|paylari|hisseyi|hisseleri|varligi|varliklari)\s+satin\s+al\w*",
        text,
    ):
        return True

    relative = re.search(
        r"\bsatin\s+aldig\w*(?P<middle>(?:\s+\w+){0,4})\s+"
        r"(?:bagli\s+)?(?:ortaklik|istirak|sirket|firma|isletme)\w*\b",
        text,
    )
    if not relative:
        return False
    # A procurement noun governed by the relative purchase predicate proves
    # that the later company is merely the location/relationship head, not the
    # purchased object (e.g. sunucunun/bilgisayarın kurulduğu şirketle...).
    if _contains_procurement_object(relative.group("middle")):
        return False
    return True


def _purchase_guard_clause(value: str) -> bool | None:
    text = normalize(value)
    if not text.strip():
        return None
    legal = _legal_designator_pattern()

    if _explicit_purchase_target(text):
        return True

    if re.search(
        r"\b(?:\w+\s+){0,3}(?:sirket|firma|ortaklik|isletme)\w*(?:\s+\w+){0,3}\s+icin\s+satin\s+alin\w*",
        text,
    ) and _contains_procurement_object(text):
        return False

    if re.search(
        rf"\b\w+(?:\s+\w+){{0,3}}\s+{legal}['’]?\w*(?:\s+\w+){{0,3}}\s+satin\s+alma\s+ihale\w*",
        text,
    ) or re.search(
        r"\b(?:sirket|firma|ortaklik|ortaklig|isletme|holding|grup)\w*(?:['’]\w*)?"
        r"(?:\s+\w+){0,3}\s+satin\s+alma\s+ihale\w*",
        text,
    ):
        return False

    if re.search(
        rf"\b\w+(?:\s+\w+){{0,3}}\s+{legal}\s+"
        r"(?:\w+\s+){0,3}(?:sirket|firma|ortaklik|isletme)\w*\s+tarafindan\s+"
        r"(?:\w+\s+){0,3}satin\s+alin\w*",
        text,
    ):
        return True

    rel = re.search(
        r"\bsatin\s+aldig\w*(?P<middle>(?:\s+\S+){0,8})\s+"
        r"(?:sirket|firma|ortaklik|isletme)\w*\b",
        text,
    )
    if rel:
        middle = rel.group("middle")
        if _contains_procurement_object(middle):
            return False
        if re.search(r"\bkurul\w*\b", middle):
            return True

    if re.search(
        r"\bsatin\s+alin\w*\s+(?:elektrik|enerji)\w*\s+dagitim\w*\s+"
        r"(?:sirket|firma|ortaklik|isletme)\w*\b",
        text,
    ):
        return True
    return None


def _purchase_guard_single(value: str) -> bool | None:
    decisions = [_purchase_guard_clause(part) for part in segments(value)]
    if True in decisions:
        return True
    if False in decisions:
        return False
    return None


def _proper_purchase_target(subject: str, summary: str) -> bool:
    raw = f"{subject}. {summary}"
    return bool(
        re.search(
            r"\b(?:Şirket|Firma|Ortaklık|İşletme)\w*\s+[A-Z0-9]{1,5}['’](?:i|ı|u|ü|yi|yı|yu|yü)\s+"
            r"satın\s+al(?:dı|acak|ıyor)\w*\b",
            raw,
            flags=re.IGNORECASE,
        )
    )


def _purchase_heading_target(subject: str, summary: str) -> bool:
    raw = normalize(f"{subject}. {summary}")
    return bool(
        re.search(
            r"\b(?:satin\s+alma|devralma)\s*:\s*(?:\w+\s+){0,3}"
            r"(?:sirketi|firmasi|ortakligi|isletmesi|holding|grup)\b",
            raw,
        )
    )


def _final_purchase_guard(subject: str, summary: str) -> bool | None:
    if _proper_purchase_target(subject, summary) or _purchase_heading_target(subject, summary):
        return True
    decisions = [_purchase_guard_single(subject), _purchase_guard_single(summary)]
    if True in decisions:
        return True
    if False in decisions:
        return False
    return None


def _final_devralma_guard(subject: str, summary: str) -> bool | None:
    raw = f"{subject}. {summary}"
    if _purchase_heading_target(subject, summary):
        return True
    if re.search(
        r"\b(?:Şirket|Firma|Ortaklık|İşletme)\w*\s+[A-Z0-9]{1,5}['’](?:i|ı|u|ü|yi|yı|yu|yü)\s+Devral\w*\b",
        raw,
    ):
        return True
    if re.search(
        r"\b(?:sirket|firma|ortaklik|isletme)\w*\s+[A-Z0-9]{1,5}\s*['’]\s*(?:i|yi|u|yu)\s+devral\w*\b",
        raw,
    ):
        return True
    return None


def _repurchase_guard_clause(value: str) -> bool | None:
    text = normalize(value)
    if not re.search(r"\bgeri\s+alim\w*", text):
        return None
    if re.search(r"\b(?:pay|hisse)\w*\s+geri\s+alim\w*", text):
        return True
    before_repurchase = re.split(r"\bgeri\s+alim\w*", text, maxsplit=1)[0]
    if _contains_product_repurchase_object(before_repurchase):
        return False
    if re.search(r"\b(?:sirket|ortaklik|ortaklig)\w*(?:\s+\w+){0,3}\s+geri\s+alim\w*\s+program\w*", text):
        return True
    return None


def _repurchase_guard_single(value: str) -> bool | None:
    decisions = [_repurchase_guard_clause(part) for part in segments(value)]
    if True in decisions:
        return True
    if False in decisions:
        return False
    return None


def _final_repurchase_guard(subject: str, summary: str) -> bool | None:
    decisions = [_repurchase_guard_single(subject), _repurchase_guard_single(summary)]
    if True in decisions:
        return True
    if False in decisions:
        return False
    return None


def _company_article_qualifier(token: str) -> bool:
    return token.startswith(("sirket", "ortaklik", "ortaklig", "firma", "isletme"))


def _named_commercial_contract(text: str) -> bool:
    normalized = normalize(text)
    for match in re.finditer(r"\b([a-z0-9]+)\w*\s+sozlesme\w*", normalized):
        descriptor = match.group(1)
        if descriptor not in {"esas", "ana"} and not _company_article_qualifier(descriptor):
            return True
    for match in re.finditer(r"\b([a-z0-9]+)\w*\s+(?:ana|esas)\s+sozlesme\w*", normalized):
        qualifier = match.group(1)
        if qualifier not in {"esas", "ana"} and not _company_article_qualifier(qualifier):
            return True
    return False


def _independent_commercial_contract(subject: str, summary: str) -> bool:
    if not re.search(r"\b(?:esas|ana)\s+sozlesme\w*", normalize(subject)):
        return False
    return _named_commercial_contract(summary)


def _numbered_article_reference(value: str) -> bool:
    """Recognize generic contract-article shorthand, including 6. and 6'ncı."""
    text = normalize(value)
    if _named_commercial_contract(value):
        return False
    return bool(
        re.search(
            r"\bsozlesme\w*(?:\s+\w+){0,3}\s+\d+(?:\.|['’]?(?:nci|nci|ncu|ncu))?\s*(?:numarali|sayili)?\s+madde\w*",
            text,
        )
        or re.search(r"\bsozlesme\w*\s+\d+\.?\s+madde\w*", text)
    )


def _articles_shorthand_reference(subject: str, summary: str) -> bool:
    if not re.search(r"\b(?:esas|ana)\s+sozlesme\w*", normalize(subject)):
        return False
    if _named_commercial_contract(summary):
        return False
    text = normalize(summary)
    return bool(
        re.search(r"\bsozlesme\w*(?:\s+\w+){0,5}\s+madde\w*", text)
        or _numbered_article_reference(summary)
    )


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
        if _numbered_article_reference(subject) or _numbered_article_reference(summary):
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
    business_relationship = False
    for candidate, weight, terms in event_rules:
        if weight <= score:
            continue
        matched_terms = []
        for term in terms:
            if normalize(term) == "is iliskisi":
                business_relationship = business_relationship or term_matches(subject, summary, term)
                continue
            if term_matches(subject, summary, term):
                matched_terms.append(term)
        if matched_terms:
            category, score = candidate, weight

    if business_relationship and score <= 80:
        category, score = "commercial", 80

    repurchase_guard = _final_repurchase_guard(subject, summary)
    articles_shorthand = _articles_shorthand_reference(subject, summary)

    if score < 80:
        purchase_guard = _final_purchase_guard(subject, summary)
        if purchase_guard is False and _contains_procurement_object(f"{subject}. {summary}"):
            category, score = "operations", 80
        else:
            base_category, base_score, _ = _engine.classify_event_fields(
                subject,
                summary,
                disclosure_type,
                False,
                event_rules,
            )
            if repurchase_guard is False and base_category == "ownership":
                base_score = -1
            if (articles_shorthand or _numbered_article_reference(subject) or _numbered_article_reference(summary)) and base_category == "commercial":
                base_score = -1
            if base_score > score:
                category, score = base_category, base_score
    if is_corrective and score:
        score = min(100, score + 5)
    severity = "critical" if score >= 95 else "high" if score >= 85 else "medium" if score >= 70 else "low"
    return category, score, severity


def event_term_matches_compat(text: str, term: str) -> bool:
    return term_matches(text, "", term)
