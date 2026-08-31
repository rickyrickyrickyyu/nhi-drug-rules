import { useEffect, useState } from 'react';
import { loadNotes, saveNotes, exportNotes } from '../lib/storage.js';

/**
 * 臨床註記：本機草稿層。
 *
 * 共用註記走 curation/clinical_notes/*.md 由使用者 commit，且必須明確標
 * publish: true 才會出現在公開網站 —— 這是 public repo 的隱私閘門。
 */
export default function ClinicalNote({ innKey }) {
  const [state, setState] = useState(() => loadNotes());
  const [draft, setDraft] = useState('');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setDraft(state.notes?.[innKey]?.text ?? '');
    setSaved(false);
  }, [innKey]);

  const commit = () => {
    const next = {
      ...state,
      notes: { ...state.notes, [innKey]: { text: draft, updated_at: new Date().toISOString() } },
    };
    setState(next);
    setSaved(saveNotes(next));
  };

  const download = () => {
    const blob = new Blob([exportNotes(state)], { type: 'text/markdown' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'clinical-notes.md';
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4">
      <div className="flex items-center justify-between">
        <h4 className="font-medium text-sm">我的臨床註記</h4>
        <button type="button" onClick={download} className="text-xs text-brand-700 underline">
          匯出全部
        </button>
      </div>
      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        rows={3}
        placeholder="申請訣竅、常被核刪的原因、需附的表單…（只存在這台裝置，不會上傳）"
        className="mt-2 w-full text-sm border border-slate-300 rounded-lg px-3 py-2
                   focus:outline-none focus:border-brand-600 resize-y"
      />
      <p className="mt-1.5 text-[11px] text-slate-500">
        存在本機瀏覽器。iOS 請「加入主畫面」，否則 Safari 可能在 7 天未使用後清除；重要內容請匯出備份。
        {saved && <span className="text-brand-700 ml-1">已儲存</span>}
      </p>
    </div>
  );
}
