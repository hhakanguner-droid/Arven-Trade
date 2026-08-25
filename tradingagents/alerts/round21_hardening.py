"""Round 21 hardening for Phase 10 KAP semantics and reload stability.

Round 21 closes the exact-head Codex findings from Round 20.  It keeps the
public API unchanged while tightening grammatical ownership of purchase and
takeover objects, preserving raw sentence boundaries for property-right
analysis, scoping legal price modifiers to their own clause, and making the
stable installer aware of reloaded base implementations.
"""

from __future__ import annotations

from typing import Any

_HARDENING_VERSION = "phase10-round21"
INSTALL_GENERATION = object()

_COMPANY_PREFIXES = (
    "sirket",
    "firma",
    "ortaklik",
    "ortaklig",
    "isletme",
    "istirak",
)
_BARE_COMPANY_FORMS = {"sirket", "firma", "ortaklik", "isletme", "istirak"}
_SPEAKER_COMPANY_PREFIXES = (
    "sirketimiz",
    "firmamiz",
    "ortakligimiz",
    "isletmemiz",
    "istirakimiz",
)
_TRANSFER_STEMS = (
    "pay",
    "hisse",
    "varlik",
    "varlig",
    "isletme",
    "istirak",
    "ortaklik",
    "ortaklig",
    "sirket",
    "firma",
    "tesis",
)
_USAGE_STEMS = ("kullan", "tuket", "yak", "harca")
_PRODUCER_LINK_STEMS = (
    "uretic",
    "imalatc",
    "gelistiric",
    "tedarikc",
    "saglayic",
    "dagitic",
    "ureten",
    "uretm",
    "urettig",
    "ureteceg",
)
_CLAUSE_WORDS = {"ve", "ancak", "sonra", "ardindan", "ayrica", "fakat"}
_LEGAL_SIMPLE_MODIFIERS = {
    "yeniden",
    "tekrar",
    "ilk",
    "gecici",
    "sureli",
    "suresiz",
    "ayni",
    "mukerrer",
    "yenilenerek",
    "olarak",
    "bedelsiz",
    "bedelli",
    "karsiliksiz",
    "ucretsiz",
    "mevcut",
    "haliyle",
}
_LEGAL_FRAME_SUFFIXES = (
    "kapsaminda",
    "kapsamindaki",
    "uyarinca",
    "geregince",
    "dogrultusunda",
    "cercevesinde",
)
_RIGHT_TERMINATING_STEMS = (
    "bulun",
    "sahip",
    "sona",
    "erdi",
    "yenilen",
    "iptal",
    "fesih",
    "doldu",
    "kaldir",
    "kaybet",
    "devret",
)


def _mark(function: Any, *, original: Any | None = None) -> Any:
    function._phase10_round21_version = _HARDENING_VERSION
    function._phase10_round21_generation = INSTALL_GENERATION
    if original is not None:
        function._phase10_round21_original = original
        for round_no in (15, 16, 17, 18, 19, 20):
            for suffix in ("version", "generation"):
                name = f"_phase10_round{round_no}_{suffix}"
                if hasattr(original, name):
                    setattr(function, name, getattr(original, name))
    return function


def _is_installed(function: Any) -> bool:
    return (
        getattr(function, "_phase10_round21_version", None) == _HARDENING_VERSION
        and getattr(function, "_phase10_round21_generation", None)
        is INSTALL_GENERATION
    )


def install(service: Any) -> None:
    """Install Round 21 fixes idempotently after the Round 20 layer."""
    if (
        _is_installed(getattr(service, "_satin_alma_is_acquisition", None))
        and _is_installed(getattr(service, "_devralma_has_acquisition_context", None))
        and _is_installed(getattr(service, "_tesis_is_operational", None))
        and _is_installed(getattr(service, "_classify_event_fields", None))
    ):
        service._PHASE10_ROUND21_HARDENING_INSTALLED = _HARDENING_VERSION
        return

    previous_purchase = getattr(
        service._satin_alma_is_acquisition,
        "_phase10_round21_original",
        service._satin_alma_is_acquisition,
    )
    previous_devralma = getattr(
        service._devralma_has_acquisition_context,
        "_phase10_round21_original",
        service._devralma_has_acquisition_context,
    )
    previous_tesis = getattr(
        service._tesis_is_operational,
        "_phase10_round21_original",
        service._tesis_is_operational,
    )
    previous_classify = getattr(
        service._classify_event_fields,
        "_phase10_round21_original",
        service._classify_event_fields,
    )
    pre_round20_classify = getattr(
        previous_classify,
        "_phase10_round20_original",
        previous_classify,
    )

    def _tokens(text: str) -> list[str]:
        return service.re.findall(r"\w+", text)

    def _company_token(token: str) -> bool:
        return token.startswith(_COMPANY_PREFIXES)

    def _speaker_company(token: str) -> bool:
        return token.startswith(_SPEAKER_COMPANY_PREFIXES)

    def _company_locative(token: str) -> bool:
        return _company_token(token) and token.endswith(("de", "da", "te", "ta"))

    def _procurement_token(token: str) -> bool:
        return service._token_has_stem(token, service._PROCUREMENT_TARGET_STEMS)

    def _transfer_token(token: str) -> bool:
        return token.startswith(_TRANSFER_STEMS)

    def _usage_in(tokens: list[str]) -> bool:
        return any(item.startswith(_USAGE_STEMS) for item in tokens)

    def _producer_linked_company(tokens: list[str]) -> bool:
        """A procurement-looking noun can modify a later producer company."""
        for start, item in enumerate(tokens):
            if not _procurement_token(item):
                continue
            relation_seen = False
            for candidate in tokens[start + 1 :]:
                if candidate in _CLAUSE_WORDS or candidate.startswith(_USAGE_STEMS):
                    break
                if candidate.startswith(_PRODUCER_LINK_STEMS):
                    relation_seen = True
                    continue
                if relation_seen and _company_token(candidate):
                    return not _speaker_company(candidate) and not _company_locative(candidate)
        return False

    def _speaker_company_owns_relative_usage(tokens: list[str]) -> bool:
        """Do not turn a purchased commodity into M&A via our own company clause."""
        if not tokens or not _procurement_token(tokens[0]):
            return False
        for index, item in enumerate(tokens[1:], start=1):
            if item in _CLAUSE_WORDS:
                break
            if not _speaker_company(item):
                continue
            tail = tokens[index + 1 :]
            has_relation = any(
                candidate.startswith(_PRODUCER_LINK_STEMS) for candidate in tail
            )
            return has_relation and _usage_in(tail)
        return False

    def _object_like_target(tokens: list[str]) -> bool:
        for item in tokens:
            if not _transfer_token(item):
                continue
            if item in _BARE_COMPANY_FORMS or _speaker_company(item):
                continue
            if item.endswith(
                (
                    "i",
                    "u",
                    "yi",
                    "yu",
                    "ni",
                    "nu",
                    "lari",
                    "leri",
                    "larini",
                    "lerini",
                )
            ):
                return True
        return False

    def _after_has_explicit_target(tokens: list[str]) -> bool:
        for item in tokens:
            if item in _CLAUSE_WORDS:
                break
            if _transfer_token(item) and not _speaker_company(item) and not _company_locative(item):
                return True
            if _procurement_token(item):
                return True
        return False

    def _finite_bare_buyer_without_target(
        before: list[str],
        purchase_token: str,
        after: list[str],
    ) -> bool:
        finite = purchase_token.startswith(
            ("aldi", "alacak", "alacag", "aliyor", "alir", "almis")
        )
        relative = purchase_token.startswith("aldig") or (
            purchase_token.startswith("almis")
            and bool(after)
            and after[0].startswith("oldug")
        )
        if not finite or relative:
            return False
        if not any(item in _BARE_COMPANY_FORMS for item in before):
            return False
        if _object_like_target(before):
            return False
        return not _after_has_explicit_target(after)

    def _satin_alma_is_acquisition(text: str) -> bool:
        tokens = _tokens(text)
        occurrences = [
            index
            for index in range(len(tokens) - 1)
            if tokens[index] == "satin" and tokens[index + 1].startswith("al")
        ]
        if not occurrences:
            return previous_purchase(text)

        saw_explicit_non_acquisition = False
        for occurrence_no, index in enumerate(occurrences):
            next_index = (
                occurrences[occurrence_no + 1]
                if occurrence_no + 1 < len(occurrences)
                else len(tokens)
            )
            previous_end = occurrences[occurrence_no - 1] + 2 if occurrence_no else 0
            before = tokens[previous_end:index]
            purchase_token = tokens[index + 1]
            after = tokens[index + 2 : next_index]

            if _producer_linked_company(after):
                return True
            if _speaker_company_owns_relative_usage(after):
                saw_explicit_non_acquisition = True
                continue
            if _finite_bare_buyer_without_target(before, purchase_token, after):
                saw_explicit_non_acquisition = True
                continue

        if saw_explicit_non_acquisition:
            return False
        return previous_purchase(text)

    def _passive_completed_procurement(after: list[str]) -> bool:
        if _producer_linked_company(after):
            return False
        for index, item in enumerate(after):
            if item in _CLAUSE_WORDS:
                break
            if _transfer_token(item) and not _company_locative(item) and not _speaker_company(item):
                return False
            if not _procurement_token(item):
                continue
            tail = after[index + 1 :]
            if _usage_in(tail):
                # Singular and plural procurement objects are equally complete
                # when the remainder is a location/usage clause.
                return True
        return False

    def _devralma_has_acquisition_context(text: str) -> bool:
        tokens = _tokens(text)
        passive_count = 0
        saw_procurement = False
        for index, item in enumerate(tokens):
            if not item.startswith("devralin"):
                continue
            passive_count += 1
            after = tokens[index + 1 :]
            if _producer_linked_company(after):
                return True
            if _passive_completed_procurement(after):
                saw_procurement = True

        if passive_count == 1 and saw_procurement:
            return False
        return previous_devralma(text)

    def _is_property_right_noun(token: str) -> bool:
        if token.startswith(("hakkinda", "hakkimizda", "hakkinizda")):
            return False
        return token == "hak" or token.startswith(
            (
                "hakki",
                "hakkin",
                "hakka",
                "hakta",
                "haktan",
                "hakla",
                "hakkimiz",
                "hakkiniz",
            )
        )

    def _legal_framing_consumes(tokens: list[str]) -> bool:
        """Return true when intervening words are framing/modifiers, not a facility head."""
        index = 0
        while index < len(tokens):
            item = tokens[index]
            if item in _LEGAL_SIMPLE_MODIFIERS:
                index += 1
                continue
            if item.startswith(("bedelsiz", "bedelli", "karsiliksiz", "ucretsiz")):
                index += 1
                continue
            if item.startswith(_LEGAL_FRAME_SUFFIXES):
                index += 1
                continue
            if index + 1 < len(tokens) and tokens[index + 1].startswith(
                _LEGAL_FRAME_SUFFIXES
            ):
                # Productive framing: "anlaşma kapsamında", "karar uyarınca", etc.
                index += 2
                continue
            if item == "iliskin" and index + 1 < len(tokens) and tokens[index + 1] == "olarak":
                index += 2
                continue
            return False
        return True

    def _right_creation_occurrence(tokens: list[str], tesis_index: int) -> bool:
        for right_index in range(tesis_index - 1, -1, -1):
            item = tokens[right_index]
            if item in _CLAUSE_WORDS or item.startswith(_RIGHT_TERMINATING_STEMS):
                return False
            if item.startswith("tesis"):
                return False
            if not _is_property_right_noun(item):
                continue
            between = tokens[right_index + 1 : tesis_index]
            return _legal_framing_consumes(between)
        return False

    def _security_context_near(tokens: list[str], tesis_index: int) -> bool:
        start = max(0, tesis_index - 4)
        end = min(len(tokens), tesis_index + 5)
        return any(
            service._token_has_stem(item, service._LEGAL_TESIS_CONTEXT_STEMS)
            for item in tokens[start:end]
        )

    def _segment_tesis_kinds(segment: str) -> tuple[bool, bool]:
        tokens = _tokens(segment)
        has_legal = False
        has_physical = False
        for index, item in enumerate(tokens):
            if not item.startswith("tesis"):
                continue
            if _right_creation_occurrence(tokens, index) or _security_context_near(tokens, index):
                has_legal = True
            else:
                has_physical = True
        return has_legal, has_physical

    def _raw_segments(value: str) -> list[str]:
        return [
            service._normalize_event_text(part).strip()
            for part in service.re.split(r"[.!?;:\n]+", value)
            if service._normalize_event_text(part).strip()
        ]

    def _all_segments(subject: str, summary: str) -> list[str]:
        return _raw_segments(subject) + _raw_segments(summary)

    def _has_physical_tesis(subject: str, summary: str) -> bool:
        return any(_segment_tesis_kinds(segment)[1] for segment in _all_segments(subject, summary))

    def _contains_right_creation_segment(segment: str) -> bool:
        return _segment_tesis_kinds(segment)[0]

    def _neutralize_legal_price_in_field(value: str) -> str:
        parts = service.re.split(r"([.!?;:\n]+)", value)
        rewritten: list[str] = []
        for part in parts:
            normalized = service._normalize_event_text(part).strip()
            if normalized and _contains_right_creation_segment(normalized):
                part = service.re.sub(
                    r"(?<!\w)(?:bedelsiz|bedelli)\w*",
                    "bedel",
                    part,
                    flags=service.re.IGNORECASE,
                )
            rewritten.append(part)
        return "".join(rewritten)

    def _tesis_is_operational(text: str) -> bool:
        tokens = _tokens(text)
        positions = [
            index for index, item in enumerate(tokens) if item.startswith("tesis")
        ]
        if not positions:
            return previous_tesis(text)

        legal = {
            index
            for index in positions
            if _right_creation_occurrence(tokens, index)
            or _security_context_near(tokens, index)
        }
        if legal == set(positions):
            return False
        if any(index not in legal for index in positions):
            return True
        return previous_tesis(text)

    def _classify_event_fields(
        subject: str,
        summary: str,
        disclosure_type: str,
        is_corrective: bool,
    ):
        result = previous_classify(
            subject,
            summary,
            disclosure_type,
            is_corrective,
        )

        if result[0] == "capital":
            neutral_subject = _neutralize_legal_price_in_field(subject)
            neutral_summary = _neutralize_legal_price_in_field(summary)
            if neutral_subject != subject or neutral_summary != summary:
                # Bypass Round 20's disclosure-wide bedelli/bedelsiz stripping:
                # Round 21 has already neutralized only the legal-right clauses.
                result = pre_round20_classify(
                    neutral_subject,
                    neutral_summary,
                    disclosure_type,
                    is_corrective,
                )

        if result[1] < 80 and _has_physical_tesis(subject, summary):
            score = 85 if is_corrective else 80
            severity = "high" if score >= 85 else "medium"
            return "operations", score, severity
        return result

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
    service._classify_event_fields = _mark(
        _classify_event_fields,
        original=previous_classify,
    )
    service._PHASE10_ROUND21_HARDENING_INSTALLED = _HARDENING_VERSION
