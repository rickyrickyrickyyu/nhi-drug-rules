/**
 * 條文起點判定 —— 從 RuleSectionPanel 抽出來，因為它有一個真實踩過的坑，
 * 需要用真實資料回歸測試（見 tests/relevance.test.mjs）。
 * 元件裡的函式測不到，抽成模組才能被測試載入 —— 不做第二份實作，避免走鐘。
 */
/** 詞邊界比對：valaciclovir 不可以被當成 aciclovir。 */
export function mentionsDrug(text, names) {
  const low = text.toLowerCase();
  return names.some((n) => {
    const esc = n.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return new RegExp(`(?<![a-z])${esc}(?![a-z])`).test(low);
  });
}

/**
 * 挑出與該學名最相關的條文起點。
 *
 * 10.7.1.1. 同時規範 acyclovir、famciclovir、valaciclovir，第 1 項整段都在講
 * acyclovir。查 famciclovir 的醫師先看到 acyclovir 的適應症清單，在門診會誤導。
 *
 * ★ 這裡曾經有兩個疊在一起的 bug，查 aciclovir 會被丟到別的藥的條文：
 *   1. 拼法：學名鍵是 WHO INN 的 Aciclovir(i)，條文寫美式 Acyclovir(y)，
 *      「第 1 項是不是本藥」的守門條件因此失效，誤判成別的藥而決定跳段。
 *   2. 子字串：接著找「含 aciclovi 的條文」，valaciclovir 含 aciclovir，
 *      於是跳到第 2 項（famciclovir／valaciclovir）—— 完全不是本藥的規定。
 *   任一個 bug 單獨存在都不會出事，兩個湊在一起才會。
 *
 * ★ 現在的原則是 fail-safe：只有能「正面指認」前面那些項屬於某個**別的藥**、
 *   而且後面確實有一段（詞邊界）提到本藥，才跳。任何一點不確定就從頭顯示 ——
 *   最壞情況只是多讀幾行，不會把別的藥的適應症當成本藥的。
 *
 * 回傳 { start, skipped } —— skipped 是被略過那段所規範的藥名，
 * UI 必須把它寫出來，否則「前 N 項規範其他藥品」只是個沒被驗證的斷言，
 * 跳錯時文案還會幫它圓謊。
 */
export function relevantStart(clauses, names) {
  const none = { start: 0, skipped: null };
  if (!names?.length || clauses.length <= 3) return none;

  // 第 1 項開頭必須是「1.某某藥名：」的形式，才有「前面在講別的藥」這回事。
  // 13.4. 第 1 項是「1.限皮膚科專科醫師使用。」，三項都適用 isotretinoin，
  // 無條件跳段會略過最關鍵的第 1、2 項。
  const lead = /^\s*\d+\s*[.、]\s*([A-Za-z][A-Za-z-]{5,})/.exec(clauses[0].text);
  if (!lead) return none;
  if (mentionsDrug(lead[1], names)) return none;      // 第 1 項就是本藥 → 不跳

  const hit = clauses.findIndex((c) => mentionsDrug(c.text, names));
  if (hit <= 0) return none;                          // 找不到本藥 → 寧可全顯示
  for (let i = hit; i >= 0; i--) {
    if ((clauses[i].level ?? 0) === 1) {
      return i > 0 ? { start: i, skipped: lead[1] } : none;
    }
  }
  return { start: hit, skipped: lead[1] };
}

