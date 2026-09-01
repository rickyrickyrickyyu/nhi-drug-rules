export default function SearchBar({ value, onChange, scope, onScope, allLoaded, loadingAll }) {
  return (
    <div className="sticky top-0 z-10 bg-slate-50 pt-3 pb-2">
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="學名 / 商品名 / 處置 / 章節碼，例：dupilumab、Valtrex、口服A酸、冷凍治療、13.4"
        autoComplete="off"
        autoCorrect="off"
        spellCheck={false}
        className="w-full text-base border border-slate-300 rounded-xl px-4 py-3 bg-white
                   focus:outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100"
      />
      <div className="flex gap-1.5 mt-2">
        {[
          ['derm', '皮膚科常用'],
          ['all', '全庫'],
        ].map(([k, label]) => (
          <button
            key={k}
            type="button"
            onClick={() => onScope(k)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition ${
              scope === k
                ? 'bg-brand-700 text-white border-brand-700'
                : 'bg-white text-slate-600 border-slate-300'
            }`}
          >
            {label}
            {k === 'all' && loadingAll && ' …'}
            {k === 'all' && allLoaded && ' ✓'}
          </button>
        ))}
      </div>
    </div>
  );
}
