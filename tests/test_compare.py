"""Two routes side by side, trips away from home, and the cost of skipping one."""
import unittest

from tests import toy
from yap_forever.costmodel import Valuer
from yap_forever.guide import gold
from yap_forever.planner import Plan, plan

BS = 164
BARS = {toy.COPPER_BAR: [(100, 100000)]}


def route(mode, recipes, listings, bank=None, caps=None):
    gd = toy.gamedata(recipes)
    st = toy.stock(bank)
    return gd, plan(gd, Valuer(toy.market(listings), gd, st, mode=mode), st, toy.NO_FAVOR, caps=caps or {BS: 20})


class CompareTests(unittest.TestCase):
    def test_compare_shows_both_routes(self):
        from yap_forever.compare import compare
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1))]
        gd, g = route("gold", rs, BARS)
        _, v = route("value", rs, BARS)
        text = compare({"gold": g, "value": v}, gd, toy.market(BARS), toy.stock())
        self.assertIn("| | Least gold | Least total value |", text)
        self.assertIn(f"| Gold out of pocket | {gold(g.cash_total)} | {gold(v.cash_total)} |", text)
        self.assertIn("| Reached | Blacksmithing 20 | Blacksmithing 20 |", text)

    def test_compare_flags_thin_market(self):
        from yap_forever.compare import compare
        gd = toy.gamedata([])
        p = Plan(bought={toy.IRON_BAR: 6})
        text = compare({"gold": p, "value": p}, gd, toy.market({toy.IRON_BAR: [(10, 10)]}), toy.stock())
        row = next(line for line in text.splitlines() if line.startswith("| Thin markets"))
        self.assertIn("Iron Bar", row)


class TripTests(unittest.TestCase):
    def test_trips_kinds(self):
        from yap_forever.trips import trips
        gd = toy.gamedata([])
        p = Plan(ranks=[(BS, 60, 150, 450), (BS, 200, 225, 4500), (BS, 275, 300, 9000)],
                 learn_log=[(BS, 10, 1, "trainer"), (BS, 20, 2, "ah"), (BS, 30, 3, "vendor"),
                            (BS, 40, 4, "favor"), (BS, 50, 5, "quest")])
        self.assertEqual([(t.kind, t.skill) for t in trips(p, gd)],
                         [("vendor", 30), ("favor", 40), ("rank", 200), ("rank", 275)])

    def test_planner_logs_learning_and_ranks(self):
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(30, "BS scroll", BS, {toy.IRON_BAR: 1}, (toy.STONE, 1), source="scroll", scroll=toy.SCROLL)]
        gd = toy.gamedata(rs)
        gd.vendor_prices[toy.SCROLL] = 500
        st = toy.stock()
        p = plan(gd, Valuer(toy.market({**BARS, toy.IRON_BAR: [(10, 100000)]}), gd, st), st, toy.NO_FAVOR,
                 caps={BS: 80})
        self.assertIn((BS, 1, 30, "vendor"), p.learn_log)
        self.assertEqual([(prof, cap) for prof, _s, cap, _f in p.ranks], [(BS, 150)])

    def test_trip_alternative_cost(self):
        from yap_forever.plan import PlanInputs, plan_route
        from yap_forever.trips import trip_alternatives
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(30, "BS scroll", BS, {toy.IRON_BAR: 1}, (toy.STONE, 1), source="scroll", scroll=toy.SCROLL)]
        gd = toy.gamedata(rs)
        gd.vendor_prices[toy.SCROLL] = 500
        st, m = toy.stock(), toy.market({**BARS, toy.IRON_BAR: [(10, 100000)]})
        inputs = PlanInputs(gd=gd, market=m, stock=st, favor=toy.NO_FAVOR, caps={BS: 40}, craft_once={},
                            quests={})
        base = plan_route(inputs, "gold")
        skip = plan_route(inputs, "gold", exclude=frozenset({30}))
        alts = trip_alternatives(base, inputs, "gold")
        self.assertEqual(alts, {30: skip.cash_total - base.cash_total})
        self.assertGreater(alts[30], 0)


if __name__ == "__main__":
    unittest.main()


class SettleRoutesTests(unittest.TestCase):
    """Among candidates that reach the targets: least gold is the lowest gold, least value the lowest value."""

    def test_least_gold_never_costs_more_gold(self):
        from yap_forever.compare import compare, settle_routes
        a = Plan(cash_total=500, economic_total=900, final_skill={BS: 20})
        b = Plan(cash_total=400, economic_total=700, final_skill={BS: 20})
        routes, same = settle_routes([a, b], {BS: 20})
        self.assertEqual((routes["gold"], routes["value"], same), (b, b, True))
        text = compare(routes, toy.gamedata([]), toy.market(), toy.stock(), same=same)
        self.assertIn("The least-total-value route also spends the least gold", text)

    def test_two_routes_when_they_differ(self):
        from yap_forever.compare import settle_routes
        a = Plan(cash_total=300, economic_total=900, final_skill={BS: 20})
        b = Plan(cash_total=400, economic_total=700, final_skill={BS: 20})
        routes, same = settle_routes([a, b], {BS: 20})
        self.assertEqual((routes["gold"], routes["value"], same), (a, b, False))

    def test_route_that_stops_short_is_not_chosen(self):
        from yap_forever.compare import settle_routes
        short = Plan(cash_total=10, economic_total=10, final_skill={BS: 12})
        full = Plan(cash_total=400, economic_total=700, final_skill={BS: 20})
        routes, _ = settle_routes([short, full], {BS: 20})
        self.assertEqual((routes["gold"], routes["value"]), (full, full))

    def test_all_short_keeps_the_furthest(self):
        from yap_forever.compare import settle_routes
        a = Plan(cash_total=10, economic_total=10, final_skill={BS: 12})
        b = Plan(cash_total=40, economic_total=70, final_skill={BS: 15})
        routes, _ = settle_routes([a, b], {BS: 20})
        self.assertEqual(routes["gold"], b)


class OneTimeInFullTests(unittest.TestCase):
    def test_gold_variant_charges_patterns_in_full(self):
        # The pattern's 15s looks cheap spread over 59 points, but a free recipe takes over at 10.
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(30, "BS scroll", BS, {toy.IRON_BAR: 1}, (toy.STONE, 1), source="scroll", scroll=toy.SCROLL),
              toy.recipe(31, "BS later", BS, {toy.DUST: 1}, (toy.STONE, 1), req=10)]
        gd = toy.gamedata(rs)
        gd.vendor_prices[toy.SCROLL] = 1500
        st = toy.stock({toy.IRON_BAR: 100, toy.DUST: 100})
        m = toy.market({toy.COPPER_BAR: [(30, 100000)]})
        spread = plan(gd, Valuer(m, gd, st, mode="gold"), st, toy.NO_FAVOR, caps={BS: 60})
        full = plan(gd, Valuer(m, gd, st, mode="gold"), st, toy.NO_FAVOR, caps={BS: 60}, one_time_in_full=True)
        self.assertIn(30, {s.spell_id for s in spread.steps})
        self.assertNotIn(30, {s.spell_id for s in full.steps})
        self.assertLess(full.cash_total, spread.cash_total)




class GoalTripTests(unittest.TestCase):
    def test_goal_recipe_trip_has_no_skip_alternative(self):
        from yap_forever.plan import PlanInputs, plan_route
        from yap_forever.trips import trip_alternatives
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(30, "BS scroll", BS, {toy.IRON_BAR: 1}, (toy.STONE, 1), req=20,
                         source="scroll", scroll=toy.SCROLL)]
        gd = toy.gamedata(rs)
        gd.vendor_prices[toy.SCROLL] = 500
        st, m = toy.stock(), toy.market({**BARS, toy.IRON_BAR: [(10, 100000)]})
        inputs = PlanInputs(gd=gd, market=m, stock=st, favor=toy.NO_FAVOR, caps={BS: 20}, craft_once={BS: 30},
                            quests={})
        self.assertEqual(trip_alternatives(plan_route(inputs, "gold"), inputs, "gold"), {})


class TripLineTests(unittest.TestCase):
    def test_skip_that_costs_nothing_says_so(self):
        from yap_forever.guide import _trip_line
        from yap_forever.trips import Trip
        t = Trip(30, BS, "vendor", "BS scroll", 30, 500)
        self.assertIn("or skip it at no extra cost", _trip_line(t, {30: -2003}))
        self.assertIn("or skip it: +30s", _trip_line(t, {30: 3000}))
