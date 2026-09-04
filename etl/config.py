"""全案共用路徑與常數。所有路徑相對 repo root，讓本機與 CI 跑同一份程式。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
BUILD = ROOT / "data" / "build"
STAGING = BUILD / ".staging"
CURATION = ROOT / "curation"
SNAPSHOTS = ROOT / "snapshots"
SNAP_PDF = SNAPSHOTS / "pdf"
SNAP_TEXT = SNAPSHOTS / "text"
SNAP_DIFF = SNAPSHOTS / "diff"
SNAP_APPX = SNAPSHOTS / "appendix"          # 官方獨立附表 PDF（本體不在章節 PDF 裡）
MANIFEST = SNAPSHOTS / "manifest.json"
APPX_MANIFEST = SNAPSHOTS / "appendix_manifest.json"
SOURCES = BUILD / "sources.json"        # 溯源登錄簿（promote 後複製到 public/data/）
PUBLIC = ROOT / "public" / "data"

NHI_DRUG_CSV = "https://info.nhi.gov.tw/api/iode0000s01/Dataset?rId=A21030000I-E41001-001"
TFDA_LICENCE = "https://data.fda.gov.tw/data/opendata/export/36/json"
# 仿單／外盒圖檔連結（許可證字號 → 官方仿單 URL）。zip 內含單一 json。
TFDA_INSERTS = "https://data.fda.gov.tw/data/opendata/export/39/json"
# 由許可證字號推導的仿單網址。實測對兩種開放資料形式都回 200。
TFDA_INSERT_URL = "https://mcp.fda.gov.tw/exportpdf/{}"
NHI_PROC_CSV = "https://info.nhi.gov.tw/api/iode0000s01/Dataset?rId=A21030000I-D20021-001"
PDF_URL = "https://info.nhi.gov.tw/api/INAE3000/INAE3000S01/getPDF?DurgFileName={}"

USER_AGENT = "nhi-drug-rules/1.0 (+https://github.com/rickyrickyrickyyu/nhi-drug-rules)"

# 健保 CSV 的欄位契約。官方改欄位是最可能的破壞來源，gate 要逐字比對。
CSV_COLUMNS = [
    "異動", "藥品代號", "藥品英文名稱", "藥品中文名稱", "成分", "規格量", "規格單位",
    "單複方", "支付價", "有效起日", "有效迄日", "藥商", "製造廠名稱", "劑型",
    "藥品分類", "分類分組名稱", "ATC代碼", "給付規定章節", "藥品代碼超連結", "給付規定章節連結",
]

# 醫療服務給付項目及支付標準（處置／診療項目）的欄位契約
PROC_CSV_COLUMNS = [
    "診療項目代碼", "健保支付點數", "生效起日", "生效迄日",
    "英文項目名稱", "中文項目名稱", "備註",
]

for _d in (RAW, BUILD, STAGING, SNAP_PDF, SNAP_TEXT, SNAP_DIFF, PUBLIC):
    _d.mkdir(parents=True, exist_ok=True)
