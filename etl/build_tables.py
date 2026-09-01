#!/usr/bin/env python3
"""為所有已快照的 PDF 產生表格 sidecar。

用法：
    python3 etl/build_tables.py

獨立成一支是因為：改了 pdftable.py 的演算法要能單獨重跑全部，
不必重新下載 534 份 PDF，也不會碰到 snapshots/text（diff 的比對基準）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import BUILD, SNAP_PDF  # noqa: E402
from lib.pdftable import EXTRACTOR_VERSION, extract_tables  # noqa: E402


def main() -> int:
    import fitz

    out = BUILD / "tables"
    out.mkdir(parents=True, exist_ok=True)
    n_tab = n_sec = n_rej = 0
    for pdf in sorted(SNAP_PDF.glob("*.pdf")):
        with fitz.open(pdf) as doc:
            tables, rejected = extract_tables(doc)
        (out / f"{pdf.stem}.json").write_text(json.dumps({
            "pdf": pdf.name, "extractor_version": EXTRACTOR_VERSION,
            "tables": tables, "rejected": rejected,
        }, ensure_ascii=False), encoding="utf-8")
        n_tab += len(tables)
        n_rej += len(rejected)
        n_sec += bool(tables)
    print(f"✅ 表格 sidecar：{n_sec} 節有表格、共 {n_tab} 個表格、拒絕 {n_rej}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
