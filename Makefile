# 本機與 CI 共用同一組入口，確保兩邊跑的是同一條 pipeline。
.PHONY: refresh rebuild build gates verify dev clean

refresh:            ## 抓最新資料 → 解析 → 驗證 → promote
	python3 etl/fetch_nhi_drugs.py
	python3 etl/fetch_tfda.py
	python3 etl/fetch_rule_pdfs.py
	python3 etl/normalize_drugs.py
	python3 etl/parse_rules.py
	python3 etl/tag_derm.py
	python3 etl/diff_rules.py
	python3 etl/build_site_data.py
	python3 etl/validate.py
	python3 etl/promote.py

gates:              ## 只跑驗證閘門
	python3 etl/validate.py

verify:             ## 逐藥比對條文原文 + 搜尋命中測試
	python3 tests/verify_drugs.py
	node tests/search.test.mjs

rebuild:            ## 用既有 raw 檔重跑，不重新下載
	python3 etl/normalize_drugs.py
	python3 etl/parse_rules.py
	python3 etl/tag_derm.py
	python3 etl/diff_rules.py
	python3 etl/build_site_data.py
	python3 etl/validate.py
	python3 etl/promote.py

dev:
	pnpm dev

build:
	pnpm build

clean:
	rm -rf data/build/.staging dist
