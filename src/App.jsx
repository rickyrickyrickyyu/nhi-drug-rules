import { useEffect, useMemo, useState } from 'react';
import { useCoreData } from './hooks/useData.js';
import { useHashRoute, go } from './lib/routes.js';
import { searchIngredients, fuzzyFallback } from './lib/search.js';
import SearchBar from './components/SearchBar.jsx';
import IngredientRow from './components/IngredientRow.jsx';
import ProcedureRow from './components/ProcedureRow.jsx';
import ProcedureDetail from './components/ProcedureDetail.jsx';
import IngredientDetail from './components/IngredientDetail.jsx';
import Footer from './components/Footer.jsx';
import About from './components/About.jsx';
import Changes from './components/Changes.jsx';
import SectionView from './components/SectionView.jsx';

export default function App() {
  const { loading, error, meta, derm, procs, all, loadAll } = useCoreData();
  const route = useHashRoute();
  const [q, setQ] = useState('');
  const [scope, setScope] = useState('derm');
  const [loadingAll, setLoadingAll] = useState(false);

  useEffect(() => {
    if (scope !== 'all' || all || loadingAll) return;
    setLoadingAll(true);
    loadAll().finally(() => setLoadingAll(false));
  }, [scope, all, loadingAll, loadAll]);

  // 處置混在 derm.json 裡；切全庫時併入 procs_all
  const dataset = scope === 'all' ? (all ?? derm) : derm;

  const results = useMemo(() => {
    if (!q.trim()) return [];
    const hits = searchIngredients(q, dataset);
    return hits.length ? hits : fuzzyFallback(q, dataset);
  }, [q, dataset]);

  // 皮膚科清單找不到時，看看全庫有沒有 —— 這是「預設子集」最大的失敗模式
  const [otherScopeCount, setOtherScopeCount] = useState(0);
  useEffect(() => {
    if (scope !== 'derm' || results.length || !q.trim() || !all) return setOtherScopeCount(0);
    if (scope === 'derm' && !results.length && q.trim() && all) {
      setOtherScopeCount(searchIngredients(q, all).length);
    }
  }, [q, results.length, scope, all]);

  const current = useMemo(() => {
    if (route.view !== 'ingredient') return null;
    const pool = all ?? derm;
    const byKey = pool.find((i) => i.k === route.key) ?? derm.find((i) => i.k === route.key);
    if (byKey) return byKey;
    // ★ 別名回退：學名鍵會隨健保主檔的拼法修正而變動
    //   （2026-09 把 ACICLOVIR→ACYCLOVIR、CICLOSPORIN→CYCLOSPORIN 改回主檔用字）。
    //   已經分享出去的連結不該因此變成一片「找不到」。
    const want = String(route.key ?? '').toLowerCase();
    const hit = (arr) => arr.find((i) =>
      (i.al ?? []).some((a) => a.toLowerCase() === want));
    return hit(pool) ?? hit(derm) ?? null;
  }, [route, derm, all]);

  return (
    <div className="min-h-dvh max-w-3xl mx-auto px-4 pb-10">
      <header className="pt-5">
        {/* 標題與署名同一列：署名靠右上，窄螢幕也不會擠掉標題（shrink-0） */}
        <div className="flex items-start justify-between gap-3">
          <button type="button" onClick={() => go('#/')} className="text-left">
            <h1 className="text-xl font-bold text-brand-900">皮膚科健保給付規定查詢</h1>
          </button>
          <span className="text-[11px] text-slate-400 shrink-0 pt-1 whitespace-nowrap">
            by M116 RickyYu
          </span>
        </div>
        <p className="text-xs text-slate-500 mt-0.5">
          以學名搜尋，分劑型對應給付章節
          {meta && `｜${meta.n_ingredients_derm} 個常用學名 / ${meta.n_products.toLocaleString()} 個健保品項`}
        </p>
      </header>

      {loading && <p className="mt-6 text-slate-500">載入中…</p>}
      {error && (
        <p className="mt-6 text-rose-700 bg-rose-50 border border-rose-200 rounded-lg p-3 text-sm">
          資料載入失敗：{error}
        </p>
      )}

      {!loading && !error && route.view === 'about' && <About meta={meta} />}

      {!loading && !error && route.view === 'changes' && <Changes />}

      {!loading && !error && route.view === 'section' && <SectionView slug={route.key} />}

      {!loading && !error && route.view === 'procedure' && (
        <ProcedureDetail item={(procs ?? []).find((p) => p.k === route.key)} />
      )}

      {!loading && !error && route.view === 'ingredient' && current && (
        <div className="mt-4">
          <IngredientDetail item={current} />
        </div>
      )}
      {!loading && !error && route.view === 'ingredient' && !current && (
        <p className="mt-6 text-slate-500">
          找不到「{route.key}」。<button type="button" className="underline" onClick={() => go('#/')}>回搜尋</button>
        </p>
      )}

      {!loading && !error && route.view === 'home' && (
        <>
          <SearchBar
            value={q}
            onChange={setQ}
            scope={scope}
            onScope={setScope}
            allLoaded={!!all}
            loadingAll={loadingAll}
          />
          {q.trim() === '' ? (
            <div className="mt-6 text-sm text-slate-500 space-y-2">
              <p>可以這樣搜：</p>
              <ul className="list-disc pl-5 space-y-1">
                <li>英文學名 — <code className="bg-slate-200 px-1 rounded">dupilumab</code>、<code className="bg-slate-200 px-1 rounded">isotretinoin</code></li>
                <li>商品名（中英皆可）— <code className="bg-slate-200 px-1 rounded">Valtrex</code>、<code className="bg-slate-200 px-1 rounded">羅可坦</code></li>
                <li>中文俗稱 — <code className="bg-slate-200 px-1 rounded">口服A酸</code></li>
                <li>章節碼或 ATC — <code className="bg-slate-200 px-1 rounded">13.4</code>、<code className="bg-slate-200 px-1 rounded">D11AH</code></li>
                <li>醫療處置 — <code className="bg-slate-200 px-1 rounded">冷凍治療</code>、<code className="bg-slate-200 px-1 rounded">照光</code>、<code className="bg-slate-200 px-1 rounded">PUVA</code>、<code className="bg-slate-200 px-1 rounded">51017C</code></li>
              </ul>
              <p className="pt-2">
                <button type="button" onClick={() => go('#/changes')} className="text-brand-700 underline">
                  查看給付規定異動 →
                </button>
              </p>
            </div>
          ) : (
            <div className="mt-2">
              <div className="text-xs text-slate-500 mb-2">{results.length} 筆結果</div>
              {results.map((hit) =>
                hit.item.t === 'p'
                  ? <ProcedureRow key={`p-${hit.item.k}`} hit={hit} />
                  : <IngredientRow key={hit.item.k} hit={hit} />,
              )}
              {results.length === 0 && (
                <div className="text-sm text-slate-600 bg-white border border-slate-200 rounded-xl p-4">
                  <p>皮膚科常用清單中查無「{q}」。</p>
                  {scope === 'derm' && (
                    <button type="button" onClick={() => setScope('all')} className="mt-2 text-brand-700 underline">
                      切換至全庫模式再搜一次 →
                      {otherScopeCount > 0 && `（全庫有 ${otherScopeCount} 筆）`}
                    </button>
                  )}
                </div>
              )}
            </div>
          )}
        </>
      )}

      <Footer meta={meta} offline={false} />
    </div>
  );
}
