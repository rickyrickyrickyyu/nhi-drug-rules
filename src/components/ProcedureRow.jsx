import { go } from '../lib/routes.js';

/** 處置的搜尋結果列。劑型分組對處置沒有意義，所以另做一個元件。 */
export default function ProcedureRow({ hit }) {
  const { item, matched, fieldLabel, field } = hit;
  const showWhy = field && field !== 'procName';

  return (
    <button
      type="button"
      onClick={() => go(`#/p/${encodeURIComponent(item.k)}`)}
      className="w-full text-left bg-white rounded-xl border border-slate-200 hover:border-brand-600
                 hover:shadow-sm transition p-4 mb-2.5"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-semibold text-lg leading-tight text-slate-900">
            🩺 {item.n}
          </div>
          {item.en && <div className="text-sm text-slate-500 mt-0.5 truncate">{item.en}</div>}
        </div>
        <div className="text-right shrink-0">
          <div className="font-mono text-xs text-brand-700">{item.k}</div>
          <div className="text-sm font-medium">
            {item.pt.toLocaleString()} <span className="text-xs text-slate-500">點</span>
          </div>
        </div>
      </div>
      {item.note && (
        <div className="mt-2 text-sm text-slate-600 line-clamp-2">{item.note}</div>
      )}
      {showWhy && (
        <div className="mt-1.5 text-xs text-brand-700">
          透過{fieldLabel} <mark>{matched}</mark> 命中
        </div>
      )}
    </button>
  );
}
