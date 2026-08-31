"""給藥途徑推導。

主來源是健保 `分類分組名稱` token[1]（官方劑型分組，只有 62 個值），
比自己從 173 種 `劑型` 字串硬推可靠。分組欄髒掉（實測有 '0.5MG'、'1MG'
這種逗號切分錯位）才退回 `劑型` 關鍵字。

★ 關鍵字順序即優先序：先判特殊給藥部位再判口服。順序寫錯會把
  「點眼乳劑」歸成外用、「軟膠囊劑」漏判。無法判定一律 OTHER，絕不猜。
"""

from __future__ import annotations

ROUTES = ("PO", "INJ", "TOP", "OPH", "OTIC", "NASAL", "INH", "PR", "PV", "TD", "DIAL", "OTHER")

ROUTE_LABEL = {
    "PO": "口服", "INJ": "注射", "TOP": "外用", "OPH": "眼用", "OTIC": "耳用",
    "NASAL": "鼻用", "INH": "吸入", "PR": "肛門", "PV": "陰道", "TD": "貼片",
    "DIAL": "透析", "OTHER": "其他",
}

# 官方 62 個劑型分組 → route（精確比對，優先於關鍵字）
GROUP_MAP = {
    "一般錠劑膠囊劑": "PO", "緩釋錠劑膠囊劑": "PO", "緩釋錠": "PO", "腸溶製劑": "PO",
    "口服液劑": "PO", "內服液劑": "PO", "口服顆粒劑": "PO", "一般錠劑膠囊劑/顆粒劑": "PO",
    "注射劑": "INJ", "預混型注射劑": "INJ", "三合一營養注射劑": "INJ",
    "三合一營養注射劑.": "INJ", "PENFILL": "INJ",
    "外用軟膏劑": "TOP", "外用液劑": "TOP", "外用噴霧劑": "TOP", "外用錠劑": "TOP",
    "外用顆粒劑": "TOP", "外用貼片": "TD", "局部貼片": "TD", "經皮吸收貼片": "TD",
    "眼用液劑": "OPH", "眼用凝膠劑": "OPH", "外用點眼液劑": "OPH", "眼耳鼻用軟膏": "OPH",
    "耳鼻用液劑": "OTIC",
    "口鼻噴霧/吸入劑": "INH",
    "口內膏": "PO",
    "栓劑": "PR",
    "陰道用錠劑膠囊劑": "PV", "陰道用軟膏劑": "PV", "陰道栓劑": "PV",
    "透析用製劑": "DIAL", "透析用液劑": "DIAL", "體腔用灌洗劑": "DIAL",
}

# fallback：劑型字串關鍵字。順序不可換。
_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("OPH",   ("點眼", "眼用", "眼藥", "眼膏", "結膜")),
    ("OTIC",  ("點耳", "耳用", "耳滴")),
    ("NASAL", ("鼻用", "鼻噴", "鼻滴")),
    ("INH",   ("吸入", "噴霧吸入")),
    ("INJ",   ("注射", "凍晶", "預充填", "輸注", "植入")),
    ("PR",    ("栓劑", "肛門", "灌腸")),
    ("PV",    ("陰道",)),
    ("TD",    ("貼片", "貼布", "穿皮")),
    ("DIAL",  ("透析", "灌洗")),
    # 「軟膏」必須在「軟膠囊」之後才安全？不會 —— 用完整關鍵字「軟膏」不會誤中「軟膠囊劑」
    ("TOP",   ("乳膏", "軟膏", "凝膠", "外用", "洗劑", "泡沫", "酊劑", "藥皂",
               "洗髮", "頭皮", "油膏", "糊劑", "膜劑", "噴液", "口內膏")),
    ("PO",    ("錠", "膠囊", "散劑", "顆粒", "糖漿", "口服", "口頰", "舌下",
               "懸液", "內服", "内服", "粉劑", "乾粉", "液劑")),
]

# 太曖昧、必須人工判定的劑型字串（可能是點眼/口服/注射）
_AMBIGUOUS = {"乳劑", "溶液", "粉劑"}


def derive(group_form: str, dose_form: str) -> tuple[str, str]:
    """回傳 (route, source)。source ∈ {group, keyword, ambiguous, unknown}"""
    g = (group_form or "").strip()
    if g in GROUP_MAP:
        return GROUP_MAP[g], "group"

    d = (dose_form or "").strip()
    if d in _AMBIGUOUS:
        return "OTHER", "ambiguous"
    for route, kws in _KEYWORDS:
        if any(k in d for k in kws):
            return route, "keyword"
    return "OTHER", "unknown"


def group_form_of(group_name: str) -> str:
    """分類分組名稱 token[1]。切分錯位時回空字串讓 derive() 走 fallback。"""
    parts = [p.strip() for p in (group_name or "").split(",")]
    return parts[1] if len(parts) > 1 else ""
