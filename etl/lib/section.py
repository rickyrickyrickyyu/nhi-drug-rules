"""給付規定章節碼處理。

★ 這個模組存在的唯一理由：章節碼的尾點有兩種互斥的處理方式，
  混用會產生極難發現的靜默誤配。所以禁止在別處自己寫字串比對。

  match_prefix()  — 保留尾點，用於「這個章節屬不屬於某個前綴」的標籤判斷
                     "8.2.16.".startswith("8.2.1.")  → False  ✅ 正確
                     "8.2.16".startswith("8.2.1")    → True   ❌ 會把 apremilast 誤收進 cyclosporin
  same_code()     — 去尾點，只用於「PDF 首行是不是這個章節」的比對
                     實測 13.3.3 的 PDF 首行寫「13.3.3 與tazarotene…」碼後無點
"""

from __future__ import annotations

import re

_RE_CODE = re.compile(r"^\d+(?:\.\d+)*\.?$")
_RE_PDF_NAME = re.compile(r"^(?P<code>[\d.]+?)_(?P<date>\d{8})(?:_(?P<seq>\d{3}))?\.pdf$")


def normalize_code(code: str) -> str:
    """一律補上尾點作為內部標準形式。'13.17.1' → '13.17.1.'"""
    c = (code or "").strip()
    if not c:
        return ""
    return c if c.endswith(".") else c + "."


def match_prefix(code: str, prefix: str) -> bool:
    """章節碼是否落在某個前綴底下（含前綴本身）。兩邊都補尾點才比。"""
    return normalize_code(code).startswith(normalize_code(prefix))


def same_code(a: str, b: str) -> bool:
    """兩個章節碼是否指同一節，忽略尾點差異。只給 PDF 首行檢查用。"""
    return (a or "").strip().rstrip(".") == (b or "").strip().rstrip(".")


def code_tuple(code: str) -> tuple[int, ...]:
    """排序鍵。字串排序會把 13.10. 排在 13.2. 前面，所以一律轉成數字 tuple。"""
    parts = normalize_code(code).rstrip(".").split(".")
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return (9999,)


def parent_code(code: str) -> str | None:
    parts = normalize_code(code).rstrip(".").split(".")
    return normalize_code(".".join(parts[:-1])) if len(parts) > 1 else None


def chapter_no(code: str) -> int:
    return code_tuple(code)[0]


def slug(code: str) -> str:
    """'13.17.1.' → '13-17-1'。尾點在檔名與 URL 都會出事。"""
    return normalize_code(code).rstrip(".").replace(".", "-")


def parse_pdf_filename(filename: str) -> tuple[str, str, str | None] | None:
    """'13.17.1._20260601.pdf' → ('13.17.1.', '2026-06-01', None)

    有些檔名帶 _000 序號後綴，同節可能同時出現有/無後綴兩種 URL。
    回傳 None 代表檔名不合預期格式 —— 呼叫端要當成 fail，不要猜。
    """
    m = _RE_PDF_NAME.match(filename.strip())
    if not m:
        return None
    from .roc import roc_to_iso

    iso = roc_to_iso(m.group("date"))
    if not iso:
        return None
    return normalize_code(m.group("code")), iso, m.group("seq")


def split_pay_codes(raw: str) -> list[str]:
    """`給付規定章節` 是逗號分隔多值：'13.17.,13.17.1.,6.2.9.'"""
    out = []
    for c in (raw or "").split(","):
        c = c.strip()
        if c and _RE_CODE.match(c):
            out.append(normalize_code(c))
    return out


def split_pay_urls(raw: str) -> dict[str, tuple[str, str]]:
    """`給付規定章節連結` → {章節碼: (檔名, 生效日ISO)}

    同節出現多筆（有/無 _000 後綴）時，以 seq 較大者優先。
    """
    out: dict[str, tuple[str, str, str]] = {}
    for url in (raw or "").split(","):
        url = url.strip()
        if "DurgFileName=" not in url:
            continue
        fn = url.split("DurgFileName=")[-1]
        parsed = parse_pdf_filename(fn)
        if not parsed:
            continue
        code, iso, seq = parsed
        seq = seq or ""
        prev = out.get(code)
        if prev is None or seq > prev[2]:
            out[code] = (fn, iso, seq)
    return {k: (v[0], v[1]) for k, v in out.items()}


PDF_URL = "https://info.nhi.gov.tw/api/INAE3000/INAE3000S01/getPDF?DurgFileName={}"
