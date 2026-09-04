#!/usr/bin/env python3
"""把獨立附表 PDF 解析成可渲染的結構（文字 + 表格 + 視覺行）。

★ 為什麼與 fetch_appendix_pdfs.py 拆開：
  比照 build_tables.py 的既有分工 —— 改了表格還原演算法要能單獨重跑全部，
  不必重新下載 77 份 PDF，`make rebuild` 也才能不連網跑完。

★ 用的是既有機制，不另寫渲染邏輯：
  lib/pdftable（框線切格）+ lib/formlines（表單填空欄位的視覺行還原）
  + parse_rules 的 clause 切塊，與章節條文走同一條路。

用法：
    python3 etl/build_appendix.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import APPX_MANIFEST, BUILD, SNAP_APPX  # noqa: E402
from lib.formlines import FORMLINES_VERSION, build_index, extract_visual_lines, rejoin  # noqa: E402
from lib.pdftable import EXTRACTOR_VERSION, extract_tables  # noqa: E402
from lib.tablesplice import splice_clauses  # noqa: E402


def to_clauses(text: str) -> list[dict]:
    """附表是表單／評分表，沒有條號階層 —— 一段一個 clause，level 一律 0。

    刻意不套 parse_rules.split_clauses：那支是為「1. (1) I.」這種條號設計的，
    用在表單上會把「□ 符合下列所有條件」之類的勾選項亂切。
    """
    out = []
    for para in text.split("\n"):
        t = para.rstrip()
        if t.strip():
            out.append({"text": t, "level": 0})
    return out


def main() -> int:
    import fitz

    if not APPX_MANIFEST.exists():
        print("⚠️  無 appendix_manifest.json，請先跑 fetch_appendix_pdfs.py")
        return 0
    manifest = json.loads(APPX_MANIFEST.read_text(encoding="utf-8"))

    out_dir = BUILD / "appendix"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.json"):
        old.unlink()

    n_tab = n_ok = n_miss = 0
    for name, meta in manifest.items():
        pdf = SNAP_APPX / f"{name.replace('/', '_').replace(' ', '')}.pdf"
        if not pdf.exists():
            n_miss += 1
            continue
        with fitz.open(pdf) as doc:
            text = "\n".join(p.get_text() for p in doc)
            tables, rejected = extract_tables(doc)
            vlines = extract_visual_lines(doc)

        clauses = to_clauses(text)
        if vlines:
            idx = build_index(vlines)
            for c in clauses:
                c["text"] = rejoin(c["text"], idx)
        clauses, spliced = splice_clauses(clauses, tables)

        (out_dir / f"{name}.json").write_text(json.dumps({
            "name": name,
            "title": meta.get("title", ""),
            "updated": meta.get("updated", ""),
            "url": meta.get("url", ""),
            "extractor_version": EXTRACTOR_VERSION,
            "formlines_version": FORMLINES_VERSION,
            "clauses": clauses,
            "tables": tables,
            "tables_spliced": spliced,
            "rejected": rejected,
        }, ensure_ascii=False), encoding="utf-8")
        n_ok += 1
        n_tab += len(tables)

    print(f"✅ 附表解析 {n_ok} 個｜表格 {n_tab} 張"
          + (f"｜缺 PDF {n_miss}" if n_miss else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
