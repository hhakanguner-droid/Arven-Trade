"""Round 16 hardening for Phase 10 KAP semantics and durable poll retention.

Round 16 closes the eight findings from the exact-head Codex review of Round 15.
It deliberately keeps the public alert API unchanged while making the hardening
installer deterministic through ``phase10_hardening.install``.
"""

from __future__ import annotations

import copy
from typing import Any


_HARDENING_VERSION = "phase10-round16"
_ACTIVE_PURCHASE_PREFIXES = (
    "aldi",
    "aldig",
    "alacag",
    "alacak",
    "aliyor",
)
_COMPANY_NOUN_PREFIXES = (
    "sirket",
    "firma",
    "ortaklik",
    "isletme",
)
_STRONG_TRANSFER_OBJECT_STEMS = (
    "pay",
    "hisse",
    "varlik",
    "varlig",
    "isletme",
)
_USAGE_CONTEXT_STEMS = (
    "tesis",
    "fabrika",
    "uretim",
    "kullan",
    "tuket",
)
_SECTOR_WORDS = ("elektrik", "enerji", "dogalgaz", "gaz")
_SECTOR_TARGET_QUALIFIERS = (
    "dagitim",
    "perakende",
    "uretim",
    "tedarik",
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
    function._phase10_round16_version = _HARDENING_VERSION
    if original is not None:
        function._phase10_round16_original = original
    return function


def _is_installed(function: Any) -> bool:
    return getattr(function, "_phase10_round16_version", None) == _HARDENING_VERSION


def install(service: Any) -> None:
    """Install Round 16 fixes idempotently after the Round 15 layer."""
    if (
        _is_installed(getattr(service, "_satin_alma_is_acquisition", None))
        and _is_installed(getattr(service, "_devralma_has_acquisition_context", None))
        and _is_installed(getattr(service, "_tesis_is_operational", None))
        and _is_installed(getattr(service, "_classify_event_fields", None))
        and _is_installed(getattr(service.KapWatchlistAlertService, "check_watchlist", None))
    ):
        service._PHASE10_ROUND16_HARDENING_INSTALLED = _HARDENING_VERSION
        return

    previous_purchase = getattr(
        service._satin_alma_is_acquisition,
        "_phase10_round16_original",
        service._satin_alma_is_acquisition,
    )
    previous_devralma = getattr(
        service._devralma_has_acquisition_context,
        "_phase10_round16_original",
        service._devralma_has_acquisition_context,
    )
    previous_tesis = getattr(
        service._tesis_is_operational,
        "_phase10_round16_original",
        service._tesis_is_operational,
    )
    previous_classify = getattr(
        service._classify_event_fields,
        "_phase10_round16_original",
        service._classify_event_fields,
    )
    previous_check = getattr(
        service.KapWatchlistAlertService.check_watchlist,
        "_phase10_round16_original",
        service.KapWatchlistAlertService.check_watchlist,
    )

    def _tokens(text: str) -> list[str]:
        return service.re.findall(r"\w+", text)

    def _is_active_purchase(token: str) -> bool:
        return token.startswith(_ACTIVE_PURCHASE_PREFIXES)

    def _looks_like_company_noun(token: str) -> bool:
        return token.startswith(_COMPANY_NOUN_PREFIXES)

    def _active_company_buyer_procurement(text: str) -> bool:
        tokens = _tokens(text)
        for index in range(len(tokens) - 1):
            if tokens[index] != "satin" or not _is_active_purchase(tokens[index + 1]):
                continue
            before = tokens[max(0, index - 6) : index]
            after = tokens[index + 2 : index + 7]
            if not any(_looks_like_company_noun(item) for item in before):
                continue
            if any(
                service._token_has_stem(item, service._PROCUREMENT_TARGET_STEMS)
                for item in after[:2]
            ):
                return True
        return False

    def _sector_word_is_completed_procurement(after: list[str], offset: int) -> bool:
        item = after[offset]
        if not item.startswith(_SECTOR_WORDS):
            return False

        following = after[offset + 1 : offset + 4]
        if not following:
            return True

        # "elektrik dağıtım şirketi" is an acquisition target noun phrase.
        if following[0].startswith(_SECTOR_TARGET_QUALIFIERS):
            return False

        # "elektrik şirket tesislerinde kullanılacaktır" uses electricity as the
        # completed procurement object; the later company/facility words belong
        # to the usage clause and must not be scanned as acquisition targets.
        if following[0].startswith(("sirket", "firma")) and len(following) > 1:
            if following[1].startswith(_USAGE_CONTEXT_STEMS):
                return True

        if following[0].startswith(_USAGE_CONTEXT_STEMS):
            return True
        return False

    def _satin_alma_is_acquisition(text: str) -> bool:
        if _active_company_buyer_procurement(text):
            return False

        tokens = _tokens(text)
        for index in range(len(tokens) - 1):
            if tokens[index] != "satin" or not tokens[index + 1].startswith("al"):
                continue
            after = tokens[index + 2 : index + 8]
            for offset, item in enumerate(after):
                if _sector_word_is_completed_procurement(after, offset):
                    return False
                if item.startswith(_SECTOR_WORDS):
                    # Traverse sector words only when they genuinely qualify a
                    # later target noun, e.g. "elektrik dağıtım şirketi".
                    continue
                break

        return previous_purchase(text)

    def _has_explicit_governance_object(before: list[str]) -> bool:
        governance_positions = [
            index
            for index, item in enumerate(before)
            if service._token_has_stem(item, service._GOVERNANCE_TRANSFER_STEMS)
        ]
        if not governance_positions:
            return False

        last_governance = governance_positions[-1]
        trailing = before[last_governance + 1 :]
        # Entity nouns in an adjunct such as "bağlı ortaklığı adına" do not
        # replace the already explicit object "yönetimini".
        strong_object = any(
            service._token_has_stem(item, _STRONG_TRANSFER_OBJECT_STEMS)
            and not item.startswith(("ortaklik", "istirak"))
            for item in trailing
        )
        return not strong_object

    def _devralma_has_acquisition_context(text: str) -> bool:
        tokens = _tokens(text)
        saw_governance_object = False
        for index, token in enumerate(tokens):
            if not token.startswith("devral"):
                continue
            before = tokens[max(0, index - 9) : index]
            after = tokens[index + 1 : index + 4]

            if _has_explicit_governance_object(before):
                saw_governance_object = True
                continue

            # Passive target morphology may put the company after the verb:
            # "Devralınacak Şirket", "Devralınan Firma".
            if token.startswith("devralin") and any(
                item in service._BARE_COMPANY_TOKENS or _looks_like_company_noun(item)
                for item in after[:2]
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

    def _tesis_is_operational(text: str) -> bool:
        tokens = _tokens(text)
        for index, token in enumerate(tokens):
            if not token.startswith("tesis"):
                continue
            before = tokens[max(0, index - 3) : index]
            # The legal construction is productive: kullanım/önalım/üst/... hakkı
            # tesisi. Requiring a fixed whitelist of right types is brittle.
            if any(_is_property_right_noun(item) for item in before):
                return False
        return previous_tesis(text)

    def _subject_split_is_corporate(subject: str) -> bool:
        tokens = _tokens(service._normalize_event_text(subject))
        split_positions = [
            index for index, item in enumerate(tokens) if item.startswith("bolun")
        ]
        if not split_positions:
            return False

        corporate = any(
            service._token_has_stem(item, service._CORPORATE_EVENT_CONTEXT_STEMS)
            for item in tokens
        )
        if not corporate:
            return False

        # Debt suppresses M&A only when the debt itself is the object being split.
        for split_index in split_positions:
            before = tokens[max(0, split_index - 4) : split_index]
            if any(item.startswith(_DEBT_STEMS) for item in before):
                continue
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
        return state.path.with_name(f"{state.path.name}.round16-capacity.json")

    def _load_capacity_map(state: Any) -> dict[str, int]:
        payload = service._read_json_object(_capacity_path(state))
        if payload is None:
            return {}
        if payload.get("version") != 1 or not isinstance(payload.get("ticker_caps"), dict):
            raise ValueError(f"invalid alert capacity state: {_capacity_path(state)}")
        result: dict[str, int] = {}
        for ticker, raw_cap in payload["ticker_caps"].items():
            if not service.is_bist_yahoo_symbol(ticker):
                raise ValueError(f"invalid alert capacity ticker: {ticker!r}")
            if not isinstance(raw_cap, int) or raw_cap < 1:
                raise ValueError(f"invalid alert capacity value for {ticker!r}")
            result[service.normalize_bist_yahoo_symbol(ticker)] = raw_cap
        return result

    def _ensure_window_capacity(
        state: Any,
        *,
        ticker: str,
        reachable_count: int,
        active_tickers: tuple[str, ...] | None,
    ) -> None:
        canonical_ticker = service.normalize_bist_yahoo_symbol(ticker)
        reachable_count = max(1, int(reachable_count))
        active = None if active_tickers is None else set(active_tickers)

        with state.locked():
            caps = _load_capacity_map(state)
            if active is not None:
                caps = {key: value for key, value in caps.items() if key in active}
            caps[canonical_ticker] = max(caps.get(canonical_ticker, 0), reachable_count)
            required = sum(caps.values())
            if state.seen_limit < required:
                raise ValueError(
                    "alert_seen_limit must cover every disclosure reachable through "
                    "unseen-first polling in the active KAP lookback window"
                )
            service._atomic_write_json(
                _capacity_path(state),
                {"version": 1, "ticker_caps": caps},
            )

    class _CapacityAwareKapProxy:
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

        def get_disclosures(self, **kwargs):
            result = self._wrapped.get_disclosures(**kwargs)
            if result.available:
                reachable = max(
                    int(kwargs.get("max_disclosures", 1)),
                    int(result.total_found or 0),
                )
                _ensure_window_capacity(
                    self._state,
                    ticker=str(kwargs["ticker"]),
                    reachable_count=reachable,
                    active_tickers=self._active_tickers,
                )
            return result

    def _check_watchlist(self: Any, tickers=None, *, now=None):
        if tickers is None:
            active_tickers = tuple(self.watchlist.list())
            requested = active_tickers
        else:
            active_tickers = None
            requested = tuple(tickers)

        shadow = copy.copy(self)
        shadow.kap_service = _CapacityAwareKapProxy(
            self.kap_service,
            state=self.state,
            active_tickers=active_tickers,
        )
        return previous_check(shadow, requested if tickers is not None else None, now=now)

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
    service._PHASE10_ROUND16_HARDENING_INSTALLED = _HARDENING_VERSION
