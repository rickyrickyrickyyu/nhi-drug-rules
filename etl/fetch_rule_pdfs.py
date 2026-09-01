#!/usr/bin/env python3
"""下載給付規定章節 PDF，並維護不可變快照。

用法：
    python3 etl/fetch_rule_pdfs.py [--limit N] [--force]

改版偵測完全依賴檔名日期 —— 官方不提供版本 API，檔名裡的生效日就是唯一
可靠的版本鍵。同時比對 sha256 抓「檔名沒變但內容變了」的靜默改檔。

★ 快照進 git 是刻意的：官方一旦換檔，舊版原文就再也拿不回來，
  git 是本專案唯一的 provenance。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import BUILD, MANIFEST, PDF_URL, RAW, SNAP_PDF, SNAP_TEXT, STAGING  # noqa: E402
from lib.http import download  # noqa: E402
from lib.section import code_tuple, split_pay_codes, split_pay_urls  # noqa: E402

TODAY = date.today().isoformat()


def collect_targets() -> tuple[dict[str, tuple[str, str]], set[str]]:
    """掃全檔的 PAYCODE_URL_LIST，得到 {章節碼: (檔名, 生效日)} 與所有出現過的章節碼。"""
    import csv

    csv.field_size_limit(1 << 24)
    files: dict[str, tuple[str, str]] = {}
    all_codes: set[str] = set()
    with (RAW / "nhi_drug.csv").open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            all_codes.update(split_pay_codes(r["給付規定章節"]))
            for code, (fn, iso) in split_pay_urls(r["給付規定章節連結"]).items():
                prev = files.get(code)
                if prev is None or iso > prev[1]:
                    files[code] = (fn, iso)
    return files, all_codes


def extract_text(pdf: Path) -> str:
    """★ 這個函式的輸出格式不可改動。

    snapshots/text/*.txt 是 diff_rules.py 逐月比對的基準。只要在裡面插入任何
    標記（例如表格分隔符），下一次 refresh 會讓 500+ 節誤報 silent_edit，
    把「官方偷改條文」這個最重要的警訊淹沒。表格走獨立 sidecar，見 extract_tables_to()。
    """
    import fitz

    with fitz.open(pdf) as doc:
        return "\n".join(page.get_text() for page in doc)


def extract_tables_to(pdf: Path, out_dir: Path) -> int:
    """表格還原成獨立 sidecar，放 data/build/tables/（衍生資料，不進 snapshots）。"""
    import fitz

    from lib.pdftable import EXTRACTOR_VERSION, extract_tables

    with fitz.open(pdf) as doc:
        tables, rejected = extract_tables(doc)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{pdf.stem}.json").write_text(json.dumps({
        "pdf": pdf.name, "extractor_version": EXTRACTOR_VERSION,
        "tables": tables, "rejected": rejected,
    }, ensure_ascii=False), encoding="utf-8")
    return len(tables)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只抓前 N 個（開發用）")
    ap.add_argument("--force", action="store_true", help="忽略 manifest，全部重抓")
    args = ap.parse_args()

    files, all_codes = collect_targets()
    no_pdf = sorted(all_codes - set(files), key=code_tuple)
    print(f"📑 章節碼 {len(all_codes)} 個｜有 PDF {len(files)} 個｜無 PDF {len(no_pdf)} 個 {no_pdf}")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    targets = sorted(files.items(), key=lambda kv: code_tuple(kv[0]))
    if args.limit:
        targets = targets[: args.limit]

    stats = {"new": 0, "unchanged": 0, "revised": 0, "silent_edit": 0, "failed": 0}
    events: list[dict] = []

    for i, (code, (fn, iso)) in enumerate(targets, 1):
        prev = manifest.get(code)
        pdf_path = SNAP_PDF / fn
        txt_path = SNAP_TEXT / fn.replace(".pdf", ".txt")

        if not args.force and prev and prev["pdf_filename"] == fn and pdf_path.exists():
            prev["last_verified"] = TODAY
            stats["unchanged"] += 1
            continue

        try:
            if not pdf_path.exists():
                download(PDF_URL.format(fn), pdf_path)
                time.sleep(0.3)                      # 對官方站台的基本禮貌
            sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            text = extract_text(pdf_path)
            txt_path.write_text(text, encoding="utf-8")
            extract_tables_to(pdf_path, BUILD / "tables")
        except Exception as e:                        # noqa: BLE001
            stats["failed"] += 1
            events.append({"code": code, "kind": "fetch_failed", "error": str(e)})
            print(f"  ❌ {code} {fn}: {e}")
            continue

        if prev is None:
            kind = "new"
        elif prev["pdf_filename"] != fn:
            kind = "revised"
        elif prev.get("pdf_sha256") != sha:
            kind = "silent_edit"                      # 官方改內容卻沒改檔名，最需要警示
        else:
            kind = "unchanged"
        stats[kind] += 1
        if kind != "unchanged":
            events.append(
                {"code": code, "kind": kind, "from": (prev or {}).get("pdf_filename"), "to": fn}
            )

        manifest[code] = {
            "section_code": code,
            "pdf_filename": fn,
            "effective_date": iso,
            "pdf_sha256": sha,
            "char_count": len(text.strip()),
            "first_seen": (prev or {}).get("first_seen", TODAY) if kind != "revised" else TODAY,
            "last_verified": TODAY,
            "prev_filename": (prev or {}).get("pdf_filename"),
        }
        if i % 50 == 0:
            print(f"  … {i}/{len(targets)}")

    for code in no_pdf:
        manifest.setdefault(code, {"section_code": code, "no_pdf": True, "first_seen": TODAY})

    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    (STAGING / "fetch_events.json").write_text(
        json.dumps({"generated_at": TODAY, "stats": stats, "events": events},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ {stats}")
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
