import dataclasses
import unittest

from tests import toy
from yap_forever.costmodel import Pools, Valuer, skillup_chance


class ChanceTests(unittest.TestCase):
    def test_chance_values(self):
        t = (1, 70, 90, 110)
        self.assertEqual(skillup_chance(50, t), 1.0)
        self.assertEqual(skillup_chance(70, t), 1.0)
        self.assertEqual(skillup_chance(90, t), 0.5)
        self.assertEqual(skillup_chance(100, t), 0.25)
        self.assertEqual(skillup_chance(110, t), 0.0)
        self.assertEqual(skillup_chance(0, t), 0.0)


class ValuerTests(unittest.TestCase):
    def valuer(self, listings=None, stock=None, quest=()):
        gd = toy.gamedata([], quest_items=quest)
        return Valuer(toy.market(listings), gd, stock or toy.stock())

    def test_stock_used_first_cash_zero(self):
        v = self.valuer({toy.COPPER_BAR: [(100, 50)]}, toy.stock({toy.COPPER_BAR: 10}))
        pools = Pools.from_stock(v.stock)
        c = v.take(toy.COPPER_BAR, 6, pools, skills={})
        self.assertEqual((c.cash, c.economic), (0, 6 * 95))
        self.assertEqual(pools.stock[toy.COPPER_BAR], 4)

    def test_buys_after_stock_runs_out(self):
        v = self.valuer({toy.COPPER_BAR: [(100, 50)]}, toy.stock({toy.COPPER_BAR: 2}))
        pools = Pools.from_stock(v.stock)
        c = v.take(toy.COPPER_BAR, 5, pools, skills={})
        self.assertEqual(c.cash, 300)
        self.assertEqual(c.economic, 2 * 95 + 300)
        self.assertEqual(pools.bought[toy.COPPER_BAR], 3)

    def test_marginal_buy_walks_book(self):
        v = self.valuer({toy.COPPER_BAR: [(10, 2), (50, 5)]})
        pools = Pools.from_stock(v.stock)
        self.assertEqual(v.take(toy.COPPER_BAR, 2, pools, skills={}).cash, 20)
        self.assertEqual(v.take(toy.COPPER_BAR, 1, pools, skills={}).cash, 50)

    def test_vendor_reagent_uses_vendor_price(self):
        v = self.valuer()
        c = v.take(toy.ROD, 3, Pools.from_stock(v.stock), skills={})
        self.assertEqual(c.cash, 372)

    def test_unpriceable_returns_none(self):
        v = self.valuer()
        self.assertIsNone(v.take(toy.ODD, 1, Pools.from_stock(v.stock), skills={}))

    def test_peek_does_not_change_pools(self):
        v = self.valuer({toy.COPPER_BAR: [(100, 50)]}, toy.stock({toy.COPPER_BAR: 10}))
        pools = Pools.from_stock(v.stock)
        v.take(toy.COPPER_BAR, 6, pools, skills={}, commit=False)
        self.assertEqual(pools.stock[toy.COPPER_BAR], 10)

    def test_stock_no_market_uses_vendor_sell(self):
        v = self.valuer(stock=toy.stock({toy.VEST: 2}))
        c = v.take(toy.VEST, 2, Pools.from_stock(v.stock), skills={})
        self.assertEqual((c.cash, c.economic), (0, 40))

    def test_farmable_bar_cash_zero(self):
        v = self.valuer({toy.IRON_BAR: [(60, 100)]}, toy.stock(mining=171))
        pools = Pools.from_stock(v.stock)
        c = v.take(toy.IRON_BAR, 3, pools, skills={})
        self.assertEqual((c.cash, c.economic), (0, 3 * 57))
        self.assertEqual(pools.farmed[toy.IRON_BAR], 3)

    def test_unfarmable_bar_bought(self):
        v = self.valuer({toy.IRON_BAR: [(60, 100)]}, toy.stock(mining=100))
        c = v.take(toy.IRON_BAR, 3, Pools.from_stock(v.stock), skills={})
        self.assertEqual(c.cash, 180)

    def test_mining_goal_makes_bar_farmable(self):
        st = dataclasses.replace(toy.stock(mining=100), mining_goal=171)
        v = self.valuer({toy.IRON_BAR: [(60, 100)]}, st)
        c = v.take(toy.IRON_BAR, 3, Pools.from_stock(v.stock), skills={})
        self.assertEqual(c.cash, 0)

    def test_made_items_cost_nothing(self):
        v = self.valuer({toy.COPPER_BAR: [(100, 50)]})
        pools = Pools.from_stock(v.stock)
        pools.made[toy.COPPER_BAR] = 4
        self.assertEqual(v.take(toy.COPPER_BAR, 4, pools, skills={}).economic, 0)

    def test_ah_value_capped_at_5_units(self):
        v = self.valuer({toy.VEST: [(1000, 50)]})
        self.assertEqual(v.output_value(toy.VEST, 0), 950)
        self.assertEqual(v.output_value(toy.VEST, 5), 20)  # vendor price after 5

    def test_ah_value_capped_at_listing_depth(self):
        v = self.valuer({toy.VEST: [(1000, 3)]})
        self.assertEqual(v.output_value(toy.VEST, 2), 950)
        self.assertEqual(v.output_value(toy.VEST, 3), 20)  # only 3 are listed: the rest go to a vendor
        self.assertNotIn("ah", v.output_options(toy.VEST, 3))

    def test_quest_items_not_capped(self):
        v = self.valuer({toy.VEST: [(1000, 50)]}, quest=[toy.VEST])
        self.assertEqual(v.output_value(toy.VEST, 6), 950)

    def test_output_value_counts_disenchant(self):
        v = self.valuer({toy.DUST: [(300, 100)]})
        # Belt ilvl 22 armor: 3.75 dust at its AH buy price 300 (a material you'd otherwise buy)
        # + essence/shard at vendor (30, 50)
        self.assertEqual(v.output_value(toy.BELT, 10), int(3.75 * 300 + 0.225 * 30 + 0.1 * 50))


if __name__ == "__main__":
    unittest.main()


class StoneTests(unittest.TestCase):
    COARSE, HEAVY = 2836, 2838

    def test_stone_farmable_with_mining(self):
        gd = toy.gamedata([])
        v = Valuer(toy.market({self.COARSE: [(50, 100)]}), gd, toy.stock(mining=100))
        self.assertTrue(v.farmable(self.COARSE))
        self.assertFalse(v.farmable(self.HEAVY))
        pools = Pools.from_stock(v.stock)
        c = v.take(self.COARSE, 4, pools, skills={})
        self.assertEqual(c.cash, 0)
        self.assertEqual(pools.farmed[self.COARSE], 4)

    def test_farmed_stone_listed_as_mined(self):
        from yap_forever.costmodel import bars_to_ore
        self.assertEqual(bars_to_ore({self.COARSE: 10, toy.COPPER_BAR: 2}), {self.COARSE: 10, 2770: 2})


class QuestSalesLimitTests(unittest.TestCase):
    def valuer(self, limit, depth=3):
        gd = toy.gamedata([], quest_items=[toy.VEST])
        st = dataclasses.replace(toy.stock(), quest_item_sales=limit)
        return Valuer(toy.market({toy.VEST: [(500, depth)]}), gd, st)

    def test_quest_item_limit(self):
        v = self.valuer(10, depth=30)
        self.assertIn("ah", v.output_options(toy.VEST, 9))
        self.assertNotIn("ah", v.output_options(toy.VEST, 10))

    def test_no_limit_by_default(self):
        self.assertIn("ah", self.valuer(None, depth=1000).output_options(toy.VEST, 500))

    def test_sale_value_uses_limit(self):
        from yap_forever.planner import sale_value
        v = self.valuer(10, depth=30)
        # 10 on the AH at 475 net, 10 to a vendor at 20
        self.assertEqual(sale_value(v, v.gd, toy.VEST, 20), 10 * 475 + 10 * 20)

    def test_sale_value_capped_by_listings(self):
        from yap_forever.planner import sale_value
        v = self.valuer(None, depth=3)
        # no quest limit, but only 3 listed: 3 on the AH, 17 to a vendor
        self.assertEqual(sale_value(v, v.gd, toy.VEST, 20), 3 * 475 + 17 * 20)


class SmeltFromStockTests(unittest.TestCase):
    """Bars that would be farmed come first from ore, coal and bars already in the bank."""
    COPPER_BAR, TIN_BAR, BRONZE_BAR, IRON_ORE, IRON_BAR, COAL, STEEL_BAR = 2840, 3576, 2841, 2772, 3575, 3857, 3859

    def take(self, item, qty, stock_items, mining):
        gd = toy.gamedata([])
        st = toy.stock(stock_items, mining=mining)
        v = Valuer(toy.market(), gd, st)
        pools = Pools.from_stock(st)
        return v.take(item, qty, pools, skills={}), pools

    def test_bronze_smelted_from_banked_copper_and_tin(self):
        c, pools = self.take(self.BRONZE_BAR, 10, {self.COPPER_BAR: 40, self.TIN_BAR: 40}, mining=100)
        self.assertEqual(c.cash, 0)
        self.assertEqual((pools.stock[self.COPPER_BAR], pools.stock[self.TIN_BAR]), (35, 35))
        self.assertEqual(pools.farmed, {})

    def test_iron_smelted_from_banked_ore(self):
        c, pools = self.take(self.IRON_BAR, 5, {self.IRON_ORE: 100}, mining=125)
        self.assertEqual(pools.stock[self.IRON_ORE], 95)
        self.assertEqual(pools.farmed, {})

    def test_banked_coal_used_before_vendor(self):
        c, pools = self.take(self.STEEL_BAR, 2, {self.COAL: 20}, mining=165)
        self.assertEqual(pools.stock[self.COAL], 18)
        self.assertEqual(pools.vendor.get(self.COAL, 0), 0)
        self.assertEqual(pools.farmed.get(self.IRON_BAR, 0) + pools.farmed.get(self.STEEL_BAR, 0) > 0, True)

    def test_banked_coal_counts_at_its_value(self):
        from yap_forever.costmodel import Valuer as V
        gd = toy.gamedata([])
        st = toy.stock({self.COAL: 20, self.IRON_ORE: 20}, mining=165)
        m = toy.market({self.COAL: [(100, 50)]})  # sells for 95 after the AH cut
        v = V(m, gd, st)
        c = v.take(self.STEEL_BAR, 2, Pools.from_stock(st), skills={})
        self.assertEqual(c.cash, 0)
        self.assertGreaterEqual(c.economic, 2 * 95)

    def test_partial_bank_then_farm(self):
        c, pools = self.take(self.IRON_BAR, 5, {self.IRON_ORE: 3}, mining=125)
        self.assertEqual(pools.stock[self.IRON_ORE], 0)
        self.assertAlmostEqual(pools.farmed[self.IRON_BAR], 2)


class CraftOrBuyTests(unittest.TestCase):
    """Craft an intermediate only when it beats buying by a margin: 10% at skill 1, 5% at 300."""

    def take_vest(self, bar_price, skill):
        gd = toy.gamedata([toy.recipe(20, "Vest", 164, {toy.COPPER_BAR: 1}, (toy.VEST, 1), source="starter")])
        v = Valuer(toy.market({toy.VEST: [(1000, 100)], toy.COPPER_BAR: [(bar_price, 100)]}), gd, toy.stock())
        pools = Pools.from_stock(v.stock)
        v.take(toy.VEST, 1, pools, skills={164: skill})
        return "craft" if pools.crafted.get(toy.VEST) else "buy" if pools.bought.get(toy.VEST) else None

    def test_craft_margin_falls_with_skill(self):
        from yap_forever.costmodel import craft_margin
        self.assertAlmostEqual(craft_margin(1), 0.90)
        self.assertAlmostEqual(craft_margin(300), 0.95)
        self.assertAlmostEqual(craft_margin(0), 0.90)
        self.assertAlmostEqual(craft_margin(400), 0.95)
        self.assertLess(craft_margin(100), craft_margin(200))

    def test_low_skill_needs_10pct(self):
        self.assertEqual(self.take_vest(880, 1), "craft")
        self.assertEqual(self.take_vest(920, 1), "buy")

    def test_high_skill_needs_5pct(self):
        self.assertEqual(self.take_vest(940, 300), "craft")
        self.assertEqual(self.take_vest(960, 300), "buy")
