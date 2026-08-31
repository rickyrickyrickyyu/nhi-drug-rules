"""下載工具：串流、退避、禮貌 UA。

刻意只用 stdlib urllib —— 全案不需要為了下載檔案動到共用 venv 的依賴。
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import USER_AGENT  # noqa: E402


def download(url: str, dest: Path, *, retries: int = 4, timeout: int = 300) -> int:
    """串流下載到 dest，回傳位元組數。失敗會指數退避重試，最後仍失敗則丟例外。

    先寫 .part 再 rename：中斷的半個檔案絕不能被下游當成完整資料使用。
    """
    tmp = dest.with_suffix(dest.suffix + ".part")
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as r, tmp.open("wb") as f:
                total = 0
                while chunk := r.read(1 << 20):
                    f.write(chunk)
                    total += len(chunk)
            tmp.replace(dest)
            return total
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            last = e
            tmp.unlink(missing_ok=True)
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"下載失敗 {url}: {last}")
