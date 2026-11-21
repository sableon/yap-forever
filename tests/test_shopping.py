"""Shopping list, mailbox trips and what to bring to a remote trainer (ported from scripts/shopping.py)."""
import unittest

from tests import toy
from yap_forever.planner import Plan, Step
from yap_forever.quests import QuestPlan
from yap_forever.shopping import CRAFT_ROOM
from tests.test_planner import BARS, ENCH, base_recipes, run, run_caps

BS = 164
S, T, L, K, G = toy.COPPER_BAR, toy.IRON_BAR, toy.ROD, toy.STONE, toy.VEST


def shopping_text(p, gd, listings):
    from yap_forever.shopping import render_shopping
    return "\n".join(render_shopping(p, gd, toy.market(listings), toy.stock())[0])


def all_need(p, gd):
    from yap_forever.shopping import route_rows
    out = {}
    for r in route_rows(p, gd):
        for i, q in r["need"].items():
            out[i] = out.get(i, 0) + q
    return out


def orange(plan):
    """Mark every step as orange (no buffer), as the old script's self-checks assumed."""
    for st in plan.steps:
        st.buffered = st.crafts
    return plan


def chain_gd():
    """L from 3 S; K from 1 L; G from 1 L and 1 T (all orange: no buffer)."""
    return toy.gamedata([toy.recipe(40, "Make L", BS, {S: 3}, (L, 1)), toy.recipe(41, "Make K", BS, {L: 1}, (K, 1)),
                         toy.recipe(42, "Make G", BS, {L: 1, T: 1}, (G, 1))])


def chain_plan():
    return orange(Plan(steps=[Step(BS, 1, 11, 40, "Make L", 10, 0, 0, {S: 30}),
                       Step(BS, 11, 16, 41, "Make K", 5, 0, 0, used_made={L: 5}),
                       Step(BS, 16, 20, 42, "Make G", 4, 0, 0, {S: 6, T: 4}, used_made={L: 2})],
                crafted={L: 2}, bought={S: 36, T: 4}, final_skill={BS: 20}))


class PortedSelfChecks(unittest.TestCase):
    def test_batch_size_goggles(self):
        from yap_forever.shopping import batch_size
        # Flying Tiger Goggles: 2 Tigerseye + 6 Light Leather, goggles don't stack, 16 free slots
        self.assertEqual(batch_size({818: 2, 2318: 6}, (4368, 1), {818: 20, 2318: 20, 4368: 1}, 16), 15)

    def test_group_trips_by_slots(self):
        from yap_forever.shopping import group_trips, route_rows
        rows = route_rows(chain_plan(), chain_gd())
        self.assertEqual([len(t) for t in group_trips(rows, 2, {S: 20, T: 20})], [2, 1])


class ShoppingListTests(unittest.TestCase):
    def test_total_is_sum_of_rounded_rows(self):
        from yap_forever.shopping import render_shopping
        gd = toy.gamedata([toy.recipe(1, "BS basic", BS, {S: 1}), toy.recipe(2, "BS basic", BS, {S: 1})])
        p = orange(Plan(steps=[Step(BS, 1, 3, 1, "BS basic", 2.2, 22, 22, {S: 2.2}),
                               Step(BS, 3, 6, 2, "BS basic", 3.1, 31, 31, {S: 3.1})],
                        bought={S: 5.3}, final_skill={BS: 6}))
        text = "\n".join(render_shopping(p, gd, toy.market({S: [(10, 100)]}), toy.stock())[0])
        self.assertIn("| Copper Bar | 7 | AH | 70c |", text)
        self.assertIn("**Gold to bring: 70c**", text)

    def test_trips_only_with_bag_slots(self):
        import dataclasses
        from yap_forever.shopping import render_shopping
        gd, p, m = chain_gd(), chain_plan(), toy.market({S: [(10, 1000)], T: [(50, 100)]})
        lines, trips = render_shopping(p, gd, m, toy.stock())
        self.assertNotIn("## Mailbox trips", lines)
        self.assertIsNone(trips)
        lines, trips = render_shopping(p, gd, m, dataclasses.replace(toy.stock(), bag_slots=60))
        self.assertIn("## Mailbox trips", lines)
        self.assertEqual(trips, 1)


def rank_trip_plan():
    p = Plan(steps=[Step(BS, 225, 235, 1, "BS one", 10, 0, 0, {S: 60}, from_stock={S: 20}),
                    Step(BS, 235, 245, 2, "BS two", 10, 0, 0, {T: 80}),
                    Step(BS, 245, 300, 3, "BS three", 55, 0, 0, {toy.ROD: 55})],
             ranks=[(BS, 225, 300, 9000)], bought={S: 40, T: 80}, vendor_bought={toy.ROD: 55},
             final_skill={BS: 300})
    orange(p)
    gd = toy.gamedata([toy.recipe(1, "BS one", BS, {S: 6}), toy.recipe(2, "BS two", BS, {T: 8}),
                       toy.recipe(3, "BS three", BS, {toy.ROD: 1})])
    for i in (S, T, toy.ROD):
        gd.items.setdefault(i, toy.item(i, "x")).stack = 20
    return p, gd


class BringListTests(unittest.TestCase):
    def trip(self):
        from yap_forever.trips import Trip
        return Trip(225, BS, "rank", "Blacksmithing rank to 300")

    def test_bring_list_fits_bags(self):
        from yap_forever.shopping import bring_list
        p, gd = rank_trip_plan()
        reach, items = bring_list(p, gd, self.trip(), bag_slots=16)  # 6 free after room for crafts
        self.assertEqual(reach, 235)
        self.assertEqual({i for i, _n, _src in items}, {S})

    def test_bring_list_without_bag_slots(self):
        from yap_forever.shopping import bring_list
        p, gd = rank_trip_plan()
        reach, items = bring_list(p, gd, self.trip(), bag_slots=None)  # rows ending within 25 points
        self.assertEqual(reach, 245)
        self.assertEqual({i for i, _n, _src in items}, {S, T})

    def test_bring_list_sources(self):
        from yap_forever.shopping import bring_list
        p, gd = rank_trip_plan()
        _reach, items = bring_list(p, gd, self.trip(), bag_slots=200)
        self.assertIn((S, 40, "mail"), items)
        self.assertIn((S, 20, "bank"), items)
        self.assertIn((toy.ROD, 55, "vendor"), items)

    def test_guide_rank_trip_bring(self):
        from yap_forever.guide import render_guide
        p, gd = rank_trip_plan()
        text = render_guide(p, gd, toy.market({S: [(10, 1000)]}), toy.stock(skills={BS: 225}), caps={BS: 300})
        line = next(l for l in text.splitlines() if l.startswith("- **Trip:**") and "rank to 300" in l)
        self.assertIn("Bring:", line)
        self.assertIn("enough to craft to 245 at the trainer", line)
        self.assertIn("no auction house, mailbox or bank", line)

    def bank_plan(self):
        from yap_forever.planner import Plan, Step
        S = toy.COPPER_BAR
        p = Plan(steps=[Step(BS, 200, 225, 1, "BS one", 20, 0, 0, {S: 20}, from_stock={S: 20}, buffered=20),
                        Step(BS, 225, 235, 2, "BS two", 10, 0, 0, {S: 60}, buffered=10)],
                 ranks=[(BS, 225, 300, 9000)], bought={S: 60}, final_skill={BS: 235})
        gd = toy.gamedata([toy.recipe(1, "BS one", BS, {S: 1}), toy.recipe(2, "BS two", BS, {S: 6})])
        return p, gd

    def test_bank_used_before_the_trip_is_not_brought(self):
        from yap_forever.shopping import bring_list
        from yap_forever.trips import Trip
        p, gd = self.bank_plan()
        trip = Trip(225, BS, "rank", "Blacksmithing rank to 300")
        for owned in (None, {toy.COPPER_BAR: 20}):
            _reach, items = bring_list(p, gd, trip, None, owned)
            self.assertEqual(items, [(toy.COPPER_BAR, 60, "mail")])
        _reach, items = bring_list(p, gd, trip, None, {toy.COPPER_BAR: 50})  # 30 spare in the bank
        self.assertEqual(sorted(items), [(toy.COPPER_BAR, 30, "bank"), (toy.COPPER_BAR, 30, "mail")])

    def test_bring_list_stops_at_the_next_rank_trip(self):
        from yap_forever.planner import Plan, Step
        from yap_forever.shopping import bring_list
        from yap_forever.trips import Trip
        S = toy.COPPER_BAR
        gd = toy.gamedata([toy.recipe(1, "A", BS, {S: 1}), toy.recipe(2, "B", BS, {S: 1})])
        p = Plan(steps=[Step(BS, 140, 200, 1, "A", 60, 0, 0, {S: 60}, buffered=60),
                        Step(BS, 200, 260, 2, "B", 60, 0, 0, {S: 60}, buffered=60)],
                 ranks=[(BS, 140, 225, 0), (BS, 200, 300, 0)], bought={S: 120}, final_skill={BS: 260})
        gd.items[S].stack = 20
        for bags in (None, 200):
            reach, items = bring_list(p, gd, Trip(140, BS, "rank", "Blacksmithing rank to 225"), bags)
            self.assertEqual(reach, 200, bags)
            self.assertEqual(items, [(S, 60, "mail")], bags)

    def test_bring_list_stops_at_the_next_recipe_visit(self):
        import dataclasses
        from yap_forever.shopping import bring_list
        p, gd = rank_trip_plan()
        gd.recipes[2] = dataclasses.replace(gd.recipes[2], required_skill=232)  # unlocks after the rank trip
        p.learn_log = [(BS, 235, 2, "trainer")]  # learned at 235: a trip back to the trainer then
        self.assertEqual(bring_list(p, gd, self.trip(), bag_slots=None)[0], 245)  # as before without start skills
        reach, items = bring_list(p, gd, self.trip(), bag_slots=None, start_skills={BS: 225})
        self.assertEqual(reach, 235)  # level at home after that, and come back at 235
        self.assertEqual({i for i, _n, _src in items}, {S})

    def recipe_visit_plan(self):
        import dataclasses
        p, gd = rank_trip_plan()
        gd.recipes[2] = dataclasses.replace(gd.recipes[2], required_skill=232)  # a trip back at 235 as needed
        p.learn_log = [(BS, 235, 2, "trainer")]
        return p, gd

    def test_one_go_bring_list_covers_stretch(self):
        from yap_forever.shopping import bring_list
        p, gd = self.recipe_visit_plan()
        for bags in (None, 16, 200):  # neither cut to the bags nor to 25 points: the bag warning says if it fits
            reach, items = bring_list(p, gd, self.trip(), bag_slots=bags, start_skills={BS: 225},
                                      trainer_trips="one_go")
            self.assertEqual(reach, 300, bags)
            self.assertEqual({i for i, _n, _src in items}, {S, T, toy.ROD}, bags)

    def test_one_go_bring_list_takes_items_made_earlier(self):
        # Enchanting levels at its trainer from 225 with an item Blacksmithing made before: bring it along
        from yap_forever.shopping import bring_list, bring_text
        from yap_forever.trips import Trip
        gd = toy.gamedata([toy.recipe(40, "Make L", BS, {S: 3}, (L, 1)),
                           toy.recipe(50, "Ench L", ENCH, {L: 1, T: 1})])
        p = orange(Plan(steps=[Step(BS, 200, 210, 40, "Make L", 10, 0, 0, {S: 30}),
                               Step(ENCH, 225, 235, 50, "Ench L", 10, 0, 0, {T: 10}, used_made={L: 10})],
                        ranks=[(ENCH, 225, 300, 0)], crafted={L: 10}, bought={S: 30, T: 10},
                        final_skill={BS: 210, ENCH: 235}))
        trip = Trip(225, ENCH, "rank", "Enchanting rank to 300")
        self.assertEqual(bring_list(p, gd, trip, None, trainer_trips="one_go"), (235, [(T, 10, "mail"), (L, 10, "yours")]))
        self.assertEqual(bring_list(p, gd, trip, None), (235, [(T, 10, "mail")]))  # as needed: as before
        self.assertIn(f"10 {gd.name(L)} (yours)", bring_text(p, gd, trip, None, trainer_trips="one_go"))

    def test_one_go_lists_what_the_other_profession_makes_later(self):
        # Enchanting levels from 225 at its trainer; Blacksmithing makes L after that in route order, and Enchanting
        # uses it at 235: not yours yet, listed apart with what it costs on the AH
        from yap_forever.shopping import bring_list, bring_text
        from yap_forever.trips import Trip
        gd = toy.gamedata([toy.recipe(40, "Make L", BS, {S: 3}, (L, 1)), toy.recipe(51, "Ench T", ENCH, {T: 1}),
                           toy.recipe(50, "Ench L", ENCH, {L: 1, T: 1})])
        p = orange(Plan(steps=[Step(ENCH, 225, 235, 51, "Ench T", 10, 0, 0, {T: 10}),
                               Step(BS, 200, 210, 40, "Make L", 10, 0, 0, {S: 30}),
                               Step(ENCH, 235, 245, 50, "Ench L", 10, 0, 0, {T: 10}, used_made={L: 10})],
                        ranks=[(ENCH, 225, 300, 0)], crafted={L: 10}, bought={S: 30, T: 20},
                        final_skill={BS: 210, ENCH: 245}))
        for i in (T, L):
            gd.items[i].stack = 20
        trip = Trip(225, ENCH, "rank", "Enchanting rank to 300")
        self.assertEqual(bring_list(p, gd, trip, None, trainer_trips="one_go"),
                         (245, [(T, 20, "mail"), (L, 10, f"later:{BS}")]))
        priced = bring_text(p, gd, trip, None, trainer_trips="one_go", market=toy.market({L: [(250, 100)]}))
        self.assertIn("so buy and collect before you go. Made later by your Blacksmithing on this route: 10 Copper Rod: "
                      "craft those rows before you go, or buy them on the AH (about 25s).", priced)
        self.assertNotIn("(yours)", priced)
        self.assertIn("(2 bag slots)", priced)  # 20 Iron Bar and 10 rods, stacks of 20
        unpriced = bring_text(p, gd, trip, None, trainer_trips="one_go", market=toy.market({}))
        self.assertTrue(unpriced.endswith("Made later by your Blacksmithing on this route: 10 Copper Rod: craft those "
                                          "rows before you go, or buy them on the AH."), unpriced)
        from yap_forever.guide import render_guide
        text = render_guide(p, gd, toy.market({L: [(250, 100)]}), toy.stock(skills={ENCH: 225, BS: 200}),
                            {ENCH: 245, BS: 210}, trainer_trips="one_go")
        self.assertIn("or buy them on the AH (about 25s).", text)  # the guide passes today's prices

    def test_one_go_extra_crafts_for_the_other_profession_are_not_made_here(self):
        # Blacksmithing made 2 L before the trip; at the trainer Enchanting uses them (225-230), then makes L at
        # 230-235, its extra crafts for Blacksmithing's later row: the 2 L are still yours to bring
        from yap_forever.shopping import bring_list, route_rows
        from yap_forever.trips import Trip
        gd = toy.gamedata([toy.recipe(40, "Make 2 L", BS, {S: 3}, (L, 2)), toy.recipe(53, "BS L", BS, {L: 1}),
                           toy.recipe(50, "Ench L", ENCH, {L: 1, T: 1}), toy.recipe(52, "Ench make L", ENCH, {T: 1}, (L, 1))])
        p = orange(Plan(steps=[Step(BS, 200, 201, 40, "Make 2 L", 1, 0, 0, {S: 3}),
                               Step(ENCH, 225, 230, 50, "Ench L", 2, 0, 0, {T: 2}, used_made={L: 2}),
                               Step(ENCH, 230, 235, 52, "Ench make L", 1, 0, 0, {T: 1}),
                               Step(BS, 201, 204, 53, "BS L", 3, 0, 0, used_made={L: 3})],
                        ranks=[(ENCH, 225, 300, 0)], crafted={L: 3}, bought={S: 3, T: 3},
                        final_skill={BS: 204, ENCH: 235}))
        self.assertEqual([r["more"] for r in route_rows(p, gd)], [0, 0, 2, 0])  # the extra crafts feed BS
        trip = Trip(225, ENCH, "rank", "Enchanting rank to 300")
        self.assertIn((L, 2, "yours"), bring_list(p, gd, trip, None, trainer_trips="one_go")[1])

    def test_one_go_lists_disenchants_of_greens_made_later(self):
        # the dust Enchanting uses at 230-240 comes from belts Blacksmithing makes after the trip, disenchanted at 231
        from yap_forever.disenchant import de_yield
        from yap_forever.shopping import bring_list
        from yap_forever.trips import Trip
        belt = toy.BELT
        gd = toy.gamedata([toy.recipe(41, "Make belt", BS, {S: 2}, (belt, 1)), toy.recipe(51, "Ench T", ENCH, {T: 1}),
                           toy.recipe(54, "Ench dust", ENCH, {toy.DUST: 1})])
        dust = de_yield(gd.items[belt])[toy.DUST] * 20
        use = int(dust)
        p = orange(Plan(steps=[Step(ENCH, 225, 230, 51, "Ench T", 5, 0, 0, {T: 5}),
                               Step(BS, 210, 230, 41, "Make belt", 20, 0, 0, {S: 40}),
                               Step(ENCH, 230, 240, 54, "Ench dust", use, 0, 0, used_made={toy.DUST: use})],
                        ranks=[(ENCH, 225, 300, 0)], bought={S: 40, T: 5}, final_skill={BS: 230, ENCH: 240},
                        events=[f"Enchanting 231: disenchant 20 {gd.name(belt)}"]))
        trip = Trip(225, ENCH, "rank", "Enchanting rank to 300")
        self.assertIn((toy.DUST, use, f"later:{BS}"), bring_list(p, gd, trip, None, trainer_trips="one_go")[1])
        p.events = [f"Enchanting 225: disenchant 20 {gd.name(belt)} from your bank"]  # disenchanted before you go
        self.assertIn((toy.DUST, use, "yours"), bring_list(p, gd, trip, None, trainer_trips="one_go")[1])

    def test_one_go_splits_the_other_professions_run_at_the_trip(self):
        # Blacksmithing's Make L run is 200-205 before the trip in route order and 205-210 after it: half is yours
        from yap_forever.shopping import bring_list
        from yap_forever.trips import Trip
        gd = toy.gamedata([toy.recipe(40, "Make L", BS, {S: 3}, (L, 1)), toy.recipe(51, "Ench T", ENCH, {T: 1}),
                           toy.recipe(50, "Ench L", ENCH, {L: 1, T: 1})])
        p = orange(Plan(steps=[Step(BS, 200, 205, 40, "Make L", 5, 0, 0, {S: 15}),
                               Step(ENCH, 225, 235, 51, "Ench T", 10, 0, 0, {T: 10}),
                               Step(BS, 205, 210, 40, "Make L", 5, 0, 0, {S: 15}),
                               Step(ENCH, 235, 245, 50, "Ench L", 10, 0, 0, {T: 10}, used_made={L: 10})],
                        ranks=[(ENCH, 225, 300, 0)], crafted={L: 10}, bought={S: 30, T: 20},
                        final_skill={BS: 210, ENCH: 245}))
        trip = Trip(225, ENCH, "rank", "Enchanting rank to 300")
        self.assertEqual(bring_list(p, gd, trip, None, trainer_trips="one_go"),
                         (245, [(T, 20, "mail"), (L, 5, "yours"), (L, 5, f"later:{BS}")]))
        self.assertEqual(bring_list(p, gd, trip, None), (245, [(T, 20, "mail")]))  # as needed: as before

    def test_one_go_disenchants_split_by_when_the_greens_were_made(self):
        # belts 210-220 before the trip and 220-230 after it, all disenchanted at Enchanting 231: half the dust is
        # yours, half made later
        from yap_forever.disenchant import de_yield
        from yap_forever.shopping import bring_list
        from yap_forever.trips import Trip
        belt = toy.BELT
        gd = toy.gamedata([toy.recipe(41, "Make belt", BS, {S: 2}, (belt, 1)), toy.recipe(51, "Ench T", ENCH, {T: 1}),
                           toy.recipe(54, "Ench dust", ENCH, {toy.DUST: 1})])
        per = de_yield(gd.items[belt])[toy.DUST]
        use = int(per * 20)
        p = orange(Plan(steps=[Step(BS, 210, 220, 41, "Make belt", 10, 0, 0, {S: 20}),
                               Step(ENCH, 225, 230, 51, "Ench T", 5, 0, 0, {T: 5}),
                               Step(BS, 220, 230, 41, "Make belt", 10, 0, 0, {S: 20}),
                               Step(ENCH, 230, 240, 54, "Ench dust", use, 0, 0, used_made={toy.DUST: use})],
                        ranks=[(ENCH, 225, 300, 0)], bought={S: 40, T: 5}, final_skill={BS: 230, ENCH: 240},
                        events=[f"Enchanting 231: disenchant 20 {gd.name(belt)}"]))
        trip = Trip(225, ENCH, "rank", "Enchanting rank to 300")
        items = bring_list(p, gd, trip, None, trainer_trips="one_go")[1]
        before = per * 10  # the oldest belts are disenchanted first: those made before the trip
        dust = [x for x in items if x[0] == toy.DUST]
        self.assertEqual([src for _i, _n, src in dust], ["yours", f"later:{BS}"])
        self.assertEqual(sum(n for _i, n, _src in dust), use)  # whole items, rounded up once
        self.assertLess(abs(dust[0][1] - before), 1)

    def test_one_go_disenchant_inside_a_merged_run_finds_its_greens(self):
        # Enchanting's dust run 230-240 is one row placed before the belts Blacksmithing makes after the trip, so the
        # disenchant at 236 comes before the belt row: the dust is still made later, not yours
        from yap_forever.disenchant import de_yield
        from yap_forever.shopping import bring_list
        from yap_forever.trips import Trip
        belt = toy.BELT
        gd = toy.gamedata([toy.recipe(41, "Make belt", BS, {S: 2}, (belt, 1)), toy.recipe(51, "Ench T", ENCH, {T: 1}),
                           toy.recipe(54, "Ench dust", ENCH, {toy.DUST: 1})])
        use = int(de_yield(gd.items[belt])[toy.DUST] * 20)
        p = orange(Plan(steps=[Step(ENCH, 225, 230, 51, "Ench T", 5, 0, 0, {T: 5}),
                               Step(ENCH, 230, 235, 54, "Ench dust", 1, 0, 0, used_made={toy.DUST: 1}),
                               Step(BS, 210, 230, 41, "Make belt", 20, 0, 0, {S: 40}),
                               Step(ENCH, 235, 240, 54, "Ench dust", use - 1, 0, 0, used_made={toy.DUST: use - 1})],
                        ranks=[(ENCH, 225, 300, 0)], bought={S: 40, T: 5}, final_skill={BS: 230, ENCH: 240},
                        events=[f"Enchanting 236: disenchant 20 {gd.name(belt)}"]))
        trip = Trip(225, ENCH, "rank", "Enchanting rank to 300")
        items = bring_list(p, gd, trip, None, trainer_trips="one_go")[1]
        self.assertEqual([x for x in items if x[0] == toy.DUST], [(toy.DUST, use, f"later:{BS}")])

    def test_one_go_disenchant_before_the_trip_uses_up_its_greens(self):
        # belts made before an Enchanting trip are disenchanted before it (at 220); the belts Blacksmithing makes after
        # it are disenchanted at 231: that dust is made later, not yours
        from yap_forever.disenchant import de_yield
        from yap_forever.shopping import bring_list
        from yap_forever.trips import Trip
        belt = toy.BELT
        gd = toy.gamedata([toy.recipe(41, "Make belt", BS, {S: 2}, (belt, 1)), toy.recipe(51, "Ench T", ENCH, {T: 1}),
                           toy.recipe(54, "Ench dust", ENCH, {toy.DUST: 1})])
        use = int(de_yield(gd.items[belt])[toy.DUST] * 10)
        p = orange(Plan(steps=[Step(BS, 210, 220, 41, "Make belt", 10, 0, 0, {S: 20}),
                               Step(ENCH, 215, 225, 54, "Ench dust", use, 0, 0, used_made={toy.DUST: use}),
                               Step(ENCH, 225, 230, 51, "Ench T", 5, 0, 0, {T: 5}),
                               Step(BS, 220, 230, 41, "Make belt", 10, 0, 0, {S: 20}),
                               Step(ENCH, 230, 240, 54, "Ench dust", use, 0, 0, used_made={toy.DUST: use})],
                        ranks=[(ENCH, 225, 300, 0)], bought={S: 40, T: 5}, final_skill={BS: 230, ENCH: 240},
                        events=[f"Enchanting 220: disenchant 10 {gd.name(belt)}",
                                f"Enchanting 231: disenchant 10 {gd.name(belt)}"]))
        trip = Trip(225, ENCH, "rank", "Enchanting rank to 300")
        items = bring_list(p, gd, trip, None, trainer_trips="one_go")[1]
        self.assertEqual([x for x in items if x[0] == toy.DUST], [(toy.DUST, use, f"later:{BS}")])

    def test_one_go_bank_disenchant_before_the_trip_takes_no_greens_made_in_it(self):
        # a Blacksmithing trip whose stretch uses dust from 20 bank belts disenchanted at Enchanting 50, long before;
        # Blacksmithing also makes that belt in the stretch (to sell): the dust is yours, from before the trip
        from yap_forever.disenchant import de_yield
        from yap_forever.shopping import bring_list
        from yap_forever.trips import Trip
        belt = toy.BELT
        gd = toy.gamedata([toy.recipe(41, "Make belt", BS, {S: 2}, (belt, 1)), toy.recipe(51, "Ench T", ENCH, {T: 1}),
                           toy.recipe(56, "Dust bar", BS, {toy.DUST: 1})])
        use = int(de_yield(gd.items[belt])[toy.DUST] * 20)
        p = orange(Plan(steps=[Step(ENCH, 50, 60, 51, "Ench T", 10, 0, 0, {T: 10}),
                               Step(BS, 225, 230, 41, "Make belt", 20, 0, 0, {S: 40}),
                               Step(BS, 230, 235, 56, "Dust bar", use, 0, 0, used_made={toy.DUST: use})],
                        ranks=[(BS, 225, 300, 0)], bought={S: 40, T: 10}, final_skill={BS: 235, ENCH: 60},
                        events=[f"Enchanting 50: disenchant 20 {gd.name(belt)} from your bank"]))
        trip = Trip(225, BS, "rank", "Blacksmithing rank to 300")
        self.assertEqual(bring_list(p, gd, trip, None, trainer_trips="one_go"),
                         (235, [(S, 40, "mail"), (toy.DUST, use, "yours")]))

    def test_one_go_counts_demand_beyond_its_own_crafts(self):
        # the stretch makes 2 L (1 and 1 more for the next row) and that row asks for 3 (the buffer): the one it
        # doesn't make is yours, not dropped
        from yap_forever.shopping import _own_sources, route_rows
        from yap_forever.trips import Trip
        gd = toy.gamedata([toy.recipe(52, "Ench make L", ENCH, {T: 1}, (L, 1)), toy.recipe(50, "Ench L", ENCH, {L: 1})])
        p = orange(Plan(steps=[Step(ENCH, 225, 226, 52, "Ench make L", 1, 0, 0, {T: 1}),
                               Step(ENCH, 226, 228, 50, "Ench L", 2, 0, 0, used_made={L: 2})],
                        ranks=[(ENCH, 225, 300, 0)], bought={T: 1}, final_skill={ENCH: 228}))
        every = route_rows(p, gd)
        every[1]["earlier"][L] = 3  # more than the walk finds
        trip = Trip(225, ENCH, "rank", "Enchanting rank to 300")
        self.assertEqual(_own_sources(p, gd, every, 0, every, trip), ({L: 1}, {}))

    def test_bring_text_with_only_made_later_items(self):
        from yap_forever.shopping import bring_text
        from yap_forever.trips import Trip
        gd = toy.gamedata([toy.recipe(40, "Make L", BS, {S: 3}, (L, 1)), toy.recipe(55, "Ench free", ENCH, {}),
                           toy.recipe(50, "Ench L", ENCH, {L: 1})])
        p = orange(Plan(steps=[Step(ENCH, 225, 226, 55, "Ench free", 1, 0, 0),
                               Step(BS, 200, 210, 40, "Make L", 10, 0, 0, {S: 30}),
                               Step(ENCH, 226, 236, 50, "Ench L", 10, 0, 0, used_made={L: 10})],
                        ranks=[(ENCH, 225, 300, 0)], crafted={L: 10}, bought={S: 30}, final_skill={BS: 210, ENCH: 236}))
        text = bring_text(p, gd, Trip(225, ENCH, "rank", "Enchanting rank to 300"), None, trainer_trips="one_go")
        self.assertTrue(text.startswith(" Bring enough to craft to 236 at the trainer ("), text)
        self.assertIn("Made later by your Blacksmithing on this route: 10 Copper Rod:", text)

    def pattern_plan(self, how, at=235):
        # an Enchanting trip to a remote Master trainer at 225 (the Annora case): the stretch to 245 learns
        # pattern 53 at `at`, bought on the AH (or from a vendor, with Favor, from your bank, mailed by an alt)
        gd = toy.gamedata([toy.recipe(51, "Ench T", ENCH, {T: 1}),
                           toy.recipe(53, "Ench P", ENCH, {T: 1}, source="favor" if how == "favor" else "scroll",
                                      scroll=toy.SCROLL, req=230)])
        p = orange(Plan(steps=[Step(ENCH, 225, 235, 51, "Ench T", 10, 0, 0, {T: 10}),
                               Step(ENCH, 235, 245, 53, "Ench P", 10, 0, 0, {T: 10})],
                        ranks=[(ENCH, 225, 300, 0)], bought={T: 20}, final_skill={ENCH: 245},
                        learn_log=[(ENCH, at, 53, how)],
                        used_mail={toy.SCROLL: [("Altname", 1)]} if how == "mail" else {}))
        gd.items[T].stack = 20
        return p, gd

    def ench_trip(self):
        from yap_forever.trips import Trip
        return Trip(225, ENCH, "rank", "Enchanting rank to 300")

    def test_one_go_brings_the_stretchs_patterns(self):
        from yap_forever.shopping import bring_list, bring_text
        said = {"ah": "from the AH", "vendor": "from a pattern vendor", "favor": "from the Merchant's Favor vendor",
                "owned": "from the bank", "mail": "mail from Altname"}
        for how, where in said.items():
            p, gd = self.pattern_plan(how)
            reach, items = bring_list(p, gd, self.ench_trip(), None, trainer_trips="one_go")
            self.assertEqual(reach, 245, how)
            self.assertEqual(items[0], (T, 20, "mail"), how)
            self.assertEqual([(i, n) for i, n, _src in items[1:]], [(toy.SCROLL, 1)], how)
            text = bring_text(p, gd, self.ench_trip(), None, trainer_trips="one_go")
            self.assertIn(f" Bring: 20 Iron Bar (from the mail), 1 Plans: Something ({where}): enough to craft to 245 "
                          "at the trainer (2 bag slots)", text)  # the pattern takes a slot of its own
            # as needed: as before
            self.assertEqual(bring_list(p, gd, self.ench_trip(), None), (245, [(T, 20, "mail")]), how)
            self.assertNotIn("Plans: Something", bring_text(p, gd, self.ench_trip(), None))

    def test_one_go_patterns_are_those_learned_inside_the_stretch(self):
        from yap_forever.shopping import bring_list
        # from the trip's skill to its end; the route's end (245, no later rank) is in it: a goal pattern is learned there
        for at, brought in ((225, True), (244, True), (220, False), (245, True), (246, False)):
            p, gd = self.pattern_plan("ah", at)
            items = bring_list(p, gd, self.ench_trip(), None, trainer_trips="one_go")[1]
            self.assertEqual(any(i == toy.SCROLL for i, _n, _src in items), brought, at)
        p, gd = self.pattern_plan("ah")
        for log in ([(BS, 235, 53, "ah")],  # the other profession's pattern: not this trip's
                    [(ENCH, 235, 53, "trainer")]):  # a trainer recipe is learned there, not brought
            p.learn_log = log
            items = bring_list(p, gd, self.ench_trip(), None, trainer_trips="one_go")[1]
            self.assertNotIn(toy.SCROLL, [i for i, _n, _src in items], log)

    def test_one_go_lower_goal_leaves_out_the_patterns_above_it(self):
        # 20 Iron Bar and the pattern are 2 slots, + 10 kept free: 11 bag slots fit the first row (to 235) only, and
        # the pattern learned at 235 is not part of that list
        from yap_forever.shopping import _bring_items, _bring_rows, bring_text
        p, gd = self.pattern_plan("ah")
        rows, left, mail, ctx = _bring_rows(p, gd, self.ench_trip(), 11, None, 0, None, None, "one_go")
        self.assertEqual(_bring_items(p, gd, rows[:1], left, mail, "one_go", ctx, self.ench_trip()), [(T, 10, "mail")])
        text = bring_text(p, gd, self.ench_trip(), 11, trainer_trips="one_go")
        self.assertTrue(text.endswith(" This needs 12 free slots and you have 11: get bigger bags, bank what this "
                                      "stretch doesn't need, or set a lower goal (for example 235) so it fits."), text)

    def test_one_go_folds_pattern_trips_inside_the_stretch(self):
        # the vendor (or Favor) pattern learned at 235 is on the trip's bring list: no trip of its own while you are away
        from yap_forever.guide import render_guide
        from yap_forever.shopping import bring_list
        from yap_forever.trips import stretch_end, trips
        start = {ENCH: 225}
        for how in ("vendor", "favor"):
            p, gd = self.pattern_plan(how)
            # the fold reads the stretch to stretch_end, the bring list to its reach: the same skill in one go
            self.assertEqual(bring_list(p, gd, self.ench_trip(), None, trainer_trips="one_go")[0],
                             stretch_end(p, ENCH, 225))
            self.assertEqual([t.kind for t in trips(p, gd, start)], ["rank", how], how)  # as needed: as before
            self.assertEqual([t.kind for t in trips(p, gd, start, "one_go")], ["rank"], how)
            text = render_guide(p, gd, toy.market({T: [(10, 1000)]}), toy.stock(skills=start), {ENCH: 245},
                                trainer_trips="one_go")
            rows = [line for line in text.splitlines() if line.startswith("- **Trip:**")]
            self.assertEqual(len(rows), 1, rows)
            self.assertIn("1 Plans: Something (from ", rows[0])
        p, gd = self.pattern_plan("vendor", 220)  # learned before the trip: still a trip of its own
        self.assertEqual([t.kind for t in trips(p, gd, start, "one_go")], ["vendor", "rank"])

    def goal_pattern_plan(self, how):
        # the goal recipe is a pattern, learned at the route's end (235) and crafted once there, as
        # planner._craft_once_step does: Step(prof, s, s, ..., crafts=1)
        gd = toy.gamedata([toy.recipe(51, "Ench T", ENCH, {T: 1}),
                           toy.recipe(53, "Ench Goal", ENCH, {T: 1}, source="scroll", scroll=toy.SCROLL, req=235)])
        gd.items[T].stack = 20
        p = orange(Plan(steps=[Step(ENCH, 225, 235, 51, "Ench T", 10, 0, 0, {T: 10}),
                               Step(ENCH, 235, 235, 53, "Ench Goal", 1, 0, 0, {T: 1})],
                        ranks=[(ENCH, 225, 300, 0)], bought={T: 11}, final_skill={ENCH: 235},
                        learn_log=[(ENCH, 235, 53, how)]))
        return p, gd

    def test_one_go_brings_a_goal_pattern_learned_at_the_end(self):
        from yap_forever.shopping import bring_list, bring_text
        p, gd = self.goal_pattern_plan("ah")
        self.assertEqual(bring_list(p, gd, self.ench_trip(), None, trainer_trips="one_go"),
                         (235, [(T, 11, "mail"), (toy.SCROLL, 1, "pattern:ah")]))
        self.assertIn(" Bring: 11 Iron Bar (from the mail), 1 Plans: Something (from the AH): enough to craft to 235 at "
                      "the trainer (2 bag slots)", bring_text(p, gd, self.ench_trip(), None, trainer_trips="one_go"))

    def test_one_go_folds_a_vendor_goal_pattern_at_the_end(self):
        from yap_forever.compare import compare
        from yap_forever.guide import render_guide
        from yap_forever.trips import trips
        p, gd = self.goal_pattern_plan("vendor")
        start, market = {ENCH: 225}, toy.market({T: [(10, 1000)]})
        self.assertEqual([(t.kind, t.skill) for t in trips(p, gd, start)], [("rank", 225), ("vendor", 235)])  # as needed
        self.assertEqual([(t.kind, t.skill) for t in trips(p, gd, start, "one_go")], [("rank", 225)])
        text = render_guide(p, gd, market, toy.stock(skills=start), {ENCH: 235}, trainer_trips="one_go")
        rows = [line for line in text.splitlines() if line.startswith("- **Trip:**")]
        self.assertEqual(len(rows), 1, rows)
        self.assertIn("1 Plans: Something (from a pattern vendor)", rows[0])
        self.assertIn("| Trips away | 1 |", compare({"gold": p}, gd, market, toy.stock(skills=start),
                                                     trainer_trips="one_go"))

    def test_one_go_pattern_at_a_rank_boundary_is_listed_once(self):
        # Artisan at 150 (its stretch ends at the Master training at 200), Master at 200: a pattern learned at 200
        # belongs to the Master trip's stretch only, and as a vendor pattern it is no trip of its own
        from yap_forever.shopping import bring_list
        from yap_forever.trips import Trip, trips
        gd = toy.gamedata([toy.recipe(51, "Ench T", ENCH, {T: 1}),
                           toy.recipe(53, "Ench P", ENCH, {T: 1}, source="scroll", scroll=toy.SCROLL, req=200)])
        for how in ("ah", "vendor"):
            p = orange(Plan(steps=[Step(ENCH, 150, 200, 51, "Ench T", 50, 0, 0, {T: 50}),
                                   Step(ENCH, 200, 210, 53, "Ench P", 10, 0, 0, {T: 10})],
                            ranks=[(ENCH, 150, 225, 0), (ENCH, 200, 300, 0)], bought={T: 60}, final_skill={ENCH: 210},
                            learn_log=[(ENCH, 200, 53, how)]))
            got = [[i for i, _n, _src in bring_list(p, gd, Trip(s, ENCH, "rank", f"Enchanting rank to {cap}"), None,
                                                    trainer_trips="one_go")[1]]
                   for s, cap in ((150, 225), (200, 300))]
            self.assertEqual([x.count(toy.SCROLL) for x in got], [0, 1], how)
            self.assertEqual([t.kind for t in trips(p, gd, {ENCH: 150}, "one_go")], ["rank", "rank"], how)

    def de_mail_plan(self, suffix):
        # Blacksmithing makes 20 belts after Enchanting's trip; Enchanting disenchants 20 belts at 231 and uses the dust
        from yap_forever.disenchant import de_yield
        belt = toy.BELT
        gd = toy.gamedata([toy.recipe(41, "Make belt", BS, {S: 2}, (belt, 1)), toy.recipe(51, "Ench T", ENCH, {T: 1}),
                           toy.recipe(54, "Ench dust", ENCH, {toy.DUST: 1})])
        per = de_yield(gd.items[belt])[toy.DUST]
        use = int(per * 20)
        p = orange(Plan(steps=[Step(ENCH, 225, 230, 51, "Ench T", 5, 0, 0, {T: 5}),
                               Step(BS, 210, 230, 41, "Make belt", 20, 0, 0, {S: 40}),
                               Step(ENCH, 230, 240, 54, "Ench dust", use, 0, 0, used_made={toy.DUST: use})],
                        ranks=[(ENCH, 225, 300, 0)], bought={S: 40, T: 5}, final_skill={BS: 230, ENCH: 240},
                        events=[f"Enchanting 231: disenchant 20 {gd.name(belt)}{suffix}"]))
        return p, gd, per, use

    def test_disenchant_of_mailed_greens_parses(self):
        # the planner's two mail forms (planner._release_held): every green mailed, or some your own
        from yap_forever.shopping import _bring_rows, _de_supply
        for suffix, mine in ((" (mail from Altname)", 0), (" (12 your own, 8 mail from Altname)", 12)):
            p, gd, per, _use = self.de_mail_plan(suffix)
            every, at = _bring_rows(p, gd, self.ench_trip(), None, None, 0, None, None, "one_go")[3]
            got = [(o, m, round(n, 6)) for lots in _de_supply(p, gd, every, at, self.ench_trip()).values()
                   for o, m, n in lots if m == toy.DUST]
            want = ([(BS, toy.DUST, round(per * mine, 6))] if mine else []) + [("pre", toy.DUST, round(per * (20 - mine), 6))]
            self.assertEqual(got, want, suffix)

    def test_one_go_mixed_mail_disenchant_splits_the_dust(self):
        from yap_forever.shopping import bring_list
        p, gd, per, use = self.de_mail_plan(" (12 your own, 8 mail from Altname)")
        dust = [x for x in bring_list(p, gd, self.ench_trip(), None, trainer_trips="one_go")[1] if x[0] == toy.DUST]
        self.assertEqual([src for _i, _n, src in dust], ["yours", f"later:{BS}"])  # the mailed belts' dust is yours
        self.assertEqual(sum(n for _i, n, _src in dust), use)
        self.assertLess(abs(dust[0][1] - per * 8), 1)

    def test_as_needed_unchanged(self):
        # the outputs main (e94cb24) gives for this fixture, before trainer_trips existed
        from yap_forever.guide import render_guide
        from yap_forever.shopping import bring_list, bring_text
        from yap_forever.trips import trips
        p, gd = self.recipe_visit_plan()
        start = {BS: 225}
        text = (" Bring: 20 Copper Bar (from the bank), 40 Copper Bar (from the mail): enough to craft to 235 at the "
                "trainer (3 bag slots); the town may have no auction house, mailbox or bank, so buy and collect before "
                "you go.")
        for bags in (None, 16):
            for kw in ({}, {"trainer_trips": "as_needed"}):
                self.assertEqual(bring_list(p, gd, self.trip(), bags, start_skills=start, **kw),
                                 (235, [(S, 20, "bank"), (S, 40, "mail")]))
                self.assertEqual(bring_text(p, gd, self.trip(), bags, start_skills=start, **kw), text)
        for found in (trips(p, gd, start), trips(p, gd, start, "as_needed")):
            self.assertEqual([(x.kind, x.skill, x.what, x.cost, x.cap, x.spells) for x in found],
                             [("rank", 225, "Blacksmithing rank to 300", 9000, 300, ()), ("recipe", 235, "BS two", 0, 300, (2,))])
        args = (p, gd, toy.market({S: [(10, 1000)]}), toy.stock(skills=start), {BS: 300})
        for text in (render_guide(*args), render_guide(*args, trainer_trips="as_needed")):
            self.assertEqual([line for line in text.splitlines() if line.startswith("- **Trip:**")],
                             ["- **Trip:** Blacksmithing rank to 300: the trainer is in a set town (the planner doesn't "
                              "say where yet). Bring: 60 Copper Bar (from the mail): enough to craft to 235 at the trainer "
                              "(3 bag slots); the town may have no auction house, mailbox or bank, so buy and collect "
                              "before you go.",
                              "- **Trip:** back to the Master Blacksmith in a set town (the planner doesn't say where "
                              "yet), at 235 for BS two."])

    def warning(self, p, gd, bags, trainer_trips="one_go"):
        from yap_forever.shopping import bring_text
        text = bring_text(p, gd, self.trip(), bags, trainer_trips=trainer_trips)
        return text[text.index(" This needs"):] if " This needs" in text else ""

    def test_bag_warning_when_too_wide(self):
        # one go from 225: 60 S, 80 T and 55 rods in stacks of 20 are 10 bag slots, + 10 kept free for crafts
        p, gd = rank_trip_plan()
        self.assertEqual(CRAFT_ROOM, 10)
        self.assertEqual(self.warning(p, gd, 16),
                         " This needs 20 free slots and you have 16: get bigger bags, bank what this stretch doesn't "
                         "need, or set a lower goal (for example 235) so it fits.")
        self.assertEqual(self.warning(p, gd, 20), "")  # just fits
        self.assertIn("This needs 20 free slots and you have 19:", self.warning(p, gd, 19))
        # even the first row (3 slots) doesn't fit in 2: no example
        self.assertEqual(self.warning(p, gd, 12),
                         " This needs 20 free slots and you have 12: get bigger bags, bank what this stretch doesn't "
                         "need, or set a lower goal so it fits.")
        # as needed the list is cut to the bags: a warning only when its first row is too wide on its own
        self.assertEqual(self.warning(p, gd, 16, "as_needed"), "")
        self.assertEqual(self.warning(p, gd, 12, "as_needed"),
                         " This needs 13 free slots and you have 12: get bigger bags, bank what this stretch doesn't "
                         "need, or set a lower goal so it fits.")

    def test_no_bag_warning_without_bag_slots(self):
        p, gd = rank_trip_plan()
        for trips in ("one_go", "as_needed"):
            self.assertEqual(self.warning(p, gd, None, trips), "")
            self.assertEqual(self.warning(p, gd, 0, trips), "")

    def test_lower_goal_example_fits(self):
        p, gd = rank_trip_plan()
        self.assertIn("(for example 235)", self.warning(p, gd, 16))
        p.steps = [st for st in p.steps if st.skill_to <= 235]  # the route to that goal
        p.final_skill = {BS: 235}
        self.assertEqual(self.warning(p, gd, 16), "")

    def test_one_go_bring_list_takes_a_run_that_crosses_the_trip(self):
        # one recipe from 210 to 235, trained to 300 at 225: one go brings what 225-235 takes, not only later rows
        from yap_forever.shopping import bring_list
        gd = toy.gamedata([toy.recipe(1, "A", BS, {S: 1}), toy.recipe(2, "B", BS, {T: 1})])
        p = orange(Plan(steps=[Step(BS, 210, 225, 1, "A", 15, 0, 0, {S: 15}), Step(BS, 225, 235, 1, "A", 10, 0, 0, {S: 10}),
                               Step(BS, 235, 245, 2, "B", 10, 0, 0, {T: 10})],
                        ranks=[(BS, 225, 300, 0)], bought={S: 25, T: 10}, final_skill={BS: 245}))
        self.assertEqual(bring_list(p, gd, self.trip(), None, trainer_trips="one_go"),
                         (245, [(S, 10, "mail"), (T, 10, "mail")]))
        self.assertEqual(bring_list(p, gd, self.trip(), None), (245, [(T, 10, "mail")]))  # as needed: as before

    def test_one_go_bring_list_takes_a_run_that_crosses_the_stretch_end(self):
        # Artisan at 140, Master at 200; recipe A runs 190-215 across the Master training: the 140 trip brings A to 200
        from yap_forever.shopping import bring_list
        from yap_forever.trips import Trip
        gd = toy.gamedata([toy.recipe(1, "A", BS, {S: 1}), toy.recipe(2, "B", BS, {T: 1})])
        p = orange(Plan(steps=[Step(BS, 140, 190, 2, "B", 50, 0, 0, {T: 50}), Step(BS, 190, 200, 1, "A", 10, 0, 0, {S: 10}),
                               Step(BS, 200, 215, 1, "A", 15, 0, 0, {S: 15})],
                        ranks=[(BS, 140, 225, 0), (BS, 200, 300, 0)], bought={S: 25, T: 50}, final_skill={BS: 215}))
        trip = Trip(140, BS, "rank", "Blacksmithing rank to 225")
        self.assertEqual(bring_list(p, gd, trip, None, trainer_trips="one_go"), (200, [(S, 10, "mail"), (T, 50, "mail")]))


if __name__ == "__main__":
    unittest.main()


class BankNeverOverdrawnTests(unittest.TestCase):
    def test_buffer_on_bank_items_is_bought(self):
        from yap_forever.shopping import render_shopping
        gd = toy.gamedata([toy.recipe(1, "BS basic", BS, {S: 1}, t=(1, 1, 300, 600))])  # yellow: buffered
        st = Step(BS, 10, 20, 1, "BS basic", 100, 0, 0, {S: 100}, from_stock={S: 100})
        p = Plan(steps=[st], final_skill={BS: 20})
        import dataclasses
        lines, _ = render_shopping(p, gd, toy.market({S: [(10, 1000)]}),
                                   dataclasses.replace(toy.stock({S: 100}), bag_slots=200))
        trip = next(l for l in lines if l.startswith("- 📬"))
        self.assertIn("From the bank: 100 Copper Bar", trip)
        self.assertIn("From the mail: 15 Copper Bar", trip)
        self.assertIn("| Copper Bar | 15 | AH |", "\n".join(lines))


class BankAcrossTripsTests(unittest.TestCase):
    def test_bank_used_once_across_trips(self):
        import dataclasses
        from yap_forever.shopping import render_shopping
        gd = toy.gamedata([toy.recipe(1, "A", BS, {S: 1}), toy.recipe(2, "B", BS, {S: 1})])
        p = orange(Plan(steps=[Step(BS, 1, 30, 1, "A", 30, 0, 0, {S: 30}, from_stock={S: 20}),
                               Step(BS, 30, 60, 2, "B", 30, 0, 0, {S: 30})],
                        bought={S: 40}, final_skill={BS: 60}))
        lines, trips = render_shopping(p, gd, toy.market({S: [(10, 1000)]}),
                                       dataclasses.replace(toy.stock({S: 20}), bag_slots=40))  # 30 a trip
        self.assertEqual(trips, 2)
        text = "\n".join(l for l in lines if l.startswith("- 📬"))
        self.assertEqual(text.count("From the bank"), 1)


class SpareBankTests(unittest.TestCase):
    def test_buffer_taken_from_spare_bank_stock(self):
        import dataclasses
        from yap_forever.shopping import render_shopping
        gd = toy.gamedata([toy.recipe(1, "BS basic", BS, {S: 1}, t=(1, 1, 300, 600))])
        p = Plan(steps=[Step(BS, 10, 20, 1, "BS basic", 100, 0, 0, {S: 100}, from_stock={S: 100})],
                 final_skill={BS: 20})
        lines, _ = render_shopping(p, gd, toy.market({S: [(10, 1000)]}),
                                   dataclasses.replace(toy.stock({S: 150}), bag_slots=200))
        trip = next(l for l in lines if l.startswith("- 📬"))
        self.assertIn("From the bank: 115 Copper Bar", trip)
        self.assertNotIn("From the mail", trip)


class WholeCraftTests(unittest.TestCase):
    """Every count is whole crafts times what one craft takes, so rounding leaves nothing unusable."""

    def test_two_per_craft_buys_whole_crafts(self):
        from yap_forever.shopping import render_shopping
        gd = toy.gamedata([toy.recipe(1, "BS basic", BS, {S: 2})])
        p = orange(Plan(steps=[Step(BS, 1, 100, 1, "BS basic", 133.4, 0, 0, {S: 266.8})],
                        bought={S: 266.8}, final_skill={BS: 100}))
        text = "\n".join(render_shopping(p, gd, toy.market({S: [(10, 1000)]}), toy.stock())[0])
        self.assertIn("| Copper Bar | 268 | AH |", text)  # 134 crafts; 267 would leave 1 unusable

    def test_three_per_craft_is_never_short(self):
        from yap_forever.shopping import route_rows
        gd = toy.gamedata([toy.recipe(1, "BS basic", BS, {S: 3})])
        p = orange(Plan(steps=[Step(BS, 1, 6, 1, "BS basic", 5.2, 0, 0, {S: 15.6})], final_skill={BS: 6}))
        self.assertEqual(route_rows(p, gd)[0]["need"], {S: 18})

    def test_own_crafts_used_before_crafting_more(self):
        from yap_forever.shopping import route_rows
        rows = route_rows(chain_plan(), chain_gd())  # 10 L made at the first row cover the 9 used later
        self.assertEqual(rows[0]["more"], 0)
        self.assertEqual(rows[0]["need"], {S: 30})
        self.assertEqual(rows[2]["need"], {T: 4})
        self.assertEqual(rows[2]["earlier"], {L: 4})

    def test_intermediate_crafted_in_whole_batches(self):
        from yap_forever.shopping import route_rows
        gd = toy.gamedata([toy.recipe(40, "Make L", BS, {S: 3}, (L, 2)), toy.recipe(42, "Make G", BS, {L: 1, T: 1})])
        p = orange(Plan(steps=[Step(BS, 1, 4, 42, "Make G", 3, 0, 0, {T: 3})], crafted={L: 3}, final_skill={BS: 4}))
        row = route_rows(p, gd)[0]
        self.assertEqual(row["need"], {T: 3, S: 6})  # 3 L from 2 crafts of 2
        self.assertEqual(row["here"], {L: 3})

    def test_disenchanted_reagents_are_not_bought(self):
        from yap_forever.shopping import route_rows
        gd = toy.gamedata([toy.recipe(1, "Enchant", 333, {toy.DUST: 2})])
        p = orange(Plan(steps=[Step(333, 1, 5, 1, "Enchant", 4, 0, 0, used_made={toy.DUST: 8})], final_skill={333: 5}))
        row = route_rows(p, gd)[0]
        self.assertEqual(row["need"], {})
        self.assertEqual(row["earlier"], {toy.DUST: 8})

    def test_goal_recipe_on_the_list(self):
        from yap_forever.shopping import render_shopping
        gd = toy.gamedata([toy.recipe(1, "BS basic", BS, {S: 1}), toy.recipe(5, "BS final", BS, {T: 2}, req=20)])
        p = orange(Plan(steps=[Step(BS, 1, 20, 1, "BS basic", 19, 0, 0, {S: 19}),
                               Step(BS, 20, 20, 5, "BS final", 1, 0, 0, {T: 2})], final_skill={BS: 20}))
        text = "\n".join(render_shopping(p, gd, toy.market({S: [(10, 100)], T: [(10, 100)]}), toy.stock())[0])
        self.assertIn("| Iron Bar | 2 | AH |", text)

    def test_row_using_extra_batch_lists_it_as_yours(self):
        from yap_forever.shopping import route_rows
        p = orange(Plan(steps=[Step(BS, 1, 11, 40, "Make L", 10, 0, 0, {S: 30}),
                               Step(BS, 11, 23, 41, "Make K", 12, 0, 0, used_made={L: 12})],
                        crafted={L: 2}, final_skill={BS: 23}))
        rows = route_rows(p, chain_gd())
        self.assertEqual(rows[0]["more"], 2)
        self.assertEqual(rows[0]["need"], {S: 36})
        self.assertEqual(rows[1]["earlier"], {L: 12})


E, GE = toy.ESSENCE, toy.GREATER_ESSENCE


def essence_gd(stack):
    gd = toy.gamedata([toy.recipe(1, "Enchant A", 333, {E: 4}), toy.recipe(2, "Enchant B", 333, {GE: 1})])
    for i in (E, GE):
        gd.items[i].stack = stack
    return gd


class EssencePackingTests(unittest.TestCase):
    """Carried essences are packed 3 lesser -> 1 greater when that saves bag slots."""

    def test_pairs_cover_every_tier(self):
        from yap_forever.disenchant import ESSENCE_PAIRS
        self.assertEqual(ESSENCE_PAIRS, {10938: 10939, 10998: 11082, 11134: 11135, 11174: 11175, 16202: 16203})

    def test_pack_stack_10(self):
        from yap_forever.shopping import carried_slots, pack
        stack = {E: 10, GE: 10}
        self.assertEqual(pack({E: 92}, stack), {GE: 30, E: 2})  # 10 slots -> 4
        self.assertEqual(carried_slots({E: 92}, stack), 4)

    def test_pack_stack_20(self):
        from yap_forever.shopping import carried_slots, pack
        stack = {E: 20, GE: 20}
        self.assertEqual(carried_slots({E: 92}, stack), 3)  # 5 slots -> 2 + 1
        self.assertEqual(sum(pack({E: 92}, stack).get(i, 0) * (3 if i == GE else 1) for i in (E, GE)), 92)

    def test_no_pack_when_it_saves_nothing(self):
        from yap_forever.shopping import pack
        self.assertEqual(pack({E: 20}, {E: 20, GE: 20}), {E: 20})  # 1 slot; packed would be 2
        self.assertEqual(pack({E: 2}, {E: 10, GE: 10}), {E: 2})

    def test_greater_already_carried_shares_its_stacks(self):
        from yap_forever.shopping import carried_slots, pack
        stack = {E: 10, GE: 10}
        self.assertEqual(pack({E: 92, GE: 5}, stack), {GE: 35, E: 2})
        self.assertEqual(carried_slots({E: 92, GE: 5}, stack), 5)

    def plan(self):
        return orange(Plan(steps=[Step(333, 100, 123, 1, "Enchant A", 23, 0, 0, {E: 92})],
                           ranks=[(333, 100, 300, 0)], bought={E: 92}, final_skill={333: 123}))

    def test_bring_text_says_pack_and_slots(self):
        from yap_forever.shopping import bring_text
        from yap_forever.trips import Trip
        gd = essence_gd(10)
        text = bring_text(self.plan(), gd, Trip(100, 333, "rank", "Enchanting rank to 225"), None)
        self.assertIn("92 Lesser Astral Essence (from the mail)", text)
        self.assertIn("pack 90 Lesser Astral Essence into 30 Greater Astral Essence", text)
        self.assertIn("4 bag slots", text)

    def test_bring_text_town_clause_goes_when_the_row_says_what_is_near(self):
        from yap_forever.shopping import bring_text
        from yap_forever.trips import Trip
        trip = Trip(100, 333, "rank", "Enchanting rank to 225")
        clause = "the town may have no auction house, mailbox or bank"
        self.assertIn(clause, bring_text(self.plan(), essence_gd(10), trip, None))
        known = bring_text(self.plan(), essence_gd(10), trip, None, services_known=True)
        self.assertNotIn(clause, known)
        self.assertTrue(known.endswith("); buy and collect before you go."), known)

    def test_bring_list_fits_more_when_packed(self):
        from yap_forever.shopping import bring_list
        from yap_forever.trips import Trip
        gd = essence_gd(10)
        p = orange(Plan(steps=[Step(333, 100, 110, 1, "Enchant A", 10, 0, 0, {E: 40}),
                               Step(333, 110, 120, 2, "Enchant B", 10, 0, 0, {GE: 10}),
                               Step(333, 120, 145, 1, "Enchant A", 13, 0, 0, {E: 52})],
                        bought={E: 92, GE: 10}, final_skill={333: 145}))
        # 15 slots, 10 kept for crafts: unpacked 40 lesser + 10 greater is 5 slots, + 52 lesser is 11;
        # packed: 30 greater (+ 10) and 2 lesser is 5 slots
        reach, items = bring_list(p, gd, Trip(100, 333, "rank", "Enchanting rank to 225"), bag_slots=15)
        self.assertEqual(reach, 145)

    def test_mailbox_trip_counts_packed_slots_and_shopping_is_unchanged(self):
        import dataclasses
        from yap_forever.shopping import render_shopping
        gd = essence_gd(10)
        m = toy.market({E: [(100, 1000)]})
        lines, trips = render_shopping(self.plan(), gd, m, dataclasses.replace(toy.stock(), bag_slots=14))
        self.assertEqual(trips, 1)  # 4 slots packed fit in 14 - 10; unpacked 10 would not
        trip = next(l for l in lines if l.startswith("- 📬"))
        self.assertIn("4 stacks", trip)
        self.assertIn("From the mail: 92 Lesser Astral Essence.", trip)
        self.assertIn("pack 90 Lesser Astral Essence into 30 Greater Astral Essence", trip)
        text = "\n".join(lines)
        self.assertIn("| Lesser Astral Essence | 92 | AH | 92s |", text)
        self.assertIn("**Gold to bring: 92s**", text)


class ReagentBagTests(unittest.TestCase):
    """Normal and reagent bag slots are counted apart: materials fill the reagent bag first."""

    def mats_plan(self):
        """Ten stacks of materials (S, T: 5 stacks each at stack 20) in two rows."""
        gd = toy.gamedata([toy.recipe(1, "Make A", BS, {S: 1}), toy.recipe(2, "Make B", BS, {T: 1})])
        for i in (S, T):
            gd.items[i].stack = 20
        p = orange(Plan(steps=[Step(BS, 1, 101, 1, "Make A", 100, 0, 0, {S: 100}),
                               Step(BS, 101, 201, 2, "Make B", 100, 0, 0, {T: 100})],
                        bought={S: 100, T: 100}, final_skill={BS: 201}))
        return p, gd

    def test_reagents_are_recipe_materials_and_trade_goods_never_gear_patterns_or_tools(self):
        from yap_forever.shopping import reagent_items
        gd = toy.gamedata([toy.recipe(1, "Make", BS, {S: 1, toy.BELT: 1})])
        self.assertEqual(gd.items[toy.SCROLL].class_id, 7)
        gd.items[toy.SCROLL].class_id = 9  # a pattern
        gd.items[toy.ODD].class_id = 0  # not trade goods, in no recipe
        got = reagent_items(gd)
        self.assertIn(S, got)  # a recipe reagent
        self.assertIn(toy.DUST, got)  # trade goods, in no loaded recipe
        self.assertIn(L, got)  # a crafted intermediate (class 7)
        self.assertNotIn(toy.BELT, got)  # gear, even as a reagent
        self.assertNotIn(toy.VEST, got)
        self.assertNotIn(toy.SCROLL, got)  # patterns
        self.assertNotIn(toy.ODD, got)
        self.assertNotIn(toy.HAMMER, got)  # tools
        self.assertNotIn(toy.ROD_TOOL, got)

    def test_split_fills_the_reagent_bag_first(self):
        from yap_forever.shopping import carried_slots, carried_slots_split
        stack = {S: 20, T: 20, toy.BELT: 1}
        counts = {S: 100, T: 100}  # 10 stacks
        self.assertEqual(carried_slots_split(counts, stack, {S, T}, 0), carried_slots(counts, stack))
        self.assertEqual(carried_slots_split(counts, stack, {S, T}, 6), 4)
        self.assertEqual(carried_slots_split(counts, stack, {S, T}, 10), 0)
        self.assertEqual(carried_slots_split(counts, stack, {S, T}, 20), 0)  # spare reagent slots help nothing else

    def test_gear_stays_on_normal_slots(self):
        from yap_forever.shopping import carried_slots_split
        stack = {S: 20, toy.BELT: 1}
        self.assertEqual(carried_slots_split({S: 40, toy.BELT: 3}, stack, {S}, 6), 3)  # belts never in the reagent bag

    def test_packed_essences_count_as_reagents(self):
        from yap_forever.shopping import carried_slots_split
        stack = {E: 10, GE: 10}
        # 92 lesser pack to 30 greater + 2 lesser = 4 stacks, all in a 4-slot reagent bag
        self.assertEqual(carried_slots_split({E: 92}, stack, {E}, 4), 0)
        self.assertEqual(carried_slots_split({E: 92}, stack, {E}, 1), 3)

    def test_group_trips_use_the_reagent_bag(self):
        from yap_forever.shopping import group_trips, route_rows
        p, gd = self.mats_plan()
        rows = route_rows(p, gd)
        stack = {S: 20, T: 20}
        self.assertEqual([len(t) for t in group_trips(rows, 4, stack)], [1, 1])
        self.assertEqual([len(t) for t in group_trips(rows, 4, stack, {S, T}, 6)], [2])  # 6 reagent + 4 normal
        self.assertEqual([len(t) for t in group_trips(rows, 4, stack, {S, T}, 0)], [1, 1])

    def test_zero_reagent_slots_change_nothing(self):
        import dataclasses
        from yap_forever.shopping import carried_slots, carried_slots_split, group_trips, render_shopping, reagent_items, route_rows
        gd, p = chain_gd(), chain_plan()
        stack = {S: 20, T: 20, L: 20}
        for counts in ({S: 100, T: 7}, {S: 1}, {}, {S: 20, T: 20, L: 21}):
            self.assertEqual(carried_slots_split(counts, stack, reagent_items(gd), 0), carried_slots(counts, stack))
        rows = route_rows(p, gd)
        for cap in (1, 2, 4, 40):
            self.assertEqual(group_trips(rows, cap, stack, reagent_items(gd), 0), group_trips(rows, cap, stack))
        m = toy.market({S: [(10, 1000)], T: [(50, 100)]})
        lines, _trips = render_shopping(p, gd, m, dataclasses.replace(toy.stock(), bag_slots=40, reagent_slots=0))
        self.assertNotIn("reagent", "\n".join(lines))

    def test_mailbox_trips_one_with_reagent_bag_two_without(self):
        import dataclasses
        from yap_forever.shopping import render_shopping
        p, gd = self.mats_plan()
        m = toy.market({S: [(10, 1000)], T: [(10, 1000)]})
        base = dataclasses.replace(toy.stock(), bag_slots=CRAFT_ROOM + 4)
        _lines, trips = render_shopping(p, gd, m, base)
        self.assertEqual(trips, 2)
        lines, trips = render_shopping(p, gd, m, dataclasses.replace(base, reagent_slots=6))
        self.assertEqual(trips, 1)
        text = "\n".join(lines)
        self.assertIn("Planned for 14 free bag slots and 6 reagent bag slots", text)
        self.assertIn("10 stacks (4 bag, 6 reagent bag)", text)

    def test_bring_list_uses_the_reagent_bag(self):
        from yap_forever.shopping import bring_list
        p, gd = rank_trip_plan()
        from yap_forever.trips import Trip
        trip = Trip(225, BS, "rank", "Blacksmithing rank to 300")
        # 16 free slots, 10 kept for crafts: 6 normal slots; 3 more rows fit with a 6-slot reagent bag
        base, _ = bring_list(p, gd, trip, bag_slots=16)
        more, _ = bring_list(p, gd, trip, bag_slots=16, reagent_slots=6)
        none, _ = bring_list(p, gd, trip, bag_slots=16, reagent_slots=0)
        self.assertEqual(none, base)
        self.assertGreater(more, base)

    def test_bring_text_names_both_slot_kinds(self):
        from yap_forever.shopping import bring_text
        from yap_forever.trips import Trip
        gd = essence_gd(10)
        plan = EssencePackingTests().plan()
        trip = Trip(100, 333, "rank", "Enchanting rank to 225")
        self.assertIn("(4 bag slots;", bring_text(plan, gd, trip, None))
        self.assertIn("(4 reagent bag slots;", bring_text(plan, gd, trip, None, reagent_slots=6))
        self.assertIn("(1 bag slot + 3 reagent bag slots;", bring_text(plan, gd, trip, None, reagent_slots=3))

    def test_batch_size_counts_the_reagent_bag(self):
        from yap_forever.shopping import batch_size
        stack = {818: 20, 2318: 20, 4368: 1}
        args = ({818: 2, 2318: 6}, (4368, 1), stack, 16)
        self.assertEqual(batch_size(*args), 15)
        self.assertEqual(batch_size(*args, reagents={818, 2318}, reagent_slots=0), 15)
        self.assertGreater(batch_size(*args, reagents={818, 2318}, reagent_slots=6), 15)

    def test_guide_passes_the_reagent_slots(self):
        import dataclasses
        from yap_forever.guide import render_guide
        p, gd = rank_trip_plan()
        stock = dataclasses.replace(toy.stock(skills={BS: 225}), bag_slots=16)
        market = toy.market({S: [(10, 1000)]})
        plain = render_guide(p, gd, market, stock, caps={BS: 300})
        bagged = render_guide(p, gd, market, dataclasses.replace(stock, reagent_slots=6), caps={BS: 300})
        self.assertNotEqual(plain, bagged)
        self.assertIn("reagent bag", bagged)
        self.assertNotIn("reagent bag", plain)


class HandInsAndToolMaterialsTests(unittest.TestCase):
    """Quest hand-ins and a crafted tool's materials are bought, so the rows and the list show them."""

    def test_quest_hand_in_on_rows_and_shopping_list(self):
        rs = base_recipes() + [toy.recipe(3, "Quest Belt", BS, {}, (toy.STONE, 1),
                                          source="scroll", scroll=toy.SCROLL)]
        quests = {3: QuestPlan("Quest Belt", {toy.IRON_BAR: 20}, 50, "Someone, Tanaris")}
        listings = {**BARS, toy.IRON_BAR: [(10, 1000)]}
        p = run(rs, listings, quests=quests)
        gd = toy.gamedata(rs)
        self.assertEqual(all_need(p, gd).get(toy.IRON_BAR), 20)  # handed in once, no buffer
        self.assertIn("| Iron Bar | 20 | AH |", shopping_text(p, gd, listings))

    def test_crafted_tool_materials_on_rows(self):
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(2, "Ench rod-needing", ENCH, {toy.COPPER_BAR: 1}, tools=[373]),
              toy.recipe(5, "Runed Copper Rod", ENCH, {toy.IRON_BAR: 3}, (toy.ROD_TOOL, 1), t=(1, 1, 1, 1),
                         source="starter")]
        listings = {**BARS, toy.IRON_BAR: [(10, 1000)]}
        p = run(rs, listings)
        self.assertTrue(any("Craft tool Runed Copper Rod" in e for e in p.events))
        gd = toy.gamedata(rs)
        self.assertEqual(all_need(p, gd).get(toy.IRON_BAR), 3)
        self.assertIn("| Iron Bar | 3 | AH |", shopping_text(p, gd, listings))


class BoughtToolTests(unittest.TestCase):
    def test_vendor_tool_in_guide_and_shopping_list(self):
        from yap_forever.guide import gold, render_guide
        rs = [toy.recipe(1, "BS hammer", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1), tools=[162]),
              toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})]
        p = run(rs, BARS)
        gd = toy.gamedata(rs)
        text = shopping_text(p, gd, BARS)
        self.assertIn(f"| Blacksmith Hammer | 1 | vendor | {gold(18)} |", text)
        guide = render_guide(p, gd, toy.market(BARS), toy.stock(), caps={BS: 225, ENCH: 225})
        route = guide.split("## Route", 1)[1]
        self.assertIn("Buy tool Blacksmith Hammer", route)

    def test_bought_tool_the_route_also_crafts_is_bought(self):
        from yap_forever.planner import Plan, Step
        from yap_forever.shopping import route_rows
        H = toy.HAMMER
        gd = toy.gamedata([toy.recipe(1, "Make hammer", BS, {toy.IRON_BAR: 2}, (H, 1)),
                           toy.recipe(2, "BS hammer", BS, {toy.COPPER_BAR: 1}, tools=[162])])
        p = Plan(steps=[Step(BS, 1, 2, 2, "BS hammer", 1, 0, 0, {toy.COPPER_BAR: 1}, buffered=1, tools_bought={H: 1}),
                        Step(BS, 2, 3, 1, "Make hammer", 1, 0, 0, {toy.IRON_BAR: 2}, buffered=1)],
                 crafted={H: 1}, vendor_bought={H: 1}, final_skill={BS: 3})
        rows = route_rows(p, gd)
        self.assertEqual(rows[0]["need"], {toy.COPPER_BAR: 1, H: 1})
        self.assertEqual(rows[0]["earlier"], {})

    def test_craft_once_tool_on_shopping_list(self):
        rs = base_recipes() + [toy.recipe(5, "BS final", BS, {toy.IRON_BAR: 1}, req=20, tools=[162])]
        listings = {**BARS, toy.IRON_BAR: [(700, 100)]}
        p = run_caps(rs, {BS: 20}, listings, craft_once={BS: 5})
        self.assertIn("| Blacksmith Hammer | 1 | vendor |", shopping_text(p, toy.gamedata(rs), listings))
