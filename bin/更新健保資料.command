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

die() { echo "❌ $1"; osascript -e "display alert \"資料更新已中止\" message \"$1／本機與網頁資料維持原狀。\" as critical"; read -k 1 -s "?按任意鍵關閉..."; exit 1; }

echo "▶ 1/9 下載健保藥品主檔（約 96 MB）"
python3 etl/fetch_nhi_drugs.py       || die "健保主檔下載失敗"
echo "▶ 2/9 下載食藥署許可證資料（約 79 MB）"
python3 etl/fetch_tfda.py            || echo "⚠️  食藥署下載失敗，沿用既有資料（仿單適應症可能不是最新）"
echo "▶ 3/9 檢查給付規定章節改版"
python3 etl/fetch_rule_pdfs.py $FULL || die "章節 PDF 下載失敗"
echo "▶ 4/9 正規化藥品資料"
python3 etl/normalize_drugs.py       || die "正規化失敗"
echo "▶ 5/9 解析條文"
python3 etl/parse_rules.py           || die "條文解析失敗"
echo "▶ 6/9 皮膚科標籤"
python3 etl/tag_derm.py              || die "標籤失敗（可能是金絲雀藥物消失）"
echo "▶ 7/9 產生條文異動 diff"
python3 etl/diff_rules.py            || die "diff 產生失敗"
echo "▶ 8/9 建置前端資料"
python3 etl/build_site_data.py       || die "前端資料建置失敗"

echo
echo "▶ 9/9 驗證閘門（fail-closed）"
if ! python3 etl/validate.py; then
  echo
  echo "   未通過的產物保留在 data/build/.staging/ 供檢查，正式資料未被修改。"
  die "驗證閘門未通過"
fi
python3 etl/promote.py || die "promote 失敗"

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
  read -k 1 -s "?按任意鍵關閉..."; exit 0
fi
if [[ -z "$(git status --porcelain)" ]]; then
  echo "✅ 資料無變化，本機已是最新，不需要推上網。"
  read -k 1 -s "?按任意鍵關閉..."; exit 0
fi

echo "📤 推上 GitHub（會自動重新部署網頁版）"
git add -A
git commit -q -m "chore(data): $(date +%Y-%m-%d) 資料更新" || true
if git remote get-url origin >/dev/null 2>&1 && git push -q; then
  echo "✅ 已推送。GitHub Actions 會在幾分鐘內重新部署網頁版。"
  osascript -e 'display notification "本機與網頁版都已更新" with title "健保資料更新完成"'
else
  echo "ℹ️  尚未設定 remote 或推送失敗，本機資料已更新。"
fi

echo
echo "🎉 完成"
read -k 1 -s "?按任意鍵關閉..."
