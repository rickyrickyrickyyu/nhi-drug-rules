"""資料溯源（provenance）登錄簿。

臨床工具必須能回答「這個數字哪來的」。本模組提供**封閉列舉**的來源類型，
任何欄位若無法對應到其中之一，validate 會擋下來 —— 這是「零幻覺」的機制保證，
而不是靠寫程式的人自律。

設計取捨：不把來源塞進每個欄位物件（derm.json 會膨脹數倍、撐爆首載預算），
改用「旁路登錄簿 + 差異式標記」：
  - sources.json 記每個來源的 URL/sha256/取得時間（全站共用，約 5–8 KB）
  - slim item 只記「與預設來源不同」的欄位（多數欄位都來自健保 CSV）
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

# ★ 封閉列舉。新增來源必須同時改這裡與 validate 的白名單 gate，
#   刻意讓「偷偷加一個沒人知道的資料來源」變成不可能。
SOURCE_KINDS = frozenset({"http", "pdf", "curation", "code", "derived"})

# 來源 id 前綴 → 人類可讀說明（UI 用）
SOURCE_LABEL = {
    "nhi_csv": "健保署藥品品項主檔",
    "nhi_proc_csv": "健保署醫療服務給付項目及支付標準",
    "nhi_proc_api": "健保署支付標準查詢（章節定位）",
    "tfda_json": "食藥署藥品許可證資料",
    "pdf:": "健保署給付規定條文 PDF",
    "cur:": "本專案人工策展",
    "code:": "本專案程式推導",
    "drv:": "本專案程式推導",
}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class Registry:
    """來源登錄簿。ETL 各階段呼叫 register()，最後 dump 成 sources.json。"""

    def __init__(self, path: Path):
        self.path = path
        self.sources: dict[str, dict] = {}
        if path.exists():
            try:
                self.sources = json.loads(path.read_text(encoding="utf-8")).get("sources", {})
            except (json.JSONDecodeError, OSError):
                self.sources = {}

    def register(self, sid: str, kind: str, **meta) -> str:
        if kind not in SOURCE_KINDS:
            raise ValueError(f"未知的來源類型 {kind!r}，允許值：{sorted(SOURCE_KINDS)}")
        self.sources[sid] = {"kind": kind, **meta}
        return sid

    def register_http(self, sid: str, url: str, local: Path, **meta) -> str:
        """下載來的檔案：記 URL、取得時間、sha256、大小。

        沒有這三樣就無法回答「這份資料是什麼時候抓的、有沒有被中途換過」。
        """
        return self.register(
            sid, "http", url=url, fetched_at=now_iso(),
            sha256=sha256_file(local), bytes=local.stat().st_size, **meta)

    def register_curation(self, path: Path) -> str:
        sid = f"cur:{path.stem}"
        return self.register(sid, "curation", path=str(path.relative_to(path.parents[1])),
                             sha256=sha256_file(path))

    def register_code(self, path: Path, **meta) -> str:
        sid = f"code:{path.stem}"
        return self.register(sid, "code", path=path.name, sha256=sha256_file(path), **meta)

    def dump(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(
            {"schema": 1, "generated_at": now_iso(), "sources": self.sources},
            ensure_ascii=False, indent=1), encoding="utf-8")


def sid_for_pdf(section_code: str) -> str:
    return f"pdf:{section_code}"


def label_for(sid: str) -> str:
    if sid in SOURCE_LABEL:
        return SOURCE_LABEL[sid]
    for pre, lab in SOURCE_LABEL.items():
        if pre.endswith(":") and sid.startswith(pre):
            return lab
    return sid
