"""還原「同一視覺行被拆成多段」的表單欄位。

★ 要解決的問題：
  附表裡的填空欄位在 PDF 上是同一行 ——
      病歷號碼：____ 茲證明本人____ 年齡__ 出生日期__年__月__日
  但底線是用矩形畫的、不是文字，pymupdf 因此把它切成 6 個 line 物件
  （y 相同、x 不同）。page.get_text() 逐個 line 輸出，結果就變成
      茲證明本人 / 年齡 / 出生日期 / 年 / 月 / 日
  一行一個詞的碎片 —— 看起來就像表格跑掉，實際上根本不是表格，
  find_tables 也永遠救不了（那裡沒有格子，只有底線）。

★ 為什麼不直接改 extract_text：
  snapshots/text/*.txt 是 diff_rules.py 逐月比對「官方有沒有偷改條文」的基準。
  動了它，下一次 refresh 會有 500+ 節誤報，把真正的法規變動淹沒。
  所以走 sidecar：原文快照原封不動，只在衍生的 clause 上還原。

★ 無損：
  還原只是把兩段之間的換行換成一個空白，一個字都不增不減。
"""

from __future__ import annotations

import collections
import re
import unicodedata

FORMLINES_VERSION = 1

# 同一視覺行的 y 容差（pt）
_Y_TOL = 1.5
# 一次最多合併幾段（避免把整頁黏成一行）
MAX_PIECES = 12


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", s or ""))


def extract_visual_lines(doc) -> list[str]:
    """回傳「原本同一行卻被拆成多段」的視覺行（已依 x 排序接回）。"""
    out: list[str] = []
    for page in doc:
        rows: dict[float, list[tuple[float, str]]] = collections.defaultdict(list)
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                text = "".join(sp["text"] for sp in line["spans"])
                if not text.strip():
                    continue
                y = line["bbox"][1]
                key = next((k for k in rows if abs(k - y) <= _Y_TOL), y)
                rows[key].append((line["bbox"][0], text.strip()))
        for _y, items in rows.items():
            if 2 <= len(items) <= MAX_PIECES:
                out.append(" ".join(t for _x, t in sorted(items)))
    return out


def rejoin(text: str, index: dict[str, str]) -> str:
    """把 clause 內「原本同一視覺行」的連續短行接回一行。

    只有整段連續行的內容與某條已知視覺行**逐字相同**（忽略空白）時才合併，
    所以不可能把不相干的兩行黏在一起。
    """
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        hit = None
        for j in range(min(i + MAX_PIECES, len(lines)), i + 1, -1):
            key = _norm("".join(lines[i:j]))
            if key and key in index:
                hit = (j, index[key])
                break
        if hit:
            out.append(hit[1])
            i = hit[0]
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out)


def build_index(visual_lines: list[str]) -> dict[str, str]:
    return {_norm(v): v for v in visual_lines if _norm(v)}
