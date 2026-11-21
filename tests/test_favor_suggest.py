"""#95: Merchant's Favor recipes to craft once ("You could also make"), apart from the route."""
import unittest

from tests import toy
from yap_forever import favor_suggest
from yap_forever.costmodel import Valuer
from yap_forever.favor import FavorData, no_favor
from yap_forever.favor_suggest import Suggestion, level_ok, lines, suggest
from yap_forever.gamedata import ENCH, ItemInfo

DUST, ODD, ROD = toy.DUST, toy.ODD, toy.ROD
STAFF, ORB, WAND = 9001, 9002, 9003  # made-up crafted items


def favor_recipe(spell, name, output=None, reagents=None):
    """A Merchant's Favor Enchanting recipe as the game data has it: a scroll item sold for Favor."""
    return toy.recipe(spell, name, ENCH, reagents if reagents is not None else {DUST: 2},
                      (output, 1) if output else None, source="scroll", scroll=toy.SCROLL)


class Case:
    """A character at Enchanting 100, level 30, 150 Favor, with 20s of group gold; Strange Dust at 5s on the AH.
    recipes: (spell, name, crafted item or None, Favor price, item level); every recipe needs skill 100."""

    def __init__(self, recipes=((1, "Staff of Ana", STAFF, 50, 30),), level=30, skill=100, favor=150, items=None,
                 listings=None, shared=None):
        self.gd = toy.gamedata([favor_recipe(s, n, out) for s, n, out, _f, _l in recipes])
        for _s, _n, out, _f, lvl in recipes:
            if out:
                self.gd.items[out] = ItemInfo(out, f"Item {out}", 2, 30, 2, 100, 400, bonding=2, required_level=lvl)
        self.favor = FavorData({s: f for s, _n, _o, f, _l in recipes}, {s: 100 for s, *_ in recipes}, [])
        self.stock = toy.stock(items or {}, favor=favor, level=level, skills={ENCH: skill}, shared=shared)
        self.market = toy.market(listings if listings is not None else {DUST: [(500, 100)]})
        self.shared = shared or {}

    def run(self, gold=2000, goals=(), limit=6):
        return suggest(self.gd, self.favor, self.stock, Valuer(self.market, self.gd, self.stock), gold, self.shared,
                       set(goals), limit=limit)

    def spells(self, **kw):
        return [s.spell for s in self.run(**kw)[0]]


class LevelWindowTests(unittest.TestCase):
    def test_level_window(self):
        self.assertEqual((favor_suggest.LEVEL_WINDOW, favor_suggest.LATE_WINDOW, favor_suggest.LATE_FROM), (5, 3, 46))
        for char, item, ok in ((40, 45, True), (39, 45, False), (46, 49, True), (46, 50, False), (48, 45, True),
                               (48, 44, False), (45, 50, True), (45, 51, False), (45, 40, True)):
            self.assertEqual(level_ok(char, item), ok, (char, item))

    def test_unknown_level_is_out(self):
        # C15: an item whose required level the data doesn't give is never in the window; a real 0 is a level
        self.assertFalse(level_ok(30, None))
        self.assertTrue(level_ok(4, 0))


class SuggestTests(unittest.TestCase):
    def test_suggested(self):
        shown, more = Case().run()
        self.assertEqual(shown, [Suggestion(1, "Staff of Ana", ENCH, 100, 30, 50, 1000, {}, {}, ("ah",))])
        self.assertEqual(more, 0)

    def test_skill_favor_gold_gates(self):
        self.assertEqual(Case(skill=99).spells(), [])  # the Favor skill is 100
        self.assertEqual(Case(favor=49).spells(), [])  # the recipe costs 50 Favor
        self.assertEqual(Case().spells(gold=999), [])  # 2 Strange Dust at 5s: 1c over the gold
        self.assertEqual(Case().spells(gold=1000), [1])
        banked = Case(items={DUST: 1})
        shown, _more = banked.run(gold=999)  # over the gold, but one Strange Dust is in the bank
        self.assertEqual([(s.spell, s.gold, s.from_bank) for s in shown], [(1, 500, {DUST: 1})])

    def test_group_mail_after_the_bank(self):
        case = Case(items={DUST: 1}, shared={"Bram Ironhide": {DUST: 3}})
        shown, _more = case.run(gold=0)
        self.assertEqual([(s.gold, s.from_bank, s.from_mail, s.bought) for s in shown],
                         [(0, {DUST: 1}, {DUST: [("Bram Ironhide", 1)]}, ())])

    def test_enchant_no_level_test(self):
        # an enchant crafts no item: no level test, only skill, Favor and materials; listed after the items
        case = Case(recipes=((1, "Enchant Ring - Shine", None, 10, None), (2, "Staff of Ana", STAFF, 50, 47)),
                    level=48)
        self.assertEqual(case.spells(), [2, 1])
        self.assertIsNone(case.run()[0][1].level)
        self.assertEqual(Case(recipes=((1, "Enchant Ring - Shine", None, 10, None),), level=1).spells(), [1])

    def test_unpriced_reagent(self):
        case = Case(listings={})  # no Strange Dust on the AH, and no vendor sells it
        self.assertEqual(case.spells(), [])
        self.assertEqual(Case(listings={}, items={DUST: 2}).spells(), [1])  # held: nothing to buy

    def test_vendor_reagent(self):
        case = Case()
        case.gd.recipes[1].reagents = {ROD: 2}  # the toy's vendor reagent, 124c each
        shown, _more = case.run()
        self.assertEqual([(s.gold, s.bought) for s in shown], [(248, ("vendor",))])

    def test_goal_not_suggested(self):
        self.assertEqual(Case().spells(goals={1}), [])

    def test_horde_no_section(self):
        case = Case()
        self.assertEqual(suggest(case.gd, no_favor(), case.stock, Valuer(case.market, case.gd, case.stock), 2000,
                                 {}, set()), ([], 0))
        self.assertEqual(lines([], 0, case.gd, 150), [])

    def test_order(self):
        # items nearest the character's level first, then by Favor; then the enchants by Favor
        recipes = ((1, "Far", STAFF, 10, 33), (2, "Near dear", ORB, 60, 30), (3, "Near cheap", WAND, 20, 30),
                   (4, "Enchant B", None, 40, None), (5, "Enchant A", None, 30, None))
        self.assertEqual(Case(recipes=recipes).spells(), [3, 2, 1, 5, 4])

    def test_limit_and_more(self):
        recipes = tuple((s, f"Enchant {s}", None, s, None) for s in range(1, 9))
        shown, more = Case(recipes=recipes).run(gold=100000)
        self.assertEqual(([s.spell for s in shown], more), ([1, 2, 3, 4, 5, 6], 2))
        self.assertEqual(favor_suggest.LIMIT, 6)
        text = lines(shown, more, Case(recipes=recipes).gd, 150)
        self.assertEqual(text[-2:], ["and 2 more.", ""])
        self.assertEqual(Case(recipes=recipes).run(gold=100000, limit=8)[1], 0)

    def test_not_a_favor_recipe(self):
        case = Case()
        case.gd.recipes[2] = toy.recipe(2, "Trainer staff", ENCH, {DUST: 1}, (ORB, 1))  # listed, but a trainer's
        case.favor.recipes[2] = 10
        self.assertEqual(case.spells(), [1])


class LinesTests(unittest.TestCase):
    INTRO = ("Merchant's Favor recipes to craft once for yourself, if you don't have the item yet. They are not part "
             "of the route, its shopping list or its gold.")

    def test_lines(self):
        gd = Case(recipes=((1, "Staff of Ana", STAFF, 50, 30), (2, "Enchant Ring - Shine", None, 10, None))).gd
        rows = [Suggestion(1, "Staff of Ana", ENCH, 100, 30, 50, 61000, {DUST: 2}, {ODD: [("Bram Ironhide", 1)]},
                           ("ah",)),
                Suggestion(2, "Enchant Ring - Shine", ENCH, 100, None, 10, 248, {}, {}, ("vendor",)),
                Suggestion(2, "Enchant Ring - Shine", ENCH, 100, None, 10, 300, {DUST: 1, ODD: 2}, {},
                           ("ah", "vendor")),
                Suggestion(2, "Enchant Ring - Shine", ENCH, 100, None, 10, 0, {DUST: 1}, {ODD: [("Bram Ironhide", 1)]},
                           ())]
        self.assertEqual(lines(rows, 3, gd, 150), [
            "## You could also make", "", self.INTRO, "",
            "- **Staff of Ana** (Enchanting 100, for level 30): 50 of your 150 Favor; materials about 6.1g on the AH, "
            "2 Strange Dust from your bank, 1 Odd Thing (mail from Bram Ironhide).",
            "- **Enchant Ring - Shine** (Enchanting 100): 10 of your 150 Favor; materials about 2s from a vendor.",
            "- **Enchant Ring - Shine** (Enchanting 100): 10 of your 150 Favor; materials about 3s on the AH and from a "
            "vendor, 2 Odd Thing and 1 Strange Dust from your bank.",
            "- **Enchant Ring - Shine** (Enchanting 100): 10 of your 150 Favor; materials: 1 Strange Dust from your "
            "bank, 1 Odd Thing (mail from Bram Ironhide).",
            "", "and 3 more.", ""])  # a paragraph of its own, not part of the last row

    def test_report_heading(self):
        gd = Case().gd
        rows = [Suggestion(1, "Staff of Ana", ENCH, 100, 30, 50, 1000, {}, {}, ("ah",))]
        self.assertEqual(lines(rows, 0, gd, 150, heading="**You could also make**")[:2],
                         ["**You could also make**", ""])

    def test_levels_known(self):
        case = Case()
        self.assertTrue(favor_suggest.levels_known(case.gd))
        case.gd.items[STAFF].required_level = None
        self.assertFalse(favor_suggest.levels_known(case.gd))


if __name__ == "__main__":
    unittest.main()
