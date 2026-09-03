#!/usr/bin/env python3
"""產生可帶進封閉網路的單一 HTML 檔。

用法：
    python3 etl/build_offline.py [--scope derm|all|both] [--zip]

★ 設計取捨
  單一 .html、零可執行檔：封閉環境的醫院電腦，.exe/.bat/.command 幾乎必被
  防毒或群組原則擋下；純網頁沒有這個問題，雙擊用瀏覽器開即可。
  file:// 下 fetch() 讀不到本機檔案，所以資料必須內嵌成 JS 字面量。

★ 與線上版保證同一份資料
  只讀 public/data/（promote 後的正式產物），不重跑任何 ETL，
  並計算指紋讓兩邊可比對。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import PUBLIC, ROOT  # noqa: E402
from lib.fingerprint import app_fingerprint, data_fingerprint  # noqa: E402

DIST = ROOT / "dist-offline"
OUT = ROOT / "offline"
TODAY = date.today().isoformat()

# 防毒啟發式掃描的紅旗。React production build 不會產生這些，
# 但產物必須實際掃過才敢說「不會被擋」。
_AV_FLAGS = ("eval(", "new Function(", "document.write(", "<iframe", "atob(")


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def collect(scope: str) -> tuple[dict, dict]:
    """回傳 (payload, per-file sha256)。payload 的 key 是前端 getJson 用的路徑。"""
    payload: dict = {}
    shas: dict[str, str] = {}

    def add(rel: str) -> None:
        p = PUBLIC / rel
        if not p.exists():
            return
        raw = p.read_bytes()
        payload[rel] = json.loads(raw)
        shas[rel] = _sha(raw)

    add("meta.json")
    add("derm.json")
    add("changelog.json")
    if scope == "all":
        add("all.json")
        add("procs_all.json")

    for p in sorted((PUBLIC / "rules").glob("*.json")):
        add(f"rules/{p.name}")
    for p in sorted((PUBLIC / "products").glob("*.json")):
        add(f"products/{p.name}")
    return payload, shas


def _embed(obj) -> str:
    """把資料安全地嵌進 <script> 內。

    ★ json.dumps 不會跳脫 `</script>`。條文原文來自健保署 PDF，只要哪天出現
      這串字，內嵌的資料就會提前關閉 script 標籤，後面的內容變成可執行的 HTML
      —— 離線檔會被帶進封閉網路的醫院電腦，這種洞不能留。
      目前資料裡沒有這串（實測 0 處），這是防未來不是防現在。

    ★ U+2028/U+2029 在舊版 JS 解析器裡不能出現在字串字面值中，一併跳脫。
    """
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return (s.replace("<", "\\u003c")
             .replace(">", "\\u003e")
             .replace("\u2028", "\\u2028")
             .replace("\u2029", "\\u2029"))


def build_html(payload: dict, shas: dict, scope: str) -> str:
    """把 app、樣式與資料合成單一 HTML。

    ★ 腳本一定要放在 </body> 之前，不能留在 <head>：
      Vite 產出的是 <script type="module">，module 會延後到 DOM 解析完才執行；
      內嵌成傳統 <script> 後會「立刻」執行，那時 <div id="root"> 還不存在，
      React 會丟 Minified error #299（找不到掛載節點），畫面整片空白。
    """
    idx = (DIST / "index.html").read_text(encoding="utf-8")

    # 抽出 app JS 並把原標籤從 head 移除
    app_js = ""
    for m in re.finditer(r'<script[^>]+src="([^"]+)"[^>]*></script>', idx):
        f = DIST / m.group(1).lstrip("./")
        if f.exists():
            app_js += f.read_text(encoding="utf-8") + "\n"
        idx = idx.replace(m.group(0), "")

    # CSS 留在 head（越早套用越不會閃版）
    for m in re.finditer(r'<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"[^>]*>', idx):
        f = DIST / m.group(1).lstrip("./")
        if f.exists():
            idx = idx.replace(m.group(0), f"<style>\n{f.read_text(encoding='utf-8')}\n</style>")
        else:
            idx = idx.replace(m.group(0), "")

    fingerprint = _sha("".join(f"{k}:{v}" for k, v in sorted(shas.items())).encode())[:16]
    meta = payload.get("meta.json", {})
    tail = (
        "<script>window.__NHI_OFFLINE__="
        + _embed(payload)
        + ";window.__NHI_OFFLINE_META__="
        + _embed({"built": meta.get("built"), "scope": scope,
                  "packed_at": TODAY, "fingerprint": fingerprint,
                  "files": len(payload)})
        + ";</script>\n<script>\n" + app_js + "\n</script>\n"
    )
    if "</body>" not in idx:
        raise SystemExit("❌ dist-offline/index.html 沒有 </body>，無法安全插入腳本")
    return idx.replace("</body>", tail + "</body>")


README = """皮膚科健保給付規定查詢 — 離線版
=====================================

怎麼用
------
用滑鼠左鍵連點兩下 .html 檔，它會用你電腦上的瀏覽器打開。
不需要安裝任何軟體，也不需要網路。

Windows：建議用 Edge 或 Chrome 開啟。
        若雙擊後開在記事本，請在檔案上按右鍵 →「開啟方式」→ 選瀏覽器。
Mac    ：直接雙擊即可。

檔案說明
--------
nhi-derm-offline-{d}.html   皮膚科版（常用學名、處置、條文）
nhi-full-offline-{d}.html   全庫版（全部學名與醫令，檔案較大）

注意事項
--------
1. 這份檔案的資料快照日期是 {built}，之後健保署若修訂規定，
   這個檔案不會自動更新。請定期向提供者索取新版。
2. 給付規定一律以中央健康保險署最新公告為準。
   本檔為非官方參考工具，申報結果由使用者自行負責。
3. 頁面上的「事前審查」「限專科」等標籤為程式自動抽取，以條文原文為準。
4. 你在這個檔案裡寫的臨床註記存在這台電腦的瀏覽器裡，
   換一台電腦或換一個瀏覽器就看不到，重要內容請自行備份。
5. 手機瀏覽器開這種大檔案可能會當掉，手機請用線上版。

資料來源
--------
衛生福利部中央健康保險署、食品藥物管理署開放資料
（政府資料開放授權條款第 1 版）
資料快照：{built}
指紋：{fp}
製作：M116 RickyYu

若無法開啟，請回報下列資訊：
  作業系統版本、瀏覽器名稱與版本、雙擊後看到的畫面
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["derm", "all", "both"], default="both")
    ap.add_argument("--zip", action="store_true", default=True)
    args = ap.parse_args()

    if not (DIST / "index.html").exists():
        raise SystemExit("❌ 找不到 dist-offline，請先執行：pnpm exec vite build --mode offline")

    OUT.mkdir(exist_ok=True)
    scopes = ["derm", "all"] if args.scope == "both" else [args.scope]
    made: list[tuple[Path, str, dict]] = []

    for scope in scopes:
        payload, shas = collect(scope)
        html = build_html(payload, shas, scope)

        flags = [f for f in _AV_FLAGS if f in html]
        if flags:
            raise SystemExit(f"❌ 產物含防毒紅旗字樣 {flags}，拒絕輸出")

        # ★ script 逃逸驗證：內嵌資料區塊裡不得出現任何 `</`。
        #   資料是用 _embed() 跳脫過的，只要這裡命中就代表跳脫被繞過或被改掉，
        #   那會讓條文原文變成可執行的 HTML。
        head, _, rest = html.partition("window.__NHI_OFFLINE__=")
        data_block, _, _ = rest.partition(";window.__NHI_OFFLINE_META__=")
        if "</" in data_block or "<script" in data_block.lower():
            raise SystemExit("❌ 內嵌資料含未跳脫的 `</`，可能造成 script 逃逸，拒絕輸出")

        # ★ 檔名一律純 ASCII：中文檔名在舊版 Windows 解壓縮會變亂碼
        name = f"nhi-{'derm' if scope == 'derm' else 'full'}-offline-{TODAY.replace('-', '')}.html"
        p = OUT / name
        p.write_text(html, encoding="utf-8")
        made.append((p, scope, shas))
        print(f"✅ {name}  {p.stat().st_size/1e6:.1f} MB  ({len(payload)} 個資料檔)")

    meta = json.loads((PUBLIC / "meta.json").read_text(encoding="utf-8"))
    # ★ 用 public/data 全域指紋，不用「本次內嵌檔案」的指紋：
    #   後者只涵蓋皮膚科版帶到的檔，線上版改了沒帶到的檔就抓不出來。
    fp = data_fingerprint(PUBLIC)
    if meta.get("data_fingerprint") not in (None, fp):
        raise SystemExit(
            f"❌ public/data 指紋 {fp} 與 meta.json 記載的 "
            f"{meta['data_fingerprint']} 不符 —— public/data 在 build 之後被改過，"
            "請重跑 make rebuild 再產離線包")
    readme = READMEBODY = README.format(d=TODAY.replace("-", ""), built=meta["built"], fp=fp)
    # Windows 記事本要 BOM + CRLF 才不會變亂碼與擠成一行
    (OUT / "READ-ME-FIRST.txt").write_bytes(
        b"\xef\xbb\xbf" + readme.replace("\n", "\r\n").encode("utf-8"))

    if args.zip:
        zp = OUT / f"nhi-offline-{TODAY.replace('-', '')}.zip"
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for p, _s, _sh in made:
                z.write(p, p.name)
            z.write(OUT / "READ-ME-FIRST.txt", "READ-ME-FIRST.txt")
        print(f"📦 {zp.name}  {zp.stat().st_size/1e6:.1f} MB")

        # ★ 清掉舊日期的產物。
        #   這個資料夾的用途是「打開它、把檔案拖到隨身碟」。留著上個月的
        #   nhi-offline-20260801.zip，就有機會把過期條文帶進醫院的封閉電腦，
        #   而 check_offline.py 只驗 MANIFEST 記的那一份，看不到舊檔。
        #   只刪自己命名規則產生的檔，且日期不是今天的 —— 不碰其他任何東西。
        stamp = TODAY.replace("-", "")
        removed = 0
        for old in OUT.iterdir():
            if not old.is_file():
                continue
            if not re.fullmatch(rf"nhi-(derm|full)-offline-\d{{8}}\.html|nhi-offline-\d{{8}}\.zip",
                                old.name):
                continue
            if stamp in old.name:
                continue
            old.unlink()
            removed += 1
        if removed:
            print(f"🧹 清除 {removed} 個舊日期產物（避免誤拿過期版本）")

        (OUT / "MANIFEST.txt").write_text(
            f"packed_at: {TODAY}\ndata_built: {meta['built']}\nfingerprint: {fp}\n"
            f"app_fingerprint: {app_fingerprint(DIST)}\n"
            + "".join(f"{p.name}  {p.stat().st_size} bytes  {_sha(p.read_bytes())[:16]}\n"
                      for p, _s, _sh in made)
            + f"{zp.name}  {zp.stat().st_size} bytes\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
