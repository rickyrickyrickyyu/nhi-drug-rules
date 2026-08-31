"""學名（INN）正規化。

主來源是健保 `分類分組名稱` 欄的 token[0]，因為健保署自己的給付分組
已經做過「去鹽、留酯」——這正是臨床上正確的處理方式，直接沿用比自己
硬拆 `成分` 欄可靠得多（成分欄同一支藥會出現 VALERATE / 17-VALERATE /
裸名三種寫法並存，不可信任）。

★ 唯一不可妥協的規則：酯基不得剝除（見 curation/ester_whitelist.yaml）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

CURATION = Path(__file__).resolve().parents[2] / "curation"

# 劑量：3 MG、0.5 MG/GM、130/0.4 60 MG/ML、.05％ 都要吃掉
_RE_STRENGTH = re.compile(
    r"\b\d*[\d.,]*\d\s*(?:MG|MCG|UG|GM|G|ML|L|IU|U|MEQ|KIU|%|％)"
    r"(?:\s*/\s*[\d.,]*\s*(?:MG|GM|G|ML|L|CM2)?)?",
    re.I,
)
_RE_LEAD_STRENGTH = re.compile(r"^[\s.,\d]+")
_RE_WS = re.compile(r"\s+")


@dataclass
class InnParse:
    keys: list[str]                       # canonical inn_key（複方多個）
    combo_key: str | None = None          # 複方時的合併鍵
    is_combo: bool = False
    source: str = "group"                 # group | ingredient | unknown
    warnings: list[str] = field(default_factory=list)


@lru_cache(maxsize=1)
def _load() -> tuple[set, set, set, dict, dict, dict, dict]:
    ew = yaml.safe_load((CURATION / "ester_whitelist.yaml").read_text(encoding="utf-8"))
    al = yaml.safe_load((CURATION / "inn_alias.yaml").read_text(encoding="utf-8"))
    return (
        {s.upper() for s in ew["preserve_ester"]},
        {s.upper() for s in ew["salt_tokens"]},
        {s.upper() for s in ew["ester_tokens"]},
        {k.upper(): v.upper() for k, v in (ew.get("ester_alias") or {}).items()},
        {k.upper(): v.upper() for k, v in (al.get("aliases") or {}).items()},
        {k.upper(): v.upper() for k, v in (ew.get("atc_ester") or {}).items()},
        {k.upper(): v.upper() for k, v in (ew.get("base_atc_ester") or {}).items()},
    )


def _strip_strength(s: str) -> str:
    s = _RE_STRENGTH.sub(" ", s)
    return _RE_WS.sub(" ", s).strip(" ,;.")


# 學名一律是拉丁字母，中文只會是劑型或分類詞
_RE_CJK = re.compile(r"[\u3400-\u9fff]")


def _cut_at_cjk(s: str) -> str:
    """砍掉學名後面黏著的中文劑型詞。

    ★ 部分 分類分組名稱 用空白而非逗號分隔：
        'AMOROLFINE HCL 55.74MG/ML 外用液劑 5.0ML'   ← 沒有逗號
        'AMOROLFINE , 外用軟膏劑 , 5.00 MG/GM'        ← 正常格式
      前者 split(",")[0] 會拿到整串，剝掉劑量後剩 'AMOROLFINE HCL 外用液劑'，
      同一支藥就被拆成兩個學名，其中一個還帶著 13.12. 的章節、另一個沒有。

    整串都是中文時（'維生素 Vitamins'、'含ANTIHISTAMINE…之複方製劑'）是分類名
    而非學名，保持原樣不動。
    """
    m = _RE_CJK.search(s)
    if not m or m.start() == 0:
        return s
    return s[: m.start()].strip(" ,;.-")


def canonicalize(raw: str, atc: str = "") -> str:
    """單一成分字串 → canonical inn_key。

    括號內容分兩類，絕不可混為一談：
      鹽類  (HYDROCHLORIDE) → 剝除
      酯基  (VALERATE)      → 若 base 在 preserve_ester 清單內，保留成
                              "BETAMETHASONE (VALERATE)" 當主鍵的一部分
    """
    preserve, salts, esters, ester_alias, aliases, atc_ester, base_atc = _load()

    s = _strip_strength((raw or "").upper())
    s = _RE_LEAD_STRENGTH.sub("", s).strip()
    s = _cut_at_cjk(s)
    if not s:
        return ""

    # ★ 健保資料同一個酯基有兩種寫法：BETAMETHASONE (VALERATE) 與 CLOBETASOL PROPIONATE。
    #   兩種都要收，且必須歸一成同一個 key，否則同一支藥會被拆成兩張卡片。
    parens = [p.strip() for p in re.findall(r"\(([^)]*)\)", s)]
    base = _RE_WS.sub(" ", re.sub(r"\([^)]*\)", " ", s)).strip(" ,;.-")

    # 尾綴逐字剝：是鹽類就丟、是酯基就收（收完繼續往前看，處理 SODIUM PHOSPHATE 這種兩字鹽）
    trailing: list[str] = []
    parts = base.split()
    while len(parts) > 1:
        tok = ester_alias.get(parts[-1], parts[-1])
        if tok in salts:
            parts.pop()
        elif tok in esters:
            trailing.insert(0, tok)
            parts.pop()
        else:
            break
    base = " ".join(parts)

    kept: list[str] = []
    for p in parens:
        tok = ester_alias.get(p, p)
        if tok and tok in esters:
            kept.append(tok)
    kept.extend(t for t in trailing if t not in kept)

    # 分組欄沒寫酯基時，ATC 第 7 碼往往已唯一決定了它 —— 能補就補，
    # 外用類固醇的效價分級靠這個。
    if not kept and base in preserve:
        a = (atc or "").strip().upper()
        fill = atc_ester.get(a)
        if not fill:
            # ATC 有時只有 5 碼（D07AC），配合 base 才能判定
            for pref_len in range(len(a), 3, -1):
                fill = base_atc.get(f"{base}|{a[:pref_len]}")
                if fill:
                    break
        if fill:
            kept = [fill]

    # 只有在 base 屬於「酯基會改變效價分級」的成分時才把酯基寫進主鍵
    if base not in preserve:
        kept = []

    key = f"{base} ({'/'.join(kept)})" if kept else base
    return aliases.get(key, aliases.get(base, key)).strip()


def _split_components(s: str) -> list[str]:
    return [p for p in re.split(r"\s*\+\s*", s) if p.strip()]


def normalize(group_name: str, ingredient_raw: str, is_mixture: str, atc: str = "") -> InnParse:
    """回傳該品項的 InnParse。

    優先序：分類分組名稱 token[0] → 成分欄 fallback（僅 1% 會走到，且標 warning）。
    """
    g0 = (group_name or "").split(",")[0].strip()
    source = "group"
    if not g0:
        g0 = (ingredient_raw or "").strip()
        source = "ingredient"
    if not g0:
        return InnParse(keys=[], source="unknown", warnings=["no_ingredient"])

    comps = _split_components(g0)
    keys = [k for k in (canonicalize(c, atc) for c in comps) if k]
    if not keys:
        return InnParse(keys=[], source="unknown", warnings=["canonicalize_empty"])

    warn: list[str] = []
    if source == "ingredient":
        warn.append("fallback_ingredient_field")
    declared_combo = (is_mixture or "").strip() == "複方"
    if declared_combo != (len(keys) > 1):
        warn.append("mixture_flag_conflict")

    if len(keys) > 1:
        combo = " + ".join(sorted(keys))
        return InnParse(keys=keys, combo_key=combo, is_combo=True, source=source, warnings=warn)
    return InnParse(keys=keys, source=source, warnings=warn)
