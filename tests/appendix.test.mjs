/**
 * 附表解析與參照的回歸測試 —— 用真實資料跑真實產物。
 *
 * 起因：查 tofacitinib 點進 8.2.4.4. 等章節，📎 附表徽章是死路。
 * 兩層根因：附表名正規表示式有兩份走鐘（不吃「之X」）、
 * 以及 8.2.4.x 家族的附表本體根本不在章節 PDF 裡（健保署另外獨立發布）。
 */
import { readFileSync, readdirSync, existsSync } from 'node:fs';

const D = 'public/data';
const rules = {};
for (const f of readdirSync(`${D}/rules`)) {
  for (const s of JSON.parse(readFileSync(`${D}/rules/${f}`, 'utf8')).sections) rules[s.code] = s;
}

let fail = 0;
const ok = (c, m) => { console.log(`${c ? '✅' : '❌'} ${m}`); if (!c) fail += 1; };

// ── 1. 附表分片存在且解析出內容 ──
const appxDir = `${D}/appendix`;
ok(existsSync(appxDir), 'public/data/appendix/ 存在');
const files = existsSync(appxDir) ? readdirSync(appxDir) : [];
ok(files.length >= 70, `附表分片 ${files.length} 個（應 ≥70）`);

// ── 2. 金絲雀：tofacitinib 需要的附表 ──
const a22 = JSON.parse(readFileSync(`${appxDir}/附表二十二之一.json`, 'utf8'));
ok(a22.tables.length >= 1, `附表二十二之一 解析出 ${a22.tables.length} 張表格`);
ok(a22.clauses.length >= 10, `附表二十二之一 有 ${a22.clauses.length} 段內容`);
ok(Boolean(a22.url), '附表二十二之一 帶官方 PDF 連結');
ok(a22.clauses.some((c) => c.text.includes('乾癬性關節炎')),
   '附表二十二之一 內容含「乾癬性關節炎」');

// ── 3. tofacitinib 的章節不再有死路 ──
for (const code of ['8.2.4.4.', '8.2.4.5.', '8.2.4.2.', '8.2.4.3.', '8.2.4.9.1.']) {
  const refs = rules[code]?.appx_refs ?? [];
  const dead = refs.filter((x) => x.missing);
  ok(refs.length > 0 && dead.length === 0,
     `${code} 的 ${refs.length} 個附表參照全部指得到本體`);
}

// ── 4. 回歸保護：dupilumab 的附表三十二仍走章節內本體 ──
const d = rules['13.17.1.']?.appx_refs?.find((x) => x.name === '附表三十二');
ok(d?.kind === 'section' && d?.host === '13.17.2.',
   `附表三十二 仍指向章節 13.17.2.（實際 kind=${d?.kind} host=${d?.host}）`);
ok((rules['13.17.2.']?.tables ?? []).length === 13,
   `13.17.2. 仍是 ${(rules['13.17.2.']?.tables ?? []).length} 張表格（回歸保護）`);

// ── 5. 基底名 → 官方子檔的回退 ──
const v = Object.values(rules).flatMap((s) => s.appx_refs ?? [])
  .find((x) => x.name === '附表二' && x.variants?.length);
ok(v && v.variants.join(',') === '附表二-A,附表二-B,附表二-C,附表二-D',
   `附表二 回退到 ${v?.variants?.join('、')}（且依數字序排列）`);

// ── 6. 仿單連結覆蓋 ──
const derm = JSON.parse(readFileSync(`${D}/derm.json`, 'utf8'));
const withIns = derm.ing.filter((i) => (i.ins ?? 0) > 0).length;
ok(withIns / derm.ing.length >= 0.90,
   `皮膚科學名有仿單連結 ${withIns}/${derm.ing.length} (${Math.round(withIns / derm.ing.length * 100)}%)`);
for (const k of ['ISOTRETINOIN', 'DUPILUMAB', 'CYCLOSPORIN', 'ACYCLOVIR']) {
  const i = derm.ing.find((x) => x.k === k);
  ok((i?.ins ?? 0) > 0, `${k} 有 ${i?.ins} 個品項附仿單連結`);
}

console.log(fail ? `\n❌ ${fail} 項失敗` : '\n✅ 全部通過');
process.exit(fail ? 1 : 0);
