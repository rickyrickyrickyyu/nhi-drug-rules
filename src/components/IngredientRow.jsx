import { go } from '../lib/routes.js';
import { priceRange } from '../lib/format.js';

const ROUTE_ICON = {
  PO: '💊', INJ: '💉', TOP: '🧴', OPH: '👁', OTIC: '👂',
  NASAL: '👃', INH: '🫁', TD: '🩹', PR: '💊', PV: '💊', DIAL: '🧪', OTHER: '•',
};

/**
 * 搜尋結果的一列 = 一個「學名」，不是一個品項。
 * 搜 acyclovir 不該吐 21 個商品名 —— 但每列必須帶出中英商品名，
 * 否則醫師無法確認搜到的是不是自己要的那支藥。
 */
export default function IngredientRow({ hit }) {
  const { item, matched, fieldLabel, field } = hit;
  // 學名以外的命中都要說明理由 —— 醫師必須能確認搜到的是不是自己想的那支藥
  const showWhy = field && field !== 'inn';
  const f = item.f ?? {};

  return (
    <button
      type="button"
      onClick={() => go(`#/i/${encodeURIComponent(item.k)}`)}
      className="w-full text-left bg-white rounded-xl border border-slate-200 hover:border-brand-600
                 hover:shadow-sm transition p-4 mb-2.5"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-semibold text-lg leading-tight text-slate-900">{item.n}</div>
          <div className="text-sm text-slate-500 mt-0.5 truncate">
            {(item.z ?? []).slice(0, 3).join('、')}
            {item.z?.length > 0 && item.a?.length > 0 && ' · '}
            {(item.a ?? []).slice(0, 3).join(' / ')}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          {f.pa === 1 && (
            <span className="text-xs font-medium bg-amber-100 text-amber-900 px-2 py-0.5 rounded-full whitespace-nowrap">
              ⚠ 事前審查
            </span>
          )}
          {f.sp?.length > 0 && (
            <span className="text-xs bg-sky-100 text-sky-900 px-2 py-0.5 rounded-full whitespace-nowrap">
              限{f.sp.join('/')}專科
            </span>
          )}
        </div>
      </div>

      {/* ★ 劑型分組：同學名的口服／注射／外用往往掛不同章節，這是全案核心 */}
      <div className="mt-2.5 space-y-1">
        {(item.r ?? []).map((r) => (
          <div key={r.ro} className="flex items-baseline gap-2 text-sm">
            <span className="w-24 shrink-0 text-slate-600 whitespace-nowrap">
              {ROUTE_ICON[r.ro]} {r.l} <span className="text-slate-400">{r.np}</span>
            </span>
            <span className="text-slate-700 truncate flex-1 min-w-0">
              {r.bp?.length ? r.bp.join('、') : <span className="text-slate-400">—</span>}
              {r.np > (r.bp?.length ?? 0) && <span className="text-slate-400"> 等</span>}
            </span>
            <span className="text-xs text-slate-400 shrink-0 hidden sm:inline">{priceRange(r.pr)}</span>
          </div>
        ))}
      </div>

      {item.s?.length > 0 && (
        <div className="mt-2 text-xs text-slate-500 truncate">📋 {item.s.join(' · ')}</div>
      )}
      {showWhy && (
        <div className="mt-1.5 text-xs text-brand-700">
          透過{fieldLabel} <mark>{matched}</mark> 命中
        </div>
      )}
    </button>
  );
}
