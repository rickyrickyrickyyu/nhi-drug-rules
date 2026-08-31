#!/usr/bin/env python3
"""終端機查詢健保給付規定。

用法：
    python3 cli/query.py <關鍵字> [--full] [--all] [--route PO|TOP|INJ...]

門診當下要的是「給不給付、什麼條件」，開瀏覽器太慢。這支讀的是
public/data/ 的建置產物，跟網頁版同一份資料，不會有兩套事實。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "public" / "data"

# 終端機色碼。輸出被導向檔案時自動關閉，免得管線裡出現亂碼。
_TTY = sys.stdout.isatty()
def _c(code: str) -> str: return code if _TTY else ""
BOLD, DIM, RESET = _c("\033[1m"), _c("\033[2m"), _c("\033[0m")
RED, GRN, YEL, BLU, CYN = (_c(f"\033[3{i}m") for i in (1, 2, 3, 4, 6))

ROUTE_ICON = {"PO": "💊", "INJ": "💉", "TOP": "🧴", "OPH": "👁", "OTIC": "👂",
              "NASAL": "👃", "INH": "🫁", "TD": "🩹", "PR": "💊", "PV": "💊",
              "DIAL": "🧪", "OTHER": "•"}
FLAG_LABEL = [("prior_review", "⚠️  事前審查"), ("consent_form", "📝 需同意書"),
              ("course_limited", "⏱  療程限制"), ("no_combination", "🚫 不得併用"),
              ("special_case", "📄 專案申請")]


def norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "").strip().lower()


def load(name: str):
    p = DATA / name
    if not p.exists():
        sys.exit(f"{RED}找不到 {p}{RESET}\n請先在專案目錄執行 make rebuild")
    return json.loads(p.read_text(encoding="utf-8"))


def score(q: str, it: dict) -> tuple[int, str, str]:
    """回傳 (分數, 命中欄位, 命中字串)。權重與網頁版 src/lib/search.js 一致。"""
    best = (0, "", "")
    def bump(sc, field, matched):
        nonlocal best
        if sc > best[0]:
            best = (sc, field, matched)

    def m(hay, exact, pre, sub):
        h = norm(hay)
        if not h:
            return 0
        return exact if h == q else pre if h.startswith(q) else sub if q in h else 0

    if s := m(it["n"], 100, 95, 50): bump(s, "學名", it["n"])
    for a in it.get("al", []):
        if s := m(a, 100, 90, 48): bump(s, "學名別名", a)
    for z in it.get("z", []):
        if s := m(z, 88, 80, 42): bump(s, "中文俗稱", z)
    origin = {b.split(" ")[0] for r in it.get("r", []) for b in r.get("bp", [])}
    for b in origin:
        if s := m(b, 90, 85, 40): bump(s, "原廠商品名", b)
    for b in it.get("be", []):
        if s := m(b, 80, 75, 40): bump(s, "商品名", b)
    for b in it.get("bz", []):
        if s := m(b, 78, 70, 38): bump(s, "中文商品名", b)
    for sec in it.get("s", []):
        if sec.rstrip(".") == q.rstrip(".") or sec.startswith(q): bump(60, "給付章節", sec)
    for a in it.get("a", []):
        if norm(a).startswith(q): bump(55, "ATC", a)
    if it.get("c"):
        for part in it["k"].split(" + "):
            if s := m(part, 50, 45, 30): bump(s, "複方成分", part)
    return best


def _edit1(a: str, b: str) -> bool:
    """兩字串是否相差至多一次編輯（插入／刪除／替換）。"""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    i = j = edits = 0
    while i < la and j < lb:
        if a[i] == b[j]:
            i, j = i + 1, j + 1
            continue
        edits += 1
        if edits > 1:
            return False
        if la > lb:
            i += 1
        elif la < lb:
            j += 1
        else:
            i, j = i + 1, j + 1
    return edits + (la - i) + (lb - j) <= 1


def wrap(text: str, width: int, indent: str) -> str:
    """中文不能靠空白斷行，逐字累加寬度（全形算 2）。"""
    out, line, w = [], "", 0
    for ch in text:
        cw = 2 if unicodedata.east_asian_width(ch) in "WF" else 1
        if ch == "\n" or w + cw > width:
            out.append(line)
            line, w = "", 0
            if ch == "\n":
                continue
        line += ch
        w += cw
    if line:
        out.append(line)
    return ("\n" + indent).join(out)


def pick_clauses(lines: list[str], inn: str, n: int) -> tuple[list[str], int, bool]:
    """挑出與該學名最相關的段落。

    10.7.1.1. 同時規範 acyclovir、famciclovir、valaciclovir，條文第 1 項整段
    都在講 acyclovir。查 famciclovir 卻先看到 acyclovir 的適應症清單，
    在門診是會誤導的 —— 所以先找提到該學名的那一段，從那裡開始顯示。
    """
    if not lines:
        return [], 0, False
    base = inn.split(" (")[0].lower()

    # ★ 只在「第 1 項一開頭就是別的藥名」時才跳段。
    #   10.7.1.1. 的第 1 項是「1.Acyclovir：…」整段講 acyclovir，
    #   查 famciclovir 的人不該先讀那一段。
    #   但 13.4. 的第 1 項是「1.限皮膚科專科醫師使用。」—— 沒有藥名，
    #   三項全都適用 isotretinoin。之前無條件跳段會略過最關鍵的第 1、2 項。
    lead = re.match(r"^\s*\d+\s*[.、]\s*([A-Za-z][A-Za-z-]{5,})", lines[0])
    if not lead or lead.group(1).lower()[:8] == base[:8]:
        return lines[:n], 0, False

    start = next((i for i, ln in enumerate(lines) if base[:8] in ln.lower()), 0)
    while start > 0 and not re.match(r"^\s*\d+\s*[.、]", lines[start]):
        prev = start - 1
        if re.match(r"^\s*\d+\s*[.、]", lines[prev]):
            start = prev
            break
        start = prev
    return lines[start:start + n], start, start > 0


def show_section(code: str, rules: dict, full: bool, width: int, inn: str = "") -> None:
    sec = rules.get(code)
    if not sec:
        print(f"    {DIM}{code}（條文未載入）{RESET}")
        return
    if sec.get("no_pdf"):
        print(f"    {CYN}{code}{RESET} {DIM}分類節點，條件見子節{RESET}")
        return

    # 生物製劑章節的標題是十幾支藥名加二十幾個修訂日期，完整印出來要七、八行，
    # 會把真正要看的給付條件擠到螢幕外。終端機只留前兩行，--full 才印完整。
    t = sec["title"]
    if not full and len(t) > 110:
        t = t[:110].rstrip() + "…"
    print(f"    {CYN}{BOLD}{code}{RESET} {wrap(t, width - 8, ' ' * 8)}")
    if sec.get("future"):
        print(f"      {YEL}⏳ 本版 {sec['eff']} 起生效，尚未適用{RESET}")

    flags = sec.get("flags") or {}
    badges = [lbl for k, lbl in FLAG_LABEL if flags.get(k)]
    badges += [f"👨‍⚕️ 限{s}專科" for s in flags.get("specialist_only", [])]
    badges += [f"📎 {a}" for a in flags.get("attachments", [])]
    if badges:
        print(f"      {YEL}{'  '.join(badges)}{RESET}")

    if sec.get("stub"):
        msg = ("本節之給付規定即為上方條文全文" if sec.get("title_rule")
               else "本節僅有標題，條件見子節")
        print(f"      {DIM}{msg}{RESET}")
        return

    clauses = sec.get("clauses", [])
    appx = sec.get("appx")
    # 附表是空白表單範本，不列進條文預覽（--full 才顯示）
    if appx is not None and not full:
        clauses = clauses[:appx]
    body = sec.get("text", "") if sec.get("raw") else "\n".join(
        c["text"] for c in clauses)
    lines = [ln for ln in body.splitlines() if ln.strip()]
    if full:
        for ln in lines:
            print(f"      {wrap(ln, width - 8, ' ' * 6)}")
        return
    shown, start, skipped = pick_clauses(lines, inn, 6)
    if skipped:
        print(f"      {DIM}…（跳過前 {start} 行，以下為與 {inn.split(' (')[0].title()} 相關的段落）{RESET}")
    for ln in shown:
        print(f"      {wrap(ln, width - 8, ' ' * 6)}")
    rest = len(lines) - start - len(shown)
    if rest > 0:
        print(f"      {DIM}… 還有 {rest} 行，加 --full 看完整條文{RESET}")
    if appx is not None:
        names = "、".join((sec.get("flags") or {}).get("attachments", [])) or "附表"
        print(f"      {DIM}📎 另附 {names} 表單範本（--full 顯示）{RESET}")


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("query", nargs="*", help="學名／商品名／中文俗稱／章節碼／ATC")
    ap.add_argument("--full", action="store_true", help="顯示完整條文")
    ap.add_argument("--all", action="store_true", help="搜全庫而非皮膚科子集")
    ap.add_argument("--route", help="只看指定劑型 PO/INJ/TOP/OPH…")
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("-h", "--help", action="help")
    args = ap.parse_args()

    if not args.query:
        return 2
    q = norm(" ".join(args.query))
    meta = load("meta.json")
    ing = load("all.json" if args.all else "derm.json")["ing"]

    hits = []
    for it in ing:
        sc, field, matched = score(q, it)
        if sc:
            hits.append((sc, it, field, matched))

    # 零結果才跑模糊比對（1 個字元差），避免每次查詢都做 O(n·m)。
    # 學名很長又難拼，打錯一個字母就查無結果對門診沒幫助。
    if not hits and len(q) >= 5:
        for it in ing:
            for cand in [it["n"], *it.get("al", [])]:
                c = norm(cand)
                if abs(len(c) - len(q)) <= 1 and _edit1(c, q):
                    hits.append((10, it, "學名（近似）", cand))
                    break
    if not hits and not args.all:
        allx = load("all.json")["ing"]
        n = sum(1 for it in allx if score(q, it)[0])
        print(f"{YEL}皮膚科常用清單查無「{' '.join(args.query)}」{RESET}")
        if n:
            print(f"全庫有 {n} 筆，加 {BOLD}--all{RESET} 再搜一次")
        return 1
    if not hits:
        print(f"{YEL}查無「{' '.join(args.query)}」{RESET}")
        return 1

    hits.sort(key=lambda x: (-x[0], x[1]["n"]))
    width = min(96, max(60, __import__("shutil").get_terminal_size((100, 24)).columns))

    for sc, it, field, matched in hits[: args.limit]:
        print()
        print(f"{BOLD}{GRN}{it['n']}{RESET}", end="")
        if it.get("z"):
            print(f"  {it['z'][0]}", end="")
        print()
        meta_line = " · ".join(filter(None, [
            " / ".join(it.get("a", [])[:3]),
            f"{it['np']} 個健保品項",
            "複方" if it.get("c") else "",
        ]))
        print(f"{DIM}{meta_line}{RESET}")
        if field != "學名":
            print(f"{DIM}（透過{field} {matched} 命中）{RESET}")

        rules_cache: dict[str, dict] = {}
        for r in it.get("r", []):
            if args.route and r["ro"] != args.route.upper():
                continue
            brands = "、".join(r.get("bp", [])) or "—"
            price = ""
            if r.get("pr"):
                lo, hi = r["pr"]
                price = f"  {DIM}${lo:,.0f}" + (f"–${hi:,.0f}" if hi != lo else "") + RESET
            print(f"\n  {ROUTE_ICON.get(r['ro'], '•')} {BOLD}{r['l']}{RESET} "
                  f"{r['np']} 項  {brands}{price}")

            derm_secs, other_secs = r.get("sd", []), r.get("so", [])
            if not derm_secs and not other_secs:
                print(f"    {DIM}無個別給付規定章節（仍須符合仿單適應症與給付規定通則）{RESET}")
                mn = it.get("mn") or {}
                codes = [*mn.get("listed", []), *mn.get("referenced", [])][:12]
                if codes:
                    print(f"    {DIM}條文中出現本藥名稱的章節：{' '.join(codes)}{RESET}")
                    print(f"    {DIM}（可能是適用藥品、複方成分或前置治療條件，"
                          f"非健保核定本藥適用該章節，請查閱原文）{RESET}")
                continue
            if not derm_secs and other_secs:
                print(f"    {YEL}本劑型無皮膚科適應症章節；健保給付之其他科別適應症如下{RESET}")

            def render(codes):
                for code in codes:
                    ch = code.split(".")[0]
                    if ch not in rules_cache:
                        try:
                            rules_cache[ch] = {
                                x["code"]: x for x in load(f"rules/ch{ch}.json")["sections"]}
                        except SystemExit:
                            rules_cache[ch] = {}
                    show_section(code, rules_cache[ch], args.full, width, it["k"])

            render(derm_secs)
            if other_secs and derm_secs:
                # 沒有分隔的話，dupilumab 的氣喘條文會跟異位性皮膚炎混在一起
                print(f"    {DIM}── 其他科別的相關規定 ──{RESET}")
            render(other_secs)

    if len(hits) > args.limit:
        print(f"\n{DIM}另有 {len(hits) - args.limit} 筆結果未顯示{RESET}")
    print(f"\n{DIM}資料快照 {meta['built']}｜以健保署最新公告為準{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
