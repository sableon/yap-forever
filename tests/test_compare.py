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

    def test_compare_counts_trips_for_trainer_trips(self):
        from yap_forever.compare import compare
        gd = toy.gamedata([toy.recipe(1, "BS late", BS, {toy.IRON_BAR: 1}, req=240, fee=100)])
        p = Plan(ranks=[(BS, 225, 300, 500)], learn_log=[(BS, 240, 1, "trainer")], final_skill={BS: 300})
        st = toy.stock(skills={BS: 225})

        def away(**kw):
            text = compare({"gold": p, "value": p}, gd, toy.market({}), st, **kw)
            return next(line for line in text.splitlines() if line.startswith("| Trips away"))
        self.assertEqual(away(), "| Trips away | 2 | 2 |")
        self.assertEqual(away(trainer_trips="as_needed"), "| Trips away | 2 | 2 |")
        self.assertEqual(away(trainer_trips="one_go"), "| Trips away | 1 | 1 |")

    def test_trips_away_counts_outside_home(self):
        # #98: the stops in the home capital are no trips away; each route counts with its own home
        from yap_forever.compare import compare
        from tests.test_trips import DARNASSUS, IRONFORGE, STAGE_CAPS, capital_route
        p, gd, start = capital_route()
        st = toy.stock(skills=start)

        def away(**kw):
            text = compare({"gold": p, "value": p}, gd, toy.market({}), st, **kw)
            return next(line for line in text.splitlines() if line.startswith("| Trips away"))
        self.assertEqual(away(), "| Trips away | 5 | 5 |")
        self.assertEqual(away(capitals=STAGE_CAPS, homes={"gold": IRONFORGE, "value": DARNASSUS}),
                         "| Trips away | 2 | 3 |")
        self.assertEqual(away(capitals=STAGE_CAPS, homes={"gold": IRONFORGE, "value": IRONFORGE},
                              trainer_trips="one_go"), "| Trips away | 1 | 1 |")
        self.assertEqual(away(capitals={}, homes={"gold": None, "value": None}), "| Trips away | 5 | 5 |")  # RF2


class TripTests(unittest.TestCase):
    def test_trips_kinds(self):
        from yap_forever.trips import trips
        gd = toy.gamedata([])
        p = Plan(ranks=[(BS, 60, 150, 450), (BS, 200, 225, 4500), (BS, 275, 300, 9000)],
                 learn_log=[(BS, 10, 1, "trainer"), (BS, 20, 2, "ah"), (BS, 30, 3, "vendor"),
                            (BS, 40, 4, "favor"), (BS, 50, 5, "quest")])
        self.assertEqual([(t.kind, t.skill) for t in trips(p, gd, {BS: 1})],
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

    def test_a_route_that_crafts_the_goal_wins(self):
        # final review, Important 1: a cheaper candidate that reaches the skill but not the goal craft is not chosen
        from yap_forever.compare import settle_routes
        from yap_forever.planner import Step
        goal = Step(BS, 20, 20, 7, "Goal", 1, 500, 500)
        cheap = Plan(cash_total=100, economic_total=100, final_skill={BS: 20})
        made = Plan(steps=[goal], cash_total=600, economic_total=600, final_skill={BS: 20})
        routes, same = settle_routes([cheap, made], {BS: 20}, {BS: 7})
        self.assertEqual((routes["gold"], routes["value"], same), (made, made, True))
        self.assertIs(settle_routes([cheap, made], {BS: 20})[0]["gold"], cheap)  # without a goal, as before
        self.assertIs(settle_routes([cheap], {BS: 20}, {BS: 7})[0]["gold"], cheap)  # none crafts it: reaching counts

    def test_settle_by_net_gold(self):
        # #97: least gold is the gold out of pocket less what vendors pay back for the crafts
        from yap_forever.compare import settle_routes
        a = Plan(cash_total=100000, economic_total=90000, final_skill={BS: 20})
        b = Plan(cash_total=110000, vendor_back=30000, economic_total=95000, final_skill={BS: 20})
        routes, same = settle_routes([a, b], {BS: 20})
        self.assertEqual((routes["gold"], routes["value"], same), (b, a, False))
        self.assertEqual(b.net_gold, 80000)

    def test_table_says_what_least_gold_counts(self):
        # #97 (C39): the least-gold column can show more gold out of pocket than the other one; the note says why
        from yap_forever.compare import compare
        note = ("Least gold is the gold out of pocket less what vendors pay back for the crafts. AH sales of crafts are "
                "not counted in choosing a route.")
        a = Plan(cash_total=110000, vendor_back=30000, economic_total=95000, final_skill={BS: 20})
        b = Plan(cash_total=100000, economic_total=90000, final_skill={BS: 20})
        for routes, same in (({"gold": a, "value": b}, False), ({"gold": b, "value": b}, True)):
            text = compare(routes, toy.gamedata([]), toy.market(), toy.stock(), same=same)
            table_end = text.index("| Thin markets")
            self.assertIn("\n\n" + note, text[table_end:])
            self.assertEqual(text.count(note), 1)

    def test_table_rows_and_note(self):
        # #97: what vendors pay back and what AH sales add on top get their own rows (— when there are none); total
        # value counts vendor sales only
        from yap_forever.compare import compare
        note = ("Least gold is the gold out of pocket less what vendors pay back for the crafts. AH sales of crafts are "
                "not counted in choosing a route.")
        a = Plan(cash_total=110000, vendor_back=30000, sale_proceeds=45000.2, economic_total=80000,
                 final_skill={BS: 20})
        b = Plan(cash_total=100000, vendor_back=12000, sale_proceeds=12000.3, economic_total=88000,
                 final_skill={BS: 20})
        text = compare({"gold": a, "value": b}, toy.gamedata([]), toy.market(), toy.stock())
        lines = text.splitlines()
        self.assertEqual(lines[2:6], ["| Gold out of pocket | 11.0g | 10.0g |",
                                      "| Back from a vendor | 3.0g | 1.2g |",
                                      "| Total value | 8.0g | 8.8g |",
                                      "| AH sales on top | 1.5g | — |"])
        self.assertEqual(lines[6], "| Reached | Blacksmithing 20 | Blacksmithing 20 |")
        self.assertEqual(text.count(note), 1)
        self.assertTrue(text.endswith("\n\n" + note), text[-200:])


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
    def test_skip_that_costs_nothing_says_nothing(self):
        # #90: a free skip that saves a visit is taken (plan.take_free_skips); one left on the route offers nothing
        from yap_forever.guide import _trip_line
        from yap_forever.trips import Trip
        t = Trip(30, BS, "vendor", "BS scroll", 30, 500)
        self.assertTrue(_trip_line(t, {30: -2003}).endswith("you can learn them."))
        self.assertNotIn("skip it", _trip_line(t, {30: 0.5}))
        self.assertIn("or skip it: +30s", _trip_line(t, {30: 3000}))
