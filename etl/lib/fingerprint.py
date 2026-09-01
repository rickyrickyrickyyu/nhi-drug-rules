"""public/data 的內容指紋 —— 線上版與離線包共用同一個定義。

★ 為什麼不用 meta.json 的 built 日期當版本鍵：
  built 只到「日」。同一天內若重跑 ETL（改了 curation、修了 parser），
  離線包與線上版的資料其實已經不同，但兩邊的 built 相同 → 閘門放行，
  醫師帶去封閉電腦的會是舊條文而不自知。指紋比對才抓得到。

★ 為什麼排除 meta.json 自己：
  指紋要寫回 meta.json，把它算進去會自我指涉（寫入後指紋就變了）。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

EXCLUDE = {"meta.json"}


def data_fingerprint(public: Path) -> str:
    parts = []
    for p in sorted(public.rglob("*.json")):
        rel = p.relative_to(public).as_posix()
        if rel in EXCLUDE:
            continue
        parts.append(f"{rel}:{hashlib.sha256(p.read_bytes()).hexdigest()}")
    return hashlib.sha256("".join(parts).encode()).hexdigest()[:16]


def app_fingerprint(dist: Path) -> str:
    """離線版 app bundle 的指紋（index.html + assets 全部）。

    ★ 為什麼資料指紋不夠：
      前端改版但資料沒變時（例如修了表格渲染、加了仿單劑量面板），
      資料指紋一模一樣，只比資料的閘門會放行一個「畫面還是舊的」離線包。
      使用者拿去封閉電腦，看到的是上一版的介面。
    """
    parts = []
    for p in sorted(dist.rglob("*")):
        if p.is_file():
            parts.append(f"{p.relative_to(dist).as_posix()}:"
                         f"{hashlib.sha256(p.read_bytes()).hexdigest()}")
    return hashlib.sha256("".join(parts).encode()).hexdigest()[:16]
