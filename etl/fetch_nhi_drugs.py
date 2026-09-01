#!/usr/bin/env python3
"""下載健保藥品品項主檔（96 MB CSV，每月更新）。

用法：
    python3 etl/fetch_nhi_drugs.py [--cached]

--cached 會在檔案已存在時跳過下載，供本機反覆開發用。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import NHI_DRUG_CSV, RAW, SOURCES  # noqa: E402
from lib.http import download  # noqa: E402
from lib.prov import Registry  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cached", action="store_true", help="已存在就不重抓")
    args = ap.parse_args()

    dest = RAW / "nhi_drug.csv"
    reg = Registry(SOURCES)
    if args.cached and dest.exists():
        print(f"⏭  沿用既有檔案 {dest} ({dest.stat().st_size/1e6:.1f} MB)")
        # 沿用也要登錄 —— 否則 sources.json 會缺這一筆而過不了 gate
        reg.register_http("nhi_csv", NHI_DRUG_CSV, dest, cached=True)
        reg.dump()
        return 0

    print(f"⬇️  下載健保藥品主檔 → {dest}")
    n = download(NHI_DRUG_CSV, dest)
    reg.register_http("nhi_csv", NHI_DRUG_CSV, dest)
    reg.dump()
    print(f"✅ 完成 {n/1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
