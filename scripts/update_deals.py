#!/usr/bin/env python3
"""Collect public Taiwan deal listings into the static site's deals.json."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "dist" / "data" / "deals.json"
CONFIG_FILE = ROOT / "config" / "sources.json"
TZ = ZoneInfo("Asia/Taipei")
NOW = datetime.now(TZ)
USER_AGENT = "TaiwanDailyDeals/1.0 (+GitHub Actions; public deal indexer)"
KEYWORDS = ("免費", "優惠", "折", "回饋", "贈", "送", "特價", "好康", "折扣", "買一送一", "點數", "券", "免運", "限時")


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


def classify(text: str) -> str:
    lowered = text.lower()
    if any(k in lowered for k in ("免費", "0元", "零元", "免費領", "贈送", "送一", "line point", "line point")):
        return "免費"
    if any(k in lowered for k in ("咖啡", "餐", "堡", "飯糰", "飲", "雞", "披薩", "甜點", "麥當勞", "肯德基", "全家", "7-11", "超商")):
        return "餐飲"
    if any(k in lowered for k in ("信用卡", "支付", "回饋金", "刷卡", "銀行", "line pay", "悠遊付", "街口")):
        return "金融"
    if any(k in lowered for k in ("騎乘", "車資", "goshare", "irent", "uber", "台鐵", "高鐵", "交通")):
        return "交通"
    if any(k in lowered for k in ("任務", "簽到", "下載", "問卷", "app", "登錄", "加入好友")):
        return "任務"
    if any(k in lowered for k in ("蝦皮", "pchome", "momo", "免運", "券後", "購物", "折價券", "特價")):
        return "購物"
    return "其他"


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


def article_text(url: str) -> str:
    soup = BeautifulSoup(fetch(url), "html.parser")
    content = soup.select_one("#main-content")
    if not content:
        return ""
    for node in content.select(".article-metaline, .article-metaline-right, .push, .f2, script, style"):
        node.decompose()
    raw = content.get_text("\n", strip=True).split("--")[0]
    useful = [line for line in raw.splitlines() if line and not line.startswith(("http://", "https://", "※ 發信站"))]
    return "\n".join(useful[:16])


def scrape_ptt(key: str, cfg: dict[str, Any]) -> SourceResult:
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
            summary = clean(next((line for line in body.splitlines() if len(line) >= 12), title), 150)
            claim = infer_claim(body, "開啟原文，依文內活動步驟與限制參加")
            published = ptt_publish_date(raw_date)
            end_date = parse_date(full_text)
            deals.append({
                "id": make_id(key, url, title), "source_key": key, "title": re.sub(r"^(Re:|R:)?\s*\[[^]]+\]\s*", "", title),
                "brand": infer_brand(full_text, "網友分享"), "summary": summary, "claim": claim, "category": classify(full_text),
                "source_type": "community", "source_name": name, "published_at": published, "end_date": end_date,
                "score": score_deal(title, body, "community", published, end_date), "url": url
            })
        if not deals:
            raise ValueError("頁面未找到可辨識的優惠文章")
        return SourceResult(key, name, deals, True)
    except Exception as exc:
        return SourceResult(key, name, [], False, clean(str(exc), 100))


def scrape_official_cards(key: str, cfg: dict[str, Any], brand: str) -> SourceResult:
    name, url = cfg["name"], cfg["url"]
    try:
        soup = BeautifulSoup(fetch(url), "html.parser")
        candidates: list[tuple[str, str, str]] = []
        seen_titles: set[str] = set()
        for heading in soup.select("h1, h2, h3, h4, [class*=title]"):
            title = clean(heading.get_text(" ", strip=True), 120)
            if len(title) < 7 or title in seen_titles or not any(word.lower() in title.lower() for word in KEYWORDS):
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
            full_text = f"{title} {summary}"
            end_date = parse_date(full_text)
            claim = infer_claim(summary, "開啟官方活動頁，依指定通路與辦法參加")
            published = NOW.isoformat(timespec="seconds")
            deals.append({
                "id": make_id(key, item_url, title), "source_key": key, "title": title, "brand": brand,
                "summary": summary or "官方活動內容與適用門市請見詳細說明。", "claim": claim, "category": classify(full_text),
                "source_type": "official", "source_name": name, "published_at": published, "end_date": end_date,
                "score": score_deal(title, summary, "official", published, end_date), "url": item_url
            })
        if not deals:
            raise ValueError("頁面未找到可辨識的優惠項目")
        return SourceResult(key, name, deals, True)
    except Exception as exc:
        return SourceResult(key, name, [], False, clean(str(exc), 100))


def load_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


def normalize(deal: dict[str, Any]) -> dict[str, Any] | None:
    required = ("id", "title", "url", "source_name", "source_type")
    if any(not deal.get(field) for field in required):
        return None
    deal["category"] = deal.get("category") if deal.get("category") in {"免費", "餐飲", "購物", "交通", "金融", "任務", "其他"} else "其他"
    deal["summary"] = clean(deal.get("summary"), 180)
    deal["claim"] = clean(deal.get("claim"), 140)
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
    old_data = load_json(DATA_FILE, {"deals": [], "sources": []})
    old_deals = old_data.get("deals", [])
    results: list[SourceResult] = []
    if config.get("ptt", {}).get("enabled"):
        results.append(scrape_ptt("ptt", config["ptt"]))
    if config.get("mcdonalds", {}).get("enabled"):
        results.append(scrape_official_cards("mcdonalds", config["mcdonalds"], "麥當勞"))
    if config.get("kfc", {}).get("enabled"):
        results.append(scrape_official_cards("kfc", config["kfc"], "肯德基"))

    if results and not any(result.ok for result in results):
        old_data["updated_at"] = NOW.isoformat(timespec="seconds")
        old_data["sources"] = [{"key": result.key, "name": result.name, "status": "error", "count": len([d for d in old_deals if d.get("source_key") == result.key or d.get("source_name") == result.name]), "message": result.message} for result in results]
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
        deal = normalize(raw)
        if not deal:
            continue
        if deal.get("end_date"):
            try:
                if datetime.fromisoformat(deal["end_date"]).date() < cutoff:
                    continue
            except ValueError:
                deal["end_date"] = None
        unique[deal["id"]] = deal
    deals = sorted(unique.values(), key=lambda d: (d.get("score", 0), d.get("published_at", "")), reverse=True)[:120]
    return {"updated_at": NOW.isoformat(timespec="seconds"), "is_demo": False, "sources": source_rows, "deals": deals}


def validate(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(data.get("deals"), list):
        return ["deals 必須是陣列"]
    ids: set[str] = set()
    for index, deal in enumerate(data["deals"]):
        for field in ("id", "title", "url", "category", "source_type", "source_name"):
            if not deal.get(field):
                errors.append(f"第 {index + 1} 筆缺少 {field}")
        if deal.get("id") in ids:
            errors.append(f"重複 id: {deal.get('id')}")
        ids.add(deal.get("id"))
        if deal.get("url") and not str(deal["url"]).startswith("https://"):
            errors.append(f"非 HTTPS 網址: {deal['url']}")
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
