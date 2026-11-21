import unittest

from tests import toy
from yap_forever import budget
from yap_forever.compare import settle_routes
from yap_forever.config import Budget
from yap_forever.gamedata import Rank
from yap_forever.guide import gold
from yap_forever.plan import PlanInputs, candidates
from yap_forever.shopping import gold_to_bring, render_shopping

BS, ENCH = 164, 333
G = 10000  # copper in a gold
# Every point costs one bar or one shard at 1s (orange crafts: no buffer). With the toy ranks, Blacksmithing
# from 1 costs 74s to 75, 1g 53s 50c to 150 (the 4s 50c rank included) and 2g 73s 50c to 225 (45s rank).
TO_75, TO_150, TO_225 = 7400, 15350, 27350


def inputs(recipes, caps, skills=None, listings=None, level=60, ranks=None):
    gd = toy.gamedata(recipes)
    for prof, extra in (ranks or {}).items():
        gd.trainer_ranks[prof] = gd.trainer_ranks[prof] + extra
    st = toy.stock(skills=skills, level=level)
    market = toy.market(listings or {toy.COPPER_BAR: [(100, 100000)], toy.SHARD: [(100, 100000)]})
    return PlanInputs(gd=gd, market=market, stock=st, favor=toy.NO_FAVOR, caps=caps, craft_once={}, quests={})


def gold_of(i):
    return lambda p: gold_to_bring(p, i.gd, i.market, i.stock)


def bs_only(t=(1, 300, 300, 300)):
    return [toy.recipe(1, "BS bar", BS, {toy.COPPER_BAR: 1}, t=t)]


def both():
    return [toy.recipe(1, "BS bar", BS, {toy.COPPER_BAR: 1}), toy.recipe(2, "Ench shard", ENCH, {toy.SHARD: 1})]


def route(i, caps, mode="gold"):
    import dataclasses
    sub = dataclasses.replace(i, caps=caps)
    return settle_routes(candidates(sub), caps)[0][mode]


def cut(i, gold, order=None, mode="gold"):
    return budget.cut(i, mode, Budget(gold, order), gold_of(i))


class StopsTests(unittest.TestCase):
    def test_stops_are_the_rank_caps_and_the_target(self):
        self.assertEqual(budget.STOPS, (75, 150, 225, 300))
        self.assertEqual(budget.stops_for(1, 225), [75, 150, 225])
        self.assertEqual(budget.stops_for(190, 300), [225, 300])
        self.assertEqual(budget.stops_for(150, 200), [200])
        self.assertEqual(budget.stops_for(225, 225), [])


class CutTests(unittest.TestCase):
    def test_gold_to_bring_is_the_shopping_lists_total(self):
        i = inputs(bs_only((1, 1, 1, 400)), {BS: 150})  # yellow: the buffer counts
        p = route(i, i.caps)
        lines, _ = render_shopping(p, i.gd, i.market, i.stock)
        self.assertIn(f"**Gold to bring: {gold(gold_to_bring(p, i.gd, i.market, i.stock))}**", lines)
        self.assertGreater(gold_to_bring(p, i.gd, i.market, i.stock), p.cash_total)
        self.assertIn("| Trainer: ranks and recipes | | trainer | 4s |", lines)  # the rows read as before

    def test_budget_below_first_stop(self):  # RF1
        i = inputs(bs_only(), {BS: 225})
        c = cut(i, 0.5)
        self.assertEqual(c.caps, {BS: 1})
        self.assertEqual(c.plan.steps, [])
        self.assertEqual(c.spent, 0)
        self.assertEqual(c.next_stop, {BS: (75, TO_75)})
        self.assertFalse(any("already at" in e for e in c.plan.events))  # the target is not reached

    def test_budget_between_stops(self):
        i = inputs(bs_only(), {BS: 225})
        c = cut(i, 1.6)
        self.assertEqual(c.caps, {BS: 150})
        self.assertEqual(c.plan.final_skill, {BS: 150})
        self.assertEqual(c.spent, TO_150)
        self.assertLessEqual(c.spent, 1.6 * G)
        self.assertEqual(c.next_stop, {BS: (225, TO_225 - TO_150)})
        self.assertGreater(c.spent + c.next_stop[BS][1], 1.6 * G)

    def test_budget_above_route(self):
        i = inputs(bs_only(), {BS: 225})
        c = cut(i, 3)
        self.assertEqual(c.caps, {BS: 225})
        self.assertEqual(c.next_stop, {})
        self.assertEqual(c.plan.final_skill, {BS: 225})
        self.assertEqual(c.spent, TO_225)

    def test_budget_checked_against_gold_to_bring(self):
        i = inputs(bs_only((1, 1, 1, 400)), {BS: 150})  # yellow crafts: the shopping list buys 15% more
        r150, r75 = route(i, {BS: 150}), route(i, {BS: 75})
        limit = r150.cash_total / G  # the route's cash fits ...
        self.assertGreater(gold_to_bring(r150, i.gd, i.market, i.stock), r150.cash_total)  # ... its shopping doesn't
        self.assertLessEqual(gold_to_bring(r75, i.gd, i.market, i.stock), r150.cash_total)
        c = cut(i, limit)
        self.assertEqual(c.caps, {BS: 75})
        self.assertLessEqual(c.spent, r150.cash_total)

    def test_even_fallback_gives_gold_to_other(self):
        # A (Blacksmithing) at 200 needs 10g to 225, B (Enchanting) at 210 needs 3g; with 5g, B reaches 225
        rs = [toy.recipe(1, "BS iron", BS, {toy.IRON_BAR: 1}), toy.recipe(2, "Ench shard", ENCH, {toy.SHARD: 1})]
        i = inputs(rs, {BS: 225, ENCH: 225}, skills={BS: 200, ENCH: 210},
                   listings={toy.IRON_BAR: [(4000, 1000)], toy.SHARD: [(2000, 1000)]})
        c = cut(i, 5)
        self.assertEqual(c.caps, {BS: 200, ENCH: 225})
        self.assertEqual(c.spent, 3 * G)
        self.assertEqual(c.next_stop, {BS: (225, 10 * G)})
        self.assertEqual({s.profession for s in c.plan.steps}, {ENCH})

    def test_even_fallback_repeats_while_the_other_fits(self):
        # A (Blacksmithing) at 100 needs 10g to 150; B (Enchanting) at 120 needs 3s to 150 and 1g 55s to 225.
        # A is lower, but its stop never fits: B takes both of its stops, so no next stop that fits is left.
        rs = [toy.recipe(1, "BS iron", BS, {toy.IRON_BAR: 1}), toy.recipe(2, "Ench shard", ENCH, {toy.SHARD: 1})]
        i = inputs(rs, {BS: 150, ENCH: 225}, skills={BS: 100, ENCH: 120},
                   listings={toy.IRON_BAR: [(2000, 1000)], toy.SHARD: [(100, 1000)]})
        c = cut(i, 5)
        self.assertEqual(c.caps, {BS: 100, ENCH: 225})
        self.assertEqual(c.spent, 15500)
        self.assertEqual(c.next_stop, {BS: (150, 10 * G)})

    def test_stalled_profession_gets_no_gold(self):  # RF4
        # Enchanting at 225 needs the next rank, which needs character level 35; the character is 30
        i = inputs(both(), {BS: 225, ENCH: 300}, skills={ENCH: 225}, level=30,
                   ranks={ENCH: [Rank(300, 10000, 200, 35)]})
        c = cut(i, 1.6)
        self.assertEqual(c.caps, {BS: 150, ENCH: 225})
        self.assertIn("next rank needs character level 35", c.stalled[ENCH])
        self.assertNotIn(ENCH, c.next_stop)
        self.assertEqual(c.spent, TO_150)  # all of it to Blacksmithing
        self.assertIn("next rank needs character level 35", c.plan.stall_reasons[ENCH])  # the guide says why

    def test_one_at_a_time(self):
        i = inputs(both(), {BS: 150, ENCH: 150})
        c = cut(i, 2, order=(BS, ENCH))  # Blacksmithing to 150 first; Enchanting's first stop doesn't fit after it
        self.assertEqual(c.caps, {BS: 150, ENCH: 1})
        self.assertEqual(c.next_stop, {ENCH: (75, TO_75)})
        more = cut(i, 2.3, order=(BS, ENCH))  # what is left goes to Enchanting
        self.assertEqual(more.caps, {BS: 150, ENCH: 75})
        crafts = [s.profession for s in more.plan.steps]
        self.assertEqual(crafts, sorted(crafts))  # every Blacksmithing step first (164 < 333)
        even = cut(inputs(both(), {BS: 150, ENCH: 150}), 2)  # side by side, the same gold stops both at 75
        self.assertEqual(even.caps, {BS: 75, ENCH: 75})

    def test_budget_equal_to_a_stops_cost_reaches_it(self):
        i = inputs(bs_only(), {BS: 225}, listings={toy.COPPER_BAR: [(101, 100000)]})
        c = cut(i, 0.7474)  # exactly the 74 bars to 75; 0.7474 * 10000 is 7473.999... in floating point
        self.assertEqual((c.caps, c.spent), ({BS: 75}, 7474))

    def test_partway_stall_says_why_on_the_next_stop(self):
        i = inputs(bs_only((1, 300, 300, 100)), {BS: 225})  # grey at 100: the route stops at 100
        c = cut(i, 0.8)
        self.assertEqual(c.caps, {BS: 75})
        self.assertEqual(c.next_stop, {BS: (100, 450 + 2500)})
        self.assertIn(f"The next stop, Blacksmithing 100, costs about {gold(2950)} more; the route stops there: "
                      "no usable recipe at 100.", budget.lines(c, Budget(0.8)))
        self.assertIn("The next stop, Blacksmithing 75, costs about", " ".join(budget.lines(cut(i, 0.5), Budget(0.5))))
        self.assertNotIn("stops there", " ".join(budget.lines(cut(i, 0.5), Budget(0.5))))

    def test_adopted_route_keeps_the_cut(self):
        # #90: a route planned without a free trip replaces the cut's route and gold; a profession the budget holds
        # at its start gets no "already at" event back from the new plan (cut drops it), one at its target keeps it
        from yap_forever.planner import Plan, reached_lines
        old = Plan(events=[])
        c = budget.BudgetCut({BS: 225, ENCH: 1}, old, 500, {ENCH: (75, 900)}, {}, {BS: 225, ENCH: 1}, {BS: 1, ENCH: 1})
        new = Plan(events=["Enchanting already at 1"])
        got = budget.adopt(c, new, 400)
        self.assertEqual(new.events, ["Enchanting already at 1"])  # the plan given (maybe cached, shared) is unchanged
        self.assertEqual(got.plan.cash_total, new.cash_total)
        self.assertEqual((got.spent, got.caps), (400, c.caps))
        self.assertEqual(got.next_stop, {ENCH: (75, 1000)})  # the next stop's route costs what it did: 100c more on top
        self.assertEqual(reached_lines(got.plan), [])
        c.next_stop = {}  # Enchanting's target is 1: reached, and said
        kept = Plan(events=["Enchanting already at 1"])
        self.assertIs(budget.adopt(c, kept, 400).plan, kept)  # nothing to drop: the same plan
        self.assertEqual(reached_lines(kept), ["Enchanting is already at 1: nothing to plan."])


class RenderTests(unittest.TestCase):
    """The guide and the report of a cut route: what the budget reaches and why."""
    def render(self, i, c, goal):
        from yap_forever.guide import render_guide
        from yap_forever.report import render, verdict
        lines = budget.lines(c, goal)
        guide = render_guide(c.plan, i.gd, i.market, i.stock, c.planned_caps, budget_lines=lines,
                             nothing_in_budget=c.below_first_stop)
        report = render(c.plan, verdict(c.plan, i.stock), i.market, i.gd, i.stock, i.favor, c.planned_caps,
                        budget_lines=lines, goal=goal, nothing_in_budget=c.below_first_stop)
        return guide, report

    def test_budget_below_first_stop_says_what_it_costs(self):  # RF1
        i = inputs(bs_only(), {BS: 225})
        goal = Budget(0.5)
        guide, report = self.render(i, budget.cut(i, "gold", goal, gold_of(i)), goal)
        for text in (guide, report):
            self.assertIn("0.5g doesn't reach the first stop: nothing is planned yet.", text)
            self.assertIn(f"The next stop, Blacksmithing 75, costs about {gold(TO_75)} more.", text)
            self.assertNotIn("already at", text)
            route = text[text.index("## Route"):]
            self.assertTrue(route.split("\n", 2)[2].startswith("Nothing to craft within this budget."), route[:80])
        self.assertIn("**Gold to bring: 0c**", guide)
        verdict_part = report[report.index("## Verdict"):report.index("## Route")]
        self.assertNotIn("Ready to level", verdict_part)
        self.assertNotIn("Planned to", verdict_part)

    def test_stalled_profession_says_why(self):  # RF4
        i = inputs(both(), {BS: 225, ENCH: 300}, skills={ENCH: 225}, level=30,
                   ranks={ENCH: [Rank(300, 10000, 200, 35)]})
        goal = Budget(1.6)
        guide, report = self.render(i, budget.cut(i, "gold", goal, gold_of(i)), goal)
        for text in (guide, report):
            self.assertIn(f"1.6g takes Blacksmithing to 150 ({gold(TO_150)}).", text)
            self.assertIn("Enchanting gets none of it: next rank needs character level 35.", text)
            self.assertIn("The next stop, Blacksmithing 225, costs about", text)
            self.assertNotIn("The next stop, Enchanting", text)

    def test_reached_target_with_a_budget_blames_no_budget(self):
        i = inputs(bs_only(), {BS: 150}, skills={BS: 200})
        goal = Budget(5)
        c = budget.cut(i, "gold", goal, gold_of(i))
        self.assertFalse(c.below_first_stop)
        guide, report = self.render(i, c, goal)
        for text in (guide, report):
            self.assertIn("Blacksmithing is already at 200: nothing to plan.", text)
            self.assertNotIn("doesn't reach", text)
            self.assertNotIn("Nothing to craft within this budget.", text)

    def test_stalled_only_profession_with_a_budget(self):
        i = inputs(both(), {ENCH: 300}, skills={ENCH: 225}, level=30, ranks={ENCH: [Rank(300, 10000, 200, 35)]})
        goal = Budget(100)
        c = budget.cut(i, "gold", goal, gold_of(i))
        self.assertFalse(c.below_first_stop)
        guide, report = self.render(i, c, goal)
        for text in (guide, report):
            self.assertIn("Enchanting gets none of it: next rank needs character level 35.", text)
            self.assertNotIn("doesn't reach", text)
            self.assertNotIn("Nothing to craft within this budget.", text)


class FeaturesTogetherTests(unittest.TestCase):
    """End to end through write_reports, on made-up game data: a budget, trainer_trips "one_go" and bag_slots at once.
    Blacksmithing from 150: the Artisan rank (a remote trainer) at 150, a pattern from the AH learned at 180, an
    Artisan trainer recipe at 200 (a trip back as needed), the Master rank at 200 for 300. 1g reaches 225."""

    def setUp(self):
        import contextlib
        import io
        import json
        import shutil
        import tempfile
        from pathlib import Path

        from yap_forever import cli, settings
        self._tmp = tempfile.TemporaryDirectory()
        self.paths = settings.paths(Path(self._tmp.name) / "home")
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(["init"], self.paths)
        shutil.copytree(Path(__file__).parent / "fixtures" / "gamedata", self.paths.gamedata)
        c, i, scroll = toy.COPPER_BAR, toy.IRON_BAR, toy.SCROLL
        listings = {str(c): [[10, 100000]], str(i): [[100, 100000]], str(scroll): [[50, 1]]}
        self.paths.prices.write_text(json.dumps({"snapshot_time": "t", "listings": listings}), encoding="utf-8")
        self.gd = toy.gamedata([
            toy.recipe(71, "BS low", BS, {i: 1}, t=(150, 300, 300, 300), req=150),
            toy.recipe(72, "BS pattern", BS, {c: 2}, t=(180, 300, 300, 300), req=180, source="scroll", scroll=scroll),
            toy.recipe(73, "BS trainer", BS, {c: 1}, t=(200, 300, 300, 300), req=200, fee=100)])
        self.gd.trainer_ranks[BS] = self.gd.trainer_ranks[BS] + [Rank(300, 9000, 200, 35)]
        for item in (c, i):
            self.gd.items[item].stack = 20
        self.stock = self.paths.character("Alt") / "stock.toml"
        self.stock.parent.mkdir(parents=True)
        self.stock.write_text("level = 60\nbag_slots = 12\n[items]\n\n[skills]\nblacksmithing = 150\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def reports(self, trainer_trips):
        from unittest import mock

        from yap_forever import gamedata, plan as plan_mod, profile
        from yap_forever.config import Goal
        with mock.patch.object(gamedata, "load_gamedata", return_value=self.gd):
            table, files = plan_mod.write_reports(self.paths, self.stock, "Neutral", {BS: Goal(skill=300)},
                                                  profile.Character("Alt", trainer_trips=trainer_trips),
                                                  target=Budget(1))
        return table, {k: v.read_text(encoding="utf-8") for k, v in files.items()}

    def test_budget_one_go_and_bags_agree(self):
        import re
        table, texts = self.reports("one_go")
        guide, report = texts["guide-gold"], texts["plan-gold"]
        self.assertEqual(guide.splitlines()[0], "# Blacksmithing to 225 — least gold route")  # the cut
        spent = re.search(r"1g takes Blacksmithing to 225 \((.+?)\)\. The next stop, Blacksmithing 300, costs about",
                          guide).group(1)
        self.assertIn(f"**Gold to bring: {spent}**", guide)  # the shopping list is the budget line's gold
        self.assertIn("planned to your 1g budget", report)
        (trip,) = [line for line in guide.splitlines() if line.startswith("- **Trip:**")]  # the trip back is folded
        self.assertIn("Blacksmithing rank to 225", trip)
        self.assertIn("Learn at the trainer as you reach them: BS trainer at 200.", trip)
        self.assertIn("1 Plans: Something (from the AH): enough to craft to 225 at the trainer (7 bag slots)", trip)
        self.assertTrue(trip.endswith("This needs 17 free slots and you have 12: get bigger bags, bank what this "
                                      "stretch doesn't need, or set a lower goal (for example 180) so it fits."), trip)
        self.assertIn("| Trips away | 1 | 1 |", table)
        _table, texts = self.reports("as_needed")  # the same budget as needed: the trip back is a trip
        trips = [line for line in texts["guide-gold"].splitlines() if line.startswith("- **Trip:**")]
        self.assertEqual(len(trips), 2)
        self.assertIn("at 200 for BS trainer (1s 0c)", trips[1])
        self.assertNotIn("Plans: Something (from", trips[0])


if __name__ == "__main__":
    unittest.main()
