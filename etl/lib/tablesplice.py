"""把已還原的表格從條文文字中「挖掉」，原位換成標記，讓 UI 就地渲染表格。

★ 要解決的問題：
  表格在 PDF 抽出的純文字裡是逐格換行的碎片（「涵蓋程/度/0﹪/1-9﹪/…」）。
  build_tables.py 已經把表格還原成 grid，但如果條文照樣把碎片印出來，
  畫面就是「一堆看不懂的碎片，後面才接一張正確的表」—— 比只有碎片更糟，
  因為同一份內容出現兩次。

★ 為什麼比對要忽略底線與空白：
  表單的填空在 PDF 文字流裡是「__年__月__日」，但在表格儲存格裡那些底線
  是用框線畫的，抽出來只有「年 月 日」。不忽略就有 8 張表定位失敗。

★ 為什麼要 NFC：
  健保 PDF 有 CJK 相容表意文字（U+F900–FAFF），「度」「數」看起來一樣但碼位
  不同。條文那側 parse_rules 已做 NFC，表格這側若不做就永遠對不上。

★ fail-safe：
  定位不到、或框住的區間夾雜太多非表格文字（可能誤刪散文）→ 整張表放棄挖除，
  退回「條文照舊 + 表格附在後面」，也就是改動前的行為，不會更差。
"""

from __future__ import annotations

import re
import unicodedata

SPLICE_VERSION = 1

# 表格標記：私用區字元，不可能出現在條文原文裡
MARK = "TB{}"
RE_MARK = re.compile(r"TB(\d+)")

# 空白、各種填空底線與間隔點：比對時一律忽略
_RE_SKIP = re.compile(r"[\s_＿﹏‥…．·・]+")

# 單格之間允許夾雜的字數（PDF 文字流會插入頁眉頁碼）
_WINDOW = 400
# 候選起點掃描上限（首格文字若很常見，全掃會拖慢）
_MAX_CANDIDATES = 60
# 允許對不上的儲存格比例（find_tables 併格造成的順序差異）
_MAX_SKIP_RATIO = 0.10


def _norm(s: str) -> str:
    return _RE_SKIP.sub("", unicodedata.normalize("NFC", s or ""))


def _cells(grid: list[list[str]]) -> list[str]:
    out = [_norm(c) for row in grid for c in row]
    return [c for c in out if c]


def _foreign_runs(cells: list[str], hay: str, lo: int, hi: int) -> list[str]:
    """區間內「扣掉所有儲存格出現處」之後剩下的文字片段。

    刻意不依順序扣：PDF 文字流對多欄表單常常不照 grid 的列序吐字，
    依順序扣會把已經是表格內容的字誤判成散文。
    """
    seg = hay[lo:hi]
    marks = [False] * len(seg)
    for c in sorted(set(cells), key=len, reverse=True):
        i = seg.find(c)
        while i >= 0:
            for k in range(i, i + len(c)):
                marks[k] = True
            i = seg.find(c, i + 1)
    runs, cur = [], ""
    for ch, m in zip(seg, marks):
        if m:
            if cur:
                runs.append(cur)
                cur = ""
        else:
            cur += ch
    if cur:
        runs.append(cur)
    return runs


def _find_span(cells: list[str], hay: str, start: int,
               max_skip: int = 0) -> tuple[int, int, int] | None:
    """依序找出每個儲存格，回傳 (起, 迄, 夾雜字數)。

    ★ 取「夾雜最少」的候選起點，不是第一個成功的：
      13.17.2. 的嚴重度表首格是「嚴重度」，而它前面的標題句
      「異位性皮膚炎嚴重度（Severity）：」也含這三個字。從標題那裡起算同樣
      能依序找完所有格，但會把標題一起吃掉 —— 挑夾雜最少的才會落在真正的表頭。
    """
    best = None
    pos = start
    for _ in range(_MAX_CANDIDATES):
        p = hay.find(cells[0], pos)
        if p < 0:
            break
        lo = cur = p
        covered = 0
        skipped = 0
        ok = True
        for c in cells:
            j = hay.find(c, cur)
            if j < 0 or j - cur > _WINDOW:
                # ★ find_tables 有時會把跨欄內容併成一格，那個字串在 PDF 的
                #   線性文字裡並不存在（順序不同）。整張表因為一格對不上就
                #   放棄太可惜 —— 允許跳過少數格子，安全性仍由下方
                #   「夾雜必須是表格內容」把關，與有沒有跳過無關。
                skipped += 1
                if skipped > max_skip:
                    ok = False
                    break
                continue
            covered += len(c)
            cur = j + len(c)
        if ok:
            foreign = cur - lo - covered
            if best is None or foreign < best[2]:
                best = (lo, cur, foreign)
            if foreign == 0:
                break
        pos = p + 1
    return best


def locate_tables(tables: list[dict], text: str) -> list[dict]:
    """在 text 中定位每張表，回傳 [{i, lo, hi}]（皆為 _norm 後的位移）。"""
    hay = _norm(text)
    spans: list[dict] = []
    for i, t in enumerate(tables):
        cells = _cells(t.get("grid") or [])
        if not cells:
            continue
        start = spans[-1]["hi"] if spans else 0
        # 先從上一張表之後找；找不到再從頭找一次（同頁多表時 PDF 文字流
        # 未必照版面順序，單向游標會錯過）。
        # ★ 嚴格版（不跳格）優先：它挑得到正確的錨點。容錯版是備援，
        #   若一開始就容錯，13.17.2. 的嚴重度表會錨在標題句而吃掉
        #   「（Severity）：」。
        skip = max(1, int(len(cells) * _MAX_SKIP_RATIO))
        r = (_find_span(cells, hay, start)
             or _find_span(cells, hay, 0)
             or _find_span(cells, hay, start, skip)
             or _find_span(cells, hay, 0, skip))
        if not r:
            continue
        lo, hi, foreign = r
        if spans and lo < spans[-1]["hi"]:
            continue                       # 與前一張重疊，放棄
        if foreign:
            # ★ 只有「夾雜的字本身就是表格內容的一部分」才准挖除。
            #   實測 5.4.1.1. 夾著 '床特徵' 與 '良' —— 那是 PDF 文字層把
            #   '臨床特徵'、'循環不良' 重複吐了一次的碎片，刪掉不損失任何資訊，
            #   因為同樣的字就在下方表格裡。
            #   反之，只要出現一個表格裡沒有的字（真正的散文），整張放棄挖除，
            #   退回「碎片 + 表格附在後面」—— 條文忠實度不能讓步。
            flat = "".join(cells)
            if any(run not in flat for run in _foreign_runs(cells, hay, lo, hi)):
                continue
        spans.append({"i": i, "lo": lo, "hi": hi})
    return spans


def splice_clauses(clauses: list[dict], tables: list[dict]) -> tuple[list[dict], int]:
    """把表格文字從 clauses 挖掉並插入標記。回傳 (新 clauses, 成功挖除數)。"""
    if not tables or not clauses:
        return clauses, 0

    # 位移對照：_norm 後的每個字元 → (clause index, 該 clause 內原始位移)
    amap: list[tuple[int, int]] = []
    parts = []
    for ci, c in enumerate(clauses):
        raw = unicodedata.normalize("NFC", c["text"] or "")
        for oi, ch in enumerate(raw):
            if _RE_SKIP.match(ch):
                continue
            amap.append((ci, oi))
            parts.append(ch)
    hay = "".join(parts)

    spans = locate_tables(tables, hay)
    if not spans:
        return clauses, 0

    # 由後往前切，避免位移失效
    out = [dict(c) for c in clauses]
    done = 0
    for sp in sorted(spans, key=lambda s: s["lo"], reverse=True):
        if sp["hi"] > len(amap) or sp["lo"] >= sp["hi"]:
            continue
        c0, o0 = amap[sp["lo"]]
        c1, o1 = amap[sp["hi"] - 1]
        mark = MARK.format(sp["i"])
        if c0 == c1:
            t = out[c0]["text"]
            out[c0]["text"] = t[:o0] + mark + t[o1 + 1:]
        else:
            out[c0]["text"] = out[c0]["text"][:o0] + mark
            for ci in range(c0 + 1, c1):
                out[ci]["text"] = ""
            out[c1]["text"] = out[c1]["text"][o1 + 1:]
        done += 1

    # 挖成空的 clause 直接移除（留著會在畫面上變成空行）
    out = [c for c in out if c["text"].strip()]
    return out, done
