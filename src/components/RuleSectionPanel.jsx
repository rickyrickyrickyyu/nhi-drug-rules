import { useState } from 'react';
import RuleTable from './RuleTable.jsx';
import { go } from '../lib/routes.js';
import { relevantStart } from '../lib/relevance.js';
import ClauseBody, { RE_TABLE_MARK, annotate } from './ClauseBody.jsx';

const FLAG_BADGES = [
  ['prior_review', '⚠️ 事前審查', 'bg-amber-100 text-amber-900'],
  ['consent_form', '📝 需同意書', 'bg-purple-100 text-purple-900'],
  ['course_limited', '⏱ 療程限制', 'bg-sky-100 text-sky-900'],
  ['no_combination', '🚫 不得併用', 'bg-rose-100 text-rose-900'],
  ['special_case', '📄 專案申請', 'bg-slate-200 text-slate-800'],
];

// 檔名來自健保署的 manifest（實測全是 [A-Za-z0-9._-]），但仍然編碼：
// 上游哪天在檔名裡放進 & 或 #，未編碼就會被改寫成別的查詢參數。
const PDF_URL = (fn) =>
  `https://info.nhi.gov.tw/api/INAE3000/INAE3000S01/getPDF?DurgFileName=${encodeURIComponent(fn)}`;

export default function RuleSectionPanel({ section, inn, innNames }) {
  const [expanded, setExpanded] = useState(false);
  if (!section) return null;
  const flags = section.flags ?? {};
  const tables = section.tables ?? [];
  // 引用了附表但本體在別節（13.17.1. 引用「附表三十二」，EASI 評分表其實在 13.17.2.）
  // 附表參照分三類：跨章節（本體在別節）、官方獨立檔、真的沒有本體。
  // 「條文寫基底名、官方細分成子檔」（附表二 → 附表二-A~D）走 variants。
  const crossRefs = (section.appx_refs ?? []).filter(
    (x) => x.kind === 'section' && x.host && !x.self);
  const fileRefs = (section.appx_refs ?? []).filter((x) => x.kind === 'file');
  const variantRefs = (section.appx_refs ?? []).filter(
    (x) => !x.kind && x.variants?.length);
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

      {section.pending && (() => {
        // ★ 「已生效但條文未更新」與「尚未生效」對臨床是完全不同的處境：
        //   生效日過了，新制就是現行規定，下方那份舊條文**不能拿來判斷**；
        //   還沒生效則舊條文仍然有效。兩者用同一句話帶過會誤導。
        const inForce = section.pending.effective <= new Date().toISOString().slice(0, 10);
        return (
          <div className="mt-2 text-sm bg-rose-50 border border-rose-300 text-rose-900 rounded-lg px-3 py-2">
            <div className="font-semibold">
              {inForce
                ? `⚠️ 新制已於 ${section.pending.effective} 生效，但健保署尚未更新官方條文檔`
                : `⚠️ 健保署已公告新制（${section.pending.effective} 生效），官方條文檔尚未更新`}
            </div>
            <p className="mt-1 leading-relaxed">{section.pending.note}</p>
            <p className="mt-1 text-[11px] text-rose-800">
              {inForce
                ? '以下條文是官方目前仍提供的舊版，已不等於現行規定，請勿據以判斷給付，一律以健保署公告為準。'
                : '以下顯示的是官方目前提供的舊版條文，請以健保署最新公告為準。'}
              （來源：{section.pending.source}；查核日 {section.pending.checked}）
            </p>
          </div>
        );
      })()}

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
          // 學名鍵、顯示名與英文別名都要納入比對：健保條文的拼法未必是 WHO INN
          // （10.7.1.1. 寫 Acyclovir，我們的鍵是 ACICLOVIR）。
          const names = (innNames?.length ? innNames : [inn]).filter(Boolean);
          const rel = expanded ? { start: 0, skipped: null } : relevantStart(all, names);
          const start = rel.start;
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
                  ↑ 本節前 {start} 項規範
                  {rel.skipped ? <b className="mx-1">{rel.skipped}</b> : '其他藥品'}
                  ，已略過。點此顯示完整條文
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

      {(crossRefs.length > 0 || fileRefs.length > 0
        || variantRefs.length > 0 || missingRefs.length > 0) && (
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
          {fileRefs.map((x) => (
            <button
              key={x.name}
              type="button"
              onClick={() => go(`#/a/${encodeURIComponent(x.name)}`)}
              className="block text-left text-brand-700 bg-brand-50 rounded-lg px-2.5 py-1.5 w-full"
            >
              📎 {x.name}（健保署獨立附表），點此查看 →
            </button>
          ))}
          {/* 條文只寫基底名，官方細分成子檔 —— 全部列出來，那正是條文所指的那一組 */}
          {variantRefs.map((x) => (
            <div key={x.name} className="bg-brand-50 rounded-lg px-2.5 py-1.5">
              <span className="text-slate-600">📎 {x.name} 於健保署分為：</span>
              <span className="ml-1 inline-flex flex-wrap gap-1.5">
                {x.variants.map((v) => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => go(`#/a/${encodeURIComponent(v)}`)}
                    className="text-brand-700 underline"
                  >
                    {v}
                  </button>
                ))}
              </span>
            </div>
          ))}
          {missingRefs.map((x) => (
            <div key={x.name} className="text-slate-500 bg-slate-50 rounded-lg px-2.5 py-1.5">
              📎 {x.name}：健保署未單獨發布此附表，請點上方官方 PDF 查閱條文內文
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
