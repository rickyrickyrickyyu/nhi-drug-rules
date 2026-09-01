#!/usr/bin/env python3
"""本機靜態伺服器：把已建置的 dist/ 服務出來。

用法：
    python3 bin/serve.py [--port 5183] [--dir dist] [--prefix /nhi-drug-rules/]

為什麼不用 `pnpm dev`：門診場景要的是「秒開、不需 node_modules、不重編譯」。
dist/ 已經是建置好的產物，用 stdlib 的 http.server 起來只要幾十毫秒。

為什麼要 prefix：vite.config.js 的 base 是 '/nhi-drug-rules/'（GitHub Pages 子路徑），
在這裡把前綴 strip 掉再對映到 dist/，就不必為了本機而改 base。

★ 這支只是本機預覽伺服器（HTTP/1.0 + Cache-Control: no-store），
  瀏覽器在它上面**註冊不了 Service Worker** —— 這是刻意可接受的：
  本機頁面本來就該永遠讀最新的 dist/，不需要離線快取。
  線上版（GitHub Pages）的 SW 正常運作。
"""

from __future__ import annotations

import argparse
import functools
import http.server
import socket
import sys
from pathlib import Path


class PrefixHandler(http.server.SimpleHTTPRequestHandler):
    prefix = "/"

    def translate_path(self, path: str) -> str:
        if self.prefix != "/" and path.startswith(self.prefix):
            path = "/" + path[len(self.prefix):]
        return super().translate_path(path)

    def log_message(self, fmt: str, *args) -> None:      # 不要洗版
        pass

    def end_headers(self) -> None:
        # 資料每月更新，快取住舊條文比查不到更危險
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5183)
    ap.add_argument("--dir", default="dist")
    ap.add_argument("--prefix", default="/nhi-drug-rules/")
    args = ap.parse_args()

    root = Path(args.dir).resolve()
    if not (root / "index.html").exists():
        print(f"❌ 找不到 {root}/index.html，請先執行：make build", file=sys.stderr)
        return 1

    port = args.port
    for _ in range(6):                      # 5183–5188，比照既有 port 慣例
        if port_free(port):
            break
        port += 1
    else:
        print("❌ 5183–5188 都被佔用", file=sys.stderr)
        return 1

    PrefixHandler.prefix = args.prefix
    handler = functools.partial(PrefixHandler, directory=str(root))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        print(f"PORT={port}")             # 給 shell 讀
        sys.stdout.flush()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
