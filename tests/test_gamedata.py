import tomllib
import unittest
from pathlib import Path

from yap_forever import gamedata
from yap_forever import settings
from yap_forever.config import STATIC_DIR

FIX = Path(__file__).parent / "fixtures" / "gamedata"
REAL = settings.paths(settings.home({})).gamedata  # the player's real cache, not the test home


class GameDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gd = gamedata.load_gamedata(FIX)

    def test_parse_recipe_reagents_output(self):
        r = self.gd.recipes[2661]
        self.assertEqual(r.name, "Copper Chain Belt")
        self.assertEqual(r.skill_line, 164)
        self.assertEqual(r.reagents, {2840: 6})
        self.assertEqual(r.output, (2851, 1))
        self.assertEqual(r.thresholds, (1, 70, 90, 110))

    def test_enchant_without_item_output(self):
        self.assertIsNone(self.gd.recipes[7418].output)

    def test_required_skill_overrides_placeholder(self):
        # Orange placeholder 1; the trainer asks 30. TrainerInferred is Classic's
        # pre-Forever value and must not win.
        r = self.gd.recipes[2661]
        self.assertEqual(r.required_skill, 30)
        self.assertEqual((r.source, r.fee), ("trainer", 90))

    def test_scroll_recipe(self):
        r = self.gd.recipes[9999]
        self.assertEqual((r.source, r.scroll_item, r.required_skill), ("scroll", 5555, 80))

    def test_starter_recipe(self):
        r = self.gd.recipes[2660]
        self.assertEqual((r.source, r.fee, r.required_skill), ("starter", 0, 1))

    def test_only_bs_and_ench_kept(self):
        self.assertNotIn(2149, self.gd.recipes)
        self.assertEqual({r.skill_line for r in self.gd.recipes.values()}, {164, 333})

    def test_load_only_planned_professions(self):
        gd = gamedata.load_gamedata(FIX, professions=(165,))
        self.assertIn(2149, gd.recipes)
        self.assertEqual({r.skill_line for r in gd.recipes.values()}, {165})

    def test_starters_for_any_profession(self):
        gd = gamedata.load_gamedata(FIX, professions=(165,))
        self.assertEqual(gd.recipes[2149].source, "starter")

    def test_item_stack_size(self):
        self.assertEqual(self.gd.items[2840].stack, 20)
        self.assertEqual(self.gd.items[2851].stack, 1)  # 0 in the data
        self.assertEqual(self.gd.items[2857].stack, 1)  # empty

    def test_professions_names_all_crafts(self):
        self.assertEqual(set(gamedata.PROFESSIONS), {164, 165, 171, 197, 202, 333})

    def test_tools_from_spelltotems(self):
        self.assertEqual(self.gd.recipes[7418].tools, [373])
        self.assertEqual(self.gd.recipes[2661].tools, [162])
        self.assertTrue(self.gd.satisfies(11145, 374))
        self.assertFalse(self.gd.satisfies(6218, 374))
        self.assertTrue(self.gd.satisfies(6339, 373))
        self.assertEqual(self.gd.tool_items[162], 5956)

    def test_item_info_fields(self):
        i = self.gd.items[2857]
        self.assertEqual((i.name, i.quality, i.item_level, i.class_id, i.sell_price),
                         ("Runed Copper Belt", 2, 18, 4, 200))

    def test_bonding_is_read_and_says_what_can_be_mailed(self):
        got = {i: self.gd.items[i].bonding for i in (2840, 2857, 2770, 5956, 6339, 11145)}
        self.assertEqual(got, {2840: 0, 2857: 2, 2770: 0, 5956: 3, 6339: 1, 11145: 4})  # an empty cell is 0
        self.assertEqual({i: self.gd.items[i].mailable for i in got},
                         {2840: True, 2857: True, 2770: True, 5956: True, 6339: False, 11145: False})

    def test_bonding_of_every_kind(self):
        kinds = {0: True, 1: False, 2: True, 3: True, 4: False, 5: False}  # 5 appears in the data, not mailable
        for bonding, mailable in kinds.items():
            with self.subTest(bonding=bonding):
                self.assertEqual(gamedata.ItemInfo(1, "x", 1, 1, 7, 0, 0, bonding=bonding).mailable, mailable)

    def test_unknown_bonding_is_not_mailable(self):
        self.assertFalse(gamedata.ItemInfo(1, "x", 1, 1, 7, 0, 0).mailable)

    def test_a_cache_without_the_bonding_column_leaves_it_unknown(self):
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            shutil.copytree(FIX, Path(d) / "gd")
            sparse = Path(d) / "gd" / "ItemSparse.csv"
            sparse.write_text("\n".join(r.rsplit(",", 1)[0] for r in sparse.read_text().splitlines()) + "\n")
            gd = gamedata.load_gamedata(Path(d) / "gd")
        self.assertIsNone(gd.items[2840].bonding)
        self.assertFalse(gd.items[2840].mailable)

    def test_quest_items_from_objectives(self):
        self.assertEqual(self.gd.quest_items, {2857, 3240})

    def test_trainer_ranks_and_vendor(self):
        self.assertEqual(self.gd.trainer_ranks[164][1], gamedata.Rank(225, 4500, 125, 20))
        self.assertEqual(self.gd.vendor_prices[6217], 124)

    def test_a_rank_with_level_0_gets_the_level_the_others_give(self):
        # the fixture's Tailoring Master rank says level 0, as the pinned data does; the other two say 35
        self.assertEqual(self.gd.trainer_ranks[197][2], gamedata.Rank(300, 50000, 200, 35))
        self.assertEqual(self.gd.trainer_ranks[197][:2], [gamedata.Rank(150, 450, 50, 10),
                                                          gamedata.Rank(225, 4500, 125, 20)])
        self.assertEqual(self.gd.trainer_ranks[164][2].level, 35)  # others are left as they were

    @unittest.skipUnless((REAL / "ItemSparse.csv").exists(), "real game data not downloaded")
    def test_ore_names_match_itemsparse(self):
        names = gamedata.item_names(REAL / "ItemSparse.csv")
        with open(STATIC_DIR / "ore.toml", "rb") as f:
            ore = tomllib.load(f)
        for section in ("ore", "bars"):
            for item_id, row in ore[section].items():
                self.assertEqual(names.get(int(item_id)), row[0], f"{section} {item_id}")


class RankLevelFillTests(unittest.TestCase):
    R = gamedata.Rank

    def fill(self, ranks):
        return gamedata.fill_rank_levels(ranks)

    def test_the_others_agree(self):
        got = self.fill({1: [self.R(300, 9, 200, 35)], 2: [self.R(300, 9, 200, 35)], 3: [self.R(300, 9, 200, 0)]})
        self.assertEqual(got[3], [self.R(300, 9, 200, 35)])

    def test_zeros_in_the_others_are_not_a_level(self):
        got = self.fill({1: [self.R(300, 9, 200, 35)], 2: [self.R(300, 9, 200, 0)], 3: [self.R(300, 9, 200, 0)]})
        self.assertEqual([r.level for r in got[2] + got[3]], [35, 35])

    def test_the_others_disagree_so_nothing_is_guessed(self):
        got = self.fill({1: [self.R(300, 9, 200, 35)], 2: [self.R(300, 9, 200, 30)], 3: [self.R(300, 9, 200, 0)]})
        self.assertEqual(got[3][0].level, 0)

    def test_nothing_to_copy(self):
        self.assertEqual(self.fill({3: [self.R(300, 9, 200, 0)]})[3][0].level, 0)
        self.assertEqual(self.fill({1: [self.R(225, 9, 125, 20)], 3: [self.R(300, 9, 200, 0)]})[3][0].level, 0)

    def test_only_the_same_cap_counts(self):
        got = self.fill({1: [self.R(225, 9, 125, 20), self.R(300, 9, 200, 35)],
                         3: [self.R(225, 9, 125, 0), self.R(300, 9, 200, 0)]})
        self.assertEqual([r.level for r in got[3]], [20, 35])

    def test_a_rank_with_a_level_is_never_changed(self):
        got = self.fill({1: [self.R(300, 9, 200, 35)], 3: [self.R(300, 9, 200, 40)]})
        self.assertEqual(got[3][0].level, 40)

    def test_the_input_is_not_changed(self):
        ranks = {1: [self.R(300, 9, 200, 35)], 3: [self.R(300, 9, 200, 0)]}
        self.fill(ranks)
        self.assertEqual(ranks[3][0].level, 0)


if __name__ == "__main__":
    unittest.main()
