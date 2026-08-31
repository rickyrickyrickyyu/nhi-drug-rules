#!/usr/bin/env python3
"""反向索引：條文內文提到哪些學名。

用法：
    python3 etl/mentions.py

★ 為什麼需要：健保「給付規定章節」欄有缺漏。實測 Bimzelx（bimekizumab）
  的品項記錄章節欄是空的，但 8.2.4.4./8.2.4.6. 的條文內文明明把它列為
  適用藥品。只看章節欄的話，醫師會以為這支藥沒有給付規定。

  這份索引「只是線索」，不是官方對應 —— UI 必須與正式章節分開呈現，
  標明「條文內文提及」，避免使用者當成健保正式核定的給付範圍。
"""

from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import STAGING  # noqa: E402


def main() -> int:
    rules = json.loads((STAGING / "rules.json").read_text(encoding="utf-8"))
    ings = json.loads((STAGING / "ingredients.json").read_text(encoding="utf-8"))

    # 只對「章節欄是空的」學名做，其他的官方對應已經夠用了
    orphans = {k for k, v in ings.items() if v["derm"] and not v["sections"]}
    if not orphans:
        (STAGING / "mentions.json").write_text("{}", encoding="utf-8")
        print("✅ mentions：無章節缺漏的皮膚科學名")
        return 0

    # 「提及」有兩種關係，臨床意義完全不同，一定要分開：
    #   出現在標題 → 較可能是該節適用藥品（bimekizumab 之於 8.2.4.4.）
    #   只在內文   → 多半是前置治療條件或對照藥
    #                （methotrexate 之於 13.17.1.：dupilumab 要先試過 MTX 無效）
    #
    # ★ 但「標題提及」也不等於適用，實測兩個反例：
    #     12.4. 是「ciprofloxacin + hydrocortisone 耳滴劑」，
    #           hydrocortisone 只是複方成分之一
    #     10.6.5. 只涵蓋 amphotericin B 的 liposomal／colloidal 劑型
    #   所以兩級都只能當線索，UI 措辭一律保守。
    out: dict[str, dict[str, list[str]]] = collections.defaultdict(
        lambda: {"listed": [], "referenced": []})
    for code, r in rules.items():
        text = (r.get("text") or "").lower()
        title = (r.get("title") or "").lower()
        if not text:
            continue
        for inn in orphans:
            base = inn.split(" (")[0].lower()
            # 短名容易誤中（如 "urea"），限定 6 字以上並要求詞邊界
            if len(base) < 6:
                continue
            if not re.search(rf"\b{re.escape(base)}\b", text):
                continue
            key = "listed" if re.search(rf"\b{re.escape(base)}\b", title) else "referenced"
            out[inn][key].append(code)

    from lib.section import code_tuple
    res = {k: {kk: sorted(vv, key=code_tuple) for kk, vv in v.items() if vv}
           for k, v in out.items()}
    (STAGING / "mentions.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    n_listed = sum(1 for v in res.values() if v.get("listed"))
    print(f"✅ mentions：{len(orphans)} 個無章節學名中 {len(res)} 個被條文提及"
          f"（{n_listed} 個出現在章節標題）")
    for k, v in res.items():
        if v.get("listed"):
            print(f"   · {k:24s} 標題提及 {v['listed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
