/** 民國↔西元顯示。條文內是 115/6/1，要能 hover 看到西元。 */
export function rocToAd(roc) {
  const m = /^(\d{2,3})\/(\d{1,2})\/(\d{1,2})$/.exec(roc ?? '');
  if (!m) return null;
  return `${Number(m[1]) + 1911}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`;
}

/**
 * 支付價顯示。
 * ★ 健保檔裡 69% 的品項支付價是 0.00，且生效起日多為 2002–2015 —— 這不代表免費，
 *   而是該品項未列價（多半已無實際流通）。顯示 $0 會誤導，一律標「未列價」。
 */
export const money = (n) =>
  n == null || Number(n) === 0
    ? '未列價'
    : `$${Number(n).toLocaleString('zh-TW', { maximumFractionDigits: 2 })}`;

export function priceRange(pr) {
  if (!pr) return '—';
  const [lo, hi] = pr;
  return lo === hi ? money(lo) : `${money(lo)} – ${money(hi)}`;
}

/** 章節碼 → 檔名 slug（13.17.1. → 13-17-1） */
export const secSlug = (code) => code.replace(/\.$/, '').replaceAll('.', '-');
export const secChapter = (code) => Number(code.split('.')[0]);
