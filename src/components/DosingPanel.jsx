import { useState } from 'react';

// ★ 這裡曾經是 `DRPIQ1000Result?licId=${licId}` —— 實測 404，是編出來的網址。
//   食藥署的許可證明細頁吃的是內部 licBaseId（不是許可證字號，我們也拿不到），
//   而查詢頁有驗證碼，無法自動組深連結。所以只連查詢入口，並告訴醫師要貼什麼。
const FDA_SEARCH = 'https://lmspiq.fda.gov.tw/web/DRPIQ/license-search';
// 仿單全文在食藥署「藥品仿單查詢平台」，該站明訂未經同意不得重製轉載，
// 因此本站只連過去、不鏡射任何仿單內容。
const FDA_INSERT = 'https://mcp.fda.gov.tw/im';

/**
 * 劑量資訊。
 *
 * ★ 顯示的永遠是健保條文原句，不是被程式重組過的敘述 —— 系統只做「選句」。
 * ★ 前置用藥（申請本藥前須先試過的其他藥）必須獨立區塊、明寫「不是本藥用法」。
 *   13.17.1. 裡的「Methotrexate 每週15mg」是申請 dupilumab 的條件，
 *   照著它開 dupilumab 會出事。
 */
export default function DosingPanel({ dosing, innDisplay, licenceNo, doseTfda = [] }) {
  const [showPrereq, setShowPrereq] = useState(false);
  const [showAllTfda, setShowAllTfda] = useState(false);
  const direct = dosing?.direct ?? [];
  const sole = dosing?.section_sole ?? [];
  const prereq = dosing?.prerequisite ?? [];
  const own = [...direct, ...sole];

  if (!own.length && !prereq.length && !doseTfda.length) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-4 mb-3 text-sm">
        <p className="text-slate-600">
          健保條文未載明 {innDisplay} 的使用劑量，食藥署開放資料也未登載本藥的用法用量。
        </p>
        <p className="mt-1 text-[12px] text-slate-500">
          請查{' '}
          <a href={FDA_INSERT} target="_blank" rel="noopener noreferrer"
             className="text-brand-700 underline">食藥署藥品仿單查詢平台 ↗</a>
          {licenceNo && <>（許可證字號 <b>{licenceNo}</b>）</>}
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-brand-600/30 bg-brand-50/40 p-4 mb-3">
      {own.length > 0 && (
        <>
          <h4 className="text-sm font-semibold text-brand-900">
            💊 健保給付規定所載之使用劑量
          </h4>
          <p className="text-[11px] text-slate-600 mt-0.5">
            以下為條文原句，是<b>給付條件的一部分</b>（開超過不給付），
            不是仿單的完整用法用量。
          </p>
          <ul className="mt-2 space-y-2">
            {own.map((d, i) => (
              <li key={i} className="text-[15px] leading-relaxed text-slate-800">
                <div className="whitespace-pre-wrap">{d.quote}</div>
                <div className="mt-0.5 text-[11px] text-slate-500">
                  出處 {d.section}
                  {d.effective_date && ` · ${d.effective_date} 生效`}
                  {sole.includes(d) && ' · 本節僅規範此藥'}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      {doseTfda.length > 0 && (
        <div className={own.length ? 'mt-3 pt-3 border-t border-brand-600/20' : ''}>
          <h4 className="text-sm font-semibold text-slate-800">
            📋 仿單登載之用法用量（食藥署開放資料）
          </h4>
          <p className="text-[11px] text-slate-600 mt-0.5">
            以下為<b>藥證登載原文逐字轉錄</b>，與健保給付無關；同一學名不同藥廠
            可能不同，每段都標示其許可證字號與品名。
          </p>
          <ul className="mt-2 space-y-2">
            {(showAllTfda ? doseTfda : doseTfda.slice(0, 2)).map((g, i) => (
              <li key={i} className="bg-white rounded-lg border border-slate-200 px-3 py-2">
                <div className="text-[15px] leading-relaxed text-slate-800 whitespace-pre-wrap">
                  {g.text}
                </div>
                {g.adjust?.length > 0 && (
                  <div className="mt-2 rounded-lg bg-sky-50 border border-sky-200 px-2.5 py-2">
                    <div className="text-[11px] font-medium text-sky-900">
                      族群／肝腎功能相關敘述（原句摘出，未改寫）
                    </div>
                    <ul className="mt-1 space-y-0.5">
                      {g.adjust.map((a, j) => (
                        <li key={j} className="text-[13px] text-sky-900">・{a}</li>
                      ))}
                    </ul>
                  </div>
                )}
                <div className="mt-1 text-[11px] text-slate-500">
                  {g.licences?.[0]}
                  {g.brands?.[0] && `｜${g.brands[0]}`}
                  {g.n_products > 1 && `　等 ${g.n_products} 個品項適用同一段原文`}
                </div>
              </li>
            ))}
          </ul>
          {doseTfda.length > 2 && (
            <button
              type="button"
              onClick={() => setShowAllTfda((v) => !v)}
              className="mt-1.5 text-xs text-brand-700 underline"
            >
              {showAllTfda ? '收合' : `其他 ${doseTfda.length - 2} 段不同藥廠的用法用量`}
            </button>
          )}
          <p className="mt-2 text-[11px] text-slate-500">
            食藥署開放資料只登載部分藥品的用法用量，且不含完整的肝腎功能調整、
            禁忌與交互作用。完整仿單請查{' '}
            <a href={FDA_INSERT} target="_blank" rel="noopener noreferrer"
               className="text-brand-700 underline">藥品仿單查詢平台 ↗</a>
            {' 或 '}
            <a href={FDA_SEARCH} target="_blank" rel="noopener noreferrer"
               className="text-brand-700 underline">許可證查詢 ↗</a>
            {licenceNo && <>（輸入 <b>{licenceNo}</b>）</>}
          </p>
        </div>
      )}

      {prereq.length > 0 && (
        <div className={own.length ? 'mt-3 pt-3 border-t border-brand-600/20' : ''}>
          <button
            type="button"
            onClick={() => setShowPrereq((v) => !v)}
            className="text-sm font-medium text-amber-900 text-left"
          >
            ⚠️ 申請條件：前置用藥的劑量（{prereq.length}）{showPrereq ? ' ▲' : ' ▼'}
          </button>
          <p className="text-[11px] text-amber-900 mt-0.5">
            以下劑量屬於<b>申請本藥給付前須完成的其他藥物治療</b>，
            <b>不是 {innDisplay} 的用法用量</b>。
          </p>
          {showPrereq && (
            <ul className="mt-2 space-y-2">
              {prereq.map((d, i) => (
                <li key={i} className="text-[14px] leading-relaxed text-slate-800 bg-amber-50 rounded-lg px-3 py-2">
                  <div className="whitespace-pre-wrap">{d.quote}</div>
                  <div className="mt-0.5 text-[11px] text-slate-500">
                    出處 {d.section}｜此處劑量屬於：{(d.for_drugs ?? []).join('、')}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
