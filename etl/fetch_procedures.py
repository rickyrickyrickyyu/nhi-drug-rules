#!/usr/bin/env python3
"""下載健保「醫療服務給付項目及支付標準」（處置／診療項目）。

用法：
    python3 etl/fetch_procedures.py [--cached]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import NHI_PROC_CSV, RAW, SOURCES  # noqa: E402
from lib.http import download  # noqa: E402
from lib.prov import Registry  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cached", action="store_true")
    args = ap.parse_args()

    dest = RAW / "nhi_proc.csv"
    reg = Registry(SOURCES)
    if args.cached and dest.exists():
        print(f"⏭  沿用既有 {dest} ({dest.stat().st_size/1e6:.1f} MB)")
        reg.register_http("nhi_proc_csv", NHI_PROC_CSV, dest, cached=True)
        reg.dump()
        return 0

    print("⬇️  下載醫療服務給付項目及支付標準")
    n = download(NHI_PROC_CSV, dest)
    reg.register_http("nhi_proc_csv", NHI_PROC_CSV, dest)
    reg.dump()
    print(f"✅ 完成 {n/1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
