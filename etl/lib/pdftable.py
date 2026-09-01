"""從健保給付規定 PDF 還原表格。

★ 重要更正：早期版本誤判「pymupdf 的 find_tables() 對這批 PDF 無效」而自建了
  座標重建器。實際上這些 PDF **有繪製框線**（2.6.1. 有 134 條水平線、60 條垂直線），
  find_tables() 依框線切格完全正確，還能自動合併跨多行的儲存格 ——
  那正是自建版本做不好的地方（會把折行的一格拆成多列）。

  自建版本的失敗案例：
    2.6.1. 降血脂表 → 「1.有急性」「冠狀動脈症候」「群病史」被拆成三列
    13.17.2. EASI  → 「涵蓋程」「度」被拆成兩列
  find_tables 兩者都正確合併成一格。

三種 strategy 的結果不同（EASI 用 lines_strict 才會把「涵蓋程/度」併成「涵蓋程度」），
所以三種都跑、評分後取最佳。
"""

from __future__ import annotations

import re
import unicodedata

EXTRACTOR_VERSION = 3

# ★ 刻意不用 "text" strategy：它不看框線、純靠文字位置猜欄位，
#   會把散文切成假表格且切在字中間（實測 8.2.16. 被切出「(2)M」「ethotrexate」）。
#   真正的表格在這批 PDF 裡都有繪製框線，兩種 lines 策略就夠。
_STRATEGIES = ("lines_strict", "lines")
_MIN_COLS = 2
_MAX_COLS = 16
_MIN_ROWS = 2
_MAX_ROWS = 80
_MIN_DENSITY = 0.25
_MAX_CELL_CHARS = 400


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or ""))


_RE_CJK = re.compile(r"[\u3000-\u303f\u3400-\u9fff\uff00-\uffef]")


def _clean(cell) -> str:
    """儲存格文字正規化：把 PDF 的折行接回去。

    ★ 中文折行不可補空白：「涵蓋程\n度」要接成「涵蓋程度」而不是「涵蓋程 度」。
    但英文折行要保留空白（「Region\nscore」→「Region score」），
    否則會黏成 Regionscore。判準：折行兩側只要有一邊是中日韓字元就直接相接。
    """
    # ★ 必須與 parse_rules.normalize_text 用同一種正規化（NFC）：
    #   健保 PDF 含 CJK 相容表意文字（U+F900–FAFF），「度/數」等字看起來一樣但
    #   碼位不同。表格這邊不做 NFC 的話，就無法把表格文字對回條文原文，
    #   結果是「條文照樣逐行印出表格碎片，還原好的表格另外接在後面」——
    #   正是使用者回報的畫面。
    text = unicodedata.normalize("NFC", (cell or "")).strip()
    if not text:
        return ""

    def join(m: re.Match) -> str:
        left, right = m.group(1), m.group(2)
        if _RE_CJK.search(left) or _RE_CJK.search(right):
            return left + right
        return f"{left} {right}"

    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"(\S)\s*\n\s*(\S)", join, text, count=1)
    return re.sub(r"\s*\n\s*", "", text).strip()


def _score(grid: list[list[str]]) -> tuple:
    """表格品質評分，數值越大越好。

    比較同一張表在不同 strategy 下的結果時用。優先扣分項是「整欄全空」與
    「整列全空」—— 那代表 strategy 把框線多切了，例如 EASI 用 default 會切出
    4×10 含兩個空欄，用 lines_strict 則是乾淨的 2×8。
    """
    if not grid:
        return (-1e9,)
    ncol = len(grid[0])
    empty_cols = sum(
        1 for c in range(ncol) if all(not r[c] for r in grid)
    )
    empty_rows = sum(1 for r in grid if not any(r))
    filled = sum(1 for r in grid for c in r if c)
    density = filled / max(len(grid) * ncol, 1)
    return (-empty_cols, -empty_rows, round(density, 3), ncol)


def _validate(grid: list[list[str]], src_text: str) -> bool:
    """fail-closed 驗證。任一不過就不輸出這張表（退回原文＝維持既有行為）。"""
    if not grid or not grid[0]:
        return False
    ncol = len(grid[0])
    if not (_MIN_COLS <= ncol <= _MAX_COLS):
        return False
    if not (_MIN_ROWS <= len(grid) <= _MAX_ROWS):
        return False
    if any(len(r) != ncol for r in grid):
        return False
    filled = sum(1 for r in grid for c in r if c)
    if filled / (len(grid) * ncol) < _MIN_DENSITY:
        return False
    if any(len(c) > _MAX_CELL_CHARS for r in grid for c in r):
        return False
    # 無損：表格內容必須是該頁原文的子集合（不得憑空生出字）
    cells = _norm("".join(c for r in grid for c in r))
    if cells and cells not in _norm(src_text):
        # find_tables 會依閱讀順序重排，逐字比對不一定成立；
        # 退而要求「表格的每個字元都在原文出現過」，仍能擋掉憑空生成
        page_chars = set(_norm(src_text))
        if any(ch not in page_chars for ch in cells):
            return False
    return True


def extract_tables(doc) -> tuple[list[dict], list[dict]]:
    """回傳 (tables, rejected)。tables 已通過驗證，可直接顯示。"""
    tables: list[dict] = []
    rejected: list[dict] = []

    for pno, page in enumerate(doc):
        src = page.get_text()
        best_by_bbox: dict[tuple, tuple] = {}

        for strat in _STRATEGIES:
            try:
                found = page.find_tables(strategy=strat)
            except Exception:                      # noqa: BLE001
                continue
            for t in found.tables:
                try:
                    raw = t.extract()
                except Exception:                  # noqa: BLE001
                    continue
                grid = [[_clean(c) for c in row] for row in raw]
                if not _validate(grid, src):
                    continue
                # 以 bbox 粗略位置當同一張表的識別，跨 strategy 比較品質
                key = tuple(round(v / 10) for v in t.bbox)
                cand = (_score(grid), strat, grid, t.bbox)
                if key not in best_by_bbox or cand[0] > best_by_bbox[key][0]:
                    best_by_bbox[key] = cand

        # ★ 依閱讀順序（先上下、再左右）排序。原本 sorted(dict.items()) 是拿
        #   bbox 元組排 → 等於先比 x0，同一頁上下兩張表會顛倒，
        #   後續「把表格文字對回條文原文」的單向游標就會錯過前一張表。
        for key, (score, strat, grid, bbox) in sorted(
            best_by_bbox.items(), key=lambda kv: (kv[1][3][1], kv[1][3][0])
        ):
            tables.append({
                "page": pno,
                "bbox": [round(v, 1) for v in bbox],
                "strategy": strat,
                "rows": len(grid),
                "cols": len(grid[0]),
                "density": score[2],
                "grid": grid,
                "lossless": True,
            })

        # 記錄「偵測到但沒通過驗證」的，供稽核門檻是否過嚴
        for strat in ("lines_strict",):
            try:
                n_found = len(page.find_tables(strategy=strat).tables)
            except Exception:                      # noqa: BLE001
                n_found = 0
            n_kept = sum(1 for t in tables if t["page"] == pno)
            if n_found > n_kept:
                rejected.append({"page": pno, "found": n_found, "kept": n_kept})

    return tables, rejected
