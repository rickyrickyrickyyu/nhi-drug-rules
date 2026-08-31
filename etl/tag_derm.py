#!/usr/bin/env python3
"""皮膚科標籤 + 學名聚合 + 商品名彙整。

用法：
    python3 etl/tag_derm.py

輸入 .staging/{products,rules}.json，輸出 .staging/ingredients.json。
每個標籤都記錄命中理由（atc/section/whitelist + 證據字串），方便日後稽核
「這個藥為什麼會在皮膚科清單裡」。
"""

from __future__ import annotations

import collections
import json
import re
import unicodedata
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import CURATION, STAGING  # noqa: E402
from lib.route import ROUTE_LABEL  # noqa: E402
from lib.section import code_tuple, match_prefix  # noqa: E402

TODAY = date.today().isoformat()
ROUTE_ORDER = ["PO", "INJ", "TOP", "OPH", "OTIC", "NASAL", "INH", "TD", "PR", "PV", "DIAL", "OTHER"]


def load_curation() -> tuple[dict, dict, dict]:
    tags = yaml.safe_load((CURATION / "derm_tags.yaml").read_text(encoding="utf-8"))
    zh = yaml.safe_load((CURATION / "ingredient_zh.yaml").read_text(encoding="utf-8"))
    al = yaml.safe_load((CURATION / "inn_alias.yaml").read_text(encoding="utf-8"))
    # 反向對照：canonical → [別名…]，讓使用者打美式拼法 acyclovir 也能命中 Aciclovir。
    # 不能只靠「剛好有商品名含該拼法」——那是巧合，不是設計。
    rev: dict[str, list[str]] = {}
    for alias, canon in (al.get("aliases") or {}).items():
        rev.setdefault(canon.upper(), []).append(alias.upper())
    return tags, (zh.get("zh_common") or {}), rev


def derm_reasons(inn_key: str, atcs: set[str], sections: set[str], t: dict) -> list[str]:
    """回傳命中理由清單；空清單代表非皮膚科。"""
    out: list[str] = []
    blocked = {a for a in atcs if any(a.startswith(b) for b in t["atc_block"])}
    for a in atcs - blocked:
        for p in t["atc_always"]:
            if a.startswith(p):
                out.append(f"atc:{p}")
        for p in t["atc_review"]:
            if a.startswith(p):
                out.append(f"atc_review:{p}")
    for s in sections:
        for p in t["sections"]:
            if match_prefix(s, p):
                out.append(f"section:{p}")
    if inn_key in {w.upper() for w in t["whitelist_inn"]}:
        out.append("whitelist")
    return sorted(set(out))


def main() -> int:
    products = json.loads((STAGING / "products.json").read_text(encoding="utf-8"))
    rules = json.loads((STAGING / "rules.json").read_text(encoding="utf-8"))
    tags, zh_map, alias_rev = load_curation()

    agg: dict[str, dict] = {}
    zh_alias_votes: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)

    for p in products.values():
        for key in p["inn_keys"] or []:
            e = agg.setdefault(key, {
                "inn": key, "atc": set(), "sections": set(), "routes": {},
                "codes": [], "is_combo_member": False, "combo_keys": set(),
            })
            if p["atc"]:
                e["atc"].add(p["atc"])
            e["sections"].update(p["sections"])
            e["codes"].append(p["code"])
            if p["is_combo"]:
                e["is_combo_member"] = True
                if p["combo_key"]:
                    e["combo_keys"].add(p["combo_key"])
            r = e["routes"].setdefault(p["route"], {
                "group": p["group_form"], "sections": set(), "products": [],
                "brands": [], "originators": [], "indications": {},
            })
            r["sections"].update(p["sections"])
            r["products"].append(p["code"])
            # 仿單適應症：同一劑型下常常一堆品項寫同一句，去重後才有意義。
            # 以「有效許可證」優先；全部都已註銷才退而用註銷證的文字並標示。
            if p["indication"]:
                r["indications"][p["indication"]] = min(
                    r["indications"].get(p["indication"], "miss"),
                    p["licence_state"],
                    key=lambda x: {"active": 0, "stale": 1, "miss": 2}[x],
                )
            label = " ".join(x for x in (p["brand_stem_en"], p["brand_stem_zh"]) if x)
            (r["originators"] if p["is_originator"] else r["brands"]).append(
                (p["price"] or 0, label, p["brand_stem_en"], p["brand_stem_zh"])
            )
            if p["zh_alias"]:
                zh_alias_votes[key][p["zh_alias"]] += 1

    out: dict[str, dict] = {}
    n_derm = 0
    for key, e in agg.items():
        reasons = derm_reasons(key, e["atc"], e["sections"], tags)
        # 中文俗稱：人工表 + 自動萃取（同 INN 出現 >=2 次才採信，一次多半是廠商花名）
        zh = list(zh_map.get(key, []))
        zh += [w for w, n in zh_alias_votes[key].items() if n >= 2 and w not in zh]

        routes = {}
        for rt in ROUTE_ORDER:
            if rt not in e["routes"]:
                continue
            r = e["routes"][rt]
            # 代表品牌優先序：原廠 → 支付價最高 → 英文名字母序（穩定、每月不跳動）
            picks = sorted(r["originators"], key=lambda x: -x[0]) or sorted(r["brands"], key=lambda x: -x[0])
            preview, seen = [], set()
            for _, label, en, _zh in picks:
                if en and en not in seen:
                    seen.add(en)
                    preview.append(label)
                if len(preview) >= 3:
                    break
            if not preview:
                preview = sorted({x[1] for x in r["brands"] if x[1]})[:3]
            # 適應症按出現次數排序，最多帶 4 條 —— 同劑型下的措辭大同小異，
            # 全列會把健保條文擠掉，而健保條文才是本站主體。
            # 同一句常只差標點或空白（「傳統療法無效之嚴重痤瘡」vs「…痤瘡。」），
            # 用正規化後的鍵合併，顯示時取最完整的那個寫法。
            ind_count: collections.Counter = collections.Counter()
            ind_repr: dict[str, str] = {}
            for c in r["products"]:
                t = (products[c]["indication"] or "").strip()
                if not t:
                    continue
                # NFKC 先做：仿單裡「２.氣喘」與「2. 氣喘」是同一句，只差全半形
                norm = re.sub(r"[\s。，、；：.,;:]+", "", unicodedata.normalize("NFKC", t))
                ind_count[norm] += 1
                if len(t) > len(ind_repr.get(norm, "")):
                    ind_repr[norm] = t
            # ★ 章節分成「皮膚科相關」與「其他科別」兩組。
            #   dupilumab 掛 6.2.9.(氣喘) 與 13.17.1.(異位性皮膚炎)，純按章節碼排序
            #   會把氣喘排在最前面、把 AD 擠到後面 —— 對皮膚科醫師是本末倒置。
            secs_all = sorted(r["sections"], key=code_tuple)
            derm_pref = tags["sections"]
            secs_derm = [c for c in secs_all if any(match_prefix(c, p) for p in derm_pref)]
            secs_other = [c for c in secs_all if c not in secs_derm]

            routes[rt] = {
                "label": ROUTE_LABEL[rt],
                "group": r["group"],
                "sections": secs_derm + secs_other,
                "sections_derm": secs_derm,
                "sections_other": secs_other,
                "n_products": len(r["products"]),
                "products": sorted(r["products"]),
                "brand_preview": preview,
                "indications": [
                    {"text": ind_repr[k], "n": n,
                     "state": r["indications"].get(ind_repr[k], "miss")}
                    for k, n in ind_count.most_common(4)
                ],
            }

        all_en = sorted({products[c]["brand_stem_en"] for c in e["codes"] if products[c]["brand_stem_en"]})
        all_zh = sorted({products[c]["brand_stem_zh"] for c in e["codes"] if products[c]["brand_stem_zh"]})
        secs = sorted(e["sections"], key=code_tuple)
        flag_any = {k: False for k in ("prior_review", "consent_form", "course_limited", "no_combination")}
        specialists: set[str] = set()
        for s in secs:
            r = rules.get(s)
            if not r:
                continue
            for k in flag_any:
                flag_any[k] = flag_any[k] or r["flags"].get(k, False)
            specialists.update(r["flags"].get("specialist_only", []))

        rec = {
            "inn": key,
            "inn_display": key.title().replace("(", "(").strip(),
            "zh_common": zh,
            "inn_aliases": sorted({a.title() for a in alias_rev.get(key, []) if a != key}),
            "atc": sorted(e["atc"]),
            "is_combo": e["is_combo_member"],
            "combo_keys": sorted(e["combo_keys"]),
            "sections": secs,
            "n_products": len(e["codes"]),
            "routes": routes,
            "brands_en": all_en,
            "brands_zh": all_zh,
            "flags": {**flag_any, "specialist_only": sorted(specialists)},
            "derm": bool(reasons),
            "derm_reasons": reasons,
        }
        out[key] = rec
        n_derm += bool(reasons)

    (STAGING / "ingredients.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")

    canary = [c.upper() for c in tags["canary_inn"]]
    missing = [c for c in canary if not out.get(c, {}).get("derm")]
    print(f"✅ ingredients.json {len(out):,} 個學名｜皮膚科 {n_derm:,}")
    print(f"   金絲雀 {len(canary)-len(missing)}/{len(canary)}" + (f"  ❌ 缺: {missing}" if missing else "  ✅"))
    (STAGING / "tag_report.json").write_text(json.dumps({
        "generated_at": TODAY, "n_ingredients": len(out), "n_derm": n_derm,
        "canary_missing": missing,
        "derm_products": sum(i["n_products"] for i in out.values() if i["derm"]),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
