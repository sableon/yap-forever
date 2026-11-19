import json
import tempfile
import unittest
from pathlib import Path

from yap_forever import profile, settings
from yap_forever.migrate import migrate


class MigrateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        t = Path(self._tmp.name)
        self.user, self.data = t / "user", t / "data"
        (self.data / "gamedata").mkdir(parents=True)
        self.user.mkdir()
        (self.user / "stock.toml").write_text("level = 47\n[items]\n", encoding="utf-8")
        (self.user / "alt2-bags.toml").write_text("profs = [197]\nbag_slots = 30\n", encoding="utf-8")
        (self.data / "house.json").write_text('{"house": 4242, "found": "x"}', encoding="utf-8")
        (self.data / "prices.json").write_text('{"snapshot_time": "t", "listings": {}}', encoding="utf-8")
        (self.data / "gamedata" / "Recipes.lua").write_text("-- data", encoding="utf-8")
        (self.data / "config.json").write_text('{"client_id": "SECRET-ID"}', encoding="utf-8")
        self.dest = settings.paths(t / "home")

    def tearDown(self):
        self._tmp.cleanup()

    def run_migrate(self):
        return migrate(self.data, self.dest, {"Ana": self.user / "stock.toml",
                                              "Bo": self.user / "alt2-bags.toml"})

    def cli_args(self, *characters, extra=()):
        return ["migrate", "--from-data", str(self.data),
                *[x for c in characters for x in ("--character", c)], *extra]

    def test_migrate_copies_files_into_home_layout(self):
        self.run_migrate()
        self.assertIn("level = 47", (self.dest.character("Ana") / "stock.toml").read_text(encoding="utf-8"))
        self.assertIn("bag_slots = 30", (self.dest.character("Bo") / "stock.toml").read_text(encoding="utf-8"))
        self.assertFalse((self.dest.character("Bo") / "bags.toml").exists())
        self.assertEqual(profile.load_house(self.dest.house), 4242)
        self.assertTrue(self.dest.prices.exists())
        self.assertTrue((self.dest.gamedata / "Recipes.lua").exists())
        prof = profile.load_profile(self.dest.profile)
        self.assertEqual(set(prof.characters), {"Ana", "Bo"})
        self.assertEqual(prof.faction, "alliance")

    def test_migrate_adds_goals(self):
        from yap_forever.config import Goal, load_stock
        (self.user / "stock.toml").write_text("level = 47\ntarget = 200\n[items]\n", encoding="utf-8")
        self.run_migrate()
        s = load_stock(self.dest.character("Ana") / "stock.toml")
        self.assertEqual(s.goals, {164: Goal(skill=200), 333: Goal(skill=200)})

    def test_migrate_keeps_existing_goals(self):
        text = "level = 47\n[items]\n\n[goals]\ntailoring = 150\n"
        (self.user / "stock.toml").write_text(text, encoding="utf-8")
        self.run_migrate()
        self.assertEqual((self.dest.character("Ana") / "stock.toml").read_text(encoding="utf-8"), text)

    def test_migrate_copies_and_keeps_existing_profile(self):
        self.dest.root.mkdir(parents=True)
        self.dest.profile.write_text('region = "us"\nfaction = "horde"\n', encoding="utf-8")
        self.run_migrate()
        self.assertEqual(self.dest.profile.read_text(encoding="utf-8"), 'region = "us"\nfaction = "horde"\n')

    def test_migrate_never_copies_config_json(self):
        self.run_migrate()
        for p in self.dest.root.rglob("*"):
            if p.is_file():
                self.assertNotIn("SECRET-ID", p.read_text(encoding="utf-8", errors="replace"), p)
        self.assertFalse(self.dest.credentials.exists())



class SameFilesForEveryCharacterTests(MigrateTests):
    def test_every_stock_file_gets_goals_by_its_content(self):
        from yap_forever.config import Goal, load_stock
        (self.user / "other.toml").write_text("level = 10\ntarget = 150\n[items]\n", encoding="utf-8")
        migrate(self.data, self.dest, {"Ana": self.user / "stock.toml", "Bo": self.user / "other.toml"})
        self.assertEqual(load_stock(self.dest.character("Ana") / "stock.toml").goals,
                         {164: Goal(skill=225), 333: Goal(skill=225)})
        self.assertEqual(load_stock(self.dest.character("Bo") / "stock.toml").goals,
                         {164: Goal(skill=150), 333: Goal(skill=150)})

    def test_a_converted_character_gets_no_goals(self):
        from yap_forever.config import load_stock
        self.run_migrate()
        self.assertEqual(load_stock(self.dest.character("Bo") / "stock.toml").goals, {})
        self.assertEqual(load_stock(self.dest.character("Bo") / "stock.toml").bag_slots, 30)

    def test_two_bags_files_are_both_converted(self):
        (self.user / "third.toml").write_text('profs = ["alchemy"]\nbag_slots = 10\n', encoding="utf-8")
        actions = migrate(self.data, self.dest, {"Bo": self.user / "alt2-bags.toml", "Cy": self.user / "third.toml"})
        for name in ("Bo", "Cy"):
            self.assertTrue((self.dest.character(name) / "stock.toml").exists(), name)
        self.assertEqual(set(profile.load_profile(self.dest.profile).characters), {"Bo", "Cy"})
        self.assertTrue(any("check level, [skills]" in a for a in actions), actions)

    def test_a_converted_character_keeps_an_existing_stock_file(self):
        stock = self.dest.character("Bo") / "stock.toml"
        stock.parent.mkdir(parents=True)
        stock.write_text("level = 9\n", encoding="utf-8")
        actions = self.run_migrate()
        self.assertEqual(stock.read_text(encoding="utf-8"), "level = 9\n")
        self.assertTrue(any(a.startswith("kept") and str(stock) in a for a in actions), actions)

    def test_a_stock_file_keeps_an_existing_stock_file_and_gets_no_goals(self):
        stock = self.dest.character("Ana") / "stock.toml"
        stock.parent.mkdir(parents=True)
        stock.write_text("level = 9\n", encoding="utf-8")
        actions = self.run_migrate()
        self.assertEqual(stock.read_text(encoding="utf-8"), "level = 9\n")
        self.assertTrue(any(a == f"kept {stock}" for a in actions), actions)
        self.assertFalse(any("goals" in a and str(stock) in a for a in actions), actions)

    def test_a_missing_file_is_skipped(self):
        actions = migrate(self.data, self.dest, {"Ana": self.user / "nope.toml"})
        self.assertTrue(any("nope.toml (not found)" in a for a in actions), actions)
        self.assertEqual(set(profile.load_profile(self.dest.profile).characters), {"Ana"})


class NamesWithSpacesTests(MigrateTests):
    def test_names_with_spaces_and_accents_load(self):
        migrate(self.data, self.dest, {"Ana Brightforge": self.user / "stock.toml",
                                       "Élise Brightforge": self.user / "alt2-bags.toml"})
        prof = profile.load_profile(self.dest.profile)
        self.assertEqual(set(prof.characters), {"Ana Brightforge", "Élise Brightforge"})
        self.assertTrue((self.dest.character("Ana Brightforge") / "stock.toml").exists())


class MigrateCliTests(MigrateTests):
    def run_cli(self, argv):
        import contextlib, io
        from yap_forever import cli
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(argv, self.dest)
        return code, out.getvalue()

    def test_cli_migrate_takes_every_character_the_same_way(self):
        code, out = self.run_cli(self.cli_args(f"Ana={self.user / 'stock.toml'}",
                                               f"Bo={self.user / 'alt2-bags.toml'}"))
        self.assertEqual(code, 0, out)
        for name in ("Ana", "Bo"):
            self.assertTrue((self.dest.character(name) / "stock.toml").exists(), name)

    def test_cli_migrate_order_and_role_do_not_matter(self):
        code, out = self.run_cli(self.cli_args(f"Bo={self.user / 'alt2-bags.toml'}",
                                               f"Ana={self.user / 'stock.toml'}"))
        self.assertEqual(code, 0, out)
        self.assertIn("level = 47", (self.dest.character("Ana") / "stock.toml").read_text(encoding="utf-8"))
        self.assertIn("bag_slots = 30", (self.dest.character("Bo") / "stock.toml").read_text(encoding="utf-8"))

    def test_cli_migrate_needs_a_character(self):
        import contextlib, io
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.run_cli(self.cli_args())

    def test_cli_migrate_malformed_character_names_the_flag(self):
        for bad in ("Ana", "=file", "Ana="):
            code, out = self.run_cli(self.cli_args(bad))
            self.assertEqual(code, 1, bad)
            self.assertIn(f"--character needs NAME=FILE, got {bad!r}", out)
        self.assertFalse(self.dest.root.exists())

    def test_cli_migrate_repeated_name_is_refused(self):
        code, out = self.run_cli(self.cli_args(f"Ana={self.user / 'stock.toml'}",
                                               f"Ana={self.user / 'alt2-bags.toml'}"))
        self.assertEqual(code, 1)
        self.assertIn("twice", out)

    def test_cli_migrate_old_flags_are_gone(self):
        import contextlib, io
        for flag in ("--main", "--alt", "--from-user"):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.run_cli(self.cli_args(f"Ana={self.user / 'stock.toml'}", extra=(flag, "x")))

    def test_cli_migrate_damaged_file_says_which_and_writes_nothing(self):
        (self.user / "alt2-bags.toml").write_text("profs = [", encoding="utf-8")
        code, out = self.run_cli(self.cli_args(f"Ana={self.user / 'stock.toml'}",
                                               f"Bo={self.user / 'alt2-bags.toml'}"))
        self.assertEqual(code, 1)
        self.assertIn("alt2-bags.toml", out)
        self.assertFalse(self.dest.root.exists())

    def test_cli_migrate_region_ruleset_faction(self):
        code, _ = self.run_cli(self.cli_args(f"Ana={self.user / 'stock.toml'}",
                                             extra=("--region", "us", "--ruleset", "3", "--faction", "horde")))
        self.assertEqual(code, 0)
        prof = profile.load_profile(self.dest.profile)
        self.assertEqual((prof.region, prof.ruleset, prof.faction), ("us", 3, "horde"))
        saved = json.loads(self.dest.house.read_text(encoding="utf-8"))
        self.assertEqual((saved["house"], saved["region"], saved["ruleset"]), (4242, "us", 3))

    def test_cli_migrate_defaults_to_eu_alliance(self):
        self.run_cli(self.cli_args(f"Ana={self.user / 'stock.toml'}"))
        prof = profile.load_profile(self.dest.profile)
        self.assertEqual((prof.region, prof.ruleset, prof.faction), ("eu", 2, "alliance"))


if __name__ == "__main__":
    unittest.main()
