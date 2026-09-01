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
        // ★ 只 precache app shell。給付規定每月改版，把 data/*.json 放進 precache
        //   會讓醫師看到上個月的條文而不自知 —— 比查不到更危險。
        globPatterns: ['**/*.{js,css,html,svg,png,ico,webmanifest}'],
        runtimeCaching: [
          {
            urlPattern: /\/data\/.*\.json$/,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'nhi-data-v1',
              networkTimeoutSeconds: 3,
              expiration: { maxEntries: 600, maxAgeSeconds: 60 * 60 * 24 * 45 },
            },
          },
        ],
        // products 分片有 455 個，maxEntries 200 會讓 LRU 把分片踢掉，
        // PWA 離線時點某些藥會失敗
        maxEntries: 600,
      },
    })]),
  ],
  };
});
