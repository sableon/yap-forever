"""Trainer visits from the route: rank trainings, recipe trips and city stops, and the trainer recipes
learned at each (learn ahead)."""
import unittest

from tests import toy
from yap_forever.planner import Plan
from yap_forever.trips import before_start, visits

BS, ENCH = 164, 333


def setup(prof, recipes, ranks=(), learns=()):
    """recipes: (spell, required skill); ranks: (skill, cap); learns: (spell, skill it is learned at)."""
    gd = toy.gamedata([toy.recipe(spell, f"Recipe {spell}", prof, {toy.IRON_BAR: 1}, req=req, fee=100)
                       for spell, req in recipes])
    p = Plan(ranks=[(prof, s, cap, 500) for s, cap in ranks],
             learn_log=[(prof, s, spell, "trainer") for spell, s in learns])
    return p, gd


def shape(vs):
    return [(v.profession, v.skill, v.rank_cap, v.remote, v.kind, v.learn, v.if_missing, v.fallback) for v in vs]


class VisitTests(unittest.TestCase):
    def test_learn_ahead_at_rank_visit(self):
        spells = [(1, 180), (2, 185), (3, 200), (4, 210), (5, 220)]
        p, gd = setup(ENCH, spells, ranks=[(225, 300)],
                      learns=[(1, 231), (2, 240), (3, 252), (4, 252), (5, 266)])
        start = {ENCH: 225}
        self.assertEqual(shape(visits(p, gd, start)),
                         [(ENCH, 225, 300, True, "rank", [], [1, 2, 3, 4, 5], {s: 225 for s in range(1, 6)})])
        self.assertEqual(before_start(p, gd, start), {})

    def test_later_master_recipes_make_recipe_visits(self):
        # the literal rule: a visit at skill s teaches every later recipe of its rank with required skill <= s
        p, gd = setup(ENCH, [(1, 240), (2, 245)], ranks=[(225, 300)], learns=[(1, 250), (2, 251)])
        self.assertEqual(shape(visits(p, gd, {ENCH: 225})),
                         [(ENCH, 225, 300, True, "rank", [], [], {}),
                          (ENCH, 250, 300, True, "recipe", [1, 2], [], {})])
        p, gd = setup(ENCH, [(1, 240), (2, 245)], ranks=[(225, 300)], learns=[(1, 240), (2, 251)])
        self.assertEqual(shape(visits(p, gd, {ENCH: 225})),
                         [(ENCH, 225, 300, True, "rank", [], [], {}),
                          (ENCH, 240, 300, True, "recipe", [1], [], {}),
                          (ENCH, 251, 300, True, "recipe", [2], [], {})])

    def test_before_start_for_recipe_used_first(self):  # RF3
        p, gd = setup(BS, [(1, 160)], learns=[(1, 184)])
        self.assertEqual(visits(p, gd, {BS: 184}), [])
        self.assertEqual(before_start(p, gd, {BS: 184}), {BS: [1]})

    def test_city_visit_for_expert_recipe(self):
        p, gd = setup(BS, [(1, 140)], learns=[(1, 142)])
        self.assertEqual(shape(visits(p, gd, {BS: 100})), [(BS, 142, 150, False, "city", [1], [], {})])
        self.assertEqual(before_start(p, gd, {BS: 100}), {})

    def test_recipe_joins_a_rank_visit_it_is_reached_by(self):
        p, gd = setup(BS, [(1, 130), (2, 210)], ranks=[(140, 225)], learns=[(1, 145), (2, 212)])
        self.assertEqual(shape(visits(p, gd, {BS: 100})),
                         [(BS, 140, 225, True, "rank", [1], [], {1: 150}),
                          (BS, 212, 225, True, "recipe", [2], [], {})])

    def test_higher_recipe_does_not_join_a_lower_trainer_visit(self):
        # an Expert stop at 160 (for a 140 recipe) can't teach a 155 recipe: that one needs an Artisan
        p, gd = setup(BS, [(1, 140), (2, 155)], learns=[(1, 160), (2, 170)])
        self.assertEqual(shape(visits(p, gd, {BS: 130})),
                         [(BS, 160, 150, False, "city", [1], [], {}),
                          (BS, 170, 225, True, "recipe", [2], [], {})])

    def test_recipes_from_other_sources_make_no_visits(self):
        p, gd = setup(BS, [(1, 140)], learns=[(1, 142)])
        p.learn_log = [(BS, 142, 1, "vendor")]
        self.assertEqual(visits(p, gd, {BS: 100}), [])
        self.assertEqual(before_start(p, gd, {BS: 100}), {})


class RecipeTripTests(unittest.TestCase):
    """Recipe trips on planned routes: the skip alternative and a budget cut."""

    def inputs(self, caps, craft_once=None):
        import dataclasses
        from tests.test_budget import inputs
        from yap_forever.gamedata import Rank
        late = toy.recipe(3, "BS late", BS, {toy.IRON_BAR: 1}, t=(240, 300, 300, 300), req=240, fee=100)
        i = inputs([toy.recipe(1, "BS bar", BS, {toy.COPPER_BAR: 1}), late], caps,
                   listings={toy.COPPER_BAR: [(100, 100000)], toy.IRON_BAR: [(50, 100000)]},
                   ranks={BS: [Rank(300, 50000, 200, 35)]})
        return dataclasses.replace(i, craft_once=craft_once or {})

    def test_recipe_trip_skip_alternative(self):
        from yap_forever.plan import plan_route
        from yap_forever.trips import trip_alternatives, trips
        i = self.inputs({BS: 300})
        base = plan_route(i, "gold")
        found = [(t.kind, t.skill, t.spells) for t in trips(base, i.gd, i.stock.skills) if t.kind == "recipe"]
        self.assertEqual(found, [("recipe", 240, (3,))])
        alts = trip_alternatives(base, i, "gold")
        self.assertGreater(alts[(3,)], 0)  # without the iron recipe the route crafts copper to 300

    def test_recipe_trip_for_the_goal_recipe_has_no_skip(self):
        from yap_forever.plan import plan_route
        from yap_forever.trips import trip_alternatives
        i = self.inputs({BS: 240}, craft_once={BS: 3})
        self.assertEqual(trip_alternatives(plan_route(i, "gold"), i, "gold"), {(3,): None})

    def test_budget_cut_route_visits(self):
        from tests.test_budget import cut
        from yap_forever.plan import plan_route
        i = self.inputs({BS: 300})
        full = visits(plan_route(i, "gold"), i.gd, i.stock.skills)
        self.assertTrue(any(v.skill > 225 for v in full))  # the uncut route goes back for the 240 recipe
        c = cut(i, 3)
        self.assertEqual(c.caps, {BS: 225})
        got = visits(c.plan, i.gd, i.stock.skills)
        self.assertTrue(got)
        self.assertEqual([v for v in got if v.skill > 225 or v.rank_cap > 225], [])


class AlternativeCapTests(unittest.TestCase):
    """Pattern trips (vendor and Favor) and recipe trips each get MAX_TRIP_ALTS alternatives, costliest first;
    nothing is planned twice."""

    def setup(self):
        from types import SimpleNamespace
        recipes = [(spell, req, fee) for spell, req, fee in
                   ((1, 240, 100), (2, 250, 500), (3, 260, 300), (4, 270, 200), (5, 280, 400))]
        gd = toy.gamedata([toy.recipe(s, f"Recipe {s}", BS, {toy.IRON_BAR: 1}, req=r, fee=f) for s, r, f in recipes]
                          + [toy.recipe(9, "Pattern", BS, {toy.IRON_BAR: 1}, source="scroll", scroll=toy.SCROLL),
                             toy.recipe(10, "Favor recipe", BS, {toy.IRON_BAR: 1}, source="favor")])
        gd.vendor_prices[toy.SCROLL] = 1000
        base = Plan(ranks=[(BS, 225, 300, 500)], final_skill={BS: 300},
                    learn_log=[(BS, req, s, "trainer") for s, req, _f in recipes] + [(BS, 230, 9, "vendor"),
                                                                                         (BS, 235, 10, "favor")])
        inputs = SimpleNamespace(gd=gd, stock=toy.stock(skills={BS: 225}), craft_once={}, caps={BS: 300})
        return base, inputs

    def test_recipe_trips_have_their_own_cap(self):
        from unittest import mock
        from yap_forever.trips import MAX_TRIP_ALTS, trip_alternatives
        base, inputs = self.setup()
        with mock.patch("yap_forever.plan.plan_route", return_value=base) as replan:
            alts = trip_alternatives(base, inputs, "gold")
        self.assertEqual(MAX_TRIP_ALTS, 3)
        # the Favor trip (no gold cost) keeps its tail although five recipe trips have fees
        self.assertEqual(set(alts), {9, 10, (2,), (5,), (3,)})  # both patterns, then the fees 5s, 4s and 3s
        self.assertEqual(replan.call_count, 5)

    def test_alternatives_are_planned_once(self):
        from unittest import mock
        from yap_forever.trips import trip_alternatives
        base, inputs = self.setup()
        cache: dict = {}
        with mock.patch("yap_forever.plan.plan_route", return_value=base) as replan:
            first = trip_alternatives(base, inputs, "gold", cache)
            again = trip_alternatives(base, inputs, "gold", cache)
            trip_alternatives(base, inputs, "value", cache)
        self.assertEqual(first, again)
        self.assertEqual(replan.call_count, 10)  # 5 for gold once, 5 for value


if __name__ == "__main__":
    unittest.main()
