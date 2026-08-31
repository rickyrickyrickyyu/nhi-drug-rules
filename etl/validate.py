#!/usr/bin/env python3
"""fail-closed 驗證閘門。全部跑完再一次報告，然後才決定要不要 promote。

用法：
    python3 etl/validate.py [--override 6,10]

刻意不「第一個失敗就 exit」——每月只跑一次，要一次看完全部問題。
warn 級一律實作成 fail，人工看過後用 --override 放行；在 CI 裡只印
warning 而讓 commit 照跑，等於沒有閘門。
"""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import CSV_COLUMNS, CURATION, MANIFEST, PUBLIC, RAW, SNAPSHOTS, STAGING  # noqa: E402
from lib.section import match_prefix  # noqa: E402

PREV = SNAPSHOTS / "last_run.json"


@dataclass
class Gate:
    id: int
    name: str
    passed: bool
    message: str


def run() -> list[Gate]:
    g: list[Gate] = []
    prev = json.loads(PREV.read_text(encoding="utf-8")) if PREV.exists() else {}
    rep = json.loads((STAGING / "normalize_report.json").read_text(encoding="utf-8"))
    products = json.loads((STAGING / "products.json").read_text(encoding="utf-8"))
    ings = json.loads((STAGING / "ingredients.json").read_text(encoding="utf-8"))
    rules = json.loads((STAGING / "rules.json").read_text(encoding="utf-8"))
    tags = yaml.safe_load((CURATION / "derm_tags.yaml").read_text(encoding="utf-8"))

    # 1 品項數健檢
    p0 = prev.get("n_products")
    ok = p0 is None or 0.90 * p0 <= len(products) <= 1.10 * p0
    g.append(Gate(1, "品項數健檢", ok, f"{len(products):,}（上期 {p0}）"))

    # 2 欄位契約
    import csv
    csv.field_size_limit(1 << 24)
    with (RAW / "nhi_drug.csv").open(encoding="utf-8-sig", newline="") as f:
        cols = next(csv.reader(f))
    cols = [c.lstrip("﻿") for c in cols]
    g.append(Gate(2, "CSV 欄位契約", cols == CSV_COLUMNS, f"{len(cols)} 欄"))

    # 3 章節解析率
    g.append(Gate(3, "章節解析數", len(rules) >= 500, f"{len(rules)} 節"))

    # 4/5 PDF 下載與抽字
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    no_text = [c for c, m in man.items() if not m.get("no_pdf") and not m.get("char_count")]
    g.append(Gate(4, "PDF 下載", not no_text, f"缺文字 {len(no_text)} 節 {no_text[:5]}"))
    bad_head = []
    for c, r in rules.items():
        if r.get("no_pdf") or not r.get("text"):
            continue
        if not r["title_raw"] and r["char_count"] < 20:
            bad_head.append(c)
    g.append(Gate(5, "PDF 抽字/首行", not bad_head, f"異常 {len(bad_head)} 節 {bad_head[:5]}"))

    # 7 INN 覆蓋
    rate = rep["n_inn_unresolved"] / max(rep["n_products"], 1)
    g.append(Gate(7, "INN 覆蓋", rate <= 0.02, f"未解析 {rate:.3%}"))

    # 8 Route 覆蓋（皮膚科子集）
    derm_codes = {c for i in ings.values() if i["derm"] for r in i["routes"].values() for c in r["products"]}
    other = sum(1 for c in derm_codes if products[c]["route"] == "OTHER")
    r8 = other / max(len(derm_codes), 1)
    g.append(Gate(8, "Route 覆蓋", r8 <= 0.05, f"皮膚科 OTHER {r8:.2%}"))

    # 13 金絲雀藥物
    canary = [c.upper() for c in tags["canary_inn"]]
    missing = [c for c in canary if not ings.get(c, {}).get("derm")]
    g.append(Gate(13, "金絲雀藥物", not missing, f"{len(canary)-len(missing)}/{len(canary)} 缺:{missing}"))

    # 14 類固醇酯基不可塌縮
    # 真正的危險是「同一個 base 的兩種酯基被併成同一個 key」——例如 betamethasone
    # valerate(Class III) 與 dipropionate(Class I–II) 變成一張卡片。
    # 外用(D07)裸名本身不一定是錯（desoximetasone、hydrocortisone base 都是真實劑型），
    # 所以只在「該 base 已知有多種酯基流通」時才判定為塌縮。
    ew = yaml.safe_load((CURATION / "ester_whitelist.yaml").read_text(encoding="utf-8"))
    preserve = {x.upper() for x in ew["preserve_ester"]}
    topical_keys = collections.defaultdict(set)
    for p in products.values():
        if not p["atc"].startswith("D07") or p["is_combo"]:
            continue
        for k in p["inn_keys"]:
            topical_keys[k.split(" (")[0]].add(k)
    allow_bare = {k.upper() for k in (ew.get("allow_bare_with_ester") or {})}
    collapsed = [
        b for b, ks in topical_keys.items()
        if b in preserve and b in ks and len(ks) > 1 and b not in allow_bare
    ]
    g.append(Gate(14, "類固醇酯基", not collapsed, f"外用裸名與酯基並存: {collapsed or '無'}"))

    # 15 stub 翻轉
    prev_stub = prev.get("stub_codes") or []
    flipped = [c for c in rules if c not in prev_stub and rules[c].get("is_stub")
               and c in prev.get("nonstub_codes", [])]
    g.append(Gate(15, "stub 翻轉", not flipped, f"{len(flipped)} 節 {flipped[:5]}"))

    # 16 皮膚科種子章節必須被標籤命中
    seed = ["13.4.", "13.17.1.", "10.7.1.1.", "10.7.1.2.", "8.2.4.", "10.6.4.", "8.2.16."]
    tagged_secs = {s for i in ings.values() if i["derm"] for s in i["sections"]}
    miss_seed = [s for s in seed if not any(match_prefix(t, s) or match_prefix(s, t) for t in tagged_secs)]
    g.append(Gate(16, "種子章節命中", not miss_seed, f"缺 {miss_seed}"))

    # 11 前端產物
    if (PUBLIC / "derm.json").exists():
        kb = len(gzip.compress((PUBLIC / "derm.json").read_bytes(), 9)) / 1024
        n = len(json.loads((PUBLIC / "derm.json").read_text(encoding="utf-8"))["ing"])
        g.append(Gate(11, "前端產物", kb < 300 and n > 200, f"derm.json {kb:.0f} KB gz / {n} 學名"))
    return g


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--override", default="", help="人工確認後放行的 gate 編號，如 6,10")
    args = ap.parse_args()
    allow = {int(x) for x in args.override.split(",") if x.strip().isdigit()}

    gates = run()
    failed = [g for g in gates if not g.passed and g.id not in allow]
    for g in gates:
        icon = "✅" if g.passed else ("🟡" if g.id in allow else "❌")
        print(f"{icon} gate {g.id:>2} {g.name:<14} {g.message}")
    (STAGING / "validation_report.json").write_text(json.dumps(
        [{"id": g.id, "name": g.name, "passed": g.passed, "message": g.message} for g in gates],
        ensure_ascii=False, indent=2), encoding="utf-8")

    if failed:
        print(f"\n❌ {len(failed)} 個閘門失敗 → 不 promote，staging 保留於 {STAGING}")
        return 1
    print("\n✅ 全部閘門通過")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
