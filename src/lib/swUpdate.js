/**
 * Service Worker 換版後強制重新載入一次。
 *
 * ★ 要解決的問題：
 *   vite-plugin-pwa 的 registerType: 'autoUpdate' 會設 skipWaiting + clientsClaim，
 *   新的 SW 確實會立刻接管 —— 但「已經渲染出來的那一頁」還是舊的 JS 與舊的
 *   app shell，要等使用者自己再重整一次才會看到新版。
 *
 *   對每月改版的健保給付規定來說，這代表醫師更新後第一次打開看到的是
 *   上個月的版本，而且畫面上沒有任何線索告訴他這件事 —— 比查不到更危險。
 *
 * ★ 為什麼要判斷「原本就有 controller」：
 *   clientsClaim 會讓首次造訪（原本沒有 SW）也觸發 controllerchange。
 *   那次不是換版，是第一次安裝，重整只會讓首開閃一下。
 *   只有「本來就有舊 SW、現在被新的取代」才需要重整。
 *
 * ★ 為什麼用 sessionStorage 上鎖：
 *   萬一 SW 反覆接管（安裝失敗重試），無條件 reload 會變成無限重整迴圈，
 *   在門診電腦上等同當機。一個分頁最多只自動重整一次。
 */
const ONCE_KEY = 'nhi.sw-reloaded';

export function watchSwUpdate() {
  const sw = navigator.serviceWorker;
  if (!sw) return;

  // 註冊當下就有 controller = 這台裝置已經裝過舊版
  const hadController = Boolean(sw.controller);

  sw.addEventListener('controllerchange', () => {
    if (!hadController) return;             // 首次安裝，不是換版
    try {
      if (sessionStorage.getItem(ONCE_KEY)) return;
      sessionStorage.setItem(ONCE_KEY, '1');
    } catch {
      // 無痕模式下 sessionStorage 會丟例外。這時寧可不自動重整，
      // 也不要冒無限迴圈的風險。
      return;
    }
    window.location.reload();
  });
}
