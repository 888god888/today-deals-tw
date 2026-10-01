// DOM behavior regression tests, not a substitute for browser layout QA.
const { JSDOM } = require("jsdom");
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const root = path.resolve(__dirname, "../dist");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const js = fs.readFileSync(path.join(root, "app.js"), "utf8");
const now = new Date().toISOString();
const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Taipei", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
const base = { title: "離線測試：耳機5折", source_key: "test", source_name: "測試來源", source_type: "community", first_seen_at: now, checked_at: now, body_read: true, category: "3C", tags: ["3C"], discount_label: "測試用5折", discount: { strong: true, percent: 50 }, steps: "網站結帳購買", eligibility: "測試條件", limits: "測試限制", hurdles: [], reasons: [], evidence_excerpt: "離線資料", score: 75 };
const fixture = { schema_version: 6, is_demo: false, updated_at: now, attempted_at: now, run_status: "partial", sources: [{ name: "測試搜尋", status: "not_configured", message: "未啟用" }], deals: [{ ...base, id: "easy", status: "easy", url: "https://example.org/a", end_date: today, coupon_code: "TEST50" }], conditional: [{ ...base, id: "conditional", title: "測試新戶優惠", status: "conditional", url: "https://example.org/b", hurdles: ["新戶／首購限定"] }], pending: [{ ...base, id: "pending", title: "測試未讀內文", status: "candidate", url: "https://example.org/c", body_read: false, checked_at: null, reasons: ["未讀內文"] }] };
let checks = 0;
const check = (value, expected) => { assert.equal(value, expected); checks++; };
async function setup(data, storage = "corrupt") {
  const dom = new JSDOM(html, { url: "https://local-test.example/", runScripts: "outside-only" });
  dom.window.fetch = async () => ({ ok: true, json: async () => data });
  if (storage === "corrupt") dom.window.localStorage.setItem("deal-saves", "broken-json");
  if (storage === "disabled") { dom.window.Storage.prototype.getItem = () => { throw new Error("disabled"); }; dom.window.Storage.prototype.setItem = () => { throw new Error("disabled"); }; }
  dom.window.eval(js); await new Promise(resolve => setImmediate(resolve));
  return dom;
}
(async () => {
  const dom = await setup(fixture), document = dom.window.document;
  const $ = selector => document.querySelector(selector);
  const click = selector => $(selector).click();
  const count = () => document.querySelectorAll(".deal-card").length;
  check(count(), 1); check($(".deadline").textContent, "今天截止"); check($("#coverageNotice").hidden, false);
  click(".save-deal"); check($("#savedCount").textContent, "1");
  click('[data-status="conditional"]'); check($(".hurdles").textContent, "新戶／首購限定");
  click("#savedButton"); check($("h3").textContent, base.title);
  click('[data-status="easy"]'); click(".hide-deal"); check(count(), 0); check($("#emptyState").hidden, false);
  click("#resetHidden"); check(count(), 1);
  $("#searchInput").value = "無匹配"; $("#searchInput").dispatchEvent(new dom.window.Event("input")); check(count(), 0);
  click("#clearFilters"); check(count(), 1);
  click('[data-category="免費"]'); check(count(), 0); click("#clearFilters"); check(count(), 1);
  click('[data-status="candidate"]'); check($("h3").textContent, "測試未讀內文"); check($(".evidence-label").textContent.startsWith("僅標題／摘要"), true);
  $("#officialOnly").checked = true; $("#officialOnly").dispatchEvent(new dom.window.Event("change")); check(count(), 0);
  click("#clearFilters"); check(count(), 1);
  check($("#statusTabs .active").getAttribute("aria-pressed"), "true");
  check($("#pendingTotal").textContent, "1");
  dom.window.close();
  const empty = await setup(JSON.parse(fs.readFileSync(path.join(root, "data/deals.json"), "utf8")));
  check(empty.window.document.querySelectorAll(".deal-card").length, 0);
  check(empty.window.document.querySelector("#coverageNotice").textContent.includes("尚未執行抓取"), true); empty.window.close();
  const disabled = await setup(fixture, "disabled"); disabled.window.document.querySelector(".save-deal").click();
  check(disabled.window.document.querySelector("#savedCount").textContent, "1"); disabled.window.close();
  const xssData = JSON.parse(JSON.stringify(fixture)); xssData.deals[0].title = '<img src="bad" onerror="window.bad=1">';
  const xss = await setup(xssData); check(xss.window.document.querySelectorAll(".deal-card img").length, 0); check(xss.window.document.querySelector("h3").textContent, xssData.deals[0].title); xss.window.close();
  const staleData = JSON.parse(JSON.stringify(fixture)); staleData.deals[0].checked_at = new Date(Date.now()-4*86400000).toISOString();
  const stale = await setup(staleData); check(stale.window.document.querySelectorAll(".deal-card").length, 0); check(stale.window.document.querySelector("#pendingTotal").textContent, "2"); stale.window.close();
  console.log(`PASS: ${checks} DOM assertions; no browser layout claim`);
})().catch(e => { console.error(e); process.exitCode = 1; });
