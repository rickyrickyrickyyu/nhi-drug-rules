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
from config import CURATION, PUBLIC, SNAP_DIFF, STAGING  # noqa: E402
from lib.fingerprint import data_fingerprint  # noqa: E402
from lib.section import code_tuple  # noqa: E402

TODAY = date.today().isoformat()


def slim_proc(p: dict) -> dict:
    """處置的 slim 形狀。與藥品共用 `t` 型別欄，讓搜尋能天然跨實體。

    刻意不硬塞進藥品的欄位語意（處置沒有劑型／ATC／商品名），
    但保留 k/n/z 三個共通欄，搜尋器就不必為每種實體各寫一份。
    """
    return {
        "t": "p",
        "k": p["code"],
        "n": p["name_zh"],
        "en": p["name_en"],
        "z": p["synonyms"],
        "pt": p["points"],
        # 官方支付標準的章節定位（第二部第二章第六節）。健保署對處置沒有
        # 逐項 PDF，這是醫師在官方原文裡找到該條的唯一定位。
        "ch": p.get("chapter") or None,
        "note": p["note"][:600],
        "note_more": len(p["note"]) > 600,
        "g": p["group"],
        "pri": 1 if p.get("primary") else 0,
        "st": p["status"],
        "dr": p["derm_reasons"],
    }


def slim(ing: dict, products: dict, mentions: dict, dosing: dict, dose_tfda: dict) -> dict:
    """搜尋列所需的最小欄位。欄名縮寫是刻意的 —— 45k 筆時省 25% 體積。"""
    return {
        "t": "d",
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
        "dt": 1 if dose_tfda.get(ing["inn"]) else 0,
        "ds": 1 if dosing.get(ing["inn"], {}).get("direct") or
                   dosing.get(ing["inn"], {}).get("section_sole") else 0,
        # 健保「給付規定章節」欄有缺漏（實測 bimekizumab、amorolfine 等），
        # 條文內文卻列有藥名。當線索提供，UI 必須與正式章節分開標示。
        "mn": mentions.get(ing["inn"], {}),
    }


def _price_range(codes: list[str], products: dict) -> list[float] | None:
    ps = [products[c]["price"] for c in codes if products.get(c) and products[c]["price"]]
    return [min(ps), max(ps)] if ps else None


def gz_size(path: Path) -> float:
    return len(gzip.compress(path.read_bytes(), 9)) / 1024


def main() -> int:
    products = json.loads((STAGING / "products.json").read_text(encoding="utf-8"))
    import yaml as _yaml
    pend_path = CURATION / "pending_updates.yaml"
    pending = {}
    if pend_path.exists():
        for x in (_yaml.safe_load(pend_path.read_text(encoding="utf-8")) or {}).get("pending", []):
            pending[x["section"]] = x

    ppath = STAGING / "procedures.json"
    procs = json.loads(ppath.read_text(encoding="utf-8")) if ppath.exists() else {}

    tpath = STAGING / "dose_tfda.json"
    dose_tfda = json.loads(tpath.read_text(encoding="utf-8")) if tpath.exists() else {}
    dpath = STAGING / "dosing.json"
    dosing = json.loads(dpath.read_text(encoding="utf-8")) if dpath.exists() else {}

    mpath = STAGING / "mentions.json"
    mentions = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {}
    ingredients = json.loads((STAGING / "ingredients.json").read_text(encoding="utf-8"))
    rules = json.loads((STAGING / "rules.json").read_text(encoding="utf-8"))

    derm = [slim(i, products, mentions, dosing, dose_tfda) for i in ingredients.values() if i["derm"]]
    allx = [slim(i, products, mentions, dosing, dose_tfda) for i in ingredients.values()]
    derm.sort(key=lambda x: x["n"])
    allx.sort(key=lambda x: x["n"])

    out_dir = PUBLIC
    (out_dir / "rules").mkdir(parents=True, exist_ok=True)

    def dump(name: str, obj) -> Path:
        p = out_dir / name
        p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        return p

    proc_derm = [slim_proc(p) for p in procs.values() if p["derm"]]
    proc_all = [slim_proc(p) for p in procs.values()]
    proc_derm.sort(key=lambda x: x["k"])
    proc_all.sort(key=lambda x: x["k"])

    # 處置混進 derm.json：只有 23 筆、體積可忽略，省一次 fetch 且搜尋天然跨實體
    p_derm = dump("derm.json", {"schema": 2, "built": TODAY, "ing": derm, "proc": proc_derm})
    p_all = dump("all.json", {"schema": 2, "built": TODAY, "ing": allx})
    dump("procs_all.json", {"schema": 1, "built": TODAY, "proc": proc_all})

    # 章節按大節分檔
    by_ch: dict[int, list] = collections.defaultdict(list)
    for r in sorted(rules.values(), key=lambda x: x["sort_key"]):
        by_ch[r["chapter"]].append({
            "code": r["code"], "slug": r["slug"], "parent": r["parent"],
            "title": r["title"], "eff": r.get("effective_date"),
            "future": r.get("is_future", False), "stub": r.get("is_stub", False),
            "no_pdf": r.get("no_pdf", False),
            "raw": r.get("render_raw", False), "cov": r.get("coverage"),
            "title_rule": r.get("title_is_rule", False),
            "tables": r.get("tables") or [],
            "appx_refs": r.get("appx_refs") or [],
            "flags_ev": r.get("flags_ev") or {},
            # 已公告但官方條文檔尚未更新的提示（人工維護，程式偵測不到）
            "pending": pending.get(r["code"]),
            "rev": r["revision_dates"], "first_seen": r.get("first_seen"),
            "pdf": r.get("pdf_filename"), "flags": r["flags"],
            "clauses": r["clauses"], "text": r["text"],
            "appx": r.get("appendix_from"),
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
            # 劑量只放在懶載分片：搜尋用不到，放進 derm.json 會撐大首載
            "dosing": dosing.get(key, {}),
            # 仿單層：食藥署開放資料的「用法用量」逐字原文，按證分組。
            # 與健保條文劑量性質不同（一個是藥證登載用法、一個是給付條件），
            # UI 必須分開呈現，不可合併成一份「建議劑量」。
            "dose_tfda": dose_tfda.get(key, []),
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

    # ★ 指紋必須在所有資料檔都寫完之後、meta.json 之前算（meta.json 不列入）。
    #   離線包用同一個函式重算，兩邊不同就代表帶出去的資料不是這一版。
    meta = {
        "built": TODAY,
        "data_fingerprint": data_fingerprint(out_dir),
        "n_ingredients_derm": len(derm),
        "n_ingredients_all": len(allx),
        "n_products": len(products),
        "n_sections": len(rules),
        "n_procs_derm": len(proc_derm),
        "n_procs_all": len(proc_all),
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
