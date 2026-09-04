# 本機與 CI 共用同一組入口，確保兩邊跑的是同一條 pipeline。
.PHONY: refresh rebuild build gates verify offline dev clean

refresh:            ## 抓最新資料 → 解析 → 驗證 → promote → 離線包
	bin/pipeline.sh fetch

gates:              ## 只跑驗證閘門
	python3 etl/validate.py

verify:             ## 逐藥比對條文原文 + 分類驗證 + 搜尋命中測試 + 兩種 build
	# ★ lint 一定要跑且要能擋：no-undef 這種「跑起來才炸」的錯，
	#   build 與所有 Node 測試都抓不到（它們不渲染 React）。
	#   實際踩過：把 annotate 抽到別的檔卻沒 import，整站白畫面，
	#   lint/build/測試全綠，只有瀏覽器實測看得到。
	pnpm exec oxlint --deny-warnings src
	# ★ 線上版 build 一定要跑：offline mode 會關掉 PWA，只跑 offline 等於
	#   沒驗到 workbox 設定，曾因此本機全綠而 CI 紅燈（maxEntries 寫錯層級）。
	pnpm build
	pnpm exec vite build --mode offline
	python3 tests/verify_drugs.py
	python3 tests/verify_categories.py
	node tests/search.test.mjs
	node tests/relevance.test.mjs
	node tests/appendix.test.mjs
	node tests/search_parity.mjs && python3 tests/search_parity.py
	python3 etl/check_offline.py

rebuild:            ## 用既有 raw 檔重跑（不重新下載）
	bin/pipeline.sh rebuild

dev:
	pnpm dev

build:
	pnpm build

offline:            ## 產生可帶進封閉網路的單檔 HTML 與 zip
	pnpm exec vite build --mode offline
	python3 etl/build_offline.py
	python3 etl/check_offline.py

clean:
	rm -rf data/build/.staging dist
