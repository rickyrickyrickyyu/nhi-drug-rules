import { useState } from 'react';
import { rocToAd } from '../lib/format.js';
import RuleTable from './RuleTable.jsx';
import { go } from '../lib/routes.js';

const FLAG_BADGES = [
  ['prior_review', '⚠️ 事前審查', 'bg-amber-100 text-amber-900'],
  ['consent_form', '📝 需同意書', 'bg-purple-100 text-purple-900'],
  ['course_limited', '⏱ 療程限制', 'bg-sky-100 text-sky-900'],
  ['no_combination', '🚫 不得併用', 'bg-rose-100 text-rose-900'],
  ['special_case', '📄 專案申請', 'bg-slate-200 text-slate-800'],
];

const PDF_URL = (fn) =>
  `https://info.nhi.gov.tw/api/INAE3000/INAE3000S01/getPDF?DurgFileName=${fn}`;

/** 民國日期加 tooltip 顯示西元。條文原文一字不改，只做視覺結構化。 */
function annotate(text) {
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
const RE_TABLE_MARK = /\ue000TB(\d+)\ue000/g;

/**
 * 一段條文。表格標記處就地換成 <RuleTable>。
 *
 * ★ 為什麼不是「條文照印、表格附在最後」：
 *   表格在 PDF 純文字裡是逐格換行的碎片（「涵蓋程/度/0﹪/1-9﹪…」）。
 *   照印等於同一份內容出現兩次，而且先出現的那份不可讀。
 *   ETL 已把碎片從條文挖掉（挖除是無損的：只有夾雜 0 個非表格字元才會挖），
 *   這裡只負責把標記換回表格。
 */
function ClauseBody({ text, tables, indent = 0 }) {
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

/**
 * 挑出與該學名最相關的條文起點。
 *
 * 10.7.1.1. 同時規範 acyclovir、famciclovir、valaciclovir，第 1 項整段都在講
 * acyclovir。查 famciclovir 的醫師先看到 acyclovir 的適應症清單，在門診會誤導。
 */
function relevantStart(clauses, inn) {
  if (!inn || clauses.length <= 3) return 0;
  const base = inn.split(' (')[0].toLowerCase().slice(0, 8);

  // 只在「第 1 項一開頭就是別的藥名」時才跳段。
  // 10.7.1.1. 第 1 項是「1.Acyclovir：…」，查 famciclovir 不該先讀那段；
  // 但 13.4. 第 1 項是「1.限皮膚科專科醫師使用。」，三項都適用 isotretinoin，
  // 無條件跳段會略過最關鍵的第 1、2 項。
  const lead = /^\s*\d+\s*[.、]\s*([A-Za-z][A-Za-z-]{5,})/.exec(clauses[0].text);
  if (!lead || lead[1].toLowerCase().slice(0, 8) === base) return 0;

  const hit = clauses.findIndex((c) => c.text.toLowerCase().includes(base));
  if (hit <= 0) return 0;
  for (let i = hit; i >= 0; i--) {
    if ((clauses[i].level ?? 0) === 1) return i;
  }
  return hit;
}

export default function RuleSectionPanel({ section, inn }) {
  const [expanded, setExpanded] = useState(false);
  if (!section) return null;
  const flags = section.flags ?? {};
  const tables = section.tables ?? [];
  // 引用了附表但本體在別節（13.17.1. 引用「附表三十二」，EASI 評分表其實在 13.17.2.）
  const crossRefs = (section.appx_refs ?? []).filter((x) => x.host && !x.self);
  const missingRefs = (section.appx_refs ?? []).filter((x) => x.missing);
  // 條文多久沒改了。健保署發布公告到更新條文 PDF 有時間落差，
  // 標出年數讓醫師對「這條可能不是最新的」有感覺。
  const lastRev = section.rev?.at(-1) ?? section.eff;
  const staleYears = lastRev
    ? Math.floor((Date.now() - new Date(lastRev).getTime()) / 31557600000)
    : 0;

  if (section.no_pdf) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-4 mb-3">
        <div className="font-semibold">{section.code}</div>
        <p className="text-sm text-slate-600 mt-1">
          本節為分類節點，健保署未提供獨立條文，實際給付條件請見其子節。
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 mb-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm text-brand-700 font-mono">{section.code}</div>
          <h3 className="font-semibold leading-snug">{section.title || '(無標題)'}</h3>
        </div>
        {staleYears >= 5 && !section.pending && (
          <span
            className="text-[11px] text-slate-500 shrink-0 self-center"
            title="條文長期未修訂不代表有問題，但若你知道近期有新公告，請以官方公告為準"
          >
            條文 {staleYears} 年未修訂
          </span>
        )}
        {section.pdf && (
          <a
            href={PDF_URL(section.pdf)}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs shrink-0 px-2.5 py-1.5 rounded-lg border border-slate-300 hover:bg-slate-50"
          >
            官方原文 PDF ↗
          </a>
        )}
      </div>

      {section.pending && (
        <div className="mt-2 text-sm bg-rose-50 border border-rose-300 text-rose-900 rounded-lg px-3 py-2">
          <div className="font-semibold">
            ⚠️ 健保署已公告新制（{section.pending.effective} 生效），但官方條文檔尚未更新
          </div>
          <p className="mt-1 leading-relaxed">{section.pending.note}</p>
          <p className="mt-1 text-[11px] text-rose-800">
            以下顯示的是官方目前提供的舊版條文，請以健保署最新公告為準。
            （來源：{section.pending.source}；查核日 {section.pending.checked}）
          </p>
        </div>
      )}

      {section.future && (
        <div className="mt-2 text-sm bg-orange-50 border border-orange-200 text-orange-900 rounded-lg px-3 py-2">
          ⏳ 本版自 <b>{section.eff}</b> 起生效，目前<b>尚未適用</b>。申請時請確認現行版本。
        </div>
      )}

      <div className="flex flex-wrap gap-1.5 mt-2.5">
        {FLAG_BADGES.filter(([k]) => flags[k]).map(([k, label, cls]) => (
          <span key={k} className={`text-xs px-2 py-0.5 rounded-full ${cls}`}>{label}</span>
        ))}
        {(flags.specialist_only ?? []).map((s) => (
          <span key={s} className="text-xs px-2 py-0.5 rounded-full bg-sky-100 text-sky-900">
            👨‍⚕️ 限{s}專科醫師
          </span>
        ))}
        {(flags.attachments ?? []).map((a) => (
          <span key={a} className="text-xs px-2 py-0.5 rounded-full bg-slate-200 text-slate-800">
            📎 {a}
          </span>
        ))}
      </div>
      {FLAG_BADGES.some(([k]) => flags[k]) && (
        <p className="mt-1.5 text-[11px] text-slate-500">
          ⚠ 上列標籤為程式自動抽取，僅供快速瀏覽，一律以下方條文原文為準。
        </p>
      )}

      {section.stub && !section.title_rule ? (
        <p className="mt-3 text-sm text-slate-500 bg-slate-50 rounded-lg px-3 py-2">
          本節僅有標題，實際給付條件請見其子節。
        </p>
      ) : section.stub && section.title_rule ? (
        // 整條規則就寫在標題行（如 13.3.3.「與 tazarotene 併用…」）。
        // 對這種節說「請見子節」是誤導 —— 上面顯示的標題就是完整規則。
        <p className="mt-3 text-[11px] text-slate-500">
          本節之給付規定即為上方條文全文（健保署原文未再分項）。
        </p>
      ) : section.raw ? (
        // 條號切塊沒涵蓋住原文（多為「修訂對照表」雙欄版型）→ 顯示完整原文。
        // 版面難看沒關係，被截斷的給付條件會害人。
        <>
          <p className="mt-3 text-xs text-slate-500 bg-slate-50 rounded-lg px-3 py-2">
            本節 PDF 為特殊版型（如修訂對照表），為避免條文被截斷，以下顯示官方原文全文。
          </p>
          <pre className="mt-2 text-[14px] leading-relaxed text-slate-800 whitespace-pre-wrap font-sans">
            {annotate(section.text ?? '')}
          </pre>
          {/* ★ 這條分支顯示的是未經條號切塊的原文，沒有表格標記可就地替換，
              所以還原好的表格要另外附上 —— 否則像 1.3.6.、14.1.1. 這種
              「修訂對照表」節，新舊條文對照表根本不會出現在畫面上。 */}
          {tables.length > 0 && (
            <div className="mt-3">
              <div className="text-xs text-slate-500 mb-1">
                由官方 PDF 版面還原之表格（{tables.length}）
              </div>
              {tables.map((t, i) => <RuleTable key={i} table={t} />)}
            </div>
          )}
        </>
      ) : (
        (() => {
          const all = section.clauses ?? [];
          const usedTables = new Set(
            [...all.map((c) => c.text ?? '').join('\n').matchAll(RE_TABLE_MARK)]
              .map((m) => Number(m[1])),
          );
          const start = expanded ? 0 : relevantStart(all, inn);
          // 附表是空白表單範本（同意書欄位），預設摺疊
          const appx = section.appx;
          const bodyEnd = appx == null ? all.length : appx;
          const shown = all.slice(start, Math.max(start, bodyEnd));
          const appendix = appx == null ? [] : all.slice(appx);
          return (
            <div className="mt-3 text-[15px] leading-relaxed text-slate-800">
              {start > 0 && (
                <button
                  type="button"
                  onClick={() => setExpanded(true)}
                  className="mb-2 text-xs text-brand-700 bg-brand-50 rounded-lg px-2.5 py-1.5 text-left w-full"
                >
                  ↑ 本節前 {start} 項規範其他藥品，已略過。點此顯示完整條文
                </button>
              )}
              {shown.map((c, i) => (
                <ClauseBody
                  key={start + i}
                  text={c.text}
                  tables={tables}
                  indent={(c.level ?? 0) * 1.1}
                />
              ))}
              {appendix.length > 0 && (
                <details className="mt-2 border-t border-slate-100 pt-2">
                  <summary className="text-xs text-slate-500 cursor-pointer">
                    📎 {appendix[0].text.split(/\s/)[0]} 附表內容（{appendix.length} 段
                    {tables.length > 0 && `、${tables.length} 個表格`}，點開檢視）
                  </summary>
                  <div className="mt-2 text-[13px] text-slate-600">
                    {appendix.map((c, i) => (
                      <ClauseBody key={i} text={c.text} tables={tables} />
                    ))}
                  </div>
                  {/* 定位不到的表格（PDF 文字流順序與版面不同）沒有標記可換，
                      仍附在最後，總比看不到好 */}
                  {tables.filter((_, i) => !usedTables.has(i))
                         .map((t, i) => <RuleTable key={`x${i}`} table={t} />)}
                </details>
              )}
            </div>
          );
        })()
      )}

      {(crossRefs.length > 0 || missingRefs.length > 0) && (
        <div className="mt-3 text-xs space-y-1">
          {crossRefs.map((x) => (
            <button
              key={x.name}
              type="button"
              onClick={() => go(`#/s/${x.host.replace(/\.$/, '').replaceAll('.', '-')}`)}
              className="block text-left text-brand-700 bg-brand-50 rounded-lg px-2.5 py-1.5 w-full"
            >
              📎 {x.name} 的內容收錄於 <span className="font-mono">{x.host}</span>，點此查看 →
            </button>
          ))}
          {missingRefs.map((x) => (
            <div key={x.name} className="text-slate-500 bg-slate-50 rounded-lg px-2.5 py-1.5">
              📎 {x.name}：本站快照未收錄此附表原文，請點上方官方 PDF 查閱
            </div>
          ))}
        </div>
      )}

      {section.rev?.length > 0 && (
        <details className="mt-3">
          <summary className="text-xs text-slate-500 cursor-pointer">
            歷次修訂 {section.rev.length} 次（最新 {section.rev.at(-1)}）
          </summary>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {section.rev.map((d) => {
              const hasSnapshot = section.eff === d;
              return (
                <span
                  key={d}
                  title={hasSnapshot ? '本站有此版本原文快照' : '僅知該日曾修訂，本站無當時原文'}
                  className={`text-xs px-2 py-0.5 rounded-full border ${
                    hasSnapshot
                      ? 'bg-brand-600 text-white border-brand-600'
                      : 'bg-white text-slate-500 border-slate-300'
                  }`}
                >
                  {d}
                </span>
              );
            })}
          </div>
          <p className="mt-1.5 text-[11px] text-slate-500">
            實心 = 本站有原文快照；空心 = 僅知該日曾修訂（本站自 {section.first_seen ?? '建站日'} 起累積快照）。
          </p>
        </details>
      )}
    </div>
  );
}
