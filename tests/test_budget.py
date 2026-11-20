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
        self.assertEqual(budget.stops_for(184, 300), [225, 300])
        self.assertEqual(budget.stops_for(150, 200), [200])
        self.assertEqual(budget.stops_for(225, 225), [])


class CutTests(unittest.TestCase):
    def test_gold_to_bring_is_the_shopping_lists_total(self):
        i = inputs(bs_only((1, 1, 1, 400)), {BS: 150})  # yellow: the buffer counts
        p = route(i, i.caps)
        lines, _ = render_shopping(p, i.gd, i.market, i.stock)
        self.assertIn(f"**Gold to bring: {gold(gold_to_bring(p, i.gd, i.market, i.stock))}**", lines)
        self.assertGreater(gold_to_bring(p, i.gd, i.market, i.stock), p.cash_total)

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


if __name__ == "__main__":
    unittest.main()
