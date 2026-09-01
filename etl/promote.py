#!/usr/bin/env python3
"""staging → 正式位置的原子搬移。gate 全綠才呼叫。

用法：
    python3 etl/promote.py

為什麼需要這支：光靠 validate 失敗時 sys.exit(1) 不夠 —— 半寫完的檔案會留在
正式位置，污染下個月的 diff 基準。所有產物先寫 .staging/，驗完才逐檔 os.replace()
（同一檔案系統內是原子操作）。
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import BUILD, PUBLIC, SNAPSHOTS, STAGING  # noqa: E402


def main() -> int:
    report = STAGING / "validation_report.json"
    if not report.exists():
        raise SystemExit("❌ 找不到 validation_report.json，請先跑 validate.py")
    gates = json.loads(report.read_text(encoding="utf-8"))
    failed = [g for g in gates if not g["passed"] and not g.get("overridden")]
    if failed:
        raise SystemExit(f"❌ 仍有 {len(failed)} 個閘門失敗，拒絕 promote: {[g['name'] for g in failed]}")
    overridden = [g for g in gates if g.get("overridden")]
    if overridden:
        # 人工放行要留痕：last_run.json 會被 commit，日後可回溯是誰在哪一期放行了什麼
        print(f"⚠️  人工放行 {len(overridden)} 個閘門: {[g['name'] for g in overridden]}")

    moved = 0
    for src in STAGING.glob("*.json"):
        dst = BUILD / src.name
        shutil.copy2(src, dst.with_suffix(".tmp"))
        os.replace(dst.with_suffix(".tmp"), dst)
        moved += 1

    # last_run.json 是下個月 gate 的比對基準，也是 cron 保活的 commit 目標
    prod = json.loads((STAGING / "products.json").read_text(encoding="utf-8"))
    rules = json.loads((STAGING / "rules.json").read_text(encoding="utf-8"))
    (SNAPSHOTS / "last_run.json").write_text(json.dumps({
        "run_at": date.today().isoformat(),
        "n_products": len(prod),
        "n_sections": len(rules),
        "n_appendix": sum(1 for r in rules.values() if r.get("appendix_from") is not None),
        "n_tables": sum(len(r.get("tables") or []) for r in rules.values()),
        "stub_codes": sorted(c for c, r in rules.items() if r.get("is_stub")),
        "nonstub_codes": sorted(c for c, r in rules.items() if not r.get("is_stub")),
        "gates": gates,
    }, ensure_ascii=False), encoding="utf-8")

    print(f"✅ promote 完成，搬移 {moved} 個檔案｜前端產物已在 {PUBLIC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
