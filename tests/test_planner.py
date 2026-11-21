import unittest

from tests import toy
from yap_forever.costmodel import Valuer
from yap_forever.favor import FavorData
from yap_forever.planner import plan

BS, ENCH = 164, 333


def base_recipes():
    """One cheap always-orange recipe per profession."""
    return [
        toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
        toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1}),
    ]


def run(recipes, listings=None, stock=None, favor=toy.NO_FAVOR, quest=(), cap=225, quests=None, reuse=None,
        **talents):
    gd = toy.gamedata(recipes, quest_items=quest)
    st = stock or toy.stock()
    return plan(gd, Valuer(toy.market(listings), gd, st), st, favor, caps={BS: cap, ENCH: cap}, quests=quests,
                reuse=reuse,
                **talents)


BARS = {toy.COPPER_BAR: [(100, 100000)]}


def run_with_data(recipes, listings, stock=None):
    """Plan both professions to 225; return the plan with its game data, market and stock."""
    gd = toy.gamedata(recipes)
    st = stock or toy.stock()
    m = toy.market(listings)
    return plan(gd, Valuer(m, gd, st), st, toy.NO_FAVOR, caps={BS: 225, ENCH: 225}), gd, m, st


class PlannerTests(unittest.TestCase):
    def test_reaches_cap_both(self):
        p = run(base_recipes(), BARS)
        self.assertEqual(p.final_skill, {BS: 225, ENCH: 225})
        self.assertEqual(p.stalled, {})

    def test_picks_cheapest_per_point(self):
        rs = base_recipes() + [toy.recipe(3, "BS iron", BS, {toy.IRON_BAR: 1}, (toy.STONE, 1))]
        p = run(rs, {**BARS, toy.IRON_BAR: [(10, 100000)]})
        self.assertEqual({s.spell_id for s in p.steps if s.profession == BS}, {3})

    def test_reuse_credit_picks_needed_reagent_up_to_count(self):
        rs = base_recipes() + [toy.recipe(3, "BS iron", BS, {toy.IRON_BAR: 1}, (toy.VEST, 1))]
        p = run(rs, {**BARS, toy.IRON_BAR: [(90, 100000)]}, reuse={toy.STONE: (10, 50)})
        basic = [s for s in p.steps if s.profession == BS and s.spell_id == 1]
        self.assertEqual(sum(s.crafts for s in basic), 10)  # 100 - 50 beats 90, but only for 10 stones
        self.assertEqual(basic[0].skill_from, 1)

    def test_skips_unpriceable_with_reason(self):
        rs = base_recipes() + [toy.recipe(3, "BS odd", BS, {toy.ODD: 1}, (toy.STONE, 1))]
        p = run(rs, BARS)
        self.assertIn((3, "unpriceable: Odd Thing"), p.skipped)

    def test_not_planned_below_required_skill(self):
        rs = base_recipes() + [toy.recipe(3, "BS iron", BS, {toy.IRON_BAR: 1}, (toy.STONE, 1), req=30)]
        p = run(rs, {**BARS, toy.IRON_BAR: [(10, 100000)]})
        first_iron = min(s.skill_from for s in p.steps if s.spell_id == 3)
        self.assertEqual(first_iron, 30)

    def test_plan_starts_from_stock_skills(self):
        p = run(base_recipes(), BARS, stock=toy.stock(skills={BS: 100, ENCH: 120}))
        self.assertEqual(min(s.skill_from for s in p.steps if s.profession == BS), 100)
        self.assertEqual(min(s.skill_from for s in p.steps if s.profession == ENCH), 120)
        self.assertEqual(p.fees, 4500 + 5000)  # the 150 ranks are already trained

    def test_skill_at_rank_cap_trains_next_rank(self):
        p = run(base_recipes(), BARS, stock=toy.stock(skills={BS: 150, ENCH: 150}))
        self.assertEqual(p.fees, 4500 + 5000)
        self.assertEqual(p.final_skill, {BS: 225, ENCH: 225})

    def test_rank_fee_added_at_cap(self):
        p = run(base_recipes(), BARS)
        self.assertEqual(p.fees, 450 + 4500 + 500 + 5000)

    def test_level_too_low_stalls(self):
        p = run(base_recipes(), BARS, stock=toy.stock(level=15))
        self.assertEqual(p.stalled, {BS: 150, ENCH: 150})
        self.assertTrue(any("level 20" in r for _, r in p.stall_reasons.items()))

    def test_stalls_without_candidates(self):
        rs = [toy.recipe(1, "BS short", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1), t=(1, 40, 50, 60)),
              toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})]
        p = run(rs, BARS)
        self.assertEqual(p.stalled, {BS: 60})
        self.assertEqual(p.final_skill[ENCH], 225)

    def test_greens_disenchanted_as_made(self):
        rs = [toy.recipe(1, "Belt", BS, {toy.COPPER_BAR: 1}, (toy.BELT, 1)),
              toy.recipe(2, "Ench dust", ENCH, {toy.DUST: 1})]
        p = run(rs, {**BARS, toy.DUST: [(300, 100000)]}, cap=40)
        # Forever has no item-level gate: belts (ilvl 22) are disenchanted from Enchanting 1
        self.assertEqual(p.held_for_de, {})
        self.assertTrue(any(e.startswith("Enchanting 1: disenchant") for e in p.events))
        self.assertGreater(p.de_materials.get(toy.DUST, 0), 0)

    def test_disenchants_raise_enchanting(self):
        rs = [toy.recipe(1, "Belt", BS, {toy.COPPER_BAR: 1}, (toy.BELT, 1)),
              toy.recipe(2, "Ench dust", ENCH, {toy.DUST: 1})]
        p = run(rs, {**BARS, toy.DUST: [(300, 100000)]}, cap=40)
        de_steps = [s for s in p.steps if s.profession == ENCH and s.spell_id == 0]
        self.assertTrue(de_steps)
        self.assertEqual(de_steps[0].skill_from, 1)
        self.assertEqual(sum(s.cash + s.economic for s in de_steps), 0)
        # Enchanting steps, recipes and disenchants together, cover every point without gaps.
        ench = sorted((s.skill_from, s.skill_to) for s in p.steps if s.profession == ENCH)
        self.assertEqual(ench[0][0], 1)
        for (_, a), (b, _) in zip(ench, ench[1:]):
            self.assertEqual(a, b)
        self.assertEqual(ench[-1][1], p.final_skill[ENCH])

    def test_disenchant_skillups_stop_at_60(self):
        rs = [toy.recipe(1, "Belts", BS, {toy.COPPER_BAR: 1}, (toy.BELT, 5))]
        p = run(rs, BARS, cap=75)
        self.assertEqual(p.final_skill[ENCH], 60)
        crafts = sum(s.crafts for s in p.steps if s.profession == ENCH and s.spell_id == 0)
        self.assertAlmostEqual(crafts, 190.1, delta=0.5)

    def test_greens_above_enchanting_gate_sold(self):
        import dataclasses
        rs = [toy.recipe(1, "Belt", BS, {toy.COPPER_BAR: 1}, (toy.BELT, 1))]
        gd = toy.gamedata(rs)
        # item level 50 keeps the Classic gate (150): disenchanting gives no skill before then
        gd.items[toy.BELT] = dataclasses.replace(gd.items[toy.BELT], item_level=50)
        st = toy.stock()
        market = toy.market({**BARS, toy.BELT: [(5000, 10)]})
        p = plan(gd, Valuer(market, gd, st), st, toy.NO_FAVOR, caps={BS: 225, ENCH: 225})
        self.assertEqual(p.held_for_de, {})
        self.assertGreater(p.sale_proceeds, 0)

    def test_greens_held_for_disenchanting_not_sold(self):
        import dataclasses
        # Dream Dust (11176) only comes from disenchanting ilvl 46-50 greens, and an Enchanting
        # recipe needs it, so the belts are kept even though Enchanting never reaches their gate.
        rs = [toy.recipe(1, "Belt", BS, {toy.COPPER_BAR: 1}, (toy.BELT, 1)),
              toy.recipe(2, "Ench dream", ENCH, {11176: 1}, req=200)]
        gd = toy.gamedata(rs)
        # item level 50 keeps the Classic gate (150), out of reach for this Enchanting
        gd.items[toy.BELT] = dataclasses.replace(gd.items[toy.BELT], item_level=50)
        st = toy.stock()
        market = toy.market({**BARS, toy.BELT: [(5000, 10)]})
        p = plan(gd, Valuer(market, gd, st), st, toy.NO_FAVOR, caps={BS: 225, ENCH: 225})
        self.assertIn(toy.BELT, p.held_for_de)
        self.assertEqual(p.sale_proceeds, 0)

    def test_favor_limit_respected(self):
        # two Favor goals (Favor recipes are only planned as goals, #95) and Favor for one of them
        rs = base_recipes() + [
            toy.recipe(3, "Fav A", BS, {}, (toy.STONE, 1), source="unknown"),
            toy.recipe(4, "Fav B", ENCH, {}, None, source="unknown")]
        fav = FavorData({3: 30, 4: 30}, {3: 20, 4: 20}, [])
        gd, st = toy.gamedata(rs), toy.stock(favor=30)
        p = plan(gd, Valuer(toy.market(BARS), gd, st), st, fav, caps={BS: 20, ENCH: 20}, craft_once={BS: 3, ENCH: 4})
        self.assertEqual(p.favor_spent, 30)
        learned = {s.spell_id for s in p.steps} & {3, 4}
        self.assertEqual(len(learned), 1)
        self.assertIn("not enough Favor (30)", " ".join(p.stall_reasons.values()))

    def test_scroll_recipe_priced_or_skipped(self):
        rs = base_recipes() + [toy.recipe(3, "Scroll free", BS, {}, (toy.STONE, 1),
                                          source="scroll", scroll=toy.SCROLL)]
        p = run(rs, BARS)  # scroll not on AH, not vendor-sold
        self.assertIn((3, "scroll not available: Plans: Something"), p.skipped)
        p2 = run(rs, {**BARS, toy.SCROLL: [(500, 1)]})
        self.assertIn(3, {s.spell_id for s in p2.steps})
        self.assertIn("Learn Scroll free (scroll 5s 0c)", " ".join(p2.events))

    def scroll_recipes(self, req=1):
        return base_recipes() + [toy.recipe(3, "Scroll free", BS, {}, (toy.STONE, 1), req=req,
                                            source="scroll", scroll=toy.SCROLL)]

    def test_owned_pattern_is_learned_at_no_cost_and_consumed(self):
        from yap_forever.shopping import render_shopping
        rs = self.scroll_recipes()
        st = toy.stock({toy.SCROLL: 1})
        p = run(rs, BARS, stock=st)  # the pattern is not on the AH: owning it is the only way
        self.assertNotIn(3, dict(p.skipped))
        self.assertIn(3, {s.spell_id for s in p.steps})
        self.assertEqual([how for _p, _s, spell, how in p.learn_log if spell == 3], ["owned"])
        self.assertIn("Learn Scroll free (your own pattern)", " ".join(p.events))
        self.assertEqual(p.used_stock.get(toy.SCROLL), 1)  # consumed: not left to sell
        self.assertNotIn(toy.SCROLL, p.leftovers)
        self.assertEqual(p.bought.get(toy.SCROLL, 0), 0)
        gd = toy.gamedata(rs)
        text = "\n".join(render_shopping(p, gd, toy.market(BARS), st)[0])
        self.assertNotIn("Plans: Something", text)
        from yap_forever.trips import trips
        self.assertEqual([t for t in trips(p, gd, st.skills) if t.spell == 3], [])  # no vendor or AH pattern trip

    def test_owned_pattern_beats_a_listed_one(self):
        rs = self.scroll_recipes()
        market = {**BARS, toy.SCROLL: [(500, 1)]}
        bought = run(rs, market)
        owned = run(rs, market, stock=toy.stock({toy.SCROLL: 1}))
        self.assertEqual([how for *_x, spell, how in bought.learn_log if spell == 3], ["ah"])
        self.assertEqual([how for *_x, spell, how in owned.learn_log if spell == 3], ["owned"])
        self.assertLess(owned.cash_total, bought.cash_total)

    def test_owned_pattern_costs_its_sale_value_in_value_mode_but_no_cash(self):
        rs = self.scroll_recipes()
        gd = toy.gamedata(rs)
        totals = []
        for price in (500, 3000):  # the same pattern, worth more on the second AH
            market = {**BARS, toy.SCROLL: [(price, 1)]}
            st = toy.stock({toy.SCROLL: 1})
            p = run(rs, market, stock=st)
            self.assertEqual([how for *_x, spell, how in p.learn_log if spell == 3], ["owned"])
            worth = Valuer(toy.market(market), gd, st).owned_value(toy.SCROLL)
            totals.append((p.cash_total, p.economic_total, worth))
        (cash_a, econ_a, worth_a), (cash_b, econ_b, worth_b) = totals
        self.assertGreater(worth_b, worth_a)
        self.assertEqual(cash_a, cash_b)  # an owned pattern costs no cash
        self.assertAlmostEqual(econ_b - econ_a, worth_b - worth_a, places=6)  # but its sale value is given up

    def test_without_the_pattern_nothing_changes(self):
        rs = self.scroll_recipes()
        self.assertEqual(run(rs, BARS).skipped, run(rs, BARS, stock=toy.stock({toy.COPPER_BAR: 3})).skipped)
        self.assertIn((3, "scroll not available: Plans: Something"), run(rs, BARS).skipped)

    def test_owned_pattern_still_needs_the_skill(self):
        p = run(self.scroll_recipes(req=50), BARS, stock=toy.stock({toy.SCROLL: 1}))
        steps = [s for s in p.steps if s.spell_id == 3]
        self.assertTrue(steps)
        self.assertTrue(all(s.skill_from >= 50 for s in steps))

    def test_missing_rod_adds_tool_cost_once(self):
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(2, "Ench rod-needing", ENCH, {toy.ROD: 1}, tools=[373]),
              toy.recipe(5, "Runed Copper Rod", ENCH, {toy.ROD: 1}, (toy.ROD_TOOL, 1), source="starter")]
        p = run(rs, BARS)
        tool_events = [e for e in p.events if "tool" in e.lower()]
        self.assertLessEqual(len(tool_events), 1)
        self.assertEqual(p.final_skill[ENCH], 225)

    def test_hammer_bought_from_vendor(self):
        rs = [toy.recipe(1, "BS hammer", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1), tools=[162]),
              toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})]
        p = run(rs, BARS)
        self.assertEqual(p.final_skill[BS], 225)
        self.assertTrue(any(e.endswith(": Buy tool Blacksmith Hammer (vendor 0s 18c)") for e in p.events))

    def test_stock_used_and_totals(self):
        p = run(base_recipes(), BARS, stock=toy.stock({toy.COPPER_BAR: 10}))
        self.assertEqual(p.used_stock.get(toy.COPPER_BAR), 10)
        self.assertGreater(p.cash_total, 0)
        self.assertGreaterEqual(p.economic_total, p.cash_total - p.sale_proceeds - p.leftover_value)

    def test_tool_and_reagent_share_thin_supply_no_crash(self):
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(2, "Ench dust", ENCH, {toy.DUST: 1}, tools=[373]),
              toy.recipe(5, "Runed Copper Rod", ENCH, {toy.ROD: 1, toy.DUST: 1}, (toy.ROD_TOOL, 1),
                         t=(1, 2, 2, 2), source="trainer")]
        p, *_ = run_with_data(rs, {**BARS, toy.DUST: [(300, 1)]})  # only one dust listed
        self.assertEqual(p.final_skill[BS], 225)

    def test_stall_lifted_when_other_profession_makes_materials(self):
        # Strange Dust only comes from disenchanting a BS green that needs BS 30.
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(3, "Belt", BS, {toy.COPPER_BAR: 1}, (toy.BELT, 1), req=30),
              toy.recipe(2, "Ench start", ENCH, {toy.ROD: 1}, t=(1, 10, 10, 10)),
              toy.recipe(4, "Ench dust", ENCH, {toy.DUST: 1}, req=10)]
        gd = toy.gamedata(rs)
        gd.items[toy.BELT].item_level = 18  # disenchantable from Enchanting 1
        st = toy.stock()
        p = plan(gd, Valuer(toy.market(BARS), gd, st), st, toy.NO_FAVOR, caps={BS: 225, ENCH: 225})
        self.assertGreater(p.final_skill[ENCH], 10)

    def test_intermediate_craft_charges_learning(self):
        # Ench recipe needs the rod tool; the rod recipe costs 5g to learn.
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(2, "Ench rod-needing", ENCH, {toy.COPPER_BAR: 1}, tools=[373]),
              toy.recipe(5, "Runed Copper Rod", ENCH, {toy.ROD: 1}, (toy.ROD_TOOL, 1),
                         t=(1, 1, 1, 1), fee=50000)]
        p, *_ = run_with_data(rs, BARS)
        self.assertIn(5, p.learned)
        self.assertTrue(any("Runed Copper Rod" in e and "5g" in e for e in p.events))

    def test_planned_recipe_not_listed_as_excluded(self):
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(3, "BS iron", BS, {toy.IRON_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})]
        # only a few iron bars: planned early, unpriceable later
        p, *_ = run_with_data(rs, {**BARS, toy.IRON_BAR: [(1, 5)]})
        self.assertIn(3, {s.spell_id for s in p.steps})
        self.assertNotIn(3, dict(p.skipped))

    def test_shopping_list_includes_scroll_tool_and_coal(self):
        rs = [toy.recipe(1, "BS hammer", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1), tools=[162]),
              toy.recipe(3, "Scrolled", BS, {}, (toy.STONE, 1), source="scroll", scroll=toy.SCROLL),
              toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})]
        p, *_ = run_with_data(rs, {**BARS, toy.SCROLL: [(500, 1)]})
        self.assertIn(toy.SCROLL, p.bought)
        p2, *_ = run_with_data([rs[0], rs[2]], BARS)  # only the hammer recipe for Blacksmithing
        self.assertIn(toy.HAMMER, p2.vendor_bought)

    def test_order_levels_first_profession_first(self):
        rs = [toy.recipe(1, "BS belt", BS, {toy.COPPER_BAR: 1}, (toy.BELT, 1)),  # a green: disenchanted
              toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})]
        for order in ((BS, ENCH), (ENCH, BS)):
            p = run(rs, BARS, order=order)
            self.assertEqual(p.final_skill, {BS: 225, ENCH: 225})
            crafts = [s.profession for s in p.steps if s.spell_id != 0]  # disenchant steps excepted
            first, second = order
            self.assertLess(max(i for i, x in enumerate(crafts) if x == first),
                            min(i for i, x in enumerate(crafts) if x == second), order)

    def test_no_order_is_unchanged(self):
        def rows(p):
            return [(s.profession, s.skill_from, s.skill_to, s.spell_id) for s in p.steps]
        p = run(base_recipes(), BARS)
        self.assertEqual(rows(p), rows(run(base_recipes(), BARS, order=None)))
        # side by side: the lower profession first, Blacksmithing on a tie
        self.assertEqual(rows(p)[:4], [(BS, 1, 2, 1), (ENCH, 1, 2, 2), (BS, 2, 3, 1), (ENCH, 2, 3, 2)])


def crafts_of(p, prof, spell=None):
    return sum(s.crafts for s in p.steps if s.profession == prof and (spell is None or s.spell_id == spell))


class WorkingOvertimeTests(unittest.TestCase):
    def yellow_route(self):
        # always yellow or green: 1 -> 100 skill at chance (100 - s) / 99 or less
        return [toy.recipe(1, "BS slow", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1), t=(1, 1, 50, 100)),
                toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})]

    def test_rank_five_needs_fewer_crafts(self):
        base = run(self.yellow_route(), BARS, cap=60)
        for reading in ("relative", "points"):
            fast = run(self.yellow_route(), BARS, cap=60, overtime=5, reading=reading)
            self.assertEqual(fast.final_skill[BS], base.final_skill[BS])
            self.assertLess(crafts_of(fast, BS, 1), crafts_of(base, BS, 1), reading)
        rel = run(self.yellow_route(), BARS, cap=60, overtime=5, reading="relative")
        pts = run(self.yellow_route(), BARS, cap=60, overtime=5, reading="points")
        self.assertLess(crafts_of(pts, BS, 1), crafts_of(rel, BS, 1))

    def test_rank_zero_changes_nothing(self):
        a = run(self.yellow_route(), BARS, cap=60)
        for reading in ("relative", "points"):
            b = run(self.yellow_route(), BARS, cap=60, overtime=0, reading=reading)
            self.assertEqual(a.steps, b.steps)
            self.assertEqual((a.cash_total, a.economic_total), (b.cash_total, b.economic_total))

    def test_disenchant_skillups_use_the_talent_too(self):
        rs = [toy.recipe(1, "Belt", BS, {toy.COPPER_BAR: 1}, (toy.BELT, 1)),
              toy.recipe(2, "Ench dust", ENCH, {toy.DUST: 1})]
        listings = {**BARS, toy.DUST: [(300, 100000)]}
        base = run(rs, listings, cap=60)
        fast = run(rs, listings, cap=60, overtime=5, reading="points")
        self.assertEqual(fast.final_skill[ENCH], base.final_skill[ENCH])

        def disenchants_per_point(p):
            de = [s for s in p.steps if s.profession == ENCH and s.spell_id == 0]
            self.assertTrue(de)
            return sum(s.crafts for s in de) / sum(s.skill_to - s.skill_from for s in de)
        self.assertLess(disenchants_per_point(fast), disenchants_per_point(base))


class BankGreensTests(unittest.TestCase):
    """Greens in the bank are disenchanted first: free Enchanting skill-ups and materials."""

    def recipes(self):
        return [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
                toy.recipe(2, "Ench dust", ENCH, {toy.DUST: 1})]

    def run_bank(self, belts=30, skills=None, cap=40):
        st = toy.stock({toy.BELT: belts}, skills=skills)
        return run(self.recipes(), {**BARS, toy.DUST: [(300, 100000)], toy.BELT: [(5000, 10)]},
                   stock=st, cap=cap), st

    def test_bank_greens_level_enchanting_first(self):
        p, _ = self.run_bank()
        first = next(s for s in p.steps if s.profession == ENCH)
        self.assertEqual((first.spell_id, first.skill_from), (0, 1))
        self.assertGreater(first.skill_to, 20)
        self.assertEqual(first.materials, {toy.BELT: 30})
        self.assertEqual(first.from_stock, {toy.BELT: 30})
        self.assertEqual(p.used_stock.get(toy.BELT), 30)
        self.assertIn("Enchanting 1: disenchant 30 Runed Copper Belt from your bank", p.events)

    def test_bank_greens_are_free_and_feed_enchanting(self):
        p, _ = self.run_bank()
        de = [s for s in p.steps if s.spell_id == 0]
        self.assertEqual(sum(s.cash + s.economic for s in de), 0)
        self.assertGreater(p.de_materials.get(toy.DUST, 0), 0)
        self.assertTrue(any(toy.DUST in s.used_made for s in p.steps if s.spell_id == 2))
        self.assertNotIn(toy.BELT, p.leftovers)

    def test_bank_greens_untouched_when_enchanting_not_planned(self):
        p, _ = self.run_bank(skills={ENCH: 40})
        self.assertNotIn(toy.BELT, p.used_stock)
        self.assertFalse(any(s.spell_id == 0 for s in p.steps))

if __name__ == "__main__":
    unittest.main()


class FavorScrollTests(unittest.TestCase):
    def test_favor_listing_overrides_scroll_source(self):
        # Forever Favor recipes are taught by a scroll item sold for Favor, so game data says "scroll".
        # A Favor recipe is planned as a goal only (#95).
        rs = base_recipes() + [toy.recipe(3, "Fav scroll", BS, {}, (toy.STONE, 1),
                                          source="scroll", scroll=toy.SCROLL)]
        fav = FavorData({3: 30}, {3: 20}, [])
        gd, st = toy.gamedata(rs), toy.stock(favor=30)
        p = plan(gd, Valuer(toy.market(BARS), gd, st), st, fav, caps={BS: 20}, craft_once={BS: 3})
        self.assertEqual(p.favor_spent, 30)
        self.assertIn((BS, 20, 3, "favor"), p.learn_log)
        self.assertIn(3, {s.spell_id for s in p.steps})
        self.assertNotIn(3, {sid for sid, _ in p.skipped})

    def favor_route(self, recipes, favor, mode="gold", cap=240, craft_once=None, listings=None):
        """Blacksmithing to cap with a Master rank from 225 (a remote trip at 225), Favor 100."""
        from yap_forever.gamedata import Rank
        gd = toy.gamedata(base_recipes() + recipes)
        gd.trainer_ranks[BS] = gd.trainer_ranks[BS] + [Rank(300, 9000, 225, 20)]
        st = toy.stock(favor=100)
        p = plan(gd, Valuer(toy.market(listings or BARS), gd, st, mode=mode), st, favor, caps={BS: cap},
                 craft_once=craft_once)
        return p, gd, st

    def test_favor_recipe_not_used_to_level(self):
        # #95: a Favor recipe with no reagents is the cheapest in gold at every skill, yet never levels the route
        from yap_forever.shopping import bring_list
        from yap_forever.trips import trips, visit_count, visits
        fav = FavorData({3: 30}, {3: 1}, [])
        rs = [toy.recipe(3, "Fav free", BS, {}, (toy.STONE, 1), source="scroll", scroll=toy.SCROLL)]
        for mode in ("gold", "value"):
            p, gd, st = self.favor_route(rs, fav, mode)
            self.assertEqual(p.final_skill, {BS: 240}, mode)
            self.assertNotIn(3, [spell for _p, _s, spell, _how in p.learn_log], mode)
            self.assertNotIn(3, {s.spell_id for s in p.steps}, mode)
            self.assertEqual(p.favor_spent, 0, mode)
            self.assertNotIn(3, {sid for sid, _ in p.skipped}, mode)  # not an "Excluded recipe" either
            for how in ("as_needed", "one_go"):
                found = trips(p, gd, {BS: 1}, how)
                self.assertNotIn("favor", [t.kind for t in found], (mode, how))
                self.assertEqual(visit_count(p, gd, {BS: 1}, how), len(visits(p, gd, {BS: 1}, how)), (mode, how))
                master = next(t for t in found if t.kind == "rank" and t.cap == 300)
                items = bring_list(p, gd, master, None, trainer_trips=how)[1]
                self.assertNotIn(toy.SCROLL, [i for i, _n, _src in items], (mode, how))

    def test_favor_goal_still_planned(self):
        # a Favor recipe as the craft-once goal: learned with Favor, crafted once, its Favor trip (as needed) or its
        # pattern on the Master trip's bring list (one go)
        from yap_forever.shopping import bring_list, bring_text
        from yap_forever.trips import trips
        fav = FavorData({4: 30}, {4: 240}, [])
        rs = [toy.recipe(4, "Fav goal", BS, {toy.IRON_BAR: 1}, (toy.VEST, 1), source="scroll", scroll=toy.SCROLL)]
        for mode in ("gold", "value"):
            p, gd, st = self.favor_route(rs, fav, mode, craft_once={BS: 4},
                                         listings={**BARS, toy.IRON_BAR: [(700, 100)]})
            self.assertIn((BS, 240, 4, "favor"), p.learn_log, mode)
            self.assertEqual(p.favor_spent, 30, mode)
            last = p.steps[-1]
            self.assertEqual((last.spell_id, last.crafts, last.skill_from, last.skill_to), (4, 1, 240, 240), mode)
            self.assertIn(("favor", 240), [(t.kind, t.skill) for t in trips(p, gd, {BS: 1})], mode)
            one_go = trips(p, gd, {BS: 1}, "one_go")
            self.assertNotIn("favor", [t.kind for t in one_go], mode)
            master = next(t for t in one_go if t.kind == "rank" and t.cap == 300)
            self.assertIn((toy.SCROLL, 1, "pattern:favor"),
                          bring_list(p, gd, master, None, trainer_trips="one_go")[1], mode)
            self.assertIn("1 Plans: Something (from the Merchant's Favor vendor)",
                          bring_text(p, gd, master, None, trainer_trips="one_go"), mode)

    def test_favor_recipe_not_used_to_make_a_tool(self):
        # the only way to the Runed Copper Rod is a Favor recipe: the recipe that needs the rod is not used
        fav = FavorData({5: 30}, {5: 1}, [])
        rs = [toy.recipe(1, "BS basic", BS, {toy.COPPER_BAR: 1}, (toy.STONE, 1)),
              toy.recipe(2, "Ench copper", ENCH, {toy.COPPER_BAR: 1}),
              toy.recipe(6, "Ench rod-needing", ENCH, {}, tools=[373]),
            toy.recipe(5, "Fav rod", ENCH, {toy.ROD: 1}, (toy.ROD_TOOL, 1), source="scroll", scroll=toy.SCROLL)]
        p = run(rs, {**BARS, toy.ROD: [(10, 100000)]}, stock=toy.stock(favor=100), favor=fav, cap=40)
        self.assertNotIn(6, {s.spell_id for s in p.steps})
        self.assertEqual(p.favor_spent, 0)
        self.assertNotIn(5, [spell for _p, _s, spell, _how in p.learn_log])


class NoOvercraftTests(unittest.TestCase):
    def test_resale_does_not_pick_lower_chance_recipe(self):
        # orange: 1 Copper Bar per point. "Vest" goes yellow at once, so it needs more crafts per
        # point, but each Vest resells on the AH for far more than its 2 bars. Levelling should not chase
        # resale (its vendor price, 20c, counts and still leaves it dearer: 180c a craft against 98c).
        rs = base_recipes() + [toy.recipe(3, "Vest", BS, {toy.COPPER_BAR: 2}, (toy.VEST, 1), t=(1, 1, 50, 99))]
        p = run(rs, {**BARS, toy.VEST: [(1000, 50)]}, cap=40)
        self.assertNotIn(3, {s.spell_id for s in p.steps})


LW = 165


def run_caps(recipes, caps, listings=None, stock=None, craft_once=None, exclude=frozenset()):
    gd = toy.gamedata(recipes)
    st = stock or toy.stock()
    return plan(gd, Valuer(toy.market(listings), gd, st), st, toy.NO_FAVOR, caps=caps,
                craft_once=craft_once, exclude=exclude)


class AnyProfessionTests(unittest.TestCase):
    def test_single_profession_route(self):
        rs = base_recipes() + [toy.recipe(10, "LW basic", LW, {toy.COPPER_BAR: 1})]
        p = run_caps(rs, {LW: 40}, BARS)
        self.assertEqual(p.final_skill, {LW: 40})
        self.assertEqual({s.profession for s in p.steps}, {LW})

    def test_per_profession_targets(self):
        p = run_caps(base_recipes(), {BS: 30, ENCH: 20}, BARS)
        self.assertEqual(p.final_skill, {BS: 30, ENCH: 20})

    def test_goal_already_reached(self):
        p = run_caps(base_recipes(), {BS: 40, ENCH: 20}, BARS, stock=toy.stock(skills={BS: 50}))
        self.assertFalse([s for s in p.steps if s.profession == BS])
        self.assertIn("Blacksmithing already at 50", p.events)
        self.assertEqual(p.final_skill[ENCH], 20)

    def test_no_disenchant_without_enchanting(self):
        rs = base_recipes() + [toy.recipe(3, "BS belt", BS, {toy.COPPER_BAR: 2}, (toy.BELT, 1))]
        listings = {**BARS, toy.DUST: [(5000, 100000)], toy.ESSENCE: [(20000, 100000)]}
        with_ench = run_caps(rs, {BS: 30, ENCH: 30}, listings)
        self.assertIn(3, {s.spell_id for s in with_ench.steps})  # the disenchant value pulls it in
        alone = run_caps(rs, {BS: 30}, listings)
        self.assertEqual({s.spell_id for s in alone.steps}, {1})
        self.assertEqual(alone.held_for_de, {})

    def test_craft_once_final_step(self):
        rs = base_recipes() + [toy.recipe(5, "BS final", BS, {toy.IRON_BAR: 1}, req=20)]
        p = run_caps(rs, {BS: 20}, {**BARS, toy.IRON_BAR: [(700, 100)]}, craft_once={BS: 5})
        last = p.steps[-1]
        self.assertEqual((last.spell_id, last.crafts, last.skill_from, last.skill_to), (5, 1, 20, 20))
        self.assertGreaterEqual(last.cash, 700)

    def test_exclude_recipe(self):
        rs = base_recipes() + [toy.recipe(3, "BS iron", BS, {toy.IRON_BAR: 1}, (toy.STONE, 1))]
        listings = {**BARS, toy.IRON_BAR: [(10, 100000)]}
        self.assertIn(3, {s.spell_id for s in run_caps(rs, {BS: 30}, listings).steps})
        p = run_caps(rs, {BS: 30}, listings, exclude=frozenset({3}))
        self.assertEqual({s.spell_id for s in p.steps}, {1})

    def test_rank_trained_with_trainer_recipe_in_window(self):
        rs = base_recipes() + [toy.recipe(6, "BS mid", BS, {toy.IRON_BAR: 1}, (toy.STONE, 1), req=60)]
        p = run_caps(rs, {BS: 80}, {**BARS, toy.IRON_BAR: [(10, 100000)]})
        self.assertIn("Blacksmithing 60: train rank up to 150 (4s 50c)", p.events)
        train = p.events.index("Blacksmithing 60: train rank up to 150 (4s 50c)")
        self.assertTrue(p.events[train + 1].startswith("Blacksmithing 60: Learn BS mid"))
        self.assertEqual(p.final_skill[BS], 80)

    def test_rank_trained_at_cap_without_trainer_visit(self):
        p = run_caps(base_recipes(), {BS: 80}, BARS)
        self.assertIn("Blacksmithing 75: train rank up to 150 (4s 50c)", p.events)

    def test_no_window_training_beyond_target(self):
        rs = base_recipes() + [toy.recipe(6, "BS mid", BS, {toy.IRON_BAR: 1}, (toy.STONE, 1), req=60)]
        p = run_caps(rs, {BS: 70}, {**BARS, toy.IRON_BAR: [(10, 100000)]})
        self.assertFalse([e for e in p.events if "train rank" in e])


class ResolveGoalsTests(unittest.TestCase):
    def setUp(self):
        from yap_forever.config import Goal
        self.Goal = Goal
        self.gd = toy.gamedata(base_recipes() + [
            toy.recipe(3, "BS Iron Thing", BS, {toy.IRON_BAR: 1}, req=40),
            toy.recipe(4, "BS Mystery", BS, {toy.IRON_BAR: 1}, t=(50, 60, 70, 80), req=50, source="unknown")])

    def test_resolve_recipe_by_name_and_id(self):
        from yap_forever.planner import resolve_goals
        caps, once = resolve_goals({BS: self.Goal(recipe="bs iron thing"), ENCH: self.Goal(skill=150)}, self.gd)
        self.assertEqual((caps, once), ({BS: 40, ENCH: 150}, {BS: 3}))
        self.assertEqual(resolve_goals({BS: self.Goal(recipe="3")}, self.gd), ({BS: 40}, {BS: 3}))

    def test_resolve_unknown_recipe_raises(self):
        from yap_forever.planner import resolve_goals
        with self.assertRaisesRegex(ValueError, "no Blacksmithing recipe called 'Iron Nothing'"):
            resolve_goals({BS: self.Goal(recipe="Iron Nothing")}, self.gd)

    def test_resolve_unlearnable_recipe_raises(self):
        from yap_forever.planner import resolve_goals
        with self.assertRaisesRegex(ValueError, "can't plan BS Mystery yet"):
            resolve_goals({BS: self.Goal(recipe="BS Mystery")}, self.gd)

    def test_resolve_favor_recipe(self):
        from yap_forever.planner import resolve_goals
        favor = FavorData({4: 30}, {}, [])
        self.assertEqual(resolve_goals({BS: self.Goal(recipe="BS Mystery")}, self.gd, favor=favor),
                         ({BS: 50}, {BS: 4}))

    def test_favor_recipe_target_uses_the_favor_skill(self):
        from yap_forever.config import Goal
        from yap_forever.favor import FavorData
        from yap_forever.planner import resolve_goals
        gd = toy.gamedata([toy.recipe(5, "Veteran Belt", BS, {toy.IRON_BAR: 2}, (toy.BELT, 1), t=(1, 50, 60, 70),
                                      source="unknown")])
        favor = FavorData({5: 30}, {5: 45}, [])
        caps, once = resolve_goals({BS: Goal(recipe="Veteran Belt")}, gd, favor)
        self.assertEqual((caps, once), ({BS: 45}, {BS: 5}))


class RouteModeTests(unittest.TestCase):
    def run_mode(self, mode, recipes, listings, bank):
        gd = toy.gamedata(recipes)
        st = toy.stock(bank)
        return plan(gd, Valuer(toy.market(listings), gd, st, mode=mode), st, toy.NO_FAVOR, caps={BS: 20})

    def test_gold_mode_prefers_bank_mats(self):
        rs = [toy.recipe(11, "BS essence", BS, {toy.ESSENCE: 1}), toy.recipe(12, "BS iron", BS, {toy.IRON_BAR: 1})]
        listings = {toy.ESSENCE: [(5000, 100)], toy.IRON_BAR: [(500, 100000)]}
        bank = {toy.ESSENCE: 30}
        self.assertEqual({s.spell_id for s in self.run_mode("gold", rs, listings, bank).steps}, {11})
        self.assertEqual({s.spell_id for s in self.run_mode("value", rs, listings, bank).steps}, {12})

    def test_gold_mode_breaks_cash_ties_by_value(self):
        rs = [toy.recipe(11, "BS essence", BS, {toy.ESSENCE: 1}), toy.recipe(13, "BS dust", BS, {toy.DUST: 1})]
        listings = {toy.ESSENCE: [(5000, 100)], toy.DUST: [(100, 100)]}
        p = self.run_mode("gold", rs, listings, {toy.ESSENCE: 30, toy.DUST: 30})
        self.assertEqual({s.spell_id for s in p.steps}, {13})
        self.assertEqual(p.cash_total, 0)

    def test_unknown_mode_raises(self):
        gd = toy.gamedata([])
        with self.assertRaises(ValueError):
            Valuer(toy.market(), gd, toy.stock(), mode="fast")


class KeepGreensTests(unittest.TestCase):
    def plan(self, keep):
        import dataclasses
        rs = [toy.recipe(3, "BS belt", BS, {toy.COPPER_BAR: 1}, (toy.BELT, 1))]
        listings = {**BARS, toy.BELT: [(900, 100)], toy.DUST: [(5000, 100000)]}
        gd = toy.gamedata(rs)
        st = dataclasses.replace(toy.stock(), keep_greens=keep)
        return plan(gd, Valuer(toy.market(listings), gd, st), st, toy.NO_FAVOR, caps={BS: 10})

    def test_greens_kept_for_another_characters_enchanting(self):
        kept, sold = self.plan(True), self.plan(False)
        self.assertGreater(kept.kept_greens.get(toy.BELT, 0), 0)
        self.assertEqual(sold.kept_greens, {})
        self.assertLess(kept.sale_proceeds, sold.sale_proceeds)
        self.assertGreater(kept.leftover_value, sold.leftover_value)

    def test_stock_keep_greens_setting(self):
        import tempfile
        from pathlib import Path
        from yap_forever.config import load_stock
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "stock.toml"
            p.write_text("keep_greens = true\n[items]\n", encoding="utf-8")
            self.assertTrue(load_stock(p).keep_greens)
            p.write_text("[items]\n", encoding="utf-8")
            self.assertFalse(load_stock(p).keep_greens)


class CraftOnceToolTests(unittest.TestCase):
    def test_craft_once_buys_a_missing_tool(self):
        rs = base_recipes() + [toy.recipe(5, "BS final", BS, {toy.IRON_BAR: 1}, req=20, tools=[162])]
        p = run_caps(rs, {BS: 20}, {**BARS, toy.IRON_BAR: [(700, 100)]}, craft_once={BS: 5})
        last = p.steps[-1]
        self.assertEqual((last.spell_id, last.crafts), (5, 1))
        self.assertGreaterEqual(last.cash, 700 + 18)  # the Blacksmith Hammer from a vendor
        self.assertTrue(any(e.endswith(": Buy tool Blacksmith Hammer (vendor 0s 18c)") for e in p.events))


class GreensForDisenchantingTests(unittest.TestCase):
    """Greens are held for disenchanting when that is the only source and Enchanting reaches their gate."""

    def test_greens_held_when_de_is_only_source(self):
        rs = [toy.recipe(1, "Belt", BS, {toy.COPPER_BAR: 1}, (toy.BELT, 1)),
              toy.recipe(2, "Ench start", ENCH, {toy.ROD: 1}, t=(1, 30, 30, 30)),
              toy.recipe(4, "Ench dust", ENCH, {toy.DUST: 1}, req=25)]
        p, *_ = run_with_data(rs, BARS)  # no dust on the AH at all
        self.assertGreater(p.final_skill[ENCH], 30)

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


class RankCutTests(unittest.TestCase):
    """A rank training ends the profession's Step: no Step spans the skill a rank was trained at."""

    def master_route(self, recipes=None):
        return toy.master_route_data(recipes)[0]

    def test_step_never_spans_a_rank_training(self):
        p = self.master_route()
        self.assertEqual([(s, cap) for _p, s, cap, _f in p.ranks], [(75, 150), (150, 225), (225, 300)])
        steps = [s for s in p.steps if s.profession == BS and s.spell_id == 1]
        for _prof, trained, _cap, _fee in p.ranks:
            self.assertFalse([s for s in steps if s.skill_from < trained < s.skill_to], trained)
            self.assertTrue(any(s.skill_to == trained for s in steps), trained)  # one Step ends there
            self.assertTrue(any(s.skill_from == trained for s in steps), trained)  # and one starts there
        self.assertEqual([(s.skill_from, s.skill_to) for s in steps], [(1, 75), (75, 150), (150, 225), (225, 300)])

    def test_totals_unchanged_by_the_cut(self):
        # a yellow-then-grey recipe so crafts and buffers differ; the literals are what main (df91a1e) gives
        rs = [toy.recipe(1, "BS yellow", BS, {toy.COPPER_BAR: 2}, (toy.STONE, 1), t=(1, 60, 150, 320)),
              toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})]
        p = self.master_route(rs)
        self.assertEqual([(s.skill_from, s.skill_to) for s in p.steps], [(1, 75), (75, 150), (150, 225), (225, 300)])
        self.assertEqual(p.cash_total, 157950)
        self.assertAlmostEqual(p.economic_total, 156510.11866886253, places=6)
        self.assertAlmostEqual(sum(s.crafts for s in p.steps), 719.9406655687324, places=6)
        self.assertAlmostEqual(sum(s.buffered for s in p.steps), 818.9317654040408, places=6)
        self.assertEqual(p.fees, 13950)
        self.assertEqual(sum(s.cash for s in p.steps), 144000)  # what the Steps carry, as on main
        self.assertEqual(sum(s.economic for s in p.steps), 144000)
        self.assertAlmostEqual(sum(s.materials[toy.COPPER_BAR] for s in p.steps), 1439.881331137465, places=6)
        self.assertAlmostEqual(p.bought[toy.COPPER_BAR], 1439.8813311374647, places=6)


class AhPremiumPlanTests(unittest.TestCase):
    """#62 in the totals: a craft's AH sales count only well above its vendor price, up to the sale limit."""
    GEAR = 7777  # a made-up craft with a 1g vendor price

    def plan(self, listing):
        gd = toy.gamedata([toy.recipe(1, "BS gear", BS, {toy.COPPER_BAR: 1}, (self.GEAR, 1))])
        gd.items[self.GEAR] = toy.item(self.GEAR, "Test Gear", sell=10000)
        st = toy.stock()
        m = toy.market({**BARS, self.GEAR: [listing]})
        return plan(gd, Valuer(m, gd, st), st, toy.NO_FAVOR, caps={BS: 20}), m

    def test_dead_market_vendored_in_totals(self):
        p, _m = self.plan((13685, 50))  # net 1.3g: every one goes to a vendor
        n = p.leftovers[self.GEAR]
        self.assertGreater(n, 5)
        self.assertAlmostEqual(p.sale_proceeds, n * 10000)

    def test_scarce_market_counted_to_the_limit_in_totals(self):
        p, m = self.plan((115790, 1))  # one listed at 11x: five on the AH, the rest to a vendor
        n = p.leftovers[self.GEAR]
        self.assertAlmostEqual(p.sale_proceeds, 5 * m.net_sell(self.GEAR) + (n - 5) * 10000)

    def test_green_below_the_premium_is_disenchanted_with_enchanting_planned(self):
        # the effect behind the real-data route change: a green whose AH price no longer counts is kept for
        # disenchanting when its materials are worth more than its vendor price (here 3.75 dust at 30c and the rest,
        # about 1s 24c, against a 1s vendor price and an AH net of 1s 90c, below 2x)
        gd = toy.gamedata([toy.recipe(1, "BS belt", BS, {toy.COPPER_BAR: 1}, (toy.BELT, 1)),
                           toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})])
        st = toy.stock(skills={ENCH: 100})  # past the skill disenchanting gives: only the materials count
        m = toy.market({**BARS, toy.BELT: [(200, 50)], toy.DUST: [(30, 100000)]})
        p = plan(gd, Valuer(m, gd, st), st, toy.NO_FAVOR, caps={BS: 20, ENCH: 120})
        self.assertTrue(any("disenchant" in e and "Runed Copper Belt" in e for e in p.events), p.events)
        self.assertNotIn(toy.BELT, p.leftovers)
        self.assertIn(toy.DUST, p.de_materials)
        self.assertIsNone(Valuer(m, gd, st).ah_price(toy.BELT))


class VendorCashbackTests(unittest.TestCase):
    """#97: a craft's vendor price counts in choosing the route. Each output unit is credited once: reused, else kept
    (held for this route's disenchanting, or a keep_greens green), else sold at its vendor price; the vendor credit
    never takes a craft below zero cost, and ties go to the higher skill-up chance."""
    PLATE, SCRAP, BOLT, PIN, MISSING = 7701, 7702, 7703, 7704, 7799  # made-up crafts (MISSING: no item row)

    def gamedata(self, recipes):
        gd = toy.gamedata(recipes)
        for i, name, sell in ((self.PLATE, "Test Plate", 2000), (self.SCRAP, "Test Scrap", 0),
                              (self.BOLT, "Test Bolt", 10), (self.PIN, "Test Pin", 30)):
            gd.items[i] = toy.item(i, name, sell=sell)
        return gd

    def plan(self, recipes, listings, mode, caps=None, stock=None, gd=None, reuse=None):
        gd = gd or self.gamedata(recipes)
        st = stock or toy.stock()
        return plan(gd, Valuer(toy.market(listings), gd, st, mode=mode), st, toy.NO_FAVOR, caps=caps or {BS: 10},
                    reuse=reuse)

    def spells(self, p, prof=BS):
        return {s.spell_id for s in p.steps if s.profession == prof}

    def test_vendor_cashback_wins(self):
        # same chance; A's reagents cost 10s less but its craft vendors for nothing, B's vendors for 20s
        rs = [toy.recipe(41, "A cheap", BS, {toy.COPPER_BAR: 1}, (self.SCRAP, 1)),
              toy.recipe(42, "B cashback", BS, {toy.IRON_BAR: 1}, (self.PLATE, 1))]
        listings = {toy.COPPER_BAR: [(1000, 100000)], toy.IRON_BAR: [(2000, 100000)]}
        for mode in ("gold", "value"):
            with self.subTest(mode=mode):
                self.assertEqual(self.spells(self.plan(rs, listings, mode)), {42})

    def test_cashback_floor(self):
        # The best pick without vendor credit is L (1 in 3, 15c a point, nothing back), so both crafts that vendor
        # pass the chance rule. H1: orange, 40c, 1s back; H2: 1 in 2, 50c a point, 2s back. Unfloored, H2 would earn
        # 1.5s a point to H1's 60c; floored, both cost 0 and the higher chance (H1) wins, though H2 has the lower id.
        rs = [toy.recipe(51, "L plain", BS, {toy.COPPER_BAR: 1}, t=(1, 8, 9, 11)),
              toy.recipe(52, "H2 more back", BS, {toy.ESSENCE: 1}, (self.PIN, 1), t=(1, 8, 10, 12)),
              toy.recipe(53, "H1 orange", BS, {toy.IRON_BAR: 1}, (self.BOLT, 1))]
        gd = self.gamedata(rs)
        gd.items[self.BOLT] = toy.item(self.BOLT, "Test Bolt", sell=100)
        gd.items[self.PIN] = toy.item(self.PIN, "Test Pin", sell=100)
        listings = {toy.COPPER_BAR: [(5, 1000)], toy.ESSENCE: [(25, 1000)], toy.IRON_BAR: [(40, 1000)]}
        for mode in ("gold", "value"):
            with self.subTest(mode=mode):
                p = self.plan(rs, listings, mode, caps={BS: 11}, stock=toy.stock(skills={BS: 10}), gd=gd)
                self.assertEqual(self.spells(p), {53})

    def test_held_green_no_gold_credit(self):
        # the belt is held for this route's disenchanting: its 1s vendor price earns no gold
        rs = [toy.recipe(1, "BS belt", BS, {toy.COPPER_BAR: 1}, (toy.BELT, 1)),
              toy.recipe(3, "BS iron", BS, {toy.IRON_BAR: 1}),
              toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})]
        listings = {toy.COPPER_BAR: [(100, 100000)], toy.IRON_BAR: [(50, 100000)]}
        caps = {BS: 10, ENCH: 10}
        held = self.plan(rs, {**listings, toy.IRON_BAR: [(150, 100000)]}, "gold", caps=caps)
        self.assertTrue(any("disenchant" in e and "Runed Copper Belt" in e for e in held.events))  # the fixture holds it
        self.assertEqual(self.spells(self.plan(rs, listings, "gold", caps=caps)), {3})

    def test_keep_greens_held_in_both_modes(self):
        # keep_greens, no Enchanting planned: the belt (1s at a vendor) is kept, worth its dust in value mode only
        import dataclasses
        rs = [toy.recipe(1, "BS belt", BS, {toy.COPPER_BAR: 1}, (toy.BELT, 1)),
              toy.recipe(3, "BS iron", BS, {toy.IRON_BAR: 1})]
        listings = {toy.COPPER_BAR: [(100, 100000)], toy.IRON_BAR: [(95, 100000)], toy.DUST: [(5000, 100000)]}
        st = dataclasses.replace(toy.stock(), keep_greens=True)
        self.assertEqual(self.spells(self.plan(rs, listings, "gold", stock=st)), {3})
        value = self.plan(rs, listings, "value", stock=st)
        self.assertEqual(self.spells(value), {1})
        self.assertIn(toy.BELT, value.kept_greens)

    def test_reuse_not_credited_twice(self):
        # A's bolt is reused (worth 50c) by later steps for 10 bolts; a reused bolt isn't also sold (40c)
        rs = [toy.recipe(61, "A bolt", BS, {toy.COPPER_BAR: 1}, (self.BOLT, 1)),
              toy.recipe(62, "B plain", BS, {toy.IRON_BAR: 1})]
        gd = self.gamedata(rs)
        gd.items[self.BOLT] = toy.item(self.BOLT, "Test Bolt", sell=40)
        listings = {toy.COPPER_BAR: [(100, 100000)], toy.IRON_BAR: [(30, 100000)]}
        for mode in ("gold", "value"):
            with self.subTest(mode=mode):
                p = self.plan(rs, listings, mode, caps={BS: 20}, gd=gd, reuse={self.BOLT: (10, 50)})
                self.assertEqual(self.spells(p), {62})

    def test_vendor_zero_or_unknown_item(self):
        # RF3: a craft vendoring for 0 and one whose item the game data lacks get no credit and don't crash; a craft
        # with a vendor price does get it
        rs = [toy.recipe(71, "A unknown", BS, {toy.COPPER_BAR: 1}, (self.MISSING, 1)),
              toy.recipe(72, "B nothing", BS, {toy.DUST: 1}, (self.SCRAP, 1)),
              toy.recipe(73, "C vendors", BS, {toy.IRON_BAR: 1}, (self.PLATE, 1))]
        listings = {toy.COPPER_BAR: [(1000, 100000)], toy.DUST: [(1001, 100000)], toy.IRON_BAR: [(2500, 100000)]}
        for mode in ("gold", "value"):
            with self.subTest(mode=mode):
                self.assertEqual(self.spells(self.plan(rs, listings, mode)), {73})
                p = self.plan(rs[:2], listings, mode)  # neither is credited: the cheaper reagents win
                self.assertEqual(self.spells(p), {71})
                self.assertIn(self.MISSING, p.leftovers)

    def test_vendor_back_and_ah_extra(self):
        # 10 Test Plates left over, 20s at a vendor, AH-worthy (net 95s): 5 on the AH, all 10 counted at the vendor
        rs = [toy.recipe(42, "B plate", BS, {toy.IRON_BAR: 1}, (self.PLATE, 1))]
        listings = {toy.IRON_BAR: [(2000, 100000)], self.PLATE: [(10000, 50)]}
        p = self.plan(rs, listings, "value", caps={BS: 11})
        self.assertAlmostEqual(p.leftovers[self.PLATE], 10)
        self.assertAlmostEqual(p.vendor_back, 10 * 2000)
        self.assertAlmostEqual(p.sale_proceeds, 5 * 9500 + 5 * 2000)
        self.assertAlmostEqual(p.ah_extra, p.sale_proceeds - p.vendor_back)
        self.assertAlmostEqual(p.net_gold, p.cash_total - 10 * 2000)
        self.assertAlmostEqual(p.economic_total, 10 * 2000 - 10 * 2000)  # vendor sales only: the AH's extra is out

    def test_vendor_back_leaves_kept_items_out(self):
        import dataclasses
        belt = [toy.recipe(1, "BS belt", BS, {toy.COPPER_BAR: 1}, (toy.BELT, 1))]
        kept = self.plan(belt, BARS, "value", stock=dataclasses.replace(toy.stock(), keep_greens=True))
        self.assertGreater(kept.kept_greens.get(toy.BELT, 0), 0)
        self.assertEqual(kept.vendor_back, 0)
        # held for disenchanting: Enchanting stalls at 30, below the belt's gate of 150, so the belts stay held
        held_rs = belt + [toy.recipe(2, "Ench start", ENCH, {toy.ROD: 1}, t=(1, 30, 30, 30))]
        gd = self.gamedata(held_rs)
        gd.items[toy.BELT].item_level = 48
        held = self.plan(held_rs, {**BARS, 11176: [(5000, 1000)]}, "value", caps={BS: 10, ENCH: 150}, gd=gd)
        self.assertIn(toy.BELT, held.held_for_de)
        self.assertEqual(held.vendor_back, 0)

    def test_vendor_back_counts_every_crafted_unit(self):
        # C38: with nothing reused or kept, every unit crafted is sold and counted at its vendor price
        rs = [toy.recipe(42, "B plate", BS, {toy.IRON_BAR: 1}, (self.PLATE, 1), t=(1, 5, 15, 30))]
        for mode in ("gold", "value"):
            with self.subTest(mode=mode):
                p = self.plan(rs, {toy.IRON_BAR: [(2000, 100000)]}, mode, caps={BS: 20})
                made = sum(s.crafts for s in p.steps)
                self.assertGreater(made, 19)  # yellow and green points: more crafts than points
                self.assertAlmostEqual(p.vendor_back, made * 2000)

    def test_value_measure_ignores_ah_resale(self):
        # the same route where the Test Plate sells on the AH and where it doesn't: equal in total value, so settling
        # keeps whichever comes first
        from yap_forever.compare import settle_routes
        rs = [toy.recipe(42, "B plate", BS, {toy.IRON_BAR: 1}, (self.PLATE, 1))]
        ah = self.plan(rs, {toy.IRON_BAR: [(2000, 100000)], self.PLATE: [(10000, 50)]}, "value")
        none = self.plan(rs, {toy.IRON_BAR: [(2000, 100000)]}, "value")
        self.assertGreater(ah.ah_extra, 0)
        self.assertEqual(none.ah_extra, 0)
        self.assertAlmostEqual(ah.economic_total, none.economic_total)
        for first, second in ((none, ah), (ah, none)):
            routes, _same = settle_routes([first, second], {BS: 10})
            self.assertIs(routes["value"], first)

    def test_gold_to_bring_unchanged(self):
        # "Gold to bring" is the gold up front: the vendor's cashback arrives after crafting. Literal from main (4870ca5).
        from yap_forever.shopping import gold_to_bring
        gd, m, st = self.gear_data()
        for mode in ("gold", "value"):
            with self.subTest(mode=mode):
                p = plan(gd, Valuer(m, gd, st, mode=mode), st, toy.NO_FAVOR, caps={BS: 20})
                self.assertGreater(p.vendor_back, 0)
                self.assertEqual(gold_to_bring(p, gd, m, st), 25000)

    def test_study_hint_unchanged(self):
        # the Dedicated Study hint stays on the row's own cost: 23000c over 19 points, not net of the vendor's 6712c.
        # Text from main (4870ca5), with 7b's vendor-back suffix (23 expected crafts at 3s) before the hint.
        from yap_forever.guide import render_guide
        gd, m, st = self.gear_data()
        for mode in ("gold", "value"):
            with self.subTest(mode=mode):
                p = plan(gd, Valuer(m, gd, st, mode=mode), st, toy.NO_FAVOR, caps={BS: 20})
                text = render_guide(p, gd, m, st, {BS: 20}, mode=mode, study_hint_gold_per_point=0.01)
                (row,) = [line for line in text.splitlines() if "× BS gear" in line]
                self.assertIn("— 25 Copper Bar → sell to a vendor: about 69s back — about 12s a point here: Dedicated Study",
                              row)

    def test_vendor_credit_never_pulls_in_a_lower_chance_craft(self):
        # alt 1's shape: a 1-in-5 craft on 20c of bought iron vendors 3 x 50c back, above its cost. It may not displace
        # an orange craft: (1) one that costs 5c net (10c bought, 5c back); (2) one made from the bank (no gold, 50c of
        # value), against which the low-chance craft would tie at zero gold
        rs = [toy.recipe(81, "Low chance", BS, {toy.IRON_BAR: 1}, (self.PIN, 3), t=(1, 6, 8, 11)),
              toy.recipe(82, "High chance", BS, {toy.COPPER_BAR: 1}, (self.BOLT, 1))]
        gd = self.gamedata(rs)
        gd.items[self.BOLT] = toy.item(self.BOLT, "Test Bolt", sell=5)
        gd.items[self.PIN] = toy.item(self.PIN, "Test Pin", sell=50)
        iron = {toy.IRON_BAR: [(20, 1000)]}
        cases = {"5c net": ({**iron, toy.COPPER_BAR: [(10, 1000)]}, None),
                 "from the bank": ({**iron, toy.COPPER_BAR: [(50, 1000)]}, {toy.COPPER_BAR: 10})}
        for case, (listings, bank) in cases.items():
            for mode in ("gold", "value"):
                with self.subTest(case=case, mode=mode):
                    p = self.plan(rs, listings, mode, caps={BS: 11}, stock=toy.stock(bank, skills={BS: 10}), gd=gd)
                    self.assertEqual(self.spells(p), {82})

    def test_gold_tie_goes_to_the_higher_chance(self):
        # at equal gold the higher skill-up chance wins before the lower total value: both crafts use bank materials
        # (no gold); the 1-in-5 one uses 5 dust worth 1s in all, the orange one an essence worth 50s
        rs = [toy.recipe(91, "Low chance", BS, {toy.DUST: 1}, t=(1, 6, 8, 11)),
              toy.recipe(92, "High chance", BS, {toy.ESSENCE: 1})]
        listings = {toy.DUST: [(20, 1000)], toy.ESSENCE: [(5000, 1000)]}
        st = toy.stock({toy.DUST: 10, toy.ESSENCE: 10}, skills={BS: 10})
        p = self.plan(rs, listings, "gold", caps={BS: 11}, stock=st)
        self.assertEqual(p.cash_total, 0)
        self.assertEqual(self.spells(p), {92})

    def test_value_tie_goes_to_the_higher_chance(self):
        # value mode: two crafts at the same 20c a point, an orange one and a 1-in-2 one (the lower id): the higher
        # chance wins
        rs = [toy.recipe(95, "Half chance", BS, {toy.DUST: 1}, t=(1, 8, 10, 12)),
              toy.recipe(96, "Orange", BS, {toy.COPPER_BAR: 1})]
        listings = {toy.DUST: [(10, 1000)], toy.COPPER_BAR: [(20, 1000)]}
        p = self.plan(rs, listings, "value", caps={BS: 11}, stock=toy.stock(skills={BS: 10}))
        self.assertEqual(self.spells(p), {96})

    def test_vendor_credit_never_alone_below_zero(self):
        # A: 1s of reagents, 2 bolts a craft: one reused (worth 80c), one sold (1s). The reuse credit stays as before;
        # the vendor credit is what is left of the cost, 20c, so A's gold is 0, not -80c. B: 50c, its scrap reused at
        # 90c: -40c. B wins.
        rs = [toy.recipe(97, "A bolts", BS, {toy.IRON_BAR: 1}, (self.BOLT, 2)),
              toy.recipe(98, "B scrap", BS, {toy.COPPER_BAR: 1}, (self.SCRAP, 1))]
        gd = self.gamedata(rs)
        gd.items[self.BOLT] = toy.item(self.BOLT, "Test Bolt", sell=100)
        listings = {toy.IRON_BAR: [(100, 1000)], toy.COPPER_BAR: [(50, 1000)]}
        for mode in ("gold", "value"):
            with self.subTest(mode=mode):
                p = self.plan(rs, listings, mode, caps={BS: 11}, stock=toy.stock(skills={BS: 10}), gd=gd,
                              reuse={self.BOLT: (1, 80), self.SCRAP: (1, 90)})
                self.assertEqual(self.spells(p), {98})

    def gear_data(self):
        """(game data, market, stock) of a one-recipe route, 1–20, whose crafts sell to a vendor for 3s each."""
        gd = self.gamedata([toy.recipe(1, "BS gear", BS, {toy.COPPER_BAR: 1}, (self.PLATE, 1), t=(1, 10, 15, 30))])
        gd.items[self.PLATE] = toy.item(self.PLATE, "Test Plate", sell=300)
        return gd, toy.market({toy.COPPER_BAR: [(1000, 100000)]}), toy.stock()


class FixedProfessionTests(unittest.TestCase):
    """#96, C43: a profession the route doesn't plan, held at its skill (plan's `fixed`), crafts the route's reagents
    with its trainer recipes up to that skill when that beats buying by the craft margin, and is never planned or
    reached."""

    def test_fixed_profession_crafts_and_is_never_reached(self):
        dye = 7900
        gd = toy.gamedata([toy.recipe(3, "BS dyed", BS, {dye: 1}),
                           toy.recipe(4, "Ench dye", ENCH, {toy.SHARD: 1}, (dye, 1), req=40, fee=500)])
        gd.items[dye] = toy.item(dye, "Test Dye", sell=5)
        m = toy.market({dye: [(100, 100000)], toy.SHARD: [(50, 100000)]})
        st = toy.stock(skills={ENCH: 50})
        held = plan(gd, Valuer(m, gd, st, mode="gold"), st, toy.NO_FAVOR, caps={BS: 20}, fixed={ENCH: 50})
        self.assertEqual((held.final_skill, held.other_crafts, held.crafted), ({BS: 20}, {dye: 4}, {dye: 19}))
        self.assertEqual({s.profession for s in held.steps}, {BS})
        self.assertEqual((held.fees, held.learn_log[1:]), (0, []))  # only BS dyed is learned (no fee in the toy)
        low = plan(gd, Valuer(m, gd, st, mode="gold"), st, toy.NO_FAVOR, caps={BS: 20}, fixed={ENCH: 39})
        self.assertEqual((low.other_crafts, low.bought), ({}, {dye: 19}))  # below the recipe's skill: bought
        bare = plan(gd, Valuer(m, gd, st, mode="gold"), st, toy.NO_FAVOR, caps={BS: 20})
        self.assertEqual((bare.other_crafts, bare.bought), ({}, {dye: 19}))

    def test_fixed_profession_never_crafts_a_tool(self):
        # C43: the Runed Copper Rod a recipe needs is bought, never made with the fixed Enchanting's known recipe
        gd = toy.gamedata([toy.recipe(3, "BS rod", BS, {toy.COPPER_BAR: 1}, tools=[373]),
                           toy.recipe(4, "Ench rod", ENCH, {toy.SHARD: 1}, (toy.ROD_TOOL, 1), req=1)])
        m = toy.market({toy.COPPER_BAR: [(10, 100000)], toy.SHARD: [(1, 100000)], toy.ROD_TOOL: [(5000, 10)]})
        st = toy.stock(skills={ENCH: 50})
        p = plan(gd, Valuer(m, gd, st, mode="gold"), st, toy.NO_FAVOR, caps={BS: 20}, fixed={ENCH: 50})
        self.assertEqual(p.steps[0].tools_bought, {toy.ROD_TOOL: 1})
