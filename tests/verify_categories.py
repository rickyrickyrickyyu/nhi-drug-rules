#!/usr/bin/env python3
"""分類驗證：生物製劑、A 酸、抗疱疹病毒藥。

每一筆都對照條文原文的可機械驗證事實，不是只看有沒有資料。
"""
from __future__ import annotations
import json, os, pathlib, re, sys

os.chdir(pathlib.Path(__file__).resolve().parents[1])
D = {i["k"]: i for i in json.load(open("public/data/derm.json", encoding="utf-8"))["ing"]}
R = json.load(open("data/build/rules.json", encoding="utf-8"))

CATEGORIES = {
    "生物製劑／小分子": [
        ("DUPILUMAB",      ["13.17.1."], "異位性皮膚炎", ["EASI", "事前審查"]),
        ("LEBRIKIZUMAB",   ["13.17.1."], "異位性皮膚炎", ["EASI"]),
        ("SECUKINUMAB",    ["8.2.4.6.", "8.2.4.14."], "乾癬／化膿性汗腺炎",
         {"8.2.4.6.": ["乾癬"], "8.2.4.14.": ["化膿性汗腺炎"]}),
        ("IXEKIZUMAB",     ["8.2.4.6."], "乾癬", ["乾癬"]),
        ("USTEKINUMAB",    ["8.2.4.6."], "乾癬", ["乾癬"]),
        ("GUSELKUMAB",     ["8.2.4.6.", "8.2.4.11."], "乾癬／掌蹠膿皰症",
         {"8.2.4.6.": ["乾癬"], "8.2.4.11.": ["掌蹠膿皰症"]}),
        ("RISANKIZUMAB",   ["8.2.4.6."], "乾癬", ["乾癬"]),
        ("BRODALUMAB",     ["8.2.4.6."], "乾癬", ["乾癬"]),
        # 健保未給 bimekizumab 章節碼（8.2.4.4. 條文標題有列名，屬資料缺漏）
        ("BIMEKIZUMAB",    [], "乾癬（健保未給章節碼）", {}),
        ("SPESOLIMAB",     ["8.2.4.6.2."], "全身型膿疱性乾癬", ["膿疱性乾癬"]),
        ("ADALIMUMAB",     ["8.2.4.6."], "乾癬", ["乾癬"]),
        ("ETANERCEPT",     ["8.2.4.6."], "乾癬", ["乾癬"]),
        ("APREMILAST",     ["8.2.16."], "斑塊乾癬", ["斑塊乾癬"]),
        ("DEUCRAVACITINIB",["8.2.16."], "斑塊乾癬", ["斑塊乾癬"]),
        ("UPADACITINIB",   ["13.17.1."], "異位性皮膚炎", ["EASI"]),
        ("ABROCITINIB",    ["13.17.1."], "異位性皮膚炎", ["EASI"]),
    ],
    "A 酸類": [
        ("ISOTRETINOIN",   ["13.4."],  "口服 A 酸", ["限皮膚科專科醫師", "同意書", "100 mg"]),
        ("ACITRETIN",      ["13.5."],  "乾癬用 A 酸", ["同意書"]),
        ("TAZAROTENE",     ["13.8."],  "外用 A 酸", []),
        ("ADAPALENE",      [],         "外用 A 酸（無專章）", []),
        # NHI 的 tretinoin 分組含口服 Vesanoid（急性前骨髓性白血病）→ 9.15.
        ("TRETINOIN",      ["9.15."],  "外用＋口服（口服屬抗癌瘤）", {}),
    ],
    "抗疱疹病毒": [
        ("ACYCLOVIR",      ["10.7.1.1.", "10.7.1.2.", "14.2."], "全身／外用／眼用",
         {"10.7.1.1.": ["疱疹性腦炎"], "10.7.1.2.": ["3 日內"], "14.2.": ["角膜"]}),
        ("FAMCICLOVIR",    ["10.7.1.1."], "全身性", {"10.7.1.1.": ["Famciclovir"]}),
        ("VALACICLOVIR",   ["10.7.1.1."], "全身性", {"10.7.1.1.": ["valaciclovir"]}),
    ],
}

fails = []
for cat, cases in CATEGORIES.items():
    print(f"\n{'═' * 74}\n{cat}\n{'═' * 74}")
    for inn, expect_secs, note, keywords in cases:
        it = D.get(inn)
        probs = []
        if not it:
            probs.append("不在皮膚科子集")
        else:
            secs = {s for r in it["r"] for s in r["s"]}
            for e in expect_secs:
                if e not in secs:
                    probs.append(f"未連到 {e}")
            if not expect_secs and secs:
                probs.append(f"預期無專章卻有 {sorted(secs)}")
            # 關鍵字必須綁定到特定章節：8.2.4.14. 是化膿性汗腺炎，
            # 拿「乾癬」去驗它當然會失敗 —— 那是測試寫錯，不是資料錯。
            kw_map = keywords if isinstance(keywords, dict) else (
                {expect_secs[0]: keywords} if expect_secs and keywords else {})
            for sec_code, kws in kw_map.items():
                t = (R.get(sec_code) or {}).get("text", "")
                for k in kws:
                    if k not in t:
                        probs.append(f"{sec_code} 條文缺「{k}」")
        mark = "✅" if not probs else "❌"
        brands = "、".join(it["r"][0].get("bp", [])[:2]) if it and it.get("r") else "—"
        print(f"  {mark} {inn:18s} {note:18s} {brands[:26]:28s} {'；'.join(probs)}")
        if probs:
            fails.append((inn, probs))

total = sum(len(v) for v in CATEGORIES.values())
print(f"\n{total - len(fails)}/{total} 通過")
sys.exit(1 if fails else 0)
