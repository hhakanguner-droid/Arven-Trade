"""Phase 10 Round 23 consolidated Turkish KAP semantic engine.

The engine is deliberately independent from the historical hardening wrappers.
It classifies sentence/clause-local event semantics and never falls back to
older grammatical matchers.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

_COMPANY_PREFIXES = (
    "sirket", "firma", "ortaklik", "ortaklig", "isletme", "istirak",
)
_SPEAKER_COMPANY_PREFIXES = (
    "sirketimiz", "firmamiz", "ortakligimiz", "isletmemiz", "istirakimiz",
)
_COMPANY_TITLE_NOMINATIVE = (
    "sirketi", "firmasi", "isletmesi", "ortakligi", "istiraki",
)
_COMPANY_TITLE_ACCUSATIVE = (
    "sirketini", "firmasini", "isletmesini", "ortakligini", "istirakini",
    "sirketlerini", "firmalarini", "isletmelerini", "ortakliklarini", "istiraklerini",
)
_COMPANY_OBJECT_MODIFIERS = {"bagli", "ana", "hedef", "yeni", "yerli", "yabanci", "halka", "acik"}
_TRANSFER_STEMS = (
    "pay", "hisse", "varlik", "varlig", "isletme", "istirak", "ortaklik",
    "ortaklig", "sirket", "firma", "marka", "portfoy", "fabrika", "tesis",
    "gayrimenkul",
)
_PROCUREMENT_STEMS = (
    "elektrik", "enerji", "dogalgaz", "gaz", "hammadde", "malzeme", "hizmet",
    "ekipman", "makine", "urun", "mal", "yakit", "parca", "tedarik", "lisans",
    "yazilim", "mobilya", "bilgisayar", "cihaz", "stok", "emtia", "arac",
)
_USAGE_STEMS = ("kullan", "tuket", "yak", "harca")
_PRODUCER_STEMS = (
    "uretic", "imalatc", "gelistiric", "tedarikc", "saglayic", "dagitic",
    "ureten", "uretil", "uretm", "urettig", "ureteceg", "sattig", "sagladig",
)
_GOVERNANCE_STEMS = (
    "yonetim", "yetki", "gorev", "sorumluluk", "imza", "makam", "kurul",
)
_SECURITY_STEMS = ("rehin", "ipotek", "teminat", "intifa", "irtifak", "haciz", "kefalet")
_PHYSICAL_HEAD_STEMS = (
    "liman", "maden", "fabrika", "santral", "depo", "yapi", "bina", "terminal",
    "merkez", "istasyon", "hat", "kampus", "saha",
)
_DEBT_STEMS = ("borc", "kredi", "tahvil", "bono", "finansman")
_PRODUCT_STEMS = ("urun", "mal", "parti", "seri", "tuketici", "arac", "cihaz", "gida")
_COORDINATORS = {"ve", "ancak", "fakat", "ayrica", "sonra", "ardindan"}
_ACCUSATIVE_SUFFIX_TOKENS = {"i", "yi", "u", "yu", "ni", "nu"}
_GENITIVE_SUFFIX_TOKENS = {"in", "nin", "un", "nun"}
_RIGHT_TERMINATORS = (
    "bulun", "sahip", "sona", "erdi", "yenilen", "iptal", "fesih", "doldu",
    "kaldir", "kaybet", "devret",
)
_PHYSICAL_PREDICATES = (
    "kurul", "acil", "devreye", "faaliyet", "insaa", "insa", "genislet",
    "modernize", "tamamlan", "yapil", "devam", "planlan",
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


def _protect_abbreviations(value: str) -> str:
    value = re.sub(r"(?i)\bA\.\s*[ŞS]\.", " AS ", str(value))
    value = re.sub(r"(?i)\bLTD\.\s*(?:ŞTİ|STI)\.", " LTD STI ", value)
    return value


def segments(*values: str) -> list[str]:
    """Return punctuation-bounded semantic clauses.

    Commas are boundaries too. This prevents a finite purchase in one comma
    clause from borrowing a target from the next clause. Acquisition lists
    still work because every comma piece is inspected independently.
    """
    out: list[str] = []
    for value in values:
        protected = _protect_abbreviations(str(value))
        for part in re.split(r"[,.!?;:\n]+", protected):
            item = normalize(part).strip()
            if item:
                out.append(item)
    return out


def tokens(value: str) -> list[str]:
    return re.findall(r"\w+", normalize(value))


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
        ("de", "da", "te", "ta", "nde", "nda", "inde", "inda", "lerinde", "larinda")
    )


def _company_genitive(token: str) -> bool:
    return _company_token(token) and token.endswith(
        ("in", "nin", "un", "nun", "inin", "sinin", "sunun", "ligin", "liginin")
    )


def _company_title_accusative(token: str) -> bool:
    return token.startswith(_COMPANY_TITLE_ACCUSATIVE)


def _procurement_token(token: str) -> bool:
    return _has_stem(token, _PROCUREMENT_STEMS)


def _transfer_token(token: str) -> bool:
    return _has_stem(token, _TRANSFER_STEMS)


def _usage_in(items: list[str]) -> bool:
    return any(_has_stem(item, _USAGE_STEMS) for item in items)


def _producer_link(token: str) -> bool:
    return _has_stem(token, _PRODUCER_STEMS)


def _object_inflection(token: str) -> bool:
    return token.endswith(
        ("i", "u", "yi", "yu", "ni", "nu", "lari", "leri", "larini", "lerini")
    )


def _proper_name_accusative(items: list[str]) -> bool:
    for index, item in enumerate(items):
        if item not in _ACCUSATIVE_SUFFIX_TOKENS or index == 0:
            continue
        previous = items[index - 1]
        if previous in {"as", "ltd", "sti"} and index >= 2:
            return True
        if previous not in {"a", "s", "ltd"} and not _company_token(previous):
            return True
    return False


def _named_company_possessor(items: list[str]) -> bool:
    if not items:
        return False
    if any(item in _GENITIVE_SUFFIX_TOKENS for item in items[-4:]):
        if any(_company_token(item) for item in items[:-1]):
            return True
        if any(item in {"a", "s", "as", "ltd", "sti"} for item in items[-5:]):
            return True
    return any(
        item.startswith(("sirketinin", "firmanin", "firmasinin", "ortakligin", "isletmenin"))
        for item in items
    )


def _named_company_buyer(items: list[str]) -> bool:
    """Recognize nominative buyer company phrases, not accusative titles."""
    if any(_speaker_company(item) for item in items):
        return True
    for index, item in enumerate(items):
        if _company_title_accusative(item):
            continue
        if item in {"sirket", "firma", "ortaklik", "isletme", "istirak"}:
            return True
        if item.startswith(_COMPANY_TITLE_NOMINATIVE) and index > 0:
            return True
    return False


def _explicit_object(items: list[str]) -> bool:
    if _proper_name_accusative(items):
        return True
    for index, item in enumerate(items):
        if _company_title_accusative(item):
            return True
        if _speaker_company(item):
            continue
        if item.startswith(_COMPANY_TITLE_NOMINATIVE):
            if index > 0 and items[index - 1] in _COMPANY_OBJECT_MODIFIERS:
                return True
            continue
        if _transfer_token(item) and _object_inflection(item):
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


def _procurement_company_phrase(items: list[str]) -> bool | None:
    proc_positions = [i for i, item in enumerate(items) if _procurement_token(item)]
    if not proc_positions:
        return None
    if _producer_company_target(items):
        return True

    first_proc = proc_positions[0]
    company_positions = [
        i for i, item in enumerate(items)
        if _company_token(item) and i > first_proc
    ]
    for i in company_positions:
        item = items[i]
        if _speaker_company(item) or _company_locative(item):
            return False
    if not company_positions:
        return False

    company_index = company_positions[0]
    company = items[company_index]
    tail = items[company_index + 1 :]
    usage = _usage_in(tail)
    if _company_genitive(company) and any(_producer_link(item) for item in tail):
        return True
    if _company_genitive(company) and usage:
        return False
    if usage and any(
        item.startswith(("tesis", "fabrika", "santral", "depo", "istasyon", "merkez"))
        for item in tail
    ):
        return False
    return True


def _target_phrase_decision(items: list[str]) -> bool | None:
    if not items:
        return None
    proc = _procurement_company_phrase(items)
    if proc is not None:
        return proc
    if _producer_company_target(items):
        return True
    if _proper_name_accusative(items):
        return True
    for item in items:
        if _speaker_company(item) or _company_locative(item):
            continue
        if _company_title_accusative(item):
            return True
        if _transfer_token(item):
            return True
    return None


def _purchase_kind(token: str, after: list[str]) -> str:
    if token.startswith("alin"):
        return "passive"
    if token.startswith("aldig"):
        return "active_relative"
    if token.startswith("almis") and after and after[0].startswith("oldug"):
        return "active_relative"
    if token.startswith(("aldi", "alacak", "alacag", "aliyor", "alir", "almis")):
        return "active_finite"
    if token.startswith(("alma", "alim")):
        return "active_nominal"
    return "other"


def _left_clause(items: list[str], index: int) -> list[str]:
    left = 0
    for pos in range(index - 1, -1, -1):
        if items[pos] in _COORDINATORS:
            left = pos + 1
            break
    return items[left:index]


def _right_clause(items: list[str], index: int, next_index: int | None) -> list[str]:
    end = next_index if next_index is not None else len(items)
    candidate = items[index + 2 : end]
    for pos, item in enumerate(candidate):
        if item not in _COORDINATORS:
            continue
        tail = candidate[pos + 1 :]
        if any(
            _has_stem(tok, _USAGE_STEMS)
            or tok.startswith(
                ("aldi", "alacak", "aliyor", "alindi", "satti", "aciklandi",
                 "devral", "kullandi", "uretti", "kuruldu")
            )
            for tok in tail
        ):
            return candidate[:pos]
    return candidate


def satin_alma_is_acquisition(text: str) -> bool:
    for segment in segments(text):
        items = re.findall(r"\w+", segment)
        occurrences = [
            i for i in range(len(items) - 1)
            if items[i] == "satin" and items[i + 1].startswith("al")
        ]
        for occ_no, index in enumerate(occurrences):
            next_index = occurrences[occ_no + 1] if occ_no + 1 < len(occurrences) else None
            before = _left_clause(items, index)
            after = _right_clause(items, index, next_index)
            kind = _purchase_kind(items[index + 1], after)

            if kind == "passive":
                pre = _target_phrase_decision(before)
                post = _target_phrase_decision(after)
                if pre is True or post is True:
                    return True
                continue
            if kind == "active_relative":
                if _target_phrase_decision(after) is True:
                    return True
                continue
            if kind == "active_finite":
                if _explicit_object(before):
                    return True
                if _target_phrase_decision(after) is True:
                    return True
                if _named_company_buyer(before):
                    continue
                continue
            if kind == "active_nominal":
                pre_proc = _procurement_company_phrase(before)
                if pre_proc is False:
                    continue
                if _target_phrase_decision(after) is True:
                    return True
                if _named_company_possessor(before):
                    continue
                continue
    return False


def _board_decision_ranges(items: list[str], verb_index: int) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for start, item in enumerate(items[:verb_index]):
        if not item.startswith("yonetim"):
            continue
        if start + 1 >= verb_index or not items[start + 1].startswith("kurul"):
            continue
        for end in range(start + 2, verb_index):
            if items[end].startswith("karar"):
                ranges.append((start, end))
                break
    return ranges


def _inside_ranges(index: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= index <= end for start, end in ranges)


def _adjunct_indices(items: list[str], verb_index: int) -> set[int]:
    out: set[int] = set()
    for index, item in enumerate(items[:verb_index]):
        if item.startswith("adina") and index > 0:
            out.update({index - 1, index})
    return out


def _governance_object_before(items: list[str], verb_index: int) -> bool:
    board = _board_decision_ranges(items, verb_index)
    adjunct = _adjunct_indices(items, verb_index)
    for index, item in enumerate(items[:verb_index]):
        if index in adjunct or _inside_ranges(index, board):
            continue
        if _has_stem(item, _GOVERNANCE_STEMS) and _object_inflection(item):
            return True
    return False


def _acquisition_object_before(items: list[str], verb_index: int) -> bool:
    board = _board_decision_ranges(items, verb_index)
    adjunct = _adjunct_indices(items, verb_index)
    relevant = items[:verb_index]
    if _proper_name_accusative(relevant):
        return True
    for index, item in enumerate(relevant):
        if index in adjunct or _inside_ranges(index, board):
            continue
        if _company_title_accusative(item):
            return True
        if _speaker_company(item):
            continue
        if _transfer_token(item) and _object_inflection(item):
            return True
    return False


def devralma_has_acquisition_context(text: str) -> bool:
    for segment in segments(text):
        items = re.findall(r"\w+", segment)
        for index, item in enumerate(items):
            if not item.startswith("devral"):
                continue
            if item.startswith("devralin"):
                pre = _target_phrase_decision(items[:index])
                post = _target_phrase_decision(items[index + 1 :])
                if pre is True or post is True:
                    return True
                continue
            if item.startswith("devralma") and any(
                tok.startswith("islem") for tok in items[max(0, index - 3): index + 4]
            ):
                return True
            acquisition = _acquisition_object_before(items, index)
            governance = _governance_object_before(items, index)
            if acquisition:
                return True
            if governance:
                continue
            if _target_phrase_decision(items[index + 1 :]) is True:
                return True
    return False


def _right_noun(token: str) -> bool:
    if token.startswith(("hakkinda", "hakkimizda", "hakkinizda")):
        return False
    return token == "hak" or token.startswith(
        ("hakki", "hakkin", "hakka", "hakta", "haktan", "hakla", "hakkimiz", "hakkiniz")
    )


def _security_noun(token: str) -> bool:
    if token.startswith(("ipotekli", "rehinli", "teminatli")):
        return False
    return _has_stem(token, _SECURITY_STEMS)


def _physical_tesis_predicate(items: list[str], index: int) -> bool:
    tail = items[index + 1 : index + 6]
    return any(_has_stem(item, _PHYSICAL_PREDICATES) for item in tail)


def _tesis_governance_modifier(items: list[str], index: int) -> bool:
    tail = items[index + 1 : index + 4]
    return any(_has_stem(item, _GOVERNANCE_STEMS) and _object_inflection(item) for item in tail)


def _forward_created_right(items: list[str], index: int) -> bool:
    tail = items[index + 1 : index + 9]
    if not tail:
        return False
    if not any(item.startswith(("edil", "olustur")) for item in tail[:2]):
        return False
    return any(_right_noun(item) or _security_noun(item) for item in tail[1:])


def _existing_right_relation(between: list[str]) -> bool:
    if any(_has_stem(item, _RIGHT_TERMINATORS) for item in between):
        return True
    if any(item.startswith(("kapsamindaki", "bulunan", "mevcut", "uzerindeki")) for item in between):
        return True
    if any(item.startswith("konu") for item in between):
        return True
    if any(_has_stem(item, _PHYSICAL_HEAD_STEMS) for item in between):
        return True
    return False


def _backward_created_right(items: list[str], index: int) -> bool:
    for pos in range(index - 1, -1, -1):
        item = items[pos]
        if item in _COORDINATORS or item.startswith("tesis"):
            return False
        if _has_stem(item, _RIGHT_TERMINATORS):
            return False
        if _security_noun(item):
            between = items[pos + 1 : index]
            if any(_has_stem(tok, _PHYSICAL_HEAD_STEMS) for tok in between):
                return False
            return True
        if _right_noun(item):
            between = items[pos + 1 : index]
            if _existing_right_relation(between):
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
            if _tesis_governance_modifier(items, index):
                continue
            if _physical_tesis_predicate(items, index):
                return True
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
        if _physical_tesis_predicate(items, index):
            continue
        if _forward_created_right(items, index) or _backward_created_right(items, index):
            return True
    return False


def _capital_price_term_matches(subject: str, summary: str, term: str) -> bool:
    needle = normalize(term)
    for segment in segments(subject, summary):
        items = re.findall(r"\w+", segment)
        if not any(item.startswith(needle) for item in items):
            continue
        if _segment_has_legal_tesis(segment):
            continue
        if _CAPITAL_CONTEXT_RE.search(segment):
            return True
        return True
    return False


def _split_is_corporate(subject: str, summary: str) -> bool:
    for segment in segments(subject):
        items = re.findall(r"\w+", segment)
        for index, item in enumerate(items):
            if not item.startswith("bolun"):
                continue
            if item.startswith("bolunmus") and any(
                tok.startswith(("yol", "karayol")) for tok in items[index + 1 : index + 4]
            ):
                continue
            before = items[:index]
            if any(_has_stem(tok, _DEBT_STEMS) for tok in before):
                continue
            if any(tok.startswith(("dosya", "veri", "yol", "karayol", "hat", "trafik")) for tok in before):
                continue
            if (
                index == 0
                or any(tok.startswith("islem") for tok in items[index + 1 : index + 3])
                or all(tok in {"kismi", "tam", "kolaylastirilmis"} for tok in before)
            ):
                return True

    for segment in segments(subject, summary):
        items = re.findall(r"\w+", segment)
        for index, item in enumerate(items):
            if not item.startswith("bolun"):
                continue
            tail = items[index + 1 : index + 4]
            if item.startswith("bolunmus") and any(tok.startswith(("yol", "karayol")) for tok in tail):
                continue
            before = items[max(0, index - 7): index]
            if any(_has_stem(tok, _DEBT_STEMS) for tok in before):
                continue
            if any(tok.startswith(("dosya", "veri", "yol", "karayol", "hat", "trafik", "parca")) for tok in before):
                if not any(_company_token(tok) for tok in before):
                    continue
            corporate = any(
                _company_token(tok)
                or tok.startswith(("pay", "hisse", "sermaye", "holding", "grup"))
                for tok in items[max(0, index - 7): index + 7]
            ) or _named_company_possessor(before)
            if corporate:
                return True
    return False


def _operational_merge_object(items: list[str], index: int) -> bool:
    before = items[max(0, index - 7): index]
    operational_heads = ("hat", "dosya", "veri", "sistem", "trafik", "yol", "karayol")
    for pos, item in enumerate(before):
        if _has_stem(item, operational_heads) and _object_inflection(item):
            return True
        if item.startswith("uretim") and pos + 1 < len(before):
            if _has_stem(before[pos + 1], operational_heads) and _object_inflection(before[pos + 1]):
                return True
    return False


def _merger_is_corporate(subject: str, summary: str) -> bool:
    for segment in segments(subject):
        items = re.findall(r"\w+", segment)
        if items and items[0].startswith("birles"):
            if len(items) <= 2 or any(tok.startswith("islem") for tok in items[1:]):
                return True
    for segment in segments(subject, summary):
        items = re.findall(r"\w+", segment)
        for index, item in enumerate(items):
            if item.startswith("birlesik") or not item.startswith("birles"):
                continue
            if _operational_merge_object(items, index):
                continue
            nearby = items[max(0, index - 7): index + 7]
            corporate = any(
                _company_token(tok)
                or tok.startswith(("pay", "hisse", "sermaye", "holding", "grup"))
                for tok in nearby
            )
            operational = any(
                tok.startswith(("hat", "dosya", "veri", "sistem", "trafik", "yol"))
                for tok in nearby
            )
            if operational and not corporate:
                continue
            if corporate:
                return True
    return False


def _rotational_devir(items: list[str], index: int) -> bool:
    nearby = items[max(0, index - 4): index + 5]
    return any(tok.startswith("motor") for tok in nearby) and any(
        _has_stem(tok, ("hiz", "rpm", "dakika", "donus")) for tok in nearby
    )


def _devir_object(items: list[str], index: int) -> bool:
    before = items[max(0, index - 7): index]
    after = items[index + 1 : index + 5]
    if _proper_name_accusative(before):
        return True
    for item in before + after:
        if _speaker_company(item):
            continue
        if _company_title_accusative(item):
            return True
        if _transfer_token(item) and _object_inflection(item):
            return True
        if _company_genitive(item):
            return True
    return any(
        _transfer_token(item)
        and not _company_token(item)
        and not _speaker_company(item)
        for item in before[-3:]
    )


def _devir_is_acquisition(subject: str, summary: str) -> bool:
    for segment in segments(subject, summary):
        items = re.findall(r"\w+", segment)
        for index, item in enumerate(items):
            if item.startswith(("devrim", "devriye", "devirdaim", "devreye")):
                continue
            if not item.startswith(("devir", "devri", "devred", "devret")):
                continue
            if _rotational_devir(items, index):
                continue
            nearby = items[max(0, index - 6): index + 7]
            governance = any(_has_stem(tok, _GOVERNANCE_STEMS) for tok in nearby)
            explicit = _devir_object(items, index)
            if governance and not explicit:
                continue
            if explicit:
                return True
    return False


def _share_repurchase(subject: str, summary: str) -> bool:
    for segment in segments(subject, summary):
        items = re.findall(r"\w+", segment)
        for index in range(len(items) - 1):
            if items[index] != "geri" or not items[index + 1].startswith("al"):
                continue
            nearby = items[max(0, index - 6): index + 8]
            if any(tok.startswith(("pay", "hisse")) for tok in nearby):
                return True
            if any(_has_stem(tok, _DEBT_STEMS) for tok in nearby):
                continue
            if any(_has_stem(tok, _PRODUCT_STEMS) for tok in nearby):
                continue
            return True
    return False


def _ceza_matches(text: str) -> bool:
    accepted = {
        "ceza", "cezai", "cezasi", "cezasina", "cezasini", "cezasinda",
        "cezasindan", "cezasinin", "cezanin", "cezaya", "cezayi", "cezada",
        "cezadan", "cezalar", "cezalari", "cezalarina", "cezalarini",
        "cezalarinda", "cezalarindan", "cezalarin",
    }
    return any(
        token in accepted or token.startswith("cezalandir")
        for token in re.findall(r"\w+", text)
    )


def _commercial_contract_matches(subject: str, summary: str) -> bool:
    segs = segments(subject, summary)
    articles_present = any(_ARTICLES_RE.search(seg) for seg in segs)
    contract_cues = (
        "tedarik", "muster", "satis", "hizmet", "ihale", "siparis", "imzalan",
        "imzal", "anlasma", "yeni", "ticari", "sozlesme yap",
    )
    for seg in segs:
        if not re.search(r"(?<!\w)sozlesme\w*", seg):
            continue
        if _ARTICLES_RE.search(seg):
            continue
        if not articles_present:
            return True
        if any(cue in seg for cue in contract_cues):
            return True
    return False


def _ownership_ortaklik_matches(subject: str, summary: str) -> bool:
    for seg in segments(subject, summary):
        items = re.findall(r"\w+", seg)
        if not any(tok.startswith(("ortaklik", "ortaklig")) for tok in items):
            continue
        if any(
            tok.startswith(
                ("pay", "hisse", "sermaye", "hakim", "kontrol", "oran", "satis",
                 "satim", "alim", "edin", "devr", "yapi", "degis")
            )
            for tok in items
        ):
            return True
    return False


def term_matches(subject: str, summary: str, term: str) -> bool:
    needle = normalize(term)
    text = normalize(f"{subject} {summary}")
    if needle == "yatirim":
        return re.search(r"(?<!\w)yatirim(?!ci)", text) is not None
    if needle == "ceza":
        return _ceza_matches(text)
    if needle == "birlesme":
        return _merger_is_corporate(subject, summary)
    if needle == "bolunme":
        return _split_is_corporate(subject, summary)
    if needle == "satin alma":
        return satin_alma_is_acquisition(f"{subject}. {summary}")
    if needle == "devralma":
        return devralma_has_acquisition_context(f"{subject}. {summary}")
    if needle == "devir":
        return _devir_is_acquisition(subject, summary)
    if needle in {"geri alim", "pay geri alim"}:
        return _share_repurchase(subject, summary)
    if needle == "sozlesme":
        return _commercial_contract_matches(subject, summary)
    if needle == "tesis":
        return tesis_is_operational(f"{subject}. {summary}")
    if needle == "pay alim satim":
        return _PAY_TRADING_RE.search(text) is not None
    if needle in {"bedelsiz", "bedelli"}:
        return _capital_price_term_matches(subject, summary, needle)
    if needle == "ortaklik":
        return _ownership_ortaklik_matches(subject, summary)
    return needle in text


def _procurement_operation(subject: str, summary: str) -> bool:
    text = f"{subject}. {summary}"
    all_items = tokens(text)
    if not any(_procurement_token(item) for item in all_items):
        return False
    purchase_present = any(
        items[index] == "satin" and items[index + 1].startswith("al")
        for segment in segments(text)
        for items in [re.findall(r"\w+", segment)]
        for index in range(len(items) - 1)
    )
    passive_takeover = any(item.startswith("devralin") for item in all_items)
    if purchase_present and not satin_alma_is_acquisition(text):
        return True
    if passive_takeover and not devralma_has_acquisition_context(text):
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
    for candidate, weight, terms in event_rules:
        if weight <= score:
            continue
        if any(term_matches(subject, summary, term) for term in terms):
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
    return term_matches(text, "", term)
