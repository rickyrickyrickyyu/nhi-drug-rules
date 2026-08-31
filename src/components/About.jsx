import DataFreshness from './DataFreshness.jsx';
import { REPO_URL, INSPIRED_BY } from '../lib/constants.js';

export default function About({ meta }) {
  return (
    <article className="mt-5 bg-white rounded-xl border border-slate-200 p-5 text-sm leading-relaxed space-y-4">
      <section>
        <h2 className="font-semibold text-base">關於本站</h2>
        <p className="mt-1 text-slate-700">
          以<b>學名</b>為入口查詢台灣健保藥品給付規定，並區分同一學名的口服／注射／外用等
          不同劑型 —— 因為它們往往適用<b>不同的給付規定章節</b>
          （例如 aciclovir 口服適用 10.7.1.1.、外用適用 10.7.1.2.）。
        </p>
        {meta && (
          <p className="mt-2 text-slate-500 text-xs">
            資料快照 {meta.built}｜{meta.n_ingredients_all.toLocaleString()} 個學名、
            {meta.n_products.toLocaleString()} 個健保品項、{meta.n_sections} 個給付規定章節。
          </p>
        )}
      </section>

      <section>
        <h2 className="font-semibold text-base">資料更新</h2>
        <div className="mt-2">
          <DataFreshness meta={meta} repoUrl={REPO_URL} />
        </div>
      </section>

      <section>
        <h2 className="font-semibold text-base">「適應證」有三種，本站能給兩種</h2>
        <ul className="mt-1 list-disc pl-5 text-slate-700 space-y-1">
          <li><b>健保給付規定</b> — 本站主體，來自健保署藥品給付規定條文。</li>
          <li><b>仿單適應症</b> — 來自食藥署許可證資料，與健保給付常有落差。</li>
          <li><b>實務審查尺度</b> — 本站無法提供，只能靠使用者自己的臨床註記累積。</li>
        </ul>
      </section>

      <section>
        <h2 className="font-semibold text-base">致謝與設計來源</h2>
        <p className="mt-1 text-slate-700">
          本站的方法論（以官方開放資料為唯一來源、保存不可變的條文快照、
          以檔名生效日偵測改版並產生 diff）啟發自{' '}
          <a href={INSPIRED_BY.url} target="_blank" rel="noopener noreferrer" className="underline">
            {INSPIRED_BY.name}的 {INSPIRED_BY.work} 專案
          </a>
          ，特此致謝。
        </p>
        <p className="mt-1.5 text-slate-600 text-[13px]">
          本站為獨立實作，程式碼、資料模型與介面均為原創，未複製該專案的任何程式碼或資料；
          兩者的範圍與作法也不同（該專案回溯重建全庫條文的完整歷史，本站則聚焦皮膚科、
          自建站日起累積快照）。與該專案及其作者無隸屬關係，亦未經其背書。
        </p>
      </section>

      <section>
        <h2 className="font-semibold text-base">資料來源與授權</h2>
        <ul className="mt-1 list-disc pl-5 text-slate-700 space-y-1">
          <li>健保藥品主檔：衛生福利部中央健康保險署《健保用藥品項查詢項目檔》，依「政府資料開放授權條款－第 1 版」公眾釋出。</li>
          <li>藥品許可證與適應症：衛生福利部食品藥物管理署《西藥、醫療器材、含藥化粧品許可證資料集》，同上授權。</li>
          <li>
            此開放資料依政府資料開放授權條款進行公眾釋出，使用者於遵守本條款各項規定之前提下，得利用之。
            條款全文：
            <a href="https://data.gov.tw/license" target="_blank" rel="noopener noreferrer" className="underline">data.gov.tw/license</a>
          </li>
          <li>
            藥品給付規定條文為「全民健康保險藥物給付項目及支付標準」（法規命令）之附件，
            依著作權法第 9 條不得為著作權之標的；本站收存之 PDF 快照僅供版本稽核。
          </li>
        </ul>
        <p className="mt-2 text-slate-700">
          本站與衛生福利部、中央健康保險署、食品藥物管理署無任何隸屬或背書關係。
          若您認為本站內容侵害您的權利，請於 GitHub 開 issue，我們將儘速處理。
        </p>
      </section>

      <section>
        <h2 className="font-semibold text-base">免責聲明</h2>
        <p className="mt-1 text-slate-700">
          本站為個人維護之非官方參考工具，內容由健保署與食藥署公開資料自動彙整而成，
          可能因資料時間差、格式變動或程式錯誤而與現行規定不符。
          <b>所有給付規定以中央健康保險署最新公告為準</b>；健保申報與臨床處方之判斷及其後果
          （包含核刪、爭議審議）由使用者自行負責。本站內容不構成醫療建議或申報建議。
          頁面標示之「事前審查」「限專科」等標籤為程式自動抽取，一律以條文原文為準。
        </p>
      </section>
    </article>
  );
}
