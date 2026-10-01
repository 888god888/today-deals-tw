"""Conservative, offline-testable evidence and eligibility policy. Never invent terms."""
import re
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def canonical_url(url):
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), ""))


DATE = r"(?:(20\d{2}|1[01]\d)[年/.-])?(\d{1,2})[月/.-](\d{1,2})日?"


def deadline(text, now):
    """Only explicit deadline/range ends; never move an expired date into next year."""
    compact = re.sub(r"[ \t]", "", text)
    matches = list(re.finditer(r"(?:截止(?:日|日期)?(?:至|於|到)?|期限(?:至|到)?|有效(?:期限)?(?:至|到)|至|到|~|～|—|–)[:：]?" + DATE, compact))
    # Also support dates immediately BEFORE 截止/結束, e.g. 10/31截止.
    matches += list(re.finditer(DATE + r"(?:截止|結束)", compact))
    dates = []
    for match in matches:
        y, m, d = match.groups()
        preceding = compact[max(0, match.start() - 45):match.start()]
        prior_years = re.findall(r"(20\d{2}|1[01]\d)[年/.-]", preceding)
        year = int(y) if y else int(prior_years[-1]) if prior_years else now.year
        if year < 1911:
            year += 1911
        # Cross-year only when an explicit Dec -> Jan range is present in December.
        if not y and not prior_years and now.month == 12 and int(m) == 1 and re.search(r"12[月/.-]\d{1,2}", preceding):
            year += 1
        try:
            dates.append(datetime(year, int(m), int(d)).date())
        except ValueError:
            pass
    # Earliest explicit end is safer than picking the most distant unrelated date.
    return min(dates).isoformat() if dates else None


def discount(text):
    text = re.sub(r"(?<=\d),(?=\d)", "", text.lower())
    signals = []
    money = r"(?:nt\$|新台幣|\$)?\s*(\d{1,7})(?:元)?"
    for match in re.finditer(r"滿\s*" + money + r"\s*(?:現)?(?:折|減|省)\s*" + money, text):
        spend, saving = map(int, match.groups())
        if 0 < saving <= spend:
            pct = saving / spend * 100
            signals.append({"kind": "coupon", "percent": round(pct, 1), "saving": saving, "min_spend": spend, "label": f"滿 ${spend:,} 折 ${saving:,} · 實際省 {pct:g}%", "strong": pct >= 25})
    for match in re.finditer(r"原價\s*" + money + r".{0,25}?(?:特價|優惠價|下殺|只要|現價|售價|現售)\s*" + money, text):
        original, current = map(int, match.groups())
        if 0 <= current < original:
            pct = (original-current)/original*100
            signals.append({"kind": "price", "percent": round(pct, 1), "saving": original-current, "price": current, "label": f"${current:,} · 較文中原價省 {pct:.0f}%", "strong": pct >= 25})
    if re.search(r"買一送一|第[二2]件(?:免費|0元)", text):
        signals.append({"kind": "bogo", "percent": 50, "label": "買一送一 · 同價商品約 5 折", "strong": True})
    for match in re.finditer(r"第[二2]件\s*(\d(?:\.\d)?)\s*折", text):
        rate = float(match.group(1))
        if 0 < rate < 10:
            pct = (10-rate)*5
            signals.append({"kind": "bundle", "percent": pct, "label": f"第二件 {rate:g} 折 · 同價兩件實際省 {pct:g}%", "strong": pct >= 25})
    # Shipping, trials, contests, purchase gifts and full-price returns aren't free goods.
    free_lines = re.split(r"[\n。；;]", text)
    if any(re.search(r"免費(?:領取|領|兌換|下載|索取)|(?:0元|零元)(?:領|購|下載)|限時免費", line)
           and not re.search(r"免運|運費|試用|體驗|抽獎|抽出|抽籤|有機會|購買.+贈|滿.+送|消費.+送|退費", line) for line in free_lines):
        signals.append({"kind": "free", "percent": 100, "label": "文中標示免費取得", "strong": True})
    for match in re.finditer(r"(?<!\d)(\d{1,2}(?:\.\d)?)\s*折(?!抵|價|扣)", text):
        if re.search(r"第[二2]件\s*$", text[max(0, match.start()-8):match.start()]):
            continue
        rate = float(match.group(1))
        rate = rate / 10 if rate > 10 else rate
        if 0 < rate <= 10:
            prefix = text[max(0, match.start()-8):match.start()]
            limited = bool(re.search(r"最低|起|最高|部分", prefix)) or text[match.end():match.end()+1] == "起"
            signals.append({"kind": "rate", "percent": round(100-rate*10, 1), "label": f"{rate:g} 折" + ("起／限部分品項" if limited else ""), "strong": rate <= 7.5, "range_claim": limited})
    for match in re.finditer(r"(?:回饋|折扣|現折|省)\s*(\d{1,2}(?:\.\d+)?)\s*%|(\d{1,2}(?:\.\d+)?)\s*%\s*(?:回饋|off)", text):
        pct = float(match.group(1) or match.group(2))
        if not 0 < pct <= 100:
            continue
        window = text[max(0, match.start()-12):match.end()+65]
        cap_match = re.search(r"(?:上限|最高(?:回饋)?|最多)\s*" + money, window)
        cap = int(cap_match.group(1)) if cap_match else None
        claimed = bool(re.search(r"最高|最多|高達", text[max(0, match.start()-10):match.start()]))
        spend_match = re.search(r"(?:消費滿|刷滿|滿額|滿)\s*" + money, text[max(0, match.start()-40):match.end()+65])
        spend = int(spend_match.group(1)) if spend_match else None
        cashback = "回饋" in match.group()
        effective = min(pct, cap / spend * 100) if cashback and cap and spend else pct
        label = f"{pct:g}%" + (f" · 上限 ${cap}" if cap else "") + (f" · 滿 ${spend:,} 實際最高 {effective:g}%" if cashback and spend else "") + ("（最高值）" if claimed else "")
        strong = (effective >= 15 and cap is not None and cap >= 50) if cashback else pct >= 25
        signals.append({"kind": "cashback" if cashback else "percent", "percent": round(effective, 1), "cap": cap, "min_spend": spend or 0, "range_claim": claimed, "label": label, "strong": strong, "unknown_cap": cashback and cap is None})
    # Small, easy tasks are useful, but one-point sign-ins aren't headline deals.
    match = re.search(r"(?:完成問卷|填問卷|簽到|加入好友).{0,30}?(?:送|領|得)\s*(\d+)\s*(?:點|points?)", text, re.I)
    if match and int(match.group(1)) >= 5:
        signals.append({"kind": "task", "percent": 0, "label": f"完成任務得 {match.group(1)} 點", "strong": True})
    if not signals:
        return None
    return max(signals, key=lambda s: (s["strong"], s["percent"]))


def triage(raw, now):
    deal = dict(raw)
    body = deal.get("evidence", "")
    text = f"{deal.get('title', '')}\n{body}"
    signal = discount(text)
    reasons = []
    hurdles = []
    hurdle_rules = [
        (r"抽獎|抽出|抽籤|有機會|機會獲得", "抽獎，不保證取得"),
        (r"新戶|首購|新會員|新客|首次申辦", "新戶／首購限定"),
        (r"分眾|受邀|收到.{0,8}(簡訊|通知)|邀請制", "指定受邀資格"),
        (r"辦卡|申辦信用卡|核卡|新卡友", "需要辦卡"),
        (r"邀請.{0,12}(好友|朋友)|揪團|拉人", "需要邀請他人"),
        (r"生日|壽星|學生限定|員工限定", "特殊身分限定"),
        (r"付費會員|訂閱|自動續訂|試用", "試用／訂閱條件"),
        (r"指定.{0,10}(信用卡|銀行|卡友)|限.{0,8}卡友", "指定信用卡"),
        (r"門市限定|限.{0,12}門市|僅限.{0,12}(台北|臺北|台中|臺中|高雄)", "指定門市／地區"),
        (r"搶登錄|需登錄|限量.{0,6}名|名額.{0,6}名", "名額／登錄競爭"),
        (r"贈品|滿額送|消費.{0,12}送|購買.{0,12}送", "贈品可能需先消費"),
    ]
    for pattern, label in hurdle_rules:
        if re.search(pattern, text):
            hurdles.append(label)
    if re.search(r"(?:每月|當月|累積|滿額).{0,12}(?:消費|刷卡)|消費滿\s*[1-9]\d{3,}", text):
        hurdles.append("消費／累積門檻")
    if signal and signal.get("min_spend", 0) > 1000:
        hurdles.append("滿額門檻超過 $1,000")
    if signal and signal.get("range_claim"):
        reasons.append("最高／最低值，適用品項或組合尚須核對")
    if signal and signal.get("unknown_cap"):
        reasons.append("回饋上限未確認，不能只看宣傳百分比")
    if not deal.get("body_read"):
        reasons.append("只取得標題或摘要，未讀到活動內文")
    if not signal:
        reasons.append("折扣幅度或免費條件未獲數字佐證")
    elif not signal["strong"]:
        reasons.append("未達大折扣門檻")
    action = re.search(r"購買|下單|結帳|領取|兌換|下載|加入好友|填寫|問卷|簽到|輸入.{0,8}(優惠碼|折扣碼)|輸入.{0,3}[A-Z0-9]{3,}", body)
    if not action:
        reasons.append("領取／購買方式未確認")
    end = deadline(text, now)
    if end and end < now.date().isoformat():
        return None, "已過期"
    if re.search(r"已截止|已結束|已售完|已失效|全數售罄", text):
        return None, "來源標示已結束"
    first = deal.get("published_at") or deal.get("first_seen_at") or now.isoformat()
    try:
        age = (now - datetime.fromisoformat(first).astimezone(now.tzinfo)).total_seconds()/86400
        if age > (30 if end else 7):
            return None, "情報過舊"
    except (TypeError, ValueError):
        reasons.append("情報發布日期不明")
    if re.search(r"美元|美國限定|日本限定|us\$|英鎊|£", text, re.I) and not re.search(r"台灣可|臺灣可|全台|新台幣|nt\$", text, re.I):
        return None, "海外優惠未確認台灣適用"
    status = "candidate" if reasons else "conditional" if hurdles else "easy"
    if signal and not signal["strong"] and deal.get("body_read"):
        return None, "折扣不足"
    checked = deal.get("checked_at") or deal.get("first_seen_at")
    try:
        stale = not checked or now - datetime.fromisoformat(checked).astimezone(now.tzinfo) > timedelta(hours=72)
    except ValueError:
        stale = True
    if stale:
        status = "candidate"
        reasons.append("超過 72 小時未重新讀取，需重查")
    score = (signal or {}).get("percent", 0)*.35 + (35 if status == "easy" else 15 if status == "conditional" else 0)
    deal.update(status=status, reasons=reasons, hurdles=list(dict.fromkeys(hurdles)), end_date=end,
                discount=signal, discount_label=signal["label"] if signal else "折扣尚未確認",
                ease_label="未見額外資格；仍需核對庫存" if status == "easy" else "有參加門檻" if status == "conditional" else "待確認",
                score=round(score + (10 if deal.get("source_type") == "official" else 0)),
                deal_strength="strong" if signal and signal["strong"] else "unknown")
    return deal, None
