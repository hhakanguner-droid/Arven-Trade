"""Round 15 hardening for Phase 10 alert semantics and KAP polling fairness.

This layer is intentionally narrow: it fixes the eight Codex Round 14 P2 findings
without changing the public alert API. It is installed after phase10_hardening.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


_HARDENING_VERSION = "phase10-round15"

_DEBT_CONTEXT_STEMS = (
    "tahvil",
    "bono",
    "borc",
    "borclanma",
    "kredi",
    "eurobond",
    "finansman",
    "odeme",
    "taksit",
    "alacak",
    "borclu",
)
_GENERIC_SPLIT_CONTEXT_STEMS = (
    "islem",
    "aciklama",
    "duyuru",
    "bildirim",
    "hakkinda",
    "iliskin",
)
_PROPERTY_RIGHT_TYPE_STEMS = (
    "ust",
    "gecit",
    "oturma",
    "kaynak",
    "mecra",
)
_OBJECT_CASE_SUFFIX_TOKENS = {"i", "yi", "u", "yu", "ni", "nu"}
_SECTOR_QUALIFIER_STEMS = ("elektrik", "enerji", "dogalgaz", "gaz")


def _mark(function: Any, *, original: Any | None = None) -> Any:
    function._phase10_round15_version = _HARDENING_VERSION
    if original is not None:
        function._phase10_round15_original = original
    return function


def _is_installed(function: Any) -> bool:
    return getattr(function, "_phase10_round15_version", None) == _HARDENING_VERSION


def install(service: Any) -> None:
    """Install Round 15 fixes idempotently on ``tradingagents.alerts.service``."""
    if (
        _is_installed(getattr(service, "_classify_event_fields", None))
        and _is_installed(getattr(service, "_satin_alma_is_acquisition", None))
        and _is_installed(getattr(service, "_devralma_has_acquisition_context", None))
        and _is_installed(getattr(service, "_tesis_is_operational", None))
        and _is_installed(getattr(service.KapWatchlistAlertService, "check_watchlist", None))
    ):
        service._PHASE10_ROUND15_HARDENING_INSTALLED = _HARDENING_VERSION
        return

    previous_classify = getattr(
        service._classify_event_fields,
        "_phase10_round15_original",
        service._classify_event_fields,
    )
    previous_check = getattr(
        service.KapWatchlistAlertService.check_watchlist,
        "_phase10_round15_original",
        service.KapWatchlistAlertService.check_watchlist,
    )

    def _explicit_generic_split_subject(subject: str) -> bool:
        normalized = service._normalize_event_text(subject)
        tokens = service.re.findall(r"\w+", normalized)
        if not tokens or not tokens[0].startswith("bolunme"):
            return False
        return all(
            item.startswith(_GENERIC_SPLIT_CONTEXT_STEMS)
            for item in tokens[1:]
        )

    def _is_company_actor_token(token: str) -> bool:
        return token.startswith(("sirketimiz", "firmamiz", "ortakligimiz", "isletmemiz"))

    def _is_acquisition_target_token(token: str) -> bool:
        if token in service._BARE_COMPANY_TOKENS or _is_company_actor_token(token):
            return False
        if token.startswith(("varlig", "ortaklig")):
            return True
        return service._token_has_stem(token, service._ACQUISITION_TARGET_STEMS)

    def _named_company_before_is_target(before: list[str], purchase_token: str) -> bool:
        if not service._looks_like_named_company_target(before):
            return False
        suffix = before[-1] if before else ""
        if suffix in _OBJECT_CASE_SUFFIX_TOKENS:
            return True
        # A genitive company is the target only in passive "satın alın..." forms.
        # Active nouns such as "satın alma/alım ihalesi" name the buyer/possessor.
        return purchase_token.startswith("alin")

    def _satin_alma_is_acquisition(text: str) -> bool:
        tokens = service.re.findall(r"\w+", text)
        for index in range(len(tokens) - 1):
            if tokens[index] != "satin" or not tokens[index + 1].startswith("al"):
                continue

            purchase_token = tokens[index + 1]
            before = tokens[max(0, index - 6) : index]

            if _named_company_before_is_target(before, purchase_token):
                return True

            before_decision: bool | None = None
            for item in reversed(before):
                if _is_acquisition_target_token(item):
                    before_decision = True
                    break
                if service._token_has_stem(item, service._PROCUREMENT_TARGET_STEMS):
                    before_decision = False
                    break
            if before_decision is True:
                return True
            if before_decision is False:
                continue

            if (
                before
                and before[-1] in service._BARE_COMPANY_TOKENS
                and purchase_token.startswith("alin")
            ):
                return True

            # Scan the post-purchase noun phrase, but never cross a completed
            # procurement object into a later clause ("makineler şirket tesisinde").
            after = tokens[index + 2 : index + 8]
            for offset, item in enumerate(after):
                if service._token_has_stem(item, service._PROCUREMENT_TARGET_STEMS):
                    if item.startswith(_SECTOR_QUALIFIER_STEMS):
                        continue
                    break
                if not (
                    _is_acquisition_target_token(item)
                    or item in service._BARE_COMPANY_TOKENS
                ):
                    continue
                next_item = after[offset + 1] if offset + 1 < len(after) else ""
                if next_item.startswith(("tarafindan", "tarafinca")):
                    continue
                return True
        return False

    def _nearest_transfer_object(before: list[str]) -> str | None:
        for item in reversed(before[-5:]):
            if service._token_has_stem(item, service._GOVERNANCE_TRANSFER_STEMS):
                return "governance"
            if _is_acquisition_target_token(item):
                return "acquisition"
        return None

    def _devralma_has_acquisition_context(text: str) -> bool:
        tokens = service.re.findall(r"\w+", text)
        for index, token in enumerate(tokens):
            if not token.startswith("devral"):
                continue

            before = tokens[max(0, index - 7) : index]
            object_kind = _nearest_transfer_object(before)
            if object_kind == "governance":
                continue
            if object_kind == "acquisition":
                return True

            nearby = service._nearby_tokens(tokens, index, radius=4)
            if any(
                service._token_has_stem(item, service._GOVERNANCE_TRANSFER_STEMS)
                for item in nearby
            ):
                continue
            if any(_is_acquisition_target_token(item) for item in nearby):
                return True
            if service._looks_like_named_company_target(before):
                return True
            if (
                token.startswith("devralin")
                and before
                and before[-1] in service._BARE_COMPANY_TOKENS
            ):
                return True
            if "devralma" in token and any(item.startswith("islem") for item in nearby):
                return True
        return False

    def _has_debt_context(tokens: list[str]) -> bool:
        return any(item.startswith(_DEBT_CONTEXT_STEMS) for item in tokens)

    def _corporate_token_count(tokens: list[str]) -> int:
        return sum(
            1
            for item in tokens
            if service._token_has_stem(item, service._CORPORATE_EVENT_CONTEXT_STEMS)
        )

    def _bolunme_is_corporate(text: str) -> bool:
        tokens = service.re.findall(r"\w+", text)
        for index, token in enumerate(tokens):
            if not token.startswith("bolun"):
                continue

            nearby = service._nearby_tokens(tokens, index, radius=5)
            debt = _has_debt_context(nearby)
            equity_restructuring = any(
                item.startswith(("pay", "hisse", "sermaye")) for item in nearby
            )
            operational = any(
                service._token_has_stem(
                    item, service._NON_CORPORATE_COMBINATION_STEMS
                )
                for item in nearby
            )
            corporate = any(
                service._token_has_stem(
                    item, service._CORPORATE_EVENT_CONTEXT_STEMS
                )
                for item in nearby
            )
            corporate_count = _corporate_token_count(nearby)
            qualified_split = any(item.startswith(("kismi", "tam")) for item in nearby)

            # Debt/credit splitting is financing even when the possessor is a company.
            if debt and not equity_restructuring:
                continue

            if token.startswith("bolunmus"):
                following = tokens[index + 1 : index + 3]
                if any(item.startswith(("yol", "karayol")) for item in following):
                    continue
                if corporate_count >= 2 or qualified_split:
                    return True
                if corporate and not operational:
                    return True
                continue

            if token.startswith(
                (
                    "bolunme",
                    "bolundu",
                    "bolunuyor",
                    "bolunecek",
                    "bolunerek",
                    "bolunur",
                    "bolunmek",
                )
            ):
                if corporate_count >= 2 or qualified_split:
                    return True
                if corporate:
                    return True
                if operational:
                    continue

                # Preserve a truly standalone generic split phrase when this helper
                # is called on subject-only text. The classifier separately preserves
                # the subject boundary when a summary is appended.
                if index == 0 and all(
                    item.startswith(_GENERIC_SPLIT_CONTEXT_STEMS)
                    for item in tokens[index + 1 :]
                ):
                    return True
        return False

    def _is_property_right_noun(token: str) -> bool:
        # Topic suffixes ("hakkında", "hakkımızda") are not the legal noun "hak".
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
        tokens = service.re.findall(r"\w+", text)
        for index, token in enumerate(tokens):
            if not token.startswith("tesis"):
                continue

            before = tokens[max(0, index - 3) : index]
            after = tokens[index + 1 : index + 4]
            nearby = before + after

            has_right_noun = any(_is_property_right_noun(item) for item in nearby)
            has_property_right_type = any(
                item.startswith(_PROPERTY_RIGHT_TYPE_STEMS) for item in nearby
            )
            if has_right_noun and has_property_right_type:
                continue

            # Security-interest nouns suppress "tesis" only when they participate
            # in the legal construction, not merely because they occur later in a
            # concatenated summary.
            if any(
                service._token_has_stem(
                    item, service._LEGAL_TESIS_CONTEXT_STEMS
                )
                for item in before[-2:]
            ):
                continue

            if (
                after
                and after[0].startswith(("edil", "olustur", "kurul"))
                and any(
                    service._token_has_stem(
                        item, service._LEGAL_TESIS_CONTEXT_STEMS
                    )
                    for item in after[1:]
                )
            ):
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
        if not _explicit_generic_split_subject(subject):
            return result

        split_score = 95 if is_corrective else 90
        if result[1] >= split_score:
            return result
        split_severity = "critical" if split_score >= 95 else "high"
        return "mna", split_score, split_severity

    def _known_alert_ids(state: Any) -> set[str]:
        with state.locked():
            payload = state._load_unlocked()
            known = {
                service._canonical_alert_id(str(alert_id))
                for alert_id in payload["seen_ids"]
            }
            for bucket in ("pending", "history"):
                for item in payload[bucket]:
                    if isinstance(item, dict) and item.get("alert_id") is not None:
                        known.add(
                            service._canonical_alert_id(str(item["alert_id"]))
                        )
            return known

    def _selection_priority(
        disclosure: object,
        *,
        known_ids: set[str],
        min_score: int,
    ) -> tuple[int, int, int, float, int]:
        score, published_at = service._alert_significance_key(disclosure)
        raw_index = getattr(disclosure, "index", None)
        alert_id = (
            None
            if raw_index is None
            else service._canonical_alert_id(f"KAP:{raw_index}")
        )
        unseen = 1 if alert_id is None or alert_id not in known_ids else 0
        important = 1 if score >= min_score else 0

        if score >= 95:
            significance_band = 3
        elif score >= 85:
            significance_band = 2
        elif score >= 70:
            significance_band = 1
        else:
            significance_band = 0

        recency = 0.0
        if isinstance(published_at, datetime):
            try:
                recency = published_at.timestamp()
            except (OSError, OverflowError, ValueError):
                recency = 0.0

        return unseen, important, significance_band, recency, score

    def _check_watchlist(
        self: Any,
        tickers=None,
        *,
        now: datetime | None = None,
    ):
        checked_at = service._market_datetime(now)
        if not self.enabled:
            return service.WatchlistAlertBatch(
                checked_at=checked_at,
                source_statuses=(
                    service.AlertSourceStatus(
                        ticker="*",
                        source="KAP",
                        status="disabled",
                        message="KAP watchlist alerts are disabled by configuration.",
                    ),
                ),
            )

        end = checked_at.date()
        start = end - service.timedelta(days=self.lookback_days)
        if tickers is None:
            persisted_watchlist = self.watchlist.list()
            requested = persisted_watchlist
            active_tickers = persisted_watchlist
        else:
            requested = tuple(tickers)
            active_tickers = None
        canonical_tickers = service.WatchlistStore._validated_unique(
            requested, strict=True
        )

        known_ids = _known_alert_ids(self.state)
        candidate_alerts = []
        observed_ids: list[str] = []
        statuses = []
        successful_tickers: list[str] = []

        for ticker in canonical_tickers:
            def ranking(raw: object):
                return _selection_priority(
                    raw,
                    known_ids=known_ids,
                    min_score=self.min_score,
                )

            result = self.kap_service.get_disclosures(
                ticker=ticker,
                start_date=start,
                end_date=end,
                max_disclosures=self.max_disclosures_per_ticker,
                include_attachments=False,
                significance_key=ranking,
                summary_limit=None,
            )
            statuses.append(
                service.AlertSourceStatus(
                    ticker=ticker,
                    source="KAP",
                    status=result.status,
                    message=result.message,
                )
            )
            if not result.available:
                continue

            successful_tickers.append(ticker)
            for disclosure in result.disclosures:
                alert_id = service._canonical_alert_id(
                    f"KAP:{disclosure.disclosure_id}"
                )
                observed_ids.append(alert_id)
                known_ids.add(alert_id)

                category, score, severity = service.classify_kap_disclosure(
                    disclosure
                )
                if score < self.min_score:
                    continue
                candidate_alerts.append(
                    service.WatchlistAlert(
                        alert_id=alert_id,
                        source="KAP",
                        ticker=ticker,
                        published_at=disclosure.published_at,
                        title=disclosure.subject,
                        summary=service._bounded_alert_summary(
                            disclosure.summary
                        ),
                        url=disclosure.url,
                        category=category,
                        severity=severity,
                        score=score,
                        disclosure_id=disclosure.disclosure_id,
                        is_corrective=disclosure.is_corrective,
                        has_attachment=disclosure.has_attachment,
                    )
                )

        self.state.ensure_capacity(
            successful_tickers,
            self.max_disclosures_per_ticker,
            active_tickers=active_tickers,
        )
        candidate_alerts.sort(
            key=lambda item: (
                service._SEVERITY_RANK[item.severity],
                item.score,
                item.published_at.isoformat(),
            ),
            reverse=True,
        )
        claimed_alerts = self.state.claim(observed_ids, candidate_alerts)

        return service.WatchlistAlertBatch(
            checked_at=checked_at,
            alerts=claimed_alerts,
            source_statuses=tuple(statuses),
        )

    service._satin_alma_is_acquisition = _mark(_satin_alma_is_acquisition)
    service._devralma_has_acquisition_context = _mark(
        _devralma_has_acquisition_context
    )
    service._bolunme_is_corporate = _mark(_bolunme_is_corporate)
    service._tesis_is_operational = _mark(_tesis_is_operational)
    service._classify_event_fields = _mark(
        _classify_event_fields,
        original=previous_classify,
    )
    service.KapWatchlistAlertService.check_watchlist = _mark(
        _check_watchlist,
        original=previous_check,
    )
    service._PHASE10_ROUND15_HARDENING_INSTALLED = _HARDENING_VERSION

    # Keep explicit Round 14 reinstalls from discarding Round 15. Some regression
    # tests and hot-reload workflows call phase10_hardening.install() directly.
    import sys

    phase10_module = sys.modules.get("tradingagents.alerts.phase10_hardening")
    if phase10_module is not None:
        current_phase10_install = getattr(phase10_module, "install", None)
        if current_phase10_install is not None and not getattr(
            current_phase10_install, "_phase10_round15_chain", False
        ):
            original_phase10_install = current_phase10_install

            def _phase10_install_with_round15(target: Any) -> None:
                original_phase10_install(target)
                install(target)

            _phase10_install_with_round15._phase10_round15_chain = True
            _phase10_install_with_round15._phase10_round15_original = (
                original_phase10_install
            )
            phase10_module.install = _phase10_install_with_round15
