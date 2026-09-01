#!/usr/bin/env python3
"""比對 JS 與 Python 兩邊的搜尋排序是否完全一致。

用法：
    node tests/search_parity.mjs && python3 tests/search_parity.py
"""
from __future__ import annotations
import importlib.util, json, os, pathlib, sys

os.chdir(pathlib.Path(__file__).resolve().parents[1])
spec = importlib.util.spec_from_file_location("q", "cli/query.py")
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)

d = json.load(open("public/data/derm.json", encoding="utf-8"))
data = [*d["ing"], *d.get("proc", [])]
js = json.load(open("/tmp/parity_js.json", encoding="utf-8"))

bad = []
for query, jres in js.items():
    nq = q.norm(query)
    hits = []
    for it in data:
        sc = q.score_proc(nq, it) if it.get("t") == "p" else q.score(nq, it)
        if sc[0]:
            hits.append((sc[0], it))
    hits.sort(key=lambda x: (-x[0], str(x[1]["n"])))
    py = [f"{it['k']}:{sc}" for sc, it in hits[:5]]
    if py != jres:
        bad.append((query, jres, py))
        print(f"❌ {query}\n   JS={jres}\n   PY={py}")

print(f"\n{len(js) - len(bad)}/{len(js)} 一致")
sys.exit(1 if bad else 0)
