/**
 * 版本化 localStorage。沿用 duty-schedule 的做法：資料帶 version，
 * 讀取時跑 migrate()，寫入失敗靜默忽略（私密模式或空間不足時資料仍在記憶體）。
 *
 * ⚠️ iOS Safari 的 ITP 對「瀏覽器內開啟」的網站，7 天未互動會清掉 localStorage；
 *    加入主畫面的 PWA 才豁免。所以 UI 要提醒 iOS 使用者加入主畫面並提供匯出。
 */
const KEY = 'nhi-drug-rules.notes.v1';
const CURRENT = 1;

function migrate(raw) {
  if (!raw || typeof raw !== 'object') return { version: CURRENT, notes: {} };
  if (!raw.version) return { version: CURRENT, notes: raw.notes ?? {} };
  return { ...raw, version: CURRENT };
}

export function loadNotes() {
  try {
    return migrate(JSON.parse(localStorage.getItem(KEY) ?? 'null'));
  } catch {
    return { version: CURRENT, notes: {} };
  }
}

export function saveNotes(state) {
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...state, version: CURRENT }));
    return true;
  } catch {
    return false;
  }
}

export function exportNotes(state) {
  // ★ 原本這行寫「貼進 curation/clinical_notes/ 後 commit 即成為共用註記」——
  //   那是錯的，而且危險：本站的 repo 是公開的，沒有任何程式會讀那個目錄，
  //   照做只會把可能含病人資訊的註記推上公開 GitHub，且得不到任何功能。
  const lines = [
    '# 匯出的臨床註記',
    '#',
    '# ⚠️ 這份檔案可能含病人資訊，請留在本機或加密隨身碟。',
    '#    不要放進本專案資料夾，也不要 commit —— 本站 repo 是公開的。',
    '',
  ];
  for (const [key, v] of Object.entries(state.notes ?? {})) {
    if (!v?.text?.trim()) continue;
    lines.push(`---`, `key: ${key}`, `publish: false   # 改成 true 才會出現在公開網站`,
      `updated_at: ${v.updated_at ?? ''}`, `---`, v.text.trim(), '');
  }
  return lines.join('\n');
}
