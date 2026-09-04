import RuleTable from './RuleTable.jsx';
import { rocToAd } from '../lib/format.js';

/** 民國日期加 tooltip 顯示西元。條文原文一字不改，只做視覺結構化。 */
export function annotate(text) {
  const parts = text.split(/(\d{2,3}\/\d{1,2}\/\d{1,2})/g);
  return parts.map((p, i) => {
    const ad = rocToAd(p);
    return ad ? (
      <abbr key={i} title={ad} className="decoration-dotted underline cursor-help text-slate-500">
        {p}
      </abbr>
    ) : (
      <span key={i}>{p}</span>
    );
  });
}

// ETL 在條文裡留下的表格佔位標記（私用區字元，不可能出現在條文原文）
export const RE_TABLE_MARK = /\ue000TB(\d+)\ue000/g;

/**
 * 一段條文。表格標記處就地換成 <RuleTable>。
 *
 * ★ 為什麼不是「條文照印、表格附在最後」：
 *   表格在 PDF 純文字裡是逐格換行的碎片（「涵蓋程/度/0﹪/1-9﹪…」）。
 *   照印等於同一份內容出現兩次，而且先出現的那份不可讀。
 *   ETL 已把碎片從條文挖掉（挖除是無損的：只有夾雜 0 個非表格字元才會挖），
 *   這裡只負責把標記換回表格。
 */
export default function ClauseBody({ text, tables, indent = 0 }) {
  const segs = String(text ?? '').split(RE_TABLE_MARK);
  const out = [];
  for (let i = 0; i < segs.length; i += 1) {
    // split 帶捕獲群組 → 偶數索引是文字、奇數索引是表格編號
    if (i % 2 === 1) {
      const t = tables?.[Number(segs[i])];
      if (t) out.push(<RuleTable key={`t${i}`} table={t} />);
      continue;
    }
    const body = segs[i].replace(/^\n+|\n+$/g, '');
    if (!body) continue;
    out.push(
      <p
        key={`p${i}`}
        className="whitespace-pre-wrap mb-1.5"
        style={indent ? { paddingLeft: `${indent}rem` } : undefined}
      >
        {annotate(body)}
      </p>,
    );
  }
  return out;
}

