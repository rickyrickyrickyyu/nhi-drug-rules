/**
 * 條文起點判定的回歸測試 —— 用真實資料跑真實實作（不做第二份 Python 重現）。
 *
 * 起因：查 aciclovir 進 10.7.1.1. 會被丟到 famciclovir／valaciclovir 的條文。
 * 兩個 bug 疊加：學名鍵是 WHO INN 的 Aciclovir(i) 但條文寫美式 Acyclovir(y)，
 * 加上沒有詞邊界所以 valaciclovir 被當成 aciclovir。
 */
import { readFileSync, readdirSync } from 'node:fs';
import { relevantStart, mentionsDrug } from '../src/lib/relevance.js';

const D = 'public/data';
const rules = {};
for (const f of readdirSync(`${D}/rules`)) {
  for (const s of JSON.parse(readFileSync(`${D}/rules/${f}`, 'utf8')).sections) rules[s.code] = s;
}

let fail = 0;
const ok = (cond, msg) => { console.log(`${cond ? '✅' : '❌'} ${msg}`); if (!cond) fail += 1; };

// ── 1. 單元：詞邊界 ──
ok(!mentionsDrug('2.Famciclovir；valaciclovir：', ['ACICLOVIR', 'Aciclovir', 'Acyclovir']),
   'valaciclovir 不可被當成 aciclovir');
ok(mentionsDrug('1.Acyclovir：', ['ACICLOVIR', 'Aciclovir', 'Acyclovir']),
   '美式拼法 Acyclovir 要認得出是 aciclovir');
ok(!mentionsDrug('1.Isotretinoin：', ['TRETINOIN', 'Tretinoin']),
   'isotretinoin 不可被當成 tretinoin');

// ── 2. 金絲雀：10.7.1.1. 三支抗病毒藥 ──
const sec = rules['10.7.1.1.'];
const cl = sec.clauses;
const A = relevantStart(cl, ['ACICLOVIR', 'Aciclovir', 'Acyclovir']);
ok(A.start === 0, `aciclovir 不跳段（實際 start=${A.start}）—— 它的規定就是第 1 項`);
for (const [inn, names] of [['famciclovir', ['FAMCICLOVIR', 'Famciclovir']],
                            ['valaciclovir', ['VALACICLOVIR', 'Valaciclovir']]]) {
  const r = relevantStart(cl, names);
  ok(r.start > 0 && r.skipped === 'Acyclovir',
     `${inn} 跳過前 ${r.start} 項，且橫幅寫出略過的是 ${r.skipped}`);
  const seg = [];
  for (const c of cl.slice(r.start)) { if (seg.length && (c.level ?? 0) === 1) break; seg.push(c.text); }
  ok(mentionsDrug(seg.join('\n'), names), `${inn} 的落點確實提到 ${inn}`);
}

// ── 3. 全庫：任何跳段的落點都必須真的提到該藥 ──
let skips = 0;
for (const scope of ['derm', 'all']) {
  for (const ing of JSON.parse(readFileSync(`${D}/${scope}.json`, 'utf8')).ing) {
    const names = [ing.k, ing.n, ...(ing.al ?? [])].filter(Boolean);
    const secs = new Set((ing.r ?? []).flatMap((rt) => rt.s ?? []));
    for (const code of secs) {
      const s = rules[code];
      if (!s?.clauses?.length) continue;
      const r = relevantStart(s.clauses, names);
      if (r.start === 0) continue;
      skips += 1;
      const seg = [];
      for (const c of s.clauses.slice(r.start)) {
        if (seg.length && (c.level ?? 0) === 1) break;
        seg.push(c.text);
      }
      ok(mentionsDrug(seg.join('\n'), names) && r.skipped,
         `${ing.k} @ ${code} 跳段正確（略過 ${r.skipped}）`);
    }
  }
}
console.log(`\n全庫共 ${skips} 次跳段`);
console.log(fail ? `❌ ${fail} 項失敗` : '✅ 全部通過');
process.exit(fail ? 1 : 0);
