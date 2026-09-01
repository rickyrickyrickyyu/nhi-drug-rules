#!/usr/bin/env python3
"""補抓處置醫令的「所屬章節」（第X部第X章第X節）。

★ 為什麼要另外抓：
  開放資料的處置 CSV 只有代碼／點數／名稱／備註，沒有章節。
  但健保署官方的「支付標準查詢」（INAE5001）有 treaT_CHAP_CODE 欄位，
  例如 51017C 液態氮冷凍治療 = 第二部第二章第六節。
  醫師要在官方支付標準原文（.doc）裡找到這一條，靠的就是這個定位。

★ 為什麼不是直接連 PDF：
  健保署對「藥品給付規定」有逐節 PDF（getPDF?DurgFileName=），
  對「醫療服務給付項目」沒有 —— 官方只發布整份支付標準壓縮檔（.doc）。
  所以這裡給的是「章節定位 + 官方原文下載頁」，不編造不存在的逐項 PDF 連結。

★ RDO_TYPE=2 是「目前給付中」，回傳 6,173 筆，與開放資料 CSV 完全同數。
  RDO_TYPE=0/1 是含歷次異動的 22,973 筆，不是我們要的現行集合。

用法：
    python3 etl/fetch_proc_chapters.py [--cached]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import RAW, SOURCES  # noqa: E402
from lib.prov import Registry  # noqa: E402

API = "https://info.nhi.gov.tw/api/inae5000/inae5001s01/SQL0001"
# ★ 伺服器把每頁上限鎖在 50（送 1000 也只回 50），所以是 124 頁不是 7 頁
PAGE = 50
# 官方查詢系統的入口（POST 查詢，無法對單一代碼做深連結）
QUERY_PAGE = "https://info.nhi.gov.tw/INAE5000/INAE5001S01"
# 官方支付標準原文（整份 .doc 壓縮檔）的發布頁
OFFICIAL_DOC_PAGE = "https://www.nhi.gov.tw/ch/lp-3778-1.html"


def _post(page: int, per: int) -> dict:
    body = json.dumps({
        "KEYWORD": "", "CNAME": "", "ENAME": "", "CODE": "", "MEMO": "",
        "TREAT_CHAP_CODE": "", "PAY_S_DATE": "", "RDO_TYPE": "2",
        "showPage": page, "showCounts": per,
    }).encode()
    req = urllib.request.Request(
        API, data=body,
        headers={"Content-Type": "application/json",
                 "Referer": "https://info.nhi.gov.tw/INAE5000/INAE5001S02"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cached", action="store_true")
    args = ap.parse_args()

    dest = RAW / "nhi_proc_chapters.json"
    reg = Registry(SOURCES)
    if args.cached and dest.exists():
        print(f"⏭  沿用既有 {dest}")
        reg.register_http("nhi_proc_api", API, dest, cached=True)
        reg.dump()
        return 0

    total = _post(1, 1)["counts"]
    print(f"⬇️  支付標準查詢 API：{total:,} 筆現行醫令")
    out: dict[str, str] = {}
    seen = 0
    for p in range(1, (total + PAGE - 1) // PAGE + 1):
        d = _post(p, PAGE)["data"]
        seen += len(d)
        for row in d:
            chap = (row.get("treaT_CHAP_CODE") or "").strip()
            if chap:
                out[row["treaT_CODE"].strip()] = chap
        if p % 20 == 0 or p == 1:
            print(f"   第 {p} 頁（累計 {len(out):,}）")
        time.sleep(0.35)         # 對政府主機客氣一點

    # ★ 完整性看「取到幾列」，不是「幾筆有章節」：
    #   官方資料本身就有 1,276 筆章節欄位是空的（多為藥事服務費一類），
    #   拿有章節數去比總筆數會誤判成分頁中斷。
    if seen < total:
        print(f"❌ 只取得 {seen}／{total} 列，疑似分頁中斷，不覆寫既有檔案")
        return 1

    dest.write_text(json.dumps(
        {"schema": 1, "api": API, "query_page": QUERY_PAGE,
         "official_doc_page": OFFICIAL_DOC_PAGE, "chapters": out},
        ensure_ascii=False, indent=1), encoding="utf-8")
    reg.register_http("nhi_proc_api", API, dest)
    reg.dump()
    print(f"✅ {seen:,} 列，其中 {len(out):,} 筆有章節定位（官方 {seen-len(out):,} 筆本無章節）→ {dest.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
