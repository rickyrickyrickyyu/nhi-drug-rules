#!/usr/bin/env python3
"""章節 PDF 純文字 → 結構化條文（標題、沿革日期、條號階層、給付條件旗標）。

用法：
    python3 etl/parse_rules.py

輸出 data/build/.staging/rules.json：{章節碼: {...}}
"""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
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
# 修訂日期區塊：（86/9/1、87/4/1）—— 至少兩個數字加斜線才算，避免誤中劑量括號
_RE_DATE_BLOCK = re.compile(r"[（(]\s*\d{2,3}/\d{1,2}/\d{1,2}[^）)]*[）)]")

_RE_SPECIALIST = re.compile(r"限([一-鿿]{2,6}?)專科醫師")
_RE_ATTACHMENT = re.compile(r"附表[一二三四五六七八九十百\d]+")
# 附表區塊的起始行：「附表十 患者服用Isotretinoin口服製劑同意書」
_RE_APPENDIX_HEAD = re.compile(r"^附表[一二三四五六七八九十百\d]+\s*[^）)]{0,40}$")


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
        ln = line.strip()
        if not ln:
            continue
        # 附表標題行是硬邊界。它不以編號開頭，會被當成上一條的續行吞掉，
        # 之後整份空白同意書（病歷號碼／年齡／出生日期…）就混進給付條件裡。
        if _RE_APPENDIX_HEAD.match(ln):
            flush()
            buf = [ln]
            cur = {"marker": "", "level": 0, "appendix": True}
            continue
        matched = None
        for level, pat in _LEVEL_PATTERNS:
            m = pat.match(line)
            if m:
                matched = (level, m.group(1))
                break
        if matched:
            was_appendix = cur.get("appendix", False)
            flush()
            buf = [ln]
            # 附表內部的編號（同意書自己的 1.2.3.）仍屬附表
            cur = {"marker": matched[1], "level": matched[0], "appendix": was_appendix}
        else:
            buf.append(ln)
    flush()
    return clauses


def clause_coverage(src: str, title: str, clauses: list[dict]) -> float:
    """條文切塊涵蓋了原文多少比例。

    有些章節的 PDF 是「藥品給付規定修訂對照表」的雙欄版型（修訂後／原給付規定
    並排），條號偵測會漏掉大半內容。醫師看到被截斷的給付條件比看不到更危險，
    所以覆蓋率不足時要退回顯示完整原文。
    """
    def norm(x: str) -> str:
        # 章節碼前綴只出現在原文，比對前先拿掉，否則短章節會被誤判成大量掉字
        x = re.sub(r"\s+", "", unicodedata.normalize("NFKC", x or ""))
        return re.sub(r"\d+(?:\.\d+)*\.?(?=[^\d])", "", x)

    a = norm(src)
    b = norm(title + "".join(c["text"] for c in clauses))
    if not a:
        return 1.0
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return sum(blk.size for blk in sm.get_matching_blocks()) / len(a)


def normalize_text(text: str) -> str:
    """把 CJK 相容表意文字正規化回一般表意文字。

    ★ 健保 PDF 裡有 70 種相容表意文字散落在 86 個章節（U+F9C1「療」出現 416 次、
      U+F967「不」129 次、U+F962「異」51 次…）。它們長得跟一般字完全一樣，但碼位不同，
      導致關鍵字比對整批失效 —— 例如「療程」會比不中，該標「療程限制」的章節漏標。

    刻意用 NFC 而非 NFKC：NFC 會把相容表意文字轉回正規碼位，但不會動全形數字
    （「５０毫克」保持原樣）。條文原文的忠實度要顧，snapshots/text/ 的 .txt
    仍保存 PDF 抽出的原始位元組，這裡只在解析階段正規化。
    """
    return unicodedata.normalize("NFC", text or "")


def parse_one(code: str, text: str) -> dict:
    text = normalize_text(text)
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

    # 標題常常換行 —— 生物製劑章節的藥名清單可以橫跨七、八行
    # （8.2.4.4. 列了 adalimumab…bimekizumab 十幾支藥）。
    #
    # 終止判準用「修訂日期區塊」而非括號配對：藥名本身就帶括號（如Humira），
    # 括號配對在第一行就平衡了，會把標題切在半路，剩下的藥名被當成條文內容。
    # 真正的標題結尾是 `（98/8/1、…、114/2/1）：用於…治療部分` 這個日期區塊。
    # 兩個終止條件，缺一不可：
    #   a) 出現編號條文 → 硬停（8.2.4.4. 的標題後面接「1.限內科專科醫師…」）
    #   b) 日期區塊已出現「且括號都閉合」→ 停
    #      只看日期區塊會太早停：13.17.1. 的日期後面還接「(12歲/以上病人治療部分)」
    #      跨兩行；只看括號配對也不行：藥名自帶括號（如Humira）第一行就平衡了。
    def _balanced(x: str) -> bool:
        return x.count("（") <= x.count("）") and x.count("(") <= x.count(")")

    def _title_complete(t: str) -> bool:
        """標題看起來收尾了沒。

        這一節的標題幾乎都以「…治療部分」或日期區塊的右括號結束。
        用結尾符判斷比用長度或括號配對穩：
          8.2.4.5. 原文斷在「…：用於活 / 動性乾癬性關節炎－乾癬性脊椎病變治療部分」
          8.2.4.6.1. 斷在「…：用於乾 / 癬治療部分」
        兩者的第一行括號都已閉合，只看括號會把標題切在詞中間。
        """
        return t.rstrip().endswith(("部分", "。", "）", ")", "："))

    end = title_idx + 1
    while end < len(lines) and end - title_idx <= 12:
        if _RE_DATE_BLOCK.search(title) and _balanced(title) and _title_complete(title):
            break
        ln = lines[end].strip()
        if not ln:
            end += 1
            continue
        if any(pat.match(ln) for _, pat in _LEVEL_PATTERNS):
            break
        title = f"{title}{ln}"
        end += 1

    body = "\n".join(lines[end:]) if title_idx >= 0 else text
    clauses = split_clauses(body)
    full = text.strip()
    coverage = clause_coverage(full, title, clauses)
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
        # 附表是要印出來給病人簽的空白表單（同意書欄位、切結書），
        # 不是給付條件。13.4. 的附表十佔了整節一半篇幅，攤開會把
        # 真正要看的三項條件擠到螢幕外。標出起點讓前端預設摺疊。
        "appendix_from": next(
            (i for i, c in enumerate(clauses) if c.get("appendix")), None),
        "coverage": round(coverage, 4),
        # 條號切塊沒涵蓋住原文 → 前端改顯示完整原文。寧可版面難看，
        # 也不能讓醫師看到被截斷的給付條件。
        "render_raw": coverage < 0.95,
        "flags": extract_flags(full),
    }


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    all_codes = set(manifest)
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
        # 沒有條文的節分兩種，UI 文案完全不同，不能混為一談：
        #   有子節 → 父節指標（8.2.4.6. 乾癬，真正條件在 8.2.4.6.1.）
        #   無子節 → 整條規則就寫在標題行（13.3.3.「與 tazarotene 併用…」）
        #            對後者說「請見子節」是誤導，那是完整規則
        r["has_children"] = any(
            c != code and c.startswith(code) for c in all_codes
        )
        r["title_is_rule"] = r["is_stub"] and not r["has_children"]
        r["effective_date"] = m["effective_date"]
        r["pdf_filename"] = m["pdf_filename"]
        r["is_future"] = m["effective_date"] > TODAY     # 尚未生效，UI 必須標示
        r["first_seen"] = m.get("first_seen")
        rules[code] = r

    (STAGING / "rules.json").write_text(json.dumps(rules, ensure_ascii=False), encoding="utf-8")

    n_stub = sum(1 for r in rules.values() if r.get("is_stub"))
    n_future = sum(1 for r in rules.values() if r.get("is_future"))
    n_pa = sum(1 for r in rules.values() if r["flags"]["prior_review"])
    n_raw = sum(1 for r in rules.values() if r.get("render_raw"))
    print(f"✅ rules.json {len(rules)} 節｜stub {n_stub}｜未生效 {n_future}｜事前審查 {n_pa}"
          f"｜退回原文顯示 {n_raw}｜缺文字 {len(failed)}")
    if failed:
        print(f"❌ 缺少文字檔: {failed[:10]}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
