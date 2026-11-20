import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from yap_forever import plan as plan_mod
from yap_forever import settings
from yap_forever.config import Goal
from yap_forever.favor import load_favor, no_favor

NEUTRAL_IDS = {int(x) for x in
               (Path(__file__).parent / "fixtures" / "favor_neutral_ids.txt").read_text(encoding="utf-8").split()}


class FavorCatalogueTests(unittest.TestCase):
    def test_neutral_matches_owner_file(self):
        self.assertEqual(set(load_favor("Neutral").recipes), NEUTRAL_IDS)

    def test_friendly_adds_23(self):
        self.assertEqual(len(load_favor("Friendly").recipes), len(NEUTRAL_IDS) + 23)

    def test_honored_adds_all_29(self):
        self.assertEqual(len(load_favor("Honored").recipes), len(NEUTRAL_IDS) + 29)

    def test_turnins_do_not_depend_on_standing(self):
        self.assertEqual(load_favor("Neutral").turnins, load_favor("Exalted").turnins)
        self.assertTrue(load_favor("Neutral").turnins)

    def test_unknown_standing_raises(self):
        with self.assertRaises(ValueError):
            load_favor("Best friends")

    def test_no_favor_is_empty(self):
        none = no_favor()
        self.assertEqual((none.recipes, none.skills, none.turnins), ({}, {}, []))


NOTE = "Merchant's Favor recipes for Horde aren't in the planner yet."


class FactionTests(unittest.TestCase):
    """write_reports on the fixture game data: the Favor list is Alliance only."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.paths = settings.paths(Path(self._tmp.name) / "home")
        shutil.copytree(Path(__file__).parent / "fixtures" / "gamedata", self.paths.gamedata)
        self.paths.cache.mkdir(parents=True, exist_ok=True)
        self.paths.prices.write_text(
            '{"snapshot_time": "t", "listings": {"2835": [[20, 500]], "2840": [[10, 500]]}}', encoding="utf-8")
        self.stock = self.paths.character("Ana Brightforge") / "stock.toml"
        self.stock.parent.mkdir(parents=True)
        self.stock.write_text("level = 20\nfavor = 500\n[items]\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def plan(self, faction):
        """(favor the planner used, the reports' texts)"""
        with mock.patch.object(plan_mod, "candidates", wraps=plan_mod.candidates) as c:
            _table, files = plan_mod.write_reports(self.paths, self.stock, "Honored", {164: Goal(skill=60)},
                                                   faction=faction)
        return c.call_args.args[0].favor, {k: v.read_text(encoding="utf-8") for k, v in files.items()}

    def test_horde_gets_no_favor_recipes(self):  # RF2
        favor, texts = self.plan("horde")
        self.assertEqual((favor.recipes, favor.turnins), ({}, []))
        for key, text in texts.items():
            self.assertIn(NOTE, text, key)
            self.assertNotIn("Crate turn-ins", text, key)
            self.assertNotIn("(Favor)", text, key)
        self.assertIn("Spent 0 of 500 Favor.", texts["plan-gold"])

    def test_alliance_unchanged(self):
        want = load_favor("Honored")
        for faction in ("alliance", ""):
            with self.subTest(faction=faction):
                favor, texts = self.plan(faction)
                self.assertEqual((favor.recipes, favor.turnins), (want.recipes, want.turnins))
                self.assertTrue(favor.recipes)
                for key, text in texts.items():
                    self.assertNotIn(NOTE, text, key)
                self.assertIn("Crate turn-ins", texts["plan-gold"])


if __name__ == "__main__":
    unittest.main()
