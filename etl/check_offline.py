#!/usr/bin/env python3
"""離線包是否與線上版同一份資料。

★ 為什麼不做成 validate.py 的閘門：
  離線包是 promote 的「下游」——validate 在 promote 之前跑，那時 offline/
  裡放的必然還是上一輪的產物，當成閘門會每次都誤報，久了就被無視。
  正確位置是 promote 之後（make verify 與一鍵更新腳本的最後一步）。

★ 為什麼比對指紋而非 built 日期：
  built 只到「日」。同一天內重跑 ETL（改 curation、修 parser）資料已變但
  built 不變，只比日期會放行過期的離線包，醫師帶去封閉電腦看到舊條文。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import PUBLIC, ROOT  # noqa: E402
from lib.fingerprint import app_fingerprint, data_fingerprint  # noqa: E402


def main() -> int:
    man = ROOT / "offline" / "MANIFEST.txt"
    if not man.exists():
        print("－ 尚未產生離線包（make offline），略過")
        return 0

    live = data_fingerprint(PUBLIC)
    meta = json.loads((PUBLIC / "meta.json").read_text(encoding="utf-8"))
    body = man.read_text(encoding="utf-8")
    m = re.search(r"fingerprint:\s*(\S+)", body)
    packed = m.group(1) if m else None

    if meta.get("data_fingerprint") != live:
        print(f"❌ public/data 指紋 {live} 與 meta.json 的 "
              f"{meta.get('data_fingerprint')} 不符 → 請重跑 make rebuild")
        return 1
    if packed != live:
        print(f"❌ 離線包資料指紋 {packed} ≠ 線上 {live} → 請重跑 make offline")
        return 1

    # ★ 也要比 app bundle：資料沒變但前端改版時，只比資料會放行一個
    #   「介面還是舊的」離線包。dist-offline 是每次 make offline 前才重建的，
    #   所以它代表「現在的前端」。
    dist = ROOT / "dist-offline"
    am = re.search(r"app_fingerprint:\s*(\S+)", body)
    if dist.exists() and am:
        live_app = app_fingerprint(dist)
        if am.group(1) != live_app:
            print(f"❌ 離線包前端指紋 {am.group(1)} ≠ 目前建置 {live_app}"
                  " → 請重跑 make offline")
            return 1

    print(f"✅ 離線包與線上版同一份資料與前端（指紋 {live}｜快照 {meta['built']}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
