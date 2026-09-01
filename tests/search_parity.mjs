// JS 與 Python 兩邊的搜尋評分必須一致。
// 兩份是各自手寫的，註解宣稱一致但實測曾漂移 5 處（exact 與 prefix 被壓成同級），
// 這支測試把它釘住。
import { readFileSync, writeFileSync } from 'node:fs';

const src = readFileSync('src/lib/search.js', 'utf8').replace(/^export /gm, '');
const mod = await import(
  'data:text/javascript;base64,' +
  Buffer.from(src + '\nexport { searchIngredients };').toString('base64')
);
const d = JSON.parse(readFileSync('public/data/derm.json', 'utf8'));
const data = [...d.ing, ...(d.proc ?? [])];

const queries = [
  'isotretinoin', 'Roaccutane', '羅可坦', '口服A酸', 'A酸', '13.4', 'D10BA01',
  'acyclovir', 'aciclovir', 'Zovirax', 'Valtrex', '祛疹易', 'valacyclovir',
  'dupilumab', 'Dupixent', '杜避炎', 'betamethasone', 'secukinumab', 'Cosentyx',
  '冷凍治療', '凍療', '液態氮', 'cryotherapy', 'liquid nitrogen', 'LN2',
  '照光', '光療', 'PUVA', 'UVB', '貼布試驗', 'patch test', '拔甲', '皮膚切片',
  '51017C', '51018C', '30508C', 'calcipotriol', 'terbinafine', 'permethrin',
];
const out = {};
for (const q of queries) {
  out[q] = mod.searchIngredients(q, data, { limit: 5 })
    .map((h) => `${h.item.k}:${h.score}`);
}
writeFileSync('/tmp/parity_js.json', JSON.stringify(out, null, 1));
console.log(`JS 產生 ${queries.length} 組查詢結果`);
