"""Characters on one ruleset and faction share gold and mail each other items (shared.py)."""
import dataclasses
import tempfile
import unittest
from pathlib import Path

from tests import toy
from yap_forever import profile, settings, shared, shopping
from yap_forever.costmodel import Pools, Valuer
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

    def test_a_tool_another_character_holds_is_not_counted(self):
        rs = [toy.recipe(1, "BS tooled", BS, {S: 1}, (toy.STONE, 1), tools=[162])]
        market = {**BARS, toy.HAMMER: [(500, 1)]}
        alone = run(toy.stock(), market, rs=rs)
        with_mate = run(toy.stock(shared={"Ann": {toy.HAMMER: 1}}), market, rs=rs)
        self.assertEqual(with_mate.used_mail.get(toy.HAMMER), None)  # nothing is said to be mailed
        self.assertEqual(with_mate.cash_total, alone.cash_total)  # the hammer is bought as before


class OwnItemsFirstTests(unittest.TestCase):
    """Your own ore, smelted, comes before bars another character mails; mining comes after them."""
    IRON_ORE = 2772

    def take(self, qty, own, mate, mining=125):
        gd = toy.gamedata([])
        st = toy.stock(own, mining=mining, shared={"Ann": mate})
        pools = Pools.from_stock(st)
        cost = Valuer(toy.market(), gd, st).take(T, qty, pools, skills={})
        return cost, pools

    def test_own_ore_is_smelted_before_the_mates_bars(self):
        cost, pools = self.take(5, {self.IRON_ORE: 3}, {T: 10})
        self.assertEqual(pools.stock[self.IRON_ORE], 0)  # all three ore smelted
        self.assertEqual(pools.mail[T], 8)  # the other two bars come from Ann
        self.assertEqual(pools.farmed, {})

    def test_the_mates_bars_come_before_mining(self):
        _cost, pools = self.take(5, {}, {T: 3})
        self.assertEqual(pools.mail.get(T, 0), 0)
        self.assertAlmostEqual(pools.farmed[T], 2)  # the rest is mined

    def test_own_bars_come_before_everything(self):
        _cost, pools = self.take(5, {T: 5, self.IRON_ORE: 9}, {T: 10})
        self.assertEqual((pools.stock[T], pools.stock[self.IRON_ORE], pools.mail[T]), (0, 9, 10))

    def test_the_mates_ore_is_not_smelted(self):
        _cost, pools = self.take(2, {}, {self.IRON_ORE: 9})
        self.assertEqual(pools.mail[self.IRON_ORE], 9)
        self.assertAlmostEqual(pools.farmed[T], 2)


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

    def test_a_source_that_ran_dry_is_not_named_again(self):
        from yap_forever.planner import Plan, Step
        # Ann's 20 and Bob's 5 bars go to the first trip; the second needs more and must not name "0" from them
        p = Plan(steps=[Step(BS, 1, 11, 1, "BS one", 10, 0, 0, {S: 30}, from_mail={S: 25}, buffered=10),
                        Step(BS, 11, 21, 2, "BS two", 10, 0, 0, {T: 30}, buffered=10)],
                 final_skill={BS: 21}, shared={"Bob": {S: 5}, "Ann": {S: 20}})
        gd = toy.gamedata([toy.recipe(1, "BS one", BS, {S: 3}), toy.recipe(2, "BS two", BS, {S: 3, T: 3})])
        gd.items[S].stack = gd.items[T].stack = 20
        st = dataclasses.replace(toy.stock(shared=p.shared), bag_slots=14)  # 4 free slots: one row a trip
        lines, trips = render_shopping(p, gd, toy.market({S: [(10, 1000)], T: [(10, 1000)]}), st)
        text = "\n".join(l for l in lines if l.startswith("- 📬"))
        self.assertEqual(trips, 2)
        self.assertNotIn(" 0 Copper Bar", text)
        self.assertEqual(text.count("(mail from Ann)"), 1)
        self.assertEqual(text.count("(mail from Bob)"), 1)

    def test_mail_text_orders_by_item_then_character(self):
        names = {S: "Copper Bar", T: "Iron Bar"}
        used = {T: [("Ann", 1)], S: [("Bob", 2), ("Cyd", 3)]}
        self.assertEqual(shared.mail_text(used, names.get),
                         "2 Copper Bar (mail from Bob), 3 Copper Bar (mail from Cyd), 1 Iron Bar (mail from Ann)")


PROFILE = """region = "eu"
ruleset = 2
faction = "alliance"
[characters.Me]
[characters.Ann]
[characters.Bob]
faction = "horde"
[characters.Cyd]
ruleset = 3
[characters.Dee]
"""


class GroupTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.paths = settings.paths(Path(self._tmp.name) / "home")
        self.paths.root.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def prof(self, extra=""):
        self.paths.profile.write_text(PROFILE + extra, encoding="utf-8")
        return profile.load_profile(self.paths.profile)

    def stock(self, name, text):
        f = self.paths.character(name) / "stock.toml"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")

    def test_only_the_same_ruleset_and_faction_contribute(self):
        for name in ("Me", "Ann", "Bob", "Cyd"):
            self.stock(name, f"cash_gold = 10\n[items]\n{S} = 5\n")
        g = shared.load_group(self.paths, self.prof(), "Me")
        self.assertEqual(sorted(g.others), ["Ann"])  # Bob is a horde, Cyd plays another ruleset
        self.assertEqual((g.ruleset, g.faction, g.label), (2, "alliance", "2/alliance"))

    def test_a_character_without_a_stock_file_contributes_nothing(self):
        self.stock("Me", "[items]\n")
        self.stock("Ann", f"[items]\n{S} = 5\n")
        g = shared.load_group(self.paths, self.prof(), "Me")  # Dee has no file
        self.assertEqual(sorted(g.others), ["Ann"])

    def test_the_character_itself_is_not_its_own_source(self):
        self.stock("Me", f"[items]\n{S} = 5\n")
        self.assertEqual(shared.load_group(self.paths, self.prof(), "Me").others, {})

    def test_a_damaged_stock_file_of_another_character_is_named(self):
        self.stock("Me", "[items]\n")
        self.stock("Ann", "[items\n")
        with self.assertRaises(ValueError) as cm:
            shared.load_group(self.paths, self.prof(), "Me")
        self.assertIn(str(self.paths.character("Ann") / "stock.toml"), str(cm.exception))

    def test_a_character_on_another_ruleset_has_its_own_group(self):
        for name in ("Me", "Ann", "Cyd"):
            self.stock(name, "[items]\n")
        prof = self.prof('[characters.Eve]\nruleset = 3\n')
        self.stock("Eve", "[items]\n")
        self.assertEqual(sorted(shared.load_group(self.paths, prof, "Cyd").others), ["Eve"])

    def test_budget_from_the_gold_table(self):
        self.stock("Me", "cash_gold = 12\n[items]\n")
        self.stock("Ann", "cash_gold = 30\n[items]\n")
        prof = self.prof('[gold]\n"2/alliance" = 45\n')
        g = shared.load_group(self.paths, prof, "Me")
        self.assertEqual(g.budget(self.load("Me")), shared.Budget(450000, "2/alliance", False))

    def test_budget_falls_back_to_the_sum_of_cash_gold(self):
        self.stock("Me", "cash_gold = 12\n[items]\n")
        self.stock("Ann", "cash_gold = 30.5\n[items]\n")
        self.stock("Bob", "cash_gold = 1000\n[items]\n")  # another faction: not counted
        g = shared.load_group(self.paths, self.prof(), "Me")
        self.assertEqual(g.budget(self.load("Me")), shared.Budget(425000, "2/alliance", True))

    def test_a_single_stock_file_is_not_called_a_sum(self):
        self.stock("Me", "cash_gold = 12\n[items]\n")
        g = shared.load_group(self.paths, self.prof(), "Me")
        self.assertEqual(g.budget(self.load("Me")), shared.Budget(120000, "2/alliance", False))

    def test_a_zero_gold_entry_is_a_budget_of_zero_not_a_missing_one(self):
        self.stock("Me", "cash_gold = 12\n[items]\n")
        g = shared.load_group(self.paths, self.prof('[gold]\n"2/alliance" = 0\n'), "Me")
        self.assertEqual(g.budget(self.load("Me")).copper, 0)

    def test_a_gold_entry_for_another_group_is_ignored(self):
        self.stock("Me", "cash_gold = 12\n[items]\n")
        g = shared.load_group(self.paths, self.prof('[gold]\n"3/alliance" = 45\n'), "Me")
        self.assertEqual(g.budget(self.load("Me")).copper, 120000)

    def load(self, name):
        from yap_forever.config import load_stock
        return load_stock(self.paths.character(name) / "stock.toml")

    def test_cash_gold_stays_readable_in_a_stock_file(self):
        self.stock("Me", "cash_gold = 1.5\n[items]\n")
        self.assertEqual(self.load("Me").cash, 15000)


class BudgetLineTests(unittest.TestCase):
    def render(self, budget, items=None, shared_items=None):
        from yap_forever.planner import Plan
        from yap_forever.report import render, verdict
        gd = toy.gamedata(recipes())
        st = toy.stock(items, shared=shared_items)
        p = plan(gd, Valuer(toy.market(BARS), gd, st), st, toy.NO_FAVOR, caps={BS: 30})
        text = render(p, verdict(p, st), toy.market(BARS), gd, st, toy.NO_FAVOR, budget=budget)
        return p, text

    def cash_line(self, text):
        return next(l for l in text.splitlines() if l.startswith("- **Cash needed:**"))

    def test_within_the_shared_gold(self):
        p, text = self.render(shared.Budget(10**9, "2/alliance"))
        self.assertIn("within the 100000g 0s 0c shared by your 2/alliance characters", self.cash_line(text))
        self.assertNotIn("your own", text)

    def test_over_the_shared_gold(self):
        p, _ = self.render(shared.Budget(0, "2/alliance"))
        _p, text = self.render(shared.Budget(p.cash_total - 5000, "3/horde"))
        line = self.cash_line(text)
        self.assertIn("over the", line)
        self.assertIn("shared by your 3/horde characters by 50s 0c", line)

    def test_exactly_the_gold_is_within(self):
        p, _ = self.render(None)
        _p, text = self.render(shared.Budget(int(p.cash_total), "2/alliance"))
        self.assertIn("within the", self.cash_line(text))

    def test_without_a_group_the_stock_budget_reads_as_before(self):
        _p, text = self.render(None)
        self.assertIn("within your 12g 0s 0c budget", self.cash_line(text))

    def test_a_sum_is_said_once_in_the_notes(self):
        _p, text = self.render(shared.Budget(10**9, "2/alliance", True))
        self.assertEqual(text.count("sum of `cash_gold`"), 1)
        self.assertIn("[gold]", text)
        _p, text = self.render(shared.Budget(10**9, "2/alliance", False))
        self.assertNotIn("sum of `cash_gold`", text)

    def test_shared_items_are_said_once_when_used(self):
        p, text = self.render(None, shared_items={"Ann": {S: 10}})
        self.assertEqual(text.count(shared.SHARED_NOTE), 1)
        self.assertIn("From your other characters, by mail: 10 Copper Bar (mail from Ann).", text)
        _p, text = self.render(None)
        self.assertNotIn(shared.SHARED_NOTE, text)
        self.assertNotIn("by mail", text)
        _p, text = self.render(None, shared_items={"Ann": {T: 10}})  # present but not needed
        self.assertNotIn(shared.SHARED_NOTE, text)


class GuideTests(unittest.TestCase):
    def guide(self, shared_items):
        from yap_forever.guide import render_guide
        gd = toy.gamedata(recipes())
        st = dataclasses.replace(toy.stock(shared=shared_items), bag_slots=200)
        p = plan(gd, Valuer(toy.market(BARS), gd, st), st, toy.NO_FAVOR, caps={BS: 30})
        return render_guide(p, gd, toy.market(BARS), st, caps={BS: 30})

    def test_the_guide_names_the_sources_and_the_caveat_once(self):
        text = self.guide({"Ann": {S: 10}})
        self.assertIn("Mailed by your other characters: 10 Copper Bar (mail from Ann)", text)
        self.assertIn("- From your other characters, by mail: 10 Copper Bar (mail from Ann).", text)
        self.assertEqual(text.count(shared.SHARED_NOTE), 1)

    def test_the_keep_table_counts_mailed_items_as_not_to_get(self):
        text = self.guide({"Ann": {S: 10}})
        self.assertIn("| Item | Keep | In bank | By mail | Still to get | Buy later |", text)
        self.assertNotIn("By mail", self.guide({}))

    def test_the_notes_count_what_the_trips_count(self):
        import re

        from yap_forever.guide import render_guide
        rs = [toy.recipe(1, "BS yellow", BS, {S: 1}, (toy.STONE, 1), t=(1, 1, 300, 600))]  # buffered 15%
        gd = toy.gamedata(rs)
        st = dataclasses.replace(toy.stock(shared={"Ann": {S: 100}}), bag_slots=200)
        p = plan(gd, Valuer(toy.market(BARS), gd, st), st, toy.NO_FAVOR, caps={BS: 30})
        text = render_guide(p, gd, toy.market(BARS), st, caps={BS: 30})
        trip = int(re.search(r"(\d+) Copper Bar \(mail from Ann\)", next(
            l for l in text.splitlines() if l.startswith("- 📬"))).group(1))
        note = int(re.search(r"(\d+) Copper Bar \(mail from Ann\)", next(
            l for l in text.splitlines() if l.startswith("- From your other characters"))).group(1))
        self.assertEqual(note, trip)
        self.assertGreater(trip, p.used_mail[S][0][1])  # the buffer is on top of what the planner took

    def test_the_report_counts_what_the_trips_count(self):
        from yap_forever.report import render, verdict
        rs = [toy.recipe(1, "BS yellow", BS, {S: 1}, (toy.STONE, 1), t=(1, 1, 300, 600))]
        gd = toy.gamedata(rs)
        st = toy.stock(shared={"Ann": {S: 100}})
        p = plan(gd, Valuer(toy.market(BARS), gd, st), st, toy.NO_FAVOR, caps={BS: 30})
        text = render(p, verdict(p, st), toy.market(BARS), gd, st, toy.NO_FAVOR)
        self.assertNotIn(f"{p.used_mail[S][0][1]} Copper Bar (mail from Ann)", text)  # the buffered count instead
        self.assertIn(f"{shopping.mailed(p, gd, st)[S][0][1]} Copper Bar (mail from Ann)", text)

    def test_a_mailed_pattern_is_named_in_the_guide_notes(self):
        from yap_forever.guide import render_guide
        rs = recipes() + [toy.recipe(3, "Scroll free", BS, {}, (toy.STONE, 1), source="scroll", scroll=toy.SCROLL)]
        gd = toy.gamedata(rs)
        st = toy.stock(shared={"Ann": {toy.SCROLL: 1}})
        p = plan(gd, Valuer(toy.market(BARS), gd, st), st, toy.NO_FAVOR, caps={BS: 30})
        text = render_guide(p, gd, toy.market(BARS), st, caps={BS: 30})
        self.assertIn("- From your other characters, by mail: 1 Plans: Something (mail from Ann).", text)

    def test_without_other_characters_the_guide_is_unchanged(self):
        text = self.guide({})
        self.assertNotIn("other characters", text)
        self.assertNotIn(shared.SHARED_NOTE, text)


class PlanCommandTests(unittest.TestCase):
    """`plan` end to end on the fixture game data: Rough Stone is the reagent of the starter recipe."""
    STONE = 2835

    def setUp(self):
        import shutil

        from tests.test_cli import run
        self.run_cli = run
        self._tmp = tempfile.TemporaryDirectory()
        self.paths = settings.paths(Path(self._tmp.name) / "home")
        run(["init"], self.paths)
        gd = Path(__file__).parent / "fixtures" / "gamedata"
        shutil.copytree(gd, self.paths.gamedata)
        with open(self.paths.gamedata / "ItemSparse.csv", "a", encoding="utf-8") as f:
            f.write(f"{self.STONE},Rough Stone,1,1,1,1,0,20,0\n")
        self.paths.prices.write_text(f'{{"snapshot_time": "t", "listings": {{"{self.STONE}": [[20, 500]]}}}}',
                                     encoding="utf-8")
        self.paths.profile.write_text(
            self.paths.profile.read_text(encoding="utf-8")
            + '\n[characters."Testy Example"]\n[characters."Horde Person"]\nfaction = "horde"\n'
              '[characters."Other Rules"]\nruleset = 3\n', encoding="utf-8")
        self.write("Firstname Lastname", "level = 20\ncash_gold = 5\n[items]\n")

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, text):
        f = self.paths.character(name) / "stock.toml"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")

    def plan(self):
        code, out = self.run_cli(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"],
                                 self.paths)
        self.assertEqual(code, 0, out)
        return {"-".join(f.name.split("-")[-2:]): f.read_text(encoding="utf-8") for f in self.paths.reports.glob("*.md")}

    def test_a_group_mate_mails_its_stones(self):
        self.write("Testy Example", f"cash_gold = 7\nlevel = 20\n[items]\n{self.STONE} = 30\n")
        reports = self.plan()
        for name in ("guide-gold.md", "plan-gold.md"):
            self.assertIn("mail from Testy Example", reports[name], name)
        self.assertIn(shared.SHARED_NOTE, reports["plan-gold.md"])

    def test_other_factions_and_rulesets_and_missing_files_contribute_nothing(self):
        self.write("Horde Person", f"[items]\n{self.STONE} = 99\n")
        self.write("Other Rules", f"[items]\n{self.STONE} = 99\n")  # Testy Example has no stock file at all
        for text in self.plan().values():
            self.assertNotIn("mail from", text)
            self.assertNotIn(shared.SHARED_NOTE, text)

    def test_the_budget_is_the_groups_shared_gold(self):
        self.write("Testy Example", "cash_gold = 7\nlevel = 20\n[items]\n")
        self.write("Horde Person", "cash_gold = 900\n[items]\n")
        line = next(l for l in self.plan()["plan-gold.md"].splitlines() if l.startswith("- **Cash needed:**"))
        self.assertIn("within the 12g 0s 0c shared by your 2/alliance characters", line)  # 5 + 7, not the horde's
        text = self.paths.profile.read_text(encoding="utf-8")
        self.paths.profile.write_text(text + '[gold]\n"2/alliance" = 0.5\n', encoding="utf-8")
        reports = self.plan()
        line = next(l for l in reports["plan-gold.md"].splitlines() if l.startswith("- **Cash needed:**"))
        self.assertIn("shared by your 2/alliance characters", line)
        self.assertIn("50s 0c shared", line)
        self.assertNotIn("sum of `cash_gold`", reports["plan-gold.md"])

    def test_a_damaged_file_of_a_group_mate_names_it(self):
        self.write("Testy Example", "[items\n")
        code, out = self.run_cli(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"],
                                 self.paths)
        self.assertEqual(code, 1)
        self.assertIn(str(self.paths.character("Testy Example") / "stock.toml"), out)


if __name__ == "__main__":
    unittest.main()
