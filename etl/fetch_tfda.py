#!/usr/bin/env python3
"""下載食藥署西藥許可證資料集（回傳的是 ZIP，內含約 79 MB 的 JSON）。

用法：
    python3 etl/fetch_tfda.py [--cached]

只取「適應症」等欄位。刻意不碰 endpoint 39（仿單全文/圖檔）—— 那是藥廠的
語文著作，重新散布的風險與單一欄位不是同一個量級。
"""

from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import RAW, SOURCES, TFDA_LICENCE  # noqa: E402
from lib.http import download  # noqa: E402
from lib.prov import Registry  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cached", action="store_true")
    args = ap.parse_args()

    dest = RAW / "tfda_licence.json"
    reg = Registry(SOURCES)
    if args.cached and dest.exists():
        reg.register_http("tfda_json", TFDA_LICENCE, dest, cached=True)
        reg.dump()
        print(f"⏭  沿用既有 {dest} ({dest.stat().st_size/1e6:.1f} MB)")
        return 0

    zip_path = RAW / "tfda_licence.zip"
    print("⬇️  下載食藥署許可證資料集")
    n = download(TFDA_LICENCE, zip_path)
    with zipfile.ZipFile(io.BytesIO(zip_path.read_bytes())) as z:
        name = next(n for n in z.namelist() if n.endswith(".json"))
        dest.write_bytes(z.read(name))
    zip_path.unlink(missing_ok=True)
    reg.register_http("tfda_json", TFDA_LICENCE, dest, zip_bytes=n)
    reg.dump()
    print(f"✅ 完成 ZIP {n/1e6:.1f} MB → JSON {dest.stat().st_size/1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
