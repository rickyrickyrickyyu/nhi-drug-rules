#!/usr/bin/env python3
"""章節 PDF 純文字 → 結構化條文（標題、沿革日期、條號階層、給付條件旗標）。

用法：
    python3 etl/parse_rules.py

輸出 data/build/.staging/rules.json：{章節碼: {...}}
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import MANIFEST, SNAP_TEXT, STAGING  # noqa: E402
from lib.roc import parse_revision_dates, roc_to_iso  # noqa: E402
from lib.section import chapter_no, code_tuple, parent_code, same_code, slug  # noqa: E402

TODAY = date.today().isoformat()

# 條號：一、 （一） 1. (1) I. A. 都要辨識，決定縮排層級
_LEVEL_PATTERNS = [
    (1, re.compile(r"^\s*([一二三四五六七八九十]+)、")),
    (2, re.compile(r"^\s*[（(]([一二三四五六七八九十]+)[）)]")),
    (1, re.compile(r"^\s*(\d+)\.")),
    (2, re.compile(r"^\s*[（(](\d+)[）)]")),
    (3, re.compile(r"^\s*([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩI]+)[.、]")),
    (4, re.compile(r"^\s*([A-Z])[.、]")),
]

# 否定詞出現在關鍵字前後 6 字內就不算命中 —— 「無需事前審查」不能標成需要
_NEGATIONS = ("不需", "無需", "無須", "毋須", "免經", "免予", "不必", "非經")

FLAG_KEYWORDS = {
    "prior_review": ("事前審查",),
    "special_case": ("專案申請", "專案審查"),
    "consent_form": ("同意書",),
    "course_limited": ("療程",),
    "no_combination": ("不得併用", "不得合併使用", "擇一使用", "擇一"),
    "annual_limit": ("每年", "半年內"),
}
_RE_SPECIALIST = re.compile(r"限([一-鿿]{2,6}?)專科醫師")
_RE_ATTACHMENT = re.compile(r"附表[一二三四五六七八九十百\d]+")


def _negated(text: str, idx: int, kw: str) -> bool:
    window = text[max(0, idx - 6): idx]
    return any(n in window for n in _NEGATIONS)


def extract_flags(text: str) -> dict:
    flags: dict = {}
    for name, kws in FLAG_KEYWORDS.items():
        hit = False
        for kw in kws:
            for m in re.finditer(re.escape(kw), text):
                if not _negated(text, m.start(), kw):
                    hit = True
                    break
            if hit:
                break
        flags[name] = hit
    flags["specialist_only"] = sorted(set(_RE_SPECIALIST.findall(text)))
    flags["attachments"] = sorted(set(_RE_ATTACHMENT.findall(text)))
    return flags


def split_clauses(body: str) -> list[dict]:
    """把條文切成帶層級的區塊。純視覺結構化，原文一字不改。"""
    clauses: list[dict] = []
    buf: list[str] = []
    cur = {"marker": "", "level": 0}

    def flush() -> None:
        txt = "\n".join(buf).strip()
        if txt:
            clauses.append({**cur, "text": txt, "dates": parse_revision_dates(txt)})

    for line in body.splitlines():
        if not line.strip():
            continue
        matched = None
        for level, pat in _LEVEL_PATTERNS:
            m = pat.match(line)
            if m:
                matched = (level, m.group(1))
                break
        if matched:
            flush()
            buf = [line.strip()]
            cur = {"marker": matched[1], "level": matched[0]}
        else:
            buf.append(line.strip())
    flush()
    return clauses


def parse_one(code: str, text: str) -> dict:
    lines = [ln.rstrip() for ln in text.splitlines()]
    title = ""
    title_idx = -1
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s:
            continue
        # 首行形如 `13.4.Isotretinoin…`，但實測 13.3.3 寫成 `13.3.3 與tazarotene…`（碼後無點）。
        # ★ 這裡必須貪婪比對：非貪婪的 [\d.]+? 對 "10.7.1.1.全身性…" 只會吃到 "1"，
        #   same_code 比不中就整節退回 fallback，標題會連號碼一起帶進去。
        m = re.match(r"^([\d]+(?:\.[\d]+)*)\.?\s*(.*)$", s)
        if m and same_code(m.group(1), code):
            title, title_idx = m.group(2).strip(), i
            break
    if title_idx < 0:
        # 子節 PDF 會先印父節標題行，找不到自己的碼時退回第一行非空
        for i, ln in enumerate(lines):
            if ln.strip():
                title, title_idx = ln.strip(), i
                break

    # 標題常常換行（13.17. 的藥名清單橫跨三行）。往下併行，直到出現編號條文為止，
    # 否則被截斷的標題尾巴會被當成條文內容，stub 判定也會跟著錯。
    end = title_idx + 1
    while end < len(lines):
        ln = lines[end].strip()
        if not ln:
            end += 1
            continue
        if any(pat.match(ln) for _, pat in _LEVEL_PATTERNS):
            break
        if title.count("（") <= title.count("）") and title.count("(") <= title.count(")"):
            break
        title = f"{title}{ln}"
        end += 1
    body = "\n".join(lines[end:]) if title_idx >= 0 else text
    clauses = split_clauses(body)
    full = text.strip()
    return {
        "code": code,
        "slug": slug(code),
        "parent": parent_code(code),
        "chapter": chapter_no(code),
        "sort_key": list(code_tuple(code)),
        "title": re.sub(r"[：:]\s*[（(][\d/、，,\s]+[）)]\s*$", "", title).strip(),
        "title_raw": title,
        "revision_dates": parse_revision_dates(title) or parse_revision_dates(full),
        "text": full,
        "char_count": len(full),
        # 父節常只有標題（13.17. 的條件其實在 13.17.1./13.17.2.）。
        # 判準是「標題之外還有沒有內容」：不能只看有無編號條文 —— 13.7. Doxepin cream
        # 的全部條文就是一句沒有編號的「限成人使用，每次處方不超過七天。」，那不是 stub。
        "is_stub": sum(len(c["text"]) for c in clauses) < 10,
        "clauses": clauses,
        "flags": extract_flags(full),
    }


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rules: dict[str, dict] = {}
    failed: list[str] = []

    for code, m in manifest.items():
        if m.get("no_pdf"):
            rules[code] = {
                "code": code, "slug": slug(code), "parent": parent_code(code),
                "chapter": chapter_no(code), "sort_key": list(code_tuple(code)),
                "title": "", "no_pdf": True, "is_stub": True, "clauses": [],
                "flags": extract_flags(""), "revision_dates": [], "text": "",
            }
            continue
        txt_path = SNAP_TEXT / m["pdf_filename"].replace(".pdf", ".txt")
        if not txt_path.exists():
            failed.append(code)
            continue
        r = parse_one(code, txt_path.read_text(encoding="utf-8"))
        r["effective_date"] = m["effective_date"]
        r["pdf_filename"] = m["pdf_filename"]
        r["is_future"] = m["effective_date"] > TODAY     # 尚未生效，UI 必須標示
        r["first_seen"] = m.get("first_seen")
        rules[code] = r

    (STAGING / "rules.json").write_text(json.dumps(rules, ensure_ascii=False), encoding="utf-8")

    n_stub = sum(1 for r in rules.values() if r.get("is_stub"))
    n_future = sum(1 for r in rules.values() if r.get("is_future"))
    n_pa = sum(1 for r in rules.values() if r["flags"]["prior_review"])
    print(f"✅ rules.json {len(rules)} 節｜stub {n_stub}｜未生效 {n_future}｜事前審查 {n_pa}｜缺文字 {len(failed)}")
    if failed:
        print(f"❌ 缺少文字檔: {failed[:10]}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
