import { go } from '../lib/routes.js';

/** 頁尾常駐：資料快照日期 + 免責聲明。這比免責文字本身更有效 —— 讓「以官方為準」可一鍵執行。 */
export default function Footer({ meta, offline }) {
  return (
    <footer className="mt-8 pt-4 border-t border-slate-200 text-xs text-slate-500 leading-relaxed">
      {offline && (
        <div className="mb-2 bg-amber-50 border border-amber-200 text-amber-900 rounded-lg px-3 py-2">
          ⚠️ 目前為離線快取內容，快照日期 {meta?.built ?? '未知'}，可能已過期。
        </div>
      )}
      <p>
        非官方工具｜資料來源：衛生福利部中央健康保險署・食品藥物管理署開放資料
        （政府資料開放授權條款第 1 版）
      </p>
      <p className="mt-1">
        資料快照：<b>{meta?.built ?? '—'}</b>｜給付規定以健保署最新公告為準，申報結果由使用者自負。
      </p>
      <p className="mt-1">
        <a href="https://www.nhi.gov.tw/ch/np-2505-1.html" target="_blank" rel="noopener noreferrer"
           className="underline">官方給付規定原文 ↗</a>
        <button type="button" onClick={() => go('#/changes')} className="underline ml-3">
          給付規定異動
        </button>
        <button type="button" onClick={() => go('#/about')} className="underline ml-3">
          關於本站與完整免責聲明
        </button>
      </p>
    </footer>
  );
}
