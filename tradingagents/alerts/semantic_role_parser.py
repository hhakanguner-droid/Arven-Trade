"""Role-aware semantic parser for Turkish KAP alert classification.

This module replaces the accreted phrase heuristics with a small role parser:
clause -> predicate -> agent/vendor -> object -> event decision.
Only grammar-sensitive event families are handled here; unrelated generic event
terms delegate to semantic_engine_v23_1.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable

from . import semantic_engine_v23_1 as _prev

IMPLEMENTATION_GENERATION = object()

_TURKISH = str.maketrans({
    "ı":"i","İ":"i","I":"i","ş":"s","Ş":"s","ğ":"g","Ğ":"g",
    "ü":"u","Ü":"u","ö":"o","Ö":"o","ç":"c","Ç":"c",
})

_COMPANY = ("sirket","firma","ortaklik","ortaklig","isletme","istirak")
_SPEAKER = ("sirketimiz","firmamiz","ortakligimiz","isletmemiz","istirakimiz")
_TRANSFER = ("pay","hisse","varlik","varlig","isletme","istirak","ortaklik","ortaklig",
             "sirket","firma","marka","portfoy","fabrika","tesis","gayrimenkul","tasinmaz")
_PROCURE = ("elektrik","enerji","dogalgaz","gaz","hammadde","malzeme","hizmet","ekipman",
            "makine","urun","mal","yakit","parca","tedarik","lisans","yazilim","mobilya",
            "bilgisayar","cihaz","stok","emtia","arac")
_GOV = ("yonetim","yetki","gorev","sorumluluk","imza","makam","kurul")
_OPERATIONAL = ("hat","uretim","dosya","veri","sistem","trafik","yol","karayol",
                "siparis","depo","akim","boru","kablo")
_DEBT = ("borc","kredi","tahvil","bono","finansman")
_PRODUCT = ("urun","mal","parti","seri","tuketici","arac","cihaz","gida")
_PHYSICAL_HEAD = ("liman","maden","fabrika","santral","depo","yapi","bina","terminal",
                  "merkez","istasyon","hat","kampus","saha")
_RIGHT = ("hak","hakki","hakkin","hakka","hakta","haktan","hakla","hakkimiz","hakkiniz",
          "intifa","irtifak","ipotek","rehin","teminat","haciz","kefalet")
_AGENT_MARKERS = ("tarafindan","araciligiyla","vasitasiyla","kanaliyla","eliyle")
_ORG_UNITS = ("departman","birim","ekip","mudurluk","mudurlugu","direktorluk","ofis",
              "komite","fonksiyon","organizasyon","politika","prosedur")
_POSTPOSITIONS = ("icin","uzere","ait","dair","iliskin","kapsaminda","yonelik","hakkinda")
_SALE_ASSETS = ("urun","mal","hizmet","gayrimenkul","tasinmaz","varlik","marka","portfoy",
                "tesis","fabrika","arac","makine","ekipman","stok","emtia","enerji","elektrik",
                "siparis","proje","arsa","bina","arazi","tarla","ofis","depo")
_TURNOVER_METRIC = ("hiz","oran","sure","siklik","adet","aded","sayi","miktar","ortalama")
_TURNOVER_FILLER = ("islem","toplam","ortalama","gunluk","aylik","yillik")
_ALLOWED_SALE_MODIFIERS = ("tamam","planlan","tum","kismi","belirli","dogrudan","dolayli","yaklasik")
_COORD = {"ve","ancak","fakat","ayrica","sonra","ardindan"}

_ARTICLES_RE = re.compile(r"(?<!\w)(?:esas|ana)\s+sozlesme\w*")


def normalize(value: str) -> str:
    value = str(value or "").translate(_TURKISH).lower()
    value = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in value if not unicodedata.combining(ch))


def tokens(value: str) -> list[str]:
    return re.findall(r"\w+", normalize(value))


def segments(*values: str) -> list[str]:
    out = []
    for value in values:
        protected = str(value or "").replace("A.Ş.", "AS").replace("a.ş.", "as").replace("Ltd. Şti.", "Ltd Sti")
        for part in re.split(r"[.!?;\n]+", protected):
            part = normalize(part).strip()
            if part:
                out.append(part)
    return out


def _starts(token: str, prefixes: tuple[str,...]) -> bool:
    return token.startswith(prefixes)


def _company(token: str) -> bool:
    return _starts(token, _COMPANY)


def _speaker(token: str) -> bool:
    return _starts(token, _SPEAKER)


def _transfer(token: str) -> bool:
    return _starts(token, _TRANSFER)


def _procure(token: str) -> bool:
    return _starts(token, _PROCURE)


def _gov(token: str) -> bool:
    if token.startswith(("kuruldu","kurulacak","kuruluyor","kurulmas","kurulm")):
        return False
    return _starts(token, _GOV)


def _right(token: str) -> bool:
    if token.startswith(("hakkinda","hakkimizda","hakkinizda")):
        return False
    return _starts(token, _RIGHT)


def _object_case(token: str) -> bool:
    return token.endswith((
        "ini","unu","ini","yi","yu","i","u","lari","leri","larini","lerini",
        "ligi","ligi","ligini","larini","sini","sunu",
    ))


def _company_object_target(token: str) -> bool:
    if token.startswith(("sirketini","firmasini","isletmesini","istirakini","ortakligini")):
        return True
    if token.startswith(("ortakligi","istiraki")):
        return True
    if token.startswith(("sirketi","firmasi","isletmesi")):
        return False
    return _company(token) and _object_case(token)


def _genitive_company(token: str) -> bool:
    return token.startswith(("sirketinin","firmanin","firmasinin","ortakligin","ortakliginin",
                             "isletmenin","isletmesinin","istirakin","istirakinin"))


def _locative_company(token: str) -> bool:
    return _company(token) and token.endswith(("de","da","te","ta","nde","nda","inde","inda","lerinde","larinda"))


def _source_company(token: str) -> bool:
    return _company(token) and token.endswith(("den","dan","ten","tan","nden","ndan","inden","indan","lerinden","larindan"))


def _comitative_company(token: str) -> bool:
    return _company(token) and token.endswith(("le","la","yle","yla"))


def _proper_accusative(items: list[str]) -> bool:
    for i, tok in enumerate(items):
        if tok in {"i","yi","u","yu","ni","nu"} and i > 0:
            if not _company(items[i-1]):
                return True
    return False


def _named_legal_genitive(items:list[str]) -> bool:
    return any(t in {"as","ltd","sti"} for t in items) and any(t in {"in","nin","un","nun"} for t in items[-5:])


def _genitive_buyer_phrase(items: list[str]) -> bool:
    if any(_genitive_company(t) for t in items):
        return True
    for i,t in enumerate(items):
        if _company(t) and any(x in {"in","nin","un","nun"} for x in items[i+1:i+3]):
            return True
    return _named_legal_genitive(items)


def _named_company_raw(value: str) -> bool:
    raw=normalize(str(value).replace("A.Ş."," AS ").replace("a.ş."," AS ").replace("Ltd. Şti."," LTD STI "))
    return bool(re.search(r"\b(?:as|ltd\s+sti)\b",raw)) or bool(re.search(r"\ba\s+s\b",raw))


def _relative(token: str) -> bool:
    if re.search(r"(?:digim|digimiz|diginiz|diklari|dugum|dugumuz|dugunuz|duklari|tigim|tigimiz|tiginiz|tiklari|tugum|tugumuz|tugunuz|tuklari)$", token):
        return True
    if token.endswith(("an","en","mis","mus")):
        return True
    if token.startswith(("alinan","alinacak","alinmis","devralinan","devralinacak","devralinmis","kurulu","kurulmus","olan","oldugu")):
        return True
    return False


def _finite(token: str) -> bool:
    if _relative(token):
        return False
    if token in {"etti","edildi","oldu","olmustur","erdi","bitti","iflas","kuruldu","kurdu","yapildi"}:
        return True
    if re.search(r"(?:di|du|ti|tu|dim|dum|tim|tum|din|dun|tin|tun|dik|duk|tik|tuk|diniz|dunuz|tiniz|tunuz|diler|dular|tiler|tular|yor|yoruz|yorsunuz|mistir|mustur|mektedir|maktadir|acak|ecek|acaktir|ecektir|ilecektir|ilacaktir)$", token):
        return True
    if token.startswith(("yuksel","dus","acikla","kullan","sagla","sonuclandir","birles","bolun",
                         "devret","devred","satil","kiralan","feshed","imzalan","tamamlan","artir",
                         "azal","yayinlan","duyurul","yenilen","insa")) and not _relative(token):
        return True
    return False


def _has_finite(items: list[str]) -> bool:
    return any(_finite(tok) for tok in items)


def _clauses(value: str) -> list[list[str]]:
    out: list[list[str]] = []
    for sent in segments(value):
        for raw in sent.split(","):
            items = re.findall(r"\w+", raw)
            start = 0
            for i,tok in enumerate(items):
                if tok not in _COORD:
                    continue
                left, right = items[start:i], items[i+1:]
                if left and right and _has_finite(left) and _has_finite(right):
                    out.append(left)
                    start = i+1
            if items[start:]:
                out.append(items[start:])
    return out


def _blocked_agent_indices(items: list[str]) -> set[int]:
    out=set()
    for m, tok in enumerate(items):
        if not tok.startswith(_AGENT_MARKERS):
            continue
        out.add(m)
        for j in range(m-1, max(-1,m-5), -1):
            if _company(items[j]) or _transfer(items[j]):
                out.add(j)
                break
    return out


def _adjunct_indices(items: list[str]) -> set[int]:
    out=set()
    for i,t in enumerate(items):
        if not t.startswith("adina"):
            continue
        out.add(i)
        for j in range(i-1,max(-1,i-4),-1):
            if _company(items[j]) or _transfer(items[j]):
                out.add(j)
                break
    return out


def _blocked_vendor_indices(items: list[str]) -> set[int]:
    out=set()
    for i,tok in enumerate(items):
        if _source_company(tok) or _comitative_company(tok):
            out.add(i)
        if _company(tok) and i+1 < len(items) and items[i+1] == "ile":
            out.update({i,i+1})
    return out


def _blocked(items:list[str]) -> set[int]:
    return _blocked_agent_indices(items) | _blocked_vendor_indices(items)


def _nearest_role_before(items: list[str], index: int) -> tuple[str,str] | None:
    blocked=_blocked(items)
    for i in range(index-1,-1,-1):
        if i in blocked:
            continue
        tok=items[i]
        if tok in {"icin","ile","uzere","yonelik","hakkinda"}:
            continue
        if _procure(tok):
            return "procure",tok
        if _transfer(tok) or _company(tok):
            return "transfer",tok
        if _starts(tok,_OPERATIONAL):
            return "operational",tok
    return None


def _nearest_role_after(items: list[str], index: int) -> tuple[str,str] | None:
    blocked=_blocked(items)
    for i in range(index,len(items)):
        if i in blocked:
            continue
        tok=items[i]
        if tok.startswith(_ORG_UNITS):
            return "unit",tok
        if _procure(tok):
            for j in range(i+1,min(len(items),i+7)):
                if j in blocked:
                    continue
                if _company(items[j]) and not _speaker(items[j]) and not _locative_company(items[j]):
                    tail=items[j+1:]
                    usage_positions=[k for k,x in enumerate(tail) if x.startswith(("kullan","tuket","yak","harca"))]
                    if not usage_positions:
                        return "transfer",items[j]
                    first_usage=usage_positions[0]
                    if any(x.startswith(("uret","sagla","imal","urettig","uretmis")) for x in tail[:first_usage]):
                        return "transfer",items[j]
            return "procure",tok
        if _transfer(tok) or _company(tok):
            return "transfer",tok
        if _starts(tok,_OPERATIONAL):
            return "operational",tok
    return None


def _purchase_kind(tok: str, after: list[str]) -> str:
    if tok.startswith("alin"):
        return "passive"
    if tok.startswith(("aldig","aldik")) or (tok.startswith("almis") and after and after[0].startswith(("oldug","olan"))):
        return "active_relative"
    if tok.startswith(("aldi","alacak","alacag","aliyor","alir","almis")):
        return "active_finite"
    if tok.startswith(("alma","alim")):
        return "active_nominal"
    return "other"


def _purchase_decision(text:str) -> str:
    """Return mna/procurement/none for satın al occurrences."""
    saw_procurement=False
    for items in _clauses(text):
        for i in range(len(items)-1):
            if items[i]!="satin" or not items[i+1].startswith("al"):
                continue
            tok=items[i+1]
            before, after = items[:i], items[i+2:]
            kind=_purchase_kind(tok,after)
            blocked_before=_blocked(before)
            explicit_before = _proper_accusative(before) or any(
                j not in blocked_before
                and ((_transfer(t) and not _company(t) and _object_case(t)) or _company_object_target(t))
                and not _speaker(t) and not _genitive_company(t)
                for j,t in enumerate(before)
            )

            if kind=="passive":
                role=_nearest_role_before(items,i)
                if role and role[0]=="transfer":
                    return "mna"
                if role and role[0] in {"procure","operational"}:
                    saw_procurement=True
                    continue
                post=_nearest_role_after(items,i+2)
                if post and post[0]=="transfer":
                    return "mna"
                if post and post[0] in {"procure","operational"}:
                    saw_procurement=True
                continue

            if kind=="active_relative":
                post=_nearest_role_after(items,i+2)
                if post and post[0]=="transfer":
                    return "mna"
                if post and post[0]=="procure":
                    if _named_legal_genitive(before):
                        continue
                    if _genitive_buyer_phrase(before):
                        saw_procurement=True
                        continue
                    saw_procurement=True
                continue

            if kind=="active_finite":
                if explicit_before:
                    return "mna"
                post=_nearest_role_after(items,i+2)
                if post and post[0]=="transfer":
                    return "mna"
                continue

            if kind=="active_nominal":
                if any(t.startswith(_ORG_UNITS) for t in after):
                    continue
                if explicit_before:
                    return "mna"
                if _named_legal_genitive(before) and not any(t.startswith(_ORG_UNITS) for t in after):
                    return "mna"
                compact_heading = (
                    before and len(before) <= 4
                    and any(_company(t) for t in before)
                    and not any(_procure(t) for t in before)
                    and not _has_finite(after)
                    and not any(t.startswith(_ORG_UNITS) for t in after)
                )
                if compact_heading:
                    return "mna"
                pre_role=_nearest_role_before(items,i)
                post_role=_nearest_role_after(items,i+2)
                if pre_role and pre_role[0]=="procure":
                    saw_procurement=True
                    continue
                if post_role and post_role[0]=="transfer":
                    return "mna"
                if (pre_role and pre_role[0]=="procure") or (post_role and post_role[0]=="procure"):
                    saw_procurement=True
                continue
    return "procurement" if saw_procurement else "none"


def satin_alma_is_acquisition(text:str) -> bool:
    return _purchase_decision(text)=="mna"


def _devralma_decision(text:str) -> str:
    saw_procurement=False
    for items in _clauses(text):
        blocked=_blocked(items) | _adjunct_indices(items)
        for i,tok in enumerate(items):
            if not tok.startswith("devral"):
                continue
            before,after=items[:i],items[i+1:]
            gov_obj=any(_gov(t) and _object_case(t) for t in before)
            explicit=any(
                j not in blocked
                and ((_transfer(t) and not _company(t) and _object_case(t)) or _company_object_target(t))
                and not _speaker(t) and not _genitive_company(t)
                for j,t in enumerate(items)
            )
            if explicit:
                return "mna"
            if gov_obj:
                continue
            if tok.startswith("devralin"):
                role=_nearest_role_before(items,i)
                if role and role[0]=="transfer":
                    return "mna"
                if role and role[0] in {"procure","operational"}:
                    saw_procurement=True
                    continue
                role2=_nearest_role_after(items,i+1)
                if role2 and role2[0]=="transfer":
                    return "mna"
                if role2 and role2[0] in {"procure","operational"}:
                    saw_procurement=True
                continue
            if tok.startswith("devralma"):
                role=_nearest_role_before(items,i)
                if role and role[0]=="transfer":
                    return "mna"
                role2=_nearest_role_after(items,i+1)
                if role2 and role2[0]=="transfer":
                    return "mna"
                continue
            post=_nearest_role_after(items,i+1)
            if post and post[0]=="transfer":
                return "mna"
    return "procurement" if saw_procurement else "none"


def devralma_has_acquisition_context(text:str)->bool:
    return _devralma_decision(text)=="mna"


def _physical_tesis_predicate(items:list[str], idx:int)->bool:
    if idx>0 and _starts(items[idx-1],_PHYSICAL_HEAD):
        return True
    tail=items[idx+1:idx+7]
    return any(t.startswith(("kurul","insa","kiraya","faaliy","devreye","acil","genislet","kapasite")) for t in tail)


def _legal_tesis(items:list[str],idx:int)->bool:
    tail=items[idx+1:idx+8]
    if tail and tail[0].startswith(("edil","olustur")) and any(_right(t) for t in tail[1:]):
        return True
    if _physical_tesis_predicate(items,idx):
        return False
    if any(_gov(t) for t in items[idx+1:idx+3]):
        return False
    for r in range(idx-1,-1,-1):
        if not _right(items[r]):
            continue
        between=items[r+1:idx]
        if any(_starts(t,_PHYSICAL_HEAD) for t in between):
            return False
        if any(t.startswith(("bulunan","mevcut","kapsamindaki","uzerindeki","konu","sahip")) for t in between):
            return False
        return True
    return False


def tesis_is_operational(text:str)->bool:
    for items in _clauses(text):
        for i,t in enumerate(items):
            if not t.startswith("tesis"):
                continue
            if any(_gov(x) for x in items[i+1:i+3]):
                continue
            if _legal_tesis(items,i):
                continue
            return True
    return False


def _capital_match(subject:str,summary:str,term:str)->bool:
    needle=normalize(term)
    for items in _clauses(f"{subject}. {summary}"):
        for i,t in enumerate(items):
            if not t.startswith(needle):
                continue
            if any(x.startswith("tesis") and _legal_tesis(items,j) for j,x in enumerate(items)):
                continue
            if i+1 < len(items) and items[i+1].startswith("artirim"):
                return True
            if i+1 < len(items) and items[i+1].startswith(("pay","hisse")):
                if i+2 < len(items) and items[i+2].startswith(("sahip","sahibi")):
                    continue
                if any(x.startswith(("dagit","sermaye","artir","azalt","ihrac")) for x in items[i+2:i+6]):
                    return True
            window=items[max(0,i-2):min(len(items),i+6)]
            if any(x.startswith("sermaye") for x in window) and any(x.startswith(("artir","azalt")) for x in window):
                return True
    return False


def _merger_match(subject:str,summary:str)->bool:
    for items in _clauses(f"{subject}. {summary}"):
        for i,t in enumerate(items):
            if t.startswith("birlesik") or not t.startswith("birles"):
                continue
            if t.startswith("birlesme"):
                if any(_company(x) or x.startswith(("pay","hisse","sermaye","holding","grup")) for x in items):
                    return True
                continue
            if t.startswith(("birlestir","birlestiril")):
                pos_transfer=max([j for j in range(i) if items[j].startswith(_TRANSFER+_COMPANY)] or [-1])
                pos_oper=max([j for j in range(i) if items[j].startswith(_OPERATIONAL)] or [-1])
                if pos_transfer > pos_oper:
                    return True
                if pos_oper >= 0:
                    return False
            if any(_company(x) or x.startswith(("pay","hisse","sermaye","holding","grup")) for x in items):
                return True
    return False


def _split_match(subject:str,summary:str)->bool:
    subj=tokens(subject)
    if subj:
        if subj[0].startswith("bolunme") or (len(subj)>1 and subj[0] in {"kismi","tam"} and subj[1].startswith("bolun")):
            if any(_starts(x,("dosya","veri","yol","karayol","arsiv","set")) for x in subj):
                return False
            return True
    if any(t.startswith("bolun") for t in subj) and _named_company_raw(subject):
        return True
    for items in _clauses(f"{subject}. {summary}"):
        for i,t in enumerate(items):
            if not t.startswith("bolun"):
                continue
            if t.startswith("bolunmus") and any(_starts(x,("dosya","veri","yol","karayol","arsiv","set")) for x in items):
                continue
            if any(_starts(x,_DEBT) for x in items[max(0,i-6):i]):
                continue
            pos_oper=max([j for j in range(i) if items[j].startswith(_OPERATIONAL)] or [-1])
            pos_company=max([j for j in range(i) if _company(items[j]) or items[j].startswith(("pay","hisse","sermaye"))] or [-1])
            if pos_oper > pos_company:
                continue
            if pos_company >= 0 or any(_company(x) for x in items[i+1:]):
                return True
    return False


def _turnover_metric(items:list[str],idx:int)->bool:
    tail=items[idx+1:idx+5]
    if not tail:
        return False
    for t in tail:
        if t.startswith(_TURNOVER_METRIC):
            return True
        if not t.startswith(_TURNOVER_FILLER):
            break
    return False


def _motor_speed(items:list[str],idx:int)->bool:
    around=items[max(0,idx-2):min(len(items),idx+4)]
    return any(t.startswith("motor") for t in around) and any(t.startswith("hiz") and not t.startswith("hizmet") for t in around)


def _devir_match(subject:str,summary:str)->bool:
    for items in _clauses(f"{subject}. {summary}"):
        for i,t in enumerate(items):
            if t.startswith(("devrim","devriye","devirdaim","devreye")) or not t.startswith(("devir","devri","devred","devret")):
                continue
            if _turnover_metric(items,i) or _motor_speed(items,i):
                continue
            prev=items[i-1] if i>0 else ""
            if prev and _transfer(prev) and not _gov(prev):
                return True
            if prev and _gov(prev):
                continue
            nearby=items[max(0,i-6):min(len(items),i+7)]
            explicit=any(_transfer(x) and _object_case(x) and not _genitive_company(x) for x in nearby)
            if explicit:
                return True
            if any(_gov(x) for x in nearby):
                continue
            if any(_company(x) and not _speaker(x) and not _source_company(x) for x in items[i+1:]):
                return True
    return False


def _repurchase_object(items:list[str],idx:int)->str:
    for j in range(idx-1,max(-1,idx-7),-1):
        t=items[j]
        if t in _COORD:
            break
        if t.startswith(_POSTPOSITIONS):
            continue
        if t in {"ile"}:
            break
        return t
    return ""


def _repurchase_match(subject:str,summary:str)->bool:
    for items in _clauses(f"{subject}. {summary}"):
        for i in range(len(items)-1):
            if items[i]!="geri" or not items[i+1].startswith("al"):
                continue
            obj=_repurchase_object(items,i)
            tail=items[i+2:i+7]
            if obj.startswith(("pay","hisse")):
                return True
            if obj and (_starts(obj,_DEBT) or _starts(obj,_PRODUCT) or _procure(obj) or (_transfer(obj) and not _company(obj))):
                continue
            if any(x.startswith(("hak","taahhut","opsiyon")) for x in tail):
                continue
            if any(x.startswith("program") for x in tail):
                return True
    return False


def _contract_segments(value:str)->list[str]:
    protected=str(value or "").replace("A.Ş.","AS").replace("a.ş.","as")
    protected=re.sub(r"(?<=\d)\.(?=\s*[A-Za-zÇĞİÖŞÜçğıöşü])"," ",protected)
    return [normalize(p).strip() for p in re.split(r"[,!?;:\n]+|\.(?=\s+[A-Za-zÇĞİÖŞÜçğıöşü])",protected) if normalize(p).strip()]


def _articles_reference(seg:str)->bool:
    return bool(re.search(r"\bsozlesme\w*\s+\d+\s+madde\w*",seg))


def _contract_match(subject:str,summary:str)->bool:
    articles_subject=bool(_ARTICLES_RE.search(normalize(subject)))
    for value in (subject,summary):
        for seg in _contract_segments(value):
            if not re.search(r"(?<!\w)sozlesme\w*",seg):
                continue
            if _ARTICLES_RE.search(seg):
                continue
            if articles_subject and _articles_reference(seg):
                continue
            return True
    return False


def _ownership_match(subject:str,summary:str)->bool:
    for items in _clauses(f"{subject}. {summary}"):
        for i,t in enumerate(items):
            if not t.startswith(("ortaklik","ortaklig")):
                continue
            around=items[max(0,i-2):min(len(items),i+6)]
            if any(x.startswith(("pay","hisse","sermaye","hakim","kontrol")) for x in around):
                return True
            if i+1 < len(items) and items[i+1].startswith(("yapi","oran")):
                return True
            if i+2 < len(items) and items[i+1].startswith(("sermaye","pay","hisse")) and items[i+2].startswith(("yapi","oran")):
                return True
            if t.startswith("ortakligin"):
                for s in range(i+1,min(len(items),i+7)):
                    if not items[s].startswith(("satisi","satilmas")):
                        continue
                    mods=items[i+1:s]
                    if any(_starts(x,_SALE_ASSETS) or _procure(x) for x in mods):
                        break
                    if mods and not all(x.startswith(_ALLOWED_SALE_MODIFIERS) for x in mods):
                        break
                    return True
    return False


def term_matches(subject:str,summary:str,term:str)->bool:
    n=normalize(term)
    if n=="satin alma": return _purchase_decision(f"{subject}. {summary}")=="mna"
    if n=="devralma": return _devralma_decision(f"{subject}. {summary}")=="mna"
    if n=="devir": return _devir_match(subject,summary)
    if n=="tesis": return tesis_is_operational(f"{subject}. {summary}")
    if n in {"bedelsiz","bedelli"}: return _capital_match(subject,summary,n)
    if n=="birlesme": return _merger_match(subject,summary)
    if n=="bolunme": return _split_match(subject,summary)
    if n in {"geri alim","pay geri alim"}: return _repurchase_match(subject,summary)
    if n=="sozlesme": return _contract_match(subject,summary)
    if n=="ortaklik": return _ownership_match(subject,summary)
    return _prev.term_matches(subject,summary,term)


def _procurement_operation(subject:str,summary:str)->bool:
    text=f"{subject}. {summary}"
    purchase=_purchase_decision(text)
    if purchase=="procurement":
        return True
    takeover=_devralma_decision(text)
    return takeover=="procurement"


def classify_event_fields(subject:str, summary:str, disclosure_type:str, is_corrective:bool,
                          event_rules:Iterable[tuple[str,int,tuple[str,...]]])->tuple[str,int,str]:
    category="other"; score=0
    if str(disclosure_type).upper() in {"FR","FS"}:
        category,score="financials",100
    for candidate,weight,terms in event_rules:
        if weight<=score:
            continue
        if any(term_matches(subject,summary,t) for t in terms):
            category,score=candidate,weight
    if score<80 and _procurement_operation(subject,summary):
        category,score="operations",80
    if is_corrective and score:
        score=min(100,score+5)
    severity="critical" if score>=95 else "high" if score>=85 else "medium" if score>=70 else "low"
    return category,score,severity


def event_term_matches_compat(text:str,term:str)->bool:
    return term_matches(text,"",term)
