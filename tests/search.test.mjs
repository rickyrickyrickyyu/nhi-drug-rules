import { readFileSync } from 'node:fs';
const src = readFileSync('src/lib/search.js', 'utf8').replace(/^export /gm, '');
const mod = await import('data:text/javascript;base64,' +
  Buffer.from(src + '\nexport { searchIngredients, fuzzyFallback, normalizeQuery };').toString('base64'));
const data = JSON.parse(readFileSync('public/data/derm.json', 'utf8')).ing;
const all = JSON.parse(readFileSync('public/data/all.json', 'utf8')).ing;

const cases = [
  ['isotretinoin', 'ISOTRETINOIN'], ['Roaccutane', 'ISOTRETINOIN'], ['羅可坦', 'ISOTRETINOIN'],
  ['口服A酸', 'ISOTRETINOIN'], ['A酸', 'ISOTRETINOIN'], ['13.4', 'ISOTRETINOIN'],
  ['D10BA01', 'ISOTRETINOIN'],
  ['Valtrex', 'VALACICLOVIR'], ['祛疹易', 'VALACICLOVIR'], ['valacyclovir', 'VALACICLOVIR'],
  ['acyclovir', 'ACYCLOVIR'], ['aciclovir', 'ACYCLOVIR'], ['Zovirax', 'ACYCLOVIR'],
  ['dupilumab', 'DUPILUMAB'], ['Dupixent', 'DUPILUMAB'], ['杜避炎', 'DUPILUMAB'],
  ['betamethasone', 'BETAMETHASONE (VALERATE)'],
  ['isotretinoim', 'ISOTRETINOIN'],   // 錯字 → fuzzy fallback
];
let pass = 0;
for (const [q, want] of cases) {
  let hits = mod.searchIngredients(q, data);
  if (!hits.length) hits = mod.fuzzyFallback(q, data);
  const idx = hits.findIndex((h) => h.item.k === want);
  const ok = idx >= 0 && idx < 5;
  pass += ok;
  const top = hits[0];
  console.log(`${ok ? '✅' : '❌'} ${q.padEnd(16)} → #${idx + 1}/${hits.length}  top=${top ? `${top.item.k} (${top.fieldLabel ?? '-'})` : '無'}`);
}
console.log(`\n${pass}/${cases.length} 通過`);
// 全庫：皮膚科查不到的藥
const m = mod.searchIngredients('metformin', data);
const m2 = mod.searchIngredients('metformin', all);
console.log(`\n皮膚科子集查 metformin: ${m.length} 筆｜全庫: ${m2.length} 筆（空狀態要能指路）`);
