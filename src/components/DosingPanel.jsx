import { useState } from 'react';

const FDA_LIC = (licId) =>
  `https://lmspiq.fda.gov.tw/web/DRPIQ/DRPIQ1000Result?licId=${licId}`;

/**
 * 劑量資訊。
 *
 * ★ 顯示的永遠是健保條文原句，不是被程式重組過的敘述 —— 系統只做「選句」。
 * ★ 前置用藥（申請本藥前須先試過的其他藥）必須獨立區塊、明寫「不是本藥用法」。
 *   13.17.1. 裡的「Methotrexate 每週15mg」是申請 dupilumab 的條件，
 *   照著它開 dupilumab 會出事。
 */
export default function DosingPanel({ dosing, innDisplay, licenceId }) {
  const [showPrereq, setShowPrereq] = useState(false);
  const direct = dosing?.direct ?? [];
  const sole = dosing?.section_sole ?? [];
  const prereq = dosing?.prerequisite ?? [];
  const own = [...direct, ...sole];

  if (!own.length && !prereq.length) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-4 mb-3 text-sm">
        <span className="text-slate-600">
          健保條文未載明 {innDisplay} 的使用劑量。
        </span>
        {licenceId && (
          <a
            href={FDA_LIC(licenceId)}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-1 text-brand-700 underline"
          >
            查食藥署仿單 ↗
          </a>
        )}
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
            以下為條文原句，非仿單完整用法用量。仿單建議劑量與肝腎功能調整請查食藥署
            {licenceId && (
              <a href={FDA_LIC(licenceId)} target="_blank" rel="noopener noreferrer"
                 className="ml-1 text-brand-700 underline">許可證資料 ↗</a>
            )}
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
