# 本機與 CI 共用同一組入口，確保兩邊跑的是同一條 pipeline。
.PHONY: refresh rebuild build gates verify offline dev clean

refresh:            ## 抓最新資料 → 解析 → 驗證 → promote → 離線包
	bin/pipeline.sh fetch

gates:              ## 只跑驗證閘門
	python3 etl/validate.py

verify:             ## 逐藥比對條文原文 + 分類驗證 + 搜尋命中測試 + 兩種 build
	# ★ 線上版 build 一定要跑：offline mode 會關掉 PWA，只跑 offline 等於
	#   沒驗到 workbox 設定，曾因此本機全綠而 CI 紅燈（maxEntries 寫錯層級）。
	pnpm build
	pnpm exec vite build --mode offline
	python3 tests/verify_drugs.py
	python3 tests/verify_categories.py
	node tests/search.test.mjs
	node tests/relevance.test.mjs
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
