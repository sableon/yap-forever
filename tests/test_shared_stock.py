"""Characters on one ruleset and faction share gold and mail each other items (shared.py)."""
import dataclasses
import tempfile
import unittest
from pathlib import Path

from tests import toy
from yap_forever import profile, settings, shared
from yap_forever.costmodel import Valuer
from yap_forever.planner import plan
from yap_forever.shopping import bring_list, bring_text, render_shopping
from yap_forever.trips import Trip

BS, ENCH = 164, 333
S, T = toy.COPPER_BAR, toy.IRON_BAR
BARS = {S: [(100, 100000)]}


def recipes():
    return [toy.recipe(1, "BS basic", BS, {S: 1}, (toy.STONE, 1)), toy.recipe(2, "Ench basic", ENCH, {toy.ROD: 1})]


def run(stock, listings=BARS, rs=None, mode="value", bonding=None):
    """Plan with toy data; bonding: item -> Bonding to set before planning."""
    gd = toy.gamedata(rs or recipes())
    for i, b in (bonding or {}).items():
        gd.items[i].bonding = b
    return plan(gd, Valuer(toy.market(listings), gd, stock, mode=mode), stock, toy.NO_FAVOR, caps={BS: 30})


def bars_used(p):
    return sum(st.from_mail.get(S, 0) for st in p.steps)


class MailPoolTests(unittest.TestCase):
    def test_a_mailable_item_is_used_before_buying(self):
        alone = run(toy.stock())
        p = run(toy.stock(shared={"Ann": {S: 10}}))
        self.assertEqual(bars_used(p), 10)
        self.assertEqual(p.used_mail, {S: [("Ann", 10)]})
        self.assertLess(p.cash_total, alone.cash_total)
        self.assertEqual(alone.bought[S] - p.bought[S], 10)

    def test_the_planner_does_not_change_the_stock_it_was_given(self):
        st = toy.stock(shared={"Ann": {S: 10}})
        run(st)
        self.assertEqual(st.shared, {"Ann": {S: 10}})

    def test_own_items_are_used_first(self):
        p = run(toy.stock({S: 6}, shared={"Ann": {S: 10}}))
        self.assertEqual(p.used_stock, {S: 6})
        self.assertEqual(bars_used(p), 10)  # then the mail, and only then the AH
        self.assertEqual(p.used_mail, {S: [("Ann", 10)]})
        only_own = run(toy.stock({S: 6}))
        self.assertEqual(only_own.used_stock, {S: 6})
        self.assertEqual(only_own.used_mail, {})

    def test_enough_own_items_leave_the_others_alone(self):
        p = run(toy.stock({S: 100}, shared={"Ann": {S: 10}}))
        self.assertEqual(p.used_mail, {})
        self.assertEqual(bars_used(p), 0)

    def test_several_sources_are_named_each_in_name_order(self):
        p = run(toy.stock(shared={"Cyd": {S: 4}, "Ann": {S: 3}, "Bob": {S: 5}}))
        self.assertEqual(p.used_mail, {S: [("Ann", 3), ("Bob", 5), ("Cyd", 4)]})

    def test_a_soulbound_item_is_not_used(self):
        for bonding in (1, 4):
            with self.subTest(bonding=bonding):
                gd = toy.gamedata(recipes())
                gd.items[S].bonding = bonding
                group = shared.Group(2, "alliance", others={"Ann": toy.stock({S: 10})})
                self.assertEqual(group.shared_items(gd), {})
                p = run(toy.stock(shared=group.shared_items(gd)), bonding={S: bonding})
                self.assertEqual(p.used_mail, {})

    def test_mailable_bonding_kinds(self):
        gd = toy.gamedata(recipes())
        group = shared.Group(2, "alliance", others={"Ann": toy.stock({S: 1, T: 1, toy.ROD: 1, toy.STONE: 1})})
        for item, bonding in ((S, 0), (T, 2), (toy.ROD, 3), (toy.STONE, 1)):
            gd.items[item].bonding = bonding
        self.assertEqual(group.shared_items(gd), {"Ann": {S: 1, T: 1, toy.ROD: 1}})

    def test_items_the_game_data_does_not_know_are_not_mailed(self):
        gd = toy.gamedata(recipes())
        group = shared.Group(2, "alliance", others={"Ann": toy.stock({S: 1, 424242: 5})})
        self.assertEqual(group.shared_items(gd), {"Ann": {S: 1}})

    def test_value_mode_costs_the_sell_value_like_own_items(self):
        for mode in ("value", "gold"):
            with self.subTest(mode=mode):
                mine = run(toy.stock({S: 10}), mode=mode)
                mailed = run(toy.stock(shared={"Ann": {S: 10}}), mode=mode)
                self.assertAlmostEqual(mailed.economic_total, mine.economic_total, places=6)
                self.assertAlmostEqual(mailed.cash_total, mine.cash_total, places=6)
        gd = toy.gamedata(recipes())
        st = toy.stock(shared={"Ann": {S: 10}})
        v = Valuer(toy.market(BARS), gd, st, mode="value")
        alone = run(toy.stock())
        p = run(st)
        # ten bars come from Ann at what they would sell for, not for nothing and not at the buy price
        self.assertAlmostEqual(p.economic_total - alone.economic_total + (alone.cash_total - p.cash_total),
                               10 * v.owned_value(S), places=6)

    def test_gold_mode_takes_mailed_items_free_in_cash(self):
        p = run(toy.stock(shared={"Ann": {S: 10}}), mode="gold")
        self.assertEqual(bars_used(p), 10)
        self.assertEqual(p.bought[S], run(toy.stock(), mode="gold").bought[S] - 10)

    def test_mailed_items_are_part_of_the_steps_materials(self):
        p = run(toy.stock(shared={"Ann": {S: 10}}))
        first = p.steps[0]
        self.assertGreaterEqual(first.materials[S], first.from_mail[S])
        self.assertEqual(first.from_stock, {})

    def test_the_other_characters_stock_is_not_overdrawn(self):
        p = run(toy.stock(shared={"Ann": {S: 3}}))
        self.assertEqual(bars_used(p), 3)

    def test_a_tool_another_character_holds_counts_as_in_hand(self):
        rs = [toy.recipe(1, "BS tooled", BS, {S: 1}, (toy.STONE, 1), tools=[162])]
        without = run(toy.stock(), {**BARS, toy.HAMMER: [(500, 1)]}, rs=rs)
        mailed = run(toy.stock(shared={"Ann": {toy.HAMMER: 1}}), {**BARS, toy.HAMMER: [(500, 1)]}, rs=rs)
        self.assertLess(mailed.cash_total, without.cash_total)


class MailedPatternTests(unittest.TestCase):
    def scroll_recipes(self):
        return recipes() + [toy.recipe(3, "Scroll free", BS, {}, (toy.STONE, 1), source="scroll", scroll=toy.SCROLL)]

    def test_a_mailed_pattern_teaches_the_recipe_and_is_consumed(self):
        rs = self.scroll_recipes()
        st = toy.stock(shared={"Ann": {toy.SCROLL: 1}})
        p = run(st, BARS, rs=rs)  # the pattern is on no AH: the other character holding it is the only way
        self.assertNotIn(3, dict(p.skipped))
        self.assertIn(3, {s.spell_id for s in p.steps})
        self.assertEqual([how for *_x, spell, how in p.learn_log if spell == 3], ["mail"])
        self.assertIn("a pattern mailed by another of your characters", " ".join(p.events))
        self.assertEqual(p.used_mail, {toy.SCROLL: [("Ann", 1)]})
        self.assertEqual(p.used_stock, {})
        self.assertNotIn(toy.SCROLL, p.leftovers)
        self.assertEqual(p.bought.get(toy.SCROLL, 0), 0)
        text = "\n".join(render_shopping(p, toy.gamedata(rs), toy.market(BARS), st)[0])
        self.assertNotIn("Plans: Something", text)  # nothing to buy

    def test_a_mailed_pattern_is_given_up_at_its_sale_value_in_value_mode(self):
        rs = self.scroll_recipes()
        gd = toy.gamedata(rs)
        totals = []
        for price in (500, 3000):
            market = {**BARS, toy.SCROLL: [(price, 1)]}
            st = toy.stock(shared={"Ann": {toy.SCROLL: 1}})
            p = run(st, market, rs=rs)
            self.assertEqual([how for *_x, spell, how in p.learn_log if spell == 3], ["mail"])
            totals.append((p.cash_total, p.economic_total, Valuer(toy.market(market), gd, st).owned_value(toy.SCROLL)))
        (cash_a, econ_a, worth_a), (cash_b, econ_b, worth_b) = totals
        self.assertEqual(cash_a, cash_b)  # no cash
        self.assertAlmostEqual(econ_b - econ_a, worth_b - worth_a, places=6)

    def test_own_pattern_comes_before_a_mailed_one(self):
        rs = self.scroll_recipes()
        p = run(toy.stock({toy.SCROLL: 1}, shared={"Ann": {toy.SCROLL: 1}}), BARS, rs=rs)
        self.assertEqual([how for *_x, spell, how in p.learn_log if spell == 3], ["owned"])
        self.assertEqual(p.used_mail, {})

    def test_a_soulbound_pattern_stays_with_its_character(self):
        rs = self.scroll_recipes()
        gd = toy.gamedata(rs)
        gd.items[toy.SCROLL].bonding = 1
        group = shared.Group(2, "alliance", others={"Ann": toy.stock({toy.SCROLL: 1})})
        p = run(toy.stock(shared=group.shared_items(gd)), BARS, rs=rs, bonding={toy.SCROLL: 1})
        self.assertIn((3, "scroll not available: Plans: Something"), p.skipped)

    def test_a_mailed_pattern_is_used_up_for_the_next_recipe_that_needs_it(self):
        rs = self.scroll_recipes() + [toy.recipe(4, "Scroll too", BS, {}, (toy.STONE, 1), req=2,
                                                 source="scroll", scroll=toy.SCROLL)]
        p = run(toy.stock(shared={"Ann": {toy.SCROLL: 1}}), BARS, rs=rs)
        taught = [spell for *_x, spell, how in p.learn_log if how == "mail"]
        self.assertEqual(len(taught), 1)  # one pattern, one recipe


class SourceTextTests(unittest.TestCase):
    def rank_plan(self, owned=None):
        from yap_forever.planner import Plan, Step
        p = Plan(steps=[Step(BS, 225, 235, 1, "BS one", 10, 0, 0, {S: 60}, from_mail={S: 25}, buffered=10)],
                 ranks=[(BS, 225, 300, 9000)], bought={S: 35}, final_skill={BS: 235},
                 shared={"Bob": {S: 5}, "Ann": {S: 20}}, used_mail={S: [("Ann", 20), ("Bob", 5)]})
        gd = toy.gamedata([toy.recipe(1, "BS one", BS, {S: 6})])
        gd.items[S].stack = 20
        return p, gd

    def test_the_bring_list_names_each_source_in_name_order(self):
        p, gd = self.rank_plan()
        trip = Trip(225, BS, "rank", "Blacksmithing rank to 300")
        _reach, items = bring_list(p, gd, trip, None)
        self.assertEqual(items, [(S, 20, "from:Ann"), (S, 5, "from:Bob"), (S, 35, "mail")])

    def test_bring_text_says_mail_from(self):
        p, gd = self.rank_plan()
        trip = Trip(225, BS, "rank", "Blacksmithing rank to 300")
        text = bring_text(p, gd, trip, None)
        self.assertIn("20 Copper Bar (mail from Ann), 5 Copper Bar (mail from Bob), 35 Copper Bar (from the mail)", text)

    def test_the_shopping_list_charges_nothing_for_mailed_items(self):
        p, gd = self.rank_plan()
        st = toy.stock(shared=p.shared)
        lines, _ = render_shopping(p, gd, toy.market({S: [(10, 1000)]}), st)
        row = next(l for l in lines if l.startswith("| Copper Bar"))
        self.assertIn("| Copper Bar | 35 | AH |", row)  # 60 needed, 25 mailed

    def test_mailbox_trips_name_who_mails_what(self):
        p, gd = self.rank_plan()
        st = dataclasses.replace(toy.stock(shared=p.shared), bag_slots=60)
        lines, _ = render_shopping(p, gd, toy.market({S: [(10, 1000)]}), st)
        trip = next(l for l in lines if l.startswith("- 📬"))
        self.assertIn("Mailed by your other characters: 20 Copper Bar (mail from Ann), "
                      "5 Copper Bar (mail from Bob).", trip)
        self.assertIn("From the mail: 35 Copper Bar.", trip)

    def test_planner_and_shopping_agree(self):
        st = toy.stock(shared={"Ann": {S: 10}, "Bob": {S: 4}})
        gd = toy.gamedata(recipes())
        p = run(st)
        lines, _ = render_shopping(p, gd, toy.market(BARS), dataclasses.replace(st, bag_slots=200))
        trip = next(l for l in lines if l.startswith("- 📬"))
        self.assertIn("10 Copper Bar (mail from Ann), 4 Copper Bar (mail from Bob)", trip)
        self.assertEqual(p.used_mail, {S: [("Ann", 10), ("Bob", 4)]})

    def test_mail_text_orders_by_item_then_character(self):
        names = {S: "Copper Bar", T: "Iron Bar"}
        used = {T: [("Ann", 1)], S: [("Bob", 2), ("Cyd", 3)]}
        self.assertEqual(shared.mail_text(used, names.get),
                         "2 Copper Bar (mail from Bob), 3 Copper Bar (mail from Cyd), 1 Iron Bar (mail from Ann)")


if __name__ == "__main__":
    unittest.main()
