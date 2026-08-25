"""Consolidated Phase 10 Turkish KAP semantics.

This module is intentionally independent from the alert-service monkey-patch
history.  It provides one sentence-aware, clause-aware decision layer for
Phase 10 event classification so later hardening rounds do not need to stack
grammatical overrides on top of one another.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

IMPLEMENTATION_GENERATION = object()

_COMPANY_PREFIXES = (
    "sirket",
    "firma",
    "ortaklik",
    "ortaklig",
    "isletme",
    "istirak",
)
_SPEAKER_COMPANY_PREFIXES = (
    "sirketimiz",
    "firmamiz",
    "ortakligimiz",
    "isletmemiz",
    "istirakimiz",
)
_BARE_COMPANY_FORMS = {"sirket", "firma", "ortaklik", "isletme", "istirak"}
_COMPANY_TITLE_FORMS = (
    "sirketi",
    "firmasi",
    "isletmesi",
    "ortakligi",
    "istiraki",
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
    "marka",
    "portfoy",
    "fabrika",
    "tesis",
    "gayrimenkul",
)
_PROCUREMENT_STEMS = (
    "elektrik",
    "enerji",
    "dogalgaz",
    "gaz",
    "hammadde",
    "malzeme",
    "hizmet",
    "ekipman",
    "makine",
    "urun",
    "mal",
    "yakit",
    "parca",
    "tedarik",
    "lisans",
    "yazilim",
    "mobilya",
    "bilgisayar",
    "cihaz",
    "stok",
    "emtia",
    "arac",
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
    "uretil",
    "uretm",
    "urettig",
    "ureteceg",
    "sattig",
    "sagladig",
)
_GOVERNANCE_STEMS = (
    "yonetim",
    "yetki",
    "gorev",
    "sorumluluk",
    "imza",
    "makam",
    "kurul",
)
_SECURITY_STEMS = (
    "rehin",
    "ipotek",
    "teminat",
    "intifa",
    "irtifak",
    "haciz",
    "kefalet",
)
_PHYSICAL_HEAD_STEMS = (
    "liman",
    "maden",
    "fabrika",
    "santral",
    "depo",
    "yapi",
    "bina",
    "terminal",
    "merkez",
    "istasyon",
    "hat",
    "kampus",
    "saha",
    "tesis",
)
_DEBT_STEMS = ("borc", "kredi", "tahvil", "bono", "finansman")
_PRODUCT_STEMS = (
    "urun",
    "mal",
    "parti",
    "seri",
    "tuketici",
    "arac",
    "cihaz",
    "gida",
)
_COORDINATORS = {"ve", "ancak", "fakat", "ayrica", "sonra", "ardindan"}
_ACCUSATIVE_SUFFIX_TOKENS = {"i", "yi", "u", "yu", "ni", "nu"}
_GENITIVE_SUFFIX_TOKENS = {"in", "nin", "un", "nun"}
_NAMED_TITLE_MODIFIERS = {
    "bagli",
    "ana",
    "yeni",
    "hedef",
    "yerli",
    "yabanci",
    "halka",
    "acik",
}
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
_ARTICLES_RE = re.compile(r"(?<!\w)(?:esas|ana)\s+sozlesme\w*")
_PAY_TRADING_RE = re.compile(r"(?<!\w)pay\s+alim(?:\s*-\s*|\s+)satim\w*")
_CAPITAL_CONTEXT_RE = re.compile(r"(?<!\w)(?:sermaye|pay|hisse)\w*")


def normalize(value: str) -> str:
    folded = str(value).casefold().replace("ı", "i")
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", folded)
        if not unicodedata.combining(char)
    )


def tokens(value: str) -> list[str]:
    return re.findall(r"\w+", normalize(value))


def _protect_abbreviations(value: str) -> str:
    value = re.sub(r"(?i)\bA\.\s*[ŞS]\.", " AS ", str(value))
    value = re.sub(r"(?i)\bLTD\.\s*(?:ŞTİ|STI)\.", " LTD STI ", value)
    return value


def segments(*values: str) -> list[str]:
    out: list[str] = []
    for value in values:
        protected = _protect_abbreviations(str(value))
        for part in re.split(r"[.!?;:\n]+", protected):
            normalized = normalize(part).strip()
            if normalized:
                out.append(normalized)
    return out


def _has_stem(token: str, stems: Iterable[str]) -> bool:
    return any(token.startswith(stem) for stem in stems)


def _company_token(token: str) -> bool:
    return token.startswith(_COMPANY_PREFIXES)


def _speaker_company(token: str) -> bool:
    return token.startswith(_SPEAKER_COMPANY_PREFIXES)


def _company_locative(token: str) -> bool:
    if not _company_token(token):
        return False
    return token.endswith(
        (
            "de",
            "da",
            "te",
            "ta",
            "nde",
            "nda",
            "inde",
            "inda",
            "lerinde",
            "larinda",
        )
    )


def _procurement_token(token: str) -> bool:
    return _has_stem(token, _PROCUREMENT_STEMS)


def _transfer_token(token: str) -> bool:
    return _has_stem(token, _TRANSFER_STEMS)


def _usage_in(items: list[str]) -> bool:
    return any(_has_stem(item, _USAGE_STEMS) for item in items)


def _producer_link(item: str) -> bool:
    return _has_stem(item, _PRODUCER_LINK_STEMS)


def _object_inflection(token: str) -> bool:
    return token.endswith(
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
    )


def _proper_name_accusative(items: list[str]) -> bool:
    for index, item in enumerate(items):
        if item not in _ACCUSATIVE_SUFFIX_TOKENS or index == 0:
            continue
        previous = items[index - 1]
        if previous in {"as", "ltd", "sti"} and index >= 2:
            return True
        if previous not in {"a", "s", "ltd"} and previous not in _BARE_COMPANY_FORMS:
            return True
    return False


def _named_company_possessor(items: list[str]) -> bool:
    if not items:
        return False
    if any(item in _GENITIVE_SUFFIX_TOKENS for item in items[-3:]):
        if any(_company_token(item) for item in items[:-1]):
            return True
        if len(items) >= 3 and any(item in {"a", "s", "as", "ltd"} for item in items[-4:]):
            return True
    return any(
        item.startswith(("sirketinin", "firmanin", "ortakligin", "isletmenin"))
        for item in items
    )


def _named_company_title_buyer(items: list[str]) -> bool:
    if any(_speaker_company(item) for item in items):
        return True
    for index, item in enumerate(items):
        if item in _BARE_COMPANY_FORMS:
            return True
        if not item.startswith(_COMPANY_TITLE_FORMS):
            continue
        if index == 0:
            continue
        previous = items[index - 1]
        if previous not in _NAMED_TITLE_MODIFIERS:
            return True
    return False


def _explicit_object_before(items: list[str]) -> bool:
    if _proper_name_accusative(items):
        return True
    for index, item in enumerate(items):
        if not _transfer_token(item) or _speaker_company(item):
            continue
        if item.startswith(_COMPANY_TITLE_FORMS) and index > 0:
            if items[index - 1] not in _NAMED_TITLE_MODIFIERS:
                continue
        if _object_inflection(item):
            return True
    return False


def _producer_company_target(items: list[str]) -> bool:
    for start, item in enumerate(items):
        if not _procurement_token(item):
            continue
        relation = False
        for candidate in items[start + 1 :]:
            if _has_stem(candidate, _USAGE_STEMS):
                break
            if _producer_link(candidate):
                relation = True
                continue
            if relation and _company_token(candidate):
                return not _speaker_company(candidate) and not _company_locative(candidate)
    return False


def _non_speaker_company_indices(items: list[str]) -> list[int]:
    return [
        index
        for index, item in enumerate(items)
        if _company_token(item) and not _speaker_company(item) and not _company_locative(item)
    ]


def _procurement_company_phrase_decision(items: list[str]) -> bool | None:
    procurement_positions = [
        index for index, item in enumerate(items) if _procurement_token(item)
    ]
    if not procurement_positions:
        return None

    if _producer_company_target(items):
        return True

    first_proc = procurement_positions[0]
    company_positions = _non_speaker_company_indices(items)
    speaker_positions = [
        index
        for index, item in enumerate(items)
        if _speaker_company(item) or _company_locative(item)
    ]

    if speaker_positions and speaker_positions[0] > first_proc:
        return False

    later_companies = [index for index in company_positions if index > first_proc]
    if not later_companies:
        return False

    company_index = later_companies[0]
    tail = items[company_index + 1 :]
    usage = _usage_in(tail)

    if usage and any(_producer_link(item) for item in tail):
        return True

    if usage and any(item.startswith(("tesis", "fabrika", "santral", "depo")) for item in tail):
        return False

    return True


def _post_purchase_decision(items: list[str]) -> bool | None:
    if not items:
        return None

    procurement_decision = _procurement_company_phrase_decision(items)
    if procurement_decision is not None:
        return procurement_decision

    for item in items:
        if _speaker_company(item) or _company_locative(item):
            continue
        if _transfer_token(item):
            return True
    return None


def _pre_passive_target(items: list[str]) -> bool:
    if _producer_company_target(items):
        return True
    if _named_company_possessor(items):
        return True
    if _proper_name_accusative(items):
        return True
    decision = _procurement_company_phrase_decision(items)
    if decision is not None:
        return decision
    return any(
        _transfer_token(item)
        and not _speaker_company(item)
        and not _company_locative(item)
        for item in items
    )


def _purchase_kind(purchase_token: str, after: list[str]) -> str:
    if purchase_token.startswith("alin"):
        return "passive"
    if purchase_token.startswith("aldig"):
        return "active_relative"
    if purchase_token.startswith("almis") and after and after[0].startswith("oldug"):
        return "active_relative"
    if purchase_token.startswith(
        ("aldi", "alacak", "alacag", "aliyor", "alir", "almis")
    ):
        return "active_finite"
    if purchase_token.startswith(("alma", "alim")):
        return "active_nominal"
    return "other"


def _left_clause(items: list[str], purchase_index: int) -> list[str]:
    left = 0
    for pos in range(purchase_index - 1, -1, -1):
        if items[pos] in _COORDINATORS:
            left = pos + 1
            break
    return items[left:purchase_index]


def _right_clause(
    items: list[str],
    purchase_index: int,
    next_purchase_index: int | None,
) -> list[str]:
    end = next_purchase_index if next_purchase_index is not None else len(items)
    candidate = items[purchase_index + 2 : end]
    for pos, item in enumerate(candidate):
        if item not in _COORDINATORS:
            continue
        tail = candidate[pos + 1 :]
        if any(
            _has_stem(token, _USAGE_STEMS)
            or token.startswith(("aldi", "alacak", "aliyor", "satti", "aciklandi"))
            for token in tail
        ):
            return candidate[:pos]
    return candidate


def satin_alma_is_acquisition(text: str) -> bool:
    for segment in segments(text):
        items = re.findall(r"\w+", segment)
        occurrences = [
            index
            for index in range(len(items) - 1)
            if items[index] == "satin" and items[index + 1].startswith("al")
        ]
        if not occurrences:
            continue

        for occurrence_no, index in enumerate(occurrences):
            next_index = (
                occurrences[occurrence_no + 1]
                if occurrence_no + 1 < len(occurrences)
                else None
            )
            before = _left_clause(items, index)
            after = _right_clause(items, index, next_index)
            purchase_token = items[index + 1]
            kind = _purchase_kind(purchase_token, after)
            post = _post_purchase_decision(after)

            if kind == "passive":
                if post is True or _pre_passive_target(before):
                    return True
                continue

            if kind == "active_relative":
                if post is True:
                    return True
                continue

            if kind == "active_finite":
                if _explicit_object_before(before):
                    return True
                if post is True:
                    return True
                if _named_company_title_buyer(before):
                    continue
                continue

            if kind == "active_nominal":
                if post is True:
                    return True
                if (
                    before
                    and _company_token(before[-1])
                    and not _named_company_possessor(before)
                    and not any(item in _GENITIVE_SUFFIX_TOKENS for item in before[-2:])
                ):
                    return True
                continue

    return False


def _board_decision_ranges(items: list[str], verb_index: int) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for start, item in enumerate(items[:verb_index]):
        if not item.startswith("yonetim"):
            continue
        tail = items[start + 1 : verb_index]
        if not tail or not tail[0].startswith("kurul"):
            continue
        for offset, candidate in enumerate(tail[1:], start=1):
            if candidate.startswith("karar"):
                ranges.append((start, start + 1 + offset))
                break
    return ranges


def _inside_ranges(index: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= index <= end for start, end in ranges)


def _adjunct_indices(items: list[str], verb_index: int) -> set[int]:
    out: set[int] = set()
    for index, item in enumerate(items[:verb_index]):
        if item.startswith("adina") and index > 0:
            out.add(index - 1)
            out.add(index)
    return out


def _governance_object_before(items: list[str], verb_index: int) -> bool:
    board_ranges = _board_decision_ranges(items, verb_index)
    adjunct = _adjunct_indices(items, verb_index)
    for index, item in enumerate(items[:verb_index]):
        if index in adjunct or _inside_ranges(index, board_ranges):
            continue
        if _has_stem(item, _GOVERNANCE_STEMS) and _object_inflection(item):
            return True
    return False


def _acquisition_object_before(items: list[str], verb_index: int) -> bool:
    board_ranges = _board_decision_ranges(items, verb_index)
    adjunct = _adjunct_indices(items, verb_index)
    for index, item in enumerate(items[:verb_index]):
        if index in adjunct or _inside_ranges(index, board_ranges):
            continue
        if _transfer_token(item) and _object_inflection(item):
            return True
    return _proper_name_accusative(items[:verb_index])


def _passive_devralma_decision(after: list[str]) -> bool | None:
    if _producer_company_target(after):
        return True
    procurement = _procurement_company_phrase_decision(after)
    if procurement is not None:
        return procurement
    for item in after:
        if _speaker_company(item) or _company_locative(item):
            continue
        if _company_token(item) or _transfer_token(item):
            return True
    return None


def devralma_has_acquisition_context(text: str) -> bool:
    for segment in segments(text):
        items = re.findall(r"\w+", segment)
        for index, item in enumerate(items):
            if not item.startswith("devral"):
                continue

            if item.startswith("devralin"):
                decision = _passive_devralma_decision(items[index + 1 :])
                if decision is True:
                    return True
                continue

            if item.startswith("devralma") and any(
                token.startswith("islem") for token in items[max(0, index - 3) : index + 4]
            ):
                return True

            governance = _governance_object_before(items, index)
            acquisition = _acquisition_object_before(items, index)
            if acquisition:
                return True
            if governance:
                continue

            post = _post_purchase_decision(items[index + 1 :])
            if post is True:
                return True

    return False


def _right_noun(token: str) -> bool:
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


def _existing_right_link(items: list[str], right_index: int, tesis_index: int) -> bool:
    between = items[right_index + 1 : tesis_index]
    if not between:
        return False
    if any(_has_stem(item, _RIGHT_TERMINATING_STEMS) for item in between):
        return True
    for index, item in enumerate(between):
        if item.startswith("kapsamindaki") and index + 1 < len(between):
            return True
        if item.startswith(("bulunan", "mevcut", "uzerindeki")) and index + 1 < len(between):
            return True
    if any(_has_stem(item, _PHYSICAL_HEAD_STEMS) for item in between):
        return True
    return False


def _security_noun(token: str) -> bool:
    if token.startswith(("ipotekli", "rehinli", "teminatli")):
        return False
    return _has_stem(token, _SECURITY_STEMS)


def _forward_created_right(items: list[str], tesis_index: int) -> bool:
    tail = items[tesis_index + 1 : tesis_index + 8]
    if not tail:
        return False
    if not any(
        item.startswith(("edil", "edilecek", "edilen", "edilmis", "olustur"))
        for item in tail[:2]
    ):
        return False
    return any(
        _right_noun(item) or _security_noun(item)
        for item in tail[1:]
    )


def _backward_created_right(items: list[str], tesis_index: int) -> bool:
    for index in range(tesis_index - 1, -1, -1):
        item = items[index]
        if item in _COORDINATORS or item.startswith("tesis"):
            return False
        if _has_stem(item, _RIGHT_TERMINATING_STEMS):
            return False
        if _security_noun(item):
            between = items[index + 1 : tesis_index]
            if any(_has_stem(token, _PHYSICAL_HEAD_STEMS) for token in between):
                return False
            return True
        if _right_noun(item):
            if _existing_right_link(items, index, tesis_index):
                return False
            return True
    return False


def tesis_is_operational(text: str) -> bool:
    found = False
    for segment in segments(text):
        items = re.findall(r"\w+", segment)
        for index, item in enumerate(items):
            if not item.startswith("tesis"):
                continue
            found = True
            if _forward_created_right(items, index):
                continue
            if _backward_created_right(items, index):
                continue
            return True
    return False if found else False


def _segment_has_legal_tesis(segment: str) -> bool:
    items = re.findall(r"\w+", normalize(segment))
    for index, item in enumerate(items):
        if not item.startswith("tesis"):
            continue
        if _forward_created_right(items, index) or _backward_created_right(items, index):
            return True
    return False


def _capital_price_term_matches(subject: str, summary: str, term: str) -> bool:
    normalized_term = normalize(term)
    for segment in segments(subject, summary):
        segment_tokens = re.findall(r"\w+", segment)
        if not any(item.startswith(normalized_term) for item in segment_tokens):
            continue
        if _CAPITAL_CONTEXT_RE.search(segment):
            return True
        if _segment_has_legal_tesis(segment):
            continue
        return True
    return False


def _split_is_corporate(subject: str, summary: str) -> bool:
    subject_n = normalize(subject)
    subject_tokens = re.findall(r"\w+", subject_n)
    if subject_tokens and subject_tokens[0].startswith("bolun"):
        if len(subject_tokens) <= 2 or any(item.startswith("islem") for item in subject_tokens[1:]):
            return True

    for segment in segments(subject, summary):
        items = re.findall(r"\w+", segment)
        for index, item in enumerate(items):
            if not item.startswith("bolun"):
                continue
            tail = items[index + 1 : index + 4]
            if item.startswith("bolunmus") and any(
                token.startswith(("yol", "karayol")) for token in tail
            ):
                continue

            nearby = items[max(0, index - 7) : index + 7]
            corporate = any(
                _company_token(token)
                or token.startswith(("pay", "hisse", "sermaye", "holding", "grup"))
                for token in nearby
            ) or _named_company_possessor(items[max(0, index - 7) : index])
            debt = any(_has_stem(token, _DEBT_STEMS) for token in nearby)
            noncorporate = any(
                token.startswith(("dosya", "veri", "yol", "karayol", "hat", "trafik", "parca"))
                for token in nearby
            )

            if debt:
                before = items[max(0, index - 6) : index]
                if any(_has_stem(token, _DEBT_STEMS) for token in before):
                    continue
            if noncorporate and not corporate:
                continue
            if corporate:
                return True

    return False


def _merger_is_corporate(subject: str, summary: str) -> bool:
    subject_tokens = re.findall(r"\w+", normalize(subject))
    if subject_tokens and subject_tokens[0].startswith("birles"):
        if len(subject_tokens) <= 2 or any(item.startswith("islem") for item in subject_tokens[1:]):
            return True

    for segment in segments(subject, summary):
        items = re.findall(r"\w+", segment)
        for index, item in enumerate(items):
            if item.startswith("birlesik") or not item.startswith("birles"):
                continue
            nearby = items[max(0, index - 6) : index + 7]
            corporate = any(
                _company_token(token)
                or token.startswith(("pay", "hisse", "sermaye", "holding", "grup"))
                for token in nearby
            )
            operational_heads = any(
                token.startswith(("hat", "uretim", "dosya", "veri", "sistem", "trafik", "yol"))
                for token in nearby
            )
            if operational_heads and not corporate:
                continue
            if corporate:
                return True
    return False


def _devir_is_acquisition(subject: str, summary: str) -> bool:
    for segment in segments(subject, summary):
        items = re.findall(r"\w+", segment)
        for index, item in enumerate(items):
            if item.startswith(("devrim", "devriye", "devirdaim", "devreye")):
                continue
            if not item.startswith(("devir", "devri", "devred", "devret")):
                continue
            nearby = items[max(0, index - 6) : index + 7]
            governance = any(_has_stem(token, _GOVERNANCE_STEMS) for token in nearby)
            target = any(
                _transfer_token(token)
                and not _speaker_company(token)
                for token in nearby
            )
            if target:
                return True
            if governance:
                continue
    return False


def _share_repurchase(subject: str, summary: str) -> bool:
    for segment in segments(subject, summary):
        items = re.findall(r"\w+", segment)
        for index in range(len(items) - 1):
            if items[index] != "geri" or not items[index + 1].startswith("al"):
                continue
            nearby = items[max(0, index - 6) : index + 8]
            if any(item.startswith(("pay", "hisse")) for item in nearby):
                return True
            if any(_has_stem(item, _DEBT_STEMS) for item in nearby):
                continue
            if any(_has_stem(item, _PRODUCT_STEMS) for item in nearby):
                continue
    return False


def _ceza_matches(text: str) -> bool:
    accepted = {
        "ceza",
        "cezai",
        "cezasi",
        "cezasina",
        "cezasini",
        "cezasinda",
        "cezasindan",
        "cezasinin",
        "cezanin",
        "cezaya",
        "cezayi",
        "cezada",
        "cezadan",
        "cezalar",
        "cezalari",
        "cezalarina",
        "cezalarini",
        "cezalarinda",
        "cezalarindan",
        "cezalarin",
    }
    return any(token in accepted or token.startswith("cezalandir") for token in re.findall(r"\w+", text))


def term_matches(subject: str, summary: str, term: str) -> bool:
    normalized_term = normalize(term)
    text = normalize(f"{subject} {summary}")

    if normalized_term == "yatirim":
        return re.search(r"(?<!\w)yatirim(?!ci)", text) is not None
    if normalized_term == "ceza":
        return _ceza_matches(text)
    if normalized_term == "birlesme":
        return _merger_is_corporate(subject, summary)
    if normalized_term == "bolunme":
        return _split_is_corporate(subject, summary)
    if normalized_term == "satin alma":
        return satin_alma_is_acquisition(f"{subject}. {summary}")
    if normalized_term == "devralma":
        return devralma_has_acquisition_context(f"{subject}. {summary}")
    if normalized_term == "devir":
        return _devir_is_acquisition(subject, summary)
    if normalized_term in {"geri alim", "pay geri alim"}:
        return _share_repurchase(subject, summary)
    if normalized_term == "sozlesme":
        if _ARTICLES_RE.search(text):
            return False
        return re.search(r"(?<!\w)sozlesme\w*", text) is not None
    if normalized_term == "tesis":
        return tesis_is_operational(f"{subject}. {summary}")
    if normalized_term == "pay alim satim":
        return _PAY_TRADING_RE.search(text) is not None
    if normalized_term in {"bedelsiz", "bedelli"}:
        return _capital_price_term_matches(subject, summary, normalized_term)
    return normalized_term in text


def _procurement_operation(subject: str, summary: str) -> bool:
    text = f"{subject}. {summary}"
    all_tokens = tokens(text)
    if not any(_procurement_token(item) for item in all_tokens):
        return False
    purchase_present = any(
        items[index] == "satin" and items[index + 1].startswith("al")
        for segment in segments(text)
        for items in [re.findall(r"\w+", segment)]
        for index in range(len(items) - 1)
    )
    passive_takeover_present = any(
        item.startswith("devralin") for item in all_tokens
    )
    if purchase_present and not satin_alma_is_acquisition(text):
        return True
    if passive_takeover_present and not devralma_has_acquisition_context(text):
        return True
    return False


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

    for candidate, weight, terms_ in event_rules:
        if weight <= score:
            continue
        if any(term_matches(subject, summary, term) for term in terms_):
            category, score = candidate, weight

    if score < 80 and _procurement_operation(subject, summary):
        category, score = "operations", 80

    if is_corrective and score:
        score = min(100, score + 5)

    if score >= 95:
        severity = "critical"
    elif score >= 85:
        severity = "high"
    elif score >= 70:
        severity = "medium"
    else:
        severity = "low"
    return category, score, severity


def event_term_matches_compat(text: str, term: str) -> bool:
    """Compatibility helper for callers that already pass normalized joined text."""
    return term_matches(text, "", term)
