import { useEffect, useState } from 'react';
import { go } from '../lib/routes.js';

const BASE = `${import.meta.env.BASE_URL}data`;

const KIND = {
  revised: ['改版', 'bg-sky-100 text-sky-900'],
  // 檔名日期沒變但 sha256 變了 —— 健保署有前科會修錯字不改日期，這種最值得警示
  silent_edit: ['靜默改檔', 'bg-rose-100 text-rose-900'],
};

export default function Changes() {
  const [log, setLog] = useState(null);
  const [detail, setDetail] = useState({});

  useEffect(() => {
    fetch(`${BASE}/changelog.json`).then((r) => r.json()).then(setLog).catch(() => setLog({ changes: [] }));
  }, []);

  const toggle = async (c) => {
    if (detail[c.code]) return setDetail((d) => ({ ...d, [c.code]: null }));
    const r = await fetch(`${BASE}/diff/${c.diff_file}`).then((x) => x.json()).catch(() => null);
    setDetail((d) => ({ ...d, [c.code]: r }));
  };

  if (!log) return <p className="mt-6 text-slate-500">載入中…</p>;

  return (
    <div className="mt-5 space-y-3">
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <h2 className="font-semibold">給付規定異動</h2>
        <p className="text-sm text-slate-600 mt-1">
          最近一次比對：{log.generated_at}｜改版 {log.n_revised}、靜默改檔 {log.n_silent_edit}
          、新增 {log.new_sections_count ?? log.n_new}
        </p>
        <p className="text-[11px] text-slate-500 mt-1.5">
          健保署不提供條文歷史版本，本站每月抓取一次並保存快照，改版即產生 diff。
          「靜默改檔」指檔名生效日未變但內容雜湊變了 —— 通常是官方事後修訂錯字。
        </p>
      </div>

      {(log.changes ?? []).length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200 p-4 text-sm text-slate-600">
          本期沒有章節改版。
          {log.new_sections_count > 50 && `（首次建庫，${log.new_sections_count} 個章節皆為初次收錄）`}
        </div>
      ) : (
        (log.changes ?? []).map((c) => {
          const [label, cls] = KIND[c.kind] ?? ['異動', 'bg-slate-200 text-slate-800'];
          const d = detail[c.code];
          return (
            <div key={c.code} className="bg-white rounded-xl border border-slate-200 p-4">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <span className="font-mono text-sm text-brand-700">{c.code}</span>
                  <span className={`ml-2 text-xs px-2 py-0.5 rounded-full ${cls}`}>{label}</span>
                  <span className="ml-2 text-xs text-slate-500">生效 {c.eff}</span>
                </div>
                <button type="button" onClick={() => toggle(c)} className="text-xs text-brand-700 underline shrink-0">
                  {d ? '收合' : '看差異'}
                </button>
              </div>
              <div className="mt-1 text-xs text-slate-500">
                +{c.added} 句 / −{c.removed} 句（變動幅度 {(c.ratio * 100).toFixed(1)}%）
              </div>
              {d && (
                <div className="mt-3 space-y-2 text-sm">
                  {d.hunks.map((h, i) => (
                    <div key={i} className="rounded-lg border border-slate-200 overflow-hidden">
                      {h.removed.map((t, j) => (
                        <div key={`r${j}`} className="bg-rose-50 text-rose-900 px-3 py-1.5 whitespace-pre-wrap">
                          − {t}
                        </div>
                      ))}
                      {h.added.map((t, j) => (
                        <div key={`a${j}`} className="bg-emerald-50 text-emerald-900 px-3 py-1.5 whitespace-pre-wrap">
                          + {t}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })
      )}
      <button type="button" onClick={() => go('#/')} className="text-sm text-brand-700 underline">
        ← 回搜尋
      </button>
    </div>
  );
}
