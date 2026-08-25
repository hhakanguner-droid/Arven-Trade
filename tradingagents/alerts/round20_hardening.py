"""Round 20 hardening for Phase 10 KAP semantics and reload stability.

Round 20 closes the exact-head Codex findings from Round 19 without adding
another fixed token cap. It adds targeted grammatical boundaries for purchase
and takeover objects, productive property-right creation handling, disabled
service short-circuiting, and latest-chain routing for reloaded older installers.
"""

from __future__ import annotations

import copy
from typing import Any

_HARDENING_VERSION = "phase10-round20"
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
_PRODUCER_RELATION_STEMS = (
    "uretic",
    "imalatc",
    "gelistiric",
    "tedarikc",
    "saglayic",
    "dagitic",
)
_RELATIVE_PRODUCTION_STEMS = (
    "urettig",
    "uretm",
    "ureten",
    "ureteceg",
    "sattig",
    "sagladig",
)
_RIGHT_PREDICATE_BOUNDARIES = (
    "sona",
    "erdi",
    "bit",
    "iptal",
    "fesih",
    "doldu",
    "kaldir",
    "kaybet",
    "devret",
    "sahip",
    "bulun",
)
_RIGHT_PHYSICAL_BOUNDARIES = (
    "maden",
    "fabrika",
    "santral",
    "depo",
    "yapi",
    "bina",
)
_CLAUSE_BOUNDARIES = {"ve", "ancak", "sonra", "ardindan", "ayrica", "fakat"}


def _mark(function: Any, *, original: Any | None = None) -> Any:
    function._phase10_round20_version = _HARDENING_VERSION
    function._phase10_round20_generation = INSTALL_GENERATION
    if original is not None:
        function._phase10_round20_original = original
        for round_no in (15, 16, 17, 18, 19):
            for suffix in ("version", "generation"):
                name = f"_phase10_round{round_no}_{suffix}"
                if hasattr(original, name):
                    setattr(function, name, getattr(original, name))
    return function


def _is_installed(function: Any) -> bool:
    return (
        getattr(function, "_phase10_round20_version", None) == _HARDENING_VERSION
        and getattr(function, "_phase10_round20_generation", None)
        is INSTALL_GENERATION
    )


def install(service: Any) -> None:
    """Install Round 20 fixes idempotently after the Round 19 layer."""
    if (
        _is_installed(getattr(service, "_satin_alma_is_acquisition", None))
        and _is_installed(getattr(service, "_devralma_has_acquisition_context", None))
        and _is_installed(getattr(service, "_tesis_is_operational", None))
        and _is_installed(getattr(service, "_classify_event_fields", None))
        and _is_installed(
            getattr(service.KapWatchlistAlertService, "check_watchlist", None)
        )
    ):
        service._PHASE10_ROUND20_HARDENING_INSTALLED = _HARDENING_VERSION
        return

    previous_purchase = getattr(
        service._satin_alma_is_acquisition,
        "_phase10_round20_original",
        service._satin_alma_is_acquisition,
    )
    previous_devralma = getattr(
        service._devralma_has_acquisition_context,
        "_phase10_round20_original",
        service._devralma_has_acquisition_context,
    )
    previous_tesis = getattr(
        service._tesis_is_operational,
        "_phase10_round20_original",
        service._tesis_is_operational,
    )
    previous_classify = getattr(
        service._classify_event_fields,
        "_phase10_round20_original",
        service._classify_event_fields,
    )
    previous_check = getattr(
        service.KapWatchlistAlertService.check_watchlist,
        "_phase10_round20_original",
        service.KapWatchlistAlertService.check_watchlist,
    )
    disabled_check = getattr(
        previous_check,
        "_phase10_round19_original",
        previous_check,
    )

    def _tokens(text: str) -> list[str]:
        return service.re.findall(r"\w+", text)

    def _company_token(token: str) -> bool:
        return token.startswith(_COMPANY_PREFIXES)

    def _company_locative(token: str) -> bool:
        return _company_token(token) and token.endswith(("de", "da", "te", "ta"))

    def _procurement_token(token: str) -> bool:
        return service._token_has_stem(token, service._PROCUREMENT_TARGET_STEMS)

    def _transfer_token(token: str) -> bool:
        return token.startswith(_TRANSFER_STEMS)

    def _usage_after(tokens: list[str], index: int) -> bool:
        return any(item.startswith(_USAGE_STEMS) for item in tokens[index + 1 :])

    def _producer_company_target(tokens: list[str]) -> bool:
        for index, item in enumerate(tokens):
            if not _procurement_token(item):
                continue
            relation = None
            for pos in range(index + 1, len(tokens)):
                candidate = tokens[pos]
                if candidate in _CLAUSE_BOUNDARIES or candidate.startswith(_USAGE_STEMS):
                    break
                if candidate.startswith(_PRODUCER_RELATION_STEMS):
                    relation = pos
                    continue
                if (
                    relation is not None
                    and pos > relation
                    and _company_token(candidate)
                    and not _company_locative(candidate)
                ):
                    return True
        return False

    def _relative_company_target(tokens: list[str]) -> bool:
        for index, item in enumerate(tokens):
            if not _company_token(item) or _company_locative(item):
                continue
            tail = tokens[index + 1 :]
            relation_positions = [
                pos
                for pos, candidate in enumerate(tail)
                if candidate.startswith(_RELATIVE_PRODUCTION_STEMS)
            ]
            if not relation_positions:
                continue
            relation_index = relation_positions[0]
            if any(
                candidate.startswith(_USAGE_STEMS)
                for candidate in tail[relation_index + 1 :]
            ):
                return True
        return False

    def _locative_procurement_usage(tokens: list[str]) -> bool:
        procurement_positions = [
            index for index, item in enumerate(tokens) if _procurement_token(item)
        ]
        if not procurement_positions:
            return False
        first_procurement = procurement_positions[0]
        for index in range(first_procurement + 1, len(tokens)):
            item = tokens[index]
            if item in _CLAUSE_BOUNDARIES:
                break
            if _company_locative(item) and _usage_after(tokens, index):
                return True
        return False

    def _object_like_preverbal_target(tokens: list[str]) -> bool:
        for item in tokens:
            if not _transfer_token(item):
                continue
            if item in _BARE_COMPANY_FORMS:
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

    def _bare_company_buyer(tokens: list[str]) -> bool:
        return any(item in _BARE_COMPANY_FORMS for item in tokens)

    def _satin_alma_is_acquisition(text: str) -> bool:
        tokens = _tokens(text)
        occurrences = [
            index
            for index in range(len(tokens) - 1)
            if tokens[index] == "satin" and tokens[index + 1].startswith("al")
        ]
        if not occurrences:
            return previous_purchase(text)

        if len(occurrences) == 1:
            index = occurrences[0]
            purchase_token = tokens[index + 1]
            before = tokens[:index]
            after = tokens[index + 2 :]

            if _producer_company_target(after):
                return True
            if _relative_company_target(after):
                return True
            if _locative_procurement_usage(after):
                return False

            relative_form = purchase_token.startswith("aldig") or (
                purchase_token.startswith("almis")
                and bool(after)
                and after[0].startswith("oldug")
            )
            finite_form = purchase_token.startswith(
                ("aldi", "alacak", "alacag", "aliyor", "alir", "almis")
            )
            if (
                finite_form
                and not relative_form
                and not after
                and _bare_company_buyer(before)
                and not _object_like_preverbal_target(before)
            ):
                return False

        return previous_purchase(text)

    def _passive_procurement_object(after: list[str]) -> bool:
        if _producer_company_target(after):
            return False
        for item in after:
            if item in _CLAUSE_BOUNDARIES or item.startswith(_USAGE_STEMS):
                break
            if _transfer_token(item) and not _company_locative(item):
                return False
            if _procurement_token(item):
                if item.endswith(
                    ("lar", "ler", "lari", "leri", "larini", "lerini")
                ) or item.startswith(("makineler", "ekipmanlar", "malzemeler")):
                    return True
        return False

    def _devralma_has_acquisition_context(text: str) -> bool:
        tokens = _tokens(text)
        saw_passive_procurement = False
        passive_occurrences = 0
        for index, item in enumerate(tokens):
            if not item.startswith("devralin"):
                continue
            passive_occurrences += 1
            after = tokens[index + 1 :]
            if _producer_company_target(after):
                return True
            if _passive_procurement_object(after):
                saw_passive_procurement = True

        if passive_occurrences == 1 and saw_passive_procurement:
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

    def _right_creation_occurrence(tokens: list[str], tesis_index: int) -> bool:
        for index in range(tesis_index - 1, -1, -1):
            item = tokens[index]
            if item in _CLAUSE_BOUNDARIES:
                return False
            if item.startswith(_RIGHT_PREDICATE_BOUNDARIES):
                return False
            if item.startswith(_RIGHT_PHYSICAL_BOUNDARIES):
                return False
            if item.startswith("tesis"):
                return False
            if _is_property_right_noun(item):
                return True
        return False

    def _security_context_near(tokens: list[str], tesis_index: int) -> bool:
        start = max(0, tesis_index - 4)
        end = min(len(tokens), tesis_index + 5)
        return any(
            service._token_has_stem(item, service._LEGAL_TESIS_CONTEXT_STEMS)
            for item in tokens[start:end]
        )

    def _tesis_is_operational(text: str) -> bool:
        tokens = _tokens(text)
        positions = [
            index for index, item in enumerate(tokens) if item.startswith("tesis")
        ]
        if not positions:
            return previous_tesis(text)

        legal = {
            index for index in positions if _right_creation_occurrence(tokens, index)
        }
        if legal == set(positions):
            return False

        has_right = any(_is_property_right_noun(item) for item in tokens)
        if has_right:
            non_legal = [index for index in positions if index not in legal]
            if non_legal and not all(
                _security_context_near(tokens, index) for index in non_legal
            ):
                return True

        return previous_tesis(text)

    def _raw_segments(subject: str, summary: str) -> list[str]:
        segments: list[str] = []
        for raw in (subject, summary):
            for part in service.re.split(r"[.!?;:\n]+", raw):
                normalized = service._normalize_event_text(part).strip()
                if normalized:
                    segments.append(normalized)
        return segments

    def _contains_right_creation(subject: str, summary: str) -> bool:
        for segment in _raw_segments(subject, summary):
            tokens = _tokens(segment)
            for index, item in enumerate(tokens):
                if item.startswith("tesis") and _right_creation_occurrence(tokens, index):
                    return True
        return False

    def _explicit_capital_context(subject: str, summary: str) -> bool:
        normalized = service._normalize_event_text(f"{subject} {summary}")
        return "sermaye" in normalized and (
            "artir" in normalized or "azalt" in normalized
        )

    def _strip_legal_price_modifiers(value: str) -> str:
        return service.re.sub(
            r"(?<!\w)(?:bedelsiz|bedelli)\w*",
            "bedel",
            value,
            flags=service.re.IGNORECASE,
        )

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
        if (
            result[0] == "capital"
            and _contains_right_creation(subject, summary)
            and not _explicit_capital_context(subject, summary)
        ):
            return previous_classify(
                _strip_legal_price_modifiers(subject),
                _strip_legal_price_modifiers(summary),
                disclosure_type,
                is_corrective,
            )
        return result

    class _SnapshotWatchlist:
        def __init__(self, wrapped: Any, snapshot: tuple[str, ...]) -> None:
            self._wrapped = wrapped
            self._snapshot = snapshot

        def __getattr__(self, name: str) -> Any:
            return getattr(self._wrapped, name)

        def list(self):
            return self._snapshot

    def _check_watchlist(self: Any, tickers=None, *, now=None):
        if not self.enabled:
            return disabled_check(self, tickers, now=now)
        if tickers is not None:
            return previous_check(self, tickers, now=now)

        requested = tuple(self.watchlist.list())
        shadow = copy.copy(self)
        shadow.watchlist = _SnapshotWatchlist(self.watchlist, requested)
        return previous_check(shadow, None, now=now)

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
    service.KapWatchlistAlertService.check_watchlist = _mark(
        _check_watchlist,
        original=previous_check,
    )
    service._PHASE10_ROUND20_HARDENING_INSTALLED = _HARDENING_VERSION
