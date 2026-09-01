import { useEffect, useState } from 'react';
import { loadChapter } from '../hooks/useData.js';
import { go } from '../lib/routes.js';
import RuleSectionPanel from './RuleSectionPanel.jsx';

/**
 * 單一章節頁。跨節附表引用（13.17.1. → 13.17.2. 的 EASI 評分表）需要它，
 * 否則點了連結會落到空白頁。
 */
export default function SectionView({ slug }) {
  const [state, setState] = useState({ loading: true, section: null, error: null });
  const code = `${slug.replaceAll('-', '.')}.`;

  useEffect(() => {
    let alive = true;
    const ch = Number(code.split('.')[0]);
    loadChapter(ch)
      .then((r) => {
        if (!alive) return;
        const s = r.sections.find((x) => x.code === code);
        setState({ loading: false, section: s ?? null, error: s ? null : `查無章節 ${code}` });
      })
      .catch((e) => alive && setState({ loading: false, section: null, error: e.message }));
    return () => { alive = false; };
  }, [code]);

  return (
    <div className="mt-5">
      {state.loading && <p className="text-slate-500">載入中…</p>}
      {state.error && (
        <p className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg p-3">
          {state.error}
        </p>
      )}
      {state.section && <RuleSectionPanel section={state.section} />}
      <button type="button" onClick={() => history.back()} className="text-sm text-brand-700 underline">
        ← 返回
      </button>
      <button type="button" onClick={() => go('#/')} className="text-sm text-brand-700 underline ml-4">
        回搜尋
      </button>
    </div>
  );
}
