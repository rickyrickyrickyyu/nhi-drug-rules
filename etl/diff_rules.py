#!/usr/bin/env python3
"""章節改版 → 條文 diff → changelog。

用法：
    python3 etl/diff_rules.py

★ 用「句子級」而非「行級」diff：pymupdf 對同一份 PDF 在不同版本間的斷行會有
  微小差異，行級 diff 會產生大量假陽性，把真正的法規變動淹沒。
"""

from __future__ import annotations

import difflib
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import MANIFEST, PUBLIC, SNAP_DIFF, SNAP_TEXT, STAGING  # noqa: E402
from lib.section import code_tuple  # noqa: E402

TODAY = date.today().isoformat()
_SENT = re.compile(r"(?<=[。；：！？])|\n+")


def sentences(text: str) -> list[str]:
    out = [s.strip() for s in _SENT.split(text or "") if s and s.strip()]
    return out


def diff_texts(old: str, new: str) -> dict:
    a, b = sentences(old), sentences(new)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    hunks, added, removed, equal = [], 0, 0, 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            equal += i2 - i1
            continue
        old_txt = a[i1:i2]
        new_txt = b[j1:j2]
        removed += len(old_txt)
        added += len(new_txt)
        hunks.append({
            "op": tag,
            "removed": old_txt,
            "added": new_txt,
            "ctx_before": a[max(0, i1 - 1): i1],
            "ctx_after": a[i2: i2 + 1],
        })
    total = max(len(a), len(b), 1)
    return {
        "hunks": hunks,
        "stats": {
            "sent_added": added, "sent_removed": removed, "sent_equal": equal,
            "change_ratio": round((added + removed) / (total * 2), 4),
        },
    }


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    events_path = STAGING / "fetch_events.json"
    events = json.loads(events_path.read_text(encoding="utf-8")) if events_path.exists() else {"events": []}

    changes = []
    for ev in events["events"]:
        code, kind = ev["code"], ev["kind"]
        if kind not in ("revised", "silent_edit"):
            continue
        m = manifest.get(code, {})
        old_name, new_name = ev.get("from"), ev.get("to")
        old_txt_p = SNAP_TEXT / (old_name or "").replace(".pdf", ".txt")
        new_txt_p = SNAP_TEXT / (new_name or "").replace(".pdf", ".txt")
        if not new_txt_p.exists():
            continue
        old_txt = old_txt_p.read_text(encoding="utf-8") if old_txt_p.exists() else ""
        d = diff_texts(old_txt, new_txt_p.read_text(encoding="utf-8"))

        month_dir = SNAP_DIFF / TODAY[:7]
        month_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{code.rstrip('.').replace('.', '-')}__{(old_name or 'new').split('_')[-1].replace('.pdf','')}__{m.get('effective_date','')}"
        (month_dir / f"{stem}.json").write_text(json.dumps({
            "section_code": code, "kind": kind, "detected_at": TODAY,
            "from": old_name, "to": new_name,
            "effective_date": m.get("effective_date"), **d,
        }, ensure_ascii=False, indent=1), encoding="utf-8")

        changes.append({
            "code": code, "kind": kind, "eff": m.get("effective_date"),
            "ratio": d["stats"]["change_ratio"],
            "added": d["stats"]["sent_added"], "removed": d["stats"]["sent_removed"],
            "diff_file": f"{TODAY[:7]}/{stem}.json",
        })

    changes.sort(key=lambda c: code_tuple(c["code"]))
    new_sections = [e["code"] for e in events["events"] if e["kind"] == "new"]
    changelog = {
        "generated_at": TODAY,
        "month": TODAY[:7],
        "n_revised": sum(1 for c in changes if c["kind"] == "revised"),
        "n_silent_edit": sum(1 for c in changes if c["kind"] == "silent_edit"),
        "n_new": len(new_sections),
        "changes": changes,
        # 首次建庫時 534 節全是 new，列出來只會洗版；之後每月才有意義
        "new_sections": new_sections if len(new_sections) < 50 else [],
        "new_sections_count": len(new_sections),
    }
    (STAGING / "changelog.json").write_text(json.dumps(changelog, ensure_ascii=False), encoding="utf-8")
    (PUBLIC / "changelog.json").write_text(json.dumps(changelog, ensure_ascii=False), encoding="utf-8")
    print(f"✅ changelog：改版 {changelog['n_revised']}｜靜默改檔 {changelog['n_silent_edit']}｜新增 {changelog['n_new']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
