/**
 * 仿單適應症（食藥署許可證資料）。
 *
 * ★ 必須與健保條文在視覺上強烈分離。仿單有的健保經常不給付 —— 那個落差正是
 *   臨床上最常被核刪的地方，也正是本站存在的理由。混在一起顯示會誤導。
 */
export default function TfdaIndication({ indications, routeLabel }) {
  const list = indications ?? [];
  if (!list.length) return null;

  return (
    <div className="rounded-xl border border-dashed border-amber-300 bg-amber-50/60 p-4 mb-3">
      <div className="flex items-baseline justify-between gap-2">
        <h4 className="text-sm font-semibold text-amber-900">
          仿單適應症（{routeLabel}）
        </h4>
        <span className="text-[11px] text-amber-800 shrink-0">食藥署許可證資料</span>
      </div>
      <p className="mt-1 text-[11px] text-amber-800">
        這是藥證核准的適應症，<b>不等於健保給付範圍</b>。健保給付條件以上方條文為準。
      </p>
      <ul className="mt-2 space-y-2">
        {list.map((ind, i) => (
          <li key={i} className="text-sm text-slate-800 leading-relaxed">
            <div className="whitespace-pre-wrap">{ind.text}</div>
            <div className="mt-0.5 text-[11px] text-slate-500">
              {ind.n} 個品項
              {ind.state === 'stale' && (
                <span className="ml-1.5 text-amber-800">
                  ⚠ 對應許可證已註銷／已廢止，仿單資訊可能過時
                </span>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
