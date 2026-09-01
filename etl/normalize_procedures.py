#!/usr/bin/env python3
"""醫療服務給付項目及支付標準 → 正規化的處置資料。

用法：
    python3 etl/normalize_procedures.py

輸出 .staging/procedures.json：{代碼: {...}}
"""

from __future__ import annotations

import csv
import json
import sys
import unicodedata
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import CURATION, PROC_CSV_COLUMNS, RAW, STAGING  # noqa: E402
from lib.roc import roc_to_iso  # noqa: E402

csv.field_size_limit(1 << 24)
TODAY = date.today().isoformat()


def _nfc(s: str) -> str:
    """健保 PDF 與 CSV 都夾雜 CJK 相容表意文字（U+F900–FAFF），
    長得一樣但碼位不同，不正規化的話關鍵字整批比不中。"""
    return unicodedata.normalize("NFC", s or "")


def _load_chapters() -> dict[str, str]:
    """支付標準章節定位。抓不到就留空 —— 缺欄位不該讓整個 build 停擺。"""
    p = RAW / "nhi_proc_chapters.json"
    if not p.exists():
        print("⚠️  無 nhi_proc_chapters.json，章節欄位留空（跑 fetch_proc_chapters.py 可補）")
        return {}
    return json.loads(p.read_text(encoding="utf-8")).get("chapters", {})


def main() -> int:
    src = RAW / "nhi_proc.csv"
    if not src.exists():
        raise SystemExit("❌ 找不到 data/raw/nhi_proc.csv，請先跑 fetch_procedures.py")

    chapters = _load_chapters()
    tags = yaml.safe_load((CURATION / "procedure_tags.yaml").read_text(encoding="utf-8"))
    groups = tags["groups"]
    block = set(tags.get("blocklist") or {})
    extra = set(tags.get("extra_codes") or [])

    # 代碼 → 同義詞（中英合併）與群組
    syn: dict[str, list[str]] = {}
    grp: dict[str, str] = {}
    primary: set[str] = set()
    for gname, g in groups.items():
        terms = [*(g.get("zh") or []), *(g.get("en") or []), g.get("label", "")]
        for i, code in enumerate(g["codes"]):
            syn.setdefault(code, []).extend(t for t in terms if t)
            grp[code] = gname
            if i == 0:
                # yaml 裡群組的第一個代碼＝該群組的首選（最貼近該說法的醫令）。
                # 查「液態氮」時 51017C 液態氮冷凍治療 應排在 37002B 冷凍治療之前。
                primary.add(code)

    with src.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        cols = [c.lstrip("﻿") for c in (r.fieldnames or [])]
        if cols != PROC_CSV_COLUMNS:
            raise SystemExit(f"❌ 處置 CSV 欄位契約不符\n預期 {PROC_CSV_COLUMNS}\n實際 {cols}")
        rows = list(r)

    out: dict[str, dict] = {}
    for row in rows:
        code = (row["診療項目代碼"] or "").strip()
        if not code:
            continue
        start, end = roc_to_iso(row["生效起日"]), roc_to_iso(row["生效迄日"])
        # 官方用「29101231」這種遠期日期表示現行有效
        active = not end or end >= TODAY
        try:
            points = float(row["健保支付點數"] or 0)
        except ValueError:
            points = 0.0

        is_derm = (code in syn or code in extra) and code not in block
        out[code] = {
            "code": code,
            "name_zh": _nfc(row["中文項目名稱"]).strip(),
            "name_en": _nfc(row["英文項目名稱"]).strip(),
            "points": points,
            "valid_from": start,
            "valid_to": end,
            "status": "active" if active else "retired",
            "note": _nfc(row["備註"]).strip(),
            # 官方支付標準裡的章節定位（開放資料 CSV 沒有這欄，另從
            # 支付標準查詢 API 取得）。醫師要在官方原文 .doc 裡翻到這一條靠它。
            "chapter": chapters.get(code, ""),
            "synonyms": sorted(set(syn.get(code, []))),
            "group": grp.get(code),
            "primary": code in primary,
            "derm": is_derm,
            "derm_reasons": (["curation:procedure_tags"] if is_derm else []),
        }

    (STAGING / "procedures.json").write_text(
        json.dumps(out, ensure_ascii=False), encoding="utf-8")

    n_chap = sum(1 for p in out.values() if p["chapter"])
    n_derm = sum(1 for p in out.values() if p["derm"])
    n_note = sum(1 for p in out.values() if p["note"])
    missing = [c for c in tags["canary"] if not out.get(c, {}).get("derm")]
    print(f"✅ procedures.json {len(out):,} 筆｜皮膚科 {n_derm}｜有備註 {n_note:,}｜有章節 {n_chap:,}")
    print(f"   金絲雀 {len(tags['canary'])-len(missing)}/{len(tags['canary'])}"
          + (f"  ❌ 缺 {missing}" if missing else "  ✅"))
    bad = [c for c in syn if c not in out]
    if bad:
        print(f"   ⚠️ 同義詞表指向不存在的代碼: {bad}")
    return 1 if missing or bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
