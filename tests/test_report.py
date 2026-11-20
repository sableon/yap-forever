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
from tests.test_planner import BARS, BS, ENCH, run_with_data


def sample():
    rs = [toy.recipe(1, "BS basic", 164, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
          toy.recipe(2, "Ench basic", 333, {toy.ROD: 1})]
    gd = toy.gamedata(rs)
    st = toy.stock({toy.COPPER_BAR: 5})
    m = toy.market({toy.COPPER_BAR: [(100, 100000)], toy.STONE: [(50, 3)]})
    return plan(gd, Valuer(m, gd, st), st, toy.NO_FAVOR, caps={164: 225, 333: 225}), m, gd, st


class VerdictTests(unittest.TestCase):
    def test_verdict_now(self):
        self.assertEqual(verdict(Plan(farm={}), toy.stock()), "Ready to level")

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
        return render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, {164: 225, 333: 225}, today=today)

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
                         "current prices. 5 items left out: not listed or older than 3 days.")


class RenderTests(unittest.TestCase):
    def test_report_sections_in_order(self):
        p, m, gd, st = sample()
        text = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, {164: 225, 333: 225})
        positions = [text.index(f"## {s}\n") for s in SECTIONS]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(len(SECTIONS), 7)

    def test_report_has_no_secrets(self):
        creds = Credentials("myclientid", "s3cr3tvalue", "eu")
        p, m, gd, st = sample()
        text = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, {164: 225, 333: 225})
        self.assertNotIn(creds.client_id, text)
        self.assertNotIn(creds.client_secret, text)

    def test_route_lists_steps(self):
        p, m, gd, st = sample()
        text = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, {164: 225, 333: 225})
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

    def test_no_market_stock_flagged(self):
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})]
        p, gd, m, st = run_with_data(rs, BARS, stock=toy.stock({toy.VEST: 3}))
        text = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, {BS: 225, ENCH: 225})
        self.assertTrue("no market" in text and "Copper Chain Vest" in text)

    def test_report_lists_crafted_intermediates(self):
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(6, "Make Copper Rod", BS, {toy.COPPER_BAR: 1}, (toy.ODD, 1), t=(1, 2, 2, 2),
                         source="starter"),
              toy.recipe(2, "Ench odd", ENCH, {toy.ODD: 1})]
        p, gd, m, st = run_with_data(rs, BARS)
        self.assertIn(toy.ODD, p.crafted)
        text = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, {BS: 225, ENCH: 225})
        self.assertTrue("Crafted for reagents" in text)

    def test_reached_target_is_said(self):
        from tests.test_planner import run_caps
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1))]
        st = toy.stock(skills={BS: 300})
        p = run_caps(rs, {BS: 300}, BARS, stock=st)
        gd, m = toy.gamedata(rs), toy.market(BARS)
        text = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, {BS: 300})
        verdict_part = text[text.index("## Verdict"):text.index("## Route")]
        self.assertIn("Blacksmithing is already at 300: nothing to plan.", verdict_part)


if __name__ == "__main__":
    unittest.main()


class BankGreensReportTests(unittest.TestCase):
    def test_bank_disenchants_in_route_table(self):
        rs = [toy.recipe(1, "BS basic", 164, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(2, "Ench dust", 333, {toy.DUST: 1})]
        gd = toy.gamedata(rs)
        st = toy.stock({toy.BELT: 30})
        m = toy.market({toy.COPPER_BAR: [(100, 100000)], toy.DUST: [(300, 100000)]})
        p = plan(gd, Valuer(m, gd, st), st, toy.NO_FAVOR, caps={164: 40, 333: 40})
        text = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, {164: 225, 333: 225})
        self.assertRegex(text, r"\| Enchanting \| 1→\d+ \| Disenchant greens \| \d+ \| 0s 0c \| 0s 0c \|")
        self.assertIn("Enchanting 1: disenchant 30 Runed Copper Belt from your bank", text)


class BufferTests(unittest.TestCase):
    def test_orange_run_in_one_profession_has_no_buffer(self):
        rs = [toy.recipe(1, "BS basic", 164, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(2, "Ench basic", 333, {toy.ROD: 1})]
        gd = toy.gamedata(rs)
        st = toy.stock(skills={333: 60})
        m = toy.market({toy.COPPER_BAR: [(100, 100000)]})
        p = plan(gd, Valuer(m, gd, st), st, toy.NO_FAVOR, caps={164: 60, 333: 60})
        text = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, {164: 225, 333: 225})
        self.assertIn("| Blacksmithing | 1→60 | BS basic | 59 |", text)

    def test_route_crafts_match_guide_buffer(self):
        from yap_forever.planner import buffer_factor
        import math
        rs = [toy.recipe(1, "BS yellow", 164, {toy.COPPER_BAR: 1}, (toy.STONE, 1), t=(1, 1, 6, 11)),
              toy.recipe(2, "Ench basic", 333, {toy.ROD: 1})]
        gd = toy.gamedata(rs)
        st = toy.stock()
        m = toy.market({toy.COPPER_BAR: [(100, 100000)]})
        p = plan(gd, Valuer(m, gd, st), st, toy.NO_FAVOR, caps={164: 11, 333: 11})
        text = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, {164: 225, 333: 225})
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

    def test_verdict_for_other_pairs(self):
        from yap_forever.planner import Plan
        self.assertEqual(verdict(Plan(), toy.stock()), "Ready to level")

    def test_no_switch_texts_for_blacksmithing_enchanting(self):
        rs = [toy.recipe(1, "BS basic", 164, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(2, "Ench dust", 333, {toy.DUST: 1})]
        gd = toy.gamedata(rs)
        st = toy.stock({toy.BELT: 30})
        m = toy.market({toy.COPPER_BAR: [(100, 100000)], toy.DUST: [(300, 100000)]})
        p = plan(gd, Valuer(m, gd, st), st, toy.NO_FAVOR, caps={164: 40, 333: 40})
        self.assertTrue(sum(p.de_materials.values()))
        text = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, {BS: 225, ENCH: 225})
        for gone in ("Switch order", "Order A", "Order B", "Farm before switching"):
            self.assertNotIn(gone, text)
        self.assertIn("Disenchanting in this route yields about", text)

    def test_ore_section_only_when_farming(self):
        from yap_forever.planner import Plan
        gd = toy.gamedata([])
        ore, bar = toy.IRON_ORE, toy.IRON_BAR
        farming = Plan(final_skill={164: 40}, farm={ore: 30}, farmed_bars={bar: 10})
        text = render(farming, "Switch after a short farm", toy.market(), gd, toy.stock(), toy.NO_FAVOR, {BS: 40})
        self.assertIn("## Ore to mine\n", text)
        self.assertIn("| Iron Ore | 30 |", text)
        self.assertIn("Smelts into: 10 Iron Bar.", text)
        self.assertLess(text.index("## Ore to mine"), text.index("## Route"))
        plain = render(Plan(final_skill={164: 40}), "Ready to level", toy.market(), gd, toy.stock(),
                       toy.NO_FAVOR, {BS: 40})
        self.assertNotIn("Ore to mine", plain)


class TalentNoteTests(unittest.TestCase):
    def test_data_notes_state_the_talents(self):
        from yap_forever.profile import Character
        p, m, gd, st = sample()
        none = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, {164: 225, 333: 225})
        self.assertNotIn("Working Overtime", none)
        self.assertNotIn("Dedicated Study", none)
        c = Character("A B", working_overtime=5, dedicated_study=True)
        text = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, {164: 225, 333: 225}, character=c, reading="points")
        notes = text[text.index("## Data notes"):]
        self.assertIn("Working Overtime 5/5, read as +20 percentage points (unconfirmed in game).", notes)
        self.assertIn("Dedicated Study: one free point a day goes to your lowest profession;", notes)
        self.assertEqual(text[:text.index("## Data notes")], none[:none.index("## Data notes")])
