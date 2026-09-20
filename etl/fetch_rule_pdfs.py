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
from config import BUILD, CURATION, MANIFEST, PDF_URL, RAW, SNAP_PDF, SNAP_TEXT, STAGING  # noqa: E402
from lib.http import download  # noqa: E402
from lib.nhi_live import all_chapter_files, resolve as resolve_live  # noqa: E402
from lib.section import code_tuple, split_pay_codes, split_pay_urls  # noqa: E402

TODAY = date.today().isoformat()


def collect_targets() -> tuple[dict[str, tuple[str, str]], set[str],
                              dict[str, str], dict[frozenset[str], str]]:
    """掃全檔的 PAYCODE_URL_LIST，得到 {章節碼: (檔名, 生效日)} 與所有出現過的章節碼。

    第三、四個回傳值都是為了問官方查詢 API（見 lib/nhi_live.py）：
      witness  {章節碼: 任一引用它的藥品代號}，_acquire() 單節救援用
      combos   {章節碼集合: 代表藥品代號}，live_overlay() 做集合覆蓋用
    """
    import csv

    csv.field_size_limit(1 << 24)
    files: dict[str, tuple[str, str]] = {}
    all_codes: set[str] = set()
    witness: dict[str, str] = {}
    combos: dict[frozenset[str], str] = {}
    with (RAW / "nhi_drug.csv").open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            all_codes.update(split_pay_codes(r["給付規定章節"]))
            urls = split_pay_urls(r["給付規定章節連結"])
            drug = (r["藥品代號"] or "").strip()
            if urls and drug:
                combos.setdefault(frozenset(urls), drug)
            for code, (fn, iso) in urls.items():
                witness.setdefault(code, drug)
                prev = files.get(code)
                if prev is None or iso > prev[1]:
                    files[code] = (fn, iso)
    return files, all_codes, witness, combos


def cover_witnesses(combos: dict[frozenset[str], str]) -> list[str]:
    """貪婪集合覆蓋：挑出最少幾支藥，就能問到全部章節的現行檔名。

    官方查詢 API 是以「藥」為單位回章節檔名清單，沒有「列出所有章節」的端點。
    一支藥常一次帶到 6–9 節，實測 534 節縮到約 484 次查詢（1.5 分鐘）。
    """
    remaining = set().union(*combos) if combos else set()
    items = list(combos.items())
    picks: list[str] = []
    while remaining:
        best_set, best_drug = max(items, key=lambda kv: len(kv[0] & remaining))
        if not (best_set & remaining):
            break
        picks.append(best_drug)
        remaining -= best_set
    return picks


def live_overlay(files: dict[str, tuple[str, str]],
                 combos: dict[frozenset[str], str]) -> int:
    """用官方查詢 API 的現行檔名覆蓋主檔連結，回傳被修正的節數。

    ★ 為什麼不能只信主檔：開放資料 CSV 是月更快照，健保署換章節 PDF 時會同時
      把舊檔下架。空窗期內 CSV 的連結一律 400，而且**檔名沒變**，增量模式會
      判成「未異動」直接跳過 —— 官方明明改了條文，本站卻毫無反應。
      實測 2026-09-20：2.6.1.（降血脂）與 2.6.3. 都已是 _20260901 版，
      CSV 仍指著 2021／2023 年的舊檔，兩個檔都已在官方站台上不存在。

    API 掛掉就整批放棄、沿用主檔連結（回 0）—— 這是加分的校正層，
    不該讓外部服務的臨時故障擋住整條管線。
    """
    witnesses = cover_witnesses(combos)
    print(f"🛰  向官方查詢 API 核對現行檔名（{len(witnesses)} 次查詢，約 1–2 分鐘）")
    live = all_chapter_files(
        witnesses,
        on_error=lambda d, e: print(f"   ⚠️  查詢 {d} 失敗：{e}"))
    if not live:
        print("   ⚠️  查詢 API 無回應，本次沿用主檔連結")
        return 0
    fixed = 0
    for code, (lfn, liso) in live.items():
        cur = files.get(code)
        if cur and cur[0] != lfn and liso >= cur[1]:
            print(f"   ↻ {code} 主檔 {cur[0]} → 官方現行 {lfn}")
            files[code] = (lfn, liso)
            fixed += 1
    print(f"   ✅ 核對 {len(live)}/{len(files)} 節，修正 {fixed} 節")
    return fixed


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

    from build_tables import sidecar
    from lib.formlines import extract_visual_lines
    from lib.pdftable import extract_tables

    with fitz.open(pdf) as doc:
        tables, rejected = extract_tables(doc)
        # 表單填空欄位被拆行的還原資料（見 lib/formlines.py）
        visual_lines = extract_visual_lines(doc)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{pdf.stem}.json").write_text(
        json.dumps(sidecar(pdf.name, tables, rejected, visual_lines),
                   ensure_ascii=False), encoding="utf-8")
    return len(tables)


def _pending_codes() -> set[str]:
    """curation/pending_updates.yaml 裡登記「已公告、等它落地」的章節碼。"""
    p = CURATION / "pending_updates.yaml"
    if not p.exists():
        return set()
    try:
        import yaml
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:                                 # noqa: BLE001
        return set()
    return {str(x["section"]) for x in (data.get("pending") or []) if x.get("section")}


def _download_snapshot(fn: str) -> None:
    """抓一份章節 PDF 進 snapshots/pdf。

    ★ 絕不「先刪本機檔再下載」。snapshots/ 是本案唯一的 provenance，官方一旦
      換檔，舊版原文就再也拿不回來。2026-09-20 實測過後果：2.6.1. 被強制重抓，
      官方已把舊檔下架回 400，先刪的那一步讓快照憑空消失，整條管線也跟著中止。
      改成先落暫存檔、成功才覆蓋 —— 下載失敗時本機仍保有上一版原文。
    """
    tmp = STAGING / f"refetch_{fn}"
    try:
        download(PDF_URL.format(fn), tmp)
        tmp.replace(SNAP_PDF / fn)           # 同一個檔案系統，rename 是原子操作
    finally:
        tmp.unlink(missing_ok=True)
    time.sleep(0.3)                          # 對官方站台的基本禮貌


def _acquire(code: str, fn: str, iso: str, witness: str | None,
             *, refetch: bool) -> tuple[str, str]:
    """確保該節的 PDF 在快照裡，回傳實際落地的 (檔名, 生效日)。

    ★ 主檔連結會過期：開放資料 CSV 是月更快照，健保署換章節 PDF 時會同時把
      舊檔下架，空窗期內照 CSV 抓一律 400。這時改問官方查詢 API 要現行檔名
      （見 lib/nhi_live.py）—— 不猜檔名、不改日期，只問官方。
    """
    if (SNAP_PDF / fn).exists() and not refetch:
        return fn, iso
    try:
        _download_snapshot(fn)
        return fn, iso
    except Exception:                                 # noqa: BLE001
        live = resolve_live(code, witness)
        if not live or live[0] == fn:
            raise                                     # 官方也說是這個檔名 → 真的失敗
        lfn, liso = live
        print(f"  ↻ {code} 主檔連結已過期（{fn}），官方現行為 {lfn}")
        _download_snapshot(lfn)
        return lfn, liso


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只抓前 N 個（開發用）")
    ap.add_argument("--force", action="store_true", help="忽略 manifest，全部重抓")
    ap.add_argument("--no-live", action="store_true",
                    help="跳過官方查詢 API 的現行檔名核對（離線或測試用）")
    args = ap.parse_args()

    files, all_codes, witness, combos = collect_targets()
    no_pdf = sorted(all_codes - set(files), key=code_tuple)
    print(f"📑 章節碼 {len(all_codes)} 個｜有 PDF {len(files)} 個｜無 PDF {len(no_pdf)} 個 {no_pdf}")
    if not args.no_live:
        live_overlay(files, combos)

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    targets = sorted(files.items(), key=lambda kv: code_tuple(kv[0]))
    if args.limit:
        targets = targets[: args.limit]

    pending_codes = _pending_codes()
    if pending_codes:
        print(f"🔁 待更新清單 {sorted(pending_codes)} 每次強制重抓比對")

    stats = {"new": 0, "unchanged": 0, "revised": 0, "silent_edit": 0,
             "stale": 0, "failed": 0}
    events: list[dict] = []

    for i, (code, (fn, iso)) in enumerate(targets, 1):
        prev = manifest.get(code)

        # ★ pending_updates.yaml 裡的章節每次都強制重抓比對。
        #   增量模式只在「檔名的生效日變了」才下載，抓不到「同檔名換內容」。
        #   而 pending 清單記的正是「已公告、等它落地」的章節 —— 沒有這一段，
        #   那份清單就只是靜態備忘，沒有任何機制會告訴你它何時真的更新了。
        #   實測 2.6.1. 降血脂：官方公告 115/9/1 生效，但條文 PDF 檔名仍是
        #   2021-03-29，增量模式永遠跳過它。
        refetch = not args.force and code in pending_codes

        # ★ 生效日只進不退。主檔連結過期時（官方已換版、CSV 還沒跟上）目標會是
        #   一個比現行版更舊的檔名，而那份舊快照往往還躺在 snapshots/（刻意保留
        #   的 provenance），於是會「成功」退版回去 —— 把 2026 的條文換成 2021 的，
        #   還在 changelog 記一筆假改版。正常情況 live_overlay 已經把檔名修正，
        #   這一段是 API 掛掉時的保險。官方真要退版，寧可漏抓也不要自動套用。
        if prev and not args.force and prev.get("effective_date") \
                and prev["pdf_filename"] != fn and iso < prev["effective_date"]:
            print(f"  ⏭  {code} 主檔連結 {fn}（{iso}）舊於現行 {prev['pdf_filename']}"
                  f"（{prev['effective_date']}），不退版")
            prev["last_verified"] = TODAY
            stats["unchanged"] += 1
            continue

        if not args.force and not refetch and prev and prev["pdf_filename"] == fn \
                and (SNAP_PDF / fn).exists():
            prev["last_verified"] = TODAY
            stats["unchanged"] += 1
            continue

        try:
            fn, iso = _acquire(code, fn, iso, witness.get(code), refetch=refetch)
            pdf_path = SNAP_PDF / fn
            txt_path = SNAP_TEXT / fn.replace(".pdf", ".txt")
            sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            text = extract_text(pdf_path)
            txt_path.write_text(text, encoding="utf-8")
            extract_tables_to(pdf_path, BUILD / "tables")
        except Exception as e:                        # noqa: BLE001
            # ★ 抓不到 ≠ 一定要中止。本機若還留著上一版快照，這一節就沿用原文
            #   （publish 出去的內容與上一版一模一樣，不會出現半套資料），
            #   只記成 stale 讓人看到。真正沒有任何原文可用才是硬失敗。
            cached = prev and prev.get("pdf_filename") \
                and (SNAP_PDF / prev["pdf_filename"]).exists() and prev.get("char_count")
            kind = "fetch_stale" if cached else "fetch_failed"
            stats["stale" if cached else "failed"] += 1
            events.append({"code": code, "kind": kind, "error": str(e),
                           "cached": prev["pdf_filename"] if cached else None})
            print(("  ⚠️  " if cached else "  ❌ ") + f"{code} {fn}: {e}"
                  + (f"（沿用快照 {prev['pdf_filename']}）" if cached else ""))
            if cached:
                prev["last_verified"] = TODAY
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
            # ★ 沒換檔名就不能動 prev_filename，否則會變成指向自己。
            #   pending 清單的章節每次都重抓，若無條件寫入，第二次重跑就把
            #   「上一版是哪個檔」這個唯一的溯源線索洗掉。
            "prev_filename": ((prev or {}).get("prev_filename") if kind == "unchanged"
                              else (prev or {}).get("pdf_filename")),
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
    if stats["stale"]:
        print(f"⚠️  {stats['stale']} 節抓不到但有快照，沿用上一版原文（見 fetch_events.json）")
    # 只有「完全沒有原文可用」才中止管線。沿用快照的節不影響已出版內容，
    # 為了它讓整條管線停掉，等於藥品與處置也跟著卡在上個月。
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
