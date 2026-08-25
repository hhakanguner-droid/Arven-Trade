"""Round 18 hardening for Phase 10 KAP semantics and poll capacity.

Round 18 closes the exact-head Codex findings from Round 17.  The main changes
are clause-aware purchase/takeover parsing, property-right creation syntax that
allows modifiers, aggregate capacity validation after all successful ticker
windows are refreshed, and installer generation markers that survive hot reloads
without accepting stale closures from an older module load.
"""

from __future__ import annotations

import copy
from typing import Any


_HARDENING_VERSION = "phase10-round18"
INSTALL_GENERATION = object()

_ACTIVE_PURCHASE_PREFIXES = (
    "aldi",
    "aldig",
    "alacag",
    "alacak",
    "aliyor",
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
_SECTOR_WORDS = ("elektrik", "enerji", "dogalgaz", "gaz")
_USAGE_VERB_STEMS = (
    "kullan",
    "tuket",
    "yak",
    "harca",
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
_TRANSFER_ADJUNCT_STEMS = (
    "adina",
    "namina",
    "hesabina",
    "icin",
    "uzerinden",
    "tarafindan",
    "tarafinca",
)
_PASSIVE_CLAUSE_VERB_STEMS = (
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
_RIGHT_CREATION_MODIFIERS = {
    "yeniden",
    "tekrar",
    "ilk",
    "gecici",
    "sureli",
    "suresiz",
    "ayni",
    "mukerrer",
    "yenilenerek",
}


def _mark(function: Any, *, original: Any | None = None) -> Any:
    function._phase10_round18_version = _HARDENING_VERSION
    function._phase10_round18_generation = INSTALL_GENERATION
    if original is not None:
        function._phase10_round18_original = original
    return function


def _is_installed(function: Any) -> bool:
    return (
        getattr(function, "_phase10_round18_version", None) == _HARDENING_VERSION
        and getattr(function, "_phase10_round18_generation", None)
        is INSTALL_GENERATION
    )


def install(service: Any) -> None:
    """Install Round 18 fixes idempotently after the Round 17 semantic layer."""
    if (
        _is_installed(getattr(service, "_satin_alma_is_acquisition", None))
        and _is_installed(getattr(service, "_devralma_has_acquisition_context", None))
        and _is_installed(getattr(service, "_tesis_is_operational", None))
        and _is_installed(getattr(service.KapWatchlistAlertService, "check_watchlist", None))
    ):
        service._PHASE10_ROUND18_HARDENING_INSTALLED = _HARDENING_VERSION
        return

    previous_purchase = getattr(
        service._satin_alma_is_acquisition,
        "_phase10_round18_original",
        service._satin_alma_is_acquisition,
    )
    previous_devralma = getattr(
        service._devralma_has_acquisition_context,
        "_phase10_round18_original",
        service._devralma_has_acquisition_context,
    )
    previous_tesis = getattr(
        service._tesis_is_operational,
        "_phase10_round18_original",
        service._tesis_is_operational,
    )

    current_check = getattr(service.KapWatchlistAlertService, "check_watchlist")
    round15_check = getattr(
        current_check,
        "_phase10_round17_original",
        getattr(
            current_check,
            "_phase10_round16_original",
            getattr(current_check, "_phase10_round15_original", current_check),
        ),
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

    def _purchase_occurrences(tokens: list[str]) -> list[int]:
        return [
            index
            for index in range(len(tokens) - 1)
            if tokens[index] == "satin" and tokens[index + 1].startswith("al")
        ]

    def _has_usage_verb(tokens: list[str]) -> bool:
        return any(item.startswith(_USAGE_VERB_STEMS) for item in tokens)

    def _purchase_clause_kind(after: list[str]) -> str | None:
        """Classify one post-purchase phrase without leaking into later clauses."""
        if not after:
            return None

        has_usage = _has_usage_verb(after)
        for index, item in enumerate(after):
            if item.startswith(_SECTOR_WORDS):
                tail = after[index + 1 :]
                company_positions = [
                    pos for pos, candidate in enumerate(tail) if _company_token(candidate)
                ]
                if company_positions:
                    # A company followed by its production facilities is still an
                    # acquisition target unless the phrase actually contains a
                    # usage/consumption verb ("... tesislerinde kullanılacaktır").
                    if has_usage:
                        return "procurement"
                    return "acquisition"
                if has_usage:
                    return "procurement"
                continue

            if _procurement_target_token(item):
                return "procurement"
            if _acquisition_target_token(item):
                return "acquisition"

            if item.startswith(_USAGE_VERB_STEMS):
                return "procurement"
        return None

    def _satin_alma_is_acquisition(text: str) -> bool:
        tokens = _tokens(text)
        occurrences = _purchase_occurrences(tokens)
        if not occurrences:
            return previous_purchase(text)

        saw_procurement = False
        for occurrence_no, index in enumerate(occurrences):
            next_index = (
                occurrences[occurrence_no + 1]
                if occurrence_no + 1 < len(occurrences)
                else len(tokens)
            )
            previous_index = (
                occurrences[occurrence_no - 1] + 2 if occurrence_no > 0 else 0
            )
            purchase_token = tokens[index + 1]
            before = tokens[previous_index:index]
            after = tokens[index + 2 : next_index]
            kind = _purchase_clause_kind(after)

            active_buyer = purchase_token.startswith(_ACTIVE_PURCHASE_PREFIXES) and any(
                _company_token(item) for item in before
            )
            passive = purchase_token.startswith("alin")

            if kind == "acquisition":
                return True
            if kind == "procurement" and (active_buyer or passive):
                saw_procurement = True
                continue

        # A procurement occurrence must not suppress a later acquisition, hence
        # the decision is made only after every purchase phrase has been scanned.
        if saw_procurement:
            return False
        return previous_purchase(text)

    def _transfer_target_token(token: str) -> bool:
        return token.startswith(_TRANSFER_TARGET_STEMS)

    def _target_is_adjunct(before: list[str], index: int) -> bool:
        following = before[index + 1 : index + 3]
        return any(item.startswith(_TRANSFER_ADJUNCT_STEMS) for item in following)

    def _is_board_decision_phrase(before: list[str], governance_index: int) -> bool:
        if not before[governance_index].startswith("yonetim"):
            return False
        following = before[governance_index + 1 : governance_index + 4]
        return bool(following) and following[0].startswith("kurul")

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
                # A real governance object (e.g. "iştirak yönetimini") owns entity
                # nouns before it. Only a non-adjunct transfer object after that
                # governance object can turn the phrase back into an acquisition.
                for index, item in enumerate(before):
                    if index <= last_governance:
                        continue
                    if _transfer_target_token(item) and not _target_is_adjunct(before, index):
                        return True
                saw_governance_object = True
            else:
                # Board-decision wording is an adjunct, not the object being taken
                # over. A target may naturally precede or follow that adjunct.
                for index, item in enumerate(before):
                    if _transfer_target_token(item) and not _target_is_adjunct(before, index):
                        return True

            if token.startswith("devralin"):
                # No arbitrary token cap: scan the full target phrase until a
                # competing clause verb begins.
                for item in tokens[verb_index + 1 :]:
                    if item.startswith("devral") or item == "satin":
                        break
                    if item.startswith(_PASSIVE_CLAUSE_VERB_STEMS):
                        break
                    if _transfer_target_token(item):
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

    def _right_governs_tesis(tokens: list[str], tesis_index: int) -> bool:
        # Allow productive modifiers such as "hakkının yeniden tesisi", but do
        # not let a remote right noun suppress a later physical facility such as
        # "kullanım hakkı bulunan maden tesisi".
        for right_index in range(tesis_index - 1, max(-1, tesis_index - 5), -1):
            token = tokens[right_index]
            if not _is_property_right_noun(token):
                continue
            between = tokens[right_index + 1 : tesis_index]
            return all(item in _RIGHT_CREATION_MODIFIERS for item in between)
        return False

    def _tesis_is_operational(text: str) -> bool:
        tokens = _tokens(text)
        tesis_positions = [
            index for index, token in enumerate(tokens) if token.startswith("tesis")
        ]
        if not tesis_positions:
            return previous_tesis(text)

        legal_positions = {
            index for index in tesis_positions if _right_governs_tesis(tokens, index)
        }
        if legal_positions == set(tesis_positions):
            return False
        return previous_tesis(text)

    def _capacity_path(state: Any):
        # Reuse the Round 17 sidecar schema so upgrades preserve current windows.
        return state.path.with_name(f"{state.path.name}.round17-capacity.json")

    def _load_window_map(state: Any) -> dict[str, dict[str, Any]]:
        payload = service._read_json_object(_capacity_path(state))
        if payload is None:
            return {}
        if payload.get("version") != 1 or not isinstance(
            payload.get("ticker_windows"), dict
        ):
            raise ValueError(f"invalid alert capacity state: {_capacity_path(state)}")

        result: dict[str, dict[str, Any]] = {}
        for ticker, raw in payload["ticker_windows"].items():
            if not service.is_bist_yahoo_symbol(ticker) or not isinstance(raw, dict):
                raise ValueError(f"invalid alert capacity ticker: {ticker!r}")
            company_key = raw.get("company_key")
            reachable_count = raw.get("reachable_count")
            if not isinstance(company_key, str) or not company_key:
                raise ValueError(f"invalid alert capacity company for {ticker!r}")
            if not isinstance(reachable_count, int) or reachable_count < 0:
                raise ValueError(f"invalid alert capacity value for {ticker!r}")
            result[service.normalize_bist_yahoo_symbol(ticker)] = {
                "company_key": company_key,
                "reachable_count": reachable_count,
            }
        return result

    def _required_window_capacity(windows: dict[str, dict[str, Any]]) -> int:
        company_caps: dict[str, int] = {}
        for item in windows.values():
            company_key = str(item["company_key"])
            count = int(item["reachable_count"])
            company_caps[company_key] = max(company_caps.get(company_key, 0), count)
        return sum(company_caps.values())

    def _company_key(result: Any, ticker: str) -> str:
        disclosures = tuple(getattr(result, "disclosures", ()) or ())
        if disclosures:
            company = service._normalize_event_text(str(disclosures[0].company)).strip()
            if company:
                return f"company:{company}"
        kap_ticker = getattr(result, "kap_ticker", None)
        if kap_ticker:
            return f"kap:{str(kap_ticker).upper()}"
        return f"ticker:{service.normalize_bist_yahoo_symbol(ticker)}"

    def _reachable_count(result: Any) -> int:
        disclosures = tuple(getattr(result, "disclosures", ()) or ())
        raw_total = getattr(result, "total_found", 0)
        total = int(raw_total) if isinstance(raw_total, int) else 0
        return max(total, len(disclosures), 0)

    def _register_tracked_tickers(
        state: Any,
        tickers: Any,
        *,
        active_tickers: tuple[str, ...] | None,
    ) -> None:
        canonical = service.WatchlistStore._validated_unique(tickers, strict=True)
        active = None if active_tickers is None else set(active_tickers)
        payload = state._load_unlocked()
        tracked = list(payload["tracked_tickers"])
        if active is not None:
            tracked = [ticker for ticker in tracked if ticker in active]
        for ticker in canonical:
            if ticker not in tracked:
                tracked.append(ticker)
        if tracked != payload["tracked_tickers"]:
            payload["tracked_tickers"] = tracked
            state._save_unlocked(payload)

    def _commit_capacity_snapshot(
        state: Any,
        *,
        successful_tickers: Any,
        active_tickers: tuple[str, ...] | None,
        fresh_windows: dict[str, dict[str, Any]],
    ) -> None:
        active = None if active_tickers is None else set(active_tickers)
        with state.locked():
            windows = _load_window_map(state)
            if active is not None:
                windows = {key: value for key, value in windows.items() if key in active}

            # Refresh every successful ticker first, then validate the aggregate.
            # This prevents the first ticker from being rejected against stale
            # peaks that a later ticker in the same successful poll would release.
            windows.update(fresh_windows)
            _register_tracked_tickers(
                state,
                successful_tickers,
                active_tickers=active_tickers,
            )
            required = _required_window_capacity(windows)
            service._atomic_write_json(
                _capacity_path(state),
                {"version": 1, "ticker_windows": windows},
            )
            if state.seen_limit < required:
                raise ValueError(
                    "alert_seen_limit must cover every unique disclosure reachable "
                    "through unseen-first polling in the active KAP lookback window"
                )

    class _Round18StateProxy:
        def __init__(
            self,
            wrapped: Any,
            *,
            active_tickers: tuple[str, ...] | None,
            fresh_windows: dict[str, dict[str, Any]],
        ) -> None:
            self._wrapped = wrapped
            self._active_tickers = active_tickers
            self._fresh_windows = fresh_windows

        def __getattr__(self, name: str) -> Any:
            return getattr(self._wrapped, name)

        def ensure_capacity(
            self,
            tickers: Any,
            per_ticker_cap: int,
            *,
            active_tickers: Any = None,
        ) -> None:
            del per_ticker_cap, active_tickers
            _commit_capacity_snapshot(
                self._wrapped,
                successful_tickers=tickers,
                active_tickers=self._active_tickers,
                fresh_windows=self._fresh_windows,
            )

    class _Round18KapProxy:
        def __init__(
            self,
            wrapped: Any,
            *,
            fresh_windows: dict[str, dict[str, Any]],
        ) -> None:
            self._wrapped = wrapped
            self._fresh_windows = fresh_windows

        def __getattr__(self, name: str) -> Any:
            return getattr(self._wrapped, name)

        def get_disclosures(self, *args: Any, **kwargs: Any):
            result = self._wrapped.get_disclosures(*args, **kwargs)
            if result.available:
                ticker = kwargs.get("ticker")
                if ticker is None and args:
                    ticker = args[0]
                canonical = service.normalize_bist_yahoo_symbol(str(ticker))
                self._fresh_windows[canonical] = {
                    "company_key": _company_key(result, canonical),
                    "reachable_count": _reachable_count(result),
                }
            return result

    def _check_watchlist(self: Any, tickers=None, *, now=None):
        if not self.enabled:
            return round15_check(self, tickers, now=now)

        if tickers is None:
            active_tickers = tuple(self.watchlist.list())
            requested = active_tickers
        else:
            active_tickers = None
            requested = tuple(tickers)

        fresh_windows: dict[str, dict[str, Any]] = {}
        shadow = copy.copy(self)
        shadow.state = _Round18StateProxy(
            self.state,
            active_tickers=active_tickers,
            fresh_windows=fresh_windows,
        )
        shadow.kap_service = _Round18KapProxy(
            self.kap_service,
            fresh_windows=fresh_windows,
        )
        return round15_check(shadow, requested if tickers is not None else None, now=now)

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
        original=round15_check,
    )
    service._PHASE10_ROUND18_HARDENING_INSTALLED = _HARDENING_VERSION
