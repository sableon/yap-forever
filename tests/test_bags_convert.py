import tempfile
import tomllib
import unittest
from pathlib import Path

from yap_forever import migrate
from yap_forever.config import load_stock

BAGS = """profs = ["alchemy", "engineering"]
bag_slots = 30
reagent_slots = 4

[items]
2589 = 12
"2592" = 7
"""


class BagsToStockTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.bags = self.dir / "bags.toml"
        self.stock = self.dir / "stock.toml"
        self.bags.write_text(BAGS, encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def convert(self):
        return migrate.bags_to_stock(self.bags, self.stock)

    def text(self):
        return self.stock.read_text(encoding="utf-8")

    def test_is_bags_file_means_a_profs_key(self):
        self.assertTrue(migrate.is_bags_file(self.bags))
        self.stock.write_text("level = 5\n[items]\n", encoding="utf-8")
        self.assertFalse(migrate.is_bags_file(self.stock))

    def test_the_stock_file_loads_and_carries_bags_and_items(self):
        self.assertTrue(self.convert())
        s = load_stock(self.stock)
        self.assertEqual((s.bag_slots, s.reagent_slots), (30, 4))
        self.assertEqual(s.items, {2589: 12, 2592: 7})
        self.assertEqual((s.goals, s.skills), ({}, {}))

    def test_without_reagent_slots_none_is_written(self):
        self.bags.write_text('profs = ["tailoring"]\nbag_slots = 20\n', encoding="utf-8")
        self.convert()
        self.assertNotIn("reagent_slots", tomllib.loads(self.text()))
        s = load_stock(self.stock)
        self.assertEqual((s.bag_slots, s.reagent_slots, s.items), (20, 0, {}))

    def test_without_bag_slots_none_is_written(self):
        self.bags.write_text('profs = ["tailoring"]\n', encoding="utf-8")
        self.convert()
        self.assertIsNone(load_stock(self.stock).bag_slots)

    def test_professions_become_commented_lines(self):
        self.convert()
        lines = self.text().splitlines()
        goals = lines.index("[goals]")
        skills = lines.index("[skills]")
        self.assertIn("# alchemy = <goal>", lines[goals:])
        self.assertIn("# engineering = <goal>", lines[goals:])
        self.assertIn("# alchemy = <current skill>", lines[skills:])
        self.assertIn("# engineering = <current skill>", lines[skills:])
        self.assertNotIn("alchemy = <goal>", [l for l in lines if not l.startswith("#")])

    def test_numeric_professions_are_named(self):
        self.bags.write_text("profs = [171, 202]\n", encoding="utf-8")
        self.convert()
        self.assertIn("# alchemy = <goal>", self.text())
        self.assertIn("# engineering = <current skill>", self.text())

    def test_a_profession_the_planner_does_not_know_is_kept_as_written(self):
        self.bags.write_text('profs = ["Cooking"]\n', encoding="utf-8")
        self.convert()
        self.assertIn("# cooking = <goal>", self.text())

    def test_the_top_comment_names_the_source_and_what_to_check(self):
        self.convert()
        top = self.text().splitlines()[0]
        self.assertTrue(top.startswith("#"), top)
        for word in ("bags.toml", "level", "cash_gold", "[skills]", "[goals]"):
            self.assertIn(word, top)

    def test_items_with_the_same_id_twice_are_refused_naming_the_file(self):
        self.bags.write_text('profs = ["alchemy"]\n[items]\n"2589" = 1\n"02589" = 2\n', encoding="utf-8")
        with self.assertRaises(ValueError) as cm:
            self.convert()
        self.assertIn(str(self.bags), str(cm.exception))
        self.assertFalse(self.stock.exists())

    def test_a_count_that_is_not_a_whole_number_is_refused_naming_the_file(self):
        for bad in ('2589 = 1.5', '2589 = "3"', '2589 = true'):
            self.bags.write_text(f'profs = ["alchemy"]\n[items]\n{bad}\n', encoding="utf-8")
            with self.assertRaises(ValueError, msg=bad) as cm:
                self.convert()
            self.assertIn(str(self.bags), str(cm.exception), bad)
            self.assertFalse(self.stock.exists(), bad)

    def test_never_overwrites_an_existing_stock_file(self):
        self.stock.write_text("level = 9\n", encoding="utf-8")
        self.assertFalse(self.convert())
        self.assertEqual(self.text(), "level = 9\n")

    def test_never_deletes_the_bags_file(self):
        self.convert()
        self.assertEqual(self.bags.read_text(encoding="utf-8"), BAGS)

    def test_a_damaged_bags_file_writes_nothing(self):
        for bad in ("profs = [", 'profs = ["alchemy"]\n[items]\nabc = 1\n',
                    'profs = ["alchemy"]\nbag_slots = -1\n', 'profs = "alchemy"\n'):
            self.bags.write_text(bad, encoding="utf-8")
            with self.assertRaises(ValueError, msg=bad):
                self.convert()
            self.assertFalse(self.stock.exists(), bad)


if __name__ == "__main__":
    unittest.main()
