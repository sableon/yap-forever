"""Shopping list, mailbox trips and what to bring to a remote trainer (ported from scripts/shopping.py)."""
import unittest

from tests import toy
from yap_forever.planner import Plan, Step
from yap_forever.shopping import CRAFT_ROOM

BS = 164
S, T, L, K, G = toy.COPPER_BAR, toy.IRON_BAR, toy.ROD, toy.STONE, toy.VEST


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

