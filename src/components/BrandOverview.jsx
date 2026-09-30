import { useMemo, useState } from 'react';

// 學名鍵是全大寫（健保主檔拼法），顯示時轉成字首大寫；括號內的鹽類保留原樣
const titleCase = (s) => s.toLowerCase().replace(/(^|[\s(/-])([a-z])/g, (_, p, c) => p + c.toUpperCase());

/**
 * 把品項表收斂成「商品名」—— 同一商品不同規格（0.25%／0.5%）、不同藥品代號只算一個。
 *
 * ★ 為什麼另做一覽，不叫醫師自己翻品項表：
 *   品項表按劑型分頁、放在頁尾、一列一個代號，Timolol 眼用 108 列裡有 87 列未列價被折疊，
 *   而且看不出哪些是複方（Cosopt = + dorzolamide）。醫師要的是「這個學名有哪些商品名」。
 * ★ 複方依「併用成分」分組，不能跟單方混在一起：開 Timoptol 與開 Cosopt 是兩回事。
 */
function summarize(items, innKey, routes) {
  const byRoute = new Map();
  for (const p of items) {
    const partners = (p.inn_keys ?? []).filter((k) => k !== innKey).toSorted();
    const group = partners.length ? `+ ${partners.map(titleCase).join(' + ')}` : '';
    const name = p.brand_stem_en || p.brand_stem_zh || p.name_en;
    const key = `${group}|${name.toLowerCase()}`;
    if (!byRoute.has(p.route)) byRoute.set(p.route, new Map());
    const m = byRoute.get(p.route);
    const b = m.get(key) ?? { name, group, zh: new Set(), orig: false, priced: false, n: 0 };
    if (p.brand_stem_zh) b.zh.add(p.brand_stem_zh);
    b.orig ||= !!p.is_originator;
    b.priced ||= !!p.price;
    b.n += 1;
    m.set(key, b);
  }
  // 依詳情頁分頁的順序排劑型
  return routes
    .filter((r) => byRoute.has(r.ro))
    .map((r) => {
      const brands = [...byRoute.get(r.ro).values()].toSorted((a, b) =>
        (b.priced - a.priced) || (b.orig - a.orig) || a.name.localeCompare(b.name));
      const groups = new Map();
      for (const b of brands) {
        if (!groups.has(b.group)) groups.set(b.group, []);
        groups.get(b.group).push(b);
      }
      // 單方（group 為空字串）永遠排第一
      const ordered = [...groups.entries()].toSorted(([a], [b]) => (a === '' ? -1 : b === '' ? 1 : a.localeCompare(b)));
      return { ro: r.ro, label: r.l, groups: ordered };
    });
}

const brandText = (b) => `${b.name}${b.zh.size ? `（${[...b.zh].join('／')}${b.orig ? '，原廠' : ''}）` : b.orig ? '（原廠）' : ''}`;

export default function BrandOverview({ item, items, onPick }) {
  const data = useMemo(() => summarize(items, item.k, item.r ?? []), [items, item.k, item.r]);
  const [copied, setCopied] = useState(false);

  const all = data.flatMap((r) => r.groups.flatMap(([, bs]) => bs));
  const nPriced = all.filter((b) => b.priced).length;
  const nUnpriced = all.length - nPriced;
  if (!all.length) return null;

  const copy = () => {
    const lines = [`${item.n} 商品名一覽（健保藥品主檔）`];
    for (const r of data) {
      for (const [g, bs] of r.groups) {
        const priced = bs.filter((b) => b.priced).map(brandText);
        const unpriced = bs.filter((b) => !b.priced).map(brandText);
        const head = `${r.label}｜${g ? `複方 ${g}` : '單方'}`;
        if (priced.length) lines.push(`${head}：${priced.join('、')}`);
        if (unpriced.length) lines.push(`${head}（未列價）：${unpriced.join('、')}`);
      }
    }
    navigator.clipboard?.writeText(lines.join('\n')).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }).catch(() => {});
  };

  return (
    // 老藥動輒上百個品名（Acetaminophen 300+），預設收合，免得把條文擠到很下面
    <details className="bg-white rounded-xl border border-slate-200" open={nPriced <= 30}>
      <summary className="px-4 py-2.5 text-sm font-medium cursor-pointer flex items-center gap-2">
        <span>商品名一覽</span>
        <span className="text-xs font-normal text-slate-500">
          {nPriced} 個有列價{nUnpriced > 0 && `，另 ${nUnpriced} 個未列價`}
        </span>
        <button
          type="button"
          onClick={(e) => { e.preventDefault(); copy(); }}
          className="ml-auto text-xs font-normal px-2 py-0.5 rounded border border-slate-300 hover:border-brand-600"
        >
          {copied ? '已複製 ✓' : '複製清單'}
        </button>
      </summary>
      <div className="px-4 pb-3 space-y-3">
        {data.map((r) => (
          <div key={r.ro}>
            {data.length > 1 && <div className="text-xs font-semibold text-slate-700 mb-1">{r.label}</div>}
            {r.groups.map(([g, bs]) => {
              const priced = bs.filter((b) => b.priced);
              const unpriced = bs.filter((b) => !b.priced);
              return (
                <div key={g} className="mb-2">
                  <div className="text-[11px] text-slate-500 mb-1">
                    {g ? <>複方 <span className="font-medium text-slate-700">{g}</span></> : '單方'}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {priced.map((b) => (
                      <button
                        key={b.name}
                        type="button"
                        onClick={() => onPick(r.ro)}
                        title={`${b.n} 個品項（不同規格／藥品代號）｜點選看${r.label}品項表`}
                        className="text-left text-xs px-2 py-1 rounded-lg border border-slate-300 hover:border-brand-600"
                      >
                        {b.name}
                        {b.zh.size > 0 && <span className="text-slate-500 ml-1">{[...b.zh][0]}</span>}
                        {b.orig && (
                          <span className="ml-1 text-[10px] px-1 py-0.5 bg-brand-100 text-brand-900 rounded">原廠</span>
                        )}
                      </button>
                    ))}
                    {priced.length === 0 && <span className="text-xs text-slate-400">（無列價品項）</span>}
                  </div>
                  {unpriced.length > 0 && (
                    <div className="mt-1 text-[11px] text-slate-400 leading-relaxed">
                      未列價：{unpriced.map((b) => b.name).join('、')}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ))}
        <p className="text-[11px] text-slate-400">
          同一商品的不同規格合併為一個；未列價多為已無流通之舊品項。點商品名跳到該劑型品項表。
        </p>
      </div>
    </details>
  );
}
