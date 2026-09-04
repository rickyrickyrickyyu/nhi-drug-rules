#!/usr/bin/env python3
"""健保藥品主檔 → 正規化的 products / ingredients。

用法：
    python3 etl/normalize_drugs.py

輸出（寫進 data/build/.staging/，gate 全綠才由 promote.py 搬到正式位置）：
    products.json      每個藥品代號一筆，含三態 status 與價格歷史
    ingredients.json   每個學名一筆，含 route 分組、商品名、章節
    normalize_report.json  給 validate.py 用的統計
"""

from __future__ import annotations

import collections
import csv
import html
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import CSV_COLUMNS, RAW, STAGING  # noqa: E402
from lib import brand, inn, route as route_lib, section, tfda  # noqa: E402
from lib.roc import roc_to_iso  # noqa: E402

csv.field_size_limit(1 << 24)
TODAY = date.today().isoformat()


def _repair(nhi_name: str, tfda_name: str | None) -> tuple[str, bool]:
    """修復掉字的品名。回傳 (品名, 是否修復過)。

    健保檔的 '?' 在原始 UTF-8 位元組就是 0x3F —— 是健保署資料庫掉的字，
    不是我們的解碼問題。多數是 ®（HALDOL? → HALDOL®），少數是罕用漢字
    （"五洲"嘴? → "五洲"嘴疱）。食藥署許可證有完整字串，優先用它補。
    """
    # 健保檔另有 18 筆的品名夾著未解碼的 HTML 實體
    # （'媚姿雅&reg;膠囊' 與 '&#31185;&#25035;'＝科懋）。unescape 對一般字串無害。
    name = html.unescape((nhi_name or "").strip())
    changed = name != (nhi_name or "").strip()
    if not tfda.has_mojibake(name):
        return name, changed
    cand = html.unescape((tfda_name or "").strip())
    if cand and not tfda.has_mojibake(cand):
        return cand, True
    # TFDA 也缺：只在問號緊接英數字時當成 ® 殘留移除，不臆測漢字
    fixed = re.sub(r"(?<=[A-Za-z0-9])\?(?=\s|$|[A-Za-z0-9])", "", name).strip()
    return (fixed, True) if fixed != name else (name, False)


def _read_rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        if r.fieldnames != CSV_COLUMNS:
            raise SystemExit(
                f"❌ CSV 欄位契約不符。\n預期: {CSV_COLUMNS}\n實際: {r.fieldnames}"
            )
        yield from r


def _price(v: str) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def resolve_status(rows: list[dict]) -> tuple[dict, dict | None, list[dict], str]:
    """從同一藥品代號的多列中選出現行列。

    ★ 這裡是最容易寫錯的地方。「取迄日=9991231」和「取最大起日」都是錯的：
      藥價調整公告後會出現「起日=未來日、迄日=9991231」的新價列，兩種天真
      規則都會選中尚未生效的價格；已停止給付的品項則一列 9991231 都沒有。
    回傳 (現行列, 未來列, 價格歷史, status)。
    """
    parsed = []
    for r in rows:
        start = roc_to_iso(r["有效起日"])
        end = roc_to_iso(r["有效迄日"])          # 9991231 → None（無限期）
        parsed.append((start, end, r))
    parsed.sort(key=lambda x: (x[0] or ""))

    current = next(
        (r for s, e, r in reversed(parsed) if s and s <= TODAY and (e is None or e >= TODAY)),
        None,
    )
    upcoming = next((r for s, e, r in parsed if s and s > TODAY), None)

    history = [
        {"from": s, "to": e, "price": _price(r["支付價"])}
        for s, e, r in parsed
        if r is not current
    ]

    if current is not None:
        status = "active"
    elif upcoming is not None:
        status = "upcoming"
    else:
        status = "delisted"
        current = parsed[-1][2] if parsed else None    # 顯示用，但 UI 會標已停止給付
    return current, upcoming, history, status


def main() -> int:
    src = RAW / "nhi_drug.csv"
    if not src.exists():
        raise SystemExit("❌ 找不到 data/raw/nhi_drug.csv，請先跑 fetch_nhi_drugs.py")

    # TFDA 索引：修中文名掉字 + 帶進仿單適應症。缺檔不中斷（TFDA 是加值層，
    # 沒有它健保給付規定本身仍可用），但會在報告裡標明。
    tfda_path = RAW / "tfda_licence.json"
    tfda_idx = tfda.build_index(tfda_path) if tfda_path.exists() else {}

    # 有官方仿單的許可證清單。缺檔不中斷 —— 沒有它只是不顯示仿單連結，
    # 給付規定本身不受影響。
    ins_path = RAW / "tfda_inserts.json"
    insert_lics = set(
        json.loads(ins_path.read_text(encoding="utf-8")).get("licences", [])
    ) if ins_path.exists() else set()
    if not tfda_idx:
        print("⚠️  找不到 TFDA 資料，將略過中文名修復與仿單適應症")

    by_code: dict[str, list[dict]] = collections.defaultdict(list)
    n_rows = 0
    for r in _read_rows(src):
        n_rows += 1
        by_code[r["藥品代號"]].append(r)
    print(f"📥 讀入 {n_rows:,} 列 / {len(by_code):,} 個藥品代號")

    products: dict[str, dict] = {}
    warn_counter: collections.Counter[str] = collections.Counter()
    status_counter: collections.Counter[str] = collections.Counter()
    route_src_counter: collections.Counter[str] = collections.Counter()

    for code, rows in by_code.items():
        cur, up, hist, status = resolve_status(rows)
        if cur is None:
            warn_counter["no_usable_row"] += 1
            continue
        status_counter[status] += 1

        parse = inn.normalize(cur["分類分組名稱"], cur["成分"], cur["單複方"], cur["ATC代碼"])
        for w in parse.warnings:
            warn_counter[w] += 1
        if not parse.keys:
            warn_counter["inn_unresolved"] += 1

        gform = route_lib.group_form_of(cur["分類分組名稱"])
        rt, rsrc = route_lib.derive(gform, cur["劑型"])
        route_src_counter[rsrc] += 1

        lic = ""
        url = cur["藥品代碼超連結"] or ""
        if "licId=" in url:
            lic = url.split("licId=")[-1].split("&")[0].strip()

        # ★ 中文名修復：健保檔 408 個品項的中文名含 ASCII '?'（多為 ® 被吃掉，
        #   少數是罕用字整個掉了）。'?' 在原始 UTF-8 檔裡就是 0x3F，不是我們的
        #   解碼問題，只能靠 TFDA 補。實測 100% 可修復。
        tf_rec = tfda.lookup(lic, tfda_idx) if lic else None
        tf_state = tfda.classify(tf_rec)

        # 中英文品名都會掉字（同一批資料、同一個成因：® 被吃成 ASCII '?'）。
        # 英文的 51 筆同樣先試 TFDA；TFDA 也壞掉時才把孤立的 '?' 當 ® 移除
        # —— 不猜測字元，只拿掉明顯是符號殘留的那個問號。
        name_zh, name_zh_repaired = _repair(cur["藥品中文名稱"], (tf_rec or {}).get("中文品名"))
        name_en, name_en_repaired = _repair(cur["藥品英文名稱"], (tf_rec or {}).get("英文品名"))
        if name_zh_repaired:
            warn_counter["name_zh_repaired"] += 1
        elif tfda.has_mojibake(name_zh):
            warn_counter["name_zh_mojibake_unfixed"] += 1
        if name_en_repaired:
            warn_counter["name_en_repaired"] += 1
        if tf_state == "miss" and lic:
            warn_counter["tfda_join_miss"] += 1
        elif tf_state == "stale":
            warn_counter["tfda_licence_stale"] += 1

        stem_zh, mojibake = brand.stem_zh(name_zh)

        products[code] = {
            "code": code,
            "name_en": name_en,
            "name_zh": name_zh,
            "name_zh_raw": cur["藥品中文名稱"],
            "name_zh_repaired": name_zh_repaired,
            "brand_stem_en": brand.stem_en(name_en),
            "brand_stem_zh": stem_zh,
            "zh_mojibake": mojibake,
            "zh_alias": brand.zh_alias(cur["藥品中文名稱"]),
            "inn_keys": parse.keys,
            "combo_key": parse.combo_key,
            "is_combo": parse.is_combo,
            "inn_source": parse.source,
            "form": cur["劑型"],
            "group_form": gform,
            "route": rt,
            "route_source": rsrc,
            "atc": (cur["ATC代碼"] or "").strip(),
            "drug_class": cur["藥品分類"],
            "is_originator": cur["藥品分類"] in ("研發廠", "生物製劑", "生物相似性藥品"),
            "vendor": cur["藥商"],
            "status": status,
            "price": _price(cur["支付價"]),
            "price_next": _price(up["支付價"]) if up else None,
            "price_next_from": roc_to_iso(up["有效起日"]) if up else None,
            "valid_from": roc_to_iso(cur["有效起日"]),
            "valid_to": roc_to_iso(cur["有效迄日"]),
            "sections": section.split_pay_codes(cur["給付規定章節"]),
            "section_files": section.split_pay_urls(cur["給付規定章節連結"]),
            "licence_id": lic,
            "licence_no": (tf_rec or {}).get("許可證字號", ""),
            "licence_state": tf_state,
            # 這張許可證在食藥署有官方仿單。只存布林值，網址由許可證字號推導
            # （見 config.TFDA_INSERT_URL）—— 逐筆存 URL 會讓離線包多 1.6 MB。
            "has_insert": ((tf_rec or {}).get("許可證字號", "") in insert_lics),
            "indication": (tf_rec or {}).get("適應症", "") or "",
            "tfda_form": (tf_rec or {}).get("劑型", "") or "",
            "price_history": hist,
        }

    out = STAGING / "products.json"
    out.write_text(json.dumps(products, ensure_ascii=False), encoding="utf-8")

    report = {
        "generated_at": TODAY,
        "n_rows": n_rows,
        "n_codes": len(by_code),
        "n_products": len(products),
        "status": dict(status_counter),
        "route_source": dict(route_src_counter),
        "warnings": dict(warn_counter),
        "n_route_other": sum(1 for p in products.values() if p["route"] == "OTHER"),
        "n_insert": sum(1 for p in products.values() if p.get("has_insert")),
        "n_tfda_active": sum(1 for p in products.values() if p["licence_state"] == "active"),
        "n_tfda_stale": sum(1 for p in products.values() if p["licence_state"] == "stale"),
        "n_tfda_miss": sum(1 for p in products.values() if p["licence_state"] == "miss"),
        "n_indication": sum(1 for p in products.values() if p["indication"]),
        "n_inn_unresolved": sum(1 for p in products.values() if not p["inn_keys"]),
    }
    (STAGING / "normalize_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"✅ products.json  {len(products):,} 筆 ({out.stat().st_size/1e6:.1f} MB)")
    print(f"   狀態      {dict(status_counter)}")
    print(f"   route 來源 {dict(route_src_counter)}")
    print(f"   route=OTHER {report['n_route_other']:,} ({report['n_route_other']/len(products):.2%})")
    print(f"   INN 未解析  {report['n_inn_unresolved']:,} ({report['n_inn_unresolved']/len(products):.2%})")
    print(f"   TFDA      有效 {report['n_tfda_active']:,}｜已註銷 {report['n_tfda_stale']:,}｜"
          f"未命中 {report['n_tfda_miss']:,}｜有適應症 {report['n_indication']:,}")
    print(f"   警告      {dict(warn_counter)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
