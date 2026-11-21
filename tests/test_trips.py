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
    return [(v.profession, v.skill, v.rank_cap, v.remote, v.kind, v.learn, v.if_missing) for v in vs]


class VisitTests(unittest.TestCase):
    def test_learn_ahead_at_rank_visit(self):
        spells = [(1, 180), (2, 185), (3, 200), (4, 210), (5, 220)]
        p, gd = setup(ENCH, spells, ranks=[(225, 300)],
                      learns=[(1, 231), (2, 240), (3, 252), (4, 252), (5, 266)])
        start = {ENCH: 225}
        self.assertEqual(shape(visits(p, gd, start)),
                         [(ENCH, 225, 300, True, "rank", [], [1, 2, 3, 4, 5])])
        self.assertEqual(before_start(p, gd, start), {})

    def test_later_master_recipes_make_recipe_visits(self):
        # the literal rule: a visit at skill s teaches every later recipe of its rank with required skill <= s
        p, gd = setup(ENCH, [(1, 240), (2, 245)], ranks=[(225, 300)], learns=[(1, 250), (2, 251)])
        self.assertEqual(shape(visits(p, gd, {ENCH: 225})),
                         [(ENCH, 225, 300, True, "rank", [], []),
                          (ENCH, 250, 300, True, "recipe", [1, 2], [])])
        p, gd = setup(ENCH, [(1, 240), (2, 245)], ranks=[(225, 300)], learns=[(1, 240), (2, 251)])
        self.assertEqual(shape(visits(p, gd, {ENCH: 225})),
                         [(ENCH, 225, 300, True, "rank", [], []),
                          (ENCH, 240, 300, True, "recipe", [1], []),
                          (ENCH, 251, 300, True, "recipe", [2], [])])

    def test_before_start_for_recipe_used_first(self):  # RF3
        p, gd = setup(BS, [(1, 160)], learns=[(1, 184)])
        self.assertEqual(visits(p, gd, {BS: 184}), [])
        self.assertEqual(before_start(p, gd, {BS: 184}), {BS: [1]})

    def test_city_visit_for_expert_recipe(self):
        p, gd = setup(BS, [(1, 140)], learns=[(1, 142)])
        self.assertEqual(shape(visits(p, gd, {BS: 100})), [(BS, 142, 150, False, "city", [1], [])])
        self.assertEqual(before_start(p, gd, {BS: 100}), {})

    def test_recipe_joins_a_rank_visit_it_is_reached_by(self):
        p, gd = setup(BS, [(1, 130), (2, 210)], ranks=[(140, 225)], learns=[(1, 145), (2, 212)])
        self.assertEqual(shape(visits(p, gd, {BS: 100})),
                         [(BS, 140, 225, True, "rank", [1], []),
                          (BS, 212, 225, True, "recipe", [2], [])])

    def test_higher_recipe_does_not_join_a_lower_trainer_visit(self):
        # an Expert stop at 160 (for a 140 recipe) can't teach a 155 recipe: that one needs an Artisan
        p, gd = setup(BS, [(1, 140), (2, 155)], learns=[(1, 160), (2, 170)])
        self.assertEqual(shape(visits(p, gd, {BS: 130})),
                         [(BS, 160, 150, False, "city", [1], []),
                          (BS, 170, 225, True, "recipe", [2], [])])

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
    nothing is planned twice. A Favor recipe is a goal only (#95), never skipped: the free pattern here is a vendor's."""

    def setup(self):
        from types import SimpleNamespace
        recipes = [(spell, req, fee) for spell, req, fee in
                   ((1, 240, 100), (2, 250, 500), (3, 260, 300), (4, 270, 200), (5, 280, 400))]
        gd = toy.gamedata([toy.recipe(s, f"Recipe {s}", BS, {toy.IRON_BAR: 1}, req=r, fee=f) for s, r, f in recipes]
                          + [toy.recipe(9, "Pattern", BS, {toy.IRON_BAR: 1}, source="scroll", scroll=toy.SCROLL),
                             toy.recipe(10, "Free pattern", BS, {toy.IRON_BAR: 1}, source="scroll", scroll=toy.ODD)])
        gd.vendor_prices[toy.SCROLL] = 1000
        base = Plan(ranks=[(BS, 225, 300, 500)], final_skill={BS: 300},
                    learn_log=[(BS, req, s, "trainer") for s, req, _f in recipes] + [(BS, 230, 9, "vendor"),
                                                                                         (BS, 235, 10, "vendor")])
        inputs = SimpleNamespace(gd=gd, stock=toy.stock(skills={BS: 225}), craft_once={}, caps={BS: 300})
        return base, inputs

    def test_recipe_trips_have_their_own_cap(self):
        from unittest import mock
        from yap_forever.trips import MAX_TRIP_ALTS, trip_alternatives
        base, inputs = self.setup()
        with mock.patch("yap_forever.plan.plan_route", return_value=base) as replan:
            alts = trip_alternatives(base, inputs, "gold")
        self.assertEqual(MAX_TRIP_ALTS, 3)
        # the free vendor pattern (no gold cost) keeps its tail although five recipe trips have fees
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


class OneGoTests(unittest.TestCase):
    """trainer_trips = "one_go": the player levels at a remote rank trainer to the end of its stretch and learns the
    recipes there as the skill reaches them (no visits back in between)."""

    def test_one_go_has_no_return_trips(self):
        from yap_forever.trips import trips
        p, gd = setup(ENCH, [(1, 240), (2, 245)], ranks=[(225, 300)], learns=[(1, 240), (2, 251)])
        p.final_skill = {ENCH: 300}
        start = {ENCH: 225}
        self.assertEqual([t.kind for t in trips(p, gd, start)], ["rank", "recipe", "recipe"])
        self.assertEqual([t.kind for t in trips(p, gd, start, "one_go")], ["rank"])
        (v,) = visits(p, gd, start, "one_go")
        self.assertEqual((v.kind, v.skill, v.learn, v.as_reached), ("rank", 225, [], [(1, 240), (2, 251)]))

    def test_one_go_stretch_ends_at_the_next_rank(self):
        # Artisan at 140 (stretch to the Master training at 200), Master at 200 (stretch to the end, 260); an Expert
        # recipe's capital stop inside the Artisan stretch is folded too
        p, gd = setup(BS, [(1, 160), (2, 230), (3, 145)], ranks=[(140, 225), (200, 300)],
                      learns=[(1, 170), (2, 240), (3, 146)])
        p.final_skill = {BS: 260}
        start = {BS: 130}
        self.assertEqual([v.kind for v in visits(p, gd, start)], ["rank", "city", "recipe", "rank", "recipe"])
        got = visits(p, gd, start, "one_go")
        self.assertEqual([(v.skill, v.kind, v.as_reached) for v in got],
                         [(140, "rank", [(3, 146), (1, 170)]), (200, "rank", [(2, 240)])])

    def test_one_go_keeps_visits_outside_a_remote_stretch(self):
        # no remote rank visit on the route (the start is past it): the trip back stays; the other profession's
        # rank trip doesn't fold Blacksmithing's visits
        from yap_forever.planner import Plan
        gd = toy.gamedata([toy.recipe(1, "BS late", BS, {toy.IRON_BAR: 1}, req=240, fee=100),
                           toy.recipe(2, "Ench late", ENCH, {toy.IRON_BAR: 1}, req=250, fee=100)])
        p = Plan(ranks=[(ENCH, 225, 300, 500)], learn_log=[(BS, 240, 1, "trainer"), (ENCH, 252, 2, "trainer")],
                 final_skill={BS: 300, ENCH: 300})
        got = visits(p, gd, {BS: 230, ENCH: 225}, "one_go")
        self.assertEqual([(v.profession, v.skill, v.kind, v.as_reached) for v in got],
                         [(ENCH, 225, "rank", [(2, 252)]), (BS, 240, "recipe", [])])

    def test_one_go_alternatives_skip_folded_trips(self):
        from unittest import mock
        from types import SimpleNamespace
        from yap_forever.trips import trip_alternatives
        p, gd = setup(ENCH, [(1, 240), (2, 245)], ranks=[(225, 300)], learns=[(1, 240), (2, 251)])
        p.final_skill = {ENCH: 300}
        inputs = SimpleNamespace(gd=gd, stock=toy.stock(skills={ENCH: 225}), craft_once={}, caps={ENCH: 300})
        with mock.patch("yap_forever.plan.plan_route", return_value=p) as replan:
            self.assertEqual(trip_alternatives(p, inputs, "gold", trainer_trips="one_go"), {})
        self.assertEqual(replan.call_count, 0)

    def test_one_go_lists_the_skill_the_route_learns_at(self):
        # as needed, the 251 trip also learns recipe 3 ahead (required 250, learned at 270): one go says "at 270",
        # where the route learns it and its "Learn" row stays
        p, gd = setup(ENCH, [(1, 240), (2, 245), (3, 250)], ranks=[(225, 300)], learns=[(1, 240), (2, 251), (3, 270)])
        p.final_skill = {ENCH: 300}
        start = {ENCH: 225}
        self.assertEqual([(v.skill, v.learn) for v in visits(p, gd, start)], [(225, []), (240, [1]), (251, [2, 3])])
        (v,) = visits(p, gd, start, "one_go")
        self.assertEqual(v.as_reached, [(1, 240), (2, 251), (3, 270)])

    def test_one_go_folds_a_goal_trainer_recipe_learned_at_the_end(self):
        # a craft-once goal taught by the Master trainer, learned at the route's end (240): as needed a trip back,
        # in one go learned at the trainer as the skill reaches it (the fold takes the stretch's end too)
        from yap_forever.trips import trips
        p, gd = setup(ENCH, [(1, 240)], ranks=[(225, 300)], learns=[(1, 240)])
        p.final_skill = {ENCH: 240}
        start = {ENCH: 225}
        self.assertEqual([(t.kind, t.skill) for t in trips(p, gd, start)], [("rank", 225), ("recipe", 240)])
        self.assertEqual([(t.kind, t.skill) for t in trips(p, gd, start, "one_go")], [("rank", 225)])
        (v,) = visits(p, gd, start, "one_go")
        self.assertEqual(v.as_reached, [(1, 240)])


def free_toy(late=((1, 240, (240, 300, 300, 300)),), fee=0):
    """(PlanInputs, Blacksmithing 1-300) where the late recipes (spell, required skill, thresholds; iron) cost what
    the copper recipe (spell 9) does: the planner takes the late ones on a tie (lower spell id), so each is a trip
    back to the Master trainer whose route-without costs the same."""
    from tests.test_budget import inputs
    from yap_forever.gamedata import Rank
    recipes = [toy.recipe(s, f"BS late {s}", BS, {toy.IRON_BAR: 1}, t=t, req=req, fee=fee) for s, req, t in late]
    return inputs(recipes + [toy.recipe(9, "BS bar", BS, {toy.COPPER_BAR: 1})], {BS: 300},
                  listings={toy.COPPER_BAR: [(100, 100000)], toy.IRON_BAR: [(100, 100000)]},
                  ranks={BS: [Rank(300, 50000, 200, 35)]})


def recipe_trips(route, i):
    from yap_forever.trips import trips
    return [(t.skill, t.spells) for t in trips(route, i.gd, i.stock.skills) if t.kind == "recipe"]


class FreeSkipTests(unittest.TestCase):
    """#90: a trip whose route-without costs at most FREE_SKIP more and makes fewer trainer visits and pattern trips
    is left out of the route (plan.take_free_skips); its skip clause goes."""

    def mocked(self, alt_cash, alt_learns=()):
        """(base, inputs, the route without recipe 3) with plan_route to mock: the base learns recipe 3 (fee 1s) on a
        trip back at 240; the route without it costs alt_cash (the base 1000) and learns alt_learns."""
        from types import SimpleNamespace
        gd = toy.gamedata([toy.recipe(3, "BS late", BS, {toy.IRON_BAR: 1}, req=240, fee=100),
                           toy.recipe(4, "BS pattern", BS, {toy.IRON_BAR: 1}, source="scroll", scroll=toy.SCROLL)])
        gd.vendor_prices[toy.SCROLL] = 1000
        base = Plan(ranks=[(BS, 225, 300, 500)], final_skill={BS: 300}, learn_log=[(BS, 240, 3, "trainer")],
                    cash_total=1000, economic_total=1000)
        alt = Plan(ranks=[(BS, 225, 300, 500)], final_skill={BS: 300}, learn_log=list(alt_learns),
                   cash_total=alt_cash, economic_total=alt_cash)
        return base, SimpleNamespace(gd=gd, stock=toy.stock(skills={BS: 225}), craft_once={}, caps={BS: 300}), alt

    def take(self, base, inputs, alt=None, **kw):
        from unittest import mock
        from yap_forever.plan import take_free_skips
        if alt is None:
            return take_free_skips(base, inputs, "gold", {}, **kw)
        with mock.patch("yap_forever.plan.plan_route", return_value=alt):
            return take_free_skips(base, inputs, "gold", {}, **kw)

    def test_visit_count(self):
        from yap_forever.trips import visit_count
        base, inputs = AlternativeCapTests().setup()
        # the rank training, five trips back for recipes and the two vendor trips
        self.assertEqual(visit_count(base, inputs.gd, inputs.stock.skills), 8)
        # in one go the trips back are folded into the rank visit and both vendor patterns are on its bring list
        self.assertEqual(visit_count(base, inputs.gd, inputs.stock.skills, "one_go"), 1)

    def test_free_skip_adopted(self):
        from yap_forever.plan import plan_route
        i = free_toy()
        base = plan_route(i, "gold")
        self.assertEqual(recipe_trips(base, i), [(240, (1,))])
        route, left = self.take(base, i)
        self.assertEqual(recipe_trips(route, i), [])
        self.assertEqual([(t.kind, t.skill, t.spells) for t in left], [("recipe", 240, (1,))])
        self.assertEqual(route.cash_total, base.cash_total)
        self.assertEqual(route.final_skill, base.final_skill)

    def test_free_skip_at_the_limit(self):
        from yap_forever.trips import FREE_SKIP
        self.assertEqual(FREE_SKIP, 0.5)
        base, inputs, alt = self.mocked(1000.5)
        route, left = self.take(base, inputs, alt)
        self.assertIs(route, alt)
        self.assertEqual([t.spells for t in left], [(3,)])
        base, inputs, alt = self.mocked(990)  # cheaper without it: taken too
        self.assertIs(self.take(base, inputs, alt)[0], alt)

    def test_dearer_skip_kept(self):
        base, inputs, alt = self.mocked(1001)
        route, left = self.take(base, inputs, alt)
        self.assertIs(route, base)
        self.assertEqual(left, [])

    def test_alternative_with_as_many_visits_not_adopted(self):
        # the route without the trip back buys a vendor pattern instead: one trip for another
        base, inputs, alt = self.mocked(1000, alt_learns=[(BS, 240, 4, "vendor")])
        route, left = self.take(base, inputs, alt)
        self.assertIs(route, base)
        self.assertEqual(left, [])

    def test_two_free_skips_in_two_rounds(self):
        from unittest import mock
        from yap_forever import plan as plan_mod
        from yap_forever.plan import plan_route
        i = free_toy(late=((1, 240, (240, 260, 260, 260)), (3, 260, (260, 300, 300, 300))))
        base = plan_route(i, "gold")
        self.assertEqual(recipe_trips(base, i), [(240, (1,)), (260, (3,))])
        with mock.patch.object(plan_mod, "plan_route", wraps=plan_mod.plan_route) as replan:
            route, left = self.take(base, i)
        self.assertEqual(recipe_trips(route, i), [])
        self.assertEqual([t.spells for t in left], [(1,), (3,)])  # equal fees: the first in skill order, then the next
        self.assertEqual(route.cash_total, base.cash_total)
        # round one plans without each trip, round two without the one left; the exclusions add up
        self.assertEqual([c.kwargs["exclude"] for c in replan.call_args_list],
                         [frozenset({1}), frozenset({3}), frozenset({1, 3})])

    def test_free_skip_respects_budget(self):
        from yap_forever.plan import plan_route
        i = free_toy()
        base = plan_route(i, "gold")
        seen = []

        def fits(p):
            seen.append(p)
            return False
        route, left = self.take(base, i, fits=fits)
        self.assertIs(route, base)
        self.assertEqual(left, [])
        self.assertEqual(len(seen), 1)
        self.assertIsNot(seen[0], base)  # the route without the trip is what has to fit
        self.assertEqual(recipe_trips(seen[0], i), [])

    def test_goal_recipe_never_left_out(self):
        import dataclasses
        from yap_forever.plan import plan_route
        i = dataclasses.replace(free_toy(), craft_once={BS: 1})
        base = plan_route(i, "gold")
        self.assertEqual(recipe_trips(base, i), [(240, (1,))])
        route, left = self.take(base, i)
        self.assertIs(route, base)
        self.assertEqual(left, [])

    def test_shown_alternatives_keep_the_recipes_left_out(self):
        # after a free skip the skip clauses measure against the adopted route: the recipe left out stays out
        from unittest import mock
        from yap_forever.trips import trip_alternatives
        base, inputs, alt = self.mocked(1001)
        cache: dict = {}
        with mock.patch("yap_forever.plan.plan_route", return_value=alt) as replan:
            alts = trip_alternatives(base, inputs, "gold", cache, excluded=frozenset({7}))
        self.assertEqual(alts, {(3,): 1})
        self.assertEqual(replan.call_args.kwargs["exclude"], frozenset({3, 7}))
        self.assertEqual(list(cache), [("gold", ((BS, 300),), frozenset({3, 7}))])

    def test_shared_route_needs_both_measures(self):
        # gold and value on one route: the route without the trip is taken only when it is free in both measures
        base, inputs, alt = self.mocked(1000)
        alt.economic_total = 1001  # free in gold, 1c more in total value
        self.assertIs(self.take(base, inputs, alt)[0], alt)
        route, left = self.take(base, inputs, alt, also=("value",))
        self.assertIs(route, base)
        self.assertEqual(left, [])
        alt.economic_total = 1000.5
        self.assertIs(self.take(base, inputs, alt, also=("value",))[0], alt)

    def test_rounds_add_up_to_at_most_free_skip(self):
        # each round is measured against the route as first settled: two skips of 0.3c each would cost 0.6c in all,
        # so only the first is taken
        from types import SimpleNamespace
        from unittest import mock
        from yap_forever.plan import take_free_skips
        gd = toy.gamedata([toy.recipe(3, "BS late", BS, {toy.IRON_BAR: 1}, req=240, fee=200),
                           toy.recipe(5, "BS later", BS, {toy.IRON_BAR: 1}, req=260, fee=100)])
        inputs = SimpleNamespace(gd=gd, stock=toy.stock(skills={BS: 225}), craft_once={}, caps={BS: 300})

        def route(learns, cost):
            return Plan(ranks=[(BS, 225, 300, 500)], final_skill={BS: 300}, cash_total=cost, economic_total=cost,
                        learn_log=[(BS, s, spell, "trainer") for spell, s in learns])
        base = route([(3, 240), (5, 260)], 1000)
        without = {frozenset({3}): route([(5, 260)], 1000.3), frozenset({5}): route([(3, 240)], 1000.4),
                   frozenset({3, 5}): route([], 1000.6)}
        with mock.patch("yap_forever.plan.plan_route", side_effect=lambda _i, _m, exclude: without[exclude]):
            got, left = take_free_skips(base, inputs, "gold", {})
        self.assertIs(got, without[frozenset({3})])
        self.assertEqual([t.spells for t in left], [(3,)])

    def test_a_later_round_never_costs_more_than_its_route(self):
        # without trip 3 the route is 10c cheaper; without both it is 5c dearer than that, though still under the
        # original: only trip 3 is left out, so each "costs the same" line is true
        from types import SimpleNamespace
        from unittest import mock
        from yap_forever.plan import take_free_skips
        gd = toy.gamedata([toy.recipe(3, "BS late", BS, {toy.IRON_BAR: 1}, req=240, fee=200),
                           toy.recipe(5, "BS later", BS, {toy.IRON_BAR: 1}, req=260, fee=100)])
        inputs = SimpleNamespace(gd=gd, stock=toy.stock(skills={BS: 225}), craft_once={}, caps={BS: 300})

        def route(learns, cost):
            return Plan(ranks=[(BS, 225, 300, 500)], final_skill={BS: 300}, cash_total=cost, economic_total=cost,
                        learn_log=[(BS, s, spell, "trainer") for spell, s in learns])
        base = route([(3, 240), (5, 260)], 1000)
        without = {frozenset({3}): route([(5, 260)], 990), frozenset({5}): route([(3, 240)], 1000.4),
                   frozenset({3, 5}): route([], 995)}
        with mock.patch("yap_forever.plan.plan_route", side_effect=lambda _i, _m, exclude: without[exclude]):
            got, left = take_free_skips(base, inputs, "gold", {})
        self.assertIs(got, without[frozenset({3})])
        self.assertEqual([t.spells for t in left], [(3,)])



ALCH, ENG = 171, 202
DARNASSUS, IRONFORGE = 1657, 1537
STAGE_CAPS = {(ALCH, 225): DARNASSUS, (ENG, 225): IRONFORGE, (BS, 225): IRONFORGE}


class HomeCapitalTests(unittest.TestCase):
    """#98: the capital the guide starts in: the character's `capital`, else the only capital the route's stages need,
    else the one whose stage the route reaches first."""

    def home(self, ranks, start=None, final=None, capital=None, caps=STAGE_CAPS):
        from yap_forever.plan import home_capital
        from yap_forever.profile import Character
        p = Plan(ranks=[(prof, s, cap, 500) for prof, s, cap in ranks],
                 final_skill=final or {prof: 225 for prof, _s, _c in ranks})
        return home_capital(caps, p, Character("Ana Brightforge", capital=capital), start or {})

    def test_default_one_capital(self):
        self.assertEqual(self.home([(ENG, 50, 150), (ENG, 125, 225)]), IRONFORGE)
        self.assertEqual(self.home([(ALCH, 130, 225), (ENCH, 125, 225)]), DARNASSUS)

    def test_default_two_capitals_first_in_route_order(self):
        # Engineering trains Artisan at 125, Alchemy at 130: Ironforge
        self.assertEqual(self.home([(ENG, 125, 225), (ALCH, 130, 225)]), IRONFORGE)
        # one profession at a time, Alchemy first: the route reaches Darnassus's stage first, whatever the skills say
        self.assertEqual(self.home([(ALCH, 130, 225), (ENG, 125, 225)]), DARNASSUS)

    def test_default_takes_the_stage_the_route_starts_in(self):
        # Blacksmithing starts at 184, its Artisan rank already trained: that stage is Ironforge's
        self.assertEqual(self.home([(BS, 225, 300)], start={BS: 184}, final={BS: 300}), IRONFORGE)
        self.assertEqual(self.home([(BS, 225, 300), (ALCH, 130, 225)], start={BS: 184, ALCH: 1},
                                   final={BS: 300, ALCH: 225}), IRONFORGE)
        # a profession the route doesn't raise has no stage on it
        self.assertEqual(self.home([(ALCH, 130, 225)], start={BS: 184, ALCH: 1}, final={BS: 184, ALCH: 225}),
                         DARNASSUS)

    def test_capital_key_wins(self):
        self.assertEqual(self.home([(ENG, 125, 225), (ALCH, 130, 225)], capital="darnassus"), DARNASSUS)
        self.assertEqual(self.home([(ENG, 125, 225)], capital="stormwind"), 1519)

    def test_no_capital_stage_no_home(self):
        self.assertIsNone(self.home([(ENCH, 125, 225), (BS, 50, 150)]))
        self.assertIsNone(self.home([(ENG, 125, 225)], caps={}))  # no trainer data (RF2)
        self.assertIsNone(self.home([(ENG, 125, 225)], caps={}, capital="ironforge"))
        # a route with no stage in a capital has no home, whatever the key says: rows say "any capital" as before
        self.assertIsNone(self.home([(ENCH, 125, 225), (BS, 50, 150)], capital="ironforge"))


def capital_route():
    """(plan, game data, start skills): Engineering trains Artisan at 125 (Ironforge) and goes back for recipes at 160
    and 170; Alchemy trains Artisan at 130 (Darnassus) and goes back at 197."""
    gd = toy.gamedata([toy.recipe(31, "Eng strut", ENG, {toy.IRON_BAR: 1}, req=155, fee=720),
                       toy.recipe(32, "Eng gizmo", ENG, {toy.IRON_BAR: 1}, req=165, fee=810),
                       toy.recipe(41, "Alch elixir", ALCH, {toy.IRON_BAR: 1}, req=190, fee=2880)])
    p = Plan(ranks=[(ENG, 125, 225, 500), (ALCH, 130, 225, 500)],
             learn_log=[(ENG, 160, 31, "trainer"), (ENG, 170, 32, "trainer"), (ALCH, 197, 41, "trainer")],
             final_skill={ENG: 225, ALCH: 225})
    return p, gd, {ENG: 120, ALCH: 120}


def trip_shape(ts):
    return [(t.kind, t.skill, t.profession, t.spells) for t in ts]


class CapitalStopTests(unittest.TestCase):
    """#98: in the home capital every visit to a capital-stage trainer is a stop, not a trip, whatever trainer_trips;
    the other capital follows trainer_trips; remote trainers stay trips."""

    def test_home_capital_visits_are_stops(self):
        from yap_forever.trips import trips
        p, gd, start = capital_route()
        kw = {"capitals": STAGE_CAPS, "home": IRONFORGE}
        got = visits(p, gd, start, **kw)
        self.assertEqual([(v.profession, v.skill, v.kind, v.city) for v in got],
                         [(ENG, 125, "rank", IRONFORGE), (ALCH, 130, "rank", DARNASSUS), (ENG, 160, "recipe", IRONFORGE),
                          (ENG, 170, "recipe", IRONFORGE), (ALCH, 197, "recipe", DARNASSUS)])
        for mode in ("as_needed", "one_go"):
            with self.subTest(mode=mode):
                self.assertNotIn(ENG, [t.profession for t in trips(p, gd, start, mode, **kw)])
                # C22: one go folds no home stop: the Engineering stops keep their rows
                stops = [(v.skill, v.kind, v.learn, v.as_reached) for v in visits(p, gd, start, mode, **kw)
                         if v.profession == ENG]
                self.assertEqual(stops, [(125, "rank", [], []), (160, "recipe", [31], []), (170, "recipe", [32], [])])
        # the same with an Expert stop before the rank training (the first visit is then no home stop)
        gd.recipes[30] = toy.recipe(30, "Eng tube", ENG, {toy.IRON_BAR: 1}, req=115, fee=100)
        p.learn_log.insert(0, (ENG, 118, 30, "trainer"))
        stops = [(v.skill, v.kind) for v in visits(p, gd, {ENG: 100, ALCH: 100}, "one_go", **kw) if v.profession == ENG]
        self.assertEqual(stops, [(118, "city"), (125, "rank"), (160, "recipe"), (170, "recipe")])

    def test_other_capital_as_needed_and_one_go(self):
        from yap_forever.trips import trips
        p, gd, start = capital_route()
        kw = {"capitals": STAGE_CAPS, "home": IRONFORGE}
        got = trips(p, gd, start, **kw)
        self.assertEqual(trip_shape(got), [("rank", 130, ALCH, ()), ("recipe", 197, ALCH, (41,))])
        self.assertEqual([t.visit.city for t in got], [DARNASSUS, DARNASSUS])
        (rank,) = trips(p, gd, start, "one_go", **kw)  # the 0.2.1 fold: levelled there, learned as reached
        self.assertEqual((rank.kind, rank.skill, rank.visit.as_reached), ("rank", 130, [(41, 197)]))
        # the other way round: home Darnassus, Ironforge's rank training and recipe visits are the trips
        got = trips(p, gd, start, capitals=STAGE_CAPS, home=DARNASSUS)
        self.assertEqual(trip_shape(got), [("rank", 125, ENG, ()), ("recipe", 160, ENG, (31,)),
                                           ("recipe", 170, ENG, (32,))])

    def test_remote_trips_unchanged(self):
        # Enchanting's Artisan and Blacksmithing's Master stand in no capital: as today, in both modes
        from yap_forever.trips import trips, visit_count
        gd = toy.gamedata([toy.recipe(51, "Ench late", ENCH, {toy.IRON_BAR: 1}, req=180, fee=100),
                           toy.recipe(52, "BS late", BS, {toy.IRON_BAR: 1}, req=240, fee=100),
                           toy.recipe(53, "BS pattern", BS, {toy.IRON_BAR: 1}, source="scroll", scroll=toy.SCROLL)])
        p = Plan(ranks=[(ENCH, 150, 225, 500), (BS, 225, 300, 500)],
                 learn_log=[(ENCH, 200, 51, "trainer"), (BS, 240, 52, "trainer"), (BS, 250, 53, "vendor")],
                 final_skill={ENCH: 225, BS: 300})
        start = {ENCH: 140, BS: 200}
        for mode in ("as_needed", "one_go"):
            with self.subTest(mode=mode):
                plain = trips(p, gd, start, mode)
                got = trips(p, gd, start, mode, capitals=STAGE_CAPS, home=IRONFORGE)
                self.assertEqual(trip_shape(got), trip_shape(plain))
                self.assertTrue(all(t.visit is None or t.visit.city is None for t in got))
                self.assertEqual(visit_count(p, gd, start, mode, capitals=STAGE_CAPS, home=IRONFORGE),
                                 visit_count(p, gd, start, mode))

    def test_one_go_home_stretch_keeps_pattern_trips(self):
        # a vendor pattern inside a home stage's stretch has no bring list to ride on: it stays a trip of its own
        from yap_forever.trips import trips
        p, gd, start = capital_route()
        gd.recipes[33] = toy.recipe(33, "Eng schematic", ENG, {toy.IRON_BAR: 1}, source="scroll", scroll=toy.SCROLL)
        p.learn_log.append((ENG, 150, 33, "vendor"))
        got = trips(p, gd, start, "one_go", capitals=STAGE_CAPS, home=IRONFORGE)
        self.assertIn(("vendor", 150, ENG, ()), trip_shape(got))

    def test_visit_count_counts_home_stops(self):
        # Part 3's free skip still sees the home stops: a route without one makes fewer visits
        from yap_forever.trips import visit_count
        p, gd, start = capital_route()
        for mode in ("as_needed", "one_go"):
            with self.subTest(mode=mode):
                self.assertEqual(visit_count(p, gd, start, mode, capitals=STAGE_CAPS, home=IRONFORGE),
                                 5 if mode == "as_needed" else 4)

    def test_no_data_falls_back(self):  # RF2: no stage capitals, no home: the visits and trips of today
        from yap_forever.trips import trips
        p, gd, start = capital_route()
        for kw in ({}, {"capitals": {}, "home": None}, {"capitals": None, "home": None}):
            with self.subTest(kw=kw):
                self.assertEqual(len(trips(p, gd, start, **kw)), 5)
                self.assertTrue(all(v.city is None for v in visits(p, gd, start, **kw)))

    def test_free_skip_still_applies_to_capital_visit(self):
        # Part 3 (C13): a home-capital recipe stop is still a candidate, keyed by its recipes, and its route-without
        # makes one visit fewer
        from types import SimpleNamespace
        from unittest import mock
        from yap_forever.plan import take_free_skips
        from yap_forever.trips import trip_alternatives
        p, gd, start = capital_route()
        p.cash_total = p.economic_total = 1000
        alt = Plan(ranks=list(p.ranks), learn_log=[x for x in p.learn_log if x[2] != 32], final_skill=dict(p.final_skill),
                   cash_total=1000, economic_total=1000)
        inputs = SimpleNamespace(gd=gd, stock=toy.stock(skills=start), craft_once={}, caps={ENG: 225, ALCH: 225})
        kw = {"capitals": STAGE_CAPS, "home": IRONFORGE}
        with mock.patch("yap_forever.plan.plan_route", side_effect=lambda _i, _m, exclude: alt if exclude == {32}
                        else p):
            self.assertIn((32,), trip_alternatives(p, inputs, "gold", {}, **kw))
            route, left = take_free_skips(p, inputs, "gold", {}, **kw)
        self.assertIs(route, alt)
        self.assertEqual([(t.kind, t.skill, t.spells, t.visit.city) for t in left], [("recipe", 170, (32,), IRONFORGE)])

if __name__ == "__main__":
    unittest.main()
