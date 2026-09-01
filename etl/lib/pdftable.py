"""從健保給付規定 PDF 還原表格。

★ 為什麼不用 pymupdf 的 find_tables()（已實測）：
    - 預設 strategy（依框線）對這批 PDF 回傳 0 個表格 —— 官方表格沒有框線
    - strategy="text" 會把正常散文切成假欄位「而且截斷內容」，比不做更糟

改用 span 座標重建。安全基石是 Step 6 的無損驗證：還原後的所有 cell 串接
必須與原始 span 串接**完全相等**。少一個字或多一個字，整張表就作廢退回純文字
—— 所以最差情況等同今天的行為，不可能比現在更糟。

★ 產物放 data/build/tables/，絕不寫回 snapshots/text/*.txt：
  那份 txt 是 diff_rules.py 逐月比對的基準，動了它會讓 500+ 節誤報 silent_edit，
  把「官方偷改條文」這個最重要的警訊淹沒。
"""

from __future__ import annotations

import re
import statistics
import unicodedata

EXTRACTOR_VERSION = 1

_ROW_TOL = 3.0        # 同列的 y 容差（pt）
_COL_TOL = 6.0        # 同欄的 x 容差（pt）
_MIN_ROWS = 3
_MIN_COLS = 3
_MIN_ALIGN = 0.5      # 欄位對齊度門檻，實測：真表格 0.69–1.00、散文 0.26–0.29
_MAX_COLS = 14
_MAX_ROWS = 60
_MIN_DENSITY = 0.40
_MIN_CORRIDOR = 4.0   # 欄間空白走廊的最小寬度（pt）
_MAX_ROW_CHARS = 22   # 列文字長度中位數上限（實測：表格 ≤8、散文 ≥40）


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or ""))


def page_spans(page) -> list[dict]:
    """用 rawdict 取字元級 bbox。

    ★ 為什麼要字元座標：pymupdf 會把「10-29﹪ 30-49﹪ 50-69﹪ 70-89﹪」四個表格
    儲存格併成一個 span。只有逐字元的 x 座標才能把它切回四格；用「span 寬度
    按比例估算切點」是在猜，猜錯就會產生錯誤的表格 —— 那比不顯示表格更糟。
    """
    out = []
    for blk in page.get_text("rawdict")["blocks"]:
        for line in blk.get("lines", []):
            for sp in line.get("spans", []):
                chars = [c for c in sp.get("chars", []) if c["c"].strip()]
                if not chars:
                    continue
                x0, y0, x1, y1 = sp["bbox"]
                out.append({
                    "x0": x0, "x1": x1, "y0": y0, "y1": y1,
                    "xc": (x0 + x1) / 2, "yc": (y0 + y1) / 2,
                    "text": "".join(c["c"] for c in sp["chars"]).strip(),
                    "chars": [{"c": c["c"], "x0": c["bbox"][0], "x1": c["bbox"][2]}
                              for c in sp["chars"]],
                })
    out.sort(key=lambda s: (s["yc"], s["x0"]))
    return out


def cluster_rows(spans: list[dict]) -> list[list[dict]]:
    rows: list[list[dict]] = []
    for sp in spans:
        if rows and abs(sp["yc"] - rows[-1][-1]["yc"]) < _ROW_TOL:
            rows[-1].append(sp)
        else:
            rows.append([sp])
    for r in rows:
        r.sort(key=lambda s: s["x0"])
    return rows


def _align(a: list[dict], b: list[dict]) -> float:
    """兩列的欄位重合度。

    ★ 比對「儲存格中心」而非左緣：表格的格子多半置中，表頭文字比數值長，
    左緣會差十幾 pt 但中心完全吻合。實測 13.17.2. 的面積表 ——
      表頭「10-29﹪」bbox 228.1–270.1 中心 249.1
      數值「2」      bbox 246.1–252.1 中心 249.1   ← 完全一致
    用左緣比會得到 0.14（誤判為非表格），用中心比得到 1.00。
    """
    xa = sorted({round(s["xc"]) for s in a})
    xb = sorted({round(s["xc"]) for s in b})
    if not xa or not xb:
        return 0.0
    hit = sum(1 for u in xa if any(abs(u - v) <= _COL_TOL * 2 for v in xb))
    return hit / max(len(xa), len(xb))


def find_bands(rows: list[list[dict]]) -> list[tuple[int, int]]:
    """回傳 [(起始列, 結束列)]。

    ★ 不能只找「連續的多欄列」：表頭的格子常常垂直換行成單 span 列，
      把多欄列切斷。13.17.2. 的 EASI 面積表就長這樣 ——
        y141 涵蓋程(1)  y147 0﹪|1-9﹪|10-29﹪…(4)  y153 度(1)
        y177 面積(1)    y183 0|1|2|3|4|5|6(7)      y189 分數(1)
      只看連續多欄列會找到兩段各 1 列，兩段都不足 3 列而被丟掉。

    改為：先用 y 間距把列切成區塊，再要求區塊內「至少 2 列是多欄列」。
    """
    if not rows:
        return []
    gaps = [rows[i + 1][0]["yc"] - rows[i][-1]["yc"] for i in range(len(rows) - 1)]
    median_gap = statistics.median(gaps) if gaps else 12.0
    split_at = max(median_gap * 2.2, 18.0)

    # 分隔點有兩種：y 間距過大，以及「中間的散文行」。
    # 後者很重要：13.17.2. 的面積表與嚴重度表之間夾著「部位：頭部(h)…」與
    # 「異位性皮膚炎嚴重度（Severity）：」兩行說明，不切開的話兩張表會被黏成
    # 一個區塊，欄界完全對不上而整塊被丟掉。
    blocks, start = [], 0
    for i in range(len(rows)):
        cut_after = (
            i + 1 < len(rows)
            and rows[i + 1][0]["yc"] - rows[i][-1]["yc"] > split_at
        )
        if _is_prose_line(rows[i]):
            if i > start:
                blocks.append((start, i))
            start = i + 1
        elif cut_after:
            blocks.append((start, i + 1))
            start = i + 1
    if start < len(rows):
        blocks.append((start, len(rows)))

    ok = []
    for s, e in blocks:
        s, e = _trim(rows, s, e)
        seg = rows[s:e]
        multi = [r for r in seg if len(r) >= _MIN_COLS]
        if len(seg) < _MIN_ROWS or not multi:
            continue

        # ★ 列長度閘：表格的儲存格短，散文的一整列很長。
        # 13.15. Permethrin 是純散文，卻因字型在數字與中文間切換被拆成 8 個 span，
        # 切分後每欄都有東西、對齊度也高 —— 但切點落在字中間（Perme|thrin）。
        # 用「列文字總長度中位數」一刀就分開：
        #   EASI 面積表各列 3/38/1/2/7/2 字 → 中位數 2.5
        #   13.15. 各列 40–50 字            → 中位數 45
        row_lens = sorted(sum(len(sp["text"]) for sp in r) for r in seg)
        if statistics.median(row_lens) > _MAX_ROW_CHARS:
            continue
        if len(multi) >= 2:
            # ★ 對齊度必須「先切分再算」。被 pymupdf 併成一個 span 的多個儲存格
            # （如「10-29﹪ 30-49﹪ 50-69﹪ 70-89﹪」）其中心值落在四格的正中間，
            # 拿它去跟數值列比對必然對不上 —— 實測面積表會得到 0.29 而被誤殺。
            # 改成：先用 anchor 的欄位中心把每列切成「佔用了哪些欄」，再比集合重合度。
            # 對齊度用第一個候選欄位配置算即可（只是要判斷「像不像表格」）
            centers = _col_candidates(seg)[0]
            occ = []
            for r in multi:
                cols = set()
                for sp in r:
                    cols.update(c for c, _t in _split_wide(sp, centers))
                occ.append(cols)
            scores = [
                len(occ[i] & occ[i + 1]) / max(len(occ[i] | occ[i + 1]), 1)
                for i in range(len(occ) - 1)
            ]
            if not scores or statistics.fmean(scores) < _MIN_ALIGN:
                continue
        else:
            # 只有一個多欄列的情形（如 EASI 面積表：表頭與分數列各一，
            # 中間夾著垂直換行的「涵蓋程/度」「面積/分數」）。
            # 沒有第二列可比對齊度，改要求其餘列都是「短的換行格」，
            # 且後面仍有無損與密度驗證把關。
            others = [r for r in seg if len(r) < _MIN_COLS]
            if any(len(r) != 1 or len(r[0]["text"]) > 8 for r in others):
                continue
        ok.append((s, e))
    return ok


def _is_prose_line(row: list[dict]) -> bool:
    """單一 span 且文字偏長 → 是標題或散文，不是表格的換行格。

    表格裡垂直換行的格都很短（「涵蓋程」「度」「面積」「分數」）；
    章節標題與說明句（「異位性皮膚炎面積暨嚴重程度指數」「8歲以上病人：」）明顯長得多。
    """
    return len(row) == 1 and len(row[0]["text"]) > 8


def _trim(rows: list[list[dict]], s: int, e: int) -> tuple[int, int]:
    """修掉區塊頭尾的標題／說明行，避免它們被當成表格的第一列。"""
    while s < e and _is_prose_line(rows[s]):
        s += 1
    while e > s and _is_prose_line(rows[e - 1]):
        e -= 1
    return s, e


def _corridors(seg: list[list[dict]], page_x0: float, page_x1: float) -> list[float] | None:
    """用「垂直空白走廊」找欄界。

    ★ 為什麼不能只用 anchor 列：2.6.1. 降血脂給付規定表的每一格都是多行折行文字，
    沒有任何一列的 span 對應真正的欄位。用 anchor 會把「LDL-C≧70mg/dL」切成
    「並LDL-」「C≧7」「0mg/dL」三格 —— 字元沒少（無損檢查會過）但語意全錯，
    比不還原更糟。

    真表格的欄與欄之間一定有一條「整個表格帶都沒有任何文字」的垂直空白。
    找出這些走廊，取中線當欄界，就不受折行影響。
    """
    step = 1.0
    n = int((page_x1 - page_x0) / step) + 1
    occupied = [False] * n
    for row in seg:
        for sp in row:
            a = max(0, int((sp["x0"] - page_x0) / step))
            b = min(n - 1, int((sp["x1"] - page_x0) / step))
            for i in range(a, b + 1):
                occupied[i] = True

    # 找出寬度足夠的空白走廊（太窄的是字間距，不是欄界）
    gaps, run = [], None
    for i, occ in enumerate(occupied):
        if not occ:
            run = i if run is None else run
        else:
            if run is not None and (i - run) * step >= _MIN_CORRIDOR:
                gaps.append((run, i))
            run = None
    if run is not None and (n - run) * step >= _MIN_CORRIDOR:
        gaps.append((run, n))

    # 去掉左右兩側的頁邊空白
    inner = [g for g in gaps if g[0] > 0 and g[1] < n]
    if len(inner) < _MIN_COLS - 1:
        return None
    return [page_x0 + (a + b) / 2 * step for a, b in inner]


def _cols_from_corridors(seg: list[list[dict]]) -> list[float] | None:
    xs0 = min(sp["x0"] for row in seg for sp in row)
    xs1 = max(sp["x1"] for row in seg for sp in row)
    bounds = _corridors(seg, xs0 - 2, xs1 + 2)
    if not bounds:
        return None
    # 欄界 → 各欄中心
    edges = [xs0 - 2, *bounds, xs1 + 2]
    return [(edges[i] + edges[i + 1]) / 2 for i in range(len(edges) - 1)]


def _col_candidates(seg: list[list[dict]]) -> list[list[float]]:
    """以 span 數最多的那列當 anchor，再補上其他列獨有的欄位。

    13.17.2. 的分數列「0 1 2 3 4 5 6」是 7 個獨立 span，天然就是 anchor；
    表頭那列的「10-29﹪ 30-49﹪…」被併成一個 span，靠 anchor 的中心切開。

    回傳「候選欄位配置」清單，由 build_grid 各建一次 grid 後挑最好的。

    兩種方法各有適用場景，單押一種都會錯：
      走廊法 —— 對 2.6.1. 降血脂表這種「每格都多行折行」的表格才正確；
                 用 anchor 會把 LDL-C≧70mg/dL 切成「並LDL-」「C≧7」「0mg/dL」
      anchor —— 對 13.17.2. EASI 面積表這種「表頭與數值各一列」的緊湊數字表才正確；
                 走廊法會因為數字間空隙太窄而少偵測到欄界，把 0﹪1-9﹪10-29﹪ 併成一格
    """
    out = []
    byc = _cols_from_corridors(seg)
    if byc and _MIN_COLS <= len(byc) <= _MAX_COLS:
        out.append(byc)
    out.append(sorted(s["xc"] for s in max(seg, key=len)))
    return out


def _split_wide(sp: dict, centers: list[float]) -> list[tuple[int, str]]:
    """把橫跨多欄的 span 依「每個字元的實際座標」分配到欄位。

    不做任何比例估算 —— 每個字元都有自己的 bbox，直接算它的中心落在哪一欄。
    這樣切出來的內容是量出來的，不是猜出來的。
    """
    buckets: dict[int, list[str]] = {}
    for ch in sp["chars"]:
        if not ch["c"].strip():
            continue
        cx = (ch["x0"] + ch["x1"]) / 2
        col = min(range(len(centers)), key=lambda i: abs(centers[i] - cx))
        buckets.setdefault(col, []).append(ch["c"])
    return [(col, "".join(cs).strip()) for col, cs in sorted(buckets.items())]


def _bad_splits(seg: list[list[dict]], centers: list[float]) -> int:
    """算「把一個 span 切在字中間」的次數。

    真正的欄界會落在空白處。切點兩側都是英數字（LDL-|C≧7）代表切錯了 ——
    字元沒少所以無損檢查會過，但語意已經壞掉，只能靠這個指標抓。
    """
    bad = 0
    for row in seg:
        for sp in row:
            pieces = _split_wide(sp, centers)
            if len(pieces) < 2:
                continue
            txt = sp["text"]
            pos = 0
            for _c, piece in pieces[:-1]:
                pos = txt.find(piece, pos) + len(piece)
                if 0 < pos < len(txt) and txt[pos - 1].strip() and txt[pos].strip():
                    bad += 1
    return bad


def build_grid(seg: list[list[dict]]) -> dict | None:
    """把一個表格帶還原成 grid。任一驗證失敗回 None（fail-safe 退回純文字）。"""
    best = None
    for cand in _col_candidates(seg):
        g = _build_one(seg, cand)
        if not g:
            continue
        g["bad_splits"] = _bad_splits(seg, cand)
        # 先比「切在字中間的次數」，再比欄數（欄數多代表切得細，前提是沒切壞）
        key = (-g["bad_splits"], g["cols"])
        if best is None or key > best[0]:
            best = (key, g)
    if best is None:
        return None
    # ★ fail-closed：兩種欄位配置都切不乾淨就不輸出表格。
    #   切在字中間（LDL-|C≧7）字元沒少、無損檢查會過，但語意已經壞掉；
    #   顯示一張錯的表比顯示原始文字更危險。退回原文＝維持今天的行為。
    if best[1]["bad_splits"] > 0:
        return None
    return best[1]


def _build_one(seg: list[list[dict]], centers: list[float]) -> dict | None:
    ncol = len(centers)
    if not (_MIN_COLS <= ncol <= _MAX_COLS) or not (2 <= len(seg) <= _MAX_ROWS):
        return None

    grid: list[list[str]] = []
    for row in seg:
        cells = [""] * ncol
        for sp in row:
            for col, piece in _split_wide(sp, centers):
                if 0 <= col < ncol and piece:
                    cells[col] = (cells[col] + piece) if cells[col] else piece
        grid.append(cells)

    # 垂直換行的格合併（「涵蓋程」+「度」→「涵蓋程度」）。
    # ★ 必須看 y 間距：13.17.2. 的面積表裡「度」與「面積」上下相鄰卻分屬
    #   不同邏輯列（「涵蓋程度」是表頭的標籤、「面積分數」是數值列的標籤）。
    #   同一格內換行的間距約等於行高（~12pt），不同標籤之間是 ~25pt。
    line_h = statistics.median(
        [sp["y1"] - sp["y0"] for row in seg for sp in row]) or 12.0
    merged: list[list[str]] = []
    merged_y: list[float] = []
    for cells, row in zip(grid, seg):
        filled = [i for i, c in enumerate(cells) if c]
        y = row[0]["yc"]
        if merged and len(filled) == 1:
            i = filled[0]
            prev_filled = [j for j, c in enumerate(merged[-1]) if c]
            if prev_filled == [i] and (y - merged_y[-1]) <= line_h * 1.4:
                merged[-1][i] += cells[i]
                merged_y[-1] = y
                continue
        merged.append(cells)
        merged_y.append(y)
    grid = merged

    # ★ 無損驗證：還原後字元必須與原文完全相同
    src = _norm("".join(sp["text"] for row in seg for sp in row))
    got = _norm("".join(c for row in grid for c in row))
    if src != got:
        return None

    density = sum(1 for row in grid for c in row if c) / max(len(grid) * ncol, 1)
    if density < _MIN_DENSITY:
        return None

    return {"grid": grid, "cols": ncol, "rows": len(grid),
            "density": round(density, 3), "lossless": True}


def extract_tables(doc) -> tuple[list[dict], list[dict]]:
    """回傳 (tables, rejected)。tables 已通過全部驗證，可直接顯示。"""
    tables, rejected = [], []
    for pno, page in enumerate(doc):
        spans = page_spans(page)
        if not spans:
            continue
        rows = cluster_rows(spans)
        for s, e in find_bands(rows):
            seg = rows[s:e]
            g = build_grid(seg)
            if g:
                tables.append({"page": pno, "y0": round(seg[0][0]["y0"], 1),
                               "y1": round(seg[-1][-1]["y1"], 1), **g})
            else:
                rejected.append({"page": pno, "rows": len(seg),
                                 "reason": "grid_validation_failed"})
    return tables, rejected
