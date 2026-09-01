import { useCallback, useEffect, useState } from 'react';

const BASE = `${import.meta.env.BASE_URL}data`;

async function getJson(path) {
  const r = await fetch(`${BASE}/${path}`);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}

/** 首載只抓皮膚科子集與 meta；全庫要使用者主動切換才載。 */
export function useCoreData() {
  const [state, setState] = useState({ loading: true, error: null, meta: null, derm: [], procs: [], all: null });

  useEffect(() => {
    let alive = true;
    Promise.all([getJson('meta.json'), getJson('derm.json')])
      .then(([meta, derm]) => alive && setState({
        loading: false, error: null, meta,
        derm: [...derm.ing, ...(derm.proc ?? [])],   // 藥品與處置混在同一個搜尋集合
        procs: derm.proc ?? [],
        all: null,
      }))
      .catch((e) => alive && setState((s) => ({ ...s, loading: false, error: e.message })));
    return () => { alive = false; };
  }, []);

  const loadAll = useCallback(async () => {
    // 處置的全庫另存一檔（6,173 筆）。任一失敗只停用該部分，
    // 不讓新功能拖垮既有的藥品查詢。
    const [all, procAll] = await Promise.all([
      getJson('all.json'),
      getJson('procs_all.json').catch(() => ({ proc: [] })),
    ]);
    const merged = [...all.ing, ...(procAll.proc ?? [])];
    setState((s) => ({ ...s, all: merged, procs: procAll.proc?.length ? procAll.proc : s.procs }));
    return merged;
  }, []);

  return { ...state, loadAll };
}

const chapterCache = new Map();

/** 章節按大節分檔：一次抓第 13 節全部，勝過對每個章節各發一次請求。 */
export async function loadChapter(n) {
  if (!chapterCache.has(n)) chapterCache.set(n, getJson(`rules/ch${n}.json`));
  return chapterCache.get(n);
}

export async function loadProducts(innKey) {
  const safe = innKey.replaceAll('/', '_').replaceAll(' ', '_').replaceAll('(', '').replaceAll(')', '');
  return getJson(`products/${safe}.json`);
}
