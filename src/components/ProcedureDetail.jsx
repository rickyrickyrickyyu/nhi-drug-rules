import { go } from '../lib/routes.js';

/**
 * 處置詳情。
 *
 * ★ 兩個必要警語（不可省略）：
 *   1. 「點」不是「元」—— 健保點數要乘浮動點值（約 0.85–0.95）才是實際給付
 *   2. CSV 單看一列看不出「同日不得併報」「互斥組合」等通則交互作用
 */
export default function ProcedureDetail({ item }) {
  if (!item) {
    return (
      <div className="mt-5">
        <p className="text-slate-500">查無此醫令。</p>
        <button type="button" onClick={() => go('#/')} className="text-sm text-brand-700 underline">
          回搜尋
        </button>
      </div>
    );
  }

  return (
    <div className="mt-5 space-y-3">
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-2xl font-bold">{item.n}</h2>
            {item.en && <div className="text-sm text-slate-500 mt-0.5">{item.en}</div>}
          </div>
          <div className="text-right shrink-0">
            <div className="font-mono text-sm text-brand-700">{item.k}</div>
            <div className="text-xl font-semibold">
              {item.pt.toLocaleString()} <span className="text-sm text-slate-500">點</span>
            </div>
          </div>
        </div>
        <p className="mt-1.5 text-[11px] text-slate-500">
          「點」非「元」：實際給付金額為點數乘以當季浮動點值（近年約 0.85–0.95）。
        </p>
        {item.z?.length > 0 && (
          <div className="mt-2 text-xs text-slate-500">
            也可用這些說法查到：{item.z.slice(0, 10).join('、')}
          </div>
        )}
      </div>

      {item.note ? (
        <div className="bg-white rounded-xl border border-slate-200 p-4">
          <h3 className="text-sm font-semibold">給付條件（官方備註原文）</h3>
          <div className="mt-2 text-[15px] leading-relaxed whitespace-pre-wrap text-slate-800">
            {item.note}
          </div>
          {item.note_more && (
            <p className="mt-2 text-[11px] text-amber-800">
              ⚠️ 備註過長已截斷，完整內容請查官方《醫療服務給付項目及支付標準》。
            </p>
          )}
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 p-4 text-sm text-slate-600">
          本醫令在支付標準中沒有個別備註。仍受支付標準通則約束。
        </div>
      )}

      <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
        ⚠️ 本頁僅列單一醫令的規定。<b>同日不得併報、互斥組合、部位計次</b>等限制
        規範於《全民健康保險醫療服務給付項目及支付標準》通則，本站未收錄，
        申報前請一併查閱。
      </div>

      <button type="button" onClick={() => go('#/')} className="text-sm text-brand-700 underline">
        ← 回搜尋
      </button>
    </div>
  );
}
