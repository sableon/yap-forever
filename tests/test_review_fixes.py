"""Regression tests for the final review's Critical and Important findings."""
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path

from yap_forever import bnet
from tests import toy
from yap_forever.config import Credentials
from yap_forever.costmodel import Pools, Valuer
from yap_forever.planner import plan
from yap_forever.report import render, verdict
from tests.test_bnet import FakeOpener, FakeResp

BS, ENCH = 164, 333
BARS = {toy.COPPER_BAR: [(100, 100000)]}


def run(recipes, listings, stock=None):
    gd = toy.gamedata(recipes)
    st = stock or toy.stock()
    m = toy.market(listings)
    return plan(gd, Valuer(m, gd, st), st, toy.NO_FAVOR, caps={BS: 225, ENCH: 225}), gd, m, st


class CriticalTests(unittest.TestCase):
    def test_tool_and_reagent_share_thin_supply_no_crash(self):
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(2, "Ench dust", ENCH, {toy.DUST: 1}, tools=[373]),
              toy.recipe(5, "Runed Copper Rod", ENCH, {toy.ROD: 1, toy.DUST: 1}, (toy.ROD_TOOL, 1),
                         t=(1, 2, 2, 2), source="trainer")]
        p, *_ = run(rs, {**BARS, toy.DUST: [(300, 1)]})  # only one dust listed
        self.assertEqual(p.final_skill[BS], 225)

    def test_stall_lifted_when_other_profession_makes_materials(self):
        # Strange Dust only comes from disenchanting a BS green that needs BS 30.
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(3, "Belt", BS, {toy.COPPER_BAR: 1}, (toy.BELT, 1), req=30),
              toy.recipe(2, "Ench start", ENCH, {toy.ROD: 1}, t=(1, 10, 10, 10)),
              toy.recipe(4, "Ench dust", ENCH, {toy.DUST: 1}, req=10)]
        gd = toy.gamedata(rs)
        gd.items[toy.BELT].item_level = 18  # disenchantable from Enchanting 1
        st = toy.stock()
        p = plan(gd, Valuer(toy.market(BARS), gd, st), st, toy.NO_FAVOR, caps={BS: 225, ENCH: 225})
        self.assertGreater(p.final_skill[ENCH], 10)


class ImportantTests(unittest.TestCase):
    def test_intermediate_craft_charges_learning(self):
        # Ench recipe needs the rod tool; the rod recipe costs 5g to learn.
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(2, "Ench rod-needing", ENCH, {toy.COPPER_BAR: 1}, tools=[373]),
              toy.recipe(5, "Runed Copper Rod", ENCH, {toy.ROD: 1}, (toy.ROD_TOOL, 1),
                         t=(1, 1, 1, 1), fee=50000)]
        p, *_ = run(rs, BARS)
        self.assertIn(5, p.learned)
        self.assertTrue(any("Runed Copper Rod" in e and "5g" in e for e in p.events))

    def test_planned_recipe_not_listed_as_excluded(self):
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(3, "BS iron", BS, {toy.IRON_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})]
        # only a few iron bars: planned early, unpriceable later
        p, *_ = run(rs, {**BARS, toy.IRON_BAR: [(1, 5)]})
        self.assertIn(3, {s.spell_id for s in p.steps})
        self.assertNotIn(3, dict(p.skipped))

    def test_stale_token_replaced_after_401(self):
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d) / "token.json"
            cache.write_text(json.dumps({"access_token": "old", "expires_at": 10 ** 12}))
            calls = []

            def api(req):
                calls.append(req.get_header("Authorization"))
                if req.get_header("Authorization") == "Bearer old":
                    raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)
                return FakeResp(b'{"ok": 1}')
            op = FakeOpener(api=api)
            c = bnet.Client(Credentials("a", "b", "eu"), opener=op, now=lambda: 1000.0, token_cache=cache)
            self.assertEqual(c.get("/x").body, {"ok": 1})
            self.assertEqual(op.token_calls, 1)

    def test_made_materials_scored_at_value(self):
        v = Valuer(toy.market({toy.ESSENCE: [(3000, 10)]}), toy.gamedata([]), toy.stock())
        pools = Pools.from_stock(v.stock)
        pools.made[toy.ESSENCE] = 2
        c = v.take(toy.ESSENCE, 1, pools, skills={})
        self.assertEqual(c.economic, 0)
        self.assertEqual(c.score, 2850)

    def test_greens_held_when_de_is_only_source(self):
        rs = [toy.recipe(1, "Belt", BS, {toy.COPPER_BAR: 1}, (toy.BELT, 1)),
              toy.recipe(2, "Ench start", ENCH, {toy.ROD: 1}, t=(1, 30, 30, 30)),
              toy.recipe(4, "Ench dust", ENCH, {toy.DUST: 1}, req=25)]
        p, *_ = run(rs, BARS)  # no dust on the AH at all
        self.assertGreater(p.final_skill[ENCH], 30)

    def test_shopping_list_includes_scroll_tool_and_coal(self):
        rs = [toy.recipe(1, "BS hammer", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1), tools=[162]),
              toy.recipe(3, "Scrolled", BS, {}, (toy.STONE, 1), source="scroll", scroll=toy.SCROLL),
              toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})]
        p, *_ = run(rs, {**BARS, toy.SCROLL: [(500, 1)]})
        self.assertIn(toy.SCROLL, p.bought)
        p2, *_ = run([rs[0], rs[2]], BARS)  # only the hammer recipe for Blacksmithing
        self.assertIn(toy.HAMMER, p2.vendor_bought)

    def test_coal_recorded_when_farming_steel(self):
        gd = toy.gamedata([])
        gd.items[3859] = toy.item(3859, "Steel Bar", sell=100)
        gd.vendor_prices[3857] = 500
        v = Valuer(toy.market({}), gd, toy.stock(mining=171))
        pools = Pools.from_stock(v.stock)
        c = v.take(3859, 2, pools, skills={})
        self.assertEqual(c.cash, 1000)
        self.assertEqual(pools.vendor.get(3857), 2)

    def test_no_market_stock_flagged(self):
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})]
        p, gd, m, st = run(rs, BARS, stock=toy.stock({toy.VEST: 3}))
        text = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, {BS: 225, ENCH: 225})
        self.assertTrue("no market" in text and "Copper Chain Vest" in text)


if __name__ == "__main__":
    unittest.main()


class CraftedIntermediateReportTests(unittest.TestCase):
    def test_report_lists_crafted_intermediates(self):
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(6, "Make Copper Rod", BS, {toy.COPPER_BAR: 1}, (toy.ODD, 1), t=(1, 2, 2, 2),
                         source="starter"),
              toy.recipe(2, "Ench odd", ENCH, {toy.ODD: 1})]
        p, gd, m, st = run(rs, BARS)
        self.assertIn(toy.ODD, p.crafted)
        text = render(p, verdict(p, st), m, gd, st, toy.NO_FAVOR, {BS: 225, ENCH: 225})
        self.assertTrue("Crafted for reagents" in text)
