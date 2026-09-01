#!/bin/zsh
# 一鍵更新：抓最新健保／食藥署資料 → 驗證 → 更新本機 → 推上 GitHub（連動網頁版）
#
# 雙擊即可執行。fail-closed：任何驗證閘門沒過就中止，不會 commit 也不會推上網，
# 本機既有資料維持原狀。
# 加 --full 參數則重新下載全部 534 份章節 PDF（半年一次的全面校驗）。

set -uo pipefail
cd "${0:A:h:h}" || exit 1

VENV="$HOME/Developer/vibe-coding/.venv/bin"
[[ -x "$VENV/python3" ]] || { osascript -e 'display alert "找不到 Python 環境" message "預期路徑 ~/Developer/vibe-coding/.venv"'; exit 1; }
export PATH="$VENV:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

echo "════════════════════════════════════════"
echo "  皮膚科健保給付規定資料庫 · 一鍵更新"
echo "  $(date '+%Y-%m-%d %H:%M')"
echo "════════════════════════════════════════"
echo

FULL=""
if [[ "${1:-}" == "--full" ]]; then
  FULL="--force"
  echo "🔁 完整模式：重新下載全部 534 份章節 PDF（半年一次的全面校驗）"
else
  echo "⚡ 增量模式：只下載檔名生效日有變的章節"
fi
echo

# 非互動執行（cron／CI／管線）時不要卡在等按鍵
pause() { [[ -t 0 ]] && read -k 1 -s "?按任意鍵關閉..." || true; }
die() {
  echo "❌ $1"
  osascript -e "display alert \"資料更新已中止\" message \"$1／本機與網頁資料維持原狀。\" as critical" 2>/dev/null
  pause; exit 1
}

# ★ 步驟清單集中在 bin/pipeline.sh，與 make refresh 共用同一份。
#   以前這裡自己維護一份，結果漏掉處置、表格、劑量、提及索引四個步驟 ——
#   按了「更新」但處置永遠停在上個月。
bash bin/pipeline.sh fetch $FULL
rc=$?
if [[ $rc -eq 2 ]]; then
  echo
  echo "❌ 驗證閘門擋下，未更新正式資料（staging 保留在 data/build/.staging）"
  echo "   線上與離線版都維持前一版，不會出現半套資料。"
  exit 1
elif [[ $rc -eq 3 ]]; then
  echo "⚠️  資料已更新，但離線包產生失敗 —— 執行 nhi offline 可單獨重產"
elif [[ $rc -ne 0 ]]; then
  die "更新失敗"
fi

echo
echo "── 本次異動 ──"
python3 - <<'PY'
import json, pathlib
c = json.loads(pathlib.Path('public/data/changelog.json').read_text(encoding='utf-8'))
print(f"  章節改版 {c['n_revised']}｜靜默改檔 {c['n_silent_edit']}｜新章節 {c['new_sections_count']}")
for x in c['changes'][:12]:
    print(f"    {x['code']:12s} {x['kind']:12s} 生效 {x['eff']}  +{x['added']}/-{x['removed']} 句")
PY

echo
if ! command -v git >/dev/null || [[ ! -d .git ]]; then
  echo "ℹ️  沒有 git repo，只更新本機（網頁版不受影響）"
  pause; exit 0
fi
if ! git remote get-url origin >/dev/null 2>&1; then
  echo "ℹ️  尚未設定 GitHub remote，只更新了本機"
  pause; exit 0
fi

if [[ -z "$(git status --porcelain)" ]]; then
  echo "✅ 本機資料無變化。"
else
  echo "📤 準備推上 GitHub"
  git add -A
  git commit -q -m "chore(data): $(date +%Y-%m-%d) 資料更新" || true
fi

# 先 pull 再 push：GitHub Actions 的月更排程也會 commit，
# 不先併會被拒（non-fast-forward），使用者只會看到一個看不懂的錯誤。
# --rebase 讓本機這筆疊在遠端之上，資料檔沒有真正的內容衝突。
echo "🔄 同步遠端變更"
if ! git pull --rebase -q 2>/dev/null; then
  echo "⚠️  自動合併失敗（可能有衝突）。本機資料已更新，請手動處理："
  echo "     cd $(pwd) && git status"
  pause; exit 1
fi

if [[ -z "$(git log origin/main..HEAD --oneline 2>/dev/null)" ]]; then
  echo "✅ 遠端已是最新，本機與網頁版一致。"
  pause; exit 0
fi

# 推送重試：家用網路 DNS 偶爾斷線，一次失敗就放棄會讓兩邊資料不同步
PUSHED=0
for i in 1 2 3 4 5; do
  if git push -q 2>/dev/null; then PUSHED=1; break; fi
  echo "   推送失敗，${i}/5 次重試…"; sleep 6
done
if (( PUSHED == 0 )); then
  echo "⚠️  推送失敗，本機已更新但網頁版還是舊的。網路恢復後執行："
  echo "     cd $(pwd) && git push"
  osascript -e 'display alert "網頁版未更新" message "本機資料已更新，但推送到 GitHub 失敗。網路恢復後請執行 git push。"' 2>/dev/null
  pause; exit 1
fi
echo "✅ 已推送"

# 確認網頁版真的更新到 —— 使用者要的是「兩邊同時更新」，
# push 成功不等於網站更新完成，要等 Actions 部署並比對線上的資料日期。
# ★ 比指紋不比日期：built 只到「日」，同一天內重跑 ETL 資料已經不同，
#   只比日期會在網站其實還沒部署好時就回報「已更新」。
LOCAL_FP=$(python3 -c "import json;print(json.load(open('public/data/meta.json'))['data_fingerprint'])")
LOCAL_BUILT=$(python3 -c "import json;print(json.load(open('public/data/meta.json'))['built'])")
SITE="https://rickyrickyrickyyu.github.io/nhi-drug-rules/data/meta.json"
echo "⏳ 等待 GitHub Actions 部署（約 1–3 分鐘）"
for i in $(seq 1 40); do
  sleep 15
  REMOTE_FP=$(curl -sS -m 10 "${SITE}?t=$RANDOM" 2>/dev/null \
    | python3 -c "import json,sys;print(json.load(sys.stdin).get('data_fingerprint',''))" 2>/dev/null || echo "")
  if [[ "$REMOTE_FP" == "$LOCAL_FP" ]]; then
    echo "✅ 網頁版已更新（資料快照 $LOCAL_BUILT｜指紋 $LOCAL_FP）— 本機、線上、離線三者一致"
    osascript -e 'display notification "本機與網頁版都已更新" with title "健保資料更新完成"' 2>/dev/null
    echo
    echo "🎉 完成  https://rickyrickyrickyyu.github.io/nhi-drug-rules/"
    pause; exit 0
  fi
  (( i % 4 == 0 )) && echo "   仍在部署…（線上指紋 ${REMOTE_FP:-讀取中}，本機 $LOCAL_FP）"
done
echo "⚠️  10 分鐘內未看到網頁版更新。commit 已推送，可到 Actions 頁確認："
echo "     https://github.com/rickyrickyrickyyu/nhi-drug-rules/actions"
pause
