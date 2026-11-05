/* Small deterministic ranking helpers. No network, account or tracking. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.DealFeed = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const categories = ['3C', '遊戲娛樂', '餐飲食品', '家電日用', '男性運動', '金融支付', '免費', '任務'];
  const primary = d => (d.tags || [d.category]).find(t => !['免費', '任務', '其他'].includes(t)) || (d.tags || []).find(t => ['免費', '任務'].includes(t)) || d.category || '其他';
  const topicWords = {
    '3C': /3c|電腦|筆電|螢幕|耳機|音響|相機|ssd|記憶體|顯示卡|充電器|行動電源|路由器|鍵盤|滑鼠|電競|平板|手機|iphone|android|galaxy|oled|投影機/i,
    '遊戲娛樂': /遊戲|電玩|steam|epic|playstation|ps5|xbox|switch|電影|影城|展覽|票券|貼圖|電子書|漫畫|netflix|myvideo|myviedo/i,
    '餐飲食品': /咖啡|餐飲|餐點|漢堡|飯糰|飲料|炸雞|披薩|甜點|麥當勞|肯德基|全家|7-eleven|7-11|萊爾富|超商|全聯|食品|零食|餅乾|可可|巧克力|便當|茶飲|餐券|壽司|雞胸|冰淇淋|哈根達斯|甜甜圈|布丁|奶茶|綠茶|焙茶|foodpanda|ubereats/i,
    '家電日用': /家電|冰箱|洗衣機|電視|冷氣|除濕機|吸塵器|電鍋|清潔|日用|衛生紙|家具|寢具|收納|牙膏|牙刷|洗衣精|洗碗精|電子鍋|吹風機|濕紙巾|濕巾/i,
    '男性運動': /男裝|男鞋|男性|男士|刮鬍|球鞋|運動|健身|戶外|露營|跑鞋/i,
    '金融支付': /信用卡|支付|回饋金|刷卡|銀行|line pay|悠遊付|街口|icash|openpoint/i,
    '任務': /任務|簽到|問卷|加入好友|加好友|綁定/i
  };
  function topics(d) {
    const known = [];
    // A descriptive headline takes precedence over noisy legacy body tags.
    for (const [category, pattern] of Object.entries(topicWords)) if (pattern.test(d.title || '')) known.push(category);
    known.push(...(d.tags || [d.category]).filter(t => categories.includes(t)));
    if (d.discount?.kind === 'free') known.push('免費');
    return [...new Set(known)].length ? [...new Set(known)] : ['其他'];
  }
  const pendingStages = [
    { key: 'clear', label: '有明確折扣', description: '已讀內文且折扣達標，仍有操作、資格或其他細節待補。' },
    { key: 'discount', label: '折扣待確認', description: '已有內文，但缺少折扣依據、回饋上限或適用品項等資訊。' },
    { key: 'summary', label: '只有標題／摘要', description: '尚未取得活動內文，先當線索看。' },
    { key: 'stale', label: '需要重新查核', description: '沿用舊資料或超過 72 小時沒有重新讀取。' }
  ];
  function pendingStage(d) {
    if (d.retained || (d.reasons || []).some(r => /72 小時|沿用舊內文|本輪未重新/.test(r))) return 'stale';
    if (!d.body_read) return 'summary';
    if (d.discount?.strong && !d.discount.range_claim && !d.discount.unknown_cap) return 'clear';
    return 'discount';
  }
  function pendingRank(d) { return pendingStages.findIndex(s => s.key === pendingStage(d)); }
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
  return { categories, topics, pendingStages, pendingStage, pendingRank, primary, fingerprint, novelty, matches, normalizeWords, score, digest };
});

