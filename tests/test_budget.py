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

    def test_cut_leaves_the_cached_routes_alone(self):
        # final review, Minor 12: the cut route drops the "already at" event in a copy; the route planned to the caps
        # stays in the cache as it was, and both modes' cuts on one shared route get the same copy
        i = inputs(bs_only(), {BS: 225})
        cache: dict = {}
        cuts = {m: budget.cut(i, m, Budget(0.5), gold_of(i), cache) for m in ("gold", "value")}
        (routes, same, _bare), = [v for k, v in cache.items() if k == budget.key({BS: 1})]
        self.assertTrue(same)
        self.assertIn("Blacksmithing already at 1", routes["gold"].events)
        self.assertFalse(any("already at" in e for e in cuts["gold"].plan.events))
        self.assertIsNot(cuts["gold"].plan, routes["gold"])
        self.assertIs(cuts["gold"].plan, cuts["value"].plan)

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
        c.goal_extra = {ENCH: 900}  # #96: so does a recipe goal the cut stops below
        self.assertEqual(budget.adopt(c, new, 400).goal_extra, {ENCH: 1000})
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

    def reports(self, trainer_trips, target=None):
        from unittest import mock

        from yap_forever import gamedata, plan as plan_mod, profile
        from yap_forever.config import Goal
        with mock.patch.object(gamedata, "load_gamedata", return_value=self.gd):
            table, files = plan_mod.write_reports(self.paths, self.stock, "Neutral", {BS: Goal(skill=300)},
                                                  profile.Character("Alt", trainer_trips=trainer_trips),
                                                  target=target or Budget(1))
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

    def test_the_budgets_pay_measures_the_cut_and_its_skips(self):
        # #97 part 3: write_reports takes one measure from the budget's pay, for the cut, its free skips and the gold
        # the cut route spends; the report's cash line says which
        from unittest import mock

        from yap_forever.config import PAYS
        from yap_forever.shopping import gold_as_you_go
        for pay in PAYS:
            with self.subTest(pay=pay), mock.patch.object(budget, "gold_measure", wraps=budget.gold_measure) as made, \
                    mock.patch("yap_forever.budget.gold_as_you_go", wraps=gold_as_you_go) as went:
                _table, texts = self.reports("as_needed", Budget(1, pay=pay))
                self.assertEqual([c.args[0].pay for c in made.call_args_list], [pay])
                self.assertEqual(went.called, pay == "as_you_go")
                # the report's cash line says how the budget was counted: its cash before any sales can be over it
                tail = ", selling crafts to a vendor as you go" if pay == "as_you_go" else ""
                self.assertIn(f"planned to your 1g budget{tail}), before any sales.", texts["plan-gold"])


GEAR = 7811  # a made-up craft that sells to a vendor for 2s


def gear_inputs(caps, skills=None, ranks=None, late=()):
    """Blacksmithing where "BS gear" (spell 61, an Iron Bar at 1s 60c) makes a Test Gear a vendor pays 2s for and "BS
    plain" (spell 62, a Copper Bar at 1s 20c) makes nothing, both orange: with the vendor credit the gear costs nothing
    and wins, without it the plain craft does. late: more recipes."""
    i = inputs([toy.recipe(61, "BS gear", BS, {toy.IRON_BAR: 1}, (GEAR, 1)),
                toy.recipe(62, "BS plain", BS, {toy.COPPER_BAR: 1}), *late], caps, skills=skills,
               listings={toy.IRON_BAR: [(160, 100000)], toy.COPPER_BAR: [(120, 100000)], toy.SHARD: [(100, 100000)]},
               ranks=ranks)
    i.gd.items[GEAR] = toy.item(GEAR, "Test Gear", sell=200)
    return i


def spells(p):
    return {s.spell_id for s in p.steps}


class UncreditedFallbackTests(unittest.TestCase):
    """#97 (owner, 2026-11-21): under a budget each stop takes the mode's route planned with the vendor credit when its
    gold to bring fits, else the route planned without it when that fits; the stop is reached when either fits."""

    def test_budget_takes_uncredited_route_when_it_fits(self):
        # to 75: the credited route brings 74 Iron Bars (1.184g), the uncredited one 74 Copper Bars (0.888g); 1g budget
        i = gear_inputs({BS: 75})
        self.assertEqual((gold_of(i)(route(i, {BS: 75})), spells(route(i, {BS: 75}))), (11840, {61}))
        for mode in ("gold", "value"):
            with self.subTest(mode=mode):
                c = cut(i, 1, mode=mode)
                self.assertEqual(c.caps, {BS: 75})
                self.assertEqual((c.spent, c.credited, c.plan.vendor_credit), (8880, False, False))
                self.assertEqual(spells(c.plan), {62})
                self.assertEqual(c.next_stop, {})

    def test_budget_prefers_credited_when_both_fit(self):
        i = gear_inputs({BS: 75})
        for mode in ("gold", "value"):
            with self.subTest(mode=mode):
                c = cut(i, 2, mode=mode)
                self.assertEqual((c.caps, c.spent, c.credited, c.plan.vendor_credit), ({BS: 75}, 11840, True, True))
                self.assertEqual(spells(c.plan), {61})

    def test_next_stop_costs_what_the_cheaper_route_brings(self):
        # neither fits 0.5g: the stop is reached with the route that brings less, so the next stop costs its gold
        c = cut(gear_inputs({BS: 75}), 0.5)
        self.assertTrue(c.below_first_stop)
        self.assertEqual(c.next_stop, {BS: (75, 8880)})

    def test_no_budget_no_extra_candidates(self):
        # the routes planned without the vendor credit are planned only when a credited route misses a stop
        from unittest import mock

        from yap_forever import plan as plan_mod
        i = gear_inputs({BS: 75})
        with mock.patch.object(plan_mod, "plan", wraps=plan_mod.plan) as planned:
            n = len(candidates(i))
            self.assertTrue(all(p.vendor_credit for p in candidates(i)))
            cut(i, 2)
        self.assertEqual(n, 3)  # one reuse round each: value, gold, gold with one-time costs in full
        self.assertEqual([c.kwargs.get("vendor_credit", True) for c in planned.call_args_list], [True] * 9)
        with mock.patch.object(plan_mod, "plan", wraps=plan_mod.plan) as planned:
            cut(i, 1)
        self.assertEqual([c.kwargs["vendor_credit"] for c in planned.call_args_list], [True] * 3 + [False] * 2)

    def test_uncredited_stop_with_a_free_skip(self):
        # C14: Blacksmithing 225-300 for 6g. With the credit the gear (1s 60c a point) brings 6.2g with the Master rank,
        # so the stop takes the route without it (5.75g): copper to 240, then "BS late" (iron at 1s 20c, the lower id on
        # the tie), a trip back to the Master trainer. Planned without that trip the route costs the same, so the trip is
        # left out, and the route without it is planned without the vendor credit too: with the credit it would take
        # the gear again, cost 1.2g less net and miss the budget
        import dataclasses

        from yap_forever.gamedata import Rank
        from yap_forever.plan import take_free_skips
        from yap_forever.trips import trip_alternatives
        late = toy.recipe(1, "BS late", BS, {toy.SHARD: 1}, t=(240, 300, 300, 300), req=240)
        i = gear_inputs({BS: 300}, skills={BS: 225}, ranks={BS: [Rank(300, 50000, 200, 35)]}, late=[late])
        i = dataclasses.replace(i, market=toy.market({toy.IRON_BAR: [(160, 100000)], toy.COPPER_BAR: [(120, 100000)],
                                                      toy.SHARD: [(120, 100000)]}))
        c = cut(i, 6)
        self.assertEqual((c.caps, c.spent, c.credited), ({BS: 300}, 59000, False))
        self.assertEqual(spells(c.plan), {1, 62})
        cache: dict = {}
        self.assertEqual(trip_alternatives(c.plan, i, "gold", cache), {(1,): 0})
        self.assertEqual([k[-1] for k in cache], [False])  # planned without the vendor credit
        route, left = take_free_skips(c.plan, i, "gold", cache, fits=lambda p: gold_of(i)(p) <= budget.copper(Budget(6)))
        self.assertEqual([t.spells for t in left], [(1,)])
        self.assertFalse(route.vendor_credit)
        self.assertEqual(spells(route), {62})
        self.assertEqual(gold_of(i)(route), 59000)

    def test_listed_saving_keeps_the_routes_credit(self):
        # the route at the Forever listing a route is compared with is planned with the same vendor credit
        import dataclasses
        from unittest import mock

        from yap_forever import plan as plan_mod
        i = gear_inputs({BS: 75})
        gd = i.gd
        gd.recipes[62] = dataclasses.replace(gd.recipes[62], listed_skill=1)
        uncredited = settle_routes(candidates(i, vendor_credit=False), {BS: 75})[0]
        with mock.patch.object(plan_mod, "candidates", wraps=plan_mod.candidates) as made:
            plan_mod.listed_savings(i, {"gold": uncredited["gold"], "value": route(i, {BS: 75}, "value")})
        self.assertEqual(sorted(c.kwargs.get("vendor_credit", True) for c in made.call_args_list), [False, True])

    def test_uncredited_route_that_stops_short_is_not_taken(self):
        # the route without the credit needs less gold but stalls at 60, below the stop at 75: the stop stays on the
        # credited route, which misses the budget, so nothing is planned and the next stop costs the credited gold
        from unittest import mock

        from yap_forever import plan as plan_mod
        from yap_forever.planner import Plan

        def planned(sub, vendor_credit=True):
            skill = sub.caps[BS] if vendor_credit else min(60, sub.caps[BS])
            cost = 0 if sub.caps[BS] == 1 else 20000 if vendor_credit else 500
            return [Plan(final_skill={BS: skill}, cash_total=cost, vendor_credit=vendor_credit)]
        i = inputs(bs_only(), {BS: 75})
        with mock.patch.object(plan_mod, "candidates", side_effect=planned):
            c = budget.cut(i, "gold", Budget(1), lambda p: p.cash_total)
        self.assertEqual((c.caps, c.credited, c.next_stop), ({BS: 1}, True, {BS: (75, 20000)}))

    def test_uncredited_route_at_a_stop_below_the_target(self):
        # two stops, 75 and 150 (its rank 4s 50c): with 1g neither route reaches 150, and 75 fits only without the
        # credit (0.888g against 1.184g), so the cut stops at 75 on that route; the next stop costs the cheaper route's
        # 1.833g less the 0.888g spent
        i = gear_inputs({BS: 150})
        for mode in ("gold", "value"):
            with self.subTest(mode=mode):
                c = cut(i, 1, mode=mode)
                self.assertEqual((c.caps, c.spent, c.credited, c.plan.vendor_credit), ({BS: 75}, 8880, False, False))
                self.assertEqual(spells(c.plan), {62})
                self.assertEqual(c.next_stop, {BS: (150, 18330 - 8880)})

    def test_uncredited_route_that_gets_further_says_so(self):
        # the credited route stalls at 60 below the target of 75 and misses the budget; the one without the credit
        # reaches 75 and fits: the cut reaches 75, with no stall to report
        from unittest import mock

        from yap_forever import plan as plan_mod
        from yap_forever.planner import Plan

        def planned(sub, vendor_credit=True):
            cap = sub.caps[BS]
            if vendor_credit:
                why = {BS: "Blacksmithing: no usable recipe at 60"} if cap > 60 else {}
                return [Plan(final_skill={BS: min(60, cap)}, stall_reasons=why, cash_total=0 if cap == 1 else 20000)]
            return [Plan(final_skill={BS: cap}, cash_total=500, vendor_credit=False)]
        i = inputs(bs_only(), {BS: 75})
        with mock.patch.object(plan_mod, "candidates", side_effect=planned):
            c = budget.cut(i, "gold", Budget(1), lambda p: p.cash_total)
        self.assertEqual((c.caps, c.credited, c.stops_early, c.stalled, c.next_stop), ({BS: 75}, False, {}, {}, {}))


class PayTests(unittest.TestCase):
    """#97 part 3 (owner, 2026-11-21): with pay = "as_you_go" a budget is compared with the gold enough up front when
    crafts are sold to a vendor as you go (shopping.gold_as_you_go), with "upfront" (the default) with "Gold to bring"."""

    def test_budget_pay_as_you_go_fits(self):
        # the route to 16 spends 10g then 5g and the first row's crafts bring 4g back: 15g to bring, 11g as you go. A 12g
        # budget misses the stop paying up front (nothing planned, the stop costs 15g) and reaches it as you go (11g)
        import dataclasses
        from unittest import mock

        from tests.test_shopping import wares_route
        from yap_forever import plan as plan_mod
        from yap_forever.planner import Plan
        full, gd, market, st = wares_route()

        def planned(sub, vendor_credit=True):
            p = full if sub.caps[BS] == 16 else Plan(final_skill={BS: 1})
            return [dataclasses.replace(p, vendor_credit=vendor_credit)]
        i = PlanInputs(gd=gd, market=market, stock=st, favor=toy.NO_FAVOR, caps={BS: 16}, craft_once={}, quests={})
        with mock.patch.object(plan_mod, "candidates", side_effect=planned):
            for mode in ("gold", "value"):
                with self.subTest(mode=mode):
                    up = budget.cut(i, mode, Budget(12))
                    self.assertEqual((up.caps, up.spent, up.next_stop), ({BS: 1}, 0, {BS: (16, 150000)}))
                    self.assertEqual(budget.cut(i, mode, Budget(12, pay="upfront")).caps, {BS: 1})
                    go = budget.cut(i, mode, Budget(12, pay="as_you_go"))
                    self.assertEqual((go.caps, go.spent, go.next_stop, go.credited), ({BS: 16}, 110000, {}, True))
                    self.assertEqual(len(go.plan.steps), 2)
                    # the budget line's gold is the as-you-go figure, and says so (as the report's cash line does)
                    self.assertEqual(budget.lines(go, Budget(12, pay="as_you_go"))[0],
                                     "12g takes Blacksmithing to 16 (11.0g, selling crafts to a vendor as you go).")
                    # one cache shared by both ways to pay keeps each one's gold apart
                    cache: dict = {}
                    self.assertEqual([budget.cut(i, mode, Budget(12, pay=pay), cache=cache).caps
                                      for pay in ("upfront", "as_you_go")], [{BS: 1}, {BS: 16}])
        measured = [budget.gold_measure(Budget(12, pay=pay), gd, market, st)(full) for pay in ("upfront", "as_you_go")]
        self.assertEqual(measured, [150000, 110000])


ALCH = 171
GOAL = 90  # "BS goal": the recipe goal of RecipeGoalTests
DYE = 7900  # a made-up reagent the AH sells and Enchanting can make
TO_GOAL = 7400 + 450 + 2500 + 100  # to 75, the rank, 25 bars to 100, the goal crafted once (a Copper Bar)


def goal_inputs(req=100, skills=None, recipes=(), listings=None, fixed=None, gear=False):
    """Blacksmithing to the recipe goal "BS goal" (spell 90, required `req`, one Copper Bar), levelled with "BS bar" (a
    Copper Bar at 1s a point, orange; gear: gear_inputs' two crafts instead). recipes: more; fixed: planner.plan's."""
    import dataclasses
    goal = toy.recipe(GOAL, "BS goal", BS, {toy.COPPER_BAR: 1}, t=(req, 300, 300, 300), req=req)
    if gear:
        i = gear_inputs({BS: req}, skills=skills, late=[goal, *recipes])
    else:
        i = inputs([*bs_only(), goal, *recipes], {BS: req}, skills=skills, listings=listings)
    return dataclasses.replace(i, craft_once={BS: GOAL}, fixed=fixed or {})


def dye_inputs(shard):
    """goal_inputs where "BS dyed" (spell 3, one Test Dye a point, orange) levels instead of the bar, the AH selling
    Test Dye at 90c; Enchanting, not planned, at 50 knows "Ench dye" (spell 4, trainer, required 40,
    a 5s fee) making one Test Dye from a Small Glimmering Shard at `shard` copper, and not "Ench dye later" (required
    60, from Strange Dust at 1c). The craft margin at Enchanting 50 is 0.908: a shard below 81.7c makes the dye."""
    dyes = [toy.recipe(3, "BS dyed", BS, {DYE: 1}),
            toy.recipe(4, "Ench dye", ENCH, {toy.SHARD: 1}, (DYE, 1), req=40, fee=500),
            toy.recipe(5, "Ench dye later", ENCH, {toy.DUST: 1}, (DYE, 1), req=60)]
    i = goal_inputs(recipes=dyes, fixed={ENCH: 50},
                    listings={DYE: [(90, 100000)], toy.SHARD: [(shard, 100000)], toy.COPPER_BAR: [(100, 100000)],
                              toy.DUST: [(1, 100000)]})
    i.gd.items[DYE] = toy.item(DYE, "Test Dye", sell=5)
    return i


class RecipeGoalTests(unittest.TestCase):
    """#96: a budget with a recipe goal cuts its profession at the rank caps below the recipe's skill, then at the goal
    (that skill and the recipe crafted once); only the goal stop's route crafts it."""

    def test_recipe_goal_fits(self):
        i = goal_inputs()
        c = cut(i, 2)
        self.assertEqual((c.caps, c.spent, c.next_stop, c.goal_extra), ({BS: 100}, TO_GOAL, {}, {}))
        self.assertEqual((c.planned_once, c.covered), ({BS: GOAL}, {BS}))
        self.assertEqual(budget.lines(c, Budget(2)),
                         [f"2g covers Blacksmithing to 100 and one BS goal ({gold(TO_GOAL)})."])
        go = budget.cut(i, "gold", Budget(2, pay="as_you_go"))  # the same gold as you go: nothing sells to a vendor
        self.assertEqual(budget.lines(go, Budget(2, pay="as_you_go")),
                         [f"2g covers Blacksmithing to 100 and one BS goal ({gold(TO_GOAL)}, selling crafts to a "
                          "vendor as you go)."])

    def test_recipe_goal_lower_stop(self):
        i = goal_inputs()
        c = cut(i, 1)
        self.assertEqual((c.caps, c.spent, c.planned_once, c.covered), ({BS: 75}, TO_75, {}, set()))
        self.assertFalse(budget.crafted(c.plan, BS, GOAL))
        self.assertEqual(c.plan.stall_reasons, {})  # no "did not reach BS goal" at the lower stop
        self.assertEqual(c.goal_extra, {BS: TO_GOAL - TO_75})
        self.assertEqual(budget.lines(c, Budget(1)),  # the goal is the next stop: no line of its own
                         [f"1g takes Blacksmithing to 75 ({gold(TO_75)}).",
                          f"The goal, Blacksmithing 100 and one BS goal, costs about {gold(TO_GOAL - TO_75)} more."])
        far = cut(goal_inputs(req=160), 1)  # stops 75, 150 and the goal at 160: the next stop is said too
        said = budget.lines(far, Budget(1))
        self.assertEqual(said[0], f"1g takes Blacksmithing to 75 ({gold(TO_75)}).")
        self.assertTrue(said[1].startswith("The goal, Blacksmithing 160 and one BS goal, costs about "), said)
        self.assertEqual(said[2], f"The next stop, Blacksmithing 150, costs about {gold(TO_150 - TO_75)} more.")

    def test_recipe_goal_zero_budget(self):  # RF5
        from unittest import mock

        from yap_forever import plan as plan_mod
        for gear in (False, True):  # gear: the route without the credit is another route
            for limit in (0, 0.5):
                with self.subTest(gear=gear, limit=limit), \
                        mock.patch.object(plan_mod, "candidates", wraps=plan_mod.candidates) as made:
                    c = cut(goal_inputs(gear=gear), limit)
                    self.assertTrue(c.below_first_stop)
                    self.assertEqual((c.caps, c.spent, c.plan.steps, c.covered), ({BS: 1}, 0, [], set()))
                    self.assertFalse(any("did not reach" in why for why in c.plan.stall_reasons.values()))
                    said = budget.lines(c, Budget(limit))
                    self.assertEqual(said[0], f"{budget.amount(Budget(limit))} doesn't reach the first stop: "
                                              "nothing is planned yet.")
                    self.assertIn("The next stop, Blacksmithing 75, costs about", " ".join(said))
                    self.assertTrue(said[1].startswith("The goal, Blacksmithing 100 and one BS goal, costs about "))
                    # the credited route misses the budget: the one without the credit is planned too
                    self.assertTrue(any(not x.kwargs.get("vendor_credit", True) for x in made.call_args_list))

    def test_recipe_goal_skill_already_there(self):
        # at 120, the goal's skill (100) is there: its one stop is the craft, which 0g doesn't reach and 1g covers
        i = goal_inputs(skills={BS: 120})
        c = cut(i, 0)
        self.assertTrue(c.below_first_stop)
        self.assertEqual((c.plan.steps, c.plan.events, c.next_stop), ([], [], {BS: (100, 100)}))
        self.assertEqual(budget.lines(c, Budget(0)),
                         ["0g doesn't reach the first stop: nothing is planned yet.",
                          "The goal, Blacksmithing 100 and one BS goal, costs about 1s more."])
        c = cut(i, 1)
        self.assertEqual((c.spent, c.covered), (100, {BS}))
        self.assertEqual(budget.lines(c, Budget(1)),  # the owner's wording: the skill is there, only the craft
                         ["1g covers one BS goal (1s); your Blacksmithing 120 already meets its 100."])
        go = budget.cut(i, "gold", Budget(1, pay="as_you_go"))
        self.assertEqual(budget.lines(go, Budget(1, pay="as_you_go")),
                         ["1g covers one BS goal (1s, selling crafts to a vendor as you go); your Blacksmithing 120 "
                          "already meets its 100."])
        self.assertNotIn("Blacksmithing already at 120", c.plan.events)  # the craft is planned: not "nothing to plan"
        from yap_forever.planner import Plan
        replanned = budget.adopt(c, Plan(events=["Blacksmithing already at 120"]), 100)  # a free skip's route too
        self.assertEqual(replanned.plan.events, [])

    def test_other_profession_craft_used_past_margin(self):
        # a shard at 50c makes the dye for less than the AH's 90c by more than the margin: Enchanting's trainer recipe
        # crafts it, with no fee, no Enchanting step or skill-up, and the row names it; the recipe above its skill is
        # not used
        from yap_forever.guide import render_guide
        i = dye_inputs(50)
        c = cut(i, 3)
        p = c.plan
        self.assertEqual((c.caps, p.other_crafts), ({BS: 100}, {DYE: 4}))
        self.assertEqual(p.crafted[DYE], 99)
        self.assertEqual({s.profession for s in p.steps}, {BS})
        self.assertEqual(p.final_skill, {BS: 100})  # C43: never Enchanting
        self.assertEqual(p.fees, 450)  # the rank only: the known recipe has no fee
        self.assertNotIn("Ench dye", " ".join(p.events))
        self.assertNotIn(toy.DUST, p.bought)
        guide = render_guide(p, i.gd, i.market, i.stock, c.planned_caps)
        rows = [line for line in guide.splitlines() if "Test Dye (your Enchanting)" in line]
        self.assertEqual(rows, ["- **1–75** · 74× BS dyed — 99 Small Glimmering Shard, 74 Test Dye (yours); first "
                                "craft 99 Test Dye (your Enchanting)"])  # the route's dyes, made at the first row
        self.assertIn("| Small Glimmering Shard | 99 | AH |", guide)
        self.assertNotIn("| Test Dye |", guide)

    def test_other_profession_craft_not_within_margin(self):
        # a shard at 85c is cheaper than the AH's 90c but within the margin (0.908 x 90c = 81.7c): the dye is bought
        from yap_forever.guide import render_guide
        i = dye_inputs(85)
        c = cut(i, 3)
        self.assertEqual((c.caps, c.plan.other_crafts, c.plan.crafted), ({BS: 100}, {}, {}))
        self.assertEqual(c.plan.bought[DYE], 99)
        guide = render_guide(c.plan, i.gd, i.market, i.stock, c.planned_caps)
        self.assertNotIn("(your Enchanting)", guide)
        self.assertIn("| Test Dye | 99 | AH |", guide)
        free = cut(dye_inputs(50), 3)  # and without Enchanting held at its skill, the dye is bought however cheap
        import dataclasses
        bare = cut(dataclasses.replace(dye_inputs(50), fixed={}), 3)
        self.assertEqual((free.plan.other_crafts, bare.plan.other_crafts, bare.plan.bought[DYE]), ({DYE: 4}, {}, 99))

    def test_two_recipe_goals_under_budget(self):
        # both goals at 100, one at a time, Blacksmithing first: 1.7g covers its goal and Enchanting to 75; each
        # route crafts only the goal it reaches
        import dataclasses
        rs = [*both(), toy.recipe(GOAL, "BS goal", BS, {toy.COPPER_BAR: 1}, t=(100, 300, 300, 300), req=100),
              toy.recipe(91, "Ench goal", ENCH, {toy.SHARD: 1}, t=(100, 300, 300, 300), req=100)]
        i = dataclasses.replace(inputs(rs, {BS: 100, ENCH: 100}), craft_once={BS: GOAL, ENCH: 91})
        c = cut(i, 1.8, order=(BS, ENCH))
        self.assertEqual((c.caps, c.planned_once, c.covered), ({BS: 100, ENCH: 75}, {BS: GOAL}, {BS}))
        self.assertEqual(c.spent, TO_GOAL + TO_75)
        self.assertEqual(c.goal_extra, {ENCH: 500 + 2500 + 100})  # Enchanting's rank is 5s
        self.assertEqual(budget.lines(c, Budget(1.8, (BS, ENCH))),
                         [f"1.8g takes Blacksmithing to 100 and one BS goal, and Enchanting to 75 "
                          f"({gold(TO_GOAL + TO_75)}).",
                          f"The goal, Enchanting 100 and one Ench goal, costs about {gold(3100)} more."])
        both_goals = cut(i, 3, order=(BS, ENCH))
        self.assertEqual(both_goals.covered, {BS, ENCH})
        self.assertEqual(budget.lines(both_goals, Budget(3, (BS, ENCH))),
                         [f"3g covers Blacksmithing to 100 and one BS goal, and Enchanting to 100 and one Ench goal "
                          f"({gold(TO_GOAL + TO_GOAL + 50)})."])
        # Enchanting at 120 already has its goal's skill: that part names only the craft, and the line says why
        i = dataclasses.replace(inputs(rs, {BS: 100, ENCH: 100}, skills={ENCH: 120}), craft_once={BS: GOAL, ENCH: 91})
        met = cut(i, 3, order=(BS, ENCH))
        self.assertEqual(budget.lines(met, Budget(3, (BS, ENCH))),
                         [f"3g covers Blacksmithing to 100 and one BS goal, and one Ench goal ({gold(TO_GOAL + 100)}); "
                          "your Enchanting 120 already meets its 100."])

    def test_goal_craft_that_gold_does_not_reach(self):
        # Minor 4: "BS goal" is a Merchant's Favor recipe for 500 Favor and the character has none: the goal stop's
        # route reaches 100 but can't craft it, so its line says why instead of what more gold would buy
        import dataclasses

        from yap_forever.favor import FavorData
        i = goal_inputs()
        i.gd.recipes[GOAL] = dataclasses.replace(i.gd.recipes[GOAL], source="scroll", scroll_item=toy.SCROLL)
        i = dataclasses.replace(i, favor=FavorData({GOAL: 500}, {GOAL: 100}))
        c = cut(i, 1)
        self.assertEqual((c.caps, c.goal_extra, c.covered), ({BS: 75}, {}, set()))
        self.assertEqual(budget.lines(c, Budget(1)),
                         [f"1g takes Blacksmithing to 75 ({gold(TO_75)}).",
                          f"The next stop, Blacksmithing 100, costs about {gold(TO_GOAL - 100 - TO_75)} more; the "
                          "route stops there: can't learn BS goal: not enough Favor (500)."])


def favor_goal_inputs(**kw):
    """goal_inputs where "BS goal" is a Merchant's Favor recipe for 500 Favor and the character has none: its route
    reaches the goal's skill but can't craft it."""
    import dataclasses

    from yap_forever.favor import FavorData
    i = goal_inputs(**kw)
    i.gd.recipes[GOAL] = dataclasses.replace(i.gd.recipes[GOAL], source="scroll", scroll_item=toy.SCROLL)
    return dataclasses.replace(i, favor=FavorData({GOAL: 500}, {GOAL: 100}))


class GoalCraftFailsTests(unittest.TestCase):
    """Final review, Important 2: a budget whose route reaches the goal's skill (or starts there) but can't craft the
    recipe says why, with the "; the route stops there: <why>" tail; and so does a goal two or more stops above the
    cut."""
    WHY = "can't learn BS goal: not enough Favor (500)"

    def test_goal_stop_taken(self):
        c = cut(favor_goal_inputs(), 3)  # the gold reaches the goal stop; the route is the one to 100, no craft
        self.assertEqual((c.caps, c.covered, c.next_stop), ({BS: 100}, set(), {}))
        self.assertEqual(budget.lines(c, Budget(3)),
                         [f"3g takes Blacksmithing to 100 ({gold(TO_GOAL - 100)}); the route stops there: {self.WHY}."])

    def test_skill_already_there(self):
        c = cut(favor_goal_inputs(skills={BS: 120}), 1)  # before: no line at all, and an empty route
        self.assertEqual((c.plan.steps, c.covered, c.below_first_stop), ([], set(), False))
        self.assertEqual(budget.lines(c, Budget(1)),
                         [f"1g doesn't cover one BS goal; your Blacksmithing 120 already meets its 100; the route stops "
                          f"there: {self.WHY}."])

    def test_goal_two_stops_above(self):
        # stops 75, 150 and the goal at 160: the next stop is 150, and the goal's reason has a line of its own
        said = budget.lines(cut(favor_goal_inputs(req=160), 1), Budget(1))
        self.assertEqual(said, [f"1g takes Blacksmithing to 75 ({gold(TO_75)}).",
                                f"The next stop, Blacksmithing 150, costs about {gold(TO_150 - TO_75)} more.",
                                f"The route stops at Blacksmithing 160: {self.WHY}."])

    def test_with_the_bring_list_tail(self):
        # Minor 7 with the stop's reason on one line: the reason first, then the bring list's
        c = budget.cut(favor_goal_inputs(), "gold", Budget(3, pay="as_you_go"))
        self.assertEqual(budget.lines(c, Budget(3, pay="as_you_go"), bring=True),
                         [f"3g takes Blacksmithing to 100 ({gold(TO_GOAL - 100)}, selling crafts to a vendor as you "
                          f"go); the route stops there: {self.WHY}; a trip's bring list is bought before the trip and "
                          "can need more."])
        up = cut(favor_goal_inputs(), 3)  # paying up front, "Gold to bring" already counts the bring lists
        self.assertNotIn("bring list", " ".join(budget.lines(up, Budget(3), bring=True)))


class RecipeGoalReportsTests(unittest.TestCase):
    """#96 through write_reports: the budget lines of a recipe goal in the guide, the report and the comparison the
    plan command prints; a skill target next to it is not planned."""

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
        listings = {str(toy.COPPER_BAR): [[100, 100000]], str(toy.SHARD): [[100, 100000]]}
        self.paths.prices.write_text(json.dumps({"snapshot_time": "t", "listings": listings}), encoding="utf-8")
        self.gd = goal_inputs(recipes=[toy.recipe(2, "Ench shard", ENCH, {toy.SHARD: 1})]).gd
        self.stock = self.paths.character("Bram Ironhide") / "stock.toml"  # planned; Ana is the group mate
        self.stock.parent.mkdir(parents=True)
        self.stock.write_text("level = 60\n[items]\n\n[skills]\nenchanting = 50\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def reports(self, target, goals, group=None, name="Bram Ironhide"):
        from unittest import mock

        from yap_forever import gamedata, plan as plan_mod, profile
        with mock.patch.object(gamedata, "load_gamedata", return_value=self.gd):
            table, files = plan_mod.write_reports(self.paths, self.stock, "Neutral", goals, profile.Character(name),
                                                  target=target, group=group)
        return table, {k: v.read_text(encoding="utf-8") for k, v in files.items()}

    def dyes(self, skills, shard=50):
        """The Blacksmithing goal levelled with "BS dyed" (a Test Dye a point, 90c on the AH), planned for Bram
        Ironhide, whose group mate Ana Brightforge has `skills`; Alchemy's "Alch dye" (trainer, required 100) makes a
        dye from a Small Glimmering Shard at `shard` copper. (table, texts)."""
        import json

        from yap_forever.config import Goal
        from yap_forever.shared import Group
        self.gd = dye_inputs(50).gd
        self.gd.recipes[4] = toy.recipe(4, "Alch dye", ALCH, {toy.SHARD: 1}, (DYE, 1), req=100)
        del self.gd.recipes[5]
        listings = {str(DYE): [[90, 100000]], str(toy.SHARD): [[shard, 100000]], str(toy.COPPER_BAR): [[100, 100000]]}
        self.paths.prices.write_text(json.dumps({"snapshot_time": "t", "listings": listings}), encoding="utf-8")
        group = Group(2, "alliance", others={"Ana Brightforge": toy.stock(skills=skills)})
        return self.reports(Budget(3), {BS: Goal(recipe="BS goal")}, group)

    def test_alt_suggestion_with_skills(self):
        # Ana's Alchemy 150 makes the route's 99 dyes for 49s 50c against 89s 10c on the AH: 39s 60c less
        table, texts = self.dyes({ALCH: 150})
        line = ("Your Alchemist Ana Brightforge can make the 99 Test Dye for about 39s less than the AH and mail them; "
                "the gold to bring doesn't count that.")
        self.assertTrue(table.endswith(f"3g covers Blacksmithing to 100 and one BS goal (94s). {line}"), table[-300:])
        for text in texts.values():
            self.assertEqual(text.count(line), 1)
        self.assertIn("| Test Dye | 99 | AH |", texts["guide-gold"])  # still bought: a suggestion, not a step
        # a shard at 84c is cheaper than the dye's 90c but within the margin at Alchemy 150 (0.925 x 90c = 83.2c)
        table, texts = self.dyes({ALCH: 150}, shard=84)
        self.assertNotIn("can make the", table + "".join(texts.values()))

    def test_no_suggestion_without_skills(self):
        from yap_forever.config import Goal
        for skills in ({}, {ALCH: 99}):  # none set, or below the recipe's skill
            with self.subTest(skills=skills):
                table, texts = self.dyes(skills)
                self.assertNotIn("can make the", table + "".join(texts.values()))
        # Ana's Alchemy names nothing without a budget, or with a budget and a skill target only
        from yap_forever.shared import Group
        self.dyes({ALCH: 150})  # the dye data and prices
        group = Group(2, "alliance", others={"Ana Brightforge": toy.stock(skills={ALCH: 150})})
        for target, goals in ((None, {BS: Goal(recipe="BS goal")}), (Budget(3), {BS: Goal(skill=100)})):
            table, texts = self.reports(target, goals, group)
            self.assertNotIn("can make the", table + "".join(texts.values()))

    def test_gold_to_bring_unchanged_by_suggestion(self):
        # pinned (D2): 99 dyes at 90c, the 4s 50c rank and the goal's Copper Bar, with Ana's Alchemy named or not
        for skills in ({}, {ALCH: 150}):
            with self.subTest(skills=skills):
                _table, texts = self.dyes(skills)
                for text in (texts["guide-gold"], texts["guide-value"]):
                    self.assertIn("**Gold to bring: 94s**", text)

    def test_other_profession_line(self):
        from yap_forever.config import Goal
        goals = {BS: Goal(recipe="BS goal"), ENCH: Goal(skill=150)}
        table, texts = self.reports(Budget(2), goals)
        covers = f"2g covers Blacksmithing to 100 and one BS goal ({gold(TO_GOAL)})."
        aside = "Enchanting is not planned with this budget: it goes to the Blacksmithing goal."
        self.assertTrue(table.endswith(f"\n\n{covers} {aside}"), table[-200:])  # once: both routes say the same
        ordered, _texts = self.reports(Budget(2, (ENCH, BS)), goals)  # an order naming the profession left out
        self.assertTrue(ordered.endswith(f"\n\n{covers} {aside}"), ordered[-200:])
        self.assertNotIn("Enchanting", table[:table.index(covers)])  # nothing planned or reached for it
        for m in ("gold", "value"):
            guide, report = texts[f"guide-{m}"], texts[f"plan-{m}"]
            self.assertTrue(guide.startswith("# Blacksmithing to 100 — "), guide[:60])
            self.assertEqual(guide.count(f"{covers} {aside}"), 1)
            verdict = report[report.index("## Verdict"):].split("\n## ")[0]
            self.assertIn(f"{covers} {aside}", verdict)
            self.assertIn("Planned to: Blacksmithing 100.", verdict)
            self.assertNotIn("Ench shard", guide + report)
        _table, texts = self.reports(Budget(1), goals)  # a lower stop: no goal recipe, no stall for it
        for text in texts.values():
            self.assertIn(f"1g takes Blacksmithing to 75 ({gold(TO_75)}). The goal, Blacksmithing 100 and one BS goal, "
                          f"costs about {gold(TO_GOAL - TO_75)} more. {aside}", text)
            self.assertNotIn("did not reach", text)
        table, _texts = self.reports(None, goals)  # without a budget both are planned, and nothing is added
        self.assertIn("Blacksmithing 100, Enchanting 150", table)
        self.assertNotIn(aside, table)
        self.assertNotIn("covers", table)

    def test_replans_keep_the_stops_goal_craft(self):
        # P23: the skip alternatives, free skips and the listed saving replan each route with the craft its stop has:
        # none at a lower stop (no "did not reach" there), the goal recipe at the goal
        from unittest import mock

        from yap_forever import plan as plan_mod
        from yap_forever.config import Goal
        for limit, once in ((1, {}), (2, {BS: GOAL})):
            with self.subTest(limit=limit), \
                    mock.patch.object(plan_mod, "trip_alternatives", wraps=plan_mod.trip_alternatives) as alts, \
                    mock.patch.object(plan_mod, "take_free_skips", wraps=plan_mod.take_free_skips) as skips, \
                    mock.patch.object(plan_mod, "listed_savings", wraps=plan_mod.listed_savings) as listed:
                self.reports(Budget(limit), {BS: Goal(recipe="BS goal")})
                for made, at in ((alts, 1), (skips, 1), (listed, 0)):  # where each takes the route's PlanInputs
                    crafts = [c.args[at].craft_once for c in made.call_args_list]
                    self.assertEqual(crafts, [once] * len(crafts))
                    self.assertTrue(crafts)

    def test_other_profession_without_a_skill_is_not_held(self):
        # Minor 5: with no [skills] entry the other profession is not held at a skill (it knows no recipes), but it is
        # still named as not planned
        from unittest import mock

        from yap_forever import plan as plan_mod
        from yap_forever.config import Goal
        goals = {BS: Goal(recipe="BS goal"), ENCH: Goal(skill=150)}
        for stock, fixed in (("", {}), ("[skills]\nenchanting = 50\n", {ENCH: 50})):
            self.stock.write_text(f"level = 60\n[items]\n\n{stock}", encoding="utf-8")
            with self.subTest(fixed=fixed), \
                    mock.patch.object(plan_mod, "candidates", wraps=plan_mod.candidates) as made:
                table, _texts = self.reports(Budget(2), goals)
                self.assertEqual({tuple(c.args[0].fixed.items()) for c in made.call_args_list}, {tuple(fixed.items())})
                self.assertIn("Enchanting is not planned with this budget", table)

    def test_goal_craft_fails_said_everywhere(self):
        # Important 2 through write_reports: stdout (the comparison returned), the guide header and the report verdict
        from unittest import mock

        from yap_forever import plan as plan_mod
        from yap_forever.config import Goal
        why = "can't learn BS goal: not enough Favor (500)"
        self.gd = favor_goal_inputs(recipes=[toy.recipe(2, "Ench shard", ENCH, {toy.SHARD: 1})]).gd
        for skills, line in (("", f"3g takes Blacksmithing to 100 ({gold(TO_GOAL - 100)}); the route stops there: "
                                  f"{why}."),
                             ("blacksmithing = 120\n", "3g doesn't cover one BS goal; your Blacksmithing 120 already "
                                                       f"meets its 100; the route stops there: {why}.")):
            self.stock.write_text(f"level = 60\n[items]\n\n[skills]\n{skills}", encoding="utf-8")
            with self.subTest(skills=skills), \
                    mock.patch.object(plan_mod, "load_favor", return_value=favor_goal_inputs().favor):
                table, texts = self.reports(Budget(3), {BS: Goal(recipe="BS goal")})
                self.assertTrue(table.endswith(f"\n\n{line}"), table[-300:])
                for m in ("gold", "value"):
                    guide, report = texts[f"guide-{m}"], texts[f"plan-{m}"]
                    self.assertEqual(guide[:guide.index("## ")].count(line), 1, m)
                    verdict = report[report.index("## Verdict"):].split("\n## ")[0]
                    self.assertEqual(verdict.count(line), 1, m)

    def test_as_you_go_line_names_the_bring_list(self):
        # Minor 7 through write_reports: the as-you-go line says a bring list can need more when the route has one
        from unittest import mock

        from yap_forever import plan as plan_mod
        from yap_forever.config import Goal
        covers = f"2g covers Blacksmithing to 100 and one BS goal ({gold(TO_GOAL)}, selling crafts to a vendor as you go)"
        for bring in (False, True):
            with self.subTest(bring=bring), mock.patch.object(plan_mod, "has_bring_list", return_value=bring) as has:
                table, texts = self.reports(Budget(2, pay="as_you_go"), {BS: Goal(recipe="BS goal")})
                tail = "; a trip's bring list is bought before the trip and can need more." if bring else "."
                self.assertTrue(table.endswith(f"\n\n{covers}{tail}"), table[-300:])
                self.assertIn(f"{covers}{tail}", texts["guide-gold"])
                self.assertTrue(has.called)

    def test_said_once_labels_routes_that_differ(self):
        from yap_forever.plan import _said_once
        self.assertEqual(_said_once({"gold": ["a.", "b."], "value": ["a.", "b."]}), "a. b.")
        self.assertEqual(_said_once({"gold": ["a."], "value": ["c."]}), "Least gold: a.\n\nLeast total value: c.")


if __name__ == "__main__":
    unittest.main()
