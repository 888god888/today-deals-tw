const state = { deals: [], category: "全部", query: "", officialOnly: false, savedOnly: false, sort: "recommended", saved: new Set(JSON.parse(localStorage.getItem("deal-saves") || "[]")) };

const els = {
  grid: document.querySelector("#dealGrid"), template: document.querySelector("#dealTemplate"), empty: document.querySelector("#emptyState"),
  count: document.querySelector("#resultCount"), title: document.querySelector("#resultTitle"), search: document.querySelector("#searchInput"),
  filters: document.querySelector("#filters"), official: document.querySelector("#officialOnly"), sort: document.querySelector("#sortSelect"),
  savedButton: document.querySelector("#savedButton"), savedCount: document.querySelector("#savedCount"), sourceList: document.querySelector("#sourceList")
};

const categoryIcons = { "免費": "🎁", "餐飲": "🍔", "購物": "🛍", "交通": "🛵", "金融": "💳", "任務": "📱", "其他": "✨" };
const excludedTerms = ["衛生棉", "護墊", "生理褲", "月經", "私密處", "私密保養", "口紅", "唇膏", "粉底", "睫毛膏", "眼影", "腮紅", "彩妝", "美妝", "卸妝", "化妝", "女裝", "洋裝", "胸罩", "女性內衣", "高跟鞋", "女鞋", "美甲", "指甲油", "假睫毛", "女香", "女性香水", "女用"];

function escapeText(value) { const span = document.createElement("span"); span.textContent = value || ""; return span.textContent; }
function daysUntil(dateText) { if (!dateText) return null; const end = new Date(`${dateText}T23:59:59+08:00`); return Math.ceil((end - new Date()) / 86400000); }
function deadlineLabel(deal) {
  if (!deal.end_date) return "依活動頁公告";
  const days = daysUntil(deal.end_date);
  if (days < 0) return "已截止";
  if (days === 0) return "今天截止";
  if (days <= 3) return `${days} 天後截止`;
  return deal.end_date.replaceAll("-", "/");
}

function isExcludedDeal(deal) {
  const text = [deal.title, deal.brand, deal.summary, deal.benefit, deal.eligibility, deal.steps, deal.limits].join(" ").toLowerCase();
  return excludedTerms.some(term => text.includes(term.toLowerCase()));
}

function visibleDeals() {
  const q = state.query.toLowerCase();
  return state.deals.filter(deal => {
    const searchable = [deal.title, deal.brand, deal.summary, deal.benefit, deal.eligibility, deal.steps, deal.limits].join(" ").toLowerCase();
    if (isExcludedDeal(deal)) return false;
    if (deal.end_date && daysUntil(deal.end_date) < 0) return false;
    if (state.category !== "全部" && deal.category !== state.category) return false;
    if (state.officialOnly && deal.source_type !== "official") return false;
    if (state.savedOnly && !state.saved.has(deal.id)) return false;
    return !q || `${searchable} ${deal.coupon_code || ""} ${deal.source_name || ""}`.toLowerCase().includes(q);
  }).sort((a, b) => {
    if (state.sort === "newest") return String(b.published_at || "").localeCompare(String(a.published_at || ""));
    if (state.sort === "ending") return String(a.end_date || "9999-12-31").localeCompare(String(b.end_date || "9999-12-31"));
    return (b.score || 0) - (a.score || 0);
  });
}

function toggleSaved(id) {
  state.saved.has(id) ? state.saved.delete(id) : state.saved.add(id);
  localStorage.setItem("deal-saves", JSON.stringify([...state.saved]));
  render();
}

function render() {
  const deals = visibleDeals();
  els.grid.replaceChildren();
  deals.forEach(deal => {
    const node = els.template.content.cloneNode(true);
    const card = node.querySelector(".deal-card");
    const days = daysUntil(deal.end_date);
    if (days !== null && days <= 3) card.classList.add("urgent");
    node.querySelector(".category-badge").textContent = `${categoryIcons[deal.category] || "✨"} ${deal.category}`;
    const sourceBadge = node.querySelector(".source-badge");
    sourceBadge.textContent = deal.source_type === "official" ? "官方" : "社群情報";
    if (deal.source_type === "official") sourceBadge.classList.add("official");
    node.querySelector(".brand-name").textContent = deal.brand || deal.source_name;
    node.querySelector("h3").textContent = deal.title;
    node.querySelector(".deal-summary").textContent = deal.summary || "已整理活動的主要辦法如下。";
    node.querySelector(".benefit-text").textContent = deal.benefit || deal.summary || "優惠內容請見下方說明";
    node.querySelector(".eligibility-text").textContent = deal.eligibility || "一般使用者；若為分眾或會員限定會以活動頁顯示為準";
    node.querySelector(".steps-text").textContent = deal.steps || deal.claim || "開啟活動頁後依頁面指示參加";
    node.querySelector(".limits-text").textContent = deal.limits || "名額、庫存及適用門市以主辦單位即時公告為準";
    if (deal.coupon_code) { node.querySelector(".code-row").hidden = false; node.querySelector(".coupon-code").textContent = deal.coupon_code; }
    const deadline = node.querySelector(".deadline");
    deadline.textContent = deadlineLabel(deal);
    if (days !== null && days <= 3) deadline.classList.add("soon");
    node.querySelector(".source-name").textContent = deal.source_name;
    const link = node.querySelector(".deal-link"); link.href = deal.url; link.setAttribute("aria-label", `查看「${escapeText(deal.title)}」活動詳情`);
    const save = node.querySelector(".save-deal");
    const isSaved = state.saved.has(deal.id); save.textContent = isSaved ? "♥" : "♡"; save.setAttribute("aria-pressed", String(isSaved));
    save.addEventListener("click", () => toggleSaved(deal.id));
    els.grid.appendChild(node);
  });
  els.empty.hidden = deals.length !== 0;
  els.grid.hidden = deals.length === 0;
  els.count.textContent = `找到 ${deals.length} 筆`;
  els.title.textContent = state.savedOnly ? "我的收藏" : state.category === "全部" ? "全部好康" : `${state.category}好康`;
  els.savedCount.textContent = state.saved.size;
  els.savedButton.setAttribute("aria-pressed", String(state.savedOnly));
}

function renderSummary(data) {
  const available = data.deals.filter(d => !isExcludedDeal(d) && (!d.end_date || daysUntil(d.end_date) >= 0));
  document.querySelector("#dealTotal").textContent = available.length;
  document.querySelector("#freeTotal").textContent = available.filter(d => d.category === "免費").length;
  document.querySelector("#urgentTotal").textContent = available.filter(d => { const days = daysUntil(d.end_date); return days !== null && days >= 0 && days <= 3; }).length;
  const updated = new Date(data.updated_at);
  document.querySelector("#updatedAt").textContent = Number.isNaN(updated.valueOf()) ? "更新時間未提供" : `更新於 ${new Intl.DateTimeFormat("zh-TW", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }).format(updated)}`;
  document.querySelector("#demoNotice").hidden = !data.is_demo;
}

function renderSources(sources = []) {
  els.sourceList.replaceChildren();
  sources.forEach(source => {
    const item = document.createElement("div"); item.className = `source-item ${source.status === "ok" ? "" : "error"}`;
    const dot = document.createElement("span"); dot.className = "source-status";
    const copy = document.createElement("span");
    const name = document.createElement("strong"); name.textContent = source.name;
    const status = document.createElement("small"); status.textContent = source.status === "ok" ? `${source.count || 0} 筆 · 正常` : "本次更新失敗，保留舊資料";
    copy.append(name, status); item.append(dot, copy); els.sourceList.append(item);
  });
}

async function loadDeals() {
  try {
    const response = await fetch(`data/deals.json?v=${Date.now()}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json(); state.deals = data.deals || [];
    renderSummary(data); renderSources(data.sources); render();
  } catch (error) {
    document.querySelector("#updatedAt").textContent = "資料暫時讀取失敗";
    els.count.textContent = "無法載入";
    els.sourceList.innerHTML = "<p>請稍後重新整理頁面。</p>";
    console.error(error);
  }
}

els.filters.addEventListener("click", event => {
  const button = event.target.closest("[data-category]"); if (!button) return;
  state.category = button.dataset.category; state.savedOnly = false;
  els.filters.querySelectorAll(".filter").forEach(item => item.classList.toggle("active", item === button)); render();
});
els.search.addEventListener("input", event => { state.query = event.target.value.trim(); render(); });
els.official.addEventListener("change", event => { state.officialOnly = event.target.checked; render(); });
els.sort.addEventListener("change", event => { state.sort = event.target.value; render(); });
els.savedButton.addEventListener("click", () => { state.savedOnly = !state.savedOnly; render(); });
document.querySelector("#clearFilters").addEventListener("click", () => {
  state.category = "全部"; state.query = ""; state.officialOnly = false; state.savedOnly = false; els.search.value = ""; els.official.checked = false;
  els.filters.querySelectorAll(".filter").forEach(item => item.classList.toggle("active", item.dataset.category === "全部")); render();
});
document.addEventListener("keydown", event => { if (event.key === "/" && document.activeElement !== els.search) { event.preventDefault(); els.search.focus(); } });

loadDeals();
