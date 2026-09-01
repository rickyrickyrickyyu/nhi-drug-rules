import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig(({ mode }) => {
  // 離線版：資料內嵌成單一 HTML，用 file:// 開，所以 base 必須是相對路徑，
  // 且不能有 Service Worker（file:// 下無法註冊且會噴 console 錯誤嚇到使用者）
  const offline = mode === 'offline';

  return {
  base: offline ? './' : '/nhi-drug-rules/',
  build: offline
    ? {
        outDir: 'dist-offline',
        assetsInlineLimit: 100_000_000,
        cssCodeSplit: false,
        rollupOptions: { output: { inlineDynamicImports: true } },
      }
    : {},
  plugins: [
    react(),
    tailwindcss(),
    ...(offline ? [] : [VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: '皮膚科健保給付規定查詢',
        short_name: '健保給付',
        lang: 'zh-TW',
        display: 'standalone',
        background_color: '#ffffff',
        theme_color: '#0f766e',
        icons: [{ src: 'icon-512.png', sizes: '512x512', type: 'image/png' }],
      },
      workbox: {
        // ★ 只 precache 有雜湊檔名的靜態資源，**不含 index.html**。
        //   index.html 是唯一指向「哪一版 bundle」的入口，一旦被 precache，
        //   新版部署後使用者第一次打開拿到的仍是舊 HTML → 舊 JS → 舊畫面，
        //   而且畫面上毫無線索。對每月改版的給付規定，那等於看到上個月的條文。
        globPatterns: ['**/*.{js,css,svg,png,ico,webmanifest}'],
        // navigateFallback 預設會拿 precache 的 index.html 回應所有導覽，
        // 等於繞過上面那條規則，必須關掉。本站是 hash 路由，所有導覽都指向
        // 同一個網址，離線時由下面的 NetworkFirst 從快取取回，不會開天窗。
        navigateFallback: null,
        runtimeCaching: [
          {
            // HTML 一律優先走網路（只有 0.8 KB，成本可忽略），
            // 連不上才用快取 —— 這樣「有網路時永遠是最新版」。
            urlPattern: ({ request }) => request.mode === 'navigate',
            handler: 'NetworkFirst',
            options: {
              cacheName: 'nhi-shell-v1',
              networkTimeoutSeconds: 4,
              expiration: { maxEntries: 4, maxAgeSeconds: 60 * 60 * 24 * 180 },
            },
          },
          {
            urlPattern: /\/data\/.*\.json$/,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'nhi-data-v1',
              networkTimeoutSeconds: 3,
              // ★ products 分片有 455 個，原本的 maxEntries: 200 會讓 LRU 把
              //   分片踢掉，PWA 離線時點某些藥會失敗。maxEntries 只在
              //   expiration 內合法，寫在 workbox 頂層會讓 build 直接失敗。
              expiration: { maxEntries: 600, maxAgeSeconds: 60 * 60 * 24 * 45 },
            },
          },
        ],
      },
    })]),
  ],
  };
});
