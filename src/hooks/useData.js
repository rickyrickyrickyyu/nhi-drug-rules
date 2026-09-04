import { useCallback, useEffect, useState } from 'react';

const BASE = `${import.meta.env.BASE_URL}data`;

/**
 * 離線版把所有資料內嵌在 window.__NHI_OFFLINE__，因為 file:// 下 fetch()
 * 讀不到本機檔案（CORS）。只要在這裡分流，loadChapter / loadProducts /
 * useCoreData 全部不必改就能在離線版運作。
 */
const EMBEDDED = typeof window !== 'undefined' ? window.__NHI_OFFLINE__ : null;

async function getJson(path) {
  if (EMBEDDED) {
    const v = EMBEDDED[path];
    if (v === undefined) throw new Error(`${path}: 離線版未內嵌此資料`);
    return v;
  }
  const r = await fetch(`${BASE}/${path}`);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}

export const isOffline = () => Boolean(EMBEDDED);
export const offlineMeta = () =>
  (typeof window !== 'undefined' ? window.__NHI_OFFLINE_META__ : null) ?? null;

/** 給元件直接取任意資料檔用，離線與線上共用同一條路徑。 */
export const fetchData = getJson;

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

const blobCache = new Map();

/**
 * 附表原文 PDF 的可開啟網址。
 *
 * ★ 線上：連本站自己的 public/data/appendix/*.pdf（不外連 nhi.gov.tw，
 *   也不受對方網站改版影響）。
 * ★ 離線：PDF 以 base64 內嵌，轉成 blob: 再開 ——
 *   瀏覽器會**擋掉 data: 的頂層導覽**，直接 <a href="data:application/pdf">
 *   點了不會有反應。blob: 沒有這個限制。
 */
function embeddedPdf(key) {
  const store = typeof window !== 'undefined' ? window.__NHI_OFFLINE_PDF__ : null;
  const b64 = store?.[key];
  if (!b64) return null;
  if (!blobCache.has(key)) {
    const bin = atob(b64);
    const buf = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i += 1) buf[i] = bin.charCodeAt(i);
    blobCache.set(key, URL.createObjectURL(new Blob([buf], { type: 'application/pdf' })));
  }
  return blobCache.get(key);
}

export function appendixPdfUrl(name) {
  if (!isOffline()) return `${BASE}/appendix/${encodeURIComponent(name)}.pdf`;
  return embeddedPdf(name);
}

/**
 * 章節條文的官方 PDF。
 *
 * ★ 離線包只內嵌皮膚科用得到的 242 份（全部 534 份要多 64 MB，會讓單檔
 *   HTML 破 90 MB）。沒內嵌的回 null，UI 改顯示「需要網路」而不是給一個
 *   點了沒反應的按鈕。
 */
export function rulePdfUrl(filename) {
  if (!filename) return null;
  if (!isOffline()) return `${BASE}/pdf/${encodeURIComponent(filename)}`;
  return embeddedPdf(`rule:${filename}`);
}

const appendixCache = new Map();

/** 附表內容分片。附表名含中文，路徑要編碼（離線版是查 key，不編碼）。 */
export function loadAppendix(name) {
  if (!appendixCache.has(name)) {
    appendixCache.set(name, getJson(`appendix/${name}.json`));
  }
  return appendixCache.get(name);
}

export async function loadProducts(innKey) {
  const safe = innKey.replaceAll('/', '_').replaceAll(' ', '_').replaceAll('(', '').replaceAll(')', '');
  return getJson(`products/${safe}.json`);
}
