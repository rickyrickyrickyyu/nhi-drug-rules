"""民國／西元日期轉換。

全案有三種日期格式並存，各自散在不同來源：
  條文內文      115/6/1      （民國，無補零）
  健保 CSV      1150601      （民國，7 碼補零）
  PDF 檔名      20260601     （西元，8 碼）
一律在這裡集中轉成 ISO `YYYY-MM-DD`，禁止在別處自己寫轉換 —
歷史上這種轉換散落各處必然出現某處少加 1911。
"""

from __future__ import annotations

import re

_RE_ROC_SLASH = re.compile(r"^(\d{2,3})/(\d{1,2})/(\d{1,2})$")
_RE_ROC_PACKED = re.compile(r"^(\d{2,3})(\d{2})(\d{2})$")
_RE_AD_PACKED = re.compile(r"^(\d{4})(\d{2})(\d{2})$")

# 民國 999/12/31 是健保資料的「無限期」哨兵值，不是真日期
SENTINEL_FOREVER = "9991231"


def roc_to_iso(value: str | None) -> str | None:
    """吃上述任一格式，回傳 ISO 日期字串；無法解析回 None。

    刻意不丟例外：資料裡真的有空字串與哨兵值，呼叫端要能區分
    「沒有日期」與「日期壞掉」，所以壞掉的一律回 None 並由 gate 統計。
    """
    if not value:
        return None
    s = str(value).strip()
    if not s or s == SENTINEL_FOREVER:
        return None

    m = _RE_ROC_SLASH.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return _fmt(y + 1911, mo, d)

    # 先試西元 8 碼：1150601 是 7 碼民國，20260601 是 8 碼西元，長度可區分
    m = _RE_AD_PACKED.match(s)
    if m and 1900 <= int(m.group(1)) <= 2100:
        return _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = _RE_ROC_PACKED.match(s)
    if m:
        return _fmt(int(m.group(1)) + 1911, int(m.group(2)), int(m.group(3)))

    return None


def _fmt(y: int, mo: int, d: int) -> str | None:
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


_RE_REVISION_BLOCK = re.compile(r"[（(]([\d/、，,\s]+)[）)]")
_RE_REVISION_ONE = re.compile(r"\d{2,3}/\d{1,2}/\d{1,2}")


def parse_revision_dates(text: str) -> list[str]:
    """從條文抽出歷次修訂日期。

    條文首行形如：`13.4.Isotretinoin 口服製劑 (如Roaccutane)：（86/9/1、87/4/1、94/3/1）`
    小項也會夾帶 `(107/12/1、108/3/1)`。全部收集、轉 ISO、去重排序。
    """
    out: set[str] = set()
    for block in _RE_REVISION_BLOCK.findall(text):
        for raw in _RE_REVISION_ONE.findall(block):
            iso = roc_to_iso(raw)
            if iso:
                out.add(iso)
    return sorted(out)
