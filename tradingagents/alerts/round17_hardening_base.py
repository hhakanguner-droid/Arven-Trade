"""Round 17 hardening for Phase 10 KAP semantics and retention capacity.

Round 17 closes the exact-head Codex findings from Round 16.  It keeps the
public alert API unchanged while making capacity reflect the current lookback
window and company-level KAP identity rather than historical per-ticker peaks.
"""

from __future__ import annotations

import copy
from typing import Any


_HARDENING_VERSION = "phase10-round17"
_ACTIVE_PURCHASE_PREFIXES = (
    "aldi",
    "aldig",
    "alacag",
    "alacak",
    "aliyor",
)
_COMPANY_PREFIXES = (
    "sirket",
    "firma",
    "ortaklik",
    "isletme",
    "istirak",
)
_COMPANY_POSSESSOR_PREFIXES = (
    "sirketin",
    "sirketimizin",
    "sirketinizin",
    "firmanin",
    "firmamizin",
    "firmanizin",
    "ortakligin",
    "ortakligimizin",
    "isletmenin",
    "isletmemizin",
)
_SECTOR_WORDS = ("elektrik", "enerji", "dogalgaz", "gaz")
_USAGE_CONTEXT_STEMS = (
    "tesis",
    "fabrika",
    "uretim",
    "kullan",
    "tuket",
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
_DEBT_STEMS = (
    "tahvil",
    "bono",
    "borc",
    "borclanma",
    "kredi",
    "finansman",
    "odeme",
    "taksit",
    "alacak",
)


def _mark(function: Any, *, original: Any | None = None) -> Any:
    function._phase10_round17_version = _HARDENING_VERSION
    if original is not None:
        function._phase10_round17_original = original
    return function


def _is_installed(function: Any) -> bool:
    return getattr(function, "_phase10_round17_version", None) == _HARDENING_VERSION


def install(service: Any) -> None:
    """Install Round 17 fixes idempotently after the Round 16 layer."""
    if (
        _is_installed(getattr(service, "_satin_alma_is_acquisition", None))
        and _is_installed(getattr(service, "_devralma_has_acquisition_context", None))
        and _is_installed(getattr(service, "_tesis_is_operational", None))
        and _is_installed(getattr(service, "_classify_event_fields", None))
        and _is_installed(getattr(service.KapWatchlistAlertService, "check_watchlist", None))
    ):
        service._PHASE10_ROUND17_HARDENING_INSTALLED = _HARDENING_VERSION
        return

    previous_purchase = getattr(
        service._satin_alma_is_acquisition,
        "_phase10_round17_original",
        service._satin_alma_is_acquisition,
    )
    previous_devralma = getattr(
        service._devralma_has_acquisition_context,
        "_phase10_round17_original",
        service._devralma_has_acquisition_context,
    )
    previous_tesis = getattr(
        service._tesis_is_operational,
        "_phase10_round17_original",
        service._tesis_is_operational,
    )
    round15_tesis = getattr(
        previous_tesis,
        "_phase10_round16_original",
        previous_tesis,
    )
    previous_classify = getattr(
        service._classify_event_fields,
        "_phase10_round17_original",
        service._classify_event_fields,
    )

    current_check = getattr(service.KapWatchlistAlertService, "check_watchlist")
    round15_check = getattr(
        current_check,
        "_phase10_round17_original",
        getattr(current_check, "_phase10_round16_original", current_check),
    )

    def _tokens(text: str) -> list[str]:
        return service.re.findall(r"\w+", text)

    def _company_token(token: str) -> bool:
        return token.startswith(_COMPANY_PREFIXES)

    def _company_possessor(token: str) -> bool:
        return token.startswith(_COMPANY_POSSESSOR_PREFIXES)

    def _acquisition_target_token(token: str) -> bool:
        if token in service._BARE_COMPANY_TOKENS or _company_token(token):
            return True
        if token.startswith(("varlig", "ortaklig")):
            return True
        return service._token_has_stem(token, service._ACQUISITION_TARGET_STEMS)

    def _procurement_target_token(token: str) -> bool:
        return service._token_has_stem(token, service._PROCUREMENT_TARGET_STEMS)

    def _sector_is_usage_object(after: list[str], offset: int) -> bool:
        following = after[offset + 1 : offset + 7]
        if not following:
            return True

        for index, item in enumerate(following):
            if not _company_possessor(item):
                continue
            tail = following[index + 1 :]
            if any(candidate.startswith(_USAGE_CONTEXT_STEMS) for candidate in tail):
                return True

        if any(item.startswith(("kullan", "tuket")) for item in following):
            return True
        return False

    def _sector_qualifies_acquisition(after: list[str], offset: int) -> bool:
        following = after[offset + 1 : offset + 5]
        if not following:
            return False
        if _sector_is_usage_object(after, offset):
            return False
        return any(
            _acquisition_target_token(item) and not _company_possessor(item)
            for item in following
        )

    def _post_purchase_target_kind(after: list[str]) -> str | None:
        for offset, item in enumerate(after[:8]):
            if item.startswith(_SECTOR_WORDS):
                if _sector_is_usage_object(after, offset):
                    return "procurement"
                if _sector_qualifies_acquisition(after, offset):
                    continue
                return "procurement"
            if _procurement_target_token(item):
                return "procurement"
            if _acquisition_target_token(item):
                return "acquisition"
            if item.startswith(("kullan", "tuket", "tarafindan", "tarafinca")):
                break
        return None

    def _satin_alma_is_acquisition(text: str) -> bool:
        tokens = _tokens(text)
        for index in range(len(tokens) - 1):
            if tokens[index] != "satin" or not tokens[index + 1].startswith("al"):
                continue

            purchase_token = tokens[index + 1]
            before = tokens[max(0, index - 8) : index]
            after = tokens[index + 2 : index + 10]
            target_kind = _post_purchase_target_kind(after)

            if purchase_token.startswith(_ACTIVE_PURCHASE_PREFIXES) and any(
                _company_token(item) for item in before
            ):
                if target_kind == "procurement":
                    return False
                if target_kind == "acquisition":
                    return True

            if purchase_token.startswith("alin"):
                if target_kind == "procurement":
                    return False
                if target_kind == "acquisition":
                    return True

        return previous_purchase(text)

    def _transfer_target_token(token: str) -> bool:
        return token.startswith(_TRANSFER_TARGET_STEMS)

    def _target_is_adjunct(before: list[str], index: int) -> bool:
        following = before[index + 1 : index + 3]
        return any(item.startswith(_TRANSFER_ADJUNCT_STEMS) for item in following)

    def _devralma_has_acquisition_context(text: str) -> bool:
        tokens = _tokens(text)
        saw_governance_object = False

        for verb_index, token in enumerate(tokens):
            if not token.startswith("devral"):
                continue

            before = tokens[max(0, verb_index - 10) : verb_index]
            governance_positions = [
                index
                for index, item in enumerate(before)
                if service._token_has_stem(item, service._GOVERNANCE_TRANSFER_STEMS)
            ]
            last_governance = governance_positions[-1] if governance_positions else -1

            valid_targets_after_governance = [
                index
                for index, item in enumerate(before)
                if index > last_governance
                and _transfer_target_token(item)
                and not _target_is_adjunct(before, index)
            ]
            if valid_targets_after_governance:
                return True

            if governance_positions:
                saw_governance_object = True
                continue

            if token.startswith("devralin"):
                after = tokens[verb_index + 1 : verb_index + 8]
                for offset, item in enumerate(after):
                    if service._token_has_stem(item, service._GOVERNANCE_TRANSFER_STEMS):
                        break
                    if not _transfer_target_token(item):
                        continue
                    if any(
                        service._token_has_stem(
                            candidate, service._GOVERNANCE_TRANSFER_STEMS
                        )
                        for candidate in after[offset + 1 : offset + 3]
                    ):
                        break
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

    def _tesis_is_operational(text: str) -> bool:
        tokens = _tokens(text)
        tesis_positions = [
            index for index, token in enumerate(tokens) if token.startswith("tesis")
        ]
        if not tesis_positions:
            return round15_tesis(text)

        legal_positions = {
            index
            for index in tesis_positions
            if index > 0 and _is_property_right_noun(tokens[index - 1])
        }
        if legal_positions == set(tesis_positions):
            return False

        # Round 15 already handles security-interest syntax locally.  Reuse that
        # narrower matcher for every non-right-creation occurrence instead of the
        # Round 16 three-token proximity rule.
        return round15_tesis(text)

    def _named_company_possessor(tokens: list[str]) -> bool:
        if service._looks_like_named_company_target(tokens):
            return True
        for index, item in enumerate(tokens):
            if item == "as" and index + 1 < len(tokens):
                if tokens[index + 1] in {"in", "nin"}:
                    return True
            if item == "a" and index + 2 < len(tokens):
                if tokens[index + 1] == "s" and tokens[index + 2] in {"in", "nin"}:
                    return True
        return False

    def _subject_split_is_corporate(subject: str) -> bool:
        normalized = service._normalize_event_text(subject)
        tokens = _tokens(normalized)
        for split_index, token in enumerate(tokens):
            if not token.startswith("bolun"):
                continue

            before = tokens[:split_index]
            debt_object = any(item.startswith(_DEBT_STEMS) for item in before[-5:])
            if debt_object:
                continue

            corporate = any(
                service._token_has_stem(
                    item, service._CORPORATE_EVENT_CONTEXT_STEMS
                )
                for item in before
            )
            if corporate or _named_company_possessor(before):
                return True
        return False

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
        if not _subject_split_is_corporate(subject):
            return result

        split_score = 95 if is_corrective else 90
        if result[1] >= split_score:
            return result
        return (
            "mna",
            split_score,
            "critical" if split_score >= 95 else "high",
        )

    def _capacity_path(state: Any):
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
            key = str(item["company_key"])
            count = int(item["reachable_count"])
            company_caps[key] = max(company_caps.get(key, 0), count)
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

    def _update_window_capacity(
        state: Any,
        *,
        ticker: str,
        result: Any,
        active_tickers: tuple[str, ...] | None,
    ) -> None:
        canonical_ticker = service.normalize_bist_yahoo_symbol(ticker)
        active = None if active_tickers is None else set(active_tickers)

        with state.locked():
            windows = _load_window_map(state)
            if active is not None:
                windows = {
                    key: value for key, value in windows.items() if key in active
                }
            windows[canonical_ticker] = {
                "company_key": _company_key(result, canonical_ticker),
                "reachable_count": _reachable_count(result),
            }
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

    def _validate_window_capacity(
        state: Any,
        *,
        active_tickers: tuple[str, ...] | None,
    ) -> None:
        active = None if active_tickers is None else set(active_tickers)
        with state.locked():
            windows = _load_window_map(state)
            if active is not None:
                windows = {
                    key: value for key, value in windows.items() if key in active
                }
                service._atomic_write_json(
                    _capacity_path(state),
                    {"version": 1, "ticker_windows": windows},
                )
            required = _required_window_capacity(windows)
            if state.seen_limit < required:
                raise ValueError(
                    "alert_seen_limit must cover every unique disclosure reachable "
                    "through unseen-first polling in the active KAP lookback window"
                )

    def _register_tracked_tickers(
        state: Any,
        tickers: Any,
        *,
        active_tickers: tuple[str, ...] | None,
    ) -> None:
        canonical = service.WatchlistStore._validated_unique(tickers, strict=True)
        active = None if active_tickers is None else set(active_tickers)
        with state.locked():
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

    class _Round17StateProxy:
        def __init__(
            self,
            wrapped: Any,
            *,
            active_tickers: tuple[str, ...] | None,
        ) -> None:
            self._wrapped = wrapped
            self._active_tickers = active_tickers

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
            _register_tracked_tickers(
                self._wrapped,
                tickers,
                active_tickers=self._active_tickers,
            )
            _validate_window_capacity(
                self._wrapped,
                active_tickers=self._active_tickers,
            )

    class _Round17KapProxy:
        def __init__(
            self,
            wrapped: Any,
            *,
            state: Any,
            active_tickers: tuple[str, ...] | None,
        ) -> None:
            self._wrapped = wrapped
            self._state = state
            self._active_tickers = active_tickers

        def __getattr__(self, name: str) -> Any:
            return getattr(self._wrapped, name)

        def get_disclosures(self, *args: Any, **kwargs: Any):
            result = self._wrapped.get_disclosures(*args, **kwargs)
            if result.available:
                ticker = kwargs.get("ticker")
                if ticker is None and args:
                    ticker = args[0]
                _update_window_capacity(
                    self._state,
                    ticker=str(ticker),
                    result=result,
                    active_tickers=self._active_tickers,
                )
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

        shadow = copy.copy(self)
        shadow.state = _Round17StateProxy(
            self.state,
            active_tickers=active_tickers,
        )
        shadow.kap_service = _Round17KapProxy(
            self.kap_service,
            state=self.state,
            active_tickers=active_tickers,
        )
        return round15_check(shadow, requested, now=now)

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
        original=round15_check,
    )
    service._PHASE10_ROUND17_HARDENING_INSTALLED = _HARDENING_VERSION
