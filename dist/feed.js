/* Small deterministic ranking helpers. No network, account or tracking. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.DealFeed = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const categories = ['3C', '遊戲娛樂', '餐飲食品', '家電日用', '男性運動', '金融支付', '免費', '任務'];
  const primary = d => (d.tags || [d.category]).find(t => !['免費', '任務'].includes(t)) || d.category || '其他';
  function fingerprint(d) {
    // Reading/checking timestamps and popularity never turn an unchanged item into news.
    return JSON.stringify([d.title, d.status, d.discount_label, d.discount, d.end_date, d.coupon_code, d.eligibility, d.steps, d.limits, d.hurdles, d.reasons]);
  }
  function matches(d, words) {
    const text = [d.title, d.benefit, d.discount_label].join(' ').toLocaleLowerCase();
    return (words || []).some(w => text.includes(w.toLocaleLowerCase()) || (w === "免費遊戲" && (d.tags || []).includes("遊戲娛樂") && d.discount?.kind === "free"));
  }
  function novelty(d, seen) {
    return !Object.prototype.hasOwnProperty.call(seen, d.id) ? 'unread' : seen[d.id] === fingerprint(d) ? 'seen' : 'changed';
  }
  function normalizeWords(input) {
    return [...new Set(String(input).split(/[\n,，、;；]+/).map(w => w.trim().slice(0, 40)).filter(Boolean))].slice(0, 20);
  }
  function score(d, options) {
    const { prefs, seen, saved, now } = options;
    const age = (now - Date.parse(d.published_at || d.first_seen_at)) / 86400000;
    return Number(d.score || 0) + (prefs.priority.includes(primary(d)) ? 12 : 0)
      + (matches(d, prefs.watch) ? 24 : 0) + (novelty(d, seen) !== 'seen' ? 9 : 0)
      + (saved.has(d.id) ? 2 : 0) + (Number.isFinite(age) ? Math.max(0, 5 - age) : 0);
  }
  function digest(items, limit = 5) {
    // Round-robin by content category, retaining ranking within each category.
    const groups = new Map();
    for (const d of items) {
      const key = primary(d);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(d);
    }
    const selected = [];
    while (selected.length < limit && [...groups.values()].some(g => g.length)) {
      for (const group of groups.values()) {
        if (group.length && selected.length < limit) selected.push(group.shift());
      }
    }
    return selected;
  }
  return { categories, primary, fingerprint, novelty, matches, normalizeWords, score, digest };
});
