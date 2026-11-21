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

    def test_working_overtime_readings(self):
        t = (1, 70, 90, 110)  # skill 90 is yellow: base chance 0.5
        self.assertAlmostEqual(skillup_chance(90, t, 5, "relative"), 0.6)
        self.assertAlmostEqual(skillup_chance(90, t, 5, "points"), 0.7)
        self.assertAlmostEqual(skillup_chance(90, t, 1, "relative"), 0.52)
        self.assertAlmostEqual(skillup_chance(90, t, 1, "points"), 0.54)
        self.assertAlmostEqual(skillup_chance(90, t, 5), 0.6)  # relative is the default

    def test_working_overtime_caps_at_one(self):
        t = (1, 70, 90, 110)
        self.assertEqual(skillup_chance(50, t, 5, "relative"), 1.0)  # orange
        self.assertEqual(skillup_chance(50, t, 5, "points"), 1.0)
        self.assertEqual(skillup_chance(75, t, 5, "points"), 1.0)  # 0.875 + 0.2 caps
        self.assertEqual(skillup_chance(75, t, 5, "relative"), 1.0)  # 0.875 * 1.2 caps
        self.assertAlmostEqual(skillup_chance(80, t, 5, "relative"), 0.9)
        self.assertAlmostEqual(skillup_chance(100, t, 5, "relative"), 0.25 * 1.2)

    def test_working_overtime_grey_and_below_orange_stay_zero(self):
        t = (10, 70, 90, 110)
        for reading in ("relative", "points"):
            self.assertEqual(skillup_chance(110, t, 5, reading), 0.0)
            self.assertEqual(skillup_chance(200, t, 5, reading), 0.0)
            self.assertEqual(skillup_chance(5, t, 5, reading), 0.0)

    def test_unknown_reading_is_refused(self):
        with self.assertRaises(ValueError):
            skillup_chance(90, (1, 70, 90, 110), 5, "percent")
        with self.assertRaises(ValueError):
            skillup_chance(90, (1, 70, 90, 110), 0, "percent")

    def test_rank_zero_is_todays_chance(self):
        t = (1, 70, 90, 110)
        for s in range(0, 130):
            for reading in ("relative", "points"):
                self.assertEqual(skillup_chance(s, t, 0, reading), skillup_chance(s, t))


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

    def test_ah_value_not_capped_at_listing_depth(self):
        # #62: what is listed today no longer caps the AH sales; the sale limit does
        v = self.valuer({toy.VEST: [(1000, 3)]})
        self.assertEqual(v.output_value(toy.VEST, 3), 950)
        self.assertIn("ah", v.output_options(toy.VEST, 4))
        self.assertNotIn("ah", v.output_options(toy.VEST, 5))

    def test_quest_items_not_capped(self):
        v = self.valuer({toy.VEST: [(1000, 50)]}, quest=[toy.VEST])
        self.assertEqual(v.output_value(toy.VEST, 6), 950)

    def test_output_value_counts_disenchant(self):
        v = self.valuer({toy.DUST: [(300, 100)]})
        # Belt ilvl 22 armor: 3.75 dust at its AH buy price 300 (a material you'd otherwise buy)
        # + essence/shard at vendor (30, 50)
        self.assertEqual(v.output_value(toy.BELT, 10), int(3.75 * 300 + 0.225 * 30 + 0.1 * 50))

    def test_made_materials_scored_at_value(self):
        v = Valuer(toy.market({toy.ESSENCE: [(3000, 10)]}), toy.gamedata([]), toy.stock())
        pools = Pools.from_stock(v.stock)
        pools.made[toy.ESSENCE] = 2
        c = v.take(toy.ESSENCE, 1, pools, skills={})
        self.assertEqual(c.economic, 0)
        self.assertEqual(c.score, 2850)

    def test_coal_recorded_when_farming_steel(self):
        gd = toy.gamedata([])
        gd.items[3859] = toy.item(3859, "Steel Bar", sell=100)
        gd.vendor_prices[3857] = 500
        v = Valuer(toy.market({}), gd, toy.stock(mining=171))
        pools = Pools.from_stock(v.stock)
        c = v.take(3859, 2, pools, skills={})
        self.assertEqual(c.cash, 1000)
        self.assertEqual(pools.vendor.get(3857), 2)


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

    def test_sale_value_not_capped_by_listings(self):
        from yap_forever.planner import sale_value
        v = self.valuer(None, depth=3)
        # #62: no quest limit, and only 3 listed: all 20 on the AH (the listing count no longer caps it)
        self.assertEqual(sale_value(v, v.gd, toy.VEST, 20), 20 * 475)


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


class AhPremiumTests(unittest.TestCase):
    """#62: a craft counts as sold on the AH only when its net AH price (lowest listing less the 5% cut) is at
    least `ah_premium` (default 2) times its vendor price and 1s more; up to the sale limit, whatever is listed."""
    GEAR, NO_ROW = 7777, 4242  # a made-up craft with a 1g vendor price; an item the game data doesn't know

    def valuer(self, listings, sell=10000, quest=False, **stock):
        gd = toy.gamedata([], quest_items=[self.GEAR] if quest else ())
        gd.items[self.GEAR] = toy.item(self.GEAR, "Test Gear", sell=sell)
        st = dataclasses.replace(toy.stock(), **stock)
        return Valuer(toy.market({self.GEAR: listings} if listings else {}), gd, st)

    def test_dead_market_vendored(self):
        from yap_forever.planner import sale_value
        v = self.valuer([(13685, 50)])  # net 1.3g, vendor 1g
        self.assertEqual(v.market.net_sell(self.GEAR), 13000)
        self.assertIsNone(v.ah_price(self.GEAR))
        self.assertNotIn("ah", v.output_options(self.GEAR, 0))
        self.assertEqual(v.output_value(self.GEAR, 0), 10000)
        self.assertEqual(sale_value(v, v.gd, self.GEAR, 8), 8 * 10000)

    def test_premium_edges(self):
        cases = [(10000, 21053, 20000, True),  # vendor 1g, net 2g: 2x and 1g more
                 (10000, 21052, 19999, False),  # just under 2x
                 (50, 157, 149, False),  # vendor 50c, net 1s 49c: 3x, but only 99c more
                 (50, 158, 150, True)]  # net 1s 50c: 3x and 1s more
        for sell, listing, net, ah in cases:
            with self.subTest(sell=sell, listing=listing):
                v = self.valuer([(listing, 10)], sell=sell)
                self.assertEqual(v.market.net_sell(self.GEAR), net)
                self.assertEqual(v.ah_price(self.GEAR), net if ah else None)
                self.assertEqual("ah" in v.output_options(self.GEAR, 0), ah)

    def test_scarce_counted_to_limit(self):
        from yap_forever.planner import sale_value
        v = self.valuer([(115790, 1)])  # one listed, net 11g at a 1g vendor price
        net = v.market.net_sell(self.GEAR)
        self.assertEqual(net, 110000)
        self.assertIn("ah", v.output_options(self.GEAR, 4))  # the one listing doesn't cap it
        self.assertNotIn("ah", v.output_options(self.GEAR, 5))
        self.assertEqual(sale_value(v, v.gd, self.GEAR, 10), 5 * net + 5 * 10000)

    def test_quest_item_rule(self):
        from yap_forever.planner import sale_value
        below = self.valuer([(13685, 50)], quest=True)  # 1.3x: vendored like any craft
        self.assertNotIn("ah", below.output_options(self.GEAR, 0))
        self.assertEqual(sale_value(below, below.gd, self.GEAR, 20), 20 * 10000)
        above = self.valuer([(115790, 1)], quest=True)
        net = above.market.net_sell(self.GEAR)
        self.assertIn("ah", above.output_options(self.GEAR, 100))
        self.assertEqual(sale_value(above, above.gd, self.GEAR, 20), 20 * net)  # no quest limit: all of them
        three = self.valuer([(115790, 1)], quest=True, quest_item_sales=3)
        self.assertIn("ah", three.output_options(self.GEAR, 2))
        self.assertNotIn("ah", three.output_options(self.GEAR, 3))
        self.assertEqual(sale_value(three, three.gd, self.GEAR, 20), 3 * net + 17 * 10000)

    def test_owned_value_unchanged(self):
        # what the player holds or uses is still worth its AH net when that beats the vendor (not a sale)
        v = self.valuer([(13685, 50)])
        self.assertIsNone(v.ah_price(self.GEAR))
        self.assertEqual(v.owned_value(self.GEAR), 13000)
        self.assertEqual(v.material_value(self.GEAR), 13685)

    def test_vendor_price_zero(self):
        from yap_forever.planner import sale_value
        for item, setup in ((self.GEAR, "vendor 0"), (self.NO_ROW, "no item row")):
            with self.subTest(setup):
                def valuer(listing, item=item):
                    v = self.valuer(None, sell=0)
                    if item == self.NO_ROW:
                        self.assertNotIn(item, v.gd.items)
                    v.market = toy.market({item: [(listing, 3)]} if listing else {})
                    return v
                v = valuer(105)  # net 99c: 1s more than nothing is not reached
                self.assertEqual(v.market.net_sell(item), 99)
                self.assertIsNone(v.ah_price(item))
                self.assertEqual(v.output_options(item, 0), {"vendor": 0})
                v = valuer(106)  # net 1s
                self.assertEqual(v.ah_price(item), 100)
                self.assertEqual(v.output_options(item, 0)["ah"], 100)
                self.assertEqual(sale_value(v, v.gd, item, 7), 5 * 100)
                v = valuer(None)  # no listing: no AH price, no crash
                self.assertIsNone(v.ah_price(item))
                self.assertEqual(sale_value(v, v.gd, item, 7), 0)

    def test_ah_premium_setting_flips_a_case(self):
        default = self.valuer([(19685, 10)])  # net 1.87g at a 1g vendor price
        self.assertEqual(default.market.net_sell(self.GEAR), 18700)
        self.assertIsNone(default.ah_price(self.GEAR))
        self.assertEqual(self.valuer([(19685, 10)], ah_premium=1.5).ah_price(self.GEAR), 18700)

    def test_green_dead_market_offers_vendor_and_disenchant(self):
        # a green at a dead market is vendored or, with Enchanting planned, kept for disenchanting as before
        v = Valuer(toy.market({toy.BELT: [(137, 50)]}), toy.gamedata([]), toy.stock())  # net 1.3x vendor
        self.assertEqual(set(v.output_options(toy.BELT, 0)), {"vendor", "de"})
