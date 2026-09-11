# 今天有好康

每天彙整台灣免費領取、餐飲、購物、交通、金融與 APP 任務優惠的靜態網站。

## 已完成

- 手機與桌面響應式介面
- 分類、關鍵字、官方來源與排序篩選
- 瀏覽器本機收藏
- PTT 省錢板，以及麥當勞、肯德基、星巴克、全家、萊爾富與 LINE Pay 官方活動頁抓取器
- 進入活動內頁整理「拿到什麼、適用條件、領取步驟、限制與優惠碼」
- 預設排除女性專用品；排除詞可在 `config/sources.json` 自行增減
- 單一來源抓取失敗時保留上一版資料
- GitHub Actions 每天台灣時間 08:15、18:15 更新並部署 GitHub Pages
- 過期活動自動隱藏，資料頁保留來源狀態

## 第一次部署

1. 在 GitHub 建立一個空白 repository。
2. 把本專案所有檔案上傳到 `main` 分支。
3. 到 repository 的 **Settings → Pages → Build and deployment**。
4. 將 **Source** 選成 **GitHub Actions**。
5. 到 **Actions** 開啟「更新每日好康並部署」，按 **Run workflow**。
6. 執行完成後，網址會顯示在該次 workflow 的 `deploy` 結果與 Settings → Pages。

## 調整來源

編輯 `config/sources.json` 可以停用來源、調整抓取頁數、筆數或 `preferences.exclude_terms`。各站改版可能導致解析失敗；頁面下方會顯示來源狀態，失敗時不會清空前一次成功資料。

## 本機查看

請在專案目錄執行：

```bash
python -m http.server 8000 -d dist
```

再開啟 `http://localhost:8000`。不要直接雙擊 `index.html`，因為瀏覽器可能阻擋它讀取 JSON。

## 資料提醒

本網站只提供活動索引與簡短摘要，不取代主辦單位公告。自動抓取僅讀取公開頁面，應控制頻率並遵守來源網站規範；若某來源要求停止自動存取，請在設定中將它停用。
