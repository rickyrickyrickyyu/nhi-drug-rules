"""向健保署官方查詢 API 問出章節 PDF 的「當下真實檔名」。

★ 為什麼需要這支模組：
  改版偵測靠的是開放資料主檔「給付規定章節連結」裡的檔名。但那份 CSV 是
  月更快照，而健保署換章節 PDF 時會**同時把舊檔從伺服器下架** —— 空窗期內
  照 CSV 給的連結去抓，一律回 HTTP 400，而且是「檔案不存在」的 400，
  不是暫時性錯誤，重試幾次都一樣。

  實測 2026-09-20：2.6.1.（降血脂）與 2.6.3. 都已換成 _20260901 版，
  CSV 卻仍指向 2.6.1._20210329.pdf／2.6.3._20231201.pdf，兩個檔都已 404 化。
  這正是 curation/pending_updates.yaml 等了一個月的那次改版。

  官方查詢頁（INAE3000S01）自己用的 SQL0001 回傳 druG_UFILE_NAME_LIST，
  那是資料庫當下的值，永遠與 getPDF 能抓到的檔一致。所以只要 CSV 的檔名
  抓失敗，就改問這支 API 要現行檔名 —— 不猜檔名、不改日期，只問官方。

刻意只在「CSV 檔名抓不到」時才呼叫：正常情況一次都不會打這支 API。
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import USER_AGENT  # noqa: E402

from .section import normalize_code, parse_pdf_filename  # noqa: E402

API = "https://info.nhi.gov.tw/api/INAE3000/INAE3000S01/SQL0001"
REFERER = "https://info.nhi.gov.tw/INAE3000/INAE3000S02"

# SQL0001 要求整組欄位都在，缺欄會被 model binding 擋成 400
_BLANK = {
    "DRUG_CODE": "", "DRUG_NAME": "", "DRUG_DOSE": "", "DRUG_CLASSIFY_NAME": "",
    "DRUG_ING": "", "DRUG_ING_QTY": "", "DRUG_ING_UNIT": "", "DRUG_STD_QTY": "",
    "DRUG_STD_UNIT": "", "DRUGGIST_NAME": "", "MIXTURE": "", "PAY_START_DATE_YEAR": "",
    "PAY_START_DATE_MON": "", "ORAL_TYPE": "", "ATC_CODE": "", "SHOWTYPE": "",
}


def _query(drug_code: str, *, timeout: int = 60) -> list[dict]:
    body = json.dumps({**_BLANK, "DRUG_CODE": drug_code, "CURPAGE": 1, "PAGESIZE": 20}).encode()
    req = urllib.request.Request(
        API, data=body,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT,
                 "Referer": REFERER})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8")).get("data") or []


def live_chapter_files(drug_code: str) -> dict[str, tuple[str, str]]:
    """查一支藥，回傳它所引用章節的現行 {章節碼: (檔名, 生效日ISO)}。

    druG_UFILE_NAME_LIST 是逗號分隔，無檔案的位置是 'X'。同一節可能出現
    兩個不同生效日的檔（官方保留舊版連結），一律取生效日較新的那個
    —— 與 fetch_rule_pdfs.collect_targets 對 CSV 的取法一致。
    """
    out: dict[str, tuple[str, str]] = {}
    for row in _query(drug_code):
        for fn in (row.get("druG_UFILE_NAME_LIST") or "").split(","):
            fn = fn.strip()
            if not fn or fn == "X":
                continue
            parsed = parse_pdf_filename(fn)
            if not parsed:
                continue                      # 檔名不合格式就不要猜，交給呼叫端 fail
            code, iso, _seq = parsed
            prev = out.get(code)
            if prev is None or iso > prev[1]:
                out[code] = (fn, iso)
    return out


def all_chapter_files(drug_codes: list[str], *, workers: int = 4,
                      on_error=None) -> dict[str, tuple[str, str]]:
    """一次問出多支藥涵蓋的所有章節現行檔名，合併成 {章節碼: (檔名, 生效日)}。

    呼叫端負責挑出「最少幾支藥就能蓋住全部章節」（集合覆蓋，實測 534 節約 484 支）。
    併發刻意壓在 4 —— 官方站台沒有公開的速率限制，這是對外部服務的基本禮貌，
    全量跑完約 1.5 分鐘，對一個月跑一次的管線完全可接受。
    """
    from concurrent.futures import ThreadPoolExecutor

    out: dict[str, tuple[str, str]] = {}

    def one(code: str) -> dict[str, tuple[str, str]]:
        try:
            return live_chapter_files(code)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                OSError, json.JSONDecodeError) as e:
            if on_error:
                on_error(code, e)
            return {}

    with ThreadPoolExecutor(workers) as ex:
        for part in ex.map(one, drug_codes):
            for code, (fn, iso) in part.items():
                prev = out.get(code)
                if prev is None or iso > prev[1]:
                    out[code] = (fn, iso)
    return out


def resolve(section_code: str, drug_code: str | None) -> tuple[str, str] | None:
    """問出某章節的現行 (檔名, 生效日)。問不到回 None，呼叫端沿用原本的失敗處理。

    API 掛掉不該讓整條管線爆掉 —— 它只是「救援路徑」，本來就是額外的。
    """
    if not drug_code:
        return None
    try:
        files = live_chapter_files(drug_code)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            OSError, json.JSONDecodeError):
        return None
    return files.get(normalize_code(section_code))
