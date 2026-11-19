import datetime
import unittest

from tests import toy
from yap_forever import settings
from yap_forever.config import Credentials
USER_DIR = settings.home({})  # the player's real folder, not the test home
from yap_forever.costmodel import Valuer
from yap_forever.favor import load_favor
from yap_forever.planner import Plan, plan
from yap_forever.report import SECTIONS, render, verdict


def sample():
    rs = [toy.recipe(1, "BS basic", 164, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
          toy.recipe(2, "Ench basic", 333, {toy.ROD: 1})]
    gd = toy.gamedata(rs)
    st = toy.stock({toy.COPPER_BAR: 5})
    m = toy.market({toy.COPPER_BAR: [(100, 100000)], toy.STONE: [(50, 3)]})
    return plan(gd, Valuer(m, gd, st), st, toy.NO_FAVOR), m, gd, st


class VerdictTests(unittest.TestCase):
    def test_verdict_now(self):
        self.assertEqual(verdict(Plan(farm={}), toy.stock()), "Switch now")

    def test_verdict_short(self):
        self.assertEqual(verdict(Plan(farm={2770: 100, 2771: 50}), toy.stock()), "Switch after a short farm")

    def test_verdict_not_yet(self):
        self.assertEqual(verdict(Plan(farm={2770: 250}), toy.stock()), "Not yet")


AUCTIONATOR_LINE = ("Prices: Auctionator scan of 2026-11-18 (one price per item, no listing depth: costs are a "
                    "lower bound and AH sale limits are approximate).")


class PricesHeaderTests(unittest.TestCase):
    def render(self, today, **fields):
        p, m, gd, st = sample()
        for k, v in fields.items():
            setattr(m, k, v)
        return render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, today=today)

    def test_api_prices_keep_todays_report(self):
        text = self.render(datetime.date(2026, 11, 20))
        self.assertNotIn("Auctionator", text)
        self.assertNotIn("days old", text)
        self.assertEqual(text.splitlines()[1], "")

    def test_fresh_auctionator_scan(self):
        text = self.render(datetime.date(2026, 11, 20), source="auctionator", scan_day="2026-11-18")
        self.assertEqual(text.splitlines()[2], AUCTIONATOR_LINE)
        self.assertNotIn("days old", text)
        self.assertIn("- Prices: Auctionator scan of 2026-11-18.", text)
        self.assertNotIn("AH snapshot", text)

    def test_stale_auctionator_scan_counts_dropped_items(self):
        text = self.render(datetime.date(2026, 11, 25), source="auctionator", scan_day="2026-11-18", dropped=5)
        self.assertEqual(text.splitlines()[2], AUCTIONATOR_LINE + " This scan is 7 days old: scan again for "
                         "current prices. 5 items older than the scan window left out.")


class RenderTests(unittest.TestCase):
    def test_report_sections_in_order(self):
        p, m, gd, st = sample()
        text = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR)
        positions = [text.index(f"## {s}\n") for s in SECTIONS]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(len(SECTIONS), 9)

    def test_report_has_no_secrets(self):
        creds = Credentials("myclientid", "s3cr3tvalue", "eu")
        p, m, gd, st = sample()
        text = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR)
        self.assertNotIn(creds.client_id, text)
        self.assertNotIn(creds.client_secret, text)

    def test_route_lists_steps(self):
        p, m, gd, st = sample()
        text = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR)
        self.assertIn("BS basic", text)
        self.assertIn("Ench basic", text)

    def test_real_favor_toml_parses(self):
        from yap_forever import gamedata
        fav = load_favor("Exalted")
        self.assertTrue(fav.recipes)
        if (settings.paths(USER_DIR).gamedata / "Recipes.lua").exists():
            gd = gamedata.load_gamedata(settings.paths(USER_DIR).gamedata)
            for spell in fav.recipes:
                self.assertIn(gd.recipes[spell].skill_line, (164, 333))


if __name__ == "__main__":
    unittest.main()


class BankGreensReportTests(unittest.TestCase):
    def test_bank_disenchants_in_route_table(self):
        rs = [toy.recipe(1, "BS basic", 164, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(2, "Ench dust", 333, {toy.DUST: 1})]
        gd = toy.gamedata(rs)
        st = toy.stock({toy.BELT: 30})
        m = toy.market({toy.COPPER_BAR: [(100, 100000)], toy.DUST: [(300, 100000)]})
        p = plan(gd, Valuer(m, gd, st), st, toy.NO_FAVOR, cap=40)
        text = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR)
        self.assertRegex(text, r"\| Enchanting \| 1→\d+ \| Disenchant greens \| \d+ \| 0s 0c \| 0s 0c \|")
        self.assertIn("Enchanting 1: disenchant 30 Runed Copper Belt from your bank", text)

    def test_order_a_text_matches_planner(self):
        rs = [toy.recipe(1, "BS basic", 164, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(2, "Ench dust", 333, {toy.DUST: 1})]
        gd = toy.gamedata(rs)
        st = toy.stock({toy.BELT: 30})
        m = toy.market({toy.COPPER_BAR: [(100, 100000)], toy.DUST: [(300, 100000)]})
        p = plan(gd, Valuer(m, gd, st), st, toy.NO_FAVOR, cap=40)
        text = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR)
        self.assertNotIn("wait in the bank or mail", text)
        self.assertIn("disenchanted first", text)


class BufferTests(unittest.TestCase):
    def test_orange_run_in_one_profession_has_no_buffer(self):
        rs = [toy.recipe(1, "BS basic", 164, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(2, "Ench basic", 333, {toy.ROD: 1})]
        gd = toy.gamedata(rs)
        st = toy.stock(skills={333: 60})
        m = toy.market({toy.COPPER_BAR: [(100, 100000)]})
        p = plan(gd, Valuer(m, gd, st), st, toy.NO_FAVOR, cap=60)
        text = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR)
        self.assertIn("| Blacksmithing | 1→60 | BS basic | 59 |", text)

    def test_route_crafts_match_guide_buffer(self):
        from yap_forever.planner import buffer_factor
        import math
        rs = [toy.recipe(1, "BS yellow", 164, {toy.COPPER_BAR: 1}, (toy.STONE, 1), t=(1, 1, 6, 11)),
              toy.recipe(2, "Ench basic", 333, {toy.ROD: 1})]
        gd = toy.gamedata(rs)
        st = toy.stock()
        m = toy.market({toy.COPPER_BAR: [(100, 100000)]})
        p = plan(gd, Valuer(m, gd, st), st, toy.NO_FAVOR, cap=11)
        text = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR)
        yellow = [s for s in p.steps if s.spell_id == 1 and s.crafts > 1]
        self.assertTrue(yellow)
        for s in yellow:
            self.assertIn(f"| BS yellow | {math.ceil(s.crafts * 1.15 - 1e-6)} |", text)
        self.assertEqual(buffer_factor(1.0), 1.0)


class AnyPairReportTests(unittest.TestCase):
    def test_report_hides_switch_order_for_other_pairs(self):
        from yap_forever.planner import Plan
        p = Plan(final_skill={197: 40, 333: 40})
        gd = toy.gamedata([])
        text = render(p, "Ready to level", toy.market(), gd, toy.stock(), toy.NO_FAVOR, caps={197: 40, 333: 40})
        self.assertEqual(text.splitlines()[0], "# Tailoring + Enchanting plan")
        self.assertNotIn("## Switch order", text)
        self.assertNotIn("## Farm before switching", text)

    def test_report_keeps_switch_order_for_the_main_pair(self):
        from yap_forever.planner import Plan
        p = Plan(final_skill={164: 40, 333: 40})
        text = render(p, "Switch now", toy.market(), toy.gamedata([]), toy.stock(), toy.NO_FAVOR)
        self.assertIn("## Switch order", text)

    def test_verdict_for_other_pairs(self):
        from yap_forever.planner import Plan
        self.assertEqual(verdict(Plan(), toy.stock(), caps={197: 40}), "Ready to level")
