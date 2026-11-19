import datetime
import json
import tempfile
import unittest
from pathlib import Path

from yap_forever.prices import Market, source_line

FIX = Path(__file__).parent / "fixtures"


def market():
    house = json.loads((FIX / "house_small.json").read_text())
    comm = json.loads((FIX / "commodities_small.json").read_text())
    return Market.from_snapshot(house, comm, snapshot_time="T")


class MarketTests(unittest.TestCase):
    def test_buy_cost_walks_listings(self):
        # Copper Bar 2840: 2 @ 10, 1 @ 50
        self.assertEqual(market().buy_cost(2840, 3), 70)
        self.assertEqual(market().buy_cost(2840, 1), 10)

    def test_buy_cost_thin_market_none(self):
        self.assertIsNone(market().buy_cost(2840, 4))

    def test_buy_cost_zero_qty(self):
        self.assertEqual(market().buy_cost(2840, 0), 0)

    def test_net_sell_applies_cut(self):
        self.assertEqual(market().net_sell(10940), 285)  # 300 * 0.95

    def test_listing_without_buyout_skipped(self):
        m = market()
        self.assertEqual(m.depth(2851), 2)
        self.assertEqual(m.min_price(2851), 5000)

    def test_empty_house(self):
        m = Market.from_snapshot({"id": 112}, {}, snapshot_time="T")
        self.assertIsNone(m.buy_cost(2840, 1))
        self.assertIsNone(m.net_sell(2840))
        self.assertEqual(m.depth(2840), 0)

    def test_save_load_roundtrip(self):
        m = market()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "prices.json"
            m.save(p)
            m2 = Market.load(p)
        self.assertEqual(m2.buy_cost(2840, 3), 70)
        self.assertEqual(m2.snapshot_time, "T")


class SourceLineTests(unittest.TestCase):
    TODAY = datetime.date(2026, 11, 20)

    def line(self, **fields):
        m = Market({})
        m.source = "auctionator"
        for k, v in fields.items():
            setattr(m, k, v)
        return source_line(m, self.TODAY)

    def test_api_prices_have_no_line(self):
        self.assertEqual(source_line(Market({}), self.TODAY), "")

    def test_unknown_scan_day_says_so(self):
        for day in ("", "garbage", None, 5):
            line = self.line(scan_day=day)
            self.assertIn("Scan date unknown: scan again for current prices.", line, repr(day))
            self.assertNotIn("days old", line)

    def test_null_or_odd_fields_in_a_hand_edited_file_do_not_crash(self):
        self.assertNotIn("left out", self.line(scan_day="2026-11-18", dropped=None))
        self.assertNotIn("left out", self.line(scan_day="2026-11-18", dropped="3"))
        self.assertNotIn("left out", self.line(scan_day="2026-11-18", dropped=True))

    def test_known_scan_day_has_no_unknown_note(self):
        self.assertNotIn("unknown", self.line(scan_day="2026-11-18"))


if __name__ == "__main__":
    unittest.main()
