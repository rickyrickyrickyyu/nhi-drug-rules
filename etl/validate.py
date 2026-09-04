#!/usr/bin/env python3
"""fail-closed 驗證閘門。全部跑完再一次報告，然後才決定要不要 promote。

用法：
    python3 etl/validate.py [--override 6,10]

刻意不「第一個失敗就 exit」——每月只跑一次，要一次看完全部問題。
warn 級一律實作成 fail，人工看過後用 --override 放行；在 CI 裡只印
warning 而讓 commit 照跑，等於沒有閘門。
"""

from __future__ import annotations

import argparse
import collections
import csv
import gzip
import re
import unicodedata
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.tablesplice import RE_MARK as RE_TBMARK  # noqa: E402
from config import (APPX_MANIFEST, CSV_COLUMNS, CURATION, MANIFEST, PUBLIC, RAW,  # noqa: E402
                    ROOT, SNAPSHOTS, SNAP_APPX, STAGING)
from lib.section import match_prefix  # noqa: E402

PREV = SNAPSHOTS / "last_run.json"


@dataclass
class Gate:
    id: int
    name: str
    passed: bool
    message: str


def run() -> list[Gate]:
    g: list[Gate] = []
    prev = json.loads(PREV.read_text(encoding="utf-8")) if PREV.exists() else {}
    rep = json.loads((STAGING / "normalize_report.json").read_text(encoding="utf-8"))
    products = json.loads((STAGING / "products.json").read_text(encoding="utf-8"))
    ings = json.loads((STAGING / "ingredients.json").read_text(encoding="utf-8"))
    rules = json.loads((STAGING / "rules.json").read_text(encoding="utf-8"))
    tags = yaml.safe_load((CURATION / "derm_tags.yaml").read_text(encoding="utf-8"))

    # 1 品項數健檢
    p0 = prev.get("n_products")
    ok = p0 is None or 0.90 * p0 <= len(products) <= 1.10 * p0
    g.append(Gate(1, "品項數健檢", ok, f"{len(products):,}（上期 {p0}）"))

    # 2 欄位契約
    import csv
    csv.field_size_limit(1 << 24)
    with (RAW / "nhi_drug.csv").open(encoding="utf-8-sig", newline="") as f:
        cols = next(csv.reader(f))
    cols = [c.lstrip("﻿") for c in cols]
    g.append(Gate(2, "CSV 欄位契約", cols == CSV_COLUMNS, f"{len(cols)} 欄"))

    # 3 章節解析率
    g.append(Gate(3, "章節解析數", len(rules) >= 500, f"{len(rules)} 節"))

    # 4/5 PDF 下載與抽字
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    no_text = [c for c, m in man.items() if not m.get("no_pdf") and not m.get("char_count")]
    g.append(Gate(4, "PDF 下載", not no_text, f"缺文字 {len(no_text)} 節 {no_text[:5]}"))
    bad_head = []
    for c, r in rules.items():
        if r.get("no_pdf") or not r.get("text"):
            continue
        if not r["title_raw"] and r["char_count"] < 20:
            bad_head.append(c)
    g.append(Gate(5, "PDF 抽字/首行", not bad_head, f"異常 {len(bad_head)} 節 {bad_head[:5]}"))

    # 7 INN 覆蓋
    rate = rep["n_inn_unresolved"] / max(rep["n_products"], 1)
    g.append(Gate(7, "INN 覆蓋", rate <= 0.02, f"未解析 {rate:.3%}"))

    # 8 Route 覆蓋（皮膚科子集）
    derm_codes = {c for i in ings.values() if i["derm"] for r in i["routes"].values() for c in r["products"]}
    other = sum(1 for c in derm_codes if products[c]["route"] == "OTHER")
    r8 = other / max(len(derm_codes), 1)
    g.append(Gate(8, "Route 覆蓋", r8 <= 0.05, f"皮膚科 OTHER {r8:.2%}"))

    # 13 金絲雀藥物
    canary = [c.upper() for c in tags["canary_inn"]]
    missing = [c for c in canary if not ings.get(c, {}).get("derm")]
    g.append(Gate(13, "金絲雀藥物", not missing, f"{len(canary)-len(missing)}/{len(canary)} 缺:{missing}"))

    # 14 類固醇酯基不可塌縮
    # 真正的危險是「同一個 base 的兩種酯基被併成同一個 key」——例如 betamethasone
    # valerate(Class III) 與 dipropionate(Class I–II) 變成一張卡片。
    # 外用(D07)裸名本身不一定是錯（desoximetasone、hydrocortisone base 都是真實劑型），
    # 所以只在「該 base 已知有多種酯基流通」時才判定為塌縮。
    ew = yaml.safe_load((CURATION / "ester_whitelist.yaml").read_text(encoding="utf-8"))
    preserve = {x.upper() for x in ew["preserve_ester"]}
    topical_keys = collections.defaultdict(set)
    for p in products.values():
        if not p["atc"].startswith("D07") or p["is_combo"]:
            continue
        for k in p["inn_keys"]:
            topical_keys[k.split(" (")[0]].add(k)
    allow_bare = {k.upper() for k in (ew.get("allow_bare_with_ester") or {})}
    collapsed = [
        b for b, ks in topical_keys.items()
        if b in preserve and b in ks and len(ks) > 1 and b not in allow_bare
    ]
    g.append(Gate(14, "類固醇酯基", not collapsed, f"外用裸名與酯基並存: {collapsed or '無'}"))

    # 15 stub 翻轉
    prev_stub = prev.get("stub_codes") or []
    flipped = [c for c in rules if c not in prev_stub and rules[c].get("is_stub")
               and c in prev.get("nonstub_codes", [])]
    g.append(Gate(15, "stub 翻轉", not flipped, f"{len(flipped)} 節 {flipped[:5]}"))

    # 16 皮膚科種子章節必須被標籤命中
    seed = ["13.4.", "13.17.1.", "10.7.1.1.", "10.7.1.2.", "8.2.4.", "10.6.4.", "8.2.16."]
    tagged_secs = {s for i in ings.values() if i["derm"] for s in i["sections"]}
    miss_seed = [s for s in seed if not any(match_prefix(t, s) or match_prefix(s, t) for t in tagged_secs)]
    g.append(Gate(16, "種子章節命中", not miss_seed, f"缺 {miss_seed}"))

    # 17 皮膚科章節條文覆蓋率
    # 低覆蓋率的節會退回顯示原文（安全），但若皮膚科主力章節覆蓋率太低，
    # 代表官方換了版型、解析器需要跟上，不能默默放過。
    derm_pref = tags["sections"]
    low = [
        (c, r.get("coverage"))
        for c, r in rules.items()
        if not r.get("no_pdf") and r.get("coverage") is not None
        and r["coverage"] < 0.70 and any(match_prefix(c, p) for p in derm_pref)
    ]
    g.append(Gate(17, "皮膚科條文覆蓋", not low, f"覆蓋率<70% 的皮膚科章節: {low or '無'}"))

    # 18 相容表意文字必須已正規化
    # 健保 PDF 夾雜 CJK 相容表意文字（U+F900–U+FAFF），長得跟一般字一樣但碼位不同，
    # 會讓「療程」這種關鍵字比對整批失效。parse 階段已做 NFC，這裡守住不能回退。
    compat = [
        c for c, r in rules.items()
        if any(0xF900 <= ord(ch) <= 0xFAFF for ch in (r.get("text") or ""))
    ]
    g.append(Gate(18, "相容表意文字", not compat, f"未正規化 {len(compat)} 節 {compat[:5]}"))

    # 19 學名鍵不得夾中文
    # 部分 分類分組名稱 用空白而非逗號分隔（'AMOROLFINE HCL 55.74MG/ML 外用液劑 5.0ML'），
    # 中文劑型詞會黏進學名，把同一支藥拆成兩個 —— 其中一個帶章節、一個沒有。
    cjk_keys = [
        k for k in ings
        if k[:1].isascii() and any("\u3400" <= ch <= "\u9fff" for ch in k)
    ]
    g.append(Gate(19, "學名鍵無中文", not cjk_keys, f"{len(cjk_keys)} 個 {cjk_keys[:5]}"))

    # 20 表格還原無損（防迴歸：只要有一個表沒通過無損驗證就不該被輸出）
    bad_tab = [c for c, r in rules.items()
               for t in (r.get("tables") or []) if not t.get("lossless")]
    g.append(Gate(20, "表格無損", not bad_tab, f"未通過 {len(bad_tab)} 個 {bad_tab[:4]}"))

    # 20b 表格金絲雀：這幾張是實測確認過的關鍵表，欄數不得跑掉
    tab_canary = {"13.17.2.": 8, "2.6.1.": 5, "8.2.4.11.": 8}
    tab_bad = []
    for code, want in tab_canary.items():
        cols = {t["cols"] for t in (rules.get(code, {}).get("tables") or [])}
        if want not in cols:
            tab_bad.append(f"{code}期望{want}欄,實得{sorted(cols)}")
    g.append(Gate(26, "表格金絲雀", not tab_bad, f"{tab_bad or '無'}"))

    # 21 散文不得被誤判成表格（負向金絲雀）
    # 這幾節是純散文。pymupdf 的 "text" strategy 會把它們切成假表格且切在字中間
    # （實測 8.2.16. 被切出「(2)M」「ethotrexate」），所以只用 lines 系列策略。
    prose_canary = ["13.15.", "13.10.", "13.11.", "13.16.", "10.6.4.", "10.7.1.1.",
                    "8.2.1.", "13.3.1.", "10.7.1.2.", "8.2.16.", "13.4.", "13.5."]
    wrong = [c for c in prose_canary if rules.get(c, {}).get("tables")]
    g.append(Gate(21, "散文非表格", not wrong, f"誤判為表格: {wrong or '無'}"))

    # 22 附表定位金絲雀：這幾節必須找得到附表（本節或跨節）
    appx_canary = {"13.4.": "附表十", "13.5.": "附表十一", "13.17.1.": "附表三十二"}
    lost = []
    for code, name in appx_canary.items():
        refs = rules.get(code, {}).get("appx_refs") or []
        if not any(x["name"] == name and not x["missing"] for x in refs):
            lost.append(f"{code}/{name}")
    g.append(Gate(22, "附表定位", not lost, f"定位失敗: {lost or '無'}"))

    # 23 附表判定數量穩定（防 regex 放寬造成誤判暴增）
    n_appx = sum(1 for r in rules.values() if r.get("appendix_from") is not None)
    prev_appx = prev.get("n_appendix")
    ok23 = prev_appx is None or n_appx <= max(prev_appx * 2, prev_appx + 15)
    g.append(Gate(23, "附表節數穩定", ok23, f"{n_appx} 節（上期 {prev_appx}）"))

    # 24 旗標皆有憑據：旗標是關鍵字掃出來的，沒有原文憑據就無法驗證
    no_ev = [c for c, r in rules.items()
             if r.get("flags", {}).get("prior_review") and not (r.get("flags_ev") or {}).get("prior_review")]
    g.append(Gate(24, "旗標有憑據", not no_ev, f"缺憑據 {len(no_ev)} 節 {no_ev[:4]}"))

    # 25 上游來源已登錄（沒有 sha256 與取得時間就無法回答「這份資料哪來的」）
    src_path = STAGING.parent / "sources.json"
    srcs = json.loads(src_path.read_text(encoding="utf-8")).get("sources", {}) if src_path.exists() else {}
    need = {"nhi_csv", "tfda_json"}
    missing_src = [s_ for s_ in need
                   if s_ not in srcs or not srcs[s_].get("sha256") or not srcs[s_].get("fetched_at")]
    g.append(Gate(25, "上游已登錄", not missing_src, f"缺: {missing_src or '無'}"))

    # 27 劑量引用忠實性：每條 quote 必須逐字出現在該章節條文中
    # 這是「零幻覺」的機制保證 —— 系統只做選句，不得生成或改寫任何字
    dpath = STAGING / "dosing.json"
    dosing = json.loads(dpath.read_text(encoding="utf-8")) if dpath.exists() else {}
    infidel = []
    for inn, kinds in dosing.items():
        for kind, items in kinds.items():
            for it in items:
                body = (rules.get(it["section"], {}).get("text") or "")
                if re.sub(r"\s+", "", it["quote"]) not in re.sub(r"\s+", "", body):
                    infidel.append(f"{inn}/{it['section']}")
    g.append(Gate(27, "劑量引用忠實", not infidel, f"非原文 {len(infidel)} 條 {infidel[:4]}"))

    # 28 前置用藥不得混入本藥劑量
    # 「Methotrexate 每週15mg」是申請 dupilumab 的條件，若跑進 direct
    # 醫師照著開就會出事，這是全案臨床風險最高的一條
    leak = []
    for inn, kinds in dosing.items():
        for it in kinds.get("direct", []) + kinds.get("section_sole", []):
            low = it["quote"].lower()
            base = inn.split(" (")[0].lower()
            others = [k for k in dosing
                      if k != inn and len(k.split(" (")[0]) >= 6
                      and re.search(rf"(?<![a-z]){re.escape(k.split(' (')[0].lower())}(?![a-z])", low)]
            if others and not re.search(rf"(?<![a-z]){re.escape(base)}(?![a-z])", low):
                leak.append(f"{inn}←{others[0]}")
    g.append(Gate(28, "劑量歸屬純度", not leak, f"疑似他藥劑量 {len(leak)} 條 {leak[:4]}"))

    # 29–31 醫療處置
    procp = STAGING / "procedures.json"
    procs = json.loads(procp.read_text(encoding="utf-8")) if procp.exists() else {}
    ptags = yaml.safe_load((CURATION / "procedure_tags.yaml").read_text(encoding="utf-8"))

    p0 = prev.get("n_procs")
    ok29 = not procs or p0 is None or 0.90 * p0 <= len(procs) <= 1.10 * p0
    g.append(Gate(29, "處置筆數健檢", ok29, f"{len(procs):,}（上期 {p0}）"))

    # 處置金絲雀：這些醫令必須在皮膚科子集內
    miss_p = [c for c in ptags["canary"] if not procs.get(c, {}).get("derm")]
    g.append(Gate(30, "處置金絲雀", not miss_p, f"缺 {miss_p or '無'}"))

    # blocklist 的醫令絕不能出現在皮膚科子集
    # 57117B「加強照光治療」是新生兒黃疸，混進來醫師查「照光」會拿到錯的
    leaked = [c for c in (ptags.get("blocklist") or {}) if procs.get(c, {}).get("derm")]
    g.append(Gate(31, "處置黑名單", not leaked, f"洩漏 {leaked or '無'}"))

    # 32 表格挖除的一致性
    #    表格文字從 clause 挖掉、原位換成標記後，UI 才不會「先印一堆碎片、
    #    後面再附一張正確的表」。這裡確認標記沒有指向不存在的表格，
    #    且沒有洩漏到 text（原文欄位是 diff 的比對基準，必須保持乾淨）。
    bad_mark, leak_txt, n_mark = [], [], 0
    for code, r in rules.items():
        tabs = r.get("tables") or []
        for c in r.get("clauses", []):
            for m in RE_TBMARK.finditer(c.get("text", "")):
                n_mark += 1
                if int(m.group(1)) >= len(tabs):
                    bad_mark.append(code)
        if RE_TBMARK.search(r.get("text", "")):
            leak_txt.append(code)
    n_spliced = sum(r.get("tables_spliced", 0) for r in rules.values())
    ok32 = not bad_mark and not leak_txt and n_mark == n_spliced
    g.append(Gate(32, "表格就地渲染", ok32,
                  f"標記 {n_mark}／挖除 {n_spliced}"
                  + (f"｜壞標記 {bad_mark[:3]}" if bad_mark else "")
                  + (f"｜原文遭汙染 {leak_txt[:3]}" if leak_txt else "")))

    # 33 仿單劑量忠實度
    #    輸出必須是食藥署開放資料「用法用量」欄位的逐字原文。
    #    只要有一段對不回原始欄位，就代表程式改動過藥廠登載的用法 —— 直接擋。
    tf_path = STAGING / "dose_tfda.json"
    if tf_path.exists() and (RAW / "tfda_licence.json").exists():
        dt = json.loads(tf_path.read_text(encoding="utf-8"))
        src = {}
        for r in json.loads((RAW / "tfda_licence.json").read_text(encoding="utf-8")):
            u = unicodedata.normalize("NFC", (r.get("用法用量") or "")).strip()
            if u:
                src[unicodedata.normalize("NFC", (r.get("許可證字號") or "")).strip()] = u
        bad33 = []
        for inn, groups in dt.items():
            for gg in groups:
                lics = gg.get("licences") or []
                if not any(gg["text"] == src.get(x) for x in lics):
                    bad33.append(f"{inn}/{lics[:1]}")
                for quote in gg.get("adjust") or []:
                    if quote not in gg["text"]:
                        bad33.append(f"{inn}:調整句非原文")
        g.append(Gate(33, "仿單劑量忠實", not bad33,
                      f"{len(dt):,} 學名｜非原文 {len(bad33)} {bad33[:3]}"))

    # 34 表格碎片殘留
    #    模擬醫師眼睛：連續 4 行以上都只有 1–6 個字 = 表格被線性化成碎片
    #    （dupilumab EASI 表當初就是長這樣）。真正的條文不會這樣排。
    #    白名單裡的四節是空白申請書，PDF 本身沒有可還原的格線結構
    #    （是/否勾選欄跨欄合併、印信框直書），find_tables 也救不了。
    #   9.41.     官印欄（印信／承辦人／複核）直書，不是臨床內容
    #   1.6.2.2.  肉毒桿菌注射評估表，欄位標題直書拆行
    #   8.2.4.11. 掌蹠膿皰症申請書的「是／否」勾選欄跨欄合併，
    #             find_tables 還原出來的字串在 PDF 線性文字裡不存在
    KNOWN_FRAG = {"9.41.", "1.6.2.2.", "8.2.4.11."}
    frag = set()
    for code, r in rules.items():
        for c in r.get("clauses", []):
            lines = [x.strip() for x in RE_TBMARK.sub("", c.get("text", "")).split("\n")]
            run = 0
            for ln in lines:
                run = run + 1 if 0 < len(ln) <= 6 else 0
                if run >= 4:
                    frag.add(code)
                    break
            if code in frag:
                break
    new_frag = sorted(frag - KNOWN_FRAG)
    g.append(Gate(34, "表格碎片殘留", not new_frag,
                  f"{len(frag)} 節（已知 {len(frag & KNOWN_FRAG)}）"
                  + (f"｜新增 {new_frag[:5]}" if new_frag else "")))

    # 35 別名不可把主檔實際使用的拼法改寫成主檔沒有的拼法
    #    本站的學名鍵就是主檔「分類分組名稱」的第一段。實際踩過：
    #    主檔寫 CYCLOSPORIN(114)/ACYCLOVIR(1785)，我們卻改寫成
    #    CICLOSPORIN(0)/ACICLOVIR(0) —— 等於發明了一個主檔查不到的鍵，
    #    造成 #/i/CYCLOSPORIN 一片「找不到」，以及條文比對判錯跳到別的藥。
    #
    #    只擋這個精確模式：「來源拼法主檔有在用，canonical 主檔完全沒有」。
    #    刻意不擋另外兩種：
    #      · 兩邊都不在主檔（如 BRIVUDIN→BRIVUDINE，健保未收載）＝休眠規則，無害
    #      · canonical 以子字串形式存在（主檔寫 RETINOIC ACID (=TRETINOIN)）＝合法
    alias_path = CURATION / "inn_alias.yaml"
    if alias_path.exists() and (RAW / "nhi_drug.csv").exists():
        heads: set[str] = set()
        with (RAW / "nhi_drug.csv").open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                v = (row.get("分類分組名稱") or "").split(",")[0].strip().upper()
                if v:
                    heads.add(v)
        blob = "\n".join(heads)
        al = yaml.safe_load(alias_path.read_text(encoding="utf-8")).get("aliases") or {}
        rewrite = [f"{k}→{v}" for k, v in al.items()
                   if k.upper() in heads and v.upper() not in blob]
        g.append(Gate(35, "別名不改寫主檔拼法", not rewrite,
                      f"{len(al)} 條規則｜違規 {rewrite[:4] or '無'}"))

    # 36 附表對照表有效
    #    URL 內含不透明 id，健保署改版附表時會換 id。快照缺漏或雜湊對不上，
    #    代表對照表過期 —— 列表頁擋程式（403），只能用瀏覽器重抓一次。
    appx_yaml = CURATION / "appendix_files.yaml"
    if appx_yaml.exists():
        cur = (yaml.safe_load(appx_yaml.read_text(encoding="utf-8")) or {}).get("appendices") or {}
        man = json.loads(APPX_MANIFEST.read_text(encoding="utf-8")) \
            if APPX_MANIFEST.exists() else {}
        stale = sorted(n for n, v in cur.items()
                       if man.get(n, {}).get("url") != v.get("url"))
        nofile = sorted(n for n in cur
                        if not (SNAP_APPX / f"{n.replace('/', '_').replace(' ', '')}.pdf").exists())
        ok36 = not stale and not nofile
        g.append(Gate(36, "附表對照表有效",
                      ok36,
                      f"{len(cur)} 個附表"
                      + (f"｜URL 變動 {stale[:3]}" if stale else "")
                      + (f"｜缺快照 {nofile[:3]}" if nofile else "")
                      + ("｜需用瀏覽器重抓列表頁" if not ok36 else "")))

    # 37 附表參照可解析
    #    條文引用的附表必須指得到本體（章節內、官方獨立檔、或細分成子檔）。
    #    白名單是健保署自己沒單獨發布的，比照 gate 34 的做法。
    KNOWN_NO_APPX = {"附表十六之二", "附表九之六"}
    unresolved = sorted({x["name"] for r in rules.values()
                         for x in (r.get("appx_refs") or []) if x.get("missing")})
    new_unres = [n for n in unresolved if n not in KNOWN_NO_APPX]
    g.append(Gate(37, "附表參照可解析", not new_unres,
                  f"無本體 {len(unresolved)}（已知 {len(set(unresolved) & KNOWN_NO_APPX)}）"
                  + (f"｜新增 {new_unres[:4]}" if new_unres else "")))

    # 38 仿單連結覆蓋率
    #    上游欄位改名會讓它靜默歸零 —— 這種「不會報錯只會變空」的破壞最難發現。
    derm_ings = [i for i in ings.values() if i.get("derm")]
    with_ins = sum(1 for i in derm_ings
                   if any(products.get(c, {}).get("has_insert")
                          for r in i["routes"].values() for c in r["products"]))
    rate = with_ins / max(1, len(derm_ings))
    g.append(Gate(38, "仿單連結覆蓋", rate >= 0.90,
                  f"皮膚科學名 {with_ins}/{len(derm_ings)} ({rate:.0%})，下限 90%"))

    # 11 前端產物
    if (PUBLIC / "derm.json").exists():
        kb = len(gzip.compress((PUBLIC / "derm.json").read_bytes(), 9)) / 1024
        n = len(json.loads((PUBLIC / "derm.json").read_text(encoding="utf-8"))["ing"])
        g.append(Gate(11, "前端產物", kb < 300 and n > 200, f"derm.json {kb:.0f} KB gz / {n} 學名"))
    return g


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--override", default="", help="人工確認後放行的 gate 編號，如 6,10")
    args = ap.parse_args()
    allow = {int(x) for x in args.override.split(",") if x.strip().isdigit()}

    gates = run()
    failed = [g for g in gates if not g.passed and g.id not in allow]
    for g in gates:
        icon = "✅" if g.passed else ("🟡" if g.id in allow else "❌")
        print(f"{icon} gate {g.id:>2} {g.name:<14} {g.message}")
    # 把 override 記進報告 —— promote.py 只讀這份檔案決定要不要搬，
    # 不記的話人工放行過的閘門在 promote 階段又會被擋一次。
    (STAGING / "validation_report.json").write_text(json.dumps(
        [{"id": g.id, "name": g.name, "passed": g.passed, "message": g.message,
          "overridden": (not g.passed) and g.id in allow} for g in gates],
        ensure_ascii=False, indent=2), encoding="utf-8")

    if failed:
        print(f"\n❌ {len(failed)} 個閘門失敗 → 不 promote，staging 保留於 {STAGING}")
        return 1
    print("\n✅ 全部閘門通過")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
