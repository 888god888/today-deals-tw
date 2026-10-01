#!/usr/bin/env python3
"""Bounded public-source collection; conservative evidence-based deal triage."""
from __future__ import annotations
import argparse
import hashlib
import ipaddress
import json
import os
import re
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
from quality import canonical_url, triage, discount

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "dist/data/deals.json"
CONFIG_FILE = ROOT / "config/sources.json"
TZ = ZoneInfo("Asia/Taipei")
UA = "TaiwanDailyDeals/6.0 (public activity index; GitHub Actions)"
KEYWORDS = ("免費", "優惠", "折", "回饋", "贈", "送", "特價", "好康", "點數", "券", "下殺", "史低", "破盤")
CATEGORIES = {
    "3C": ("3c", "手機", "電腦", "筆電", "螢幕", "耳機", "音響", "相機", "ssd", "記憶體", "顯示卡", "充電器", "行動電源", "路由器", "鍵盤", "滑鼠", "電競", "平板"),
    "遊戲娛樂": ("遊戲", "電玩", "steam", "epic", "playstation", "ps5", "xbox", "switch", "電影", "影城", "展覽", "演唱會", "票券"),
    "餐飲食品": ("咖啡", "餐飲", "餐點", "漢堡", "飯糰", "飲料", "炸雞", "披薩", "甜點", "麥當勞", "肯德基", "全家", "7-eleven", "7-11", "萊爾富", "超商", "食品", "零食", "早餐", "便當", "茶飲", "ubereats", "uber eats", "foodpanda"),
    "家電日用": ("家電", "冰箱", "洗衣機", "電視", "冷氣", "除濕機", "吸塵器", "電鍋", "清潔", "日用", "衛生紙", "家具", "寢具", "收納"),
    "男性運動": ("男裝", "男鞋", "男性", "男士", "刮鬍", "球鞋", "運動", "健身", "戶外", "露營", "跑鞋"),
    "金融支付": ("信用卡", "支付", "回饋金", "刷卡", "銀行", "line pay", "悠遊付", "街口", "icash", "openpoint"),
    "免費": ("免費", "0元", "零元"),
    "任務": ("任務", "簽到", "問卷", "加入好友", "綁定"),
    "交通": ("騎乘", "車資", "goshare", "irent", "台鐵", "高鐵", "機車", "汽車"),
}


def clean(text, limit=180):
    return re.sub(r"\s+", " ", text or "").strip()[:limit]


def load_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def safe_url(url):
    parts = urlparse(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.port not in (None, 443):
        raise ValueError("不支援的活動網址")
    try:
        addresses = socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("網域無法解析") from exc
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError("拒絕非公開網路網址")


class AccessBlocked(Exception):
    pass


class Reader:
    """Per-source budget; no retries around login, CAPTCHA or rate limits."""
    def __init__(self, max_requests=32, seconds=90):
        self.remaining = max_requests
        self.until = time.monotonic() + seconds
        self.blocked_hosts = set()
        self.detail_errors = 0

    def get(self, url, headers=None, params=None):
        for _ in range(4):
            host = urlparse(url).hostname
            if host in self.blocked_hosts:
                raise AccessBlocked("來源限制自動讀取；本輪停止存取該網域")
            if self.remaining <= 0 or time.monotonic() >= self.until:
                raise TimeoutError("達到本輪讀取上限")
            safe_url(url)
            self.remaining -= 1
            response = requests.get(url, headers=headers or {"User-Agent": UA}, params=params, timeout=(4, 8), allow_redirects=False)
            if response.status_code in (401, 403, 429):
                self.blocked_hosts.add(host)
                raise AccessBlocked(f"HTTP {response.status_code}；未繞過存取限制")
            if response.is_redirect:
                url = urljoin(url, response.headers.get("Location", ""))
                headers, params = None, None
                continue
            if not response.ok:
                raise ValueError(f"HTTP {response.status_code}")
            if len(response.content) > 3_000_000:
                raise ValueError("頁面超過讀取大小上限")
            response.encoding = response.apparent_encoding or "utf-8"
            return response
        raise ValueError("重新導向次數過多")

    def body(self, url, selector=""):
        try:
            response = self.get(url)
            if "html" not in response.headers.get("Content-Type", "").lower():
                return "", "非 HTML 活動頁"
            soup = BeautifulSoup(response.text, "html.parser")
            if soup.select_one('input[type="password"]') or re.search(r"just a moment|verify you are human|captcha", soup.title.get_text() if soup.title else "", re.I):
                return "", "登入或驗證頁，未繞過限制"
            node = soup.select_one(selector) if selector else soup.select_one("article, main, #main-content, #content, .article-content")
            if not node:
                return "", "無法辨識活動內文（可能為動態頁）"
            for el in node.select("script, style, nav, header, footer, .push, .article-metaline, .article-metaline-right, .f2"):
                el.decompose()
            body = node.get_text("\n", strip=True)
            if selector == "#main-content":
                body = re.split(r"\n--\s*(?:\n|$)", body)[0]
            if len(body) < 20:
                return "", "內文過短，尚未確認條款"
            return body[:12000], ""
        except Exception as exc:
            self.detail_errors += 1
            return "", error_message(exc)


def error_message(exc):
    if isinstance(exc, (AccessBlocked, TimeoutError, ValueError)):
        return clean(str(exc), 120)
    if isinstance(exc, requests.Timeout):
        return "來源讀取逾時"
    return f"來源讀取失敗（{type(exc).__name__}）"


@dataclass
class SourceResult:
    key: str
    name: str
    deals: list = field(default_factory=list)
    status: str = "ok"
    message: str = ""


def tags_for(text):
    text = text.lower()
    matched = {name for name, words in CATEGORIES.items() if name != "免費" and any(word in text for word in words)}
    signal = discount(text)
    if signal and signal["kind"] == "free":
        matched.add("免費")
    return [name for name in CATEGORIES if name in matched] or ["其他"]


def details(title, body):
    lines = [clean(line, 200) for line in re.split(r"[\n。；]", body) if len(line.strip()) >= 5]
    def pick(pattern, fallback):
        return next((line for line in lines if re.search(pattern, line)), fallback)
    code = re.search(r"(?:優惠碼|折扣碼|序號)\s*[:：為是]?\s*([A-Za-z0-9][A-Za-z0-9_-]{2,20})", body)
    return dict(summary=clean(body, 140) or title,
                benefit=pick(r"免費|折|回饋|特價|買一送一", title),
                eligibility=pick(r"限定|會員|新戶|首購|指定|分眾|消費滿|滿\d", "內文未列明額外資格；不代表所有人都適用"),
                steps=pick(r"購買|結帳|下單|兌換|領取|下載|輸入|問卷|加入好友|簽到", "內文未確認操作方式"),
                limits=pick(r"上限|每人|每戶|限量|名額|門市|售完|不可", "庫存、名額與完整限制未確認"),
                coupon_code=code.group(1) if code else "")


def record(key, cfg, title, url, body, now, *, read=False, published=None, note=""):
    title = clean(re.sub(r"^\[[^]]+\]\s*", "", title), 180)
    url = canonical_url(url)
    timestamp = now.isoformat(timespec="seconds")
    tags = tags_for(title + " " + body)
    if cfg.get("default_tags"):
        matched = set(tags) | set(cfg["default_tags"])
        tags = [tag for tag in CATEGORIES if tag in matched] or ["其他"]
    return dict(id=hashlib.sha256(url.encode()).hexdigest()[:16], source_key=key, source_name=cfg["name"], source_type=cfg.get("source_type", "discovery"),
                title=title, url=url, brand=cfg.get("brand", cfg["name"]), **details(title, body), evidence=body[:12000], evidence_excerpt=clean(body, 300), body_read=read,
                body_note=note, published_at=published, first_seen_at=timestamp, checked_at=timestamp if read else None, tags=tags, category=tags[0])


def collect_ptt(key, cfg, now):
    reader = Reader(int(cfg.get("article_limit", 32))+int(cfg.get("pages", 4)), 100)
    result = SourceResult(key, cfg["name"])
    url, entries, seen = cfg["url"], [], set()
    try:
        for _ in range(int(cfg.get("pages", 4))):
            soup = BeautifulSoup(reader.get(url).text, "html.parser")
            rows = soup.select(".r-ent")
            if not rows:
                raise ValueError("未辨識到文章列表；來源可能改版")
            for row in reversed(rows):
                a = row.select_one(".title a[href]")
                if not a:
                    continue
                title, article_url = a.get_text(" ", strip=True), urljoin(url, a["href"])
                if article_url in seen or re.match(r"Re:|R:|\[(公告|問題|討論)\]", title) or not any(word.lower() in title.lower() for word in KEYWORDS):
                    continue
                seen.add(article_url)
                stamp = re.search(r"/M\.(\d+)\.", article_url)
                published = datetime.fromtimestamp(int(stamp.group(1)), TZ) if stamp else None
                if published and now - published > timedelta(days=7):
                    continue
                entries.append((title, article_url, published.isoformat() if published else None))
            prev = next((a.get("href") for a in soup.select("a.btn.wide") if "上頁" in a.get_text()), None)
            if not prev:
                break
            url = urljoin(url, prev)
        for title, url, published in entries[:int(cfg.get("article_limit", 32))]:
            body, note = reader.body(url, "#main-content")
            result.deals.append(record(key, {**cfg, "source_type": "community"}, title, url, body, now, read=bool(body), published=published, note=note))
        if reader.detail_errors:
            result.status, result.message = "partial", f"{reader.detail_errors} 篇內文讀取失敗，未讀項目列待核對"
        elif not entries:
            result.message = "列表可讀；近期沒有候選文章"
    except Exception as exc:
        result.status, result.message = ("partial" if result.deals else "error"), error_message(exc)
    return result


def collect_html(key, cfg, now):
    reader = Reader(int(cfg.get("item_limit", 8))+2, 65)
    result = SourceResult(key, cfg["name"])
    try:
        soup = BeautifulSoup(reader.get(cfg["url"]).text, "html.parser")
        candidates, seen = [], set()
        for a in soup.select(cfg.get("link_selector", "a[href]")):
            title = clean(a.get_text(" ", strip=True) or a.get("title") or a.get("aria-label"))
            url = urljoin(cfg["url"], a.get("href", ""))
            if len(title) < 7 or not url.startswith("https://") or url in seen or not any(word in title for word in KEYWORDS):
                continue
            if title in {"最新優惠", "優惠活動", "優惠券專區", "好康資訊", "活動專區"}:
                continue
            candidates.append((title, url)); seen.add(url)
        if not candidates:
            result.status, result.message = "unparsed", "頁面可連線，但未辨識到活動內頁（可能為動態頁／需更新解析器）"
        for title, url in candidates[:int(cfg.get("item_limit", 8))]:
            body, note = reader.body(url, cfg.get("body_selector", ""))
            result.deals.append(record(key, {**cfg, "source_type": "official"}, title, url, body, now, read=bool(body), note=note))
        if reader.detail_errors:
            result.status, result.message = "partial", f"{reader.detail_errors} 個內頁讀取失敗；未核對項目不列首頁"
    except Exception as exc:
        result.status, result.message = ("partial" if result.deals else "error"), error_message(exc)
    return result


def collect_feed(key, cfg, now):
    reader, result = Reader(20, 65), SourceResult(key, cfg["name"])
    urls = list(cfg.get("urls", [])) + ["https://news.google.com/rss/search?q=" + quote_plus(q.format(year=now.year, month=now.month)) + "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant" for q in cfg.get("queries", [])]
    successes, failures, seen = 0, [], set()
    for url in urls:
        try:
            root = ET.fromstring(reader.get(url).content)
            if root.tag.split("}")[-1] not in {"rss", "feed", "RDF"}:
                raise ValueError("回應不是 RSS/Atom")
            successes += 1
            for item in root.findall(".//item") + root.findall("{http://www.w3.org/2005/Atom}entry"):
                title = clean(item.findtext("title") or item.findtext("{http://www.w3.org/2005/Atom}title"))
                link = item.findtext("link")
                if not link:
                    node = item.find("{http://www.w3.org/2005/Atom}link")
                    link = node.get("href", "") if node is not None else ""
                if not link.startswith("https://") or link in seen or not any(w in title for w in KEYWORDS):
                    continue
                seen.add(link)
                date = item.findtext("pubDate") or item.findtext("{http://www.w3.org/2005/Atom}published")
                try:
                    published = (parsedate_to_datetime(date) if "GMT" in (date or "") or "," in (date or "") else datetime.fromisoformat(date)).astimezone(TZ).isoformat()
                except (TypeError, ValueError):
                    published = None
                desc = BeautifulSoup(item.findtext("description") or item.findtext("{http://www.w3.org/2005/Atom}summary") or "", "html.parser").get_text(" ", strip=True)
                body, note = ("", "新聞索引摘要，尚未讀到原始條款") if urlparse(link).hostname == "news.google.com" else reader.body(link)
                result.deals.append(record(key, cfg, title, link, body or desc, now, read=bool(body), published=published, note=note))
                if len(result.deals) >= int(cfg.get("item_limit", 40)):
                    break
        except Exception as exc:
            failures.append(error_message(exc))
        if len(result.deals) >= int(cfg.get("item_limit", 40)):
            break
    result.status = "partial" if successes and failures else "error" if not successes else "ok"
    result.message = f"{successes}/{len(urls)} 個訂閱／查詢可讀" + ("；" + failures[0] if failures else "")
    return result


def collect_search(key, cfg, now):
    token = os.environ.get("BRAVE_SEARCH_API_KEY", "")
    if not token:
        return SourceResult(key, cfg["name"], status="not_configured", message="未設定搜尋 API；本次沒有搜尋 Threads／全網。論壇與 RSS 仍可運作")
    result, reader = SourceResult(key, cfg["name"]), Reader(28, 100)
    seen, successes, failures = set(), 0, []
    for query in cfg.get("queries", []):
        try:
            response = reader.get("https://api.search.brave.com/res/v1/web/search", headers={"X-Subscription-Token": token, "Accept": "application/json"},
                                  params={"q": query.format(year=now.year, month=now.month), "country": "TW", "search_lang": "zh-hant", "freshness": cfg.get("freshness", "pw"), "count": min(20, int(cfg.get("results_per_query", 8)))})
            payload = response.json()
            if "web" not in payload:
                raise ValueError("搜尋回應缺少 web 結果")
            successes += 1
            for row in payload["web"].get("results", []):
                url, title = row.get("url", ""), clean(row.get("title"))
                if not url.startswith("https://") or url in seen or not any(w in title for w in KEYWORDS):
                    continue
                seen.add(url)
                body, note = reader.body(url)
                desc = BeautifulSoup(row.get("description", ""), "html.parser").get_text(" ", strip=True)
                result.deals.append(record(key, cfg, title, url, body or desc, now, read=bool(body), note=note))
                if len(result.deals) >= int(cfg.get("item_limit", 24)):
                    break
        except AccessBlocked as exc:
            failures.append(error_message(exc)); break
        except Exception as exc:
            failures.append(error_message(exc))
        if len(result.deals) >= int(cfg.get("item_limit", 24)):
            break
        time.sleep(1.1)
    result.status = "partial" if successes and failures else "error" if not successes else "ok"
    result.message = f"{successes}/{len(cfg.get('queries', []))} 組查詢完成；內文未讀者列待核對" + ("；" + failures[0] if failures else "")
    return result


def merge_results(results, old, prefs, now):
    old_records = [] if old.get("is_demo") or old.get("schema_version") != 6 else old.get("deals", []) + old.get("conditional", []) + old.get("pending", [])
    seen_history = dict(old.get("seen_history", {})) if old.get("schema_version") == 6 else {}
    for d in old_records:
        seen_history.setdefault(d["id"], {"first": d.get("first_seen_at"), "last": d.get("first_seen_at")})
    unique, health = {}, []
    for result in results:
        counts = {"easy": 0, "conditional": 0, "candidate": 0, "rejected": 0, "retained": 0}
        fresh_ids = {d["id"] for d in result.deals}
        processed_ids = set()
        carried = [dict(d, retained=True) for d in old_records if d.get("source_key") == result.key and d["id"] not in fresh_ids] if result.status in {"error", "partial", "unparsed"} else []
        for raw in result.deals + carried:
            raw = dict(raw)
            if raw["id"] in processed_ids:
                continue
            processed_ids.add(raw["id"])
            history = seen_history.get(raw["id"], {})
            raw["first_seen_at"] = history.get("first") or raw.get("first_seen_at") or now.isoformat()
            seen_history[raw["id"]] = {"first": raw["first_seen_at"], "last": now.isoformat(timespec="seconds")}
            text = raw["title"] + " " + raw.get("evidence", "")
            tags = raw.get("tags") or tags_for(text)
            unknown_category = tags == ["其他"]
            if any(t.lower() in text.lower() for t in prefs.get("exclude_terms", [])) or set(tags).intersection(prefs.get("excluded_categories", ["交通"])) or not unknown_category and not set(tags).intersection(prefs.get("interest_categories", CATEGORIES.keys())):
                counts["rejected"] += 1; continue
            raw["tags"] = tags
            raw["category"] = next((t for t in tags if t in prefs.get("interest_categories", CATEGORIES)), tags[0])
            deal, rejection = triage(raw, now)
            if rejection:
                counts["rejected"] += 1; continue
            if unknown_category:
                deal["status"] = "candidate"
                deal["reasons"] = list(dict.fromkeys(deal["reasons"] + ["品類尚未確認，暫不因陌生品牌直接排除"]))
            if deal.get("retained"):
                deal["status"] = "candidate"
                deal["reasons"] = list(dict.fromkeys(deal["reasons"] + ["本輪未重新取得此情報，沿用舊內文，需重查"]))
                counts["retained"] += 1
            counts[deal["status"]] += 1
            previous = unique.get(deal["id"])
            rank = {"easy": 3, "conditional": 2, "candidate": 1}
            if not previous or (rank[deal["status"]], deal["score"]) > (rank[previous["status"]], previous["score"]):
                unique[deal["id"]] = deal
        health.append(dict(key=result.key, name=result.name, status=result.status, message=result.message, harvested=len(result.deals), **counts, attempted_at=now.isoformat(timespec="seconds")))
    groups = {"easy": [], "conditional": [], "candidate": []}
    for d in unique.values():
        groups[d["status"]].append(d)
    for items in groups.values():
        items.sort(key=lambda d: (d["score"], d.get("published_at") or d["first_seen_at"]), reverse=True)
    success = any(r.status in {"ok", "partial"} for r in results)
    seen_history = {key: value for key, value in seen_history.items() if value.get("last", "") >= (now-timedelta(days=365)).isoformat()}
    previous_success = old.get("updated_at") if old.get("schema_version") == 6 and not old.get("is_demo") else None
    return dict(schema_version=6, is_demo=False, attempted_at=now.isoformat(timespec="seconds"), updated_at=now.isoformat(timespec="seconds") if success else previous_success,
                run_status="partial" if success and any(r.status != "ok" for r in results) else "ok" if success else "error",
                sources=health, seen_history=seen_history, deals=groups["easy"][:80], conditional=groups["conditional"][:80], pending=groups["candidate"][:100])


def update(config, old, now, source_filter=None):
    jobs = []
    for key, cfg in config.items():
        if not isinstance(cfg, dict) or not cfg.get("enabled") or not cfg.get("url") and key not in {"news_radar", "web_discovery"}:
            continue
        fn = collect_ptt if key.startswith("ptt") else collect_feed if key == "news_radar" else collect_search if key == "web_discovery" else collect_html
        jobs.append((fn, key, cfg))
    for cfg in config.get("feeds", []):
        if cfg.get("enabled"):
            jobs.append((collect_feed, cfg["key"], cfg))
    if source_filter:
        jobs = [job for job in jobs if job[1] in source_filter]
    def run_job(job):
        try:
            return job[0](job[1], job[2], now)
        except Exception as exc:
            return SourceResult(job[1], job[2].get("name", job[1]), status="error", message=error_message(exc))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run_job, jobs))
    return merge_results(results, old, config.get("preferences", {}), now)


def validate(data):
    errors, seen = [], set()
    if data.get("schema_version") != 6:
        errors.append("資料需使用 schema_version 6")
    for group, status in (("deals", "easy"), ("conditional", "conditional"), ("pending", "candidate")):
        if not isinstance(data.get(group), list):
            errors.append(f"{group} 必須是陣列"); continue
        for deal in data[group]:
            if deal.get("status") != status:
                errors.append(f"分類狀態不一致：{deal.get('id')}")
            for field in ("id", "title", "url", "source_key", "source_name", "category", "tags", "first_seen_at"):
                if not deal.get(field):
                    errors.append(f"缺少 {field}")
            if not str(deal.get("url", "")).startswith("https://") or deal.get("id") in seen:
                errors.append("網址不安全或重複 ID")
            seen.add(deal.get("id"))
            if status == "easy" and (not deal.get("body_read") or deal.get("hurdles") or deal.get("reasons") or not (deal.get("discount") or {}).get("strong")):
                errors.append("首頁出現未確認或有門檻的項目")
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--sources", help="只跑指定來源（逗號分隔）；限測試")
    parser.add_argument("--output", type=Path, default=DATA_FILE)
    args = parser.parse_args()
    old = load_json(DATA_FILE, {})
    data = old if args.validate_only else update(load_json(CONFIG_FILE, {}), old, datetime.now(TZ), set(args.sources.split(",")) if args.sources else None)
    errors = validate(data)
    if errors:
        print("\n".join(errors), file=sys.stderr); return 1
    if not args.validate_only:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{data.get('run_status')}: 首頁 {len(data['deals'])}、有門檻 {len(data['conditional'])}、待核對 {len(data['pending'])}")
    for s in data.get("sources", []):
        print(f"{s['key']}: {s['status']} · 抓到 {s['harvested']} · 首頁 {s['easy']} · 待核對 {s['candidate']} · {s['message']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
