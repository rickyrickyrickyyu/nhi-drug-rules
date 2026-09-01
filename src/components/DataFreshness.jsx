import { useState } from 'react';

import { isOffline } from '../hooks/useData.js';

const BASE = `${import.meta.env.BASE_URL}data`;
const STALE_DAYS = 45;   // 月更 + GitHub cron 可能延遲，45 天才算過期

/**
 * 資料新鮮度。給付規定每月改版，讓醫師看到上個月的條文比查不到更危險，
 * 所以快照日期必須常駐、過期必須主動警告。
 *
 * 「檢查更新」按鈕會繞過 Service Worker 直接向伺服器要 meta.json，
 * 比對後告知使用者本機快取是不是已經落後。
 */
export default function DataFreshness({ meta, repoUrl }) {
  const [state, setState] = useState({ checking: false, msg: null });

  const ageDays = meta?.built
    ? Math.floor((Date.now() - new Date(meta.built).getTime()) / 86400000)
    : null;
  const stale = ageDays != null && ageDays > STALE_DAYS;

  // 離線版沒有網路可查，也不該嘗試連外（會被防毒視為可疑行為）
  const offline = isOffline();

  const check = async () => {
    setState({ checking: true, msg: null });
    try {
      // cache: 'reload' 強制繞過 SW 與瀏覽器快取，否則檢查到的還是舊的
      const r = await fetch(`${BASE}/meta.json?t=${Date.now()}`, { cache: 'reload' });
      const fresh = await r.json();
      if (fresh.built !== meta?.built) {
        setState({ checking: false, msg: `伺服器上有更新的資料（${fresh.built}），重新整理即可套用。` });
      } else {
        setState({ checking: false, msg: `已是最新（資料快照 ${fresh.built}）。` });
      }
    } catch {
      setState({ checking: false, msg: '無法連線，目前顯示的是離線快取內容。' });
    }
  };

  return (
    <div className={`rounded-xl border p-4 ${stale ? 'border-amber-300 bg-amber-50' : 'border-slate-200 bg-white'}`}>
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <div>
          <span className="text-sm font-medium">資料快照：{meta?.built ?? '—'}</span>
          {ageDays != null && (
            <span className="text-xs text-slate-500 ml-2">（{ageDays} 天前）</span>
          )}
        </div>
        <div className="flex gap-3 shrink-0">
          {!offline && (
          <button
            type="button"
            onClick={check}
            disabled={state.checking}
            className="text-xs px-2.5 py-1 rounded-lg border border-slate-300 hover:bg-slate-50 disabled:opacity-50"
          >
            {state.checking ? '檢查中…' : '檢查更新'}
          </button>
          )}
          {repoUrl && !offline && (
            <a
              href={`${repoUrl}/actions/workflows/monthly-update.yml`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs px-2.5 py-1 rounded-lg border border-slate-300 hover:bg-slate-50"
            >
              立即重抓資料 ↗
            </a>
          )}
        </div>
      </div>
      {offline && (
        <p className="mt-2 text-sm text-slate-700">
          這是離線版，無法自動檢查更新。請向提供者索取新版檔案。
        </p>
      )}
      {stale && (
        <p className="mt-2 text-sm text-amber-900">
          ⚠️ 資料已超過 {STALE_DAYS} 天未更新，可能與現行給付規定不符。請按「立即重抓資料」或以健保署公告為準。
        </p>
      )}
      {state.msg && <p className="mt-2 text-sm text-slate-700">{state.msg}</p>}
      <p className="mt-2 text-[11px] text-slate-500">
        自動更新排程：每月 6 日增量更新；每年 1 月與 7 月完整重抓全部章節並比對雜湊，
        以偵測官方「改內容但不改生效日」的靜默改檔。
      </p>
    </div>
  );
}
