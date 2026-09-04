#!/usr/bin/env python3
"""下載食藥署「仿單／外盒圖檔連結」開放資料（許可證字號 → 官方仿單）。

★ 為什麼是這份資料：
  先前的仿單劑量層取自許可證資料的「用法用量」欄位，皮膚科只覆蓋 24%，
  而且 isotretinoin / dupilumab / cyclosporin / methotrexate 全是空的。
  這份資料集直接給「每張許可證的官方仿單網址」，皮膚科覆蓋 93% 的學名。

★ 只連結、不鏡射：
  mcp.fda.gov.tw 明訂未經同意不得重製轉載。但這些 URL 是食藥署**自己的開放
  資料**發布的，連過去正是它的用途。本站不下載、不快取任何仿單內容。

★ 為什麼只存布林旗標而非 URL：
  開放資料有兩種形式（pdfcasefile 直接 PDF、exportpdf/<許可證字號>）。
  實測 `https://mcp.fda.gov.tw/exportpdf/<許可證字號>` 對兩種都回 200，
  所以網址可由既有的 licence_no 推導 —— 45,179 個品項逐筆存 URL 會讓
  離線包多出 1.6 MB，沒有必要。

用法：
    python3 etl/fetch_tfda_inserts.py [--cached]
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import RAW, SOURCES, TFDA_INSERTS, USER_AGENT  # noqa: E402
from lib.prov import Registry  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cached", action="store_true")
    args = ap.parse_args()

    dest = RAW / "tfda_inserts.json"
    reg = Registry(SOURCES)
    if args.cached and dest.exists():
        print(f"⏭  沿用既有 {dest.name}")
        reg.register_http("tfda_inserts", TFDA_INSERTS, dest, cached=True)
        reg.dump()
        return 0

    print("⬇️  下載食藥署仿單連結資料")
    req = urllib.request.Request(TFDA_INSERTS, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as r:
        blob = r.read()

    # 這個 endpoint 回傳的是 zip，內含單一 json
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        rows = json.loads(z.read(z.namelist()[0]).decode("utf-8"))

    out: dict[str, bool] = {}
    for row in rows:
        lic = (row.get("許可證字號") or "").strip()
        url = (row.get("仿單圖檔連結") or "").strip()
        if lic and url:
            out[lic] = True

    dest.write_text(json.dumps({"schema": 1, "source": TFDA_INSERTS,
                                "licences": sorted(out)},
                               ensure_ascii=False), encoding="utf-8")
    reg.register_http("tfda_inserts", TFDA_INSERTS, dest)
    reg.dump()
    print(f"✅ {len(out):,} 張許可證有官方仿單 → {dest.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
