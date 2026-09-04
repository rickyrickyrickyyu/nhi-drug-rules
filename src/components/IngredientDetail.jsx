import { useEffect, useState } from 'react';
import { loadChapter, loadProducts } from '../hooks/useData.js';
import { secChapter, money } from '../lib/format.js';
import RuleSectionPanel from './RuleSectionPanel.jsx';
import ClinicalNote from './ClinicalNote.jsx';
import TfdaIndication from './TfdaIndication.jsx';
import DosingPanel from './DosingPanel.jsx';

// ★ 食藥署自己的開放資料就是用這個形式發布仿單網址（實測對兩種形式的證都回 200）。
//   只連結、不鏡射 —— mcp.fda.gov.tw 明訂不得重製轉載，但連過去正是這些 URL 的用途。
const insertUrl = (licenceNo) =>
  `https://mcp.fda.gov.tw/exportpdf/${encodeURIComponent(licenceNo)}`;
import { go } from '../lib/routes.js';

export default function IngredientDetail({ item }) {
  // ★ 條文比對必須連英文別名一起帶：健保條文的拼法未必是 WHO INN。
  //   10.7.1.1. 寫的是美式 Acyclovir，我們的鍵是 ACICLOVIR —— 少了別名，
  //   「這一項是不是本藥」會判錯，進而跳到別的藥的條文。
  const innNames = [item.k, item.n, ...(item.al ?? [])].filter(Boolean);
  const [tab, setTab] = useState(item.r?.[0]?.ro ?? null);
  const [sections, setSections] = useState({});
  const [products, setProducts] = useState(null);

  useEffect(() => {
    setTab(item.r?.[0]?.ro ?? null);
    setProducts(null);
    loadProducts(item.k).then(setProducts).catch(() => setProducts({ items: [] }));

    const chapters = [...new Set((item.s ?? []).map(secChapter))];
    Promise.all(chapters.map((n) => loadChapter(n).catch(() => null))).then((res) => {
      const map = {};
      for (const r of res) {
        if (!r) continue;
        for (const s of r.sections) map[s.code] = s;
      }
      setSections(map);
    });
  }, [item.k]);

  const active = item.r?.find((r) => r.ro === tab);
  const routeSections = active?.s ?? [];
  // 分組在 ETL 就算好了（依 curation/derm_tags.yaml 的章節白名單），
  // 前端不要自己用「第一個章節的大節」猜 —— 那會把 dupilumab 的氣喘章節當主角。
  const own = active?.sd ?? [];
  const other = active?.so ?? [];
  // 有章節但沒有皮膚科章節 —— rituximab 就是這種：健保只給類風濕性關節炎與
  // 淋巴瘤，沒有天疱瘡。醫師最需要知道的就是這件事，不能只是靜靜地列出來。
  const noDermSection = routeSections.length > 0 && own.length === 0;
  const mentionCodes = [
    ...(item.mn?.listed ?? []), ...(item.mn?.referenced ?? []),
  ].slice(0, 12);
  // 有列價的排前面：未列價的多半已無流通，醫師要先看到真正開得到的
  const allRouteItems = (products?.items ?? []).filter((p) => p.route === tab);
  const routeItems = allRouteItems.filter((p) => p.price);
  const unpricedItems = allRouteItems.filter((p) => !p.price);

  return (
    <div className="space-y-3">
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <h2 className="text-2xl font-bold">{item.n}</h2>
        <div className="text-sm text-slate-500 mt-1">
          {(item.z ?? []).join('、')}
          {item.z?.length > 0 && ' · '}
          {(item.a ?? []).join(' / ')}
          {item.c === 1 && <span className="ml-2 px-2 py-0.5 bg-slate-200 rounded-full text-xs">複方</span>}
        </div>
        <div className="mt-1 text-xs text-slate-400">
          共 {item.np} 個健保品項｜標籤來源：{(item.dr ?? []).join('、') || '—'}
        </div>
      </div>

      {/* ★ 依劑型分頁：acyclovir 外用掛 10.7.1.2、口服掛 10.7.1.1，條文完全不同 */}
      <div className="flex gap-1.5 flex-wrap">
        {(item.r ?? []).map((r) => (
          <button
            key={r.ro}
            type="button"
            onClick={() => setTab(r.ro)}
            className={`px-3.5 py-2 rounded-lg text-sm font-medium border transition ${
              tab === r.ro
                ? 'bg-brand-700 text-white border-brand-700'
                : 'bg-white text-slate-700 border-slate-300 hover:border-brand-600'
            }`}
          >
            {r.l} <span className="opacity-70">{r.np}</span>
          </button>
        ))}
      </div>

      {active && (
        <>
          {/* ★ 代表仿單：優先取原廠。同一學名不同藥廠仿單可能不同，所以必須
              標明這是誰的仿單，並指路到品項表看其他家 —— 不能讓人以為
              這一份代表全部。 */}
          {(() => {
            const pick = routeItems.find((p) => p.has_insert && p.is_originator)
              ?? routeItems.find((p) => p.has_insert);
            if (!pick) return null;
            return (
              <p className="mb-3 text-sm">
                <a
                  href={insertUrl(pick.licence_no)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-brand-700 underline"
                >
                  📄 食藥署仿單 ↗
                </a>
                <span className="text-[11px] text-slate-500 ml-1.5">
                  （{pick.brand_stem_zh || pick.brand_stem_en}
                  {pick.is_originator && ' · 原廠'}
                  ；其他藥廠見下方品項表）
                </span>
              </p>
            );
          })()}

          {/* 劑量放最前面：醫師確認「可以申請」之後，下一個問題就是「怎麼開」 */}
          <DosingPanel
            dosing={products?.dosing}
            innDisplay={item.n}
            licenceNo={routeItems[0]?.licence_no || allRouteItems[0]?.licence_no}
            doseTfda={products?.dose_tfda ?? []}
          />

          {routeSections.length === 0 ? (
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <div className="font-semibold">本劑型無個別給付規定章節</div>
              {mentionCodes.length > 0 && (
                <div className="mt-2 text-sm bg-slate-50 rounded-lg px-3 py-2">
                  <div className="font-medium text-slate-700">條文中出現本藥名稱的章節</div>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {mentionCodes.map((c) => (
                      <button
                        key={c}
                        type="button"
                        onClick={() => go(`#/s/${c.replace(/\.$/, '').replaceAll('.', '-')}`)}
                        className="font-mono text-xs px-2 py-0.5 rounded border border-slate-300 hover:border-brand-600"
                      >
                        {c}
                      </button>
                    ))}
                  </div>
                  {/* 實測過的反例：12.4. 是「ciprofloxacin + hydrocortisone 耳滴劑」，
                      名稱出現不代表 hydrocortisone 本身適用；10.6.5. 只涵蓋
                      amphotericin B 的 liposomal 劑型。措辭不能給暗示。 */}
                  <p className="mt-1.5 text-[11px] text-slate-500 leading-relaxed">
                    健保「給付規定章節」欄未指定本藥，但上列章節的條文中出現本藥名稱。
                    可能是適用藥品、複方成分，也可能只是前置治療條件或其他劑型的規定
                    —— <b>並非健保核定本藥適用該章節</b>，請點開查閱原文自行判斷。
                  </p>
                </div>
              )}
              <p className="text-sm text-slate-600 mt-1.5 leading-relaxed">
                健保藥品主檔中，此劑型的品項未標註任何給付規定章節碼，代表沒有針對本品的
                <b>專章限制</b>（例如事前審查、專科限制、療程上限）。
                給付仍須符合：① 藥品許可證核准之適應症 ② 藥品給付規定通則
                ③ 合理臨床劑量，並受各院內部規範約束。
              </p>
            </div>
          ) : (
            <>
              {noDermSection && (
                <div className="rounded-xl border border-amber-300 bg-amber-50 p-4">
                  <div className="font-semibold text-amber-900">
                    本劑型在健保給付規定中沒有皮膚科適應症章節
                  </div>
                  <p className="text-sm text-amber-900 mt-1.5 leading-relaxed">
                    此藥有健保給付規定，但條文限定的是其他科別的適應症（見下方）。
                    以皮膚科診斷申報本藥，健保並無對應的給付條文。
                  </p>
                </div>
              )}
              {own.map((c) => <RuleSectionPanel key={c} section={sections[c]} inn={item.k} innNames={innNames} />)}
              {other.length > 0 && (
                <>
                  <div className="text-sm text-slate-500 pt-1">
                    {noDermSection ? '健保給付之其他科別適應症' : '其他科別的相關規定'}
                  </div>
                  {other.map((c) => <RuleSectionPanel key={c} section={sections[c]} inn={item.k} innNames={innNames} />)}
                </>
              )}
            </>
          )}

          <TfdaIndication
            indications={products?.indications?.[tab]}
            routeLabel={active.l}
          />

          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
            <div className="px-4 py-2.5 text-sm font-medium border-b border-slate-200">
              {active.l}品項（{routeItems.length} 項有列價
              {unpricedItems.length > 0 && `，另 ${unpricedItems.length} 項未列價`}）
            </div>
            {routeItems.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-slate-500 text-xs">
                  <tr>
                    <th className="text-left px-3 py-2 font-medium">商品名</th>
                    <th className="text-left px-3 py-2 font-medium">中文名</th>
                    <th className="text-left px-3 py-2 font-medium whitespace-nowrap">藥品代號</th>
                    <th className="text-right px-3 py-2 font-medium whitespace-nowrap">健保價</th>
                    <th className="text-center px-2 py-2 font-medium whitespace-nowrap">仿單</th>
                  </tr>
                </thead>
                <tbody>
                  {routeItems.map((p) => (
                    <tr key={p.code} className="border-t border-slate-100">
                      <td className="px-3 py-2">
                        {p.brand_stem_en}
                        {p.is_originator && (
                          <span className="ml-1.5 text-[10px] px-1.5 py-0.5 bg-brand-100 text-brand-900 rounded">原廠</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-slate-600">
                        {p.brand_stem_zh}
                        {p.name_zh_repaired && (
                          <span
                            className="text-slate-400 ml-1"
                            title={`健保檔中文名有掉字，已用食藥署許可證 ${p.licence_no} 修復`}
                          >
                            ✓
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-slate-500">{p.code}</td>
                      <td className="px-3 py-2 text-right whitespace-nowrap">
                        {money(p.price)}
                        {p.price_next != null && (
                          <div className="text-[11px] text-orange-700">
                            {p.price_next_from} 起 {money(p.price_next)}
                          </div>
                        )}
                      </td>
                      <td className="px-2 py-2 text-center whitespace-nowrap">
                        {/* 每張許可證有自己的仿單（不同藥廠可能不同），所以是逐列連結。
                            沒有仿單的品項留白 —— 不放點了沒用的假連結。 */}
                        {p.has_insert ? (
                          <a
                            href={insertUrl(p.licence_no)}
                            target="_blank"
                            rel="noopener noreferrer"
                            title={`食藥署仿單（${p.licence_no}）`}
                            className="text-brand-700 underline text-xs"
                          >
                            仿單 ↗
                          </a>
                        ) : (
                          <span className="text-slate-300 text-xs">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            )}
            {unpricedItems.length > 0 && (
              <details className="border-t border-slate-100">
                <summary className="px-4 py-2.5 text-xs text-slate-500 cursor-pointer">
                  另有 {unpricedItems.length} 項未列價品項（健保檔支付價為 0，多為已無流通之舊品項）
                </summary>
                <ul className="px-4 pb-3 text-xs text-slate-500 space-y-0.5">
                  {unpricedItems.map((p) => (
                    <li key={p.code}>
                      {p.brand_stem_en} {p.brand_stem_zh}
                      <span className="font-mono ml-2 text-slate-400">{p.code}</span>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        </>
      )}

      <ClinicalNote innKey={item.k} />
      <button type="button" onClick={() => go('#/')} className="text-sm text-brand-700 underline">
        ← 回搜尋
      </button>
    </div>
  );
}
