/**
 * 「畫面上這份資料，是不是伺服器上的最新版？」
 *
 * ★ 為什麼不能只靠 Service Worker 的 NetworkFirst：
 *   data/*.json 的 NetworkFirst 有 3 秒逾時 —— 醫院網路慢一點就會靜靜退回
 *   快取，畫面照常顯示，唯一的線索是「關於」頁裡那行小小的快照日期。
 *   給付規定每月改版，看到上個月的條文而不自知比查不到更危險，
 *   所以必須主動查、主動說，而且要能自己修好。
 *
 * ★ 為什麼比 data_fingerprint 不比 built：
 *   built 只到「日」，同一天內重跑 ETL 資料已經不同。
 *
 * ★ 為什麼要 session 上鎖：
 *   自動套用會清 SW 與快取再重載。萬一伺服器回的東西持續對不上
 *   （部署到一半、CDN 節點不一致），無條件重載就是無限迴圈，
 *   在門診電腦上等同當機。一個分頁最多自動修一次，之後只提示不重載。
 */
const ONCE_KEY = 'nhi.freshness-reloaded';

/** 繞過 SW 與 HTTP 快取直接問伺服器。回 null 代表問不到（離線、擋掉）。 */
export async function fetchServerMeta(base) {
  try {
    const r = await fetch(`${base}/meta.json?t=${Date.now()}`, { cache: 'reload' });
    if (!r.ok) return null;
    return await r.json();
  } catch {
    return null;
  }
}

export const stamp = (m) => m?.data_fingerprint ?? m?.built ?? null;

/** 清掉 SW 與所有快取後重新載入。醫師不該被要求去開 DevTools。 */
export async function hardReload() {
  try {
    const regs = await navigator.serviceWorker?.getRegistrations?.() ?? [];
    await Promise.all(regs.map((r) => r.unregister()));
    if (window.caches) {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    }
  } catch {
    // 清不掉也要重載：時間戳可以繞過 HTTP 快取
  }
  window.location.replace(
    `${window.location.pathname}?fresh=${Date.now()}${window.location.hash}`);
}

/** 這個分頁是否還可以自動修一次。 */
export function claimAutoFix() {
  try {
    if (sessionStorage.getItem(ONCE_KEY)) return false;
    sessionStorage.setItem(ONCE_KEY, '1');
    return true;
  } catch {
    return false;          // 無痕模式：寧可只提示，也不冒無限重載的風險
  }
}
