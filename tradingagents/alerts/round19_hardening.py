"""Round 19 hardening for Phase 10 KAP semantics and stable polling snapshots.

Round 19 removes the remaining fixed-distance/whitelist assumptions reported on
the Round 18 exact head.  It keeps the public alert API unchanged while making
purchase/takeover object scans clause-aware, property-right creation syntax
productive, and full-watchlist polling use one immutable watchlist snapshot.
"""

from __future__ import annotations

import copy
from typing import Any


_HARDENING_VERSION = "phase10-round19"
INSTALL_GENERATION = object()

_ACTIVE_FINITE_PURCHASE_PREFIXES = (
    "aldi",
    "alacak",
    "alacag",
    "aliyor",
    "alir",
    "almis",
)
_ACTIVE_RELATIVE_PURCHASE_PREFIXES = (
    "aldig",
    "almis",
)
_COMPANY_PREFIXES = (
    "sirket",
    "firma",
    "ortaklik",
    "ortaklig",
    "isletme",
    "istirak",
)
_TRANSFER_TARGET_STEMS = (
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
_ADJUNCT_MARKERS = (
    "adina",
    "namina",
    "hesabina",
    "icin",
    "uzerinden",
    "tarafindan",
    "tarafinca",
)
_USAGE_VERB_STEMS = (
    "kullan",
    "tuket",
    "yak",
    "harca",
)
_RELATIVE_PRODUCTION_STEMS = (
    "urettig",
    "uretilen",
    "ureten",
    "sattig",
    "sagladig",
    "tedarik",
)
_PHYSICAL_LOCATION_STEMS = (
    "tesis",
    "fabrika",
    "santral",
    "depo",
    "isletme",
)
_RIGHT_CLAUSE_BLOCKERS = (
    "bulun",
    "sahip",
    "kapsam",
    "konu",
    "iliskin",
    "mevcut",
)
_PASSIVE_OBJECT_BOUNDARY_STEMS = (
    "kullan",
    "tuket",
    "uretil",
    "acikla",
    "bildir",
    "duyur",
    "tamamla",
    "gerceklestir",
    "planla",
)


def _mark(function: Any, *, original: Any | None = None) -> Any:
    function._phase10_round19_version = _HARDENING_VERSION
    function._phase10_round19_generation = INSTALL_GENERATION
    if original is not None:
        function._phase10_round19_original = original
        for name in (
            "_phase10_round18_version",
            "_phase10_round18_generation",
        ):
            if hasattr(original, name):
                setattr(function, name, getattr(original, name))
    return function


def _is_installed(function: Any) -> bool:
    return (
        getattr(function, "_phase10_round19_version", None) == _HARDENING_VERSION
        and getattr(function, "_phase10_round19_generation", None)
        is INSTALL_GENERATION
    )


def install(service: Any) -> None:
    """Install Round 19 fixes idempotently after the Round 18 layer."""
    if (
        _is_installed(getattr(service, "_satin_alma_is_acquisition", None))
        and _is_installed(getattr(service, "_devralma_has_acquisition_context", None))
        and _is_installed(getattr(service, "_tesis_is_operational", None))
        and _is_installed(
            getattr(service.KapWatchlistAlertService, "check_watchlist", None)
        )
    ):
        service._PHASE10_ROUND19_HARDENING_INSTALLED = _HARDENING_VERSION
        return

    previous_purchase = getattr(
        service._satin_alma_is_acquisition,
        "_phase10_round19_original",
        service._satin_alma_is_acquisition,
    )
    previous_devralma = getattr(
        service._devralma_has_acquisition_context,
        "_phase10_round19_original",
        service._devralma_has_acquisition_context,
    )
    previous_tesis = getattr(
        service._tesis_is_operational,
        "_phase10_round19_original",
        service._tesis_is_operational,
    )
    previous_check = getattr(
        service.KapWatchlistAlertService.check_watchlist,
        "_phase10_round19_original",
        service.KapWatchlistAlertService.check_watchlist,
    )

    def _tokens(text: str) -> list[str]:
        return service.re.findall(r"\w+", text)

    def _company_token(token: str) -> bool:
        return token.startswith(_COMPANY_PREFIXES)

    def _acquisition_target_token(token: str) -> bool:
        if token in service._BARE_COMPANY_TOKENS or _company_token(token):
            return True
        if token.startswith(("varlig", "ortaklig")):
            return True
        return service._token_has_stem(token, service._ACQUISITION_TARGET_STEMS)

    def _procurement_target_token(token: str) -> bool:
        return service._token_has_stem(token, service._PROCUREMENT_TARGET_STEMS)

    def _transfer_target_token(token: str) -> bool:
        return token.startswith(_TRANSFER_TARGET_STEMS)

    def _is_plural_or_inflected_procurement_object(token: str) -> bool:
        return (
            token.endswith(("lar", "ler", "lari", "leri", "larini", "lerini"))
            or token.startswith(("makineler", "ekipmanlar", "malzemeler"))
        )

    def _contains_usage_pattern(tokens: list[str], company_index: int) -> bool:
        tail = tokens[company_index + 1 :]
        if any(item.startswith(_RELATIVE_PRODUCTION_STEMS) for item in tail[:4]):
            return False

        usage_positions = [
            index for index, item in enumerate(tail) if item.startswith(_USAGE_VERB_STEMS)
        ]
        if not usage_positions:
            return False
        first_usage = usage_positions[0]
        before_usage = tail[:first_usage]
        return any(item.startswith(_PHYSICAL_LOCATION_STEMS) for item in before_usage)

    def _post_purchase_kind(after: list[str]) -> str | None:
        first_procurement: tuple[int, str] | None = None

        for index, item in enumerate(after):
            if item == "satin" or item.startswith("devral"):
                break
            if item.startswith(_USAGE_VERB_STEMS):
                return "procurement"

            if _acquisition_target_token(item):
                if _company_token(item) and _contains_usage_pattern(after, index):
                    return "procurement"
                return "acquisition"

            if _procurement_target_token(item) and first_procurement is None:
                first_procurement = (index, item)
                if _is_plural_or_inflected_procurement_object(item):
                    return "procurement"

        if first_procurement is not None:
            return "procurement"
        return None

    def _clause_before_purchase(
        tokens: list[str],
        occurrence_index: int,
        previous_occurrence_end: int,
    ) -> list[str]:
        before = tokens[previous_occurrence_end:occurrence_index]
        boundary = -1
        for index, item in enumerate(before):
            if item in {"ve", "ancak", "sonra", "ardindan", "ayrica"}:
                boundary = index
        return before[boundary + 1 :]

    def _pre_purchase_has_object(
        before: list[str],
        purchase_token: str,
        after: list[str],
    ) -> bool:
        if not before:
            return False

        relative_form = purchase_token.startswith("aldig") or (
            purchase_token.startswith("almis")
            and bool(after)
            and after[0].startswith("oldug")
        )
        if relative_form:
            return False

        if not purchase_token.startswith(_ACTIVE_FINITE_PURCHASE_PREFIXES):
            return False

        for item in reversed(before):
            if item in {"ve", "ancak", "sonra", "ayrica"}:
                break
            if _acquisition_target_token(item):
                return True
            if _procurement_target_token(item):
                return False
        return False

    def _satin_alma_is_acquisition(text: str) -> bool:
        tokens = _tokens(text)
        occurrences = [
            index
            for index in range(len(tokens) - 1)
            if tokens[index] == "satin" and tokens[index + 1].startswith("al")
        ]
        if not occurrences:
            return previous_purchase(text)

        saw_procurement = False
        for occurrence_no, index in enumerate(occurrences):
            next_index = (
                occurrences[occurrence_no + 1]
                if occurrence_no + 1 < len(occurrences)
                else len(tokens)
            )
            previous_end = (
                occurrences[occurrence_no - 1] + 2 if occurrence_no > 0 else 0
            )
            purchase_token = tokens[index + 1]
            before = _clause_before_purchase(tokens, index, previous_end)
            after = tokens[index + 2 : next_index]

            if _pre_purchase_has_object(before, purchase_token, after):
                return True

            kind = _post_purchase_kind(after)
            if kind == "acquisition":
                return True
            if kind == "procurement":
                saw_procurement = True
                continue

        if saw_procurement:
            return False
        return previous_purchase(text)

    def _target_is_adjunct(before: list[str], index: int) -> bool:
        return (
            index + 1 < len(before)
            and before[index + 1].startswith(_ADJUNCT_MARKERS)
        )

    def _is_board_decision_phrase(before: list[str], governance_index: int) -> bool:
        if not before[governance_index].startswith("yonetim"):
            return False
        tail = before[governance_index + 1 : governance_index + 6]
        if not tail or not tail[0].startswith("kurul"):
            return False
        return any(item.startswith("karar") for item in tail[1:])

    def _passive_takeover_target(after: list[str]) -> bool:
        for item in after:
            if item.startswith("devral") or item == "satin":
                break
            if item.startswith(_PASSIVE_OBJECT_BOUNDARY_STEMS):
                break

            if _transfer_target_token(item):
                return True

            if _procurement_target_token(item):
                if _is_plural_or_inflected_procurement_object(item):
                    return False
        return False

    def _devralma_has_acquisition_context(text: str) -> bool:
        tokens = _tokens(text)
        saw_governance_object = False

        for verb_index, token in enumerate(tokens):
            if not token.startswith("devral"):
                continue

            before = tokens[:verb_index]
            governance_positions = [
                index
                for index, item in enumerate(before)
                if service._token_has_stem(item, service._GOVERNANCE_TRANSFER_STEMS)
                and not _is_board_decision_phrase(before, index)
            ]
            last_governance = governance_positions[-1] if governance_positions else -1

            if governance_positions:
                for index, item in enumerate(before):
                    if index <= last_governance:
                        continue
                    if _transfer_target_token(item) and not _target_is_adjunct(
                        before, index
                    ):
                        return True
                saw_governance_object = True
            else:
                for index, item in enumerate(before):
                    if _transfer_target_token(item) and not _target_is_adjunct(
                        before, index
                    ):
                        return True

            if token.startswith("devralin") and _passive_takeover_target(
                tokens[verb_index + 1 :]
            ):
                return True

        if saw_governance_object:
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
            if item.startswith(_RIGHT_CLAUSE_BLOCKERS):
                return False
            if item.startswith(("tesis", "fabrika", "maden", "santral")):
                return False
            if _is_property_right_noun(item):
                return True
            if item in {"ve", "ancak", "sonra", "ardindan"}:
                return False
        return False

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
        return previous_tesis(text)

    class _SnapshotWatchlist:
        def __init__(self, wrapped: Any, snapshot: tuple[str, ...]) -> None:
            self._wrapped = wrapped
            self._snapshot = snapshot

        def __getattr__(self, name: str) -> Any:
            return getattr(self._wrapped, name)

        def list(self):
            return self._snapshot

    def _check_watchlist(self: Any, tickers=None, *, now=None):
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
    service.KapWatchlistAlertService.check_watchlist = _mark(
        _check_watchlist,
        original=previous_check,
    )
    service._PHASE10_ROUND19_HARDENING_INSTALLED = _HARDENING_VERSION
