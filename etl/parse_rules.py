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
from lib.formlines import build_index, rejoin  # noqa: E402
from lib.tablesplice import splice_clauses  # noqa: E402
from config import BUILD, MANIFEST, SNAP_TEXT, STAGING  # noqa: E402
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
# ★ 附表名的唯一定義。這裡曾經有兩份：
#   本處的 _RE_ATTACHMENT 不吃「之X」，而下方 build_appendix_registry 用的
#   版本吃 —— 條文寫「◎附表二十二之一」，旗標抽成「附表二十二」，registry 卻以
#   「附表二十二之一」建索引，於是每一筆參照都對不上，附表徽章變成死路。
#   （這是本專案第四次出現「同一規則兩份實作走鐘」，前三次是 JS/Python 搜尋權重、
#     sidecar 欄位清單、pipeline 步驟清單。）
#   只能有一份，兩邊都從這裡取用。
_RE_APPX_NAME = re.compile(
    r"附表[一二三四五六七八九十百零〇\d]+(?:之[一二三四五六七八九十\d]+)?")
# 附表區塊的起始行。實測三種寫法都要吃：
#   「附表十 患者服用Isotretinoin口服製劑同意書」          純標題
#   「◎附表三十二：異位性皮膚炎面積暨嚴重度指數【EASI】(108/12/1)」 有 ◎ 前綴、有括號
#   「附表三十二之一：全民健康保險12歲以上病人…申請表」        有「之N」序號
# 舊版寫成 ^附表…$ 且排除右括號，上面第二三種都比不中 —— 13.17.1. 的
# appendix_from 因此一直是 None。
_RE_APPENDIX_HEAD = re.compile(
    r"^[◎●※★・\s]*附表[一二三四五六七八九十百零〇\d]+"
    r"(?:之[一二三四五六七八九十\d]+)?\s*[：:、【（(\s]"
)
# 條文內文的引用（「詳附表十」「見附表三十二」）不是標題，不可當區塊起點
_RE_APPENDIX_INLINE = re.compile(r"[詳見參照如]\s*附表")


def _negated(text: str, idx: int, kw: str) -> bool:
    window = text[max(0, idx - 6): idx]
    return any(n in window for n in _NEGATIONS)


def extract_flags(text: str) -> tuple[dict, dict]:
    """回傳 (flags, evidence)。

    ★ 旗標一定要留憑據。「事前審查」這種 badge 會直接影響醫師要不要送審查，
    但它是關鍵字掃出來的 —— 沒有憑據就無法讓人自行驗證，也無法在關鍵字表改動時
    抓到殘留的假旗標。evidence 記命中的字串與前後文，UI 點 badge 就地展開。
    """
    flags: dict = {}
    ev: dict = {}
    for name, kws in FLAG_KEYWORDS.items():
        hits = []
        for kw in kws:
            for m in re.finditer(re.escape(kw), text):
                if _negated(text, m.start(), kw):
                    continue
                lo, hi = max(0, m.start() - 22), min(len(text), m.end() + 22)
                hits.append({"kw": kw, "pos": m.start(),
                             "quote": text[lo:hi].replace("\n", " ").strip()})
                break
            if hits:
                break
        flags[name] = bool(hits)
        if hits:
            ev[name] = hits

    spec = sorted(set(_RE_SPECIALIST.findall(text)))
    flags["specialist_only"] = spec
    if spec:
        ev["specialist_only"] = []
        for s_ in spec:
            m = re.search(rf"限{re.escape(s_)}專科醫師", text)
            if m:
                lo, hi = max(0, m.start() - 12), min(len(text), m.end() + 26)
                ev["specialist_only"].append(
                    {"kw": f"限{s_}專科醫師", "pos": m.start(),
                     "quote": text[lo:hi].replace("\n", " ").strip()})

    flags["attachments"] = sorted(set(_RE_APPX_NAME.findall(text)))
    return flags, ev


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
        if _RE_APPENDIX_HEAD.match(ln) and not _RE_APPENDIX_INLINE.search(ln[:6]):
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


def parse_one(code: str, text: str, tables: list[dict] | None = None,
              visual_lines: list[str] | None = None) -> dict:
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
    _flags, _ev = extract_flags(full)
    # ★ 表單填空欄位（「茲證明本人／年齡／出生日期／年／月／日」）在 PDF 上是
    #   同一行，被底線矩形切成多個 line 物件。先接回一行再處理表格。
    if visual_lines:
        idx = build_index(visual_lines)
        for c in clauses:
            c["text"] = rejoin(c["text"], idx)

    # ★ 把表格文字從 clause 裡挖掉、原位換成標記。必須在算 appendix_from 之前做，
    #   因為挖除會刪掉變空的 clause，索引會位移。
    clauses, spliced = splice_clauses(clauses, tables or [])

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
        "tables_spliced": spliced,
        # 附表是要印出來給病人簽的空白表單（同意書欄位、切結書），
        # 不是給付條件。13.4. 的附表十佔了整節一半篇幅，攤開會把
        # 真正要看的三項條件擠到螢幕外。標出起點讓前端預設摺疊。
        "appendix_from": next(
            (i for i, c in enumerate(clauses) if c.get("appendix")), None),
        "coverage": round(coverage, 4),
        # 條號切塊沒涵蓋住原文 → 前端改顯示完整原文。寧可版面難看，
        # 也不能讓醫師看到被截斷的給付條件。
        "render_raw": coverage < 0.95,
        "flags": _flags,
        "flags_ev": _ev,
    }


def load_visual_lines(pdf_filename: str) -> list[dict]:
    p = BUILD / "tables" / f"{Path(pdf_filename).stem}.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("visual_lines", [])


def load_tables(pdf_filename: str) -> list[dict]:
    """讀表格 sidecar（由 etl/build_tables.py 產生，放 data/build/tables/）。"""
    p = BUILD / "tables" / f"{Path(pdf_filename).stem}.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("tables", [])
    except (json.JSONDecodeError, OSError):
        return []


_CN_DIGIT = {c: i for i, c in enumerate("零一二三四五六七八九", 0)}


def appx_sort_key(name: str) -> tuple:
    """附表名的自然排序鍵。

    直接用字串排序會得到「之一、之三、之二、之五、之六、之四」——
    中文數字的碼位順序不是數值順序。醫師掃一眼就覺得亂。
    """
    def cn_int(t: str) -> int:
        if not t:
            return 0
        if t.isdigit():
            return int(t)
        n = tot = 0
        for ch in t:
            if ch == "十":
                n = (n or 1) * 10
                tot, n = tot + n, 0
            elif ch in _CN_DIGIT:
                n = _CN_DIGIT[ch]
        return tot + n

    m = re.match(r"附表([一二三四五六七八九十百零〇\d]+)"
                 r"(?:之([一二三四五六七八九十\d]+)|-([A-Z]))?", name)
    if not m:
        return (999, 999, "", name)
    return (cn_int(m.group(1)), cn_int(m.group(2) or ""), m.group(3) or "", name)


def build_appendix_registry(rules: dict) -> dict[str, str]:
    """{附表名: 內容所在的章節碼}。

    ★ 為什麼需要：13.17.1.（12 歲以上 dupilumab）條文引用「附表三十二 EASI 評分表」，
    但表格本體收在 13.17.2.。醫師在 13.17.1. 頁面完全看不到評分表 —— 而 EASI≧16
    正是申請門檻。這裡建索引讓 UI 能跨節指過去，**不複製內容**（維持單一事實來源）。
    """
    reg: dict[str, dict] = {}

    # ① 章節內本體優先。理由：13.17.2. 的附表三十二現在顯示正常，而章節 PDF 是
    #    snapshots/text/ 的 diff 基準；不動它可避免既有行為被擾動。
    for code, r in rules.items():
        a = r.get("appendix_from")
        if a is None:
            continue
        body = r["clauses"][a:]
        # ★ 「◎附表二十二之一：…」開頭的是**引用行**，不是本體。
        #   本體的標題不帶◎（13.17.2. 的 clause 29 是「附表三十二：異位性…」）。
        #   原本只看總字數 >200，結果 8.2.4.4. 的 219 字純引用行被誤判成本體，
        #   於是那四個附表被登記成「收錄在自己這一節」，畫面上既看不到內容、
        #   也不會跳去官方獨立檔 —— 徽章直接消失。
        real = [c for c in body if not c["text"].lstrip().startswith(("◎", "●", "※", "★"))]
        substantial = sum(len(c["text"]) for c in real) > 200 or bool(r.get("tables"))
        if not substantial:
            continue
        for c in real:
            for name in _RE_APPX_NAME.findall(c["text"][:60]):
                reg.setdefault(name, {"kind": "section", "host": code, "url": None})

    # ② 官方獨立附表檔。8.2.4.x 生物製劑家族的附表本體根本不在章節 PDF 裡，
    #    健保署把它們當獨立檔案發布 —— 沒有這一段，那些附表徽章就是死路。
    appx_dir = BUILD / "appendix"
    if appx_dir.exists():
        for f in sorted(appx_dir.glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            reg.setdefault(d["name"], {"kind": "file", "host": None,
                                       "url": d.get("url"), "title": d.get("title", "")})
    return reg


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
                "flags": extract_flags("")[0], "flags_ev": {}, "revision_dates": [], "text": "",
            }
            continue
        txt_path = SNAP_TEXT / m["pdf_filename"].replace(".pdf", ".txt")
        if not txt_path.exists():
            failed.append(code)
            continue
        tabs = load_tables(m["pdf_filename"])
        vlines = load_visual_lines(m["pdf_filename"])
        r = parse_one(code, txt_path.read_text(encoding="utf-8"), tabs, vlines)
        # 沒有條文的節分兩種，UI 文案完全不同，不能混為一談：
        #   有子節 → 父節指標（8.2.4.6. 乾癬，真正條件在 8.2.4.6.1.）
        #   無子節 → 整條規則就寫在標題行（13.3.3.「與 tazarotene 併用…」）
        #            對後者說「請見子節」是誤導，那是完整規則
        r["has_children"] = any(
            c != code and c.startswith(code) for c in all_codes
        )
        r["title_is_rule"] = r["is_stub"] and not r["has_children"]
        r["tables"] = tabs
        r["effective_date"] = m["effective_date"]
        r["pdf_filename"] = m["pdf_filename"]
        r["is_future"] = m["effective_date"] > TODAY     # 尚未生效，UI 必須標示
        r["first_seen"] = m.get("first_seen")
        rules[code] = r

    # 附表索引：條文引用了哪些附表、本體在哪一節或哪個官方獨立檔
    registry = build_appendix_registry(rules)
    for code, r in rules.items():
        refs = []
        for name in sorted(set(r.get("flags", {}).get("attachments", []))):
            hit = registry.get(name)
            # ★ 條文常寫基底名（「詳見附表二」），官方卻細分成 附表二-A~-D。
            #   找不到精確同名時，收集所有「以它為前綴再接分隔號」的官方附表，
            #   全部列給醫師 —— 那正是條文所指的那一組。
            #   方向不可反：引用「附表十六之二」而官方只有「附表十六」不算命中，
            #   那是不同的文件。
            variants = []
            if hit is None:
                variants = sorted(
                    (n for n in registry
                     if n.startswith(name) and len(n) > len(name)
                     and n[len(name)] in "-之"),
                    key=appx_sort_key,
                )
            refs.append({
                "name": name,
                "kind": (hit or {}).get("kind"),
                "host": (hit or {}).get("host"),
                "url": (hit or {}).get("url"),
                "variants": variants,
                "missing": hit is None and not variants,
                "self": bool(hit) and hit.get("host") == code,
            })
        r["appx_refs"] = refs

    (STAGING / "rules.json").write_text(json.dumps(rules, ensure_ascii=False), encoding="utf-8")

    n_stub = sum(1 for r in rules.values() if r.get("is_stub"))
    n_future = sum(1 for r in rules.values() if r.get("is_future"))
    n_pa = sum(1 for r in rules.values() if r["flags"]["prior_review"])
    n_raw = sum(1 for r in rules.values() if r.get("render_raw"))
    n_tab = sum(len(r.get("tables") or []) for r in rules.values())
    n_missing = sum(1 for r in rules.values() for x in r.get("appx_refs", []) if x["missing"])
    print(f"✅ rules.json {len(rules)} 節｜stub {n_stub}｜未生效 {n_future}｜事前審查 {n_pa}"
          f"｜退回原文顯示 {n_raw}｜表格 {n_tab}｜附表本體缺 {n_missing}｜缺文字 {len(failed)}")
    if failed:
        print(f"❌ 缺少文字檔: {failed[:10]}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
