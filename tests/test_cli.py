import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

from yap_forever import cli, settings
from yap_forever.__main__ import python_too_old


def run(argv, paths):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(argv, paths)
    return code, out.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.paths = settings.paths(Path(self._tmp.name) / "home")

    def tearDown(self):
        self._tmp.cleanup()

    def test_python_too_old_message(self):
        self.assertEqual(python_too_old((3, 10)), "yap-forever needs Python 3.11 or newer; you have 3.10.")
        self.assertIsNone(python_too_old((3, 11)))

    def test_main_module_defines_on_old_python(self):
        # Python < 3.10 evaluates annotations like "str | None" when a function is defined, which
        # would crash before the version message. Only a lazily-evaluated module is safe there.
        import ast
        src = (Path(cli.__file__).parent / "__main__.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        lazy = any(isinstance(n, ast.ImportFrom) and n.module == "__future__"
                   and any(a.name == "annotations" for a in n.names) for n in tree.body)
        unions = [n for n in ast.walk(tree) if isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr)]
        self.assertTrue(lazy or not unions)

    def test_init_prints_cyrillic_home_on_ansi_console(self):
        # Windows pipes stdout in the ANSI code page; Claude Code reads it through a pipe.
        import subprocess
        import sys
        home = Path(self._tmp.name) / "Мой дом"
        env = dict(os.environ, YAP_FOREVER_HOME=str(home), PYTHONIOENCODING="cp1252")
        r = subprocess.run([sys.executable, "-m", "yap_forever", "init"], env=env,
                           cwd=Path(cli.__file__).parent.parent, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace")[-300:])
        self.assertTrue((home / "profile.toml").exists())

    def test_command_hint_windows(self):
        self.assertEqual(cli.command_hint("check", "nt"), "py -3 -m yap_forever check")
        self.assertEqual(cli.command_hint("check", "posix"), "python3 -m yap_forever check")

    def test_init_creates_files_and_keeps_existing(self):
        code, _ = run(["init"], self.paths)
        self.assertEqual(code, 0)
        for p in (self.paths.profile, self.paths.credentials, self.paths.cache, self.paths.reports):
            self.assertTrue(p.exists(), p)
        self.paths.profile.write_text('region = "us"\nfaction = "horde"\n', encoding="utf-8")
        run(["init"], self.paths)
        self.assertEqual(self.paths.profile.read_text(encoding="utf-8"), 'region = "us"\nfaction = "horde"\n')

    @unittest.skipIf(os.name == "nt", "file modes are POSIX only")
    def test_init_credentials_mode_600(self):
        run(["init"], self.paths)
        self.assertEqual(self.paths.credentials.stat().st_mode & 0o777, 0o600)

    def test_check_reports_missing_credentials(self):
        run(["init"], self.paths)
        code, out = run(["check", "--offline"], self.paths)
        self.assertEqual(code, 1)
        line = next(l for l in out.splitlines() if l.startswith("credentials"))
        self.assertIn("MISSING:", line)
        self.assertIn(str(self.paths.credentials), line)
        self.assertIn("develop.battle.net", line)

    def test_prices_without_house_names_probe(self):
        run(["init"], self.paths)
        code, out = run(["prices"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn(cli.command_hint("probe"), out)

    def test_plan_without_prices_names_next_step(self):
        run(["init"], self.paths)
        code, out = run(["plan", "--character", "Firstname Lastname"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn(cli.command_hint("prices"), out)

    def test_plan_offline_game_data_names_network(self):
        import urllib.error
        from unittest import mock
        run(["init"], self.paths)
        self.paths.prices.write_text('{"snapshot_time": "t", "listings": {}}', encoding="utf-8")
        stock = self.paths.character("Firstname Lastname") / "stock.toml"
        stock.parent.mkdir(parents=True)
        stock.write_text("level = 20\n[items]\n", encoding="utf-8")
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn("network", out)

    def test_plan_refuses_prices_from_another_house(self):
        from yap_forever import profile
        run(["init"], self.paths)
        profile.save_house(self.paths.house, 11, "eu", 2)
        self.paths.prices.write_text('{"snapshot_time": "t", "house": 10, "region": "eu", "ruleset": 2, '
                                     '"listings": {}}', encoding="utf-8")
        stock = self.paths.character("Firstname Lastname") / "stock.toml"
        stock.parent.mkdir(parents=True)
        stock.write_text("level = 20\n[items]\n", encoding="utf-8")
        code, out = run(["plan", "--character", "Firstname Lastname"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn(cli.command_hint("prices"), out)
        self.assertIn("house 10", out)

    def ready_home(self):
        import shutil
        run(["init"], self.paths)
        shutil.copytree(Path(__file__).parent / "fixtures" / "gamedata", self.paths.gamedata)
        self.paths.prices.write_text('{"snapshot_time": "t", "listings": {"2835": [[20, 500]]}}', encoding="utf-8")
        stock = self.paths.character("Firstname Lastname") / "stock.toml"
        stock.parent.mkdir(parents=True)
        stock.write_text("level = 20\n[items]\n", encoding="utf-8")
        return stock

    def test_plan_writes_both_routes(self):
        self.ready_home()
        code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"], self.paths)
        self.assertEqual(code, 0, out)
        self.assertIn("Least gold", out)
        self.assertIn("Least total value", out)
        for name in ("guide-gold", "guide-value", "plan-gold", "plan-value"):
            self.assertTrue(list(self.paths.reports.glob(f"*-{name}.md")), name)

    def guide_text(self):
        (path,) = self.paths.reports.glob("*-guide-gold.md")
        return path.read_text(encoding="utf-8")

    def test_plan_with_damaged_trainer_file_still_renders_and_says_why(self):
        self.ready_home()
        (self.paths.gamedata / "foreverNpcDB.lua").write_text("QuestieDB.npcData = [[return {", encoding="utf-8")
        code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"], self.paths)
        self.assertEqual(code, 0, out)
        self.assertNotIn("Traceback", out)
        text = self.guide_text()
        self.assertEqual(text.count("Trainer names are left out"), 1)
        self.assertIn("foreverNpcDB.lua is damaged", text)

    def test_plan_offline_with_trainer_files_missing_still_renders(self):
        import urllib.error
        from unittest import mock
        self.ready_home()
        for name in ("foreverNpcDB.lua", "foreverObjectDB.lua", "AreaTable.csv"):
            (self.paths.gamedata / name).unlink()
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"], self.paths)
        self.assertEqual(code, 0, out)
        self.assertIn("Trainer names are left out", self.guide_text())

    def test_plan_passes_the_profile_faction_to_the_guide(self):
        from unittest import mock
        self.ready_home()
        with mock.patch("yap_forever.plan.render_guide", return_value="guide") as guide:
            code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:20"], self.paths)
        self.assertEqual(code, 0, out)
        info = guide.call_args.args[7 + 1]  # trainer_info follows alts
        self.assertEqual(info.faction, "alliance")

    def test_plan_uses_saved_goals(self):
        stock = self.ready_home()
        stock.write_text("level = 20\n[items]\n\n[goals]\nblacksmithing = 20\n", encoding="utf-8")
        code, out = run(["plan", "--character", "Firstname Lastname"], self.paths)
        self.assertEqual(code, 0, out)

    def test_plan_without_goals_names_flag(self):
        self.ready_home()
        code, out = run(["plan", "--character", "Firstname Lastname"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn("--prof blacksmithing:225", out)

    def test_plan_bad_recipe_target_names_it(self):
        self.ready_home()
        code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "blacksmithing:Golden Nothing"],
                        self.paths)
        self.assertEqual(code, 1)
        self.assertIn("no Blacksmithing recipe called 'Golden Nothing'", out)

    def test_plan_bad_prof_flag(self):
        self.ready_home()
        code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "cooking:150"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn("unknown profession", out)

    def test_plan_rejects_three_professions_or_a_repeat(self):
        self.ready_home()
        for flags in (["blacksmithing:20", "enchanting:20", "tailoring:20"], ["blacksmithing:20", "blacksmithing:30"]):
            argv = ["plan", "--character", "Firstname Lastname"] + [x for f in flags for x in ("--prof", f)]
            code, out = run(argv, self.paths)
            self.assertEqual(code, 1, flags)
            self.assertIn("one or two different professions", out)

    def test_plan_numeric_profession_must_be_known(self):
        self.ready_home()
        code, out = run(["plan", "--character", "Firstname Lastname", "--prof", "129:20"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn("unknown profession", out)

    def test_plan_rejects_three_saved_goals(self):
        self.ready_home()
        stock = self.paths.character("Firstname Lastname") / "stock.toml"
        stock.write_text("level = 20\n[items]\n\n[goals]\nblacksmithing = 20\nenchanting = 20\ntailoring = 20\n",
                         encoding="utf-8")
        code, out = run(["plan", "--character", "Firstname Lastname"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn("plan one or two at a time", out)

    def test_plan_unknown_character_lists_known(self):
        run(["init"], self.paths)
        code, out = run(["plan", "--character", "Bob"], self.paths)
        self.assertEqual(code, 1)
        self.assertIn("Firstname Lastname", out)


if __name__ == "__main__":
    unittest.main()
