import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, Mock
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from quality import discount, deadline, triage, canonical_url
from update_deals import SourceResult, Reader, AccessBlocked, merge_results, record, validate, safe_url, collect_ptt, collect_feed, collect_search, update

NOW = datetime(2026, 10, 1, 12, tzinfo=ZoneInfo("Asia/Taipei"))
PREFS = {"interest_categories": ["3C", "免費", "任務", "遊戲娛樂", "餐飲食品", "金融支付"], "exclude_terms": ["星巴克", "女裝"], "excluded_categories": ["交通"]}


def item(text="滑鼠原價1690元，特價518元，於網站結帳購買。活動至10/5。", **kwargs):
    raw = record("ptt", {"name": "測試論壇", "source_type": "community"}, "滑鼠限時特價", "https://example.org/deal", text, NOW, read=True)
    return {**raw, **kwargs}


class DiscountTests(unittest.TestCase):
    def test_price_pair(self):
        d = discount("耳機原價1,690元，特價518元，網站結帳")
        self.assertTrue(d["strong"]); self.assertEqual(d["price"], 518)

    def test_large_coupon_low_ratio(self):
        self.assertFalse(discount("滿20000折1000")["strong"])
        self.assertEqual(discount("滿20000折1000")["percent"], 5)

    def test_good_coupon(self):
        self.assertTrue(discount("滿300元折100元")["strong"])

    def test_free_shipping_not_free_product(self):
        self.assertIsNone(discount("滿200免運費，免費配送"))

    def test_free_trial(self):
        self.assertIsNone(discount("免費領取試用，需要訂閱"))

    def test_lottery(self):
        self.assertIsNone(discount("抽獎有機會免費領取耳機"))

    def test_bogo(self):
        self.assertEqual(discount("咖啡買一送一")["percent"], 50)

    def test_95_fold(self):
        self.assertFalse(discount("全館95折")["strong"])

    def test_percentage_scope(self):
        self.assertIsNone(discount("耳機100%充滿電，另有優惠資訊"))

    def test_percentage_max_100(self):
        self.assertIsNone(discount("回饋200%"))

    def test_cap_matters(self):
        self.assertFalse(discount("回饋20%，上限10元")["strong"])
        self.assertTrue(discount("回饋20%，上限100元")["strong"])

    def test_cap_with_spend(self):
        d = discount("消費滿1000元，回饋20%，上限50元")
        self.assertEqual(d["percent"], 5); self.assertFalse(d["strong"])

    def test_second_item_discount(self):
        self.assertEqual(discount("第二件5折")["percent"], 25)
        self.assertFalse(discount("第二件6折")["strong"])

    def test_unknown_cashback_cap(self):
        self.assertFalse(discount("回饋30%")["strong"])

    def test_high_claim(self):
        self.assertTrue(discount("高達20%回饋，上限100元")["range_claim"])

    def test_claimed_low_price_not_verified(self):
        self.assertIsNone(discount("滑鼠史低518元，2026年優惠"))

    def test_small_task(self):
        self.assertIsNone(discount("簽到送1點"))
        self.assertTrue(discount("完成問卷送10點")["strong"])


class DateTests(unittest.TestCase):
    def test_no_rollover(self):
        self.assertEqual(deadline("活動至3/1", NOW), "2026-03-01")

    def test_no_random_dates(self):
        self.assertIsNone(deadline("發布於2026/9/28；手機型號10/20", NOW))

    def test_range_inherits_year(self):
        self.assertEqual(deadline("活動2025/9/1～9/30", NOW), "2025-09-30")

    def test_chinese_range(self):
        self.assertEqual(deadline("活動2026年10月1日至10月5日", NOW), "2026-10-05")

    def test_suffix(self):
        self.assertEqual(deadline("10/5截止", NOW), "2026-10-05")

    def test_invalid_date(self):
        self.assertIsNone(deadline("活動至2/30", NOW))

    def test_roc_year(self):
        self.assertEqual(deadline("活動至115/10/5", NOW), "2026-10-05")

    def test_old_roc_range(self):
        self.assertEqual(deadline("活動113年9月1日～9月30日", NOW), "2024-09-30")


class TriageTests(unittest.TestCase):
    def test_easy(self):
        d, reason = triage(item(), NOW)
        self.assertIsNone(reason); self.assertEqual(d["status"], "easy")

    def test_unread(self):
        self.assertEqual(triage(item(body_read=False), NOW)[0]["status"], "candidate")

    def test_new_user(self):
        d = triage(item("新戶限定耳機5折，於網站結帳購買。"), NOW)[0]
        self.assertEqual(d["status"], "conditional"); self.assertIn("新戶／首購限定", d["hurdles"])

    def test_max_rate(self):
        self.assertEqual(triage(item("滑鼠最低5折，於網站結帳購買。"), NOW)[0]["status"], "candidate")

    def test_unknown_action(self):
        self.assertEqual(triage(item("滑鼠原價1690元，特價518元。"), NOW)[0]["status"], "candidate")

    def test_expired(self):
        self.assertEqual(triage(item("耳機5折，網站購買，至9/30。"), NOW)[1], "已過期")

    def test_stale_check(self):
        self.assertEqual(triage(item(checked_at=(NOW-timedelta(days=4)).isoformat()), NOW)[0]["status"], "candidate")

    def test_old_without_deadline(self):
        self.assertEqual(triage(item("耳機5折，網站購買。", first_seen_at=(NOW-timedelta(days=8)).isoformat()), NOW)[1], "情報過舊")

    def test_foreign(self):
        self.assertEqual(triage(item("耳機原價50美元特價20美元，網站購買。"), NOW)[1], "海外優惠未確認台灣適用")


class MergeTests(unittest.TestCase):
    def test_no_demo_carry(self):
        out = merge_results([SourceResult("ptt", "測試", status="error")], {"is_demo": True, "deals": [item()]}, PREFS, NOW)
        self.assertEqual(out["deals"] + out["pending"], [])

    def test_all_failed_does_not_fake_update(self):
        out = merge_results([SourceResult("ptt", "測試", status="error")], {"schema_version": 6, "updated_at": "2026-09-30T12:00:00+08:00"}, PREFS, NOW)
        self.assertEqual(out["updated_at"], "2026-09-30T12:00:00+08:00"); self.assertEqual(out["run_status"], "error")

    def test_failed_source_retained_as_pending(self):
        old = merge_results([SourceResult("ptt", "測試", [item()])], {}, PREFS, NOW)
        new = merge_results([SourceResult("ptt", "測試", status="error")], old, PREFS, NOW)
        self.assertFalse(new["deals"]); self.assertEqual(len(new["pending"]), 1)

    def test_filters_and_real_counts(self):
        out = merge_results([SourceResult("ptt", "測試", [item(), item("星巴克咖啡買一送一，購買。", id="other")])], {}, PREFS, NOW)
        self.assertEqual(len(out["deals"]), 1); self.assertEqual(out["sources"][0]["rejected"], 1); self.assertEqual(validate(out), [])

    def test_dedup(self):
        out = merge_results([SourceResult("ptt", "測試", [item(), item()])], {}, PREFS, NOW)
        self.assertEqual(len(out["deals"]), 1)

    def test_discovery_age_does_not_reset(self):
        old = merge_results([SourceResult("ptt", "測試", [item("耳機5折，網站購買。")])], {}, PREFS, NOW)
        later = NOW + timedelta(days=8)
        raw = item("耳機5折，網站購買。", first_seen_at=later.isoformat(), checked_at=later.isoformat())
        out = merge_results([SourceResult("ptt", "測試", [raw])], old, PREFS, later)
        self.assertFalse(out["deals"])
        again = merge_results([SourceResult("ptt", "測試", [raw])], out, PREFS, later+timedelta(days=1))
        self.assertFalse(again["deals"])


class SafetyTests(unittest.TestCase):
    def test_canonical(self):
        self.assertEqual(canonical_url("https://example.org/a/?id=2&utm_source=x#foo"), "https://example.org/a?id=2")

    def test_private_network(self):
        with patch("update_deals.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
            with self.assertRaises(ValueError): safe_url("https://example.org/")

    def test_429_not_retried(self):
        response = Mock(status_code=429)
        with patch("update_deals.safe_url"), patch("update_deals.requests.get", return_value=response) as get:
            reader = Reader()
            for _ in range(2):
                with self.assertRaises(AccessBlocked): reader.get("https://example.org/")
            self.assertEqual(get.call_count, 1)

    def test_redirect_drops_token(self):
        redirect = Mock(status_code=302, is_redirect=True, headers={"Location": "https://other.example.org/"})
        ok = Mock(status_code=200, is_redirect=False, ok=True, content=b"ok", apparent_encoding="utf-8")
        with patch("update_deals.safe_url"), patch("update_deals.requests.get", side_effect=[redirect, ok]) as get:
            Reader().get("https://example.org/", headers={"X-Subscription-Token": "test-secret"})
            self.assertNotIn("X-Subscription-Token", get.call_args_list[1].kwargs["headers"])


class CollectorTests(unittest.TestCase):
    def test_ptt_newest_first(self):
        timestamp = int(NOW.timestamp())
        html = f'<div class="r-ent"><div class="title"><a href="/bbs/Test/M.{timestamp-20}.A.html">[情報]舊耳機特價</a></div></div><div class="r-ent"><div class="title"><a href="/bbs/Test/M.{timestamp}.B.html">[情報]新耳機特價</a></div></div>'
        with patch.object(Reader, "get", return_value=Mock(text=html)), patch.object(Reader, "body", return_value=("耳機5折，網站結帳購買。", "")):
            r = collect_ptt("ptt", {"name": "測試", "url": "https://example.org/bbs/Test/index.html", "pages": 1, "article_limit": 1}, NOW)
            self.assertEqual(r.status, "ok"); self.assertIn("新耳機", r.deals[0]["title"])

    def test_feed_partial_preserves_success(self):
        xml = b'<rss><channel><item><title>free \xe5\x85\x8d\xe8\xb2\xbb</title><link>https://news.google.com/rss/articles/example</link><description>summary</description><pubDate>Thu, 01 Oct 2026 01:00:00 GMT</pubDate></item></channel></rss>'
        with patch.object(Reader, "get", side_effect=[Mock(content=xml), ValueError("HTTP 500")]):
            r = collect_feed("feed", {"name": "測試", "urls": ["https://example.org/a.xml", "https://example.org/b.xml"]}, NOW)
            self.assertEqual(r.status, "partial"); self.assertEqual(len(r.deals), 1); self.assertFalse(r.deals[0]["body_read"])

    def test_feed_empty_is_not_failure(self):
        with patch.object(Reader, "get", return_value=Mock(content=b"<rss><channel/></rss>")):
            self.assertEqual(collect_feed("feed", {"name": "測試", "urls": ["https://example.org/a.xml"]}, NOW).status, "ok")

    def test_search_without_key_does_not_request(self):
        with patch.dict("os.environ", {"BRAVE_SEARCH_API_KEY": ""}), patch.object(Reader, "get") as get:
            r = collect_search("search", {"name": "測試"}, NOW)
            self.assertEqual(r.status, "not_configured"); get.assert_not_called()

    def test_bad_source_is_isolated(self):
        cfg = {"ptt_bad": {"enabled": True, "url": "https://example.org/"}, "preferences": PREFS}
        result = update(cfg, {}, NOW)
        self.assertEqual(result["sources"][0]["status"], "error")

    def test_url_dedup_across_tracking(self):
        a = record("ptt", {"name": "測試"}, "耳機5折", "https://example.org/deal?utm_source=a", "耳機5折，結帳購買。", NOW, read=True)
        b = record("rss", {"name": "測試"}, "耳機5折", "https://example.org/deal?utm_source=b", "耳機5折，結帳購買。", NOW, read=True)
        result = merge_results([SourceResult("ptt", "測試", [a]), SourceResult("rss", "測試", [b])], {}, PREFS, NOW)
        self.assertEqual(len(result["deals"]), 1)

    def test_unknown_brand_is_pending_not_dropped(self):
        raw = record("ptt", {"name": "測試"}, "陌生品牌XYZ原價1000特價500", "https://example.org/unknown", "原價1000元，特價500元，網站結帳購買。", NOW, read=True)
        result = merge_results([SourceResult("ptt", "測試", [raw])], {}, PREFS, NOW)
        self.assertFalse(result["deals"]); self.assertEqual(len(result["pending"]), 1)

    def test_board_context_classifies_unknown_game(self):
        raw = record("ptt_steam", {"name": "遊戲板", "default_tags": ["遊戲娛樂"]}, "XYZ限時免費領取", "https://example.org/game", "本作限時免費領取，於網站下載。", NOW, read=True)
        self.assertEqual(raw["tags"], ["遊戲娛樂", "免費"])


if __name__ == "__main__": unittest.main()
