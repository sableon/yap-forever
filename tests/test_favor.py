import unittest
from pathlib import Path

from yap_forever.favor import load_favor

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


if __name__ == "__main__":
    unittest.main()
