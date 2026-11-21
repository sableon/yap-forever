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
        self.assertEqual(verdict(Plan(farm={2770: 100, 2771: 50}), toy.stock()), "Short farm first")

    def test_verdict_not_yet(self):
        self.assertEqual(verdict(Plan(farm={2770: 250}), toy.stock()), "Not yet")


AUCTIONATOR_LINE = ("Prices: Auctionator scan of 2026-11-18 (one price and one count per item, no listing depth: "
                    "costs are a lower bound, and the supplier note and buyout flag use that one count).")


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
        self.assertNotIn("Ready to level", verdict_part)  # every target reached: no verdict is claimed
        self.assertNotIn("Planned to", verdict_part)

    def test_a_verdict_stays_while_another_target_is_still_to_plan(self):
        from tests.test_planner import run_caps
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})]
        st = toy.stock(skills={BS: 300})
        p = run_caps(rs, {BS: 300, ENCH: 20}, BARS, stock=st)
        text = render(p, verdict(p, st), toy.market(BARS), toy.gamedata(rs), st, toy.NO_FAVOR, {BS: 300, ENCH: 20})
        verdict_part = text[text.index("## Verdict"):text.index("## Route")]
        self.assertIn("Blacksmithing is already at 300: nothing to plan.", verdict_part)
        self.assertIn("**Ready to level.**", verdict_part)
        self.assertIn("Planned to:", verdict_part)


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
        text = render(farming, "Short farm first", toy.market(), gd, toy.stock(), toy.NO_FAVOR, {BS: 40})
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


class BudgetLineTests(unittest.TestCase):
    def test_budget_lines(self):
        from yap_forever import budget
        from yap_forever.config import Budget
        from yap_forever.guide import gold
        from yap_forever.shared import Budget as SharedGold
        p, m, gd, st = sample()
        caps = {164: 225, 333: 225}
        cut = budget.BudgetCut(dict(caps), p, 341200, {164: (300, 1200000)}, {}, dict(caps), {164: 1, 333: 1})
        goal = Budget(30)
        text = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, caps, budget=SharedGold(500000, "2/alliance"),
                      budget_lines=budget.lines(cut, goal), goal=goal)
        head = text[text.index("## Verdict"):text.index("## Route")]
        self.assertIn(f"30g takes Blacksmithing to 225 and Enchanting to 225 ({gold(341200)}).", head)
        self.assertIn(f"The next stop, Blacksmithing 300, costs about {gold(1200000)} more.", head)
        self.assertIn("shared by your 2/alliance characters; planned to your 30g budget)", text)
        cut.next_stop = {}
        plain = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, caps, budget_lines=budget.lines(cut, goal))
        self.assertNotIn("The next stop", plain)
        self.assertNotIn("planned to your", render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, caps))


class FreeSkipNoteTests(unittest.TestCase):
    def test_data_notes_name_the_trips_left_out(self):
        # #90: each trip the route was planned without (plan.take_free_skips) is one line, after the saving line
        p, m, gd, st = sample()
        caps = {164: 225, 333: 225}
        skips = ["Planned without the trip to buy the pattern for BS scroll: the route without it costs the same."]
        text = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, caps, saving_line="A saving line.", free_skips=skips)
        notes = text[text.index("## Data notes"):]
        self.assertEqual(text.count(skips[0]), 1)
        self.assertLess(notes.index("- A saving line."), notes.index(f"- {skips[0]}"))
        self.assertNotIn("Planned without", render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, caps))


class CouldAlsoMakeReportTests(unittest.TestCase):
    """#95: inside "Merchant's Favor", the suggestions under a bold heading (the report's sections stay seven), and a
    data note that Favor recipes are not used to level."""
    BLOCK = ["**You could also make**", "", "Merchant's Favor recipes to craft once ...", "",
             "- **Staff of Ana** (Enchanting 100, for level 30): 50 of your 150 Favor; materials about 10s on the AH.", ""]

    def render(self, favor, could_make=(), levels=True):
        from yap_forever.gamedata import ItemInfo
        p, m, gd, st = sample()
        if levels:
            gd.items[9001] = ItemInfo(9001, "Staff", 2, 30, 2, 100, 400, bonding=2, required_level=30)
        return render(p, verdict(p, st), m, gd, st, favor, {164: 225, 333: 225}, could_make=could_make)

    def test_inside_merchants_favor(self):
        from yap_forever.favor import FavorData
        text = self.render(FavorData({1: 50}, {}, [toy_turnin()]), self.BLOCK)
        favor = text[text.index("## Merchant's Favor\n"):text.index("## Totals\n")]
        self.assertIn("\n".join(self.BLOCK), favor)
        self.assertLess(favor.index("Spent 0 of 0 Favor."), favor.index("**You could also make**"))
        self.assertLess(favor.index("**You could also make**"), favor.index("Crate turn-ins"))
        positions = [text.index(f"## {s}\n") for s in SECTIONS]
        self.assertEqual(positions, sorted(positions))
        notes = text[text.index("## Data notes"):]
        self.assertIn("- Merchant's Favor recipes are not used to level (see You could also make).", notes)

    def test_data_note_without_suggestions(self):
        from yap_forever.favor import FavorData, no_favor
        notes = self.render(FavorData({1: 50}, {}, []))
        notes = notes[notes.index("## Data notes"):]
        self.assertIn("- Merchant's Favor recipes are not used to level.", notes)
        self.assertNotIn("You could also make", notes)
        horde = self.render(no_favor())  # no Favor recipes: nothing to say
        self.assertNotIn("not used to level", horde)
        self.assertNotIn("You could also make", horde)

    def test_data_note_when_item_levels_are_unknown(self):
        # C15: a cache without ItemSparse RequiredLevel gives no item a level: item suggestions are skipped, and said
        from yap_forever.favor import FavorData
        line = ("- Item required levels are not in the game data: Merchant's Favor items are not suggested, only "
                "enchants.")
        self.assertIn(line, self.render(FavorData({1: 50}, {}, []), levels=False))
        self.assertNotIn(line, self.render(FavorData({1: 50}, {}, [])))


class AhSalesReportTests(unittest.TestCase):
    """#62: the supplier note and the buyout flag under "Crafted along the way", and the data note of the AH rule."""
    GEAR = 7777  # a made-up craft with a 1g vendor price

    def render(self, listings, made=10, market=None, **stock):
        import dataclasses
        gd = toy.gamedata([])
        gd.items[self.GEAR] = toy.item(self.GEAR, "Test Gear", sell=10000)
        st = dataclasses.replace(toy.stock(), **stock)
        m = market or toy.market({self.GEAR: listings})
        p = Plan(leftovers={self.GEAR: made}, final_skill={BS: 20})
        return render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, {BS: 20}), p, gd, m, st

    def crafted(self, text):
        return text[text.index("Crafted along the way"):text.index("## Excluded recipes")]

    def thin(self, p, gd, m, st):
        from yap_forever.compare import compare
        text = compare({"gold": p, "value": p}, gd, m, st)
        return next(line for line in text.splitlines() if line.startswith("| Thin markets"))

    def test_supplier_note_and_buyout(self):
        supplier = ("- 10 Test Gear: only 1 listed at 11g 57s 90c (vendor 1g 0s 0c): you may be the supplier; "
                    "list more than 5 if you think the market takes them.")
        text, *rest = self.render([(115790, 1)])  # one listed at 11x
        self.assertIn(supplier + " Check the AH before listing.\n", self.crafted(text))
        self.assertEqual(self.thin(*rest),
                         "| Thin markets | Test Gear (sells 10, 1 listed): check the AH before listing "
                         "| Test Gear (sells 10, 1 listed): check the AH before listing |")
        text, *rest = self.render([(31579, 3)])  # three listed at 3x: supplier only
        self.assertIn("- 10 Test Gear: only 3 listed at 3g 15s 79c (vendor 1g 0s 0c): you may be the supplier; "
                      "list more than 5 if you think the market takes them.\n", self.crafted(text))
        self.assertNotIn("check the ah", text.lower())
        self.assertNotIn("check the AH", self.thin(*rest))
        text, *rest = self.render([(115790, 6)])  # six listed: neither
        self.assertIn("- 10 Test Gear\n", self.crafted(text))
        self.assertNotIn("supplier", text)
        self.assertNotIn("check the AH", self.thin(*rest))

    def test_auctionator_single_count(self):
        # RF4: an import has one price and one count per item; the notes use that count, and it doesn't cap sales
        from yap_forever.planner import sale_value
        from yap_forever.prices import Market
        m = Market({self.GEAR: [(115790, 2)]})
        m.source, m.scan_day = "auctionator", "2026-11-20"
        text, p, gd, m, st = self.render(None, market=m)
        self.assertIn("- 10 Test Gear: only 2 listed at 11g 57s 90c (vendor 1g 0s 0c): you may be the supplier; "
                      "list more than 5 if you think the market takes them. Check the AH before listing.\n",
                      self.crafted(text))
        self.assertIn("Test Gear (sells 10, 2 listed): check the AH before listing", self.thin(p, gd, m, st))
        v = Valuer(m, gd, st)
        self.assertEqual(sale_value(v, gd, self.GEAR, 10), 5 * m.net_sell(self.GEAR) + 5 * 10000)

    def test_supplier_note_not_for_a_vendored_craft(self):
        text, *rest = self.render([(13685, 1)])  # one listed at 1.3x: sold to a vendor, no AH note
        self.assertIn("- 10 Test Gear\n", self.crafted(text))
        self.assertNotIn("supplier", text)
        self.assertEqual(self.thin(*rest), "| Thin markets | none | none |")  # C32: no AH sale, no thin AH market

    def test_buyout_flag_without_a_supplier_line(self):
        # C33: made no more than the sale limit, so no supplier line; the flag is on the Thin markets entry
        text, *rest = self.render([(115790, 1)], made=4)
        self.assertIn("- 4 Test Gear\n", self.crafted(text))
        self.assertNotIn("check the ah", text.lower())
        self.assertIn("Test Gear (sells 4, 1 listed): check the AH before listing", self.thin(*rest))
        _text, *rest = self.render([(115790, 2)], made=2)  # no more made than listed: the flag still has its entry
        self.assertIn("Test Gear (sells 2, 2 listed): check the AH before listing", self.thin(*rest))
        _text, *rest = self.render([(115790, 3)], made=2)  # 3 listed: no buyout risk, and no more made than listed
        self.assertEqual(self.thin(*rest), "| Thin markets | none | none |")

    def test_data_note_states_the_ah_rule(self):
        note = ("- AH resale of a crafted item counts at most 5 (quest items: `quest_item_sales`), and only when the AH "
                "pays, after its cut, at least {}× the vendor price and 1s more.")
        self.assertIn(note.format(2) + "\n", self.render([(115790, 1)])[0])
        self.assertIn(note.format(1.5) + "\n", self.render([(115790, 1)], ah_premium=1.5)[0])
        self.assertNotIn("gear counts at most 5", self.render([(115790, 1)])[0])

    def test_crafts_above_material_cost_follow_the_ah_rule(self):
        # the list prices a craft as the route rows do: at its AH net only when the AH pays well above a vendor
        gd = toy.gamedata([toy.recipe(1, "BS scarce", BS, {toy.COPPER_BAR: 1}, (self.GEAR, 1)),
                           toy.recipe(2, "BS dead", BS, {toy.COPPER_BAR: 1}, (7778, 1))])
        gd.items[self.GEAR] = toy.item(self.GEAR, "Test Gear", sell=10000)
        gd.items[7778] = toy.item(7778, "Dull Gear", sell=10000)
        st = toy.stock()
        m = toy.market({toy.COPPER_BAR: [(100, 1000)], self.GEAR: [(115790, 50)], 7778: [(13685, 50)]})
        p = Plan(learned=[1, 2], final_skill={BS: 20})
        text = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, {BS: 20})
        block = text[text.index("Crafts that sell above material cost"):text.index("## Excluded recipes")]
        self.assertIn("- BS scarce: +10g 99s 0c each", block)  # 11x: at its AH net, 110000c less 100c of material
        self.assertIn("- BS dead: +99s 0c each", block)  # 1.3x: at its vendor price, 10000c less 100c
        self.assertNotIn("+1g 29s 0c", block)  # not at its AH net of 13000c

    def test_thin_markets_skip_what_is_not_sold(self):
        # the same "sold" test as "Crafted along the way": a kept green and leftover dust are not sold
        from yap_forever.compare import compare
        gd, st = toy.gamedata([]), toy.stock()
        m = toy.market({toy.BELT: [(5000, 1)], toy.DUST: [(5000, 1)]})  # one listed each, well above vendor
        for p in (Plan(leftovers={toy.BELT: 10}, kept_greens={toy.BELT: 10}),
                  Plan(leftovers={toy.DUST: 10}, de_materials={toy.DUST: 10})):
            text = compare({"gold": p, "value": p}, gd, m, st)
            self.assertIn("| Thin markets | none | none |", text)
            report = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, {BS: 20})
            self.assertNotIn("supplier", report)
        sold = Plan(leftovers={toy.BELT: 10})
        self.assertIn("Runed Copper Belt (sells 10, 1 listed): check the AH before listing",
                      compare({"gold": sold, "value": sold}, gd, m, st))


def toy_turnin():
    from yap_forever.favor import Turnin
    return Turnin("Copper crate", {toy.COPPER_BAR: 2}, 5)

