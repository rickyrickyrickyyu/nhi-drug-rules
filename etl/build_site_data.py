#!/usr/bin/env python3
"""產生前端靜態資料分片。

用法：
    python3 etl/build_site_data.py

輸出 public/data/：
    meta.json          資料快照日期（每頁常駐顯示，也是 cron 保活的 commit 目標）
    derm.json          皮膚科子集，首載（目標 gzip < 200 KB）
    all.json           全庫，切換才懶載
    rules/ch{N}.json   按大節分檔（一次抓 22 KB 勝過 6 次 HTTP 往返）
"""

from __future__ import annotations

import collections
import gzip
import json
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import PUBLIC, SNAP_DIFF, STAGING  # noqa: E402
from lib.section import code_tuple  # noqa: E402

TODAY = date.today().isoformat()


def slim(ing: dict, products: dict) -> dict:
    """搜尋列所需的最小欄位。欄名縮寫是刻意的 —— 45k 筆時省 25% 體積。"""
    return {
        "k": ing["inn"],
        "n": ing["inn_display"],
        "z": ing["zh_common"],
        "al": ing.get("inn_aliases", []),
        "a": ing["atc"],
        "c": 1 if ing["is_combo"] else 0,
        "np": ing["n_products"],
        "s": ing["sections"],
        "f": {
            "pa": 1 if ing["flags"]["prior_review"] else 0,
            "sp": ing["flags"]["specialist_only"],
            "cs": 1 if ing["flags"]["consent_form"] else 0,
            "co": 1 if ing["flags"]["course_limited"] else 0,
        },
        "be": ing["brands_en"][:40],       # 搜尋用；超過 40 個品牌的老藥不必全帶
        "bz": ing["brands_zh"][:40],
        "r": [
            {
                "ro": rt, "l": r["label"], "g": r["group"], "s": r["sections"],
                "sd": r.get("sections_derm", []), "so": r.get("sections_other", []),
                "np": r["n_products"], "bp": r["brand_preview"],
                "pr": _price_range(r["products"], products),
            }
            for rt, r in ing["routes"].items()
        ],
        "dr": ing["derm_reasons"],
    }


def _price_range(codes: list[str], products: dict) -> list[float] | None:
    ps = [products[c]["price"] for c in codes if products.get(c) and products[c]["price"]]
    return [min(ps), max(ps)] if ps else None


def gz_size(path: Path) -> float:
    return len(gzip.compress(path.read_bytes(), 9)) / 1024


def main() -> int:
    products = json.loads((STAGING / "products.json").read_text(encoding="utf-8"))
    ingredients = json.loads((STAGING / "ingredients.json").read_text(encoding="utf-8"))
    rules = json.loads((STAGING / "rules.json").read_text(encoding="utf-8"))

    derm = [slim(i, products) for i in ingredients.values() if i["derm"]]
    allx = [slim(i, products) for i in ingredients.values()]
    derm.sort(key=lambda x: x["n"])
    allx.sort(key=lambda x: x["n"])

    out_dir = PUBLIC
    (out_dir / "rules").mkdir(parents=True, exist_ok=True)

    def dump(name: str, obj) -> Path:
        p = out_dir / name
        p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        return p

    p_derm = dump("derm.json", {"schema": 1, "built": TODAY, "ing": derm})
    p_all = dump("all.json", {"schema": 1, "built": TODAY, "ing": allx})

    # 章節按大節分檔
    by_ch: dict[int, list] = collections.defaultdict(list)
    for r in sorted(rules.values(), key=lambda x: x["sort_key"]):
        by_ch[r["chapter"]].append({
            "code": r["code"], "slug": r["slug"], "parent": r["parent"],
            "title": r["title"], "eff": r.get("effective_date"),
            "future": r.get("is_future", False), "stub": r.get("is_stub", False),
            "no_pdf": r.get("no_pdf", False),
            "rev": r["revision_dates"], "first_seen": r.get("first_seen"),
            "pdf": r.get("pdf_filename"), "flags": r["flags"],
            "clauses": r["clauses"], "text": r["text"],
        })
    ch_sizes = {}
    for ch, items in by_ch.items():
        p = dump(f"rules/ch{ch}.json", {"schema": 1, "chapter": ch, "sections": items})
        ch_sizes[ch] = round(gz_size(p), 1)

    # 品項明細：一個學名一檔，點開才載
    (out_dir / "products").mkdir(exist_ok=True)
    for key, ing in ingredients.items():
        if not ing["derm"]:
            continue
        codes = sorted({c for r in ing["routes"].values() for c in r["products"]})
        safe = key.replace("/", "_").replace(" ", "_").replace("(", "").replace(")", "")
        dump(f"products/{safe}.json", {
            "inn": key,
            # 仿單適應症只有詳情頁用得到，放在懶載分片裡；
            # 塞進 derm.json 會讓首載從 82 KB 膨脹到 180 KB。
            "indications": {rt: r.get("indications", []) for rt, r in ing["routes"].items()},
            "items": [{k: products[c][k] for k in (
                "code", "name_en", "name_zh", "brand_stem_en", "brand_stem_zh",
                "form", "route", "atc", "drug_class", "is_originator", "status",
                "price", "price_next", "price_next_from", "vendor", "sections",
                "licence_id", "licence_no", "licence_state", "indication",
                "name_zh_repaired", "zh_mojibake")} for c in codes if c in products],
        })

    # diff 檔要能被前端 fetch —— 快照目錄不在 Vite 的 public/ 底下，得複製過去
    diff_src = SNAP_DIFF
    diff_dst = out_dir / "diff"
    if diff_dst.exists():
        shutil.rmtree(diff_dst)
    if diff_src.exists() and any(diff_src.rglob("*.json")):
        shutil.copytree(diff_src, diff_dst)

    meta = {
        "built": TODAY,
        "n_ingredients_derm": len(derm),
        "n_ingredients_all": len(allx),
        "n_products": len(products),
        "n_sections": len(rules),
        "n_indications": sum(1 for p in products.values() if p.get("indication")),
        "n_name_repaired": sum(1 for p in products.values() if p.get("name_zh_repaired")),
        "sizes_kb_gz": {
            "derm.json": round(gz_size(p_derm), 1),
            "all.json": round(gz_size(p_all), 1),
            "rules": ch_sizes,
        },
    }
    dump("meta.json", meta)
    print(f"✅ derm.json {len(derm):,} 學名  {meta['sizes_kb_gz']['derm.json']} KB gz")
    print(f"   all.json  {len(allx):,} 學名  {meta['sizes_kb_gz']['all.json']} KB gz")
    print(f"   rules ch13 {ch_sizes.get(13)} KB gz｜全部 {sum(ch_sizes.values()):.0f} KB gz")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
