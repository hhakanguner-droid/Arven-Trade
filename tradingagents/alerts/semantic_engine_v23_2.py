"""Round 23.2 root-cause semantic engine for consolidated Turkish KAP semantics.

The module keeps one deterministic decision layer for grammar-sensitive event
types and delegates only unaffected generic terms to the Round 23.1 engine.
"""

from __future__ import annotations

import re
from typing import Iterable

from . import semantic_engine_v23 as _base
from . import semantic_engine_v23_1 as _prev

_COMPANY_PREFIXES = ("sirket", "firma", "ortaklik", "ortaklig", "isletme", "istirak")
_SPEAKER_COMPANY_PREFIXES = ("sirketimiz", "firmamiz", "ortakligimiz", "isletmemiz", "istirakimiz")
_TRANSFER_PREFIXES = (
    "pay", "hisse", "varlik", "varlig", "isletme", "istirak",
    "ortaklik", "ortaklig", "sirket", "firma", "marka", "portfoy",
    "fabrika", "tesis", "gayrimenkul",
)
_PROCUREMENT_PREFIXES = (
    "elektrik", "enerji", "dogalgaz", "gaz", "hammadde", "malzeme",
    "hizmet", "ekipman", "makine", "urun", "mal", "yakit", "parca",
    "tedarik", "lisans", "yazilim", "mobilya", "bilgisayar", "cihaz",
    "stok", "emtia", "arac",
)
_GOVERNANCE_PREFIXES = ("yonetim", "yetki", "gorev", "sorumluluk", "imza", "makam", "kurul")
_OPERATIONAL_OBJECT_PREFIXES = (
    "hat", "uretim", "dosya", "veri", "sistem", "trafik", "yol",
    "karayol", "siparis", "depo", "akim", "boru", "kablo",
)
_DEBT_PREFIXES = ("borc", "kredi", "tahvil", "bono", "finansman")
_PRODUCT_PREFIXES = ("urun", "mal", "parti", "seri", "tuketici", "arac", "cihaz", "gida")
_PHYSICAL_HEAD_PREFIXES = (
    "liman", "maden", "fabrika", "santral", "depo", "yapi", "bina",
    "terminal", "merkez", "istasyon", "hat", "kampus", "saha",
)
_RIGHT_PREFIXES = (
    "hak", "hakki", "hakkin", "hakka", "hakta", "haktan", "hakla",
    "hakkimiz", "hakkiniz", "intifa", "irtifak", "ipotek", "rehin",
    "teminat", "haciz", "kefalet",
)
_ARTICLES_RE = re.compile(r"(?<!\w)(?:esas|ana)\s+sozlesme\w*")
_ACCUSATIVE_ENDINGS = (
    "ini", "unu", "yi", "yu", "lari", "leri", "larini", "lerini",
)
_COORDINATORS = {"ve", "ancak", "fakat", "ayrica", "sonra", "ardindan"}
_FINITE_STEMS = (
    "aldi", "alacak", "aliyor", "alir", "almis",
    "devraldi", "devralacak", "devralir", "devralmis",
    "yuksel", "dus", "acikla", "kullan", "sagla", "sonuclandir",
    "birles", "bolun", "devret", "devred", "kurul", "satil", "kiralan",
    "feshed", "imzalan", "tamamlan", "artti", "azal", "yayinlan", "duyurul",
)
_PARTICIPLE_PREFIXES = (
    "alinan", "alinacak", "alinmis", "devralinan", "devralinacak",
    "devralinmis", "olan", "oldugu",
)
_RIGHT_RELATION_BLOCKERS = (
    "bulunan", "mevcut", "kapsamindaki", "uzerindeki", "konu", "sahip",
)


def normalize(value: str) -> str:
    return _base.normalize(value)


def tokens(value: str) -> list[str]:
    return re.findall(r"\w+", normalize(value))


def segments(*values: str) -> list[str]:
    return _base.segments(*values)


def _raw_sentences(value: str) -> list[str]:
    protected = _base._protect_abbreviations(str(value))
    out: list[str] = []
    for part in re.split(r"[.!?;\n]+", protected):
        normalized = normalize(part).strip()
        if normalized:
            out.append(normalized)
    return out


def _looks_finite(token: str) -> bool:
    if token.startswith(_PARTICIPLE_PREFIXES):
        return False
    if token in {"aldi", "alacak", "aliyor", "alir", "almis"}:
        return True
    return token.startswith(_FINITE_STEMS)


def _has_finite_predicate(items: list[str]) -> bool:
    return any(_looks_finite(item) for item in items)


def _split_coordinated_items(items: list[str]) -> list[list[str]]:
    """Split only coordinators that join two predicate-bearing clauses.

    This keeps modifier lists such as "halka açık ve yabancı sermayeli şirket"
    and compound objects such as "üretim hattı ve depoları birleştirdi" intact,
    while separating "satın aldı ve ... yükseldi".
    """
    out: list[list[str]] = []
    start = 0
    for index, item in enumerate(items):
        if item not in _COORDINATORS:
            continue
        left = items[start:index]
        right = items[index + 1 :]
        if left and right and _has_finite_predicate(left) and _has_finite_predicate(right):
            out.append(left)
            start = index + 1
    tail = items[start:]
    if tail:
        out.append(tail)
    return out


def _clauses(value: str) -> list[str]:
    out: list[str] = []
    for sentence in _raw_sentences(value):
        for comma_part in sentence.split(","):
            items = re.findall(r"\w+", comma_part)
            for clause_items in _split_coordinated_items(items):
                if clause_items:
                    out.append(" ".join(clause_items))
    return out


def _has_prefix(token: str, prefixes: tuple[str, ...]) -> bool:
    return token.startswith(prefixes)


def _company_token(token: str) -> bool:
    return _has_prefix(token, _COMPANY_PREFIXES)


def _speaker_company(token: str) -> bool:
    return _has_prefix(token, _SPEAKER_COMPANY_PREFIXES)


def _company_locative(token: str) -> bool:
    return _company_token(token) and token.endswith(
        ("de", "da", "te", "ta", "nde", "nda", "inde", "inda", "lerinde", "larinda")
    )


def _procurement_token(token: str) -> bool:
    return _has_prefix(token, _PROCUREMENT_PREFIXES)


def _transfer_token(token: str) -> bool:
    return _has_prefix(token, _TRANSFER_PREFIXES)


def _governance_token(token: str) -> bool:
    if token.startswith(("kurulacak", "kuruldu", "kuruluyor", "kurulmas", "kurulm")):
        return False
    return _has_prefix(token, _GOVERNANCE_PREFIXES)


def _object_inflected(token: str) -> bool:
    if token.endswith(_ACCUSATIVE_ENDINGS):
        return True
    return token.startswith(
        (
            "sirketini", "firmasini", "ortakligi", "ortakligini", "isletmesini",
            "istiraki", "istirakini", "varligi", "varligini", "paylari",
            "paylarini", "hisseleri", "hisselerini",
        )
    )


def _genitive_company(token: str) -> bool:
    return token.startswith(
        (
            "sirketinin", "firmanin", "firmasinin", "ortakligin", "ortakliginin",
            "isletmenin", "isletmesinin", "istirakin", "istirakinin",
        )
    )


def _named_legal_company_genitive(items: list[str]) -> bool:
    if not any(token in {"as", "ltd", "sti"} for token in items):
        return False
    return any(token in {"in", "nin", "un", "nun"} for token in items[-4:])


def _proper_accusative(items: list[str]) -> bool:
    for index, item in enumerate(items):
        if item in {"i", "yi", "u", "yu", "ni", "nu"} and index > 0:
            previous = items[index - 1]
            if previous not in {"sirket", "firma", "ortaklik", "isletme", "istirak"}:
                return True
    return False


def _explicit_transfer_object(items: list[str]) -> bool:
    if _proper_accusative(items):
        return True
    return any(
        _transfer_token(item)
        and _object_inflected(item)
        and not _speaker_company(item)
        and not _genitive_company(item)
        for item in items
    )


def _producer_company_phrase(items: list[str]) -> bool:
    for start, item in enumerate(items):
        if not _procurement_token(item):
            continue
        relation = False
        for candidate in items[start + 1 :]:
            if candidate.startswith(("kullan", "tuket", "yak", "harca")):
                break
            if candidate.startswith(
                (
                    "uretic", "imalatc", "gelistiric", "tedarikc", "saglayic",
                    "dagitic", "ureten", "uretil", "uretm", "urettig", "ureteceg",
                    "uretmus", "uretmis",
                )
            ):
                relation = True
                continue
            if relation and _company_token(candidate):
                return not _speaker_company(candidate) and not _company_locative(candidate)
    return False


def _company_agent_indices(items: list[str]) -> set[int]:
    out: set[int] = set()
    for index, item in enumerate(items[:-1]):
        if _company_token(item) and items[index + 1].startswith("tarafindan"):
            out.add(index)
            out.add(index + 1)
    return out


def _procurement_before_purchase(items: list[str]) -> bool:
    return any(_procurement_token(item) for item in items)


def _company_genitive_possesses_procurement(items: list[str]) -> bool:
    for index, item in enumerate(items):
        if not _genitive_company(item):
            continue
        tail = items[index + 1 :]
        if any(_procurement_token(token) for token in tail) and not _explicit_transfer_object(tail):
            return True
    return False


def _industry_company_target(items: list[str]) -> bool:
    procurement_positions = [
        index for index, item in enumerate(items) if _procurement_token(item)
    ]
    if not procurement_positions:
        return False
    first_procurement = procurement_positions[0]
    agent = _company_agent_indices(items)
    return any(
        index > first_procurement
        and index not in agent
        and _company_token(item)
        and not _speaker_company(item)
        and not _company_locative(item)
        for index, item in enumerate(items)
    )


def _nominal_pre_target(before: list[str], after: list[str]) -> bool:
    if _explicit_transfer_object(before):
        return True
    if any(item.startswith("ihale") for item in after):
        return False
    if _named_legal_company_genitive(before):
        return True
    if _industry_company_target(before):
        return True
    if any(_procurement_token(item) for item in before):
        return False
    return any(
        (_company_token(item) or _transfer_token(item))
        and not _speaker_company(item)
        and not _genitive_company(item)
        for item in before
    )


def _post_purchase_target(after: list[str]) -> bool:
    if not after:
        return False

    agent = _company_agent_indices(after)
    if _producer_company_phrase(after):
        return True

    procurement_positions = [i for i, item in enumerate(after) if _procurement_token(item)]
    if procurement_positions:
        first_proc = procurement_positions[0]
        for index in range(first_proc + 1, len(after)):
            item = after[index]
            if index in agent:
                continue
            if _speaker_company(item) or _company_locative(item):
                return False
            if _company_token(item):
                tail = after[index + 1 :]
                if any(token.startswith(("kullan", "tuket", "yak", "harca")) for token in tail):
                    if item.endswith(("in", "inin", "nin")) and any(
                        token.startswith(("uret", "sagla", "sat")) for token in tail
                    ):
                        return True
                    return False
                return True
        return False

    for index, item in enumerate(after):
        if index in agent or _speaker_company(item) or _company_locative(item):
            continue
        if _transfer_token(item) or _company_token(item):
            return True
    return False


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


def _passive_pre_target(before: list[str]) -> bool:
    if not before:
        return False

    # Strong grammatical evidence must win before procurement/possessor guards.
    if _explicit_transfer_object(before):
        return True
    if _producer_company_phrase(before):
        return True
    if _named_legal_company_genitive(before):
        return True

    agent = _company_agent_indices(before)
    if _procurement_before_purchase(before):
        if _industry_company_target(before):
            return True
        if _company_genitive_possesses_procurement(before):
            return False
        if agent:
            return False
        return False

    for index, item in enumerate(before):
        if index in agent:
            continue
        if _genitive_company(item):
            if not any(
                _procurement_token(token) or _transfer_token(token)
                for token in before[index + 1 :]
            ):
                return True

    return any(
        (_company_token(item) or _transfer_token(item))
        and index not in agent
        and not _speaker_company(item)
        for index, item in enumerate(before)
    )


def satin_alma_is_acquisition(text: str) -> bool:
    for clause in _clauses(text):
        items = re.findall(r"\w+", clause)
        occurrences = [
            index
            for index in range(len(items) - 1)
            if items[index] == "satin" and items[index + 1].startswith("al")
        ]
        for index in occurrences:
            purchase_token = items[index + 1]
            before = items[:index]
            after = items[index + 2 :]
            kind = _purchase_kind(purchase_token, after)

            if kind == "passive":
                if _post_purchase_target(after) or _passive_pre_target(before):
                    return True
                continue

            if kind == "active_relative":
                if _post_purchase_target(after):
                    return True
                continue

            if kind == "active_finite":
                if _explicit_transfer_object(before) or _post_purchase_target(after):
                    return True
                continue

            if kind == "active_nominal":
                if _nominal_pre_target(before, after) or _post_purchase_target(after):
                    return True
                continue

    return False


def _board_decision_span(items: list[str]) -> set[int]:
    out: set[int] = set()
    for start, item in enumerate(items):
        if not item.startswith("yonetim"):
            continue
        if start + 1 >= len(items) or not items[start + 1].startswith("kurul"):
            continue
        for end in range(start + 2, min(len(items), start + 7)):
            if items[end].startswith("karar"):
                out.update(range(start, end + 1))
                break
    return out


def _adjunct_span(items: list[str]) -> set[int]:
    out: set[int] = set()
    for index, item in enumerate(items):
        if item.startswith("adina") and index > 0:
            out.add(index - 1)
            out.add(index)
    return out


def _governance_object(items: list[str]) -> bool:
    board = _board_decision_span(items)
    adjunct = _adjunct_span(items)
    for index, item in enumerate(items):
        if index in board or index in adjunct:
            continue
        if _governance_token(item) and _object_inflected(item):
            return True
    return False


def _devralma_transfer_object(items: list[str]) -> bool:
    board = _board_decision_span(items)
    adjunct = _adjunct_span(items)
    for index, item in enumerate(items):
        if index in board or index in adjunct:
            continue
        if (
            _transfer_token(item)
            and _object_inflected(item)
            and not _speaker_company(item)
            and not _genitive_company(item)
        ):
            return True
    return _proper_accusative(items)


def _passive_devralma_target(before: list[str], after: list[str]) -> bool:
    if _devralma_transfer_object(before):
        return True
    if _producer_company_phrase(before):
        return True

    if _procurement_before_purchase(before):
        if _company_genitive_possesses_procurement(before):
            return False
        if _company_agent_indices(before):
            return False
        return False

    if any(_company_token(item) and not _speaker_company(item) for item in before):
        return True

    if _procurement_before_purchase(after):
        return _producer_company_phrase(after)
    agent = _company_agent_indices(after)
    return any(
        (_company_token(item) or _transfer_token(item))
        and index not in agent
        and not _speaker_company(item)
        and not _company_locative(item)
        for index, item in enumerate(after)
    )


def devralma_has_acquisition_context(text: str) -> bool:
    for clause in _clauses(text):
        items = re.findall(r"\w+", clause)
        for index, item in enumerate(items):
            if not item.startswith("devral"):
                continue

            before = items[:index]
            after = items[index + 1 :]

            if item.startswith("devralin"):
                if _passive_devralma_target(before, after):
                    return True
                continue

            if item.startswith("devralma"):
                if _devralma_transfer_object(before) or _post_purchase_target(after):
                    return True
                continue

            transfer = _devralma_transfer_object(before)
            governance = _governance_object(before)
            if transfer:
                return True
            if governance:
                continue
            if _post_purchase_target(after):
                return True

    return False


def _right_noun(token: str) -> bool:
    if token.startswith(("hakkinda", "hakkimizda", "hakkinizda")):
        return False
    return token.startswith(_RIGHT_PREFIXES)


def _legal_tesis_clause(items: list[str], tesis_index: int) -> bool:
    # Passive-relative order: "Tesis edilen kullanım hakkı".
    tail = items[tesis_index + 1 : tesis_index + 8]
    if tail and tail[0].startswith(("edil", "olustur")):
        if any(_right_noun(token) for token in tail[1:]):
            return True

    # A physical facility head immediately governs "tesis".
    if tesis_index > 0 and _has_prefix(items[tesis_index - 1], _PHYSICAL_HEAD_PREFIXES):
        return False

    # Governance-object usage: "tesis yönetimini devraldı".
    if any(_governance_token(token) for token in items[tesis_index + 1 : tesis_index + 3]):
        return False

    # Backward right-creation syntax: "hakkının ... tesisi".  Relational
    # participles indicate an existing right governing a physical facility.
    for right_index in range(tesis_index - 1, -1, -1):
        token = items[right_index]
        if not _right_noun(token):
            continue
        between = items[right_index + 1 : tesis_index]
        if any(_has_prefix(part, _PHYSICAL_HEAD_PREFIXES) for part in between):
            return False
        if any(part.startswith(_RIGHT_RELATION_BLOCKERS) for part in between):
            return False
        return True

    return False


def tesis_is_operational(text: str) -> bool:
    found = False
    for sentence in _raw_sentences(text):
        items = re.findall(r"\w+", sentence)
        for index, item in enumerate(items):
            if not item.startswith("tesis"):
                continue
            found = True
            if any(_governance_token(token) for token in items[index + 1 : index + 3]):
                continue
            if _legal_tesis_clause(items, index):
                continue
            return True
    return False if found else False


def _segment_legal_tesis(segment: str) -> bool:
    items = re.findall(r"\w+", normalize(segment))
    for index, item in enumerate(items):
        if item.startswith("tesis") and _legal_tesis_clause(items, index):
            return True
    return False


def _capital_price_matches(subject: str, summary: str, term: str) -> bool:
    needle = normalize(term)
    for segment in _base.segments(subject, summary):
        items = re.findall(r"\w+", segment)
        if not any(item.startswith(needle) for item in items):
            continue
        if _segment_legal_tesis(segment):
            continue
        if any(item.startswith(("sermaye", "pay", "hisse")) for item in items):
            return True
        if any(item.startswith("artir") for item in items):
            return True
    return False


def _split_is_corporate(subject: str, summary: str) -> bool:
    subject_items = re.findall(r"\w+", normalize(_base._protect_abbreviations(subject)))
    if subject_items:
        if (
            subject_items[0].startswith("bolun")
            or (
                len(subject_items) >= 2
                and subject_items[0] in {"kismi", "tam"}
                and subject_items[1].startswith("bolun")
            )
        ):
            if any(
                _has_prefix(item, ("dosya", "veri", "yol", "karayol", "arsiv", "set"))
                for item in subject_items
            ):
                return False
            return True
        if any(item.startswith("bolun") for item in subject_items) and _named_legal_company_genitive(subject_items):
            return True

    for segment in _base.segments(subject, summary):
        items = re.findall(r"\w+", segment)
        for index, item in enumerate(items):
            if not item.startswith("bolun"):
                continue
            nearby = items[max(0, index - 7) : index + 7]
            if any(_has_prefix(token, _DEBT_PREFIXES) for token in nearby):
                continue
            if item.startswith("bolunmus") and any(
                _has_prefix(token, ("dosya", "veri", "yol", "karayol", "arsiv", "set"))
                for token in nearby
            ):
                continue
            if any(
                _company_token(token)
                or token.startswith(("pay", "hisse", "sermaye", "holding", "grup"))
                for token in nearby
            ):
                return True
    return False


def _operational_merger_object(items: list[str], index: int) -> bool:
    before = items[max(0, index - 8) : index]
    for token in before:
        if not _has_prefix(token, _OPERATIONAL_OBJECT_PREFIXES):
            continue
        if token.endswith(
            ("lari", "leri", "larini", "lerini", "larinin", "lerinin", "in", "nin")
        ):
            return True
    return False


def _merger_is_corporate(subject: str, summary: str) -> bool:
    subject_items = tokens(subject)
    if subject_items and subject_items[0].startswith("birles") and len(subject_items) <= 2:
        return True

    for segment in _base.segments(subject, summary):
        items = re.findall(r"\w+", segment)
        for index, item in enumerate(items):
            if item.startswith("birlesik") or not item.startswith("birles"):
                continue
            if _operational_merger_object(items, index):
                continue
            nearby = items[max(0, index - 6) : index + 7]
            if any(
                _company_token(token)
                or token.startswith(("pay", "hisse", "sermaye", "holding", "grup"))
                for token in nearby
            ):
                return True
    return False


def _devir_is_acquisition(subject: str, summary: str) -> bool:
    for clause in _clauses(f"{subject}. {summary}"):
        items = re.findall(r"\w+", clause)
        for index, item in enumerate(items):
            if item.startswith(("devrim", "devriye", "devirdaim", "devreye")):
                continue
            if not item.startswith(("devir", "devri", "devred", "devret")):
                continue

            nearby = items[max(0, index - 7) : index + 8]
            if any(token.startswith(("motor", "rpm", "donus")) for token in nearby) and any(
                token.startswith(("hiz", "devir")) for token in nearby
            ):
                continue

            governance = any(_governance_token(token) for token in nearby)
            explicit = any(
                _transfer_token(token)
                and _object_inflected(token)
                and not _genitive_company(token)
                for token in nearby
            )
            if governance and not explicit:
                continue

            after = items[index + 1 :]
            if any(_company_token(token) and not _speaker_company(token) for token in after):
                return True

            # Nominal transfer heading: "Gayrimenkul/Marka/Portföy/Fabrika/Tesis Devri".
            if index > 0 and _transfer_token(items[index - 1]) and not _genitive_company(items[index - 1]):
                return True

            if any(
                _transfer_token(token)
                and _object_inflected(token)
                and not _genitive_company(token)
                for token in nearby
            ):
                return True

            if any(_genitive_company(token) for token in nearby) and not governance:
                return True
    return False


def _share_repurchase(subject: str, summary: str) -> bool:
    for segment in _base.segments(subject, summary):
        items = re.findall(r"\w+", segment)
        for index in range(len(items) - 1):
            if items[index] != "geri" or not items[index + 1].startswith("al"):
                continue
            nearby = items[max(0, index - 6) : index + 9]

            # Explicit share syntax outranks unrelated debt/product mentions.
            if any(item.startswith(("pay", "hisse")) for item in nearby):
                return True

            if any(_has_prefix(item, _DEBT_PREFIXES) for item in nearby):
                continue
            if any(_has_prefix(item, _PRODUCT_PREFIXES) for item in nearby):
                continue
            if any(item.startswith("program") for item in nearby):
                return True
    return False


def _contract_segments(value: str) -> list[str]:
    protected = _base._protect_abbreviations(str(value))
    protected = re.sub(r"(?<=\d)\.(?=\s*[A-Za-zÇĞİÖŞÜçğıöşü])", " ", protected)
    return [
        normalize(part).strip()
        for part in re.split(r"[,!?;:\n]+|\.(?=\s+[A-Za-zÇĞİÖŞÜçğıöşü])", protected)
        if normalize(part).strip()
    ]


def _contract_matches(subject: str, summary: str) -> bool:
    articles_subject = _ARTICLES_RE.search(normalize(subject)) is not None
    for value in (subject, summary):
        for segment in _contract_segments(value):
            if not re.search(r"(?<!\w)sozlesme\w*", segment):
                continue
            if _ARTICLES_RE.search(segment):
                continue
            items = re.findall(r"\w+", segment)
            if articles_subject and any(item.startswith(("madde", "tadil")) for item in items):
                continue
            return True
    return False


def _ownership_ortaklik_matches(subject: str, summary: str) -> bool:
    for segment in _base.segments(subject, summary):
        items = re.findall(r"\w+", segment)
        if not any(item.startswith(("ortaklik", "ortaklig")) for item in items):
            continue

        if any(
            item.startswith(("pay", "hisse", "sermaye", "hakim", "kontrol", "oran", "yapi", "degis"))
            for item in items
        ):
            return True

        for index, item in enumerate(items[:-1]):
            if not item.startswith("ortakligin"):
                continue
            sale = items[index + 1]
            if sale.startswith(("satisi", "satilmas")):
                return True
    return False


def term_matches(subject: str, summary: str, term: str) -> bool:
    needle = normalize(term)
    if needle == "satin alma":
        return satin_alma_is_acquisition(f"{subject}. {summary}")
    if needle == "devralma":
        return devralma_has_acquisition_context(f"{subject}. {summary}")
    if needle == "devir":
        return _devir_is_acquisition(subject, summary)
    if needle == "tesis":
        return tesis_is_operational(f"{subject}. {summary}")
    if needle in {"bedelsiz", "bedelli"}:
        return _capital_price_matches(subject, summary, needle)
    if needle == "birlesme":
        return _merger_is_corporate(subject, summary)
    if needle == "bolunme":
        return _split_is_corporate(subject, summary)
    if needle in {"geri alim", "pay geri alim"}:
        return _share_repurchase(subject, summary)
    if needle == "sozlesme":
        return _contract_matches(subject, summary)
    if needle == "ortaklik":
        return _ownership_ortaklik_matches(subject, summary)
    return _prev.term_matches(subject, summary, term)


def _procurement_operation(subject: str, summary: str) -> bool:
    text = f"{subject}. {summary}"
    all_tokens = tokens(text)
    if not any(_procurement_token(item) for item in all_tokens):
        return False

    passive_or_relative_purchase = False
    for clause in _clauses(text):
        items = re.findall(r"\w+", clause)
        for index in range(len(items) - 1):
            if items[index] != "satin" or not items[index + 1].startswith("al"):
                continue
            kind = _purchase_kind(items[index + 1], items[index + 2 :])
            if kind in {"passive", "active_relative"}:
                passive_or_relative_purchase = True

    passive_takeover_present = any(item.startswith("devralin") for item in all_tokens)

    if passive_or_relative_purchase and not satin_alma_is_acquisition(text):
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
