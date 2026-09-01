import { go } from '../lib/routes.js';

// ★ 健保署對「藥品給付規定」有逐節 PDF，對「醫療服務給付項目」沒有 ——
//   官方只發布整份支付標準壓縮檔（.doc）。所以這裡給的是官方發布頁與
//   官方查詢系統，不編造不存在的逐項 PDF 連結。
const OFFICIAL_DOC = 'https://www.nhi.gov.tw/ch/lp-3778-1.html';
// 查詢系統是 POST + sessionStorage，沒有單一代碼的深連結，
// 所以只連到入口並告訴醫師要貼哪個代碼 —— 不編一個看起來像深連結的假網址。
const OFFICIAL_QUERY = 'https://info.nhi.gov.tw/INAE5000/INAE5001S01';

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

      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <h3 className="text-sm font-semibold">官方原文出處</h3>
        {item.ch ? (
          <p className="mt-1.5 text-sm text-slate-700">
            收錄於《全民健康保險醫療服務給付項目及支付標準》
            <b className="text-brand-700">{item.ch}</b>
          </p>
        ) : (
          <p className="mt-1.5 text-sm text-slate-500">
            官方支付標準查詢未提供本醫令的章節定位。
          </p>
        )}
        <div className="mt-2 flex flex-col gap-1.5 text-sm">
          <a
            href={OFFICIAL_DOC}
            target="_blank"
            rel="noreferrer"
            className="text-brand-700 underline"
          >
            📄 支付標準原文下載（健保署發布頁，整份 .doc 壓縮檔）↗
          </a>
          <a
            href={OFFICIAL_QUERY}
            target="_blank"
            rel="noreferrer"
            className="text-brand-700 underline"
          >
            🔍 健保署支付標準查詢系統（在「診療項目代碼」貼上 {item.k} 可核對）↗
          </a>
        </div>
        <p className="mt-2 text-[11px] text-slate-500">
          健保署對醫療處置未發布逐項 PDF（僅藥品給付規定有），
          因此以章節定位＋官方發布頁作為出處。
        </p>
      </div>

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
