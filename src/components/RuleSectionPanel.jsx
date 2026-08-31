import { rocToAd } from '../lib/format.js';

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

export default function RuleSectionPanel({ section }) {
  if (!section) return null;
  const flags = section.flags ?? {};

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
        </>
      ) : (
        <div className="mt-3 text-[15px] leading-relaxed text-slate-800">
          {(section.clauses ?? []).map((c, i) => (
            <p key={i} className="whitespace-pre-wrap mb-1.5" style={{ paddingLeft: `${(c.level ?? 0) * 1.1}rem` }}>
              {annotate(c.text)}
            </p>
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
