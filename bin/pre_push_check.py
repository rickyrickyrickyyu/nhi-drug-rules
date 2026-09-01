#!/usr/bin/env python3
"""推上公開 repo 之前的最後一道閘門。

★ 為什麼需要：
  本專案的 repo 是**公開**的，而一鍵更新原本是 `git add -A` —— 任何被放進
  專案資料夾的檔案都會被 commit 並推上 GitHub。醫師把病歷截圖、匯出的臨床
  註記、或隨手的 scratch 檔放進來，就會變成永久的公開紀錄
  （刪掉也還在 git 歷史、reflog，以及別人早已 clone 的副本裡）。

  所以改成：只允許 commit 已知的資料路徑，其餘一律擋下並列出來讓人確認。

★ 兩道檢查：
  1. 路徑白名單 —— 只有 pipeline 會產出的路徑可以進 commit
  2. 內容掃描   —— 就算路徑合法，內容出現身分證號／手機／病歷號＋姓名
                   這類樣式也擋下（防止上游資料或人工策展夾帶個資）

用法：
    python3 bin/pre_push_check.py          檢查目前工作區的變更
    python3 bin/pre_push_check.py --staged 檢查已 staged 的內容
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# pipeline 會動到的路徑（前綴比對）。其餘一律視為「不該出現在這裡的東西」。
ALLOW_PREFIX = (
    "public/data/",
    "snapshots/",
    "curation/",          # 人工策展層（clinical_notes/ 已被 .gitignore 排除）
    "etl/", "src/", "cli/", "tests/", "bin/", ".github/",
    "offline/MANIFEST.txt",
    "docs/",
)
ALLOW_EXACT = {
    "README.md", "DATA_LICENSE.md", "LICENSE", "Makefile", ".gitignore",
    "package.json", "pnpm-lock.yaml", "vite.config.js", ".oxlintrc.json",
    "index.html", "pyproject.toml", "uv.lock",
}

# 個資樣式。刻意不抓「病歷號碼：」單獨出現 —— 官方空白表單裡本來就有這個標籤。
PII = {
    "身分證字號": re.compile(r"(?<![A-Za-z0-9])[A-Z][12]\d{8}(?![0-9])"),
    # ★ 不能只比對數字樣式：官方公告文號長得一模一樣
    #   （「93.6.14健保醫字第0930060063號公告」出現在 procs_all.json 幾十次）。
    #   排除前面是「第」或後面是「號」的情形，否則閘門每次都誤報，
    #   久了就會被當成雜訊忽略 —— 那比沒有閘門更糟。
    "手機號碼": re.compile(r"(?<![第\d])09\d{2}[- ]?\d{3}[- ]?\d{3}(?![\d號])"),
    "病歷號（有值）": re.compile(r"病歷號碼?\s*[：:]\s*[A-Za-z0-9]{4,}"),
    "出生日期（有值）": re.compile(r"出生日期\s*[：:]\s*\d{2,4}[/年-]\d{1,2}"),
    "金鑰樣式": re.compile(r"(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,})"),
}

# 掃內容時跳過的二進位／超大檔
SKIP_SUFFIX = {".pdf", ".png", ".jpg", ".jpeg", ".ico", ".zip", ".woff", ".woff2"}


def _git_z(*args: str) -> list[str]:
    """★ 一律用 -z：git 預設會把含非 ASCII 的路徑加引號並跳脫成
    "bin/\346\233\264..."，那串既不是真實路徑、也對不上白名單前綴，
    會把 bin/更新健保資料.command 這種正常檔案誤判成可疑檔案。
    另外檔名可能含空白，用 split() 也會拆錯。"""
    out = subprocess.run(["git", *args, "-z"], cwd=ROOT,
                         capture_output=True, text=True).stdout
    return [x for x in out.split("\0") if x]


def changed_files(staged: bool) -> list[str]:
    args = ["diff", "--name-only", "--diff-filter=ACMR"]
    if staged:
        args.append("--cached")
    out = _git_z(*args)
    if not staged:
        out += _git_z("ls-files", "--others", "--exclude-standard")
    return sorted(set(out))


def allowed(path: str) -> bool:
    return path in ALLOW_EXACT or path.startswith(ALLOW_PREFIX)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--staged", action="store_true")
    args = ap.parse_args()

    files = changed_files(args.staged)
    if not files:
        print("－ 沒有變更")
        return 0

    stray = [f for f in files if not allowed(f)]
    findings: list[tuple[str, str, str]] = []
    for f in files:
        p = ROOT / f
        if p.suffix.lower() in SKIP_SUFFIX or not p.exists() or p.stat().st_size > 40_000_000:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, pat in PII.items():
            m = pat.search(text)
            if m:
                findings.append((f, name, m.group(0)[:40]))

    if stray:
        print("❌ 出現不屬於資料管線的檔案，拒絕推上公開 repo：")
        for f in stray[:20]:
            print(f"     {f}")
        print("   → 這是公開 repo。請確認這些檔案該不該公開；"
              "本機草稿請移出專案資料夾或加進 .gitignore。")
    if findings:
        print("❌ 內容出現疑似個資／金鑰：")
        for f, name, s in findings[:20]:
            print(f"     {f}  【{name}】{s}")
        print("   → 一旦推上去就永遠留在公開歷史裡，請先移除。")

    if stray or findings:
        return 1
    print(f"✅ 推送前檢查通過（{len(files)} 個檔案，皆屬資料管線路徑，無個資樣式）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
