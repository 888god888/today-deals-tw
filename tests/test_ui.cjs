// Local browser regression test; fixture data NEVER goes into dist/data/deals.json.
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const assert = require("node:assert/strict");
const root = path.resolve(__dirname, "../dist");
const output = process.argv[2];
const now = new Date().toISOString();
const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Taipei", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
const base = { title: "測試用：耳機優惠", source_key: "fixture", source_name: "離線測試來源", source_type: "community", first_seen_at: now, checked_at: now, body_read: true, tags: ["3C"], category: "3C", discount_label: "測試價 $500 · 較文中原價省 50%", discount: { strong: true, percent: 50 }, steps: "於網站結帳購買", eligibility: "測試：內文未列明特殊資格", limits: "測試：每人一次；庫存未確認", evidence_excerpt: "離線測試資料，不是真實活動。原價1000元，特價500元，可於網站結帳購買。", hurdles: [], reasons: [], score: 75 };
const fixture = { schema_version: 6, is_demo: false, updated_at: now, attempted_at: now, run_status: "partial", deals: [{ ...base, id: "easy", url: "https://example.org/easy", status: "easy", end_date: today, coupon_code: "TEST50" }], conditional: [{ ...base, id: "conditional", title: "測試用：新戶優惠", url: "https://example.org/new", status: "conditional", hurdles: ["新戶／首購限定"] }], pending: [{ ...base, id: "pending", title: "測試用：尚未讀內文", url: "https://example.org/pending", status: "candidate", checked_at: null, body_read: false, reasons: ["只取得摘要"] }], sources: [{ key: "fixture", name: "離線測試来源", status: "ok", harvested: 3, easy: 1, conditional: 1, candidate: 1 }, { key: "search", name: "跨品牌搜尋", status: "not_configured", message: "未設定搜尋 API" }] };

(async () => {
  const server = http.createServer((req, res) => {
    const pathname = new URL(req.url, "http://localhost").pathname;
    const file = path.resolve(root, "." + (pathname === "/" ? "/index.html" : pathname));
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file)) { res.writeHead(404).end(); return; }
    res.setHeader("Content-Type", file.endsWith(".js") ? "text/javascript" : file.endsWith(".css") ? "text/css" : file.endsWith(".json") ? "application/json" : "text/html");
    res.end(fs.readFileSync(file));
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  let browser;
  let checks = 0;
  const check = (actual, expected) => { assert.equal(actual, expected); checks++; };
  try {
    browser = await chromium.launch({ headless: true });
    for (const width of [390, 1280]) {
      const context = await browser.newContext({ viewport: { width, height: 900 } });
      const page = await context.newPage();
      const errors = []; page.on("pageerror", e => errors.push(e.message));
      await page.route("**/data/deals.json?*", route => route.fulfill({ json: fixture }));
      await page.addInitScript(() => { localStorage.setItem("deal-saves", "broken-json"); });
      await page.goto(`http://127.0.0.1:${server.address().port}`);
      await page.waitForFunction(() => document.querySelector("#resultCount").textContent === "1 筆");
      check(await page.locator(".deal-card").count(), 1);
      check(await page.locator(".deadline").textContent(), "今天截止");
      check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      check(await page.locator("#coverageNotice").isVisible(), true);
      await page.locator(".save-deal").click(); check(await page.locator("#savedCount").textContent(), "1");
      await page.locator('[data-status="conditional"]').click(); check(await page.locator(".hurdles").textContent(), "新戶／首購限定");
      await page.locator("#savedButton").click(); check(await page.locator("h3").textContent(), base.title);
      await page.locator('[data-status="easy"]').click();
      await page.locator(".hide-deal").click(); check(await page.locator("#emptyState").isVisible(), true);
      await page.locator("#resetHidden").click(); check(await page.locator(".deal-card").count(), 1);
      await page.locator("#searchInput").fill("不可能匹配"); check(await page.locator("#emptyState").isVisible(), true);
      await page.locator("#clearFilters").click(); check(await page.locator(".deal-card").count(), 1);
      await page.locator('[data-status="candidate"]').click(); check(await page.locator("h3").textContent(), "測試用：尚未讀內文");
      await page.locator(".deal-details summary").click(); check((await page.locator(".evidence-label").textContent()).startsWith("僅標題／摘要"), true);
      await page.locator('[data-status="easy"]').click();
      if (output) { fs.mkdirSync(output, { recursive: true }); await page.screenshot({ path: path.join(output, `fixture-${width}.png`), fullPage: true }); }
      check(errors.length, 0);
      await context.close();
    }
    // Empty production bundle must remain honest and usable.
    const page = await browser.newPage();
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.waitForFunction(() => document.querySelector("#resultCount").textContent === "0 筆");
    check(await page.locator(".deal-card").count(), 0);
    check((await page.locator("#coverageNotice").textContent()).includes("尚未執行抓取"), true);
    // Storage-disabled browsers must still load the UI.
    const blocked = await browser.newPage();
    await blocked.addInitScript(() => { Storage.prototype.getItem = () => { throw new Error("disabled"); }; Storage.prototype.setItem = () => { throw new Error("disabled"); }; });
    await blocked.route("**/data/deals.json?*", route => route.fulfill({ json: fixture }));
    await blocked.goto(`http://127.0.0.1:${server.address().port}`);
    await blocked.waitForFunction(() => document.querySelector("#resultCount").textContent === "1 筆");
    await blocked.locator(".save-deal").click(); check(await blocked.locator("#savedCount").textContent(), "1");
    console.log(`PASS: ${checks} browser assertions (390px, 1280px, corrupt/disabled storage, empty production data)`);
  } finally { if (browser) await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(e => { console.error(e); process.exitCode = 1; });
