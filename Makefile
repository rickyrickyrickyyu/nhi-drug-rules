# 本機與 CI 共用同一組入口，確保兩邊跑的是同一條 pipeline。
.PHONY: refresh rebuild build gates verify offline dev clean

refresh:            ## 抓最新資料 → 解析 → 驗證 → promote
	python3 etl/fetch_nhi_drugs.py
	python3 etl/fetch_tfda.py
	python3 etl/fetch_procedures.py
	python3 etl/fetch_rule_pdfs.py
	python3 etl/normalize_drugs.py
	python3 etl/normalize_procedures.py
	python3 etl/build_tables.py
	python3 etl/parse_rules.py
	python3 etl/tag_derm.py
	python3 etl/dosing.py
	python3 etl/mentions.py
	python3 etl/diff_rules.py
	python3 etl/build_site_data.py
	python3 etl/validate.py
	python3 etl/promote.py

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
	node tests/search_parity.mjs && python3 tests/search_parity.py

rebuild:            ## 用既有 raw 檔重跑，不重新下載
	python3 etl/normalize_drugs.py
	python3 etl/normalize_procedures.py
	python3 etl/build_tables.py
	python3 etl/parse_rules.py
	python3 etl/tag_derm.py
	python3 etl/dosing.py
	python3 etl/mentions.py
	python3 etl/diff_rules.py
	python3 etl/build_site_data.py
	python3 etl/validate.py
	python3 etl/promote.py

dev:
	pnpm dev

build:
	pnpm build

offline:            ## 產生可帶進封閉網路的單檔 HTML 與 zip
	pnpm exec vite build --mode offline
	python3 etl/build_offline.py

clean:
	rm -rf data/build/.staging dist
