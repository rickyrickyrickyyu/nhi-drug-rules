/**
 * 官方 PDF 還原出來的表格。
 *
 * 只有通過無損驗證（還原後字元與原文完全相同）的表格才會被輸出到這裡，
 * 所以前端不需要任何降級判斷 —— 拿到就是可信的。
 */
// 只有一格有內容的列多半是「欄位標籤」（如「涵蓋程度」「面積分數」），
// 讓它橫跨整列顯示，比塞在第一欄好讀
const isLabelRow = (row) => row.filter((c) => c).length === 1;

export default function RuleTable({ table }) {
  const grid = table?.grid ?? [];
  if (!grid.length) return null;

  return (
    <div className="my-3 rounded-lg border border-slate-200 overflow-hidden">
      {/* 表格一律可橫向捲動：健保的表常有 5–8 欄，窄螢幕硬擠會讓
          「LDL-C≧70mg/dL」在字中間斷行，比捲動更難讀 */}
      <div className="overflow-x-auto">
        <table className="text-[13px] border-collapse min-w-full">
          <tbody>
            {grid.map((row, i) => {
              if (isLabelRow(row)) {
                const label = row.find((c) => c) ?? '';
                return (
                  <tr key={i} className="bg-slate-100">
                    <td colSpan={row.length} className="px-2 py-1 font-medium text-slate-700">
                      {label}
                    </td>
                  </tr>
                );
              }
              return (
                <tr key={i} className={i % 2 ? 'bg-slate-50/60' : ''}>
                  {row.map((c, j) => (
                    <td
                      key={j}
                      className="px-2.5 py-1.5 border-t border-slate-200 align-top whitespace-pre-wrap break-normal min-w-[5.5rem] max-w-[18rem]"
                    >
                      {c}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="px-2 py-1 text-[11px] text-slate-500 bg-slate-50 border-t border-slate-200">
        由官方 PDF 版面還原，內容已通過無損比對；格式以官方 PDF 為準
      </div>
    </div>
  );
}
