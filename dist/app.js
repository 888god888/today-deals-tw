"use strict";
function readLocal(key) {
  try { const value = JSON.parse(localStorage.getItem(key) || "[]"); return new Set(Array.isArray(value) ? value.filter(v => typeof v === "string") : []); }
  catch { return new Set(); }
}
function persist(key, values) { try { localStorage.setItem(key, JSON.stringify([...values])); } catch { /* Browsing remains usable with storage disabled. */ } }
const F = DealFeed;
function readObject(key, fallback = {}) {
  try { const v = JSON.parse(localStorage.getItem(key)); return v && typeof v === "object" && !Array.isArray(v) ? v : fallback; }
  catch { return fallback; }
}
function writeObject(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); return true; } catch { return false; } }
const storedPrefs = readObject("deal-preferences-v7");
const state = { deals: [], status: "easy", category: "全部", query: "", officialOnly: false, savedOnly: false, sort: "recommended", mode: "digest", saved: readLocal("deal-saves"), hidden: readLocal("deal-hidden"), seen: readObject("deal-read-v7"), prefs: {
  watch: Array.isArray(storedPrefs.watch) ? storedPrefs.watch.filter(v => typeof v === "string" && v.trim()).slice(0, 20) : [],
  mute: Array.isArray(storedPrefs.mute) ? storedPrefs.mute.filter(v => typeof v === "string" && v.trim()).slice(0, 20) : [],
  priority: Array.isArray(storedPrefs.priority) ? storedPrefs.priority.filter(v => F.categories.includes(v)) : []
} };
const $ = selector => document.querySelector(selector);
const els = { grid: $("#dealGrid"), template: $("#dealTemplate"), empty: $("#emptyState"), count: $("#resultCount"), search: $("#searchInput"), filters: $("#filters"), tabs: $("#statusTabs"), official: $("#officialOnly"), sort: $("#sortSelect"), savedButton: $("#savedButton") };
const labels = { easy: "大折扣・少門檻", conditional: "有參加條件", candidate: "待核對情報" };
const explanations = {
  easy: "已讀內文、達折扣門檻，且未辨識到特殊資格；不代表已確認庫存或結帳價。",
  conditional: "優惠幅度達標，但有新戶、指定信用卡、名額、消費等門檻；先看自己是否適用。",
  candidate: "缺少內文、折扣依據、操作方式，或只有最高／最低宣傳值。這些是線索，不是已確認優惠。"
};
const dateFormat = new Intl.DateTimeFormat("zh-TW", { timeZone: "Asia/Taipei", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
function shortDate(value) { const d = new Date(value); return value && Number.isFinite(d.valueOf()) ? dateFormat.format(d) : "未知"; }
function taipeiDay(value = new Date()) { return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Taipei", year: "numeric", month: "2-digit", day: "2-digit" }).format(value); }
function daysUntil(value) { return value ? Math.round((Date.parse(value + "T00:00:00+08:00") - Date.parse(taipeiDay() + "T00:00:00+08:00")) / 86400000) : null; }
function deadlineLabel(deal) { const days = daysUntil(deal.end_date); return days === null ? "截止日未確認" : days === 0 ? "今天截止" : days > 0 && days <= 3 ? `${days} 天後截止` : `${deal.end_date.replaceAll("-", "/")} 截止`; }
function safeLink(value) { try { const u = new URL(value); return u.protocol === "https:" && !u.username && !u.password ? u.href : null; } catch { return null; } }
function currentDeals() {
  const now = Date.now();
  return state.deals.filter(d => {
    if (state.hidden.has(d.id) || !safeLink(d.url)) return false;
    if (!state.savedOnly && F.matches(d, state.prefs.mute)) return false;
    if (d.end_date && daysUntil(d.end_date) < 0) return false;
    const first = Date.parse(d.published_at || d.first_seen_at);
    return Number.isFinite(first) && now - first <= (d.end_date ? 30 : 7) * 86400000;
  }).map(d => {
    const check = Date.parse(d.checked_at);
    return d.status !== "candidate" && (!Number.isFinite(check) || now - check > 72 * 3600000)
      ? { ...d, status: "candidate", reasons: [...(d.reasons || []), "超過 72 小時未重新讀取，需重查"] } : d;
  });
}
function visibleDeals() {
  const q = state.query.toLowerCase();
  let items = currentDeals().filter(d => {
    if (state.savedOnly ? !state.saved.has(d.id) : d.status !== state.status) return false;
    if (!state.savedOnly && state.mode === "watch" && !F.matches(d, state.prefs.watch)) return false;
    if (!state.savedOnly && state.mode === "updates" && F.novelty(d, state.seen) === "seen") return false;
    if (state.category !== "全部" && !(d.tags || [d.category]).includes(state.category)) return false;
    if (state.officialOnly && d.source_type !== "official") return false;
    const text = [d.title, d.summary, d.benefit, d.eligibility, d.steps, d.limits, d.coupon_code, d.source_name, ...(d.hurdles || [])].join(" ").toLowerCase();
    return !q || text.includes(q);
  }).sort((a, b) => {
    if (state.sort === "newest") return String(b.published_at || b.first_seen_at).localeCompare(String(a.published_at || a.first_seen_at));
    if (state.sort === "ending") return String(a.end_date || "9999").localeCompare(String(b.end_date || "9999"));
    if (state.sort === "discount") return (b.discount?.percent || 0) - (a.discount?.percent || 0);
    const options = { prefs: state.prefs, seen: state.seen, saved: state.saved, now: Date.now() };
    return F.score(b, options) - F.score(a, options) || a.id.localeCompare(b.id);
  });
  return !state.savedOnly && state.mode === "digest" ? F.digest(items, 5) : items;
}
function recommendation(d) {
  const reasons = [];
  if (F.matches(d, state.prefs.watch)) reasons.push("符合你的關注");
  if (state.prefs.priority.includes(F.primary(d))) reasons.push("你優先看的類型");
  if (d.discount?.kind === "free") reasons.push("文中標示可免費取得");
  else if (d.discount?.percent >= 50) reasons.push("文中折扣省一半以上");
  if (d.status === "easy") reasons.push("未見特殊資格限制");
  return reasons.slice(0, 2).join(" · ") || "依折扣依據與新鮮度排序";
}
function render() {
  const deals = visibleDeals();
  els.grid.replaceChildren();
  for (const [index, d] of deals.entries()) {
    const node = els.template.content.cloneNode(true), card = node.querySelector(".deal-card");
    const set = (selector, text) => { node.querySelector(selector).textContent = text || "未提供"; };
    const novelty = F.novelty(d, state.seen);
    set(".new-badge", novelty === "unread" ? "還沒看過" : novelty === "changed" ? "內容有變動" : "已讀");
    node.querySelector(".new-badge").classList.toggle("was-read", novelty === "seen");
    set(".pick-number", !state.savedOnly && state.mode === "digest" ? `PICK ${String(index + 1).padStart(2, "0")}` : labels[d.status]);
    set(".recommendation-reason", recommendation(d));
    const description = node.querySelector(".benefit-description");
    description.textContent = d.benefit && d.benefit !== d.title ? d.benefit : "";
    description.hidden = !description.textContent;
    const days = daysUntil(d.end_date);
    if (days !== null && days <= 3) { card.classList.add("urgent"); node.querySelector(".deadline").classList.add("soon"); }
    set(".category-badge", (d.tags || [d.category]).slice(0, 2).join(" · "));
    set(".source-badge", d.source_type === "official" ? "官方頁面" : d.source_type === "community" ? "論壇情報" : "公開索引情報");
    set("h3", d.title); set(".benefit-text", d.discount_label);
    set(".ease-text", d.status === "easy" ? "未見特殊資格 · 庫存仍須核對" : labels[d.status]);
    set(".steps-preview", `怎麼拿：${d.steps || "方式未確認"}`);
    set(".eligibility-text", d.eligibility); set(".steps-text", d.steps); set(".limits-text", d.limits);
    for (const reason of [...(d.hurdles || []), ...(d.reasons || [])]) { const badge = document.createElement("span"); badge.textContent = reason; node.querySelector(".hurdles").append(badge); }
    if (d.coupon_code) {
      node.querySelector(".code-row").hidden = false; set(".coupon-code", d.coupon_code);
      const copy = node.querySelector(".copy-code"); copy.addEventListener("click", async () => { try { await navigator.clipboard.writeText(d.coupon_code); copy.textContent = "已複製"; } catch { copy.textContent = "請手動選取"; } });
    }
    set(".deadline", deadlineLabel(d)); set(".checked-at", d.checked_at ? `內文讀取 ${shortDate(d.checked_at)}` : `首次發現 ${shortDate(d.first_seen_at)}`);
    set(".evidence-label", d.body_read ? "已讀內文摘錄（原價為來源聲稱，未獨立比價）" : `僅標題／摘要：${d.body_note || "內文未讀"}`);
    set(".evidence-text", d.evidence_excerpt || "沒有可引用的內文，不補寫領取條件。"); set(".source-name", `來源：${d.source_name}`);
    const link = node.querySelector(".deal-link"); link.href = safeLink(d.url); link.textContent = d.source_type === "official" ? "查看官方頁面 ↗" : "查看情報原文 ↗";
    const save = node.querySelector(".save-deal"), saved = state.saved.has(d.id); save.textContent = saved ? "♥" : "♡"; save.setAttribute("aria-pressed", String(saved)); save.setAttribute("aria-label", `${saved ? "取消收藏" : "收藏"}：${d.title}`);
    save.addEventListener("click", () => { state.saved.has(d.id) ? state.saved.delete(d.id) : state.saved.add(d.id); persist("deal-saves", state.saved); render(); });
    node.querySelector(".hide-deal").addEventListener("click", () => { state.hidden.add(d.id); persist("deal-hidden", state.hidden); render(); });
    els.grid.append(node);
  }
  els.empty.hidden = deals.length > 0; els.grid.hidden = !deals.length;
  els.count.textContent = `${deals.length} 筆`; $("#resultTitle").textContent = state.savedOnly ? "我的收藏（跨區）" : labels[state.status]; $("#statusExplanation").textContent = state.savedOnly ? "收藏仍會排除已過期項目；超過 72 小時未重查的項目會標為待核對。" : explanations[state.status];
  $("#savedCount").textContent = state.saved.size; els.savedButton.setAttribute("aria-pressed", String(state.savedOnly));
  const current = currentDeals();
  for (const [status, id] of [["easy", "easyTotal"], ["conditional", "conditionalTotal"], ["candidate", "pendingTotal"]]) $("#" + id).textContent = current.filter(d => d.status === status).length;
  $("#emptyTitle").textContent = state.savedOnly ? "目前沒有可顯示的收藏" : "目前沒有符合條件的優惠";
  $("#emptyCopy").textContent = state.deals.length ? "可能是篩選、已隱藏、已過期，或情報尚未讀到完整條款。可清除篩選或查看待核對情報；不以宣傳標題充數。" : "本輪尚無可顯示的優惠。查看來源狀態，確認是尚未執行、讀取失敗，或未找到符合門檻的內容。";
  $("#viewPending").hidden = state.status === "candidate" && !state.savedOnly;
  renderViewContext(deals, current);

  for (const b of els.tabs.querySelectorAll("button")) { const active = b.dataset.status === state.status && !state.savedOnly; b.classList.toggle("active", active); b.setAttribute("aria-pressed", String(active)); }
  for (const b of els.filters.querySelectorAll("button")) { const active = b.dataset.category === state.category; b.classList.toggle("active", active); b.setAttribute("aria-pressed", String(active)); }
}
function renderHealth(data) {
  const sources = data.sources || [], labels = { ok: "可讀", partial: "部分可讀", error: "讀取失敗", unparsed: "解析未確認", not_configured: "未啟用" };
  $("#sourceList").replaceChildren();
  for (const s of sources) {
    const item = document.createElement("div"); item.className = `source-item ${s.status === "ok" ? "" : "error"}`;
    const name = document.createElement("strong"); name.textContent = s.name;
    const status = document.createElement("span"); status.className = "source-state"; status.textContent = labels[s.status] || s.status;
    const counts = document.createElement("p"); counts.textContent = `候選 ${s.harvested || 0} · 首頁 ${s.easy || 0} · 有門檻 ${s.conditional || 0} · 待核對 ${s.candidate || 0} · 淘汰 ${s.rejected || 0}`;
    const note = document.createElement("p"); note.textContent = s.message || "完成讀取；未確認庫存／結帳價";
    item.append(name, status, counts, note); $("#sourceList").append(item);
  }
  const problems = sources.filter(s => s.status !== "ok"), notice = $("#coverageNotice");
  $("#sourceSummary").textContent = sources.length ? `${sources.length - problems.length}/${sources.length} 個來源完整可讀` : "尚未執行更新";
  const stamp = data.updated_at ? `最近有來源成功 ${shortDate(data.updated_at)}` : "尚無成功更新";
  $("#updatedAt").textContent = `${stamp}${data.attempted_at ? ` · 最近嘗試 ${shortDate(data.attempted_at)}` : ""}（台灣時間）`;
  notice.hidden = !problems.length && data.run_status !== "not_run";
  notice.replaceChildren();
  const text = document.createElement("span"); text.textContent = data.run_status === "not_run" ? "尚未執行抓取。請先在 GitHub Actions 執行一次更新，本版不附虛構的示範優惠。 " : `${problems.length} 個來源未完整讀取或未啟用；此頁不是全網優惠清單。 `;
  const link = document.createElement("a"); link.href = "#sourcePanel"; link.textContent = "查看原因"; link.addEventListener("click", () => { $("#sourcePanel").open = true; });
  notice.append(text, link);
}
async function loadDeals() {
  try {
    const response = await fetch(`data/deals.json?v=${Date.now()}`, { cache: "no-store" }); if (response.status === 404) { state.deals = []; renderHealth({ run_status: "not_run" }); render(); return; } if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json(); if (data.schema_version !== 6 || data.is_demo) throw new Error("資料格式不相容");
    state.deals = [...(data.deals || []), ...(data.conditional || []), ...(data.pending || [])]; renderHealth(data); render();
  } catch (error) {
    $("#updatedAt").textContent = "資料讀取失敗"; render(); const notice = $("#coverageNotice"); notice.hidden = false; notice.textContent = "無法讀取優惠資料。請確認 app.js 與 dist/data/deals.json 一起更新，並透過網站網址開啟。"; console.error(error);
  }
}
els.tabs.addEventListener("click", e => { const b = e.target.closest("[data-status]"); if (b) { state.status = b.dataset.status; state.savedOnly = false; render(); } });
els.filters.addEventListener("click", e => { const b = e.target.closest("[data-category]"); if (b) { state.category = b.dataset.category; render(); } });
els.search.addEventListener("input", e => { state.query = e.target.value.trim(); render(); });
els.official.addEventListener("change", e => { state.officialOnly = e.target.checked; render(); });
els.sort.addEventListener("change", e => { state.sort = e.target.value; render(); });
els.savedButton.addEventListener("click", () => { state.savedOnly = !state.savedOnly; render(); });
$("#clearFilters").addEventListener("click", () => { Object.assign(state, { category: "全部", query: "", officialOnly: false, savedOnly: false, mode: "all" }); els.search.value = ""; els.official.checked = false; render(); });
$("#viewPending").addEventListener("click", () => { state.status = "candidate"; state.mode = "all"; state.savedOnly = false; state.category = "全部"; state.query = ""; state.officialOnly = false; els.search.value = ""; els.official.checked = false; render(); });
$("#resetHidden").addEventListener("click", () => { state.hidden.clear(); persist("deal-hidden", state.hidden); render(); });
document.addEventListener("keydown", e => { if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { e.preventDefault(); $("#filterPanel").open = true; els.search.focus(); } });
function renderViewContext(deals, current) {
  const eligible = current.filter(d => d.status === state.status);
  const unread = eligible.filter(d => F.novelty(d, state.seen) !== "seen");
  const watch = eligible.filter(d => F.matches(d, state.prefs.watch));
  $("#unreadCount").textContent = unread.length;
  $("#watchCount").textContent = watch.length;
  const modeLabels = { digest: "五則精選", updates: "還沒看過與內容更新", watch: "我的關注", all: "全部優惠" };
  if (!state.savedOnly) $("#resultTitle").textContent = `${modeLabels[state.mode]} · ${labels[state.status]}`;
  $("#digestNote").textContent = state.savedOnly ? "想下手之前，回來看你的收藏。過期情報會自動退出列表。"
    : state.mode === "watch" ? (state.prefs.watch.length ? `正在留意：${state.prefs.watch.join("、")}。只比對已收集的商品標題與優惠內容。` : "還沒填想找的東西。打開「我的口味」，寫下耳機、免費遊戲等關鍵字。")
    : state.mode === "updates" ? (unread.length ? `此分類還有 ${unread.length} 則未讀或內容變更；重複抓取相同內容不會算更新。` : "這個分類已看完。可以換個分類，或等下一次資料更新。")
    : state.mode === "digest" ? `每次最多 5 則，分散品類、照你的關注與口味排序。${unread.length ? `這個分類有 ${unread.length} 則未讀或內容變動。` : "目前沒有未讀更新，以下是仍有效的優惠。"}`
    : "自己逛全部情報；有資格限制、待核對內容，仍分區呈現。";
  $("#markRead").hidden = !deals.length;
  $("#endOfBatch").hidden = !deals.length || state.savedOnly;
  $("#showAll").hidden = state.mode === "all" || state.savedOnly;
  for (const b of $("#feedModes").querySelectorAll("button")) {
    const active = !state.savedOnly && b.dataset.mode === state.mode;
    b.classList.toggle("active", active); b.setAttribute("aria-pressed", String(active));
  }
  const filters = [state.category !== "全部" && state.category, state.query && `搜尋：${state.query}`, state.officialOnly && "限官方", state.status !== "easy" && labels[state.status]].filter(Boolean);
  $("#activeFilterLabel").textContent = filters.length ? ` · ${filters.join(" / ")}` : "";
  if (!deals.length && !state.savedOnly && state.mode === "watch") {
    $("#emptyTitle").textContent = state.prefs.watch.length ? "還沒遇到符合關注的情報" : "先寫下你想找什麼";
    $("#emptyCopy").textContent = state.prefs.watch.length ? "可換看有參加條件／待核對區。沒有命中不代表市場沒有折扣；本站僅從可讀來源收集。" : "按「我的口味」設定商品或關鍵字。它會找出已收集的相關優惠，不需指定品牌。";
  }
  if (!deals.length && !state.savedOnly && state.mode === "updates" && state.deals.length) {
    $("#emptyTitle").textContent = "這裡已經看完了";
    $("#emptyCopy").textContent = "查看全部仍有效的優惠，或等下次更新。重複讀取同一批資料，不會重新算成新消息。";
  }
}
function openPreferences(open = true) {
  $("#preferencesPanel").hidden = !open;
  $("#preferencesButton").setAttribute("aria-expanded", String(open));
  if (open) {
    $("#watchInput").value = state.prefs.watch.join("、"); $("#muteInput").value = state.prefs.mute.join("、");
    for (const input of $("#priorityChoices").querySelectorAll("input")) input.checked = state.prefs.priority.includes(input.value);
    $("#watchInput").focus();
  } else $("#preferencesButton").focus();
}
for (const category of F.categories) {
  const label = document.createElement("label"), input = document.createElement("input");
  input.type = "checkbox"; input.value = category; label.append(input, document.createTextNode(category)); $("#priorityChoices").append(label);
}
$("#feedModes").addEventListener("click", e => {
  const b = e.target.closest("[data-mode]"); if (!b) return;
  state.mode = b.dataset.mode; state.savedOnly = false; render();
});
$("#showAll").addEventListener("click", () => { state.mode = "all"; state.savedOnly = false; render(); });
function markBatchRead() {
  const batch = visibleDeals();
  for (const d of batch) { delete state.seen[d.id]; state.seen[d.id] = F.fingerprint(d); }
  // Bounded local history, preserving most recently read records.
  state.seen = Object.fromEntries(Object.entries(state.seen).slice(-2000));
  const saved = writeObject("deal-read-v7", state.seen);
  render();
  $("#readStatus").textContent = `已標記這批 ${batch.length} 則${saved ? "；下次從沒看過的開始" : "；瀏覽器無法保存，關閉後可能重置"}`;
}
$("#markRead").addEventListener("click", markBatchRead);
$("#markReadBottom").addEventListener("click", () => { markBatchRead(); $("#dealGrid").scrollIntoView?.({ behavior: "smooth", block: "start" }); });
$("#preferencesButton").addEventListener("click", () => openPreferences($("#preferencesPanel").hidden));
$("#closePreferences").addEventListener("click", () => openPreferences(false));
$("#preferencesForm").addEventListener("submit", e => {
  e.preventDefault();
  state.prefs = { watch: F.normalizeWords($("#watchInput").value), mute: F.normalizeWords($("#muteInput").value), priority: [...$("#priorityChoices").querySelectorAll("input:checked")].map(i => i.value) };
  const saved = writeObject("deal-preferences-v7", state.prefs);
  openPreferences(false); render();
  $("#readStatus").textContent = saved ? "已儲存你的口味" : "已套用；瀏覽器無法保存，關閉後可能重置";
});
$("#resetPreferences").addEventListener("click", () => { state.prefs = { watch: [], mute: [], priority: [] }; writeObject("deal-preferences-v7", state.prefs); openPreferences(); render(); });
document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("#preferencesPanel").hidden) openPreferences(false); });
loadDeals();
