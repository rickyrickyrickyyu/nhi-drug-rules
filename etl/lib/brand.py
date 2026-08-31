"""商品名處理：抽出可搜尋、可顯示的「品牌詞幹」。

健保 `藥品英文名稱` 100% 有值但含劑型與劑量（VALTREX TABLETS 500MG），
`藥品中文名稱` 99.9% 有值但 30.9% 含全形英數、0.9% 含 '?' 亂碼。
醫師搜尋時打的是 "Valtrex" 而不是完整品名，所以必須切出詞幹。
"""

from __future__ import annotations

import re
import unicodedata

_EN_FORM_WORDS = (
    "F.C. TABLETS|FILM COATED TABLETS|FILM-COATED TABLETS|SOFT GELATIN CAPSULES|"
    "PROLONGED-RELEASE HARD CAPSULES|EXTENDED-RELEASE TABLETS|CONCENTRATE FOR SOLUTION|"
    "POWDER FOR SOLUTION|SOLUTION FOR INJECTION|SOLUTION FOR INFUSION|FOR INJECTION|"
    "PREFILLED|TABLETS|TABLET|CAPSULES|CAPSULE|CREAM|OINTMENT|INJECTION|SOLUTION|"
    "SUSPENSION|GEL|LOTION|SYRUP|SPRAY|PATCH|POWDER|GRANULES|SUPPOSITORY|EMULSION|"
    "VANISHING CREAM|EYE DROPS|INFUSION"
)
_RE_EN_CUT = re.compile(rf"\b(?:{_EN_FORM_WORDS})\b", re.I)
_RE_STRENGTH = re.compile(r"\b\d*[\d.]*\d\s*(?:MG|MCG|GM|G|ML|IU|%|％)", re.I)
_RE_QUOTED_MAKER = re.compile(r'["“”「」\'][^"“”「」\']{1,12}["“”「」\']')
# 劑型尾詞。長字串必須排在短字串前面，否則「懸液用粉」會被「液」先切掉留下殘字。
_RE_ZH_FORM_TAIL = re.compile(
    r"(?:懸液用粉劑|懸液用粉|口服懸液劑|持續性藥效膠囊劑|持續性藥效錠|凍晶乾粉注射劑|"
    r"預充填式注射劑|外用凝膠劑|眼用軟膏劑|點眼液劑|點眼膏劑|點眼劑|口腔吸入劑|鼻用噴液劑|"
    r"膜衣錠|糖衣錠|口溶錠|咀嚼錠|腸溶錠|軟膠囊劑|軟膠囊|膠囊劑|膠囊|"
    r"乳膏劑|乳膏|軟膏劑|軟膏|霜劑|霜|凝膠劑|凝膠|乾粉注射劑|凍晶注射劑|注射液劑|注射劑|注射液|"
    r"針劑|內服液劑|外用液劑|懸液劑|懸浮液|液劑|溶液|糖漿劑|糖漿|散劑|顆粒劑|細粒劑|粉劑|"
    r"貼片|栓劑|噴劑|噴液|洗劑|洗髮精|口內膏|眼藥水|眼藥膏|錠劑|錠)\s*$"
)
_RE_ZH_DOSE_TAIL = re.compile(r"[\d.．]+\s*(?:毫克|公克|毫升|微克|克|％|%|單位)(?:/\s*[\w公毫]+)?\s*$")
_RE_PAREN = re.compile(r"[（(]([^）)]{2,12})[）)]")


def _titlecase(s: str) -> str:
    """Title Case，但保留全大寫短詞與連字號後的大寫（Celestoderm-V、U-Chu）。"""

    def one(w: str) -> str:
        if w.isupper() and len(w) <= 3:      # IV / SR / XL / HCL
            return w
        # 連字號各段分別處理，否則 CELESTODERM-V 會變成 Celestoderm-v
        return "-".join(p.capitalize() if len(p) > 1 else p.upper() for p in w.split("-"))

    return " ".join(one(w) for w in s.split())


def stem_en(name_en: str) -> str:
    """VALTREX TABLETS 500MG → Valtrex

    切在「第一個劑型詞」與「第一個劑量」較前者。切完為空則退回原字串——
    絕不產生空品牌名，寧可顯示得長一點。
    """
    s = (name_en or "").strip()
    if not s:
        return ""
    cuts = [m.start() for m in (_RE_EN_CUT.search(s), _RE_STRENGTH.search(s)) if m]
    if cuts:
        s2 = s[: min(cuts)].strip(" -,()")
        if s2:
            s = s2
    return _titlecase(s)


def stem_zh(name_zh: str) -> tuple[str, bool]:
    """祛疹易錠５００毫克 → ('祛疹易', False)

    回傳 (詞幹, has_mojibake)。含 '?'/'□' 的（實測 0.9%）標記出來，
    UI 顯示時附原文 tooltip，不做猜測性修補。
    """
    raw = (name_zh or "").strip()
    if not raw:
        return "", False
    mojibake = "?" in raw or "□" in raw or "?" in raw

    s = unicodedata.normalize("NFKC", raw)      # 全形英數 → 半形
    s = _RE_PAREN.sub("", s)                     # 括號另外抽成別名
    s = _RE_QUOTED_MAKER.sub("", s)              # "五洲" 這類廠商標記
    for _ in range(3):                           # 劑量與劑型可能交錯，剝幾輪
        s2 = _RE_ZH_DOSE_TAIL.sub("", s).strip()
        s2 = _RE_ZH_FORM_TAIL.sub("", s2).strip()
        if s2 == s:
            break
        s = s2
    s = s.strip(" -,()（）")
    return (s or raw), mojibake


def zh_alias(name_zh: str) -> str | None:
    """中文品名括號內常是學名的中文俗稱，是免費的別名來源。

    "五洲"嘴?乳膏５０毫克/公克（艾賽可威）→ 艾賽可威
    只收不含數字、2–8 字的內容；呼叫端還要再過「同 INN 出現 >=2 次」才採用
    （出現一次多半只是廠商自取的花名）。
    """
    for m in _RE_PAREN.findall(name_zh or ""):
        t = m.strip()
        if not (2 <= len(t) <= 8) or any(c.isdigit() for c in t):
            continue
        # 括號裡常常是廠商、國別或劑型註記而非藥名俗稱
        # （"Ganciclovir（義大利廠）" 會被誤收成中文俗稱）
        if any(k in t for k in ("廠", "公司", "股份", "有限", "藥業", "製藥",
                                "進口", "分裝", "國", "版", "型")):
            continue
        return t
    return None
