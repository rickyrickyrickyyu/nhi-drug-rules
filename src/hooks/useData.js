import { useCallback, useEffect, useState } from 'react';

const BASE = `${import.meta.env.BASE_URL}data`;

async function getJson(path) {
  const r = await fetch(`${BASE}/${path}`);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}

/** 首載只抓皮膚科子集與 meta；全庫要使用者主動切換才載。 */
export function useCoreData() {
  const [state, setState] = useState({ loading: true, error: null, meta: null, derm: [], all: null });

  useEffect(() => {
    let alive = true;
    Promise.all([getJson('meta.json'), getJson('derm.json')])
      .then(([meta, derm]) => alive && setState({ loading: false, error: null, meta, derm: derm.ing, all: null }))
      .catch((e) => alive && setState((s) => ({ ...s, loading: false, error: e.message })));
    return () => { alive = false; };
  }, []);

  const loadAll = useCallback(async () => {
    const all = await getJson('all.json');
    setState((s) => ({ ...s, all: all.ing }));
    return all.ing;
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
