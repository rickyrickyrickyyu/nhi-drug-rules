#!/usr/bin/env python3
"""從健保條文抽取「明確屬於本藥」的劑量敘述。

用法：
    python3 etl/dosing.py

★ 為什麼不用食藥署的「用法用量」欄：實測 join 到的 23,644 張許可證中，
  空白 72.1%、「詳見仿單」類 20.6%、真有內容僅 7.3%，且集中在老的國產學名藥；
  Dupixent／Cosentyx／Protopic 全是「詳見仿單」。混用會讓醫師誤以為
  「這裡有就代表全都有」，比全空更危險。改為連到食藥署官方查詢頁。

★ 零幻覺的根本保證：本模組只做「選句」，永遠輸出條文原句，
  絕不重組成「每日 0.5 mg/kg」這種被程式改寫過的句子。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import STAGING  # noqa: E402

# 條文裡「這一段在講劑量」的編號標題。用標題而非關鍵字掃描，是因為
# 生物製劑條文裡的 methotrexate 10mg/m²/週 掛在「給付條件」標題下，
# 按標題抽取天然排除了前置用藥的劑量。
_RE_DOSE_HEAD = re.compile(
    r"^\s*[（(]?[\dA-Za-z一二三四五六七八九十ⅠⅡⅢⅣⅤ]+\s*[.)）、]?\s*"
    r"(使用劑量|劑量給予方式|用法用量|給藥方式|使用方式|劑量及用法|劑量)\s*[：:]"
)

# 劑量數值樣式：數字＋單位（含全形、範圍、每公斤／每平方公尺）
_RE_DOSE_VALUE = re.compile(
    r"\d[\d.,\-–~至]*\s*(mg|ｍｇ|毫克|公絲|mcg|微克|g\b|gm|公克|ml|毫升|IU|單位|%|﹪)"
    r"(\s*/\s*(kg|公斤|m2|平方公尺|day|日|天|次|週|月))?", re.I)
# 用藥頻率樣式
_RE_FREQ = re.compile(
    r"每\s*\d*\s*(週|周|星期|日|天|月|次|小時|療程|人|指|趾)|"
    r"隔\s*\d*\s*(週|日|天)|起始劑量|維持劑量|首劑|一次|一療程|總劑量|限用|不超過|不高於")

# 前置治療語氣：這些句子講的是「申請前要先做過什麼」，不是本藥用法
_RE_PREREQ = re.compile(
    r"曾(經)?接受|治療無效|反應不佳|無法耐受|禁忌|先前|已使用|充分治療|"
    r"標準療法|傳統(全身性)?治療|至少.{0,8}(週|個月|月)"
)


def _inn_variants(inn: str) -> list[str]:
    base = inn.split(" (")[0].lower()
    return [base, base.replace("-", "")]


def _mentions(text_low: str, inn: str) -> bool:
    """條文是否提到這個學名。

    ★ 必須用詞邊界：'tretinoin' 是 'isotretinoin' 的子字串，
    純子字串比對會讓 13.4.（只規範 isotretinoin）被誤判成「同時提到兩個學名」，
    整節專屬那一級就永遠抓不到 isotretinoin 的劑量。
    """
    for v in _inn_variants(inn):
        if len(v) < 6:
            continue
        if re.search(rf"(?<![a-z]){re.escape(v)}(?![a-z])", text_low):
            return True
    return False


def collect(rules: dict, ingredients: dict) -> dict:
    """回傳 {inn_key: {"direct": [...], "section_sole": [...], "prerequisite": [...]}}"""
    out: dict[str, dict] = {}

    # 先算每節提到哪些學名，用來判斷「整節只規範本藥」
    sec_inns: dict[str, set[str]] = {}
    for code, r in rules.items():
        text = (r.get("text") or "").lower()
        sec_inns[code] = {key for key in ingredients if _mentions(text, key)}

    for key, ing in ingredients.items():
        if not ing.get("derm"):
            continue
        entries = {"direct": [], "section_sole": [], "prerequisite": []}

        for code in ing.get("sections", []):
            r = rules.get(code)
            if not r:
                continue
            clauses = r.get("clauses") or []
            eff = r.get("effective_date")

            i = 0
            while i < len(clauses):
                head = clauses[i]
                if not _RE_DOSE_HEAD.match(head["text"].split("\n")[0]):
                    i += 1
                    continue
                # 劑量段落＝該標題 clause 加上後續更深層級的 clause
                lv = head["level"]
                j = i + 1
                while j < len(clauses) and clauses[j]["level"] > lv:
                    j += 1
                block = clauses[i:j]

                for c in block:
                    txt = c["text"]
                    low = txt.lower()
                    mine = _mentions(low, key)
                    others = {k for k in sec_inns[code] if k != key and _mentions(low, k)}
                    item = {"quote": txt, "section": code, "effective_date": eff,
                            "clause_level": c["level"]}
                    if mine and not others:
                        entries["direct"].append(item)          # 明確指名本藥且無他藥
                    elif not mine and not others and len(sec_inns[code]) == 1 \
                            and key in sec_inns[code]:
                        entries["section_sole"].append(item)    # 整節只規範本藥
                    elif others and _RE_PREREQ.search(txt):
                        entries["prerequisite"].append(
                            {**item, "for_drugs": sorted(others)})
                i = j

            # ── 整節只規範本藥時，條文任一處的劑量敘述都屬於本藥 ──
            # 13.4. isotretinoin 的「每一療程最高總劑量為100 mg–120 mg/kg」
            # 沒有掛在「使用劑量：」標題下，靠這一級才抓得到。
            # 前提嚴格：整節提到的學名只有本藥一個，才不會張冠李戴。
            if sec_inns.get(code) == {key}:
                for c in clauses:
                    txt = c["text"]
                    if not (_RE_DOSE_VALUE.search(txt) and _RE_FREQ.search(txt)):
                        continue
                    if any(x["quote"] == txt for x in entries["direct"]):
                        continue
                    entries["section_sole"].append(
                        {"quote": txt, "section": code, "effective_date": eff,
                         "clause_level": c["level"]})

            # ── 前置用藥：條文提到「曾接受 X 治療」且帶劑量 ──
            # 這是申請本藥的條件，不是本藥用法，必須獨立標示
            for c in clauses:
                txt = c["text"]
                low = txt.lower()
                others = {k for k in sec_inns[code] if k != key and _mentions(low, k)}
                if others and _RE_PREREQ.search(txt) and _RE_DOSE_VALUE.search(txt):
                    if not any(x["quote"] == txt for x in entries["prerequisite"]):
                        entries["prerequisite"].append(
                            {"quote": txt, "section": code, "effective_date": eff,
                             "clause_level": c["level"], "for_drugs": sorted(others)})

        if any(entries.values()):
            out[key] = {k: v for k, v in entries.items() if v}
    return out


def main() -> int:
    rules = json.loads((STAGING / "rules.json").read_text(encoding="utf-8"))
    ings = json.loads((STAGING / "ingredients.json").read_text(encoding="utf-8"))
    res = collect(rules, ings)
    (STAGING / "dosing.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    n_d = sum(len(v.get("direct", [])) for v in res.values())
    n_s = sum(len(v.get("section_sole", [])) for v in res.values())
    n_p = sum(len(v.get("prerequisite", [])) for v in res.values())
    print(f"✅ dosing：{len(res)} 個學名有劑量敘述"
          f"（直接指名 {n_d}、整節專屬 {n_s}、前置用藥 {n_p}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
