import { useEffect, useState } from 'react';

import { loadAppendix } from '../hooks/useData.js';
import { go } from '../lib/routes.js';
import ClauseBody from './ClauseBody.jsx';
import RuleTable from './RuleTable.jsx';

/**
 * 健保署獨立附表的檢視頁。
 *
 * ★ 為什麼需要獨立一頁：
 *   8.2.4.x 生物製劑家族的附表本體不在章節 PDF 裡（那裡只有「◎附表二十二之一：…」
 *   這種引用行），健保署把它們當獨立檔案發布。而同一個附表常被多個章節引用
 *   —— 附表二十二之一 就同時被乾癬性關節炎的好幾節指到。給它一頁、各章節指過來，
 *   內容只有一份，與跨章節附表（13.17.2. 的 EASI）走同樣的「跳過去看」邏輯。
 *
 * ★ 渲染完全沿用既有元件（ClauseBody + RuleTable），不另寫一套 ——
 *   附表和條文的表格還原走的是同一條路，看起來就該一樣。
 */
export default function AppendixView({ name }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    setData(null);
    setError(null);
    loadAppendix(name)
      .then((d) => { if (alive) setData(d); })
      .catch((e) => { if (alive) setError(String(e.message ?? e)); });
    return () => { alive = false; };
  }, [name]);

  if (error) {
    return (
      <div className="mt-5">
        <p className="text-slate-600">找不到「{name}」的內容。</p>
        <button type="button" onClick={() => go('#/')} className="text-sm text-brand-700 underline">
          回搜尋
        </button>
      </div>
    );
  }
  if (!data) return <p className="mt-6 text-slate-500">載入中…</p>;

  // 條文裡已就地嵌回的表格不重複顯示；沒嵌回的（PDF 文字流順序對不上）附在最後
  const used = new Set(
    [...(data.clauses ?? []).map((c) => c.text ?? '').join('\n')
      .matchAll(/TB(\d+)/g)].map((m) => Number(m[1])),
  );

  return (
    <div className="mt-4 space-y-3">
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-lg font-bold text-brand-900">{data.name}</h2>
            {data.title && (
              <p className="text-sm text-slate-600 mt-0.5">{data.title}</p>
            )}
          </div>
          {data.url && (
            <a
              href={data.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs shrink-0 px-2.5 py-1.5 rounded-lg border border-slate-300 hover:bg-slate-50"
            >
              官方原文 PDF ↗
            </a>
          )}
        </div>
        <p className="mt-1.5 text-[11px] text-slate-500">
          健保署獨立發布之附表
          {data.updated && `｜官方標示更新日 ${data.updated}`}
          ｜以下為由官方 PDF 還原之結果，一律以官方原文為準。
        </p>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 p-4 text-[15px] leading-relaxed text-slate-800">
        {(data.clauses ?? []).map((c, i) => (
          <ClauseBody key={i} text={c.text} tables={data.tables} />
        ))}
        {(data.tables ?? []).filter((_, i) => !used.has(i)).map((t, i) => (
          <RuleTable key={`x${i}`} table={t} />
        ))}
      </div>

      <button type="button" onClick={() => go('#/')} className="text-sm text-brand-700 underline">
        ← 回搜尋
      </button>
    </div>
  );
}
