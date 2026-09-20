/**
 * 「你現在看到的不是最新版」的全站橫幅。
 *
 * 刻意放在最上面而不是「關於」頁裡：資料過期是臨床安全問題，
 * 不該藏在一個要自己點進去的分頁。useFreshness 已經自動修過一次，
 * 還會走到這裡代表自動修失敗（無痕模式、或已修過一次仍對不上），
 * 所以要給一顆按鈕，而不是只顯示狀態。
 */
export default function StaleBanner({ serverBuilt, onApply }) {
  return (
    <div className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-3">
      <p className="text-sm text-amber-900">
        ⚠️ 畫面上的資料不是最新版
        {serverBuilt && <>（伺服器快照 <b>{serverBuilt}</b>）</>}
        ，條文可能與現行給付規定不符。
      </p>
      <button
        type="button"
        onClick={onApply}
        className="mt-2 text-xs px-2.5 py-1 rounded-lg border border-amber-400 bg-white hover:bg-amber-100"
      >
        立即套用最新版
      </button>
    </div>
  );
}
