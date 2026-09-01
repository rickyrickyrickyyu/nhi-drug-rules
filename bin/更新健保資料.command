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

echo "▶ 1/10 下載健保藥品主檔（約 96 MB）"
python3 etl/fetch_nhi_drugs.py       || die "健保主檔下載失敗"
echo "▶ 2/10 下載食藥署許可證資料（約 79 MB）"
python3 etl/fetch_tfda.py            || echo "⚠️  食藥署下載失敗，沿用既有資料（仿單適應症可能不是最新）"
echo "▶ 3/10 檢查給付規定章節改版"
python3 etl/fetch_rule_pdfs.py $FULL || die "章節 PDF 下載失敗"
echo "▶ 4/10 正規化藥品資料"
python3 etl/normalize_drugs.py       || die "正規化失敗"
echo "▶ 5/10 解析條文"
python3 etl/parse_rules.py           || die "條文解析失敗"
echo "▶ 6/10 皮膚科標籤"
python3 etl/tag_derm.py              || die "標籤失敗（可能是金絲雀藥物消失）"
echo "▶ 7/10 產生條文異動 diff"
python3 etl/diff_rules.py            || die "diff 產生失敗"
echo "▶ 8/10 建置前端資料"
python3 etl/build_site_data.py       || die "前端資料建置失敗"

echo
echo "▶ 9/10 驗證閘門（fail-closed）"
if ! python3 etl/validate.py; then
  echo
  echo "   未通過的產物保留在 data/build/.staging/ 供檢查，正式資料未被修改。"
  die "驗證閘門未通過"
fi
python3 etl/promote.py || die "promote 失敗"

echo "▶ 10/10 產生離線包（皮膚科版＋全庫版）"
if pnpm exec vite build --mode offline >/dev/null 2>&1 && python3 etl/build_offline.py; then
  echo "   📦 offline/ 已更新，可直接拖到隨身碟帶去封閉電腦"
else
  echo "   ⚠️  離線包產生失敗（線上版不受影響）"
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
LOCAL_BUILT=$(python3 -c "import json;print(json.load(open('public/data/meta.json'))['built'])")
SITE="https://rickyrickyrickyyu.github.io/nhi-drug-rules/data/meta.json"
echo "⏳ 等待 GitHub Actions 部署（約 1–3 分鐘）"
for i in $(seq 1 40); do
  sleep 15
  REMOTE_BUILT=$(curl -sS -m 10 "${SITE}?t=$RANDOM" 2>/dev/null \
    | python3 -c "import json,sys;print(json.load(sys.stdin).get('built',''))" 2>/dev/null || echo "")
  if [[ "$REMOTE_BUILT" == "$LOCAL_BUILT" ]]; then
    echo "✅ 網頁版已更新（資料快照 $REMOTE_BUILT）— 本機與線上一致"
    osascript -e 'display notification "本機與網頁版都已更新" with title "健保資料更新完成"' 2>/dev/null
    echo
    echo "🎉 完成  https://rickyrickyrickyyu.github.io/nhi-drug-rules/"
    pause; exit 0
  fi
  (( i % 4 == 0 )) && echo "   仍在部署…（線上 ${REMOTE_BUILT:-讀取中}，本機 $LOCAL_BUILT）"
done
echo "⚠️  10 分鐘內未看到網頁版更新。commit 已推送，可到 Actions 頁確認："
echo "     https://github.com/rickyrickyrickyyu/nhi-drug-rules/actions"
pause
