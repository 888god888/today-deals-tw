# 今天有好康 · 第七版

把優惠索引改成一份能快速看完的個人小抄，沿用 GitHub Pages、Python 更新器與外部 Cron-job。

## 這版的使用方式

- **五則精選**：開啟先看最多 5 則，按實際折扣依據、新鮮度、關注詞與優先品類排序，並分散品類。不是隨機洗牌，也不是每天硬湊五則。
- **還沒看過**：按「這批看完了」才記錄已讀，只標記當前顯示的項目。下次仍保留未讀；重抓但內容相同不算更新，折扣、條件、優惠碼或截止日等變更則標示「內容有變動」。
- **我的口味 → 想找什麼**：輸入商品或關鍵字，例如「耳機、免費遊戲」，可從已收集內容找出符合標題或優惠的情報。多個詞採任一命中；不會額外觸發全網比價，也沒有推播。
- **優先類型**只加分、不封鎖其他類；**完全不想看**會按標題與優惠內容隱藏含該字詞的項目。收藏頁仍可看被口味屏蔽的收藏；逐則「不實用，隱藏」則要透過「恢復已隱藏項目」還原。
- **更多篩選**收在可展開區塊；「有參加條件」「待核對情報」保留分區，不會為了補足精選而混進少門檻首頁。

口味、收藏、隱藏與已讀留在同一瀏覽器，沒有雲端同步；清除瀏覽資料或換裝置會重設。儲存被瀏覽器停用時，本次仍可使用但無法跨次保存。

## 收集端的具體修正

- PTT 的 `[情報]` 文章即使只寫陌生品牌與數字售價，也會讀內文再判斷，不再要求標題必須有「折、特價」。加入價格符號與「降價、特賣、限免、跳水」的候選辨識。
- RSS／新聞先讀每一組查詢，再輪流選取候選，避免第一組餐飲或 3C 新聞占滿整個名額；超過 7 天的已知發布日期先剔除。
- 支援 Atom 未註明 `rel` 的正常文章連結，以及 `updated` 日期。這是解析修正，沒有新增付費服務或寫死品牌名單。
- 保留第六版折扣實算、過期排除、證據摘錄與失敗降級。來源可讀不等於優惠核實，新聞摘要也不會冒充活動內文。

## 更新原來的 GitHub 專案

1. 解壓縮後把檔案覆蓋到原 repository 的對應路徑，包含隱藏資料夾 `.github`。不要把整個專案多包一層再上傳。
2. 覆蓋程式與設定，包含新增的 `dist/feed.js`、`package.json`、`package-lock.json` 和 `tests`。**這份更新包刻意不附 `dist/data/deals.json`，請保留 repository 裡原本的資料檔與價格／發現歷史。** 全新部署時，第一次 Action 執行會建立資料檔；之前頁面會提示尚未抓取。
3. **Settings → Pages → Source** 保持 **GitHub Actions**。不要變成「Deploy from a branch」。
4. 到 **Actions → 更新每日好康並部署 → Run workflow** 執行一次，檢查「更新好康資料」輸出與網站來源狀態。
5. 沒有網頁寫入權限時，檢查 Actions 的 repository 權限、Pages 環境與執行紀錄。不要把 GitHub token 放在 `dist`。

既有外部 cron-job 若呼叫同一個 `update-and-deploy.yml` 的 `workflow_dispatch`，不用更換端點。排程仍是台灣時間每天 08:15、18:15；GitHub 排程可能延遲，網站只顯示實際抓取時間。

## 跨品牌搜尋／Threads：需要明確啟用

目前**不刮取 Brave 搜尋網頁**，因為網頁改版、限流或封鎖會使其不可靠。改成選配官方 Search API；沒有 key 時，狀態明確顯示「未啟用」，而不是假裝有全網資料。

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
npm ci
npm test
```

選配實際瀏覽器測試，需 Node.js 與 Playwright：

```bash
npm install --no-save playwright
npx playwright install chromium
node tests/test_ui.cjs
```

測試中的價格／活動是**離線 fixture**，不寫入正式資料。自動化 workflow 執行 Python 規則測試與資料格式檢查，不安裝瀏覽器。

## 驗證範圍與限制

本版通過 56 項 Python 資料規則測試、26 項既有 DOM 互動檢查與 31 項個人化／回訪檢查。實際嘗試連線 PTT 與新聞來源時，本環境回覆「網域無法解析」，因此**未驗證今日實際情報內容**。未進行瀏覽器渲染與真機手機操作，也未在你的 GitHub 帳號部署。首次更新後請查看真實來源狀態；不保證每站都能讀取。

現階段仍是啟發式抓取／文字判斷，不是人工查證、歷史成交價資料庫或即時庫存系統。免費取得、折數、原價對照與回饋計算必須能辨識；只有「史低、破盤」字眼而沒有比例依據，只列待核對。普通促銷會淘汰，未確認來源則列待核對，寧可標出不確定性，不自行補寫參加條件。
