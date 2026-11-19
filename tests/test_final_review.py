"""Fixes from the phase 2 final review (2026-11-19)."""
import unittest

from tests import toy
from tests.test_planner import BARS, ENCH, base_recipes, run, run_caps
from yap_forever.quests import QuestPlan

BS = 164


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

    def test_bought_tool_not_a_material_on_rows_or_keep_table(self):
        from yap_forever.guide import render_guide
        rs = [toy.recipe(1, "BS hammer", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1), tools=[162]),
              toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})]
        p = run(rs, BARS)
        gd = toy.gamedata(rs)
        guide = render_guide(p, gd, toy.market(BARS), toy.stock(), caps={BS: 225, ENCH: 225})
        keep = guide[guide.index("## Keep while levelling"):guide.index("## Route")]
        self.assertNotIn("Blacksmith Hammer", keep)
        rows = [l for l in guide.splitlines() if l.startswith("- **") and "× BS hammer" in l]
        self.assertTrue(rows)
        self.assertFalse(any("Blacksmith Hammer" in l for l in rows))

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


class BringListBankTests(unittest.TestCase):
    def plan(self):
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
        p, gd = self.plan()
        trip = Trip(225, BS, "rank", "Blacksmithing rank to 300")
        for owned in (None, {toy.COPPER_BAR: 20}):
            _reach, items = bring_list(p, gd, trip, None, owned)
            self.assertEqual(items, [(toy.COPPER_BAR, 60, "mail")])
        _reach, items = bring_list(p, gd, trip, None, {toy.COPPER_BAR: 50})  # 30 spare in the bank
        self.assertEqual(sorted(items), [(toy.COPPER_BAR, 30, "bank"), (toy.COPPER_BAR, 30, "mail")])


class FirstCraftTests(unittest.TestCase):
    def test_row_names_the_intermediate_to_craft_first(self):
        from yap_forever.guide import render_guide
        from yap_forever.planner import Plan, Step
        S, T, L = toy.COPPER_BAR, toy.IRON_BAR, toy.ROD
        gd = toy.gamedata([toy.recipe(40, "Make L", BS, {S: 3}, (L, 2)), toy.recipe(42, "Make G", BS, {L: 1, T: 1})])
        st = Step(BS, 1, 4, 42, "Make G", 3, 0, 0, {T: 3}, buffered=3)
        p = Plan(steps=[st], crafted={L: 3}, final_skill={BS: 4})
        text = render_guide(p, gd, toy.market(), toy.stock(), caps={BS: 4})
        line = next(l for l in text.splitlines() if "× Make G" in l)
        self.assertIn("first craft 3 Copper Rod", line)
        self.assertIn("6 Copper Bar", line)


class GreensPastEnchantingTargetTests(unittest.TestCase):
    def test_green_not_held_when_enchanting_stops_below_its_gate(self):
        from yap_forever.costmodel import Valuer
        from yap_forever.planner import plan
        rs = [toy.recipe(1, "BS green", BS, {toy.COPPER_BAR: 1}, (toy.BELT, 1)),
              toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})]
        gd = toy.gamedata(rs)
        gd.items[toy.BELT].item_level = 48  # disenchanting needs Enchanting 150
        listings = {**BARS, 11176: [(5000, 1000)]}  # Dream Dust worth far more than the belt
        st = toy.stock()
        p = plan(gd, Valuer(toy.market(listings), gd, st), st, toy.NO_FAVOR, caps={BS: 20, ENCH: 20})
        self.assertEqual(p.final_skill[ENCH], 20)
        self.assertNotIn(toy.BELT, p.held_for_de)


class FavorGoalTests(unittest.TestCase):
    def test_favor_recipe_target_uses_the_favor_skill(self):
        from yap_forever.config import Goal
        from yap_forever.favor import FavorData
        from yap_forever.planner import resolve_goals
        gd = toy.gamedata([toy.recipe(5, "Veteran Belt", BS, {toy.IRON_BAR: 2}, (toy.BELT, 1), t=(1, 50, 60, 70),
                                      source="unknown")])
        favor = FavorData({5: 30}, {5: 45}, [])
        caps, once = resolve_goals({BS: Goal(recipe="Veteran Belt")}, gd, favor)
        self.assertEqual((caps, once), ({BS: 45}, {BS: 5}))


class BringListNextRankTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
