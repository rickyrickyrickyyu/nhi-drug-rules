#!/usr/bin/env python3
"""下載健保署的獨立附表 PDF。

★ 為什麼需要這一步：
  條文 PDF 裡的附表區塊，對 8.2.4.x 生物製劑家族而言只有「◎附表二十二之一：…」
  這種引用行（46–168 字），**本體不在裡面**。健保署把附表當獨立檔案發布在
  另一個頁面。少了這一步，醫師點附表徽章就是死路。

★ 為什麼 URL 要人工維護在 curation/appendix_files.yaml：
  來源列表頁對程式回 403（WAF），只有瀏覽器開得起來；
  但列表裡的 dl-…-1.pdf 檔案本身可以直接下載（實測 200）。
  所以 URL 對照人工維護、檔案下載自動化。gate 36 會在 URL 失效時叫你重抓。

★ 快照進 git 的理由與章節 PDF 相同：健保署換檔後就拿不回舊版，
  這是唯一的 provenance；同檔名內容變動 = 靜默改檔，要能偵測。

用法：
    python3 etl/fetch_appendix_pdfs.py [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import APPX_MANIFEST, CURATION, SNAP_APPX  # noqa: E402
from lib.http import download  # noqa: E402

TODAY = date.today().isoformat()


def safe_name(name: str) -> str:
    """附表名 → 檔名。附表名只含中文與「之」「-」與數字，直接可用。"""
    return name.replace("/", "_").replace(" ", "")


def load_curation() -> dict:
    p = CURATION / "appendix_files.yaml"
    if not p.exists():
        return {}
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("appendices") or {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="忽略既有快照，全部重抓")
    args = ap.parse_args()

    entries = load_curation()
    if not entries:
        print("⚠️  curation/appendix_files.yaml 無資料，略過")
        return 0

    SNAP_APPX.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(APPX_MANIFEST.read_text(encoding="utf-8")) \
        if APPX_MANIFEST.exists() else {}

    stats = {"new": 0, "unchanged": 0, "silent_edit": 0, "failed": 0}
    events: list[dict] = []

    for name, meta in entries.items():
        url = meta.get("url")
        if not url:
            continue
        dest = SNAP_APPX / f"{safe_name(name)}.pdf"
        prev = manifest.get(name)

        if not args.force and prev and dest.exists() and prev.get("url") == url:
            prev["last_verified"] = TODAY
            stats["unchanged"] += 1
            continue

        try:
            download(url, dest)
            time.sleep(0.3)                       # 對政府主機的基本禮貌
            sha = hashlib.sha256(dest.read_bytes()).hexdigest()
        except Exception as e:                    # noqa: BLE001
            stats["failed"] += 1
            events.append({"name": name, "kind": "fetch_failed", "error": str(e)})
            print(f"  ❌ {name}: {e}")
            continue

        if prev is None:
            kind = "new"
        elif prev.get("sha256") != sha:
            # 同一個 URL、內容卻變了 = 健保署改了附表但沒換連結
            kind = "silent_edit" if prev.get("url") == url else "new"
        else:
            kind = "unchanged"
        stats[kind] = stats.get(kind, 0) + 1
        if kind != "unchanged":
            events.append({"name": name, "kind": kind})

        manifest[name] = {
            "url": url,
            "title": meta.get("title", ""),
            "updated": meta.get("updated", ""),
            "sha256": sha,
            "bytes": dest.stat().st_size,
            "fetched_at": TODAY,
            "last_verified": TODAY,
        }

    APPX_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ 附表 PDF {len(manifest)} 個｜{stats}")
    for e in events[:10]:
        print(f"   · {e['name']} {e['kind']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
