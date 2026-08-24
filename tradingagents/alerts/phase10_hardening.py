"""Runtime hardening for Phase 10 KAP alert semantics and state migration.

The Phase 10 alert service intentionally keeps its public API stable.  This module
installs narrowly-scoped semantic/state fixes on that module during package import
so existing callers and direct imports continue to use the same service classes.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


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


def install(service: Any) -> None:
    """Install the final Phase 10 semantic/state hardening exactly once."""
    if getattr(service, "_PHASE10_HARDENING_INSTALLED", False):
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
            before = tokens[max(0, index - 6) : index]
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
                if operational:
                    continue
                if corporate:
                    return True
                continue
        return False

    def _satin_alma_is_acquisition(text: str) -> bool:
        tokens = service.re.findall(r"\w+", text)
        for index in range(len(tokens) - 1):
            if tokens[index] != "satin" or not tokens[index + 1].startswith("al"):
                continue

            purchase_token = tokens[index + 1]
            before = tokens[max(0, index - 6) : index]

            # Explicit named-company evidence is stronger than sector/procurement words.
            if service._looks_like_named_company_target(before):
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
            has_right_noun = any(item.startswith("hak") for item in nearby)
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

    def _canonicalize_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
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

    original_load_unlocked = service.AlertStateStore._load_unlocked

    def _load_unlocked(self: Any) -> dict[str, Any]:
        payload = original_load_unlocked(self)
        seen_raw = list(payload["seen_ids"])
        seen = list(dict.fromkeys(service._canonical_alert_id(str(item)) for item in seen_raw))
        pending, pending_changed = _canonicalize_records(list(payload["pending"]))
        history, history_changed = _canonicalize_records(list(payload["history"]))
        changed = seen != seen_raw or pending_changed or history_changed
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

    service._is_acquisition_target_token = _is_acquisition_target_token
    service._devir_has_acquisition_context = _devir_has_acquisition_context
    service._devralma_has_acquisition_context = _devralma_has_acquisition_context
    service._birlesme_is_corporate = _birlesme_is_corporate
    service._bolunme_is_corporate = _bolunme_is_corporate
    service._satin_alma_is_acquisition = _satin_alma_is_acquisition
    service._tesis_is_operational = _tesis_is_operational
    service._share_repurchase_matches = _share_repurchase_matches
    service.AlertStateStore._load_unlocked = _load_unlocked
    service._PHASE10_HARDENING_INSTALLED = True
