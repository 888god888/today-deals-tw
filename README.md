# 今天有好康 · 第六版

台灣優惠索引：不限定品牌，優先顯示折扣幅度有依據、已讀到內文與操作方式、未辨識到特殊資格的情報。保留 GitHub Pages、Python 更新器、GitHub Actions 和 `workflow_dispatch`；不需要前端放任何 token。

## 這次真正改了什麼

- **三區分流**：首頁「大折扣・少門檻」、另區「有參加條件」、另區「待核對情報」。不把搜尋摘要當成已確認活動。
- **實際折扣**：滿 20,000 折 1,000 是 5%，不是「省千元就推薦」；第二件 5 折是同價兩件平均省 25%，不是 50%；回饋會考慮已辨識的上限與最低消費。
- **資格先篩**：新戶、首購、指定信用卡、受邀分眾、辦卡、抽獎、生日、訂閱、指定地區、消費門檻等不會混入少門檻首頁。
- **證據透明**：可展開來源摘錄、操作、限制、優惠碼，以及內文讀取時間。來源聲稱的原價未獨立比價；庫存與結帳價未驗證。
- **來源擴充**：PTT 省錢板 + Steam 板、跨品牌新聞 RSS 搜尋、可新增 RSS/Atom 訂閱、選配跨品牌搜尋 API。官方活動頁是補充，不是唯一的品牌清單。
- **新鮮度誠實**：區分最近成功與最近嘗試；日期不再把過期活動滾到明年；無截止日的情報最多保留 7 天；超過 72 小時未重讀或本輪沿用舊內文，一律待核對。已辨識發布日期且有截止日的情報最多保留 30 天。
- **不實用可隱藏**：本機收藏、跨區收藏查看、隱藏與復原、搜尋／分類／排序。儲存空間受限或內容損壞不會讓頁面停止運作。
- **移除示範優惠**：套件中的正式資料為空，第一次實際更新後才出現資料。舊版示範不會被保留成真優惠。

## 更新原來的 GitHub 專案

1. 解壓縮後把檔案覆蓋到原 repository 的對應路徑，包含隱藏資料夾 `.github`。不要把整個專案多包一層再上傳。
2. 新增 `scripts/quality.py` 和整個 `tests` 資料夾；同時更新 `dist/index.html`、`dist/app.js`、`dist/styles.css`、`dist/data/deals.json`、`config/sources.json`、`scripts/update_deals.py` 和 workflow。
3. **Settings → Pages → Source** 保持 **GitHub Actions**。不要變成「Deploy from a branch」。
4. 到 **Actions → 更新每日好康並部署 → Run workflow** 執行一次，檢查「更新好康資料」輸出與網站來源狀態。
5. 沒有網頁寫入權限時，檢查 Actions 的 repository 權限、Pages 環境與執行紀錄。不要把 GitHub token 放在 `dist`。

既有外部 cron-job 若呼叫同一個 `update-and-deploy.yml` 的 `workflow_dispatch`，不用更換端點。排程仍是台灣時間每天 08:15、18:15；GitHub 排程可能延遲，網站只顯示實際抓取時間。

## 跨品牌搜尋／Threads：需要明確啟用

第六版**不再刮取 Brave 搜尋網頁**，因為網頁改版、限流或封鎖會使其不可靠。改成選配官方 Search API；沒有 key 時，狀態明確顯示「未啟用」，而不是假裝有全網資料。

如果你選擇使用 API：

1. 先自行確認 [Brave Search API](https://brave.com/search/api/) 的當前方案／費用，本專案不會替你註冊、付費或開通。
2. 在 repository **Settings → Secrets and variables → Actions → New repository secret** 新增 `BRAVE_SEARCH_API_KEY`。workflow 已接好；key 只傳給官方 API，不送到網頁或被搜尋到的網站。
3. 再手動執行一次 workflow，查看「跨品牌搜尋」來源是否可讀。`config/sources.json` 中的查詢按優惠、品類、地區尋找，不須逐一補品牌。

**限制：** API 搜尋索引可能延遲、漏文；Threads 頁面可能要求登入或無法抽出內文。這些項目最多列入待核對，沒有保證完整、即時涵蓋 Threads，也不會繞過 CAPTCHA、登入或 HTTP 403/429。未設定 key 仍可跑公開論壇、RSS 與官方頁，但不是全網搜尋。

官方 API 文件：[Web Search](https://api-dashboard.search.brave.com/api-reference/web/search/get)。GitHub Pages 文件：[Custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)。

## 增加資料來源，不用重寫網頁

編輯 `config/sources.json`：

- `news_radar.queries`：按優惠關鍵字、品類與地區增加新聞索引查詢，摘要只列待核對。
- `web_discovery.queries`：啟用 API 後可跨網站搜尋；`freshness: "pw"` 是近一週索引限制，不代表活動仍有效。
- `feeds`：填入自己已確認允許使用的公開 RSS/Atom。新聞全文仍以公開文章頁的可讀內文為準。
- `ptt_*`：新增 PTT 板的 `url`、`name`、`pages`、`article_limit`。優先從最新文章開始讀。
- 官方來源：可調整 `link_selector`、`body_selector`、`item_limit`；無法辨識內頁會顯示「解析未確認」，不假稱來源正常。

RSS 範例（URL 須換成你已確認的真實訂閱，不要直接用下面的佔位網址）：

```json
"feeds": [
  {
    "key": "custom_deals",
    "enabled": true,
    "name": "我的公開優惠訂閱",
    "urls": ["https://example.org/deals.xml"],
    "item_limit": 20
  }
]
```

偏好保留 3C、遊戲娛樂、免費、任務、餐飲食品、家電日用、男性運動、金融支付，排除交通、女性專用品與星巴克。只作文字分類，可能誤判；若有漏收或誤收可調整關鍵字，不能視為理解所有複雜辦法的人工審核。

## 本機執行與測試

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/update_deals.py
python scripts/update_deals.py --validate-only
python -m http.server 8000 -d dist
```

開啟 `http://localhost:8000`，不要直接雙擊 HTML。更新器有每站請求／時間上限，不會無限重試；即使所有來源失敗仍輸出來源狀態，保留上次成功時間，舊情報降為待核對。這讓錯誤狀態可部署顯示，不會冒充更新成功。

指定來源檢查（僅供診斷，請指定不同輸出，避免把正式資料換成不完整的來源清單）：

```bash
python scripts/update_deals.py --sources ptt,ptt_steam,news_radar,web_discovery --output smoke.json
```

互動邏輯測試（DOM，不能取代實際手機版面檢查），需 Node.js 與 jsdom：

```bash
npm install --no-save jsdom
node tests/test_dom.cjs
```

選配實際瀏覽器測試，需 Node.js 與 Playwright：

```bash
npm install --no-save playwright
npx playwright install chromium
node tests/test_ui.cjs
```

測試中的價格／活動是**離線 fixture**，不寫入正式資料。自動化 workflow 執行 Python 規則測試與資料格式檢查，不安裝瀏覽器。

## 驗證範圍與限制

第六版提供可重現的規則與介面測試；交付環境無法解析 PTT／新聞網域，因此**未完成實際來源抓取驗證**，也未在你的 GitHub 帳號部署。瀏覽器下載亦失敗，尚未完成實際渲染／手機版面驗證。首次在 GitHub Actions 執行後，須以實際來源狀態判斷可用範圍，不保證部署後每站都能讀取。

現階段仍是啟發式抓取／文字判斷，不是人工查證、歷史成交價資料庫或即時庫存系統。免費取得、折數、原價對照與回饋計算必須能辨識；只有「史低、破盤」字眼而沒有比例依據，只列待核對。普通促銷會淘汰，未確認來源則列待核對，寧可標出不確定性，不自行補寫參加條件。
