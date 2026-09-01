# 皮膚科健保給付規定查詢

> **給接手的 AI／工程師**，照這個順序讀：
> [30 秒定位](#給接手者30-秒定位) →
> [更新資料（三個版本怎麼同步）](#更新資料) →
> [架構](#架構) →
> [**踩過的坑**](#踩過的坑不要再踩一次) →
> [驗證清單](#驗證清單) →
> [安全與隱私](#安全與隱私)。
>
> 「踩過的坑」那一節記的都是**實測打臉過的結論**，不是推測。
> 憑常識重寫任何一條，都會原地踩回去。改完務必跑完[驗證清單](#驗證清單)。

以**學名**為入口查詢台灣健保藥品給付規定，並依**劑型**分流對應的給付章節。

同一個學名的不同劑型往往適用**完全不同的給付規定**，這是本專案存在的理由：

| 學名 | 口服 | 外用 | 注射 | 眼用 |
|---|---|---|---|---|
| Aciclovir | `10.7.1.1.` | `10.7.1.2.` | `10.7.1.1.` | `14.2.` |
| Itraconazole | `10.6.3.1.` | — | `10.6.3.2.` | — |
| Fluconazole | `10.6.1.1.` | — | `10.6.1.2.` | — |

搜尋支援英文學名、英美拼法別名、中英文商品名、中文俗稱、章節碼、ATC 碼與藥品代號，
結果列會標明是「透過哪個欄位」命中。

## 資料規模

- 45,179 個健保藥品品項 / 2,521 個學名（皮膚科標籤 443 個）
- 538 個給付規定章節（534 個有條文 PDF，4 個為純分類節點）
- 6,173 個醫療處置醫令（皮膚科標籤 23 個）
- 71 張從 PDF 還原的表格（55 張已就地嵌回條文）
- 59 個學名有健保條文所載劑量、547 個有仿單登載用法用量
- 首載 gzip 約 88 KB（皮膚科子集），全庫懶載約 437 KB

### 給接手者：30 秒定位

| 想改什麼 | 檔案 |
|---|---|
| 加／改一個處理步驟 | `bin/pipeline.sh`（**唯一**的步驟清單，Makefile 與一鍵更新都呼叫它） |
| 加驗證閘門 | `etl/validate.py`（fail-closed，沒過就不 promote） |
| PDF 表格還原 | `etl/lib/pdftable.py`（抽表）＋ `etl/lib/tablesplice.py`（嵌回條文） |
| 表單填空欄位被拆行 | `etl/lib/formlines.py` |
| 人工判斷（皮膚科標籤、酯基、同義詞） | `curation/*.yaml`（pipeline 只讀不寫） |
| 搜尋排序 | `src/lib/search.js` ＋ `cli/query.py`（**兩份實作**，靠 `tests/search_parity.*` 綁在一起） |
| 前端條文顯示 | `src/components/RuleSectionPanel.jsx` |

**權威資料只有一份**：`public/data/`。`dist/`（本機網頁）與 `offline/`（離線包）
都是它的衍生物，三者用 `data_fingerprint` 綁在一起（見下節）。


## 使用

```bash
pnpm install
make rebuild     # 用既有 data/raw 重建（不重新下載）
pnpm dev
```

### 終端機查詢（`nhi`）

`~/Developer/local_LLM/bin/nhi`（setup.sh 會 symlink 到 `~/.local/bin/nhi`）。
門診當下開瀏覽器太慢，打一行就有答案：

```bash
nhi dupilumab              # 學名
nhi Valtrex                # 商品名（中英皆可）
nhi 口服A酸                 # 中文俗稱
nhi 13.4                   # 章節碼直查
nhi aciclovir --route TOP  # 只看外用劑型
nhi dupilumab --full       # 完整條文（預設前 6 行）
nhi metformin --all        # 搜全庫

nhi status    # 資料快照日期與規模（超過 45 天會提醒）
nhi changes   # 本期給付規定異動
nhi verify    # 逐藥比對條文原文 + 搜尋命中測試
nhi update    # 一鍵更新（本機 dist + 線上 GitHub + 離線包，三者一起）
nhi offline   # 只重產離線包並用 Finder 開啟 offline/（方便拖到隨身碟）
nhi web       # 起本機開發站    nhi open  開線上版

nhi -q <關鍵字>   # 強制查詢模式（避免 update/status/web 等字被當成子指令）
```

CLI 與網頁版讀同一份 `public/data/`，不會有兩套事實。
repo 路徑可用 `NHI_RULES_DIR` 環境變數覆寫。

### 更新資料

**一鍵更新（雙擊即可）**

```
bin/更新健保資料.command          增量：只抓檔名生效日有變的章節
bin/更新健保資料.command --full   完整：重抓全部 534 份 PDF 比對 sha256，抓「靜默改檔」
```

命令列等價：`make refresh` / `bash bin/pipeline.sh fetch --force`。

自動排程：**每月 6 日**增量更新；**每年 1 月與 7 月**完整重抓校驗。
資料超過 45 天未更新時，網站會主動顯示過期警告。

#### 一次更新會動到哪三個版本

| 版本 | 位置 | 由哪一步產生 |
|---|---|---|
| **本機網頁** | `dist/`（`nhi` 開的那個） | pipeline 第 13 步 `pnpm build` |
| **線上網頁** | GitHub Pages | `.command` 推 commit → Actions 建置部署 |
| **離線包** | `offline/*.html` + `.zip` | pipeline 第 14 步 |

三者都從同一份 `public/data/` 衍生，用 **`data_fingerprint`**（`public/data/**.json`
內容雜湊，排除 `meta.json` 自身）綁在一起：

- `etl/check_offline.py` — 離線包的資料指紋與前端指紋都要對得上，否則 exit 1
- `nhi` 啟動前檢查 `dist/data/meta.json` 的指紋，不符就拒絕開站
- `.command` 推送後輪詢線上 `meta.json`，指紋一致才回報「網頁版已更新」

> ★ **為什麼是指紋不是日期**：`built` 只到「日」。同一天內重跑 ETL（改 curation、
> 修 parser）資料已經不同但日期一樣，比日期會放行過期的 dist／離線包，
> 也會在網站還沒部署好時就回報成功。這個坑踩過三次，三處都已改成比指紋。

#### 步驟清單（`bin/pipeline.sh`）

`fetch` 模式 19 步、`rebuild` 模式 14 步（跳過前 5 個下載步驟）。

```
下載（只有 fetch 模式跑）
  fetch_nhi_drugs.py       健保藥品主檔 CSV（96 MB）
  fetch_tfda.py            食藥署許可證 JSON（79 MB）        [soft：失敗只警告，沿用舊資料]
  fetch_procedures.py      醫療服務給付項目 CSV（處置醫令）
  fetch_proc_chapters.py   處置的支付標準章節定位（官方 API，124 頁）  [soft]
  fetch_rule_pdfs.py       章節 PDF（檔名生效日有變才下載；--force 全抓）

建置（兩種模式都跑）
   1  normalize_drugs.py       學名／劑型／途徑／商品名正規化
   2  normalize_procedures.py  處置醫令 + 皮膚科標籤 + 同義詞
   3  build_tables.py          從 PDF 還原表格 + 視覺行 sidecar
   4  parse_rules.py           條文切塊、旗標、附表定位、表格嵌回、視覺行還原
   5  tag_derm.py              皮膚科標籤
   6  dosing.py                健保條文所載劑量（direct / section_sole / prerequisite）
   7  dose_tfda.py             仿單登載用法用量（按許可證分組）
   8  mentions.py              藥名提及索引
   9  diff_rules.py            條文異動 diff（偵測靜默改檔）
  10  build_site_data.py       前端靜態分片
  11  validate.py              ✋ 30 道閘門，fail-closed（沒過 → exit 2）
  12  promote.py               原子搬移 .staging → public/data
  13  pnpm build               重建 dist/（本機網頁）
  14  build_offline.py         離線包 + check_offline.py 驗指紋（失敗 → exit 3）
```

失敗語意：`exit 2` = 閘門擋下（三個版本全維持前一版，不會出現半套資料）；
`exit 3` = 資料好了但離線包沒出（跑 `nhi offline` 單獨補）。

#### 換一台電腦要做什麼

```bash
git clone <repo> ~/Developer/小工具專區/nhi-drug-rules
cd ~/Developer/小工具專區/nhi-drug-rules
pnpm install
cd ~/Developer/vibe-coding && uv sync        # Python 環境（pymupdf、pyyaml）
cd -
make refresh                                  # 重抓全部資料並重建三個版本
```

`snapshots/`（條文 PDF 與文字快照）**有進 git**，所以 clone 下來就有歷史；
`data/raw/`（原始 CSV／JSON，共約 180 MB）沒進 git，`make refresh` 會重抓。
`offline/*.html` 與 `*.zip` 也沒進 git（每月 15–19 MB），只有 `MANIFEST.txt`
進版控，用來回溯「某月帶出去的是哪一版」。

`nhi` 指令在 `~/Developer/local_LLM/bin/nhi`，跑 `local_LLM/setup.sh` 會
symlink 到 `~/.local/bin/`。repo 路徑可用 `NHI_RULES_DIR` 覆寫。

## 架構

```
bin/            一鍵更新入口 + pipeline.sh（步驟的唯一事實來源）+ serve.py
etl/            Python pipeline（跑在 ~/Developer/vibe-coding/.venv）
  lib/          共用模組：pdftable(抽表) tablesplice(嵌回) formlines(視覺行)
                fingerprint(指紋) section(章節碼) inn/brand/route(正規化) prov(溯源)
curation/       人工維護層，pipeline 只讀不寫（皮膚科標籤、酯基白名單、處置同義詞）
snapshots/      條文快照 pdf/ + text/（★ 進 git：健保署換檔後就拿不回舊版，
                這是唯一 provenance，也是 diff 偵測「靜默改檔」的基準）
data/raw/       上游原始檔（★ 不進 git，約 180 MB，make refresh 會重抓）
data/build/     .staging（未通過閘門的產物）+ tables（表格 sidecar）+ sources.json
public/data/    ★ 權威資料。前端靜態分片，dist/ 與 offline/ 都是它的衍生物
src/            Vite + React 前端
cli/query.py    終端機查詢（與網頁讀同一份 public/data）
dist/           本機網頁（nhi 開的）        ← 衍生，不進 git
offline/        離線單檔 HTML + zip          ← 衍生，只有 MANIFEST.txt 進 git
```

資料流向是單向的，任何一步都不回寫上游：

```
data/raw ─→ data/build/.staging ─(30 道閘門)→ public/data ─┬→ dist/      本機
                                                            ├→ GitHub    線上
                                                            └→ offline/  離線
```

### 設計要點

- **酯基不可合併**：betamethasone valerate（Class III）與 dipropionate（Class I–II）
  效價差兩級，必須是兩張不同的卡片。`curation/ester_whitelist.yaml` 管這件事，
  `gate 14` 是保險。健保分組欄漏標酯基時，用 ATC 第 7 碼補回。
- **章節碼一律帶尾點比對**：`"8.2.16.".startswith("8.2.1.")` 是 `False`，
  去掉尾點就會把 apremilast 誤收進 cyclosporin 那條規則。見 `etl/lib/section.py`。
- **fail-closed**：所有產物先寫 `data/build/.staging/`，**30 個閘門**全綠才
  `promote.py` 原子搬移。閘門分四類：
  上游健檢（1–5、29）、正規化正確性（7、8、14、18、19）、
  臨床可用性（13 金絲雀藥物、30 處置金絲雀、16、17）、
  忠實度（20 表格無損、24 旗標有憑據、27／28 劑量歸屬、33 仿單原文、32／34 表格渲染）。
  `gate 13` 是唯一直接檢驗「這工具對皮膚科還有用嗎」的閘門。
- **零幻覺是靠選句而非生成**：劑量、適應症、處置備註全部輸出原文逐字，
  程式只做「哪一句是劑量」的選擇。`gate 27` / `gate 33` 逐條驗證輸出是原始欄位的
  子字串，只要有一條對不回去就整批擋下。
- **溯源封閉列舉**：`etl/lib/prov.py` 的 `SOURCE_KINDS` 只允許
  `http / pdf / curation / code / derived` 五種來源類型，登錄其他類型直接丟例外；
  每個下載來源都記 URL、取得時間、sha256 與大小到 `data/build/sources.json`，
  `gate 25` 確認上游都有登錄。這樣才答得出「這個數字是哪一版原始檔產生的」。
- **支付價 0 不是免費**：69% 的品項支付價為 0（多為已無流通的舊品項），UI 標「未列價」。
- **Service Worker 不快取資料**：給付規定每月改版，讓醫師看到上個月的條文比查不到更危險。
  `data/*.json` 走 NetworkFirst，每頁常駐顯示資料快照日期。

## 踩過的坑（不要再踩一次）

每一條都是**實測打臉過**的結論，不是推測。憑常識重寫會原地踩回去。

### PDF 表格

- **`find_tables()` 對這批 PDF 是有效的。** 我曾誤判「回傳 0 張表」而自建座標
  重建器 —— 那是因為測在 13.17.1.（本來就沒表格）。這些 PDF **有繪製框線**，
  `strategy='lines_strict'` / `'lines'` 兩種都跑、評分取最佳。
- **`strategy='text'` 絕對不能用**：不看框線、純靠文字位置猜欄位，會把散文切成
  假表格還切在字中間（實測 8.2.16. 被切出「(2)M」「ethotrexate」）。
- **儲存格要做 NFC**。健保 PDF 有 CJK 相容表意文字（U+F900–FAFF），`度` vs `度`
  看起來一樣但碼位不同。表格那側不做 NFC 就永遠對不回條文 —— 曾經 10 張表 0 張能定位。
- **同頁多表要按閱讀順序 `(y0, x0)` 排**。`sorted(dict.items())` 是拿 bbox 元組排，
  等於先比 x0，上下兩張表會顛倒，單向游標就會錯過前一張。
- **驗證門檻別憑感覺定**。原值（欄 ≤16 / 密度 ≥0.25 / 格 ≤400 字 / 列 ≥2）
  擋掉了 21 張**真表格**：申請書有 21–29 欄、空白表單密度天生只有 0.11–0.22、
  修訂對照表把整條規則塞在一格（488 字）、跨頁表格的續頁只有 1 列。
  現值：欄 ≤32 / 密度 ≥0.10 / 格 ≤1500 字 / 列 ≥1。
- **不是所有碎片都是表格**。13.4. isotretinoin 同意書的
  「病歷號碼：__ 茲證明本人__ 年齡__ 出生日期__年__月__日」在 PDF 上是同一行
  （y=151.8），但底線是**矩形不是文字**，pymupdf 因此切成 6 個 line 物件。
  `find_tables` 對這種永遠無解 —— 那裡沒有格子，只有底線。
  解法是 `etl/lib/formlines.py`：記錄「同一視覺行」，在 clause 層接回。

### 表格嵌回條文（`tablesplice.py`）

- **安全性靠「夾雜文字必須是表格內容」，不靠比對順序。** 所以可以容許 10% 的
  儲存格對不上（`find_tables` 併格會產生 PDF 線性文字裡不存在的字串）。
- **候選錨點要挑「夾雜最少」的，不是第一個成功的。** 13.17.2. 嚴重度表的首格是
  「嚴重度」，而前面的標題句「異位性皮膚炎嚴重度（Severity）：」也含這三個字，
  從標題起算同樣能依序找完所有格，但會把標題一起吃掉。
- **驗無損要比字元多重集合，不能用 difflib。** 表格是列優先、原文是版面順序，
  difflib 會把「順序不同」誤報成「內容遺失」。
- **`gate 34` 鎖住碎片白名單**：`9.41.`（官印欄直書）、`1.6.2.2.`（評估表標題直書）、
  `8.2.4.11.`（是／否勾選欄跨欄合併）。這三個 PDF 本身沒有可還原的結構。
  白名單以外出現新的碎片章節就 fail。

### 前端 / PWA

- **`index.html` 不可以進 precache。** 它是唯一指向「哪一版 bundle」的入口，
  precache 之後新版部署，使用者第一次打開拿到的是舊 HTML → 舊 JS → 舊畫面，
  而且畫面上毫無線索。曾因此以為部署失敗（實際 CI 全綠、線上資料全新）。
  `navigateFallback` 預設也會拿 precache 的 index.html 回應導覽，要一併設 `null`，
  導覽改走 NetworkFirst。
- **驗線上一定要用瀏覽器開畫面**，只 curl API 會被騙過去 —— 資料是新的、畫面是舊的。
- **內嵌到離線包的 `<script>` 必須放 `</body>` 之前。** Vite 產的是
  `type="module"`（延後到 DOM 解析完才執行），內嵌成傳統 script 後變成立即執行，
  那時 `#root` 還不存在，React 丟 Minified error #299，整頁空白。
- **`body { overflow-wrap: anywhere }` 會切斷 `LDL-C≧70mg/dL`。**
  `table td, th` 要另外設 `overflow-wrap: normal; word-break: keep-all`。
- **`make verify` 必須跑線上版與離線版兩種 build。** offline mode 會關掉 PWA，
  只跑 offline 等於沒驗到 workbox 設定（曾因此本機全綠、CI 紅燈）。

### 外部連結與資料來源

- **別自己編官方網址。** `lmspiq.fda.gov.tw/.../DRPIQ1000Result?licId=` 曾經上線
  且是 **404** —— 真參數是 `licBaseId` 且吃內部 id（不是許可證字號，我們拿不到），
  查詢頁還有驗證碼。任何要寫進程式的官方 URL 都要先實測。
- **處置沒有逐項 PDF。** 健保署只對「藥品給付規定」發布逐節 PDF，
  「醫療服務給付項目」只有整份 `.doc` 壓縮檔。章節定位靠
  `fetch_proc_chapters.py` 打 INAE5001 API（`RDO_TYPE=2` 才是現行 6,173 筆，
  每頁上限硬鎖 50 → 124 頁）。1,276 筆是官方本身就沒填章節，不是抓漏。
- **食藥署開放資料的「用法用量」只覆蓋皮膚科 24%**（105/443），
  isotretinoin、dupilumab、MTX、cyclosporin 全是空的。判斷有無實質內容
  不能只看長度 —— 「(詳細敘述請參見仿單擬稿)。」有 14 個字。
- **仿單全文不鏡射。** 食藥署仿單平台明訂「未經同意不得以任何形式重製、轉載、引用」。
- **`www.nhi.gov.tw` 有 WAF 擋非瀏覽器**（curl 一律 403）。連結給人點沒問題，
  程式抓不到。

### 流程與架構

- **步驟清單只能有一份。** `bin/pipeline.sh` 是唯一事實來源。曾經 Makefile 與
  一鍵更新各維護一份而走鐘，導致一鍵更新**完全沒跑**處置、表格、劑量、提及索引
  四個步驟 —— 按了更新，藥品更新了但處置永遠停在上個月。
  同樣的分岔也發生在 `build_tables.py` 與 `fetch_rule_pdfs.py` 各寫一份 sidecar
  欄位清單，結果 `visual_lines` 只進了其中一支、表單還原完全沒生效。
- **`pnpm build` 不能省。** `nhi` 開的本機網頁服務的是 `dist/`，而 Vite 是在
  build 時才把 `public/data` 複製進去。少了這一步，線上與離線都更新了，
  只有本機網頁停在上一版 —— 三者中最難察覺的一個。
- **改抽字方式會讓 diff 炸掉。** `snapshots/text/*.txt` 是 `diff_rules.py` 逐月
  比對「官方有沒有偷改條文」的基準。動了 `extract_text()` 的輸出格式，
  下一次 refresh 會有 500+ 節誤報 `silent_edit`，把真正的法規變動淹沒。
  衍生資料（表格、視覺行）一律走 sidecar，不進 `snapshots/`。
- **搜尋權重是 JS／Python 雙實作**，靠 `tests/search_parity.*` 的 39 組查詢綁在
  一起。曾經 JS 的 `prefixOrSub()` 回傳 3/2/1 但呼叫端寫成 `s >= 2 ? X : Y`，
  把 exact 與 prefix 壓成同一級，9/10 查詢分數與 Python 不同。
- **處置的皮膚科標籤必須人工核可。** 打「照光」會命中 `57117B 加強照光治療`
  ——那是**新生兒黃疸照光**。同義詞表在 `curation/procedure_tags.yaml`，
  `gate 31` 確保黑名單不會洩漏進皮膚科子集。
- **劑量只從條文的「使用劑量」標題抽，絕不從關鍵字掃描。** 生物製劑條文裡的
  methotrexate 10mg/m²/週 掛在「給付條件」標題下，按標題抽取**天然排除**
  前置用藥劑量。前置用藥永遠獨立區塊、橘底、明寫「不是本藥的用法用量」。

## 驗證清單

改完任何東西，這四道都要綠：

```bash
make gates      # 30 道 fail-closed 閘門
make verify     # 逐藥比對條文原文 + 分類 + 搜尋命中 + JS/Python 排序一致 + 兩種 build
make offline    # 重產離線包並驗指紋
python3 etl/check_offline.py
```

再用瀏覽器實際開畫面確認（**不能只看 API**）：

| 檢查 | 期望 |
|---|---|
| `#/s/13-17-2` | 13 張表格，EASI 面積表首列 `涵蓋程度｜0﹪｜1-9﹪…90-100﹪` |
| `#/s/13-4` | 同意書欄位是一行「茲證明本人 年齡 出生日期 年 月 日」，不是一行一個詞 |
| `#/s/2-6-1` | statin 給付規定表 2 張，`LDL-C≧70mg/dL` 不被中間斷行 |
| `#/i/DUPILUMAB` | 健保條文劑量 + 前置用藥橘底警語 |
| `#/i/BETAMETHASONE` | 仿單登載用法用量，每段帶許可證字號 |
| `#/p/51017C` | 液態氮冷凍治療 600 點 + 第二部第二章第六節 |
| 離線 HTML | 網路請求**只有 HTML 自己 1 筆**；`offline/` 內不該有舊日期的產物 |


## 安全與隱私

這是**公開** repo、**公開**網站，而使用者是臨床醫師 —— 兩者相加的風險是
「病人資訊被永久公開」。設計上的三道防線：

| 層 | 做法 |
|---|---|
| 臨床註記 | 只寫進**這台瀏覽器的 localStorage**，不上傳、不進 git、不同步。`curation/clinical_notes/` 與 `*clinical-notes*.md` 已列入 `.gitignore`。**沒有「共用註記」這個功能** |
| 推送前 | `bin/pre_push_check.py`：路徑白名單（只有 pipeline 產出的路徑可 commit）＋ 內容掃描（身分證字號／手機／病歷號有值／出生日期有值／金鑰樣式）。一鍵更新在 `git add` 之前呼叫它，沒過就停在本機 |
| 瀏覽器 | 線上版 meta CSP，`connect-src 'self'` —— 這個站只讀自己 origin 的靜態 JSON，任何往外送資料的行為都會被瀏覽器擋下 |

> ★ 一鍵更新原本是無條件 `git add -A` + push。任何被放進專案資料夾的檔案
> （病歷截圖、匯出的註記、scratch 檔）都會被 commit 並**永久**留在公開歷史、
> reflog 與別人的 clone 裡。刪掉也拿不回來。這是本專案最高風險的一條路徑。

### 注入面向

- **離線包內嵌資料一律走 `_embed()`**：`json.dumps` **不會**跳脫 `</script>`。
  條文原文來自健保署 PDF，只要哪天出現這串，內嵌資料就會提前關閉 script 標籤、
  後面變成可執行的 HTML —— 而這個檔案是要被帶進醫院封閉網路的電腦的。
  `build_offline.py` 另有靜態檢查：資料區出現 `</` 就拒絕輸出。
- **前端不存在 `dangerouslySetInnerHTML` / `innerHTML` / `eval` / `new Function`**。
  所有上游文字都以 React text node 渲染，永遠是資料不是程式。
- **外連網域封閉**：只有 `nhi.gov.tw`、`fda.gov.tw`、`data.gov.tw`、`github.com`，
  全部是硬編常數，沒有一個 URL 是用上游資料拼出來的（`PDF_URL` 的檔名有
  `encodeURIComponent`）。
- **離線 zip 內只有 2 個 `.html` 與 1 個 `.txt`**，無任何可執行檔、無巨集、
  無自解壓、不加密碼（加密 ZIP 是防毒最常攔的特徵）。
- **CI 權限最小化**：`deploy.yml` 只有 `contents: read`；沒有 `pull_request_target`
  這類會執行外部 PR 程式碼的觸發條件。
- **`bin/serve.py` 只綁 `127.0.0.1`**，不對區網開放。

### 定期該做的檢查

```bash
python3 bin/pre_push_check.py     # 推送前個資／異物掃描（一鍵更新會自動跑）
grep -rn "dangerouslySetInnerHTML\|innerHTML\|eval(\|new Function" src/   # 應為空
unzip -l offline/*.zip            # 應只有 2 個 .html + 1 個 .txt
```

### commit 作者 email

本 repo 已把 `user.email` 設為 GitHub 的 noreply 位址
（`git config --local user.email 212214878+rickyrickyrickyyu@users.noreply.github.com`），
**2026-09-01 之後**的 commit 不再帶私人信箱。CI 的自動 commit 本來就用
`github-actions[bot]@users.noreply.github.com`。

⚠️ **在那之前的 26 個 commit 仍帶著私人 gmail**，任何人用
`gh api repos/<owner>/<repo>/commits` 就讀得到。刻意不改寫歷史：force push
會讓所有 commit 換 SHA，但舊 SHA 在 GitHub 上短期內仍可存取、已 clone 的
副本也還留著 —— 代價大而效果有限。

還沒做、**需要帳號擁有者自己到網頁操作**的一步：
GitHub → Settings → Emails → 勾選
「Keep my email addresses private」與
「Block command line pushes that expose my email」。
第二項是真正的保險：之後任何一台電腦忘了設 noreply，push 會直接被 GitHub 擋下。

> 換一台電腦時記得重設，`--local` 設定不會跟著 clone 走：
> `git config --local user.email <你的>@users.noreply.github.com`

## 致謝與設計來源

本站的方法論啟發自 [**王介立醫師**（Copper Wang）的 `nhi-rule-history` 專案](https://github.com/copper0722/nhi-rule-history)
—— 具體來說是「以官方開放資料為唯一權威來源、保存不可變的條文快照、以版本鍵偵測改版並產生
可稽核的 diff」這套作法。特此致謝。

**授權與原創性說明（已查證）**

- 該專案採 **MIT 授權**（Copyright (c) 2026 Copper Wang and contributors）。
- 本專案**未複製該專案的任何程式碼、資料或文件**。技術棧不同（該專案為 PostgreSQL + JSONL，
  本專案為 Python ETL + 靜態 JSON + React），資料模型、正規化規則、驗證閘門與介面均為獨立實作。
- 著作權法第 10-1 條明定「著作權保護僅及於該著作之表達，而不及於其所表達之**思想、程序、
  製程、系統、操作方法、概念、原理、發現**」。採用同一套方法論不構成重製，法律上無須授權；
  即使有引用，MIT 授權亦已允許，僅需保留著作權聲明。
- 因此本專案的致謝屬**學術與社群禮儀**，非授權義務。若權利人認為標示方式不妥，請開 issue 告知，
  我們會立即依其意見調整。
- 兩專案範圍不同：該專案回溯重建全庫條文的完整歷史（截至撰寫時 0/1548 條完成）；
  本專案不做回溯，改為自建站日起累積快照，並聚焦皮膚科用藥。
- 本站與該專案及其作者**無隸屬關係，亦未經其背書**。

## 資料來源與授權

程式碼 MIT（`LICENSE`）。資料層見 **[DATA_LICENSE.md](DATA_LICENSE.md)**。

- 健保藥品主檔：衛生福利部中央健康保險署《健保用藥品項查詢項目檔》，依「政府資料開放授權條款－第 1 版」公眾釋出。
- 藥品許可證與適應症：衛生福利部食品藥物管理署《西藥、醫療器材、含藥化粧品許可證資料集》，同上授權。
- 此開放資料依政府資料開放授權條款進行公眾釋出，使用者於遵守本條款各項規定之前提下，得利用之。條款全文：<https://data.gov.tw/license>
- 藥品給付規定條文為「全民健康保險藥物給付項目及支付標準」（法規命令）之附件，依著作權法第 9 條不得為著作權之標的；本站收存之 PDF 快照僅供版本稽核。

本站與衛生福利部、中央健康保險署、食品藥物管理署無任何隸屬或背書關係。
若您認為本站內容侵害您的權利，請開 issue，我們將儘速處理。

## 免責聲明

本站為個人維護之**非官方**參考工具，內容由健保署與食藥署公開資料自動彙整而成，
可能因資料時間差、格式變動或程式錯誤而與現行規定不符。

**所有給付規定以中央健康保險署最新公告為準**；健保申報與臨床處方之判斷及其後果
（包含核刪、爭議審議）由使用者自行負責。本站內容不構成醫療建議或申報建議。
頁面上的「事前審查」「限專科」等標籤為程式自動抽取，**一律以條文原文為準**。
各頁面均標示資料快照日期，使用前請確認。
