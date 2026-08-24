"""Runtime hardening for Phase 10 KAP alert semantics and state migration.

The Phase 10 alert service intentionally keeps its public API stable. This module
installs narrowly-scoped semantic/state fixes on that module during package import
so existing callers and direct imports continue to use the same service classes.
"""

from __future__ import annotations

from typing import Any


_HARDENING_VERSION = "phase10-round14"
_COMPANY_ACTOR_PREFIXES = (
    "sirketimiz",
    "firmamiz",
    "ortakligimiz",
    "isletmemiz",
)
_SOFTENED_ACQUISITION_STEMS = ("varlig", "ortaklig")
_DEBT_REPURCHASE_STEMS = (
    "tahvil",
    "bono",
    "borc",
    "borclanma",
    "kredi",
    "eurobond",
    "finansman",
)
_PROPERTY_RIGHT_TYPE_STEMS = (
    "ust",
    "gecit",
    "oturma",
    "kaynak",
    "mecra",
)
_GENERIC_SPLIT_CONTEXT_STEMS = (
    "islem",
    "aciklama",
    "duyuru",
    "bildirim",
    "hakkinda",
    "iliskin",
)
_OBJECT_CASE_SUFFIX_TOKENS = {"i", "yi", "u", "yu", "ni", "nu"}


def _mark_hardened(function: Any, *, original: Any | None = None) -> Any:
    function._phase10_hardening_version = _HARDENING_VERSION
    if original is not None:
        function._phase10_original = original
    return function


def _is_hardened(function: Any) -> bool:
    return getattr(function, "_phase10_hardening_version", None) == _HARDENING_VERSION


def install(service: Any) -> None:
    """Install the final Phase 10 semantic/state hardening idempotently.

    Do not trust a module-level boolean alone: ``importlib.reload(service)`` keeps
    arbitrary names in the module dictionary while recreating the functions and
    classes. Function-level version markers let an explicit reinstall repair a
    hot-reloaded service module without wrapping already-patched functions twice.
    """
    if (
        _is_hardened(getattr(service, "_event_term_matches", None))
        and _is_hardened(getattr(service, "_satin_alma_is_acquisition", None))
        and _is_hardened(getattr(service.AlertStateStore, "_load_unlocked", None))
    ):
        service._PHASE10_HARDENING_INSTALLED = _HARDENING_VERSION
        return

    def _is_company_actor_token(token: str) -> bool:
        return token.startswith(_COMPANY_ACTOR_PREFIXES)

    def _is_acquisition_target_token(token: str) -> bool:
        if token in service._BARE_COMPANY_TOKENS or _is_company_actor_token(token):
            return False
        if token.startswith(_SOFTENED_ACQUISITION_STEMS):
            return True
        return service._token_has_stem(token, service._ACQUISITION_TARGET_STEMS)

    def _is_speed_context_token(token: str) -> bool:
        if token.startswith("hizmet"):
            return False
        return token == "hiz" or token.startswith(
            ("hizi", "hizin", "hizda", "hizdan", "hizlar", "hizla")
        )

    def _devir_has_acquisition_context(text: str) -> bool:
        tokens = service.re.findall(r"\w+", text)
        for index, token in enumerate(tokens):
            if not service._is_devir_token(token):
                continue
            nearby = service._nearby_tokens(tokens, index, radius=3)
            has_non_transfer_operation = any(
                item.startswith(("motor", "pompa", "rpm", "dakika", "donus"))
                or _is_speed_context_token(item)
                for item in nearby
            )
            if has_non_transfer_operation:
                continue
            if any(
                service._token_has_stem(item, service._STRONG_TRANSFER_CONTEXT_STEMS)
                for item in nearby
            ):
                return True
            if any(
                service._token_has_stem(item, service._GOVERNANCE_TRANSFER_STEMS)
                for item in nearby
            ):
                continue
            if any(
                item.startswith(("sirket", "firma", "ortaklik"))
                and not _is_company_actor_token(item)
                for item in nearby
            ):
                return True
        return False

    def _devralma_has_acquisition_context(text: str) -> bool:
        tokens = service.re.findall(r"\w+", text)
        for index, token in enumerate(tokens):
            if not token.startswith("devral"):
                continue

            nearby = service._nearby_tokens(tokens, index, radius=4)
            before = tokens[max(0, index - 6) : index]
            immediate_object = before[-1] if before else ""

            # Turkish role-transfer phrasing places the grammatical object right
            # before devralmak: "iştirak yönetimini devraldı", "görevini devraldı".
            # That explicit management/authority object outranks nearby entity nouns.
            if immediate_object and service._token_has_stem(
                immediate_object, service._GOVERNANCE_TRANSFER_STEMS
            ):
                continue

            governance_context = any(
                service._token_has_stem(item, service._GOVERNANCE_TRANSFER_STEMS)
                for item in nearby
            )
            strong_target = any(
                _is_acquisition_target_token(item)
                and not item.startswith(("sirket", "firma", "ortaklik"))
                for item in nearby
            )
            if governance_context and not strong_target:
                continue
            if strong_target or any(_is_acquisition_target_token(item) for item in nearby):
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

    def _corporate_token_count(tokens: list[str]) -> int:
        return sum(
            1
            for item in tokens
            if service._token_has_stem(item, service._CORPORATE_EVENT_CONTEXT_STEMS)
        )

    def _birlesme_is_corporate(text: str) -> bool:
        tokens = service.re.findall(r"\w+", text)
        for index, token in enumerate(tokens):
            if token.startswith("birlesik") or not token.startswith("birles"):
                continue
            nearby = service._nearby_tokens(tokens, index, radius=4)
            operational = any(
                service._token_has_stem(item, service._NON_CORPORATE_COMBINATION_STEMS)
                for item in nearby
            )
            corporate = any(
                service._token_has_stem(item, service._CORPORATE_EVENT_CONTEXT_STEMS)
                for item in nearby
            )
            corporate_count = _corporate_token_count(nearby)
            two_company_context = "iki" in nearby and corporate

            if token.startswith(("birlestir", "birlestiril")):
                if two_company_context or corporate_count >= 2:
                    return True
                if operational:
                    continue
                if corporate:
                    return True
                continue

            if token.startswith(
                (
                    "birlesme",
                    "birlesti",
                    "birlesiyor",
                    "birlesecek",
                    "birlesmis",
                    "birlesmek",
                    "birleserek",
                )
            ):
                if corporate:
                    return True
                if operational:
                    continue
                return True
        return False

    def _has_non_corporate_split_context(tokens: list[str]) -> bool:
        return any(
            service._token_has_stem(item, service._NON_CORPORATE_COMBINATION_STEMS)
            or item.startswith(_DEBT_REPURCHASE_STEMS)
            or item.startswith(("odeme", "taksit", "alacak", "borclu"))
            for item in tokens
        )

    def _is_explicit_generic_split_subject(tokens: list[str], index: int, token: str) -> bool:
        if index != 0 or not token.startswith("bolunme"):
            return False
        trailing = tokens[index + 1 :]
        if not trailing:
            return True
        return all(item.startswith(_GENERIC_SPLIT_CONTEXT_STEMS) for item in trailing)

    def _bolunme_is_corporate(text: str) -> bool:
        tokens = service.re.findall(r"\w+", text)
        for index, token in enumerate(tokens):
            if not token.startswith("bolun"):
                continue
            nearby = service._nearby_tokens(tokens, index, radius=4)
            operational = any(
                service._token_has_stem(item, service._NON_CORPORATE_COMBINATION_STEMS)
                for item in nearby
            )
            non_corporate = _has_non_corporate_split_context(nearby)
            corporate = any(
                service._token_has_stem(item, service._CORPORATE_EVENT_CONTEXT_STEMS)
                for item in nearby
            )
            corporate_count = _corporate_token_count(nearby)
            qualified_split = any(item.startswith(("kismi", "tam")) for item in nearby)

            if token.startswith("bolunmus"):
                following = tokens[index + 1 : index + 3]
                if any(item.startswith(("yol", "karayol")) for item in following):
                    continue
                if corporate_count >= 2 or qualified_split:
                    return True
                if operational:
                    continue
                return corporate

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
                if _is_explicit_generic_split_subject(tokens, index, token) and not non_corporate:
                    return True
                if operational or non_corporate:
                    continue
                continue
        return False

    def _named_company_before_is_target(before: list[str], purchase_token: str) -> bool:
        if not service._looks_like_named_company_target(before):
            return False
        suffix = before[-1] if before else ""
        if suffix in _OBJECT_CASE_SUFFIX_TOKENS:
            return True
        return service._purchase_form_can_name_target(purchase_token)

    def _satin_alma_is_acquisition(text: str) -> bool:
        tokens = service.re.findall(r"\w+", text)
        for index in range(len(tokens) - 1):
            if tokens[index] != "satin" or not tokens[index + 1].startswith("al"):
                continue

            purchase_token = tokens[index + 1]
            before = tokens[max(0, index - 6) : index]

            # Case-marked named companies are targets in accusative forms (A.Ş.'yi
            # satın aldı) and in noun/passive purchase forms (A.Ş.'nin satın
            # alınması). In active relative clauses (A.Ş.'nin satın aldığı makine)
            # the named company is the buyer, not the acquisition target.
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
                and service._purchase_form_can_name_target(purchase_token)
            ):
                return True

            after = tokens[index + 2 : index + 8]
            for offset, item in enumerate(after):
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

    def _is_property_right_noun(token: str) -> bool:
        # "hakkında" is a ubiquitous topic suffix and must not count as the noun
        # "hak/hakkı". Keep only actual right-noun inflections used in KAP prose.
        if token.startswith(("hakkind", "hakkiniz", "hakkimiz")):
            return False
        return token == "hak" or token.startswith(
            ("hakki", "hakkin", "hakka", "hakta", "haktan", "hakla")
        )

    def _tesis_is_operational(text: str) -> bool:
        tokens = service.re.findall(r"\w+", text)
        for index, token in enumerate(tokens):
            if not token.startswith("tesis"):
                continue
            nearby = service._nearby_tokens(tokens, index, radius=5)
            if any(
                service._token_has_stem(item, service._LEGAL_TESIS_CONTEXT_STEMS)
                for item in nearby
            ):
                continue
            has_right_noun = any(_is_property_right_noun(item) for item in nearby)
            has_property_right_type = any(
                item.startswith(_PROPERTY_RIGHT_TYPE_STEMS) for item in nearby
            )
            if has_right_noun and has_property_right_type:
                continue
            return True
        return False

    def _share_repurchase_matches(text: str) -> bool:
        tokens = service.re.findall(r"\w+", text)
        for index in range(len(tokens) - 1):
            if tokens[index] != "geri" or not tokens[index + 1].startswith("al"):
                continue
            nearby = service._nearby_tokens(tokens, index, radius=5)
            if any(item.startswith(("pay", "hisse")) for item in nearby):
                return True
            if any(
                service._token_has_stem(item, service._PRODUCT_RECALL_STEMS)
                for item in nearby
            ):
                continue
            if any(item.startswith(_DEBT_REPURCHASE_STEMS) for item in nearby):
                continue
            if any(item.startswith("program") for item in nearby):
                return True
        return False

    current_event_term_matches = service._event_term_matches
    original_event_term_matches = getattr(
        current_event_term_matches, "_phase10_original", current_event_term_matches
    )

    def _event_term_matches(text: str, term: str) -> bool:
        normalized = service._normalize_event_text(term)
        if normalized == "pay alim satim":
            # Productive Turkish suffixes attach to satım: satımı, satımına,
            # satımının. Preserve spaced and hyphenated KAP forms.
            return (
                service.re.search(
                    r"(?<!\w)pay\s+alim(?:\s*-\s*|\s+)satim\w*",
                    text,
                )
                is not None
            )
        return original_event_term_matches(text, term)

    def _canonicalize_records(
        records: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], bool]:
        chosen: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        changed = False
        for raw in records:
            item = dict(raw)
            raw_id = str(item.get("alert_id", ""))
            canonical_id = service._canonical_alert_id(raw_id)
            if canonical_id != raw_id:
                changed = True
            item["alert_id"] = canonical_id
            if canonical_id not in chosen:
                chosen[canonical_id] = item
                order.append(canonical_id)
                continue
            changed = True
            current = chosen[canonical_id]
            if service._alert_dict_priority(item) > service._alert_dict_priority(current):
                chosen[canonical_id] = item
        return [chosen[key] for key in order], changed

    current_load_unlocked = service.AlertStateStore._load_unlocked
    original_load_unlocked = getattr(
        current_load_unlocked, "_phase10_original", current_load_unlocked
    )

    def _load_unlocked(self: Any) -> dict[str, Any]:
        payload = original_load_unlocked(self)
        seen_raw = list(payload["seen_ids"])
        seen = list(dict.fromkeys(service._canonical_alert_id(str(item)) for item in seen_raw))
        pending, pending_changed = _canonicalize_records(list(payload["pending"]))
        history, history_changed = _canonicalize_records(list(payload["history"]))

        # A disclosure that already reached delivered history must never remain in
        # the retryable outbox after legacy share-class IDs collapse to one KAP ID.
        history_ids = {str(item.get("alert_id", "")) for item in history}
        filtered_pending = [
            item for item in pending if str(item.get("alert_id", "")) not in history_ids
        ]
        pending_history_changed = len(filtered_pending) != len(pending)
        pending = filtered_pending

        changed = (
            seen != seen_raw
            or pending_changed
            or history_changed
            or pending_history_changed
        )
        normalized = {
            "version": payload["version"],
            "seen_ids": seen,
            "pending": pending,
            "history": history,
            "tracked_tickers": list(payload["tracked_tickers"]),
        }
        if changed:
            self._save_unlocked(normalized)
        return normalized

    service._is_acquisition_target_token = _mark_hardened(_is_acquisition_target_token)
    service._devir_has_acquisition_context = _mark_hardened(_devir_has_acquisition_context)
    service._devralma_has_acquisition_context = _mark_hardened(
        _devralma_has_acquisition_context
    )
    service._birlesme_is_corporate = _mark_hardened(_birlesme_is_corporate)
    service._bolunme_is_corporate = _mark_hardened(_bolunme_is_corporate)
    service._satin_alma_is_acquisition = _mark_hardened(_satin_alma_is_acquisition)
    service._tesis_is_operational = _mark_hardened(_tesis_is_operational)
    service._share_repurchase_matches = _mark_hardened(_share_repurchase_matches)
    service._event_term_matches = _mark_hardened(
        _event_term_matches, original=original_event_term_matches
    )
    service.AlertStateStore._load_unlocked = _mark_hardened(
        _load_unlocked, original=original_load_unlocked
    )
    service._PHASE10_HARDENING_INSTALLED = _HARDENING_VERSION
