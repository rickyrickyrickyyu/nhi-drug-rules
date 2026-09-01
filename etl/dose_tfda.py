#!/usr/bin/env python3
"""從食藥署許可證開放資料抽出「用法用量」，作為仿單層的劑量參考。

★ 這一層與健保條文劑量（etl/dosing.py）互補，但性質完全不同，UI 不可混在一起：
    健保條文劑量 = 給付條件的一部分，開超過不給付
    仿單用法用量 = 藥證登載的用法，與給付無關
  醫師要的是兩者都看得到，而且知道哪一段是哪一種。

★ 資料現實（實測，不美化）：
    皮膚科 443 個學名中，只有 105 個（24%）至少有一張證登載了實質用法用量。
    其餘不是空白（9,130 張證），就是「詳見仿單」這類指標句（2,992 張）。
    覆蓋率會如實顯示在 UI 上 —— 查不到就說查不到，不補、不推論。

★ 零幻覺保證：
    輸出永遠是開放資料欄位的**逐字原文**，程式只做三件事：
      1. 判斷這段字是不是實質內容（還是「詳見仿單」）
      2. 把相同文字的多張證合併，避免同一段話重複十次
      3. 挑出提到肝腎／族群調整的**整句**（原句，不改寫）
    絕不生成、不摘要、不換算劑量。

★ 為什麼以「證」為單位而非以學名為單位：
    同一個學名不同藥廠的用法用量可能不同（外用 vs 口服、濃度不同）。
    把 A 廠的用法掛在 B 廠的藥上是臨床風險，所以每段文字都帶著它的
    許可證字號與商品名。
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import RAW, STAGING  # noqa: E402

# 指向仿單、沒有實質內容的樣板句
RE_POINTER = re.compile(
    r"(詳見|參見|請詳閱|詳如|見|依|遵)\s*[^。]{0,8}"
    r"(仿單|說明書|附件|包裝插頁|外盒|標籤|擬稿)|遵醫師指示|依醫師處方|請洽醫師")

# 提到族群或器官功能調整的關鍵字。命中才把整句挑出來，不命中就不編。
RE_ADJUST = re.compile(
    r"腎功能|腎臟|腎不全|腎損|肌酸酐|creatinine|CrCl|GFR|透析|洗腎|"
    r"肝功能|肝硬化|肝臟|肝損|Child-?Pugh|"
    r"老年|高齡|年長|兒童|小兒|嬰兒|新生兒|青少年|"
    r"孕婦|懷孕|哺乳|授乳|體重|kg", re.I)

# 句子切分：中文句號、分號、換行都算界線
RE_SENT = re.compile(r"[^。；;\n]+[。；;\n]?")

MIN_BODY = 10          # 去掉指標句與括號後，至少要剩這麼多字才算實質內容


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "").strip()


def is_substantive(text: str) -> bool:
    """判斷這段用法用量有沒有實質內容。

    ★ 不能只看長度：「(詳細敘述請參見仿單擬稿)。」有 14 個字但沒有任何劑量。
      先把指標句與括號內容拿掉，再看剩下多少。
    """
    body = RE_POINTER.sub("", text)
    body = re.sub(r"[（(][^）)]*[）)]", "", body)
    body = re.sub(r"[\s。、，,.；;]", "", body)
    return len(body) >= MIN_BODY


def adjust_quotes(text: str) -> list[str]:
    """挑出提到肝腎／族群調整的整句。原句照抄，不改寫。

    ★ 若整段用法用量只有一句、而那句剛好命中關鍵字（如 clotrimazole 的
      「一天2次，塗於患部，兒童不宜使用。」），摘出來等於把同一句印兩次，
      反而讓人以為是兩件事 —— 這種情況不摘。
    """
    out = []
    for m in RE_SENT.finditer(text):
        s = m.group(0).strip()
        if len(s) >= 6 and RE_ADJUST.search(s):
            out.append(s)
    if len(out) == 1 and out[0].rstrip("。；;") == text.strip().rstrip("。；;"):
        return []
    return out


def main() -> int:
    lic_path = RAW / "tfda_licence.json"
    if not lic_path.exists():
        print("⚠️  無 tfda_licence.json，略過仿單劑量層")
        (STAGING / "dose_tfda.json").write_text("{}", encoding="utf-8")
        return 0

    tf = {}
    for r in json.loads(lic_path.read_text(encoding="utf-8")):
        tf[_nfc(r.get("許可證字號"))] = r

    products = json.loads((STAGING / "products.json").read_text(encoding="utf-8"))

    # inn → 用法用量原文 → 掛在這段文字底下的品項
    by_inn: dict[str, dict[str, dict]] = defaultdict(dict)
    stat = {"real": 0, "pointer": 0, "blank": 0, "no_licence": 0}

    for code, p in products.items():
        keys = p.get("inn_keys") or []
        if not keys:
            continue
        lic = _nfc(p.get("licence_no"))
        rec = tf.get(lic)
        if not rec:
            stat["no_licence"] += 1
            continue
        text = _nfc(rec.get("用法用量"))
        if not text:
            stat["blank"] += 1
            continue
        if not is_substantive(text):
            stat["pointer"] += 1
            continue
        stat["real"] += 1
        for inn in keys:
            slot = by_inn[inn].setdefault(text, {
                "text": text, "licences": [], "brands": [], "codes": [],
                "adjust": adjust_quotes(text),
            })
            if lic not in slot["licences"]:
                slot["licences"].append(lic)
            name = p.get("name_zh") or p.get("name_en") or code
            if name and name not in slot["brands"]:
                slot["brands"].append(name)
            slot["codes"].append(code)

    out = {}
    for inn, groups in by_inn.items():
        items = sorted(groups.values(), key=lambda g: (-len(g["codes"]), g["text"]))
        for g in items:
            # 品項可能上百個，只留前 6 個當代表（完整清單在品項表裡）
            g["n_products"] = len(g["codes"])
            g["brands"] = g["brands"][:6]
            g["licences"] = g["licences"][:6]
            del g["codes"]
        out[inn] = items

    (STAGING / "dose_tfda.json").write_text(
        json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    n_adj = sum(1 for v in out.values() if any(g["adjust"] for g in v))
    print(f"✅ dose_tfda.json {len(out):,} 個學名有仿單用法用量"
          f"｜其中 {n_adj} 個含族群/肝腎調整敘述")
    print(f"   證層級：實質 {stat['real']:,}｜指標句 {stat['pointer']:,}"
          f"｜空白 {stat['blank']:,}｜對不到證 {stat['no_licence']:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
