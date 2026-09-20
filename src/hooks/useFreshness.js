import { useEffect, useState } from 'react';

import { isOffline } from './useData.js';
import { claimAutoFix, fetchServerMeta, hardReload, stamp } from '../lib/freshness.js';

const BASE = `${import.meta.env.BASE_URL}data`;

/**
 * 開站就比對一次「畫面上的資料」與「伺服器上的資料」。
 *
 * 舊版只有「關於」頁裡一顆要人主動按的「檢查更新」—— 等於把
 * 「你看到的是不是現行規定」這件事交給使用者自己想到要去查。
 * 現在改成開站自動比，對不上就在最上面講清楚，並自動修一次。
 *
 * 回 { outdated, serverBuilt, apply }：apply 是手動觸發的自救出口。
 */
export function useFreshness(meta) {
  const [server, setServer] = useState(null);

  useEffect(() => {
    if (!meta || isOffline()) return;          // 離線版不連外（防毒會視為可疑）
    let alive = true;
    fetchServerMeta(BASE).then((fresh) => {
      if (!alive || !fresh) return;            // 問不到就沿用現況，不打擾
      setServer(fresh);
      if (stamp(fresh) !== stamp(meta) && claimAutoFix()) hardReload();
    });
    return () => { alive = false; };
  }, [meta]);

  return {
    outdated: Boolean(server && stamp(server) !== stamp(meta)),
    serverBuilt: server?.built ?? null,
    apply: hardReload,
  };
}
