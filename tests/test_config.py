import os
import tempfile
import unittest
from pathlib import Path

from yap_forever import config, settings

STOCK = """
level = 37
favor = 245
cash_gold = 12
mining = 171
short_farm_ore = 200

[items]
2840 = 195
2841 = 238

[marker]
item_id = 0
buyout_copper = 0
"""


def write(dirpath, name, text, mode=0o600):
    p = Path(dirpath) / name
    p.write_text(text)
    os.chmod(p, mode)
    return p


class StockTests(unittest.TestCase):
    def test_load_stock_values(self):
        with tempfile.TemporaryDirectory() as d:
            s = config.load_stock(write(d, "stock.toml", STOCK, 0o644))
        self.assertEqual(s.favor, 245)
        self.assertEqual(s.cash, 120000)
        self.assertEqual(s.items[2841], 238)
        self.assertEqual(s.level, 37)
        self.assertEqual(s.mining, 171)
        self.assertEqual(s.short_farm_ore, 200)
        self.assertIsNone(s.marker)
        self.assertEqual(s.target, 225)
        self.assertEqual(s.mining_goal, 171)

    def test_target_and_mining_goal(self):
        text = "target = 300\nmining_goal = 250\n" + STOCK
        with tempfile.TemporaryDirectory() as d:
            s = config.load_stock(write(d, "stock.toml", text, 0o644))
        self.assertEqual((s.target, s.mining_goal), (300, 250))
        self.assertIsNone(s.quest_item_sales)
        s2 = config.load_stock(write(tempfile.mkdtemp(), "stock.toml", "quest_item_sales = 20\n" + STOCK, 0o644))
        self.assertEqual(s2.quest_item_sales, 20)

    def test_marker_set(self):
        text = STOCK.replace("item_id = 0", "item_id = 2589").replace(
            "buyout_copper = 0", "buyout_copper = 71313")
        with tempfile.TemporaryDirectory() as d:
            s = config.load_stock(write(d, "stock.toml", text, 0o644))
        self.assertEqual(s.marker, (2589, 71313))


class SkillsTests(unittest.TestCase):
    def test_load_stock_skills_by_name(self):
        with tempfile.TemporaryDirectory() as d:
            s = config.load_stock(write(d, "stock.toml", STOCK + "\n[skills]\nblacksmithing = 184\nenchanting = 200\n"))
        self.assertEqual(s.skills, {164: 184, 333: 200})

    def test_unknown_profession_name_raises(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                config.load_stock(write(d, "stock.toml", STOCK + "\n[skills]\nbasketweaving = 10\n"))


class GoalsTests(unittest.TestCase):
    def test_parse_prof_arg_skill_and_recipe(self):
        self.assertEqual(config.parse_prof_arg("Tailoring:225"), (197, config.Goal(skill=225)))
        self.assertEqual(config.parse_prof_arg("enchanting:Enchant Bracer - Minor Health"),
                         (333, config.Goal(recipe="Enchant Bracer - Minor Health")))
        # above 300 a number is a recipe's spell ID, not a skill
        self.assertEqual(config.parse_prof_arg("blacksmithing:2662"), (164, config.Goal(recipe="2662")))

    def test_parse_goal_number_is_skill(self):
        self.assertEqual(config.parse_goal(150), config.Goal(skill=150))
        self.assertEqual(config.parse_goal("300"), config.Goal(skill=300))
        self.assertEqual(config.parse_goal("Veteran's Chain Belt"), config.Goal(recipe="Veteran's Chain Belt"))

    def test_parse_prof_arg_errors(self):
        for bad in ("tailoring", "cooking:150", "tailoring:0", "tailoring:-5", "tailoring:"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                config.parse_prof_arg(bad)

    def test_stock_goals_and_bag_slots(self):
        with tempfile.TemporaryDirectory() as d:
            s = config.load_stock(write(d, "stock.toml", "bag_slots = 40\n" + STOCK
                                        + '\n[goals]\ntailoring = 225\nenchanting = "Enchant X"\n'))
            plain = config.load_stock(write(d, "plain.toml", STOCK))
        self.assertEqual(s.goals, {197: config.Goal(skill=225), 333: config.Goal(recipe="Enchant X")})
        self.assertEqual(s.bag_slots, 40)
        self.assertEqual((plain.goals, plain.bag_slots), ({}, None))

    def test_stock_reagent_slots(self):
        with tempfile.TemporaryDirectory() as d:
            s = config.load_stock(write(d, "stock.toml", "reagent_slots = 6\n" + STOCK))
            plain = config.load_stock(write(d, "plain.toml", STOCK))
        self.assertEqual(s.reagent_slots, 6)
        self.assertEqual(plain.reagent_slots, 0)

    def test_stock_negative_slots_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            for key in ("reagent_slots", "bag_slots"):
                with self.subTest(key=key), self.assertRaisesRegex(ValueError, key):
                    config.load_stock(write(d, "stock.toml", f"{key} = -1\n" + STOCK))
            self.assertEqual(config.load_stock(write(d, "zero.toml", "bag_slots = 0\nreagent_slots = 0\n" + STOCK)).bag_slots, 0)


class CredentialTests(unittest.TestCase):
    def test_credentials_repr_masks(self):
        c = config.Credentials("myclientid", "s3cr3tvalue", "eu")
        self.assertNotIn("s3cr3tvalue", repr(c))
        self.assertNotIn("myclientid", repr(c))
        self.assertNotIn("s3cr3tvalue", str(c))

    @unittest.skipIf(os.name == "nt", "file modes are POSIX only")
    def test_a_bad_value_names_the_file_and_the_key(self):
        cases = [("[items]\n2840 = \"many\"\n", "items.2840"),
                 ("[items]\nbars = 3\n", "items.bars"),
                 ("level = \"forty\"\n", "level"),
                 ("cash_gold = \"lots\"\n", "cash_gold"),
                 ("favor = 1.5\n", "favor"),
                 ("bag_slots = \"x\"\n", "bag_slots"),
                 ("[skills]\nblacksmithing = \"high\"\n", "skills.blacksmithing"),
                 ("items = 3\n", "items"),
                 ("[goals]\nbasketweaving = 10\n", "goals.basketweaving")]
        with tempfile.TemporaryDirectory() as d:
            for text, key in cases:
                path = write(d, "stock.toml", text)
                with self.subTest(key=key), self.assertRaises(ValueError) as cm:
                    config.load_stock(path)
                msg = str(cm.exception)
                self.assertIn(str(path), msg)
                self.assertIn(key, msg)
                self.assertNotIn("invalid literal", msg)

    def test_whole_numbers_written_other_ways_still_load(self):
        with tempfile.TemporaryDirectory() as d:
            s = config.load_stock(write(d, "stock.toml", 'level = 47.0\n[items]\n2840 = "12"\n'))
        self.assertEqual((s.level, s.items), (47, {2840: 12}))

    def test_a_toml_syntax_error_names_the_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = write(d, "stock.toml", "level = \n")
            with self.assertRaises(ValueError) as cm:
                config.load_stock(path)
        self.assertIn(str(path), str(cm.exception))

    def test_credentials_refuses_open_permissions(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "config.json",
                      '{"client_id": "a", "client_secret": "b", "region": "eu"}', 0o644)
            with self.assertRaises(PermissionError):
                settings.load_credentials(p)

    def test_credentials_empty_values(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "config.json",
                      '{"client_id": "", "client_secret": "", "region": "eu"}')
            with self.assertRaises(ValueError) as cm:
                settings.load_credentials(p)
        self.assertIn("fill in client_id and client_secret in config.json", str(cm.exception))

    def test_credentials_load(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "config.json",
                      '{"client_id": "a", "client_secret": "b", "region": "eu"}')
            c = settings.load_credentials(p)
        self.assertEqual((c.client_id, c.client_secret, c.region), ("a", "b", "eu"))


if __name__ == "__main__":
    unittest.main()
