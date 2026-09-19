#!/usr/bin/env python3
"""Collect public Taiwan deal listings into the static site's deals.json."""

from __future__ import annotations

import argparse
import html as html_lib
import hashlib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urljoin, urlparse
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "dist" / "data" / "deals.json"
CONFIG_FILE = ROOT / "config" / "sources.json"
TZ = ZoneInfo("Asia/Taipei")
NOW = datetime.now(TZ)
USER_AGENT = "TaiwanDailyDeals/1.0 (+GitHub Actions; public deal indexer)"
KEYWORDS = ("免費", "優惠", "折", "回饋", "贈", "送", "特價", "好康", "折扣", "買一送一", "點數", "券", "免運", "限時")
DEFAULT_EXCLUDED_TERMS = (
    "衛生棉", "護墊", "生理褲", "月經", "私密處", "私密保養", "口紅", "唇膏", "粉底", "睫毛膏",
    "眼影", "腮紅", "彩妝", "美妝", "卸妝", "化妝", "女裝", "洋裝", "胸罩", "女性內衣", "高跟鞋",
    "女鞋", "美甲", "指甲油", "假睫毛", "女香", "女性香水", "女用", "星巴克",
)
DEFAULT_SHOPPING_INTEREST_TERMS = (
    "3c", "手機", "iphone", "android", "apple", "平板", "電腦", "筆電", "螢幕", "耳機", "音響", "相機",
    "家電", "遊戲", "電玩", "票券", "食品", "飲料", "零食", "日用", "衛生紙", "清潔", "男裝", "男鞋", "運動", "戶外",
)
DEFAULT_INTEREST_CATEGORIES = ("3C", "遊戲娛樂", "免費", "任務", "餐飲食品", "家電日用", "男性運動", "金融支付")
PRIMARY_CATEGORY_ORDER = ("3C", "遊戲娛樂", "餐飲食品", "家電日用", "男性運動", "金融支付", "免費", "任務", "交通", "其他")
CATEGORY_KEYWORDS = {
    "3C": (
        "3c", "iphone", "android", "apple", "平板", "電腦", "筆電", "螢幕", "耳機", "音響", "喇叭", "相機",
        "ssd", "記憶體", "顯示卡", "gpu", "cpu", "充電", "行動電源", "路由器", "oled", "鍵盤", "滑鼠",
        "razer", "雷蛇", "logitech", "羅技", "rog", "微星", "msi", "benq", "hyperx", "steelseries",
    ),
    "遊戲娛樂": ("遊戲", "電玩", "steam", "playstation", "ps5", "xbox", "switch", "電影", "影城", "展覽", "演唱會", "ktv", "票券"),
    "餐飲食品": (
        "咖啡", "餐飲", "餐點", "漢堡", "飯糰", "飲料", "炸雞", "披薩", "甜點", "麥當勞", "肯德基", "全家", "7-eleven",
        "7-11", "萊爾富", "okmart", "超商", "食品", "零食", "牛排", "早餐", "便當", "茶飲",
    ),
    "家電日用": (
        "家電", "冰箱", "洗衣機", "電視", "冷氣", "除濕機", "吸塵器", "掃地機", "電鍋", "氣炸鍋", "清潔", "日用",
        "衛生紙", "家具", "寢具", "廚房", "收納",
    ),
    "男性運動": ("男裝", "男鞋", "男性", "男士", "刮鬍", "球鞋", "運動", "健身", "戶外", "露營", "跑鞋", "球衣"),
    "金融支付": ("信用卡", "支付", "回饋金", "刷卡", "銀行", "line pay", "悠遊付", "街口", "pi錢包", "icash", "openpoint"),
    "免費": ("免費", "0元", "零元", "免費領", "贈送", "贈品", "好禮", "line point", "p幣", "蝦幣", "購物金"),
    "任務": ("任務", "簽到", "下載", "問卷", "登錄", "登入", "加入好友", "綁定"),
    "交通": ("騎乘", "車資", "goshare", "irent", "uber", "台鐵", "高鐵", "交通", "機車", "汽車"),
}


@dataclass
class SourceResult:
    key: str
    name: str
    deals: list[dict[str, Any]]
    ok: bool
    message: str = ""


def fetch(url: str, *, timeout: int = 20) -> str:
    response = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-TW,zh;q=0.9"}, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def clean(value: str | None, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    return text[:limit].rstrip("，,。；; ")


def useful_sentences(text: str) -> list[str]:
    """Turn noisy activity-page copy into short, useful, de-duplicated sentences."""
    text = re.sub(r"https?://\S+", " ", text or "")
    pieces = re.split(r"[\r\n。！？!?；;，,]+", text)
    result: list[str] = []
    for piece in pieces:
        sentence = clean(re.sub(r"^[\s•●▪◆◇★☆※*\-–—]+", "", piece), 150)
        if not 5 <= len(sentence) <= 150:
            continue
        if sentence in result or sentence.startswith(("來源", "發信站", "作者", "標題", "時間")):
            continue
        result.append(sentence)
    return result[:40]


def pick_sentence(sentences: list[str], cues: tuple[str, ...], used: set[str], max_items: int = 1) -> str:
    ranked = sorted(
        (sentence for sentence in sentences if any(cue.lower() in sentence.lower() for cue in cues)),
        key=lambda sentence: (sum(cue.lower() in sentence.lower() for cue in cues), -len(sentence)),
        reverse=True,
    )
    if not ranked:
        return ""
    selected = [sentence for sentence in ranked if sentence not in used][:max_items] or ranked[:1]
    used.update(selected)
    return "；".join(selected)


def infer_details(title: str, body: str, fallback_summary: str = "") -> dict[str, str]:
    sentences = useful_sentences(body)
    used: set[str] = set()
    benefit_cues = ("免費", "贈", "送", "買一送一", "折", "回饋", "特價", "點", "優惠", "免運", "騎乘金")
    eligibility_cues = ("限定", "會員", "新戶", "舊戶", "指定", "資格", "適用", "綁定", "滿額", "消費滿", "收到", "分眾")
    step_cues = ("領取", "兌換", "輸入", "下載", "開啟", "使用", "登錄", "登入", "購買", "消費", "加入", "結帳")
    limit_cues = ("限量", "每人", "每戶", "每帳號", "額滿", "名額", "不可", "不適用", "門市", "售完", "庫存", "期限")

    benefit = pick_sentence(sentences, benefit_cues, used) or clean(title, 140)
    eligibility = pick_sentence(sentences, eligibility_cues, used)
    steps = pick_sentence(sentences, step_cues, used, 2)
    limits = pick_sentence(sentences, limit_cues, used, 2)
    summary = clean(fallback_summary, 170) or next(
        (sentence for sentence in sentences if sentence not in used and not re.match(r"^(優惠碼|折扣碼|序號|代碼)", sentence)),
        "",
    ) or benefit

    code_match = re.search(r"(?:優惠碼|折扣碼|序號|代碼)\s*[:：為是]?\s*([A-Za-z0-9][A-Za-z0-9_-]{2,19})", body, re.I)
    return {
        "summary": clean(summary, 180),
        "benefit": clean(benefit, 160),
        "eligibility": clean(eligibility or "一般使用者；若為會員、分眾或指定支付限定，以活動頁顯示為準", 160),
        "steps": clean(steps or "開啟活動頁確認可領取或購買後，依頁面指示完成", 160),
        "limits": clean(limits or "名額、庫存、活動期限與適用門市以主辦單位即時狀態為準", 160),
        "coupon_code": clean(code_match.group(1), 24) if code_match else "",
    }


def is_unwanted(text: str, excluded_terms: list[str] | tuple[str, ...]) -> bool:
    lowered = (text or "").lower()
    return any(term.lower() in lowered for term in excluded_terms if term)


def make_id(source_key: str, url: str, title: str) -> str:
    raw = f"{source_key}|{url}|{title}".encode("utf-8")
    return f"{source_key}-{hashlib.sha1(raw).hexdigest()[:12]}"


def parse_date(text: str) -> str | None:
    candidates = re.findall(r"(?:(20\d{2})\s*[年/.-])?\s*(\d{1,2})\s*[月/.-]\s*(\d{1,2})\s*日?", text)
    valid: list[datetime] = []
    for year_text, month_text, day_text in candidates:
        year = int(year_text) if year_text else NOW.year
        try:
            date = datetime(year, int(month_text), int(day_text), tzinfo=TZ)
            if not year_text and date < NOW - timedelta(days=45):
                date = date.replace(year=year + 1)
            if date >= NOW - timedelta(days=2):
                valid.append(date)
        except ValueError:
            continue
    return max(valid).date().isoformat() if valid else None


def classify_tags(text: str) -> list[str]:
    lowered = text.lower()
    matched = {category for category, keywords in CATEGORY_KEYWORDS.items() if any(keyword in lowered for keyword in keywords)}
    if "手機" in lowered and not any(phrase in lowered for phrase in ("手機點餐", "手機支付", "手機綁定", "手機驗證")):
        matched.add("3C")
    if re.search(r"(?<![a-z])app(?![a-z])", lowered):
        matched.add("任務")
    tags = [category for category in PRIMARY_CATEGORY_ORDER if category in matched]
    return tags or ["其他"]


def classify(text: str) -> str:
    return classify_tags(text)[0]


def analyze_discount(text: str) -> dict[str, Any] | None:
    """Return a concrete strong-discount signal; vague sale wording is not enough."""
    lowered = clean(text, 2400).lower().replace(",", "")
    if not lowered:
        return None
    if any(term in lowered for term in ("買一送一", "第二件0元", "第2件0元")):
        return {"label": "買一送一（約 5 折）", "score": 98, "kind": "bogo"}
    if any(term in lowered for term in ("免費領", "免費兌換", "0元領", "零元領", "免費下載")):
        return {"label": "可免費取得", "score": 96, "kind": "free"}

    price_pairs = re.findall(
        r"原價\s*(?:nt\$?|\$)?\s*(\d{2,7}).{0,30}?(?:特價|優惠價|下殺|只要|現價)\s*(?:nt\$?|\$)?\s*(\d{2,7})",
        lowered,
    )
    for original_text, current_text in price_pairs:
        original, current = int(original_text), int(current_text)
        if original > current > 0:
            saved_pct = round((original - current) / original * 100)
            if saved_pct >= 25:
                return {
                    "label": f"原價 NT${original:,}，現價 NT${current:,}，省 {saved_pct}%",
                    "score": min(100, 76 + saved_pct), "kind": "price_pair",
                }

    rates = [float(value) for value in re.findall(r"(?<!\d)(\d{1,2}(?:\.\d)?)\s*折", lowered)]
    rates = [rate / 10 if rate > 10 else rate for rate in rates]
    strong_rates = [rate for rate in rates if 0 < rate <= 7.5]
    if strong_rates:
        rate = min(strong_rates)
        return {"label": f"最低 {rate:g} 折", "score": min(99, round(104 - rate * 5)), "kind": "rate"}

    percentages = [int(value) for value in re.findall(r"(\d{1,3})\s*%", lowered)]
    strong_percentages = [value for value in percentages if value >= 15]
    if strong_percentages and any(term in lowered for term in ("回饋", "折扣", "現折", "省", "off")):
        value = max(strong_percentages)
        return {"label": f"最高 {value}% 優惠／回饋", "score": min(96, 74 + value), "kind": "percent"}

    money_patterns = (
        r"(?:現折|折抵|折價|省|回饋)\s*(?:nt\$?|\$)?\s*(\d{3,7})",
        r"(?:nt\$?|\$)?\s*(\d{3,7})\s*元?\s*(?:現折|折抵|折價|回饋)",
    )
    amounts = [int(value) for pattern in money_patterns for value in re.findall(pattern, lowered)]
    if any(amount >= 1000 for amount in amounts):
        amount = max(amounts)
        return {"label": f"可省／回饋 NT${amount:,}", "score": min(94, 76 + amount // 500), "kind": "amount"}

    if any(term in lowered for term in ("歷史最低", "史低", "腰斬", "跳水", "破盤")) and re.search(r"\d", lowered):
        return {"label": "情報來源標示歷史低價／破盤價", "score": 88, "kind": "low_claim"}
    return None


def is_meaningful_deal(text: str, threshold: str = "medium", *, shopping: bool = False) -> bool:
    """Keep tangible benefits and reject ordinary prices or token discounts."""
    if threshold == "loose":
        return any(word.lower() in text.lower() for word in KEYWORDS)
    if threshold == "strong":
        return analyze_discount(text) is not None

    lowered = clean(text, 1000).lower().replace(",", "")
    if not lowered:
        return False

    strong_free = any(term in lowered for term in ("免費", "0元", "零元", "買一送一", "第二件0元", "免運"))
    reward_task = any(term in lowered for term in ("簽到", "任務", "問卷", "登錄", "加入好友")) and any(
        term in lowered for term in ("領", "送", "贈", "point", "點", "p幣", "蝦幣", "購物金", "好禮")
    )
    gift_offer = any(term in lowered for term in ("贈送", "贈品", "滿額送", "登記送", "送好禮"))
    if strong_free or reward_task or gift_offer:
        return True

    discount_rates = [float(value) for value in re.findall(r"(?<!\d)(\d{1,2}(?:\.\d)?)\s*折", lowered)]
    discount_rates = [rate / 10 if rate > 10 else rate for rate in discount_rates]
    if any(rate <= 8.0 for rate in discount_rates):
        return True

    percentages = [int(value) for value in re.findall(r"(\d{1,3})\s*%", lowered)]
    if any(value >= 10 for value in percentages) and any(term in lowered for term in ("回饋", "折", "省", "現折")):
        return True

    money_patterns = (
        r"(?:現折|折抵|折價|折|回饋|省|購物金|折價券|優惠券)\s*(?:nt\$?|\$)?\s*(\d{2,6})",
        r"(?:nt\$?|\$)?\s*(\d{2,6})\s*元?\s*(?:現折|折抵|折價|回饋|購物金|券)",
    )
    amounts = [int(value) for pattern in money_patterns for value in re.findall(pattern, lowered)]
    if any(amount >= 50 for amount in amounts):
        return True

    if discount_rates:
        return False

    if shopping:
        return any(term in lowered for term in ("神券", "破盤", "下殺", "限時瘋搶")) and bool(re.search(r"\d", lowered))
    return any(term in lowered for term in ("優惠券專區", "限時組合價", "神券", "破盤價"))


def infer_brand(text: str, fallback: str) -> str:
    brands = ("7-ELEVEN", "全家", "萊爾富", "OKmart", "麥當勞", "肯德基", "星巴克", "蝦皮", "PChome", "momo", "LINE", "GoShare", "悠遊付", "街口", "Uber Eats", "foodpanda")
    normalized = text.lower()
    for brand in brands:
        if brand.lower() in normalized:
            return brand
    return fallback


def infer_claim(text: str, fallback: str) -> str:
    lines = [clean(line, 120) for line in re.split(r"[\r\n。]", text)]
    cues = ("方式", "辦法", "步驟", "領取", "兌換", "輸入", "加入", "下載", "綁定", "使用", "消費", "購買", "滿")
    for line in lines:
        if 8 <= len(line) <= 120 and any(cue in line for cue in cues) and not line.startswith(("※", "來源")):
            return line
    return fallback


def score_deal(title: str, body: str, source_type: str, published_at: str | None, end_date: str | None) -> int:
    text = f"{title} {body}"
    score = 68 if source_type == "official" else 58
    score += min(18, sum(4 for word in ("免費", "買一送一", "回饋", "贈", "折", "限量") if word in text))
    if published_at and published_at[:10] == NOW.date().isoformat():
        score += 12
    if end_date:
        try:
            left = (datetime.fromisoformat(end_date).date() - NOW.date()).days
            if 0 <= left <= 3:
                score += 8
        except ValueError:
            pass
    return min(score, 100)


def ptt_publish_date(raw: str) -> str:
    match = re.search(r"(\d{1,2})/(\d{1,2})", raw)
    if not match:
        return NOW.isoformat(timespec="seconds")
    month, day = map(int, match.groups())
    year = NOW.year
    try:
        date = datetime(year, month, day, 9, 0, tzinfo=TZ)
        if date > NOW + timedelta(days=2):
            date = date.replace(year=year - 1)
        return date.isoformat(timespec="seconds")
    except ValueError:
        return NOW.isoformat(timespec="seconds")


def page_text(url: str, selector: str = "") -> str:
    soup = BeautifulSoup(fetch(url), "html.parser")
    content = soup.select_one(selector) if selector else None
    content = content or soup.select_one("article, main, #main-content, #content, .content, .main") or soup.body
    if not content:
        return ""
    for node in content.select(".article-metaline, .article-metaline-right, .push, .f2, script, style, noscript, nav, header, footer"):
        node.decompose()
    raw = content.get_text("\n", strip=True)
    if selector == "#main-content":
        raw = raw.split("--")[0]
    useful = [line for line in raw.splitlines() if line and not line.startswith(("http://", "https://", "※ 發信站"))]
    return "\n".join(useful[:60])[:6000]


def article_text(url: str) -> str:
    return page_text(url, "#main-content")


def scrape_ptt(key: str, cfg: dict[str, Any], excluded_terms: list[str]) -> SourceResult:
    name, page_url = cfg["name"], cfg["url"]
    entries: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    try:
        for _ in range(int(cfg.get("pages", 2))):
            soup = BeautifulSoup(fetch(page_url), "html.parser")
            for row in soup.select(".r-ent"):
                link = row.select_one(".title a")
                if not link:
                    continue
                title = clean(link.get_text(" ", strip=True), 120)
                url = urljoin(page_url, link.get("href", ""))
                raw_date = clean(row.select_one(".date").get_text() if row.select_one(".date") else "")
                looks_like_deal = title.startswith(("[情報]", "[免費]", "[優惠]", "[好康]")) or any(word in title for word in KEYWORDS)
                is_noise = title.startswith(("Re:", "R:", "[公告]", "[問題]", "[討論]"))
                if url not in seen and looks_like_deal and not is_noise:
                    entries.append((title, url, raw_date)); seen.add(url)
            previous = next((a.get("href") for a in soup.select("a.btn.wide") if "上頁" in a.get_text()), None)
            if not previous:
                break
            page_url = urljoin(page_url, previous)

        deals: list[dict[str, Any]] = []
        for title, url, raw_date in entries[: int(cfg.get("article_limit", 20))]:
            body = ""
            try:
                body = article_text(url)
                time.sleep(0.12)
            except Exception:
                pass
            full_text = f"{title}\n{body}"
            if is_unwanted(full_text, excluded_terms):
                continue
            display_title = re.sub(r"^(Re:|R:)?\s*\[[^]]+\]\s*", "", title)
            details = infer_details(display_title, body, next((line for line in body.splitlines() if len(line) >= 12), display_title))
            published = ptt_publish_date(raw_date)
            end_date = parse_date(full_text)
            deals.append({
                "id": make_id(key, url, title), "source_key": key, "title": display_title,
                "brand": infer_brand(full_text, "網友分享"), **details, "claim": details["steps"], "category": classify(full_text), "tags": classify_tags(full_text),
                "source_type": "community", "source_name": name, "published_at": published, "end_date": end_date,
                "score": score_deal(title, body, "community", published, end_date), "url": url
            })
        if not deals:
            raise ValueError("頁面未找到可辨識的優惠文章")
        return SourceResult(key, name, deals, True)
    except Exception as exc:
        return SourceResult(key, name, [], False, clean(str(exc), 100))


def scrape_official_cards(key: str, cfg: dict[str, Any], brand: str, excluded_terms: list[str]) -> SourceResult:
    name, url = cfg["name"], cfg["url"]
    try:
        soup = BeautifulSoup(fetch(url), "html.parser")
        candidates: list[tuple[str, str, str]] = []
        seen_titles: set[str] = set()
        for heading in soup.select("h1, h2, h3, h4, h5, [class*=title]"):
            title = clean(heading.get_text(" ", strip=True), 120)
            if len(title) < 7 or title in seen_titles or not any(word.lower() in title.lower() for word in KEYWORDS):
                continue
            vague = any(phrase in title for phrase in ("最新優惠", "優惠活動", "活動專區", "熱門推薦", "好康資訊"))
            concrete = bool(re.search(r"\d|%|免費|回饋|買一送一|贈|折|特價", title))
            if vague and not concrete:
                continue
            parent = heading.find_parent(["article", "li", "section", "div"]) or heading.parent
            paragraph = parent.find("p") if parent else None
            summary = clean(paragraph.get_text(" ", strip=True) if paragraph else "", 160)
            anchor = heading.find("a", href=True) or (parent.find("a", href=True) if parent else None)
            item_url = urljoin(url, anchor["href"]) if anchor else url
            if not item_url.startswith("https://"):
                item_url = url
            candidates.append((title, summary, item_url)); seen_titles.add(title)
        deals: list[dict[str, Any]] = []
        for title, summary, item_url in candidates[: int(cfg.get("item_limit", 20))]:
            detail_text = ""
            if item_url != url:
                try:
                    detail_text = page_text(item_url)
                    time.sleep(0.1)
                except Exception:
                    pass
            full_text = f"{title}\n{summary}\n{detail_text}"
            if is_unwanted(full_text, excluded_terms):
                continue
            details = infer_details(title, detail_text or summary, summary)
            end_date = parse_date(full_text)
            published = NOW.isoformat(timespec="seconds")
            deals.append({
                "id": make_id(key, item_url, title), "source_key": key, "title": title, "brand": brand,
                **details, "claim": details["steps"], "category": classify(full_text), "tags": classify_tags(full_text),
                "source_type": "official", "source_name": name, "published_at": published, "end_date": end_date,
                "score": score_deal(title, full_text, "official", published, end_date), "url": item_url
            })
        if not deals:
            raise ValueError("頁面未找到可辨識的優惠項目")
        return SourceResult(key, name, deals, True)
    except Exception as exc:
        return SourceResult(key, name, [], False, clean(str(exc), 100))


def scrape_shopping_links(key: str, cfg: dict[str, Any], brand: str, excluded_terms: list[str], interest_terms: list[str]) -> SourceResult:
    """Extract concrete platform promotions while skipping generic navigation and product noise."""
    name, url = cfg["name"], cfg["url"]
    try:
        soup = BeautifulSoup(fetch(url), "html.parser")
        candidates: list[tuple[str, str, str]] = []
        seen_titles: set[str] = set()
        for anchor in soup.select("a[href]"):
            title = clean(anchor.get_text(" ", strip=True) or anchor.get("aria-label") or anchor.get("title"), 150)
            lowered = title.lower()
            if not 8 <= len(title) <= 150 or title in seen_titles:
                continue
            if title in {"查看更多", "看更多", "活動合集", "領取", "立即領取", "立即購買", "馬上搶", "回首頁"}:
                continue
            has_interest = any(term.lower() in lowered for term in interest_terms)
            has_offer = any(word.lower() in lowered for word in KEYWORDS) or bool(re.search(r"\d+(?:\.\d+)?\s*折|\$\s*[\d,]+|\d+\s*%", title))
            if not has_interest or not has_offer or is_unwanted(title, excluded_terms) or not is_meaningful_deal(title, shopping=True):
                continue
            item_url = urljoin(url, anchor.get("href", ""))
            if not item_url.startswith("https://"):
                continue
            parent = anchor.find_parent(["article", "li", "section", "div"])
            context = clean(parent.get_text(" ", strip=True) if parent else title, 260)
            if len(context) > 230 or is_unwanted(context, excluded_terms):
                context = title
            candidates.append((title, context, item_url))
            seen_titles.add(title)

        deals: list[dict[str, Any]] = []
        for title, context, item_url in candidates[: int(cfg.get("item_limit", 24))]:
            details = infer_details(title, context, context)
            end_date = parse_date(context)
            published = NOW.isoformat(timespec="seconds")
            deals.append({
                "id": make_id(key, item_url, title), "source_key": key, "title": title, "brand": brand,
                **details, "claim": details["steps"], "category": classify(f"{title} {context}"), "tags": classify_tags(f"{title} {context}"),
                "source_type": "official", "source_name": name,
                "published_at": published, "end_date": end_date,
                "score": score_deal(title, context, "official", published, end_date), "url": item_url,
            })
        if not deals:
            raise ValueError("頁面未找到符合偏好的購物優惠")
        return SourceResult(key, name, deals, True)
    except Exception as exc:
        return SourceResult(key, name, [], False, clean(str(exc), 100))


def scrape_news_radar(key: str, cfg: dict[str, Any], excluded_terms: list[str]) -> SourceResult:
    """Discover short-lived deals that fixed merchant homepages often miss."""
    name = cfg["name"]
    try:
        deals: list[dict[str, Any]] = []
        seen: set[str] = set()
        for query in cfg.get("queries", []):
            url = (
                "https://news.google.com/rss/search?q=" + quote_plus(query)
                + "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
            )
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
            response.raise_for_status()
            root = ElementTree.fromstring(response.content)
            for item in root.findall(".//item"):
                raw_title = clean(item.findtext("title"), 180)
                item_url = clean(item.findtext("link"), 500)
                source_node = item.find("source")
                publisher = clean(source_node.text if source_node is not None else "即時情報", 60)
                title = re.sub(rf"\s+-\s+{re.escape(publisher)}$", "", raw_title).strip()
                description = html_lib.unescape(item.findtext("description") or "")
                description = clean(BeautifulSoup(description, "html.parser").get_text(" ", strip=True), 360)
                full_text = f"{title} {description}"
                lowered = full_text.lower()
                if not title or not item_url.startswith("https://") or title in seen:
                    continue
                discount = analyze_discount(full_text)
                if is_unwanted(full_text, excluded_terms) or not discount:
                    continue
                # The site is for Taiwan shoppers; discard obvious overseas-only deal posts.
                overseas = any(term in lowered for term in ("amazon", "亞馬遜", "美元", "us$", "£", "英鎊"))
                taiwan = any(term in lowered for term in ("台灣", "全台", "pchome", "momo", "蝦皮", "yahoo", "新台幣", "nt$"))
                if overseas and not taiwan:
                    continue
                published_raw = item.findtext("pubDate") or ""
                try:
                    published = parsedate_to_datetime(published_raw).astimezone(TZ).isoformat(timespec="seconds")
                except (TypeError, ValueError):
                    published = NOW.isoformat(timespec="seconds")
                details = infer_details(title, description, description or title)
                end_date = parse_date(full_text)
                deals.append({
                    "id": make_id(key, item_url, title), "source_key": key, "title": title,
                    "brand": infer_brand(full_text, publisher), **details, "claim": details["steps"],
                    "category": classify(full_text), "tags": classify_tags(full_text),
                    "source_type": "discovery", "source_name": f"即時雷達 · {publisher}",
                    "published_at": published, "end_date": end_date,
                    "score": max(discount["score"], min(98, score_deal(title, description, "community", published, end_date) + 8)),
                    "deal_strength": "strong", "discount_label": discount["label"],
                    "url": item_url,
                })
                seen.add(title)
                if len(deals) >= int(cfg.get("item_limit", 36)):
                    break
            if len(deals) >= int(cfg.get("item_limit", 36)):
                break
            time.sleep(0.15)
        if not deals:
            raise ValueError("近期沒有找到符合門檻的即時優惠")
        return SourceResult(key, name, deals, True)
    except Exception as exc:
        return SourceResult(key, name, [], False, clean(str(exc), 100))


def scrape_web_discovery(key: str, cfg: dict[str, Any], excluded_terms: list[str]) -> SourceResult:
    """Search the public web and social indexes without assuming any brand in advance."""
    name = cfg["name"]
    try:
        queries = [
            str(query).format(year=NOW.year, month=NOW.month, date=NOW.date().isoformat())
            for query in cfg.get("queries", [])
        ]

        def search(query: str) -> list[dict[str, str]]:
            response = None
            for attempt in range(2):
                response = requests.get(
                    "https://search.brave.com/search",
                    params={"q": query, "source": "web", "tf": cfg.get("freshness", "pm")},
                    headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"},
                    timeout=25,
                )
                if response.status_code != 429:
                    break
                time.sleep(2 + attempt * 2)
            if response is None or response.status_code == 429:
                return []
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            rows: list[dict[str, str]] = []
            for result in soup.select("div.result-content"):
                anchor = result.select_one("a.l1[href]")
                title_node = result.select_one(".search-snippet-title")
                snippet_node = result.select_one(".generic-snippet .content")
                if not anchor or not title_node:
                    continue
                rows.append({
                    "url": clean(anchor.get("href"), 600),
                    "title": clean(title_node.get_text(" ", strip=True), 200),
                    "snippet": clean(snippet_node.get_text(" ", strip=True) if snippet_node else "", 500),
                })
                if len(rows) >= int(cfg.get("results_per_query", 12)):
                    break
            return rows

        result_groups: list[list[dict[str, str]]] = []
        for query in queries:
            try:
                result_groups.append(search(query))
            except Exception:
                result_groups.append([])
            time.sleep(2.5)

        deals: list[dict[str, Any]] = []
        seen: set[str] = set()
        for rows in result_groups:
            for row in rows:
                title, item_url, snippet = row["title"], row["url"], row["snippet"]
                domain = urlparse(item_url).netloc.lower().removeprefix("www.")
                full_text = f"{title} {snippet}"
                discount = analyze_discount(full_text)
                if not title or not item_url.startswith("https://") or item_url in seen:
                    continue
                if domain in {"search.brave.com", "brave.com"} or is_unwanted(full_text, excluded_terms) or not discount:
                    continue
                tags = classify_tags(full_text)
                if tags == ["其他"]:
                    continue
                details = infer_details(title, snippet, snippet or title)
                details["benefit"] = clean(f"{discount['label']}；{details['benefit']}", 160)
                end_date = parse_date(full_text)
                source_label = "Threads" if "threads.com" in domain else domain
                deals.append({
                    "id": make_id(key, item_url, title), "source_key": key, "title": title,
                    "brand": infer_brand(full_text, source_label), **details, "claim": details["steps"],
                    "category": classify(full_text), "tags": tags,
                    "source_type": "discovery", "source_name": f"全網雷達 · {source_label}",
                    "published_at": NOW.isoformat(timespec="seconds"), "end_date": end_date,
                    "score": discount["score"] + (2 if "threads.com" in domain else 0),
                    "deal_strength": "strong", "discount_label": discount["label"], "url": item_url,
                })
                seen.add(item_url)
                if len(deals) >= int(cfg.get("item_limit", 50)):
                    break
            if len(deals) >= int(cfg.get("item_limit", 50)):
                break
        if not deals:
            raise ValueError("近期搜尋結果沒有通過強折扣門檻的情報")
        return SourceResult(key, name, deals, True)
    except Exception as exc:
        return SourceResult(key, name, [], False, clean(str(exc), 100))


def load_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


def normalize(
    deal: dict[str, Any], excluded_terms: list[str], interest_categories: list[str], threshold: str,
    excluded_categories: list[str] | None = None,
) -> dict[str, Any] | None:
    required = ("id", "title", "url", "source_name", "source_type")
    if any(not deal.get(field) for field in required):
        return None
    searchable = " ".join(str(deal.get(field, "")) for field in ("title", "brand", "summary", "benefit", "eligibility", "steps", "limits"))
    if is_unwanted(searchable, excluded_terms):
        return None
    tags = classify_tags(searchable)
    existing_tags = deal.get("tags", []) if isinstance(deal.get("tags"), list) else []
    tags = [category for category in PRIMARY_CATEGORY_ORDER if category in set(tags + existing_tags)]
    blocked = set(excluded_categories or [])
    if blocked.intersection(tags) or not set(interest_categories).intersection(tags):
        return None
    if not is_meaningful_deal(searchable, threshold, shopping=deal.get("source_key") in {"yahoo", "shopee"}):
        return None
    discount = analyze_discount(searchable)
    if discount:
        deal["deal_strength"] = "strong"
        deal["discount_label"] = deal.get("discount_label") or discount["label"]
        deal["score"] = max(int(deal.get("score", 50)), int(discount["score"]))
    deal["tags"] = tags
    deal["category"] = next((category for category in PRIMARY_CATEGORY_ORDER if category in tags and category in interest_categories), tags[0])
    deal["summary"] = clean(deal.get("summary"), 180)
    deal["benefit"] = clean(deal.get("benefit") or deal.get("summary") or deal.get("title"), 160)
    deal["eligibility"] = clean(deal.get("eligibility") or "一般使用者；實際資格以活動頁為準", 160)
    deal["steps"] = clean(deal.get("steps") or deal.get("claim") or "開啟活動頁後依頁面指示參加", 160)
    deal["limits"] = clean(deal.get("limits") or "名額、庫存與適用門市以主辦單位即時公告為準", 160)
    deal["coupon_code"] = clean(deal.get("coupon_code"), 24)
    deal["claim"] = deal["steps"]
    deal["score"] = max(0, min(100, int(deal.get("score", 50))))
    return deal


def update() -> dict[str, Any]:
    global requests, BeautifulSoup
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise SystemExit("缺少抓取套件，請先執行 pip install -r requirements.txt") from exc
    config = load_json(CONFIG_FILE, {})
    excluded_terms = config.get("preferences", {}).get("exclude_terms", list(DEFAULT_EXCLUDED_TERMS))
    interest_terms = config.get("preferences", {}).get("shopping_interest_terms", list(DEFAULT_SHOPPING_INTEREST_TERMS))
    interest_categories = config.get("preferences", {}).get("interest_categories", list(DEFAULT_INTEREST_CATEGORIES))
    excluded_categories = config.get("preferences", {}).get("excluded_categories", ["交通"])
    threshold = config.get("preferences", {}).get("deal_threshold", "strong")
    old_data = load_json(DATA_FILE, {"deals": [], "sources": []})
    old_deals = old_data.get("deals", [])
    results: list[SourceResult] = []
    if config.get("ptt", {}).get("enabled"):
        results.append(scrape_ptt("ptt", config["ptt"], excluded_terms))
    if config.get("news_radar", {}).get("enabled"):
        results.append(scrape_news_radar("news_radar", config["news_radar"], excluded_terms))
    if config.get("web_discovery", {}).get("enabled"):
        results.append(scrape_web_discovery("web_discovery", config["web_discovery"], excluded_terms))
    official_sources = {
        "mcdonalds": "麥當勞", "kfc": "肯德基", "familymart": "全家便利商店", "hilife": "萊爾富",
        "linepay": "LINE Pay", "pchome": "PChome 24h", "yahoo": "Yahoo 購物中心", "shopee": "蝦皮購物",
    }
    enabled_official = [(key, brand) for key, brand in official_sources.items() if config.get(key, {}).get("enabled")]

    def scrape_official_source(item: tuple[str, str]) -> SourceResult:
        key, brand = item
        if config[key].get("parser") == "shopping_links":
            return scrape_shopping_links(key, config[key], brand, excluded_terms, interest_terms)
        return scrape_official_cards(key, config[key], brand, excluded_terms)

    if enabled_official:
        with ThreadPoolExecutor(max_workers=min(5, len(enabled_official))) as pool:
            results.extend(pool.map(scrape_official_source, enabled_official))

    if results and not any(result.ok for result in results):
        filtered_old = [
            deal for raw in old_deals
            if (deal := normalize(raw, excluded_terms, interest_categories, threshold, excluded_categories))
        ]
        old_data["updated_at"] = NOW.isoformat(timespec="seconds")
        old_data["deals"] = filtered_old
        old_data["sources"] = [{"key": result.key, "name": result.name, "status": "error", "count": len([d for d in filtered_old if d.get("source_key") == result.key or d.get("source_name") == result.name]), "message": result.message} for result in results]
        return old_data

    merged: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []
    for result in results:
        deals = result.deals if result.ok else [d for d in old_deals if d.get("source_key") == result.key or d.get("source_name") == result.name]
        merged.extend(deals)
        source_rows.append({"key": result.key, "name": result.name, "status": "ok" if result.ok else "error", "count": len(deals), "message": result.message})

    unique: dict[str, dict[str, Any]] = {}
    cutoff = NOW.date() - timedelta(days=14)
    for raw in merged:
        deal = normalize(raw, excluded_terms, interest_categories, threshold, excluded_categories)
        if not deal:
            continue
        if deal.get("end_date"):
            try:
                if datetime.fromisoformat(deal["end_date"]).date() < cutoff:
                    continue
            except ValueError:
                deal["end_date"] = None
        unique[deal["id"]] = deal
    deals = sorted(unique.values(), key=lambda d: (d.get("score", 0), d.get("published_at", "")), reverse=True)[:160]
    return {"updated_at": NOW.isoformat(timespec="seconds"), "is_demo": False, "sources": source_rows, "deals": deals}


def validate(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(data.get("deals"), list):
        return ["deals 必須是陣列"]
    ids: set[str] = set()
    for index, deal in enumerate(data["deals"]):
        for field in ("id", "title", "url", "category", "tags", "source_type", "source_name", "summary", "benefit", "eligibility", "steps", "limits"):
            if not deal.get(field):
                errors.append(f"第 {index + 1} 筆缺少 {field}")
        if deal.get("id") in ids:
            errors.append(f"重複 id: {deal.get('id')}")
        ids.add(deal.get("id"))
        if deal.get("url") and not str(deal["url"]).startswith("https://"):
            errors.append(f"非 HTTPS 網址: {deal['url']}")
        if deal.get("tags") and not isinstance(deal["tags"], list):
            errors.append(f"第 {index + 1} 筆 tags 必須是陣列")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true", help="Only validate the existing JSON file")
    args = parser.parse_args()
    data = load_json(DATA_FILE, {}) if args.validate_only else update()
    errors = validate(data)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    if not args.validate_only:
        DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK: {len(data.get('deals', []))} deals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
