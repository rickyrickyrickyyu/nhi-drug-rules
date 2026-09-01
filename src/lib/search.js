/**
 * 學名／商品名搜尋評分。
 *
 * 主鍵是英文學名，但門診常只記得商品名（「那個 Valtrex 給不給付？」），
 * 所以中英商品名、章節碼、ATC、藥品代號都要能命中，且要回報「靠哪個欄位命中」，
 * 讓醫師確認搜到的是不是自己想的那支藥。
 *
 * 刻意不用 MiniSearch/FlexSearch：皮膚科子集只有數百個學名，線性掃描 <1ms，
 * 而且它們的預設 tokenizer 會把「杜避炎注射劑」整串當一個 token，中文子字串搜不到。
 */

/** 全形→半形、去空白、大小寫摺疊。祛疹易錠５００毫克 這種全形數字必須先正規化。 */
export function normalizeQuery(q) {
  return (q ?? '')
    .normalize('NFKC')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, ' ');
}

const FIELD_LABEL = {
  inn: '學名',
  alias: '學名別名',
  zh: '中文俗稱',
  brandOrig: '原廠商品名',
  brandEn: '商品名',
  brandZh: '中文商品名',
  code: '藥品代號',
  section: '給付章節',
  atc: 'ATC 碼',
  combo: '複方成分',
  procName: '處置名稱',
  procEn: '英文名稱',
  procSyn: '同義詞',
  procCode: '醫令代碼',
  procNote: '給付備註',
};

/**
 * 比對層級：3=完全相符 2=前綴 1=子字串 0=不中。
 *
 * ★ 呼叫端必須用 pick() 展開成三級分數。舊版寫成 `s >= 2 ? X : Y`
 * 把「完全相符」與「前綴」壓成同一分，與 cli/query.py 的三級版本不一致，
 * 實測 9/10 查詢兩邊分數不同（valtrex JS 85 / PY 90）。
 */
function prefixOrSub(hay, q) {
  if (!hay) return 0;
  const h = hay.normalize('NFKC').toLowerCase();
  if (h === q) return 3;
  if (h.startsWith(q)) return 2;
  if (h.includes(q)) return 1;
  return 0;
}

const pick = (lvl, exact, pre, sub) => (lvl === 3 ? exact : lvl === 2 ? pre : sub);

/**
 * 對單一處置計分。
 *
 * 同義詞權重刻意接近名稱本身 —— 醫師打「照光」時，51018C 光化治療的名稱裡
 * 沒有這兩個字，全靠同義詞命中；若同義詞分數太低，會被名稱含「照光」的
 * 57117B（新生兒黃疸）壓過去。
 */
export function scoreProcedure(q, item) {
  let best = { score: 0, field: null, matched: null };
  const bump = (score, field, matched) => {
    if (score > best.score) best = { score, field, matched };
  };

  if (item.k.toLowerCase() === q) bump(100, 'procCode', item.k);
  else if (q.length >= 3 && item.k.toLowerCase().startsWith(q)) bump(92, 'procCode', item.k);

  // 名稱命中優先於同義詞：查「液態氮」時 51017C「液態氮冷凍治療」的名稱
  // 就含這三個字，應排在只靠同義詞命中的 37002B「冷凍治療」之前。
  const n = prefixOrSub(item.n, q);
  if (n) bump(pick(n, 99, 95, 93), 'procName', item.n);

  const e = prefixOrSub(item.en, q);
  if (e) bump(pick(e, 94, 88, 52), 'procEn', item.en);

  for (const sy of item.z ?? []) {
    const s = prefixOrSub(sy, q);
    if (s) bump(pick(s, 92, 86, 50), 'procSyn', sy);
  }

  if (item.note && item.note.normalize('NFKC').toLowerCase().includes(q)) {
    bump(20, 'procNote', item.note.slice(0, 40));
  }
  // 同分時群組首選代碼勝出（yaml 裡群組的第一個代碼）
  if (best.score > 0 && item.pri) best.score += 1;
  return best;
}

/**
 * 對單一學名計分。回傳 { score, field, matched } —— matched 是實際命中的字串，
 * UI 會把它標亮並顯示「透過商品名 Valtrex 命中」。
 */
export function scoreIngredient(q, item) {
  let best = { score: 0, field: null, matched: null };
  const bump = (score, field, matched) => {
    if (score > best.score) best = { score, field, matched };
  };

  const m = prefixOrSub(item.n, q);
  if (m) bump(pick(m, 100, 95, 50), 'inn', item.n);

  for (const a of item.al ?? []) {
    const s = prefixOrSub(a, q);
    if (s) bump(pick(s, 100, 90, 48), 'alias', a);
  }

  for (const z of item.z ?? []) {
    const s = prefixOrSub(z, q);
    if (s) bump(pick(s, 88, 80, 42), 'zh', z);
  }

  // 原廠商品名（route 的第一個 brand_preview）權重高於一般學名藥商品名
  const originators = new Set();
  for (const r of item.r ?? []) for (const b of r.bp ?? []) originators.add(b.split(' ')[0]);
  for (const b of originators) {
    const s = prefixOrSub(b, q);
    if (s) bump(pick(s, 90, 85, 40), 'brandOrig', b);
  }
  for (const b of item.be ?? []) {
    const s = prefixOrSub(b, q);
    if (s) bump(pick(s, 80, 75, 40), originators.has(b) ? 'brandOrig' : 'brandEn', b);
  }
  for (const b of item.bz ?? []) {
    const s = prefixOrSub(b, q);
    if (s) bump(pick(s, 78, 70, 38), 'brandZh', b);
  }

  for (const s of item.s ?? []) {
    // 章節碼比對去尾點，讓使用者打 13.4 就能中 13.4.
    if (s.replace(/\.$/, '') === q.replace(/\.$/, '') || s.startsWith(q)) {
      bump(60, 'section', s);
    }
  }
  for (const a of item.a ?? []) {
    if (a.toLowerCase().startsWith(q)) bump(55, 'atc', a);
  }
  if (item.c) {
    for (const part of item.k.split(' + ')) {
      const s = prefixOrSub(part, q);
      if (s) bump(pick(s, 50, 45, 30), 'combo', part);
    }
  }
  return best;
}

/** 藥品代號直查：不在 slim 資料裡，靠 be/bz 之外的獨立索引由呼叫端補。 */
/** 依 item.t 分派到對應的評分器，讓藥品與處置能在同一個結果清單裡排序。 */
export function scoreEntity(q, item) {
  return item.t === 'p' ? scoreProcedure(q, item) : scoreIngredient(q, item);
}

export function searchIngredients(query, dataset, { limit = 60 } = {}) {
  const q = normalizeQuery(query);
  if (q.length < 1) return [];
  const out = [];
  for (const item of dataset) {
    const hit = scoreEntity(q, item);
    if (hit.score > 0) out.push({ item, ...hit, fieldLabel: FIELD_LABEL[hit.field] });
  }
  out.sort((a, b) => b.score - a.score || String(a.item.n).localeCompare(String(b.item.n)));
  return out.slice(0, limit);
}

/** 只在零結果且輸入夠長時才跑，避免每次按鍵都做 O(n·m) 編輯距離。 */
export function fuzzyFallback(query, dataset, { limit = 10 } = {}) {
  const q = normalizeQuery(query);
  if (q.length < 5) return [];
  const out = [];
  for (const item of dataset) {
    const n = item.n.toLowerCase();
    if (Math.abs(n.length - q.length) > 2) continue;
    if (within1Edit(n.slice(0, q.length + 1), q)) {
      out.push({ item, score: 10, field: 'inn', matched: item.n, fieldLabel: '學名（近似）' });
    }
  }
  return out.slice(0, limit);
}

function within1Edit(a, b) {
  if (a === b) return true;
  let i = 0;
  let j = 0;
  let edits = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      i++;
      j++;
      continue;
    }
    if (++edits > 1) return false;
    if (a.length > b.length) i++;
    else if (a.length < b.length) j++;
    else {
      i++;
      j++;
    }
  }
  return edits + (a.length - i) + (b.length - j) <= 1;
}
