"""食藥署（TFDA）許可證資料的 join 與正規化。

兩個用途，第二個原本沒預期到但更重要：
  1. 仿單適應症 —— 與健保給付規定並排，落差處就是最常被核刪的地方
  2. ★ 修復健保資料的中文品名掉字 —— 健保檔裡 408 個品項的中文名含 ASCII '?'，
     實測 100% 可用 TFDA 補回。多數是 ® 被吃掉（好度?液 → 好度®液），
     少數是罕用字整個掉了（"五洲"嘴?乳膏 → "五洲"嘴疱乳膏）。
     這不是我們的解碼問題 —— '?' 在原始 UTF-8 檔裡就是 0x3F 單一位元組。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# licId = 2 碼字別 + 6 碼流水號。對照由 6000 筆抽樣比對導出，命中率 96%。
LIC_PREFIX = {
    "01": "衛署藥製字", "02": "衛署藥輸字", "09": "衛署菌疫製字", "10": "衛署菌疫輸字",
    "12": "內衛藥製字", "20": "衛署罕藥輸字", "21": "衛署罕藥製字", "22": "衛署罕菌疫輸字",
    "51": "衛部藥製字", "52": "衛部藥輸字", "59": "衛部菌疫製字", "60": "衛部菌疫輸字",
    "70": "衛部罕藥輸字", "71": "衛部罕藥製字", "72": "衛部罕菌疫輸字",
}

_RE_LIC = re.compile(r"^(.+?字)第0*(\d+)號")
_RE_MOJIBAKE = re.compile(r"[?？□�]")


def build_index(path: Path) -> dict[tuple[str, str], dict]:
    """(字別, 流水號) → 許可證資料。同號多筆時保留「有效」那筆。"""
    idx: dict[tuple[str, str], dict] = {}
    for r in json.loads(path.read_text(encoding="utf-8")):
        m = _RE_LIC.match(r.get("許可證字號") or "")
        if not m:
            continue
        key = (m.group(1), m.group(2))
        prev = idx.get(key)
        # 有效證優先於已註銷；同狀態則保留發證較新的
        if prev is None or (prev.get("註銷狀態") and not r.get("註銷狀態")):
            idx[key] = r
    return idx


def lic_id_to_key(lic_id: str) -> tuple[str, str] | None:
    s = (lic_id or "").strip()
    if len(s) < 3 or not s.isdigit():
        return None
    prefix = LIC_PREFIX.get(s[:2])
    return (prefix, str(int(s[2:]))) if prefix else None


def lookup(lic_id: str, idx: dict) -> dict | None:
    key = lic_id_to_key(lic_id)
    return idx.get(key) if key else None


def has_mojibake(s: str) -> bool:
    return bool(_RE_MOJIBAKE.search(s or ""))


def classify(rec: dict | None) -> str:
    """join 結果分級。

    ★ 必須「先 join 再分級」，不可先過濾註銷：許可證移轉／換證時舊證會標已註銷，
      但健保主檔的 licId 可能仍指舊證號。先過濾就會靜默漏掉適應症。
    """
    if rec is None:
        return "miss"
    status = (rec.get("註銷狀態") or "").strip()
    if not status:
        return "active"
    return "stale"          # 已註銷／已廢止，仍保留適應症但標示狀態異常
