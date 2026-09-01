#!/usr/bin/env bash
# 資料管線的單一事實來源。
#
# ★ 為什麼要抽出來：
#   原本 Makefile 的 refresh 與 bin/更新健保資料.command 各自維護一份步驟清單，
#   兩份已經走鐘 —— 一鍵更新完全沒有跑處置（fetch_procedures / normalize_procedures）、
#   表格（build_tables）、劑量（dosing）、提及索引（mentions），
#   結果是「按了更新，藥品更新了但處置還是上個月的」。
#   現在兩邊都呼叫這支腳本，不可能再分岔。
#
# 用法：
#   bin/pipeline.sh fetch     完整抓取 + 解析 + 驗證 + promote
#   bin/pipeline.sh rebuild   不重新下載，用既有 raw 檔重跑
#   bin/pipeline.sh offline   產生離線包並驗證與線上同一份資料
set -euo pipefail
cd "$(dirname "$0")/.."

MODE="${1:-fetch}"
FULL="${2:-}"

# 每一行是「腳本:說明」。fetch 專屬的下載步驟標 dl:
FETCH_STEPS=(
  "etl/fetch_nhi_drugs.py:下載健保藥品主檔（約 96 MB）"
  "etl/fetch_tfda.py:下載食藥署許可證資料（約 79 MB）:soft"
  "etl/fetch_procedures.py:下載醫療服務給付項目（處置醫令）"
  "etl/fetch_proc_chapters.py:抓處置的支付標準章節定位:soft"
  "etl/fetch_rule_pdfs.py:檢查給付規定章節改版:$FULL"
)
BUILD_STEPS=(
  "etl/normalize_drugs.py:正規化藥品資料"
  "etl/normalize_procedures.py:正規化處置醫令"
  "etl/build_tables.py:從 PDF 還原表格"
  "etl/parse_rules.py:解析條文"
  "etl/tag_derm.py:皮膚科標籤"
  "etl/dosing.py:抽取條文所載劑量"
  "etl/dose_tfda.py:抽取仿單登載用法用量"
  "etl/mentions.py:建立藥名提及索引"
  "etl/diff_rules.py:產生條文異動 diff"
  "etl/build_site_data.py:建置前端資料"
)

steps=()
[[ "$MODE" == "fetch" ]] && steps+=("${FETCH_STEPS[@]}")
steps+=("${BUILD_STEPS[@]}")

total=$(( ${#steps[@]} + 3 ))   # +驗證 +promote +離線包
i=0
for entry in "${steps[@]}"; do
  script="${entry%%:*}"; rest="${entry#*:}"
  desc="${rest%%:*}"; opt="${rest#*:}"; [[ "$opt" == "$desc" ]] && opt=""
  i=$((i+1))
  echo "▶ $i/$total $desc"
  if [[ "$opt" == "soft" ]]; then
    # soft：失敗只警告不中止（外部服務可能暫時掛掉，沿用既有資料仍可出版）
    python3 "$script" || echo "   ⚠️  $script 失敗，沿用既有資料"
  else
    python3 "$script" ${opt:+$opt} || { echo "❌ $script 失敗"; exit 1; }
  fi
done

i=$((i+1)); echo "▶ $i/$total 驗證閘門（fail-closed）"
python3 etl/validate.py || exit 2          # exit 2 = 閘門擋下，呼叫端要顯示 staging 位置

i=$((i+1)); echo "▶ $i/$total promote 到 public/data"
python3 etl/promote.py || exit 1

i=$((i+1)); echo "▶ $i/$total 產生離線包（皮膚科版＋全庫版）"
if pnpm exec vite build --mode offline >/dev/null 2>&1 \
   && python3 etl/build_offline.py && python3 etl/check_offline.py; then
  echo "   📦 offline/ 已更新"
else
  echo "   ⚠️  離線包產生失敗（線上版不受影響）"
  exit 3                                    # exit 3 = 資料好了但離線包沒出
fi
